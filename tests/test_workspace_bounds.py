"""Bounds of the executable workspace: output caps and runaway cells.

Two layers are exercised. In-child (the kernel, driven directly): the shared
output budget across both streams, the tail caps with honest totals, table
and produced-file caps, and repr bounds. Parent-side (the manager against a
fake child over real pipes): a child that floods the protocol line bound, a
child that hangs and ignores SIGINT (the runaway cell the parent must
terminate), and the fabricated receipts that tell the truth about what was
lost. No bwrap required.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from hutch.workspace import protocol
from hutch.workspace.kernel import Kernel
from hutch.workspace.manager import WorkspaceManager

from tests.test_workspace_manager import fake_spawn, make_manager, wait_for_state


def bare_kernel(tmp_path: Path, **kwargs) -> Kernel:
    return Kernel(workspace=str(tmp_path), generation=3,
                  proto_write=lambda data: len(data), readline=lambda: "",
                  interrupt_main=lambda: None, enable_tracer=True, **kwargs)


def run_exec(kernel: Kernel, code: str, *, timeout_ms: int = 10_000) -> dict:
    return kernel.handle_request({"op": "exec", "id": "wx_bounds", "code": code,
                                  "timeout_ms": timeout_ms})


@pytest.fixture(autouse=True)
def _fast_interrupt_windows(monkeypatch):
    monkeypatch.setattr("hutch.workspace.manager.INTERRUPT_ACK_SECONDS", 0.3)
    monkeypatch.setattr("hutch.workspace.manager.PARENT_RESPONSE_MARGIN_SECONDS", 0.3)


# ------------------------------------------------------------------ in-child caps


def test_output_budget_is_shared_across_both_streams(tmp_path):
    kernel = bare_kernel(tmp_path, output_budget=600)
    response = run_exec(kernel,
                        "import sys\n"
                        "for i in range(40):\n"
                        "    print('out' * 10)\n"            # 120 chars x 40 = 4800 on stdout
                        "    print('err' * 5, file=sys.stderr)\n")  # 30 chars x 40 on stderr
    assert response["receipt"]["status"] == "timeout"
    assert response["receipt"]["stdout_chars_total"] + \
        response["receipt"]["stderr_chars_total"] > 600
    assert len(response["stdout_tail"]) <= protocol.STDOUT_TAIL_CHARS
    assert len(response["stderr_tail"]) <= protocol.STDERR_TAIL_CHARS
    assert response["error"]["type"] == "OutputBudgetExceeded"


def test_tail_preserved_and_total_truthful_on_budget_cut(tmp_path):
    kernel = bare_kernel(tmp_path, output_budget=400)
    response = run_exec(kernel, "for i in range(100):\n    print(f'line {i:03d}')")
    assert response["receipt"]["status"] == "timeout"
    tail = response["stdout_tail"]
    lines = tail.strip().splitlines()
    assert len(lines) >= 10                          # the ring kept the LAST lines before the cut
    assert lines[-1].startswith("line 0")
    last = int(lines[-1].split()[1])
    assert 5 <= last <= 60                           # the cut landed mid-loop, not at the end
    assert response["receipt"]["stdout_chars_total"] > 400


def test_table_preview_caps_at_500_rows_with_true_total(tmp_path):
    kernel = bare_kernel(tmp_path)
    response = run_exec(kernel, "[{'row': i, 'square': i * i} for i in range(1500)]")
    tables = [b for b in response["blocks"] if b["kind"] == "table"]
    assert len(tables) == 1
    payload = tables[0]["payload"]
    assert len(payload["rows"]) == 500
    assert payload["row_total"] == 1500
    assert payload["truncation"]["omitted_rows"] == 1000
    assert "reason" in payload["truncation"]


def test_produced_files_capped_at_32(tmp_path):
    kernel = bare_kernel(tmp_path)
    response = run_exec(kernel,
                        "for i in range(40):\n"
                        "    open(f'f{i:02d}.txt', 'w').write('x')\n"
                        "len(list(__import__('os').listdir('.')))")
    assert response["result_repr"] == "40"
    assert len(response["produced_files"]) == protocol.MAX_PRODUCED_FILES == 32


def test_oversized_result_repr_truncated_with_disclosure(tmp_path):
    kernel = bare_kernel(tmp_path)
    response = run_exec(kernel, "{'k': 'v' * 100_000}")
    assert len(response["result_repr"]) == protocol.RESULT_REPR_CHARS
    assert "omitted" in response["result_repr"]


def test_oversized_stdout_under_budget_keeps_last_4000(tmp_path):
    kernel = bare_kernel(tmp_path)               # default budget: 200k chars
    response = run_exec(kernel, "print('a' * 9000)\nprint('b' * 9000)")
    assert response["receipt"]["status"] == "ok"
    assert len(response["stdout_tail"]) == 4000
    assert response["stdout_tail"].endswith("b" * 3999 + "\n")   # the LAST chars, honestly
    assert response["receipt"]["stdout_chars_total"] == 18002


# ---------------------------------------------------- parent-side: hostile children


def test_protocol_line_flood_is_lost_with_honest_receipt(store, tmp_path):
    """A child that pours 5MB into the protocol channel is terminated; the
    receipt says the outcome was lost, never fabricated as success."""
    manager = make_manager(store, tmp_path, mode="flood")
    response = manager.execute("1", 30_000)
    assert response["status"] == "lost"
    assert response["error"]["type"] == "ProtocolViolation"
    assert response["receipt"]["status"] == "error"
    assert "line bound" in response["receipt"]["note"]
    assert store.get_workspace_session("conv-manager-test")["status"] == "expired"
    assert manager.session_info()["child_alive"] is False
    manager.close()


def test_runaway_cell_that_ignores_sigint_is_terminated_with_a_truthful_timeout(store, tmp_path):
    """The runaway path: the child hangs past every deadline, ignores the
    parent's SIGINT, and is killed; the fabricated receipt admits the output
    was lost instead of inventing tails."""
    manager = make_manager(store, tmp_path, mode="hang")
    started = time.monotonic()
    response = manager.execute("while True: pass", 1_000)
    elapsed = time.monotonic() - started
    assert response["status"] == "timeout"
    assert response["error"]["type"] == "TimeoutError"
    assert response["receipt"]["status"] == "timeout"
    assert "never reported" in response["receipt"]["note"]
    assert "lost" in response["receipt"]["note"]
    assert elapsed < 15                                  # bounded, not forever
    assert manager.session_info()["child_alive"] is False
    assert store.get_workspace_session("conv-manager-test")["status"] == "expired"
    assert manager.session_info()["status"] == "lost"
    manager.close()


def test_kernel_watchdog_terminates_deadline_breach_with_tails(tmp_path):
    """In-child deadline (the normal path): the CHILD reports the timeout, so
    the tails survive. This is the parent-watchdog case's honest sibling."""
    kernel = bare_kernel(tmp_path)
    response = run_exec(kernel,
                        "lines = []\n"
                        "for i in range(10 ** 9):\n"
                        "    lines.append(i)\n"
                        "len(lines)", timeout_ms=250)
    assert response["receipt"]["status"] == "timeout"
    assert response["receipt"]["stdout_chars_total"] == 0   # the cell never printed
    assert response["error"]["type"] == "TimeoutError"


def test_session_recovers_after_a_runaway_with_a_new_generation(store, tmp_path):
    spawns: list[int] = []
    manager = make_manager(store, tmp_path, mode="hang", spawns=spawns)
    first = manager.execute("1", 1_000)
    assert first["status"] == "timeout"
    manager._spawn = fake_spawn(spawns, "normal")           # the next spawn is healthy
    second = manager.execute("2", 30_000)
    assert second["status"] == "ok"
    assert spawns[-1] == 2                                  # new generation after the kill
    assert second["receipt"]["environment_generation"] == 2
    manager.close()
