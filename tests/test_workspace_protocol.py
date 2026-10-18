"""The workspace kernel against a fake stdio pair: protocol v1 behaviour.

Covers the pieces the contract and the failure research pin down: receipts
bound to the EXACT submitted code, bounded stdout/stderr/result_repr, redacted
tracebacks with no locals, table auto-preview bounds, emit_block validation,
the produced-files convention, and honest interruption/timeout statuses. No
real bubblewrap is needed here — the kernel is driven directly.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from hutch.workspace import protocol
from hutch.workspace.kernel import Kernel


class FakeStdio:
    """A fake stdio pair: preloaded request lines in, protocol lines out."""

    def __init__(self, request_lines: list[str] | None = None):
        self._lines = list(request_lines or [])
        self.written: list[str] = []

    def readline(self) -> str:
        return self._lines.pop(0) if self._lines else ""

    def write(self, data) -> int:
        text = bytes(data).decode("utf-8")
        self.written.append(text)
        return len(data)

    def responses(self) -> list[dict]:
        out = []
        for chunk in self.written:
            for line in chunk.splitlines():
                if line.strip():
                    out.append(json.loads(line))
        return out


def bare_kernel(tmp_path: Path, **kwargs) -> tuple[Kernel, FakeStdio]:
    """A kernel whose protocol channel is recorded; drive it with direct calls."""
    stdio = FakeStdio()
    kernel = Kernel(workspace=str(tmp_path), generation=3,
                    proto_write=stdio.write, readline=stdio.readline,
                    interrupt_main=lambda: None, enable_tracer=True, **kwargs)
    return kernel, stdio


def run_exec(kernel: Kernel, code: str, *, timeout_ms: int = 10_000, request_id: str = "wx_test") -> dict:
    return kernel.handle_request({"op": "exec", "id": request_id, "code": code,
                                  "timeout_ms": timeout_ms})


# ------------------------------------------------------------------- protocol units


def test_encode_decode_round_trip_and_object_enforcement():
    message = {"op": "exec", "id": "wx_1", "code": "print('héllo')\n"}
    line = protocol.encode_message(message)
    assert line.endswith("\n") and "\n" not in line[:-1]
    assert protocol.decode_message(line) == message
    with pytest.raises(ValueError):
        protocol.decode_message("[1, 2]\n")            # a JSON array is not a message
    with pytest.raises(ValueError):
        protocol.decode_message("garbage\n")


def test_truncate_discloses_the_omission():
    assert protocol.truncate("short", 10) == "short"
    bounded = protocol.truncate("x" * 5000, 100)
    assert len(bounded) == 100 and "4" in bounded and "omitted" in bounded


def test_redact_path_keeps_workspace_and_synthetic_names():
    ws = Path("/state/workspaces/conv1")
    assert protocol.redact_path("/state/workspaces/conv1/out.png", ws) == "/state/workspaces/conv1/out.png"
    assert protocol.redact_path("<cell>", ws) == "<cell>"
    assert protocol.redact_path("/usr/lib/python3/json/decoder.py", ws) == "<redacted>"
    assert protocol.redact_path("/home/user/.ssh/id_rsa", ws) == "<redacted>"


def test_fabricate_receipt_only_admits_honest_statuses():
    receipt = protocol.fabricate_receipt(ordinal=2, generation=5, started_at="s", finished_at="f",
                                         status="timeout", source_sha256="0" * 64, note="why")
    assert receipt["status"] == "timeout" and receipt["note"] == "why"
    assert receipt["stdout_chars_total"] == 0          # the loss is stated, not faked
    with pytest.raises(ValueError):
        protocol.fabricate_receipt(ordinal=1, generation=1, started_at="s", finished_at="f",
                                   status="ok", source_sha256="0" * 64, note="nope")


def test_source_hash_is_over_the_exact_submitted_code():
    code = "total = 40 + 2\nprint(f\"the answer is {total}\")\n"
    assert protocol.sha256_of_source(code) == hashlib.sha256(code.encode()).hexdigest()


def test_table_preview_shapes_and_bounds():
    payload = protocol.table_preview_from_value({"city": "Lisbon", "population": 545000})
    assert payload["columns"] == [{"name": "key", "dtype": "text"},
                                  {"name": "value", "dtype": "unknown"}]   # mixed value types
    assert payload["rows"] == [["city", "Lisbon"], ["population", 545000]]
    assert payload["row_total"] == 2 and "truncation" not in payload

    numeric = protocol.table_preview_from_value({"a": 1, "b": 2.5})
    assert numeric["columns"][1] == {"name": "value", "dtype": "number"}

    scalar_list = protocol.table_preview_from_value([1, 2.5, "x", True, None])
    assert scalar_list["columns"][0]["dtype"] == "unknown"
    assert scalar_list["row_total"] == 5

    long_list = protocol.table_preview_from_value(list(range(700)))
    assert len(long_list["rows"]) == protocol.TABLE_PREVIEW_ROWS == 500
    assert long_list["row_total"] == 700
    assert long_list["truncation"]["omitted_rows"] == 200

    tabular = protocol.table_preview_from_value([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    assert [c["name"] for c in tabular["columns"]] == ["a", "b"]
    assert tabular["rows"] == [[1, "x"], [2, "y"]]

    assert protocol.table_preview_from_value({"bad": [1, 2]}) is None      # non-scalar value
    assert protocol.table_preview_from_value([{"a": 1}, {"b": 2}]) is None  # non-uniform rows
    assert protocol.table_preview_from_value("just a string") is None
    assert protocol.table_preview_from_value([{f"c{i}": i for i in range(65)}]) is None  # too wide


def test_produced_files_are_hashed_bounded_and_new_only(tmp_path):
    (tmp_path / "old.txt").write_text("old")
    before = protocol.snapshot_workspace(tmp_path)
    for i in range(40):
        (tmp_path / f"new-{i:02d}.txt").write_text(f"content {i}")
    after = protocol.snapshot_workspace(tmp_path)
    produced = protocol.produced_files_between(before, after, tmp_path)
    assert len(produced) == protocol.MAX_PRODUCED_FILES == 32   # bounded at 32
    expected_names = {f"new-{i:02d}.txt" for i in range(40)}
    assert all(f["name"] in expected_names for f in produced)
    target = next(f for f in produced if f["name"] == "new-39.txt")   # newest first
    assert target["bytes"] == len("content 39")
    assert target["sha256"] == hashlib.sha256(b"content 39").hexdigest()

    # a file CHANGED after the snapshot counts as produced too
    before2 = protocol.snapshot_workspace(tmp_path)
    (tmp_path / "new-00.txt").write_text("rewritten")
    produced2 = protocol.produced_files_between(before2, protocol.snapshot_workspace(tmp_path), tmp_path)
    assert [f["name"] for f in produced2] == ["new-00.txt"]
    assert produced2[0]["sha256"] == hashlib.sha256(b"rewritten").hexdigest()

    (tmp_path / "huge.bin").write_bytes(b"x" * (protocol.FILE_HASH_MAX_BYTES + 1))
    after3 = protocol.snapshot_workspace(tmp_path)
    produced3 = protocol.produced_files_between(before2, after3, tmp_path)
    assert all(f["name"] != "huge.bin" for f in produced3)      # never partially hashed and passed off


# ------------------------------------------------------------------- exec + receipts


def test_exec_receipt_binds_source_hash_ordinal_and_generation(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    code = "x = 6\nx * 7"
    response = run_exec(kernel, code)
    assert response["status"] == "ok"
    receipt = response["receipt"]
    assert receipt["status"] == "ok"
    assert receipt["ordinal"] == 1
    assert receipt["environment_generation"] == 3
    assert receipt["source_sha256"] == hashlib.sha256(code.encode()).hexdigest()
    assert response["result_repr"] == "42"
    assert receipt["started_at"] and receipt["finished_at"]
    second = run_exec(kernel, code, request_id="wx_test2")
    assert second["receipt"]["ordinal"] == 2


def test_persistent_namespace_and_reset_ns(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    run_exec(kernel, "accumulated = []\naccumulated.append(1)")
    response = run_exec(kernel, "len(accumulated)")
    assert response["result_repr"] == "1"
    reset = kernel.handle_request({"op": "reset_ns", "id": "wx_r"})
    assert reset["status"] == "ok"
    response = run_exec(kernel, "accumulated", request_id="wx_2")
    assert response["receipt"]["status"] == "error"
    assert response["error"]["type"] == "NameError"


def test_inspect_csv_is_injected_and_matches_the_upload_report(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    csv_file = tmp_path / "readings.csv"
    csv_file.write_text("a,a\n1,2\n3\n", encoding="utf-8")
    run_exec(kernel,
             "report = inspect_csv(%r)\n"
             "(report['duplicate_columns'], report['malformed_rows']['count'])" % str(csv_file))
    # The response above must be a clean result; assert via a second exec reading it back.
    response = run_exec(kernel, "(report['duplicate_columns'], report['malformed_rows']['count'])",
                        request_id="wx_csv")
    assert response["receipt"]["status"] == "ok"
    assert response["result_repr"] == "(['a'], 1)"


def test_stdout_stderr_captured_and_result_auto_repr(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "print('to stdout')\nimport sys\nprint('to stderr', file=sys.stderr)\n'value'")
    assert response["stdout_tail"] == "to stdout\n"
    assert response["stderr_tail"] == "to stderr\n"
    assert response["receipt"]["stdout_chars_total"] == len("to stdout\n")
    assert response["result_repr"] == "'value'"


def test_stdin_syntax_error_is_an_error_receipt_not_a_crash(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "def broken(:\n    pass")
    assert response["receipt"]["status"] == "error"
    assert response["error"]["type"] == "SyntaxError"


def test_empty_code_is_a_protocol_error(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "   \n")
    assert response["status"] == "error"
    assert "receipt" not in response


# ------------------------------------------------------- redaction: paths and locals


def test_traceback_paths_outside_workspace_are_redacted(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    code = "import json\npayload = '{bad json'\njson.loads(payload)"
    response = run_exec(kernel, code)
    assert response["receipt"]["status"] == "error"
    frames = response["error"]["redacted_traceback"]
    assert frames, "an error receipt carries the frame list"
    joined = "\n".join(frames)
    assert "<redacted>" in joined                       # stdlib frames, outside the workspace
    assert "json/decoder" not in joined                 # ...and their paths are gone entirely
    assert response["error"]["type"] == "JSONDecodeError"


def test_traceback_never_contains_locals(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    code = ("api_token = 'super-secret-token-value'\n"
            "row_count = 42\n"
            "raise ValueError('boom')\n")
    response = run_exec(kernel, code)
    joined = "\n".join(response["error"]["redacted_traceback"])
    assert "super-secret-token-value" not in joined
    assert "api_token" not in joined and "row_count" not in joined
    assert "boom" in joined                             # the diagnostic itself is kept


# ----------------------------------------------------------------- bounded output


def test_output_budget_terminates_the_cell_honestly(tmp_path):
    kernel, _ = bare_kernel(tmp_path, output_budget=500)
    response = run_exec(kernel, "for i in range(1000):\n    print('x' * 50)")
    assert response["receipt"]["status"] == "timeout"
    assert response["receipt"]["stdout_chars_total"] > 500
    assert len(response["stdout_tail"]) <= protocol.STDOUT_TAIL_CHARS
    assert "output budget" in response["receipt"]["note"]
    assert response["error"]["type"] == "OutputBudgetExceeded"


def test_stdout_tail_is_capped_at_4000_chars(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "print('y' * 9000)")
    assert response["receipt"]["status"] == "ok"
    assert len(response["stdout_tail"]) == protocol.STDOUT_TAIL_CHARS == 4000
    assert response["receipt"]["stdout_chars_total"] == 9001


def test_result_repr_is_capped_at_2000_chars(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "'z' * 50_000")
    assert len(response["result_repr"]) <= protocol.RESULT_REPR_CHARS == 2000
    assert "omitted" in response["result_repr"]


def test_table_auto_preview_from_trailing_expression(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "[{'city': 'Lisbon', 'population': 545_000},\n"
                                " {'city': 'Porto', 'population': 231_000}]")
    tables = [b for b in response["blocks"] if b["kind"] == "table"]
    assert len(tables) == 1
    payload = tables[0]["payload"]
    assert payload["row_total"] == 2
    assert payload["rows"] == [["Lisbon", 545000], ["Porto", 231000]]

    response = run_exec(kernel, "{'a': 1}", request_id="wx_d")
    assert any(b["kind"] == "table" for b in response["blocks"])

    response = run_exec(kernel, "{'obj': object()}", request_id="wx_o")   # not scalars: no table
    assert not any(b["kind"] == "table" for b in response["blocks"])
    assert response["result_repr"]                                        # but the repr is still there


def test_produced_files_reported_after_exec(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "open('answer.txt', 'w').write('the answer is 42\\n')")
    [produced] = response["produced_files"]
    assert produced["name"] == "answer.txt"
    assert produced["sha256"] == hashlib.sha256(b"the answer is 42\n").hexdigest()
    assert produced["bytes"] == 17


def test_pending_files_convention_is_injected(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel,
                        "open('a.csv', 'w').write('x\\n')\n"
                        "open('b.csv', 'w').write('y\\n')\n"
                        "sorted(f['name'] for f in hutch_workspace_pending_files())")
    assert response["result_repr"] == "['a.csv', 'b.csv']"


# --------------------------------------------------------------------- emit_block


def test_emit_block_accepts_a_valid_payload(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel,
                        "emit_block('text', {'content': 'found 42 answers'}, "
                        "text_fallback='Found 42 answers.')\n'ok'")
    emitted = [b for b in response["blocks"] if b["kind"] == "text"]
    assert len(emitted) == 1
    assert emitted[0]["payload"] == {"content": "found 42 answers"}
    assert emitted[0]["text_fallback"] == "Found 42 answers."


def test_emit_block_rejects_an_invalid_payload_visibly(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "emit_block('chart', {'kind': 'bar'})")   # missing series/axes
    assert response["result_repr"] == "False"
    problems = [b for b in response["blocks"] if b["kind"] == "text"
                and "rejected" in b["payload"]["content"]]
    assert problems, "a rejected emission degrades to a visible text block, not silence"


def test_emit_block_without_outputblocks_still_queues(tmp_path, monkeypatch):
    kernel, _ = bare_kernel(tmp_path)
    monkeypatch.setitem(__import__("sys").modules, "hutch.outputblocks", None)
    response = run_exec(kernel, "emit_block('text', {'content': 'queued raw'})")
    assert any(b["kind"] == "text" and b["payload"]["content"] == "queued raw"
               for b in response["blocks"])


def test_emit_block_table_payload_survives_the_real_models(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel,
                        "emit_block('table', {'columns': [{'name': 'city', 'dtype': 'text'}],\n"
                        "                    'rows': [['Lisbon']], 'row_total': 1},\n"
                        "         text_fallback='One city.')")
    assert any(b["kind"] == "table" for b in response["blocks"])
    assert not any(b["kind"] == "text" and "rejected" in str(b.get("payload", {}))
                   for b in response["blocks"])


# --------------------------------------------------------------------- lifecycle


def test_ping_reports_generation_and_ordinal(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    run_exec(kernel, "1", request_id="wx_1")
    pong = kernel.handle_request({"op": "ping", "id": "wx_p"})
    assert pong == {"op": "ping", "id": "wx_p", "status": "ok", "generation": 3, "ordinal": 1}


def test_unknown_op_is_answered_unknown_id(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = kernel.handle_request({"op": "teleport", "id": "wx_x"})
    assert response["status"] == "unknown_id"


def test_second_exec_while_one_is_in_flight_is_busy(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    done = threading.Event()
    result: dict = {}

    def first():
        result["value"] = run_exec(kernel, "while True: pass", timeout_ms=5_000,
                                   request_id="wx_first")
        done.set()

    worker = threading.Thread(target=first, daemon=True)
    worker.start()
    for _ in range(200):
        if kernel._inflight is not None:
            break
        time.sleep(0.01)
    busy = run_exec(kernel, "1", request_id="wx_second")
    assert busy["status"] == "busy"
    assert "receipt" not in busy
    kernel.handle_interrupt({"op": "interrupt", "id": "wx_first"})   # stop the spinning cell
    assert done.wait(5)
    assert result["value"]["receipt"]["status"] == "interrupted"


def test_interrupt_with_unknown_id_is_answered_unknown_id(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    response = kernel.handle_interrupt({"op": "interrupt", "id": "wx_absent"})
    assert response["status"] == "unknown_id"


def test_deadline_terminates_a_spinning_cell_with_status_timeout(tmp_path):
    kernel, _ = bare_kernel(tmp_path)
    start = time.monotonic()
    response = run_exec(kernel, "while True: pass", timeout_ms=200)
    elapsed = time.monotonic() - start
    assert response["receipt"]["status"] == "timeout"
    assert elapsed < 5
    assert response["error"]["type"] == "TimeoutError"


def test_serve_loop_answers_requests_in_order_and_stops_at_eof(tmp_path):
    requests = FakeStdio([
        protocol.encode_message({"op": "ping", "id": "wx_a"}),
        "this is not json\n",
        protocol.encode_message({"op": "exec", "id": "wx_b", "code": "40 + 2", "timeout_ms": 1000}),
    ])
    kernel = Kernel(workspace=str(tmp_path), generation=7,
                    proto_write=requests.write, readline=requests.readline,
                    interrupt_main=lambda: None, enable_tracer=True)
    server = threading.Thread(target=kernel.serve, daemon=True)
    server.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        responses = [r for r in requests.responses() if r["op"] == "ping" or r["op"] == "exec"]
        if len(responses) >= 2:
            break
        time.sleep(0.02)
    responses = requests.responses()
    assert responses[0]["op"] == "hello" and responses[0]["generation"] == 7
    assert responses[0]["protocol"] == protocol.PROTOCOL_VERSION
    by_id = {r["id"]: r for r in responses if r["op"] != "hello"}
    assert by_id["wx_a"]["status"] == "ok"                  # the malformed line was dropped silently
    assert by_id["wx_b"]["receipt"]["status"] == "ok"
    assert by_id["wx_b"]["result_repr"] == "42"


def test_hello_announces_protocol_version(tmp_path):
    kernel, stdio = bare_kernel(tmp_path)
    assert kernel.hello()["protocol"] == 1


def test_trailing_matplotlib_figure_renders_png_into_the_workspace(tmp_path, monkeypatch):
    """matplotlib is a detected extra: with it importable, a trailing Figure
    is rendered to PNG bytes in the workspace (picked up as a produced file);
    the tests must pass without it, so this fakes the import surface."""
    import sys as _sys
    import types

    class FakeFigure:
        def savefig(self, path, format=None):
            assert format == "png"
            Path(path).write_bytes(b"\x89PNG-fake-bytes")

    figure_mod = types.ModuleType("matplotlib.figure")
    figure_mod.Figure = FakeFigure
    mpl_mod = types.ModuleType("matplotlib")
    mpl_mod.figure = figure_mod
    mpl_mod.use = lambda *a, **k: None
    monkeypatch.setitem(_sys.modules, "matplotlib", mpl_mod)
    monkeypatch.setitem(_sys.modules, "matplotlib.figure", figure_mod)

    kernel, _ = bare_kernel(tmp_path)
    response = run_exec(kernel, "import sys as _s\n_s.modules['matplotlib.figure'].Figure()")
    assert response["receipt"]["status"] == "ok"
    [png] = response["produced_files"]
    assert png["name"] == "figure-1.png"
    assert png["sha256"] == hashlib.sha256(b"\x89PNG-fake-bytes").hexdigest()


def test_no_matplotlib_means_no_render_and_no_crash(tmp_path):
    kernel, _ = bare_kernel(tmp_path)      # matplotlib is not installed in the test environment
    response = run_exec(kernel, "object()")
    assert response["receipt"]["status"] == "ok"
    assert response["produced_files"] == []
