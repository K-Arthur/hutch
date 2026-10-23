import json
from pathlib import Path

import pytest

from hutch.models import ApprovalMode, EventType, Limits, RuntimeKind
from hutch.runtime import RunAborted
from hutch.runtime.opencode import OpenCodeRuntime
from hutch.runtime.opencode_protocol import (
    OpenCodeContract,
    OpenCodeProtocolError,
    SseDecoder,
    parse_permission_request,
    permission_reply_body,
)
from hutch.runtime.opencode_server import OpenCodeModel, OpenCodeServerError
from tests.test_runtime_builtin import build, run_it


FIXTURE = Path(__file__).parent / "fixtures" / "opencode_v2_0_24_contract.json"


def contract_fixture():
    return json.loads(FIXTURE.read_text())


class FakeOpenCodeServer:
    """Deterministic stand-in for the owned local server, with no network or model call."""

    def __init__(self, *_args, **_kwargs):
        self.process = None
        self.prompt_called = False
        self.permissions_calls = 0
        self.replies: list[tuple[str, str]] = []
        self.assistant: dict = {}
        self.pending: list[dict] = []
        self.fail_after_prompt = False

    def start(self):
        return None

    def close(self):
        return None

    def models(self, _directory=None):
        return [OpenCodeModel("test", "model", "Test Model", context=8192, output=1024)]

    def create_session(self, **_kwargs):
        return {"id": "ses_fake"}

    def session(self, _session_id):
        return {"id": "ses_fake", "outcome": "succeeded" if self.assistant else None}

    def prompt(self, _session_id, _text, **_kwargs):
        self.prompt_called = True
        return {"id": "msg_user"}

    def messages(self, _session_id, **_kwargs):
        if not self.prompt_called:
            return []
        if self.fail_after_prompt:
            raise OpenCodeServerError("fixture server disappeared after admission")
        return [self.assistant] if self.assistant else []

    def permissions(self, _session_id):
        self.permissions_calls += 1
        return list(self.pending)

    def reply_permission(self, _session_id, request_id, decision, _message=""):
        self.replies.append((request_id, decision))
        self.pending = [row for row in self.pending if row.get("id") != request_id]

    def interrupt(self, _session_id):
        return None

    def tool_running_message(self):
        return {
            "id": "msg_tool", "type": "assistant", "finish": "tool-calls",
            "time": {"created": 1_700_000_000_000},
            "content": [{"type": "tool", "id": "tool_1", "name": "edit", "state": {
                "status": "running", "input": {"path": "a.txt"}, "metadata": {},
            }}],
            "tokens": {"input": 10, "output": 1, "reasoning": 0, "cache": {"read": 0, "write": 0}},
            "cost": 0,
        }


def completed_assistant(text="OK", *, finish="stop", tokens=(120, 3, 40), cost=0.0):
    return {
        "id": "msg_assistant", "type": "assistant", "finish": finish,
        "time": {"created": 1_700_000_000_000, "completed": 1_700_000_001_000},
        "content": [{"type": "text", "text": text}] if text else [],
        "tokens": {"input": tokens[0], "output": tokens[1], "reasoning": 0,
                   "cache": {"read": tokens[2], "write": 0}},
        "cost": cost,
    }


def test_installed_2024_contract_is_experimental_and_event_loss_is_explicit():
    fixture = contract_fixture()
    api = {key: value for key, value in fixture.items() if key != "installed_binary"}
    contract = OpenCodeContract.from_openapi(api)

    assert fixture["installed_binary"] == "opencode v2.0.24"
    assert contract.api_version == "0.0.1"
    assert contract.api_experimental
    assert contract.event_stream_volatile
    assert not contract.safe_for_durable_hutch_execution
    assert set(contract.permission_fields) >= {"id", "sessionID", "action", "resources"}


def test_runtime_records_a_real_completion_usage_and_assistant_message(store, config, tmp_path, monkeypatch):
    ctx, run, emitted, tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.assistant = completed_assistant("hello from OpenCode")
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)

    result = run_it(OpenCodeRuntime(), run, ctx, tools)

    assert result == "hello from OpenCode"
    messages = [event for event in emitted if event.type is EventType.message
                and event.data.get("role") == "assistant"]
    assert messages and messages[-1].data["content"] == "hello from OpenCode"
    latest = store.get_run(run.id)
    assert (latest.prompt_tokens, latest.completion_tokens, latest.cached_tokens) == (120, 3, 40)
    assert not store.unresolved_usage_reservations(), "usage must settle after reported totals"


def test_runtime_retains_truncated_output_but_never_reports_completion(store, config, tmp_path, monkeypatch):
    ctx, run, emitted, tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.assistant = completed_assistant("half an answer", finish="length")
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)

    with pytest.raises(RunAborted) as exc:
        run_it(OpenCodeRuntime(), run, ctx, tools)
    assert exc.value.reason == "length"
    partial = [event for event in emitted if event.type is EventType.message
               and event.data.get("incomplete")]
    assert partial and partial[0].data["content"] == "half an answer"


def test_runtime_brokers_a_shell_permission_once_and_never_emits_always(
        store, config, tmp_path, monkeypatch):
    ctx, run, _emitted, tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.pending = [{"id": "per_1", "sessionID": "ses_fake", "action": "bash",
                     "resources": ["echo hello"], "message": "run a command"}]
    fake.assistant = completed_assistant()
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)

    run_it(OpenCodeRuntime(), run, ctx, tools)

    assert fake.replies == [("per_1", "once")]
    assert all(decision != "always" for _request, decision in fake.replies)
    assert not store.pending_approvals()


def test_runtime_marks_a_stop_during_a_running_tool_as_unknown(store, config, tmp_path, monkeypatch):
    ctx, run, _emitted, tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.assistant = fake.tool_running_message()
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)
    calls = {"n": 0}

    def stop_after_first_poll():
        if not fake.prompt_called:
            return False
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(RunAborted) as exc:
        run_it(OpenCodeRuntime(), run, ctx, tools, stop=stop_after_first_poll)
    assert exc.value.reason == "outcome_unknown"
    assert "tool was running" in exc.value.detail


def test_runtime_marks_usage_uncertain_when_server_disappears_after_admission(
        store, config, tmp_path, monkeypatch):
    ctx, run, _emitted, tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.fail_after_prompt = True
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)

    with pytest.raises(RunAborted) as exc:
        run_it(OpenCodeRuntime(), run, ctx, tools)
    assert exc.value.reason == "outcome_unknown"
    held = store.unresolved_usage_reservations()
    assert held and held[0]["status"] == "uncertain"


def test_sse_decoder_handles_chunked_crlf_multiline_data_and_unicode():
    decoder = SseDecoder()
    source = (
        ': keepalive\r\nevent: permission.updated\r\nid: evt-7\r\n'
        'data: {"message":"first\u2028line",\r\n'
        'data: "ok":true}\r\n\r\n'
    ).encode("utf-8")
    events = []
    for size in (1, 2, 7, 3, 13, 5, 19):
        if not source:
            break
        events.extend(decoder.feed(source[:size]))
        source = source[size:]
    events.extend(decoder.feed(source))
    decoder.finish()

    assert len(events) == 1
    assert events[0].event == "permission.updated"
    assert events[0].event_id == "evt-7"
    assert events[0].json_payload() == {"message": "first\u2028line", "ok": True}


def test_last_event_id_persists_within_stream_and_json_encoded_twice_payload_is_decoded():
    decoder = SseDecoder()
    first = decoder.feed(b'id: durable-id\ndata: "{\\"kind\\":\\"tick\\"}"\n\n')
    second = decoder.feed(b'data: {"kind":"next"}\n\n')
    assert first[0].json_payload() == {"kind": "tick"}
    assert second[0].event_id == "durable-id"
    assert second[0].json_payload() == {"kind": "next"}


def test_sse_rejects_oversized_invalid_and_truncated_frames():
    decoder = SseDecoder(max_event_bytes=16)
    with pytest.raises(OpenCodeProtocolError, match="byte limit"):
        decoder.feed(b"data: 12345678901234567890")
    with pytest.raises(OpenCodeProtocolError, match="invalid UTF-8"):
        SseDecoder().feed(b"data: \xff\n\n")
    decoder = SseDecoder()
    decoder.feed(b"data: {\"ok\":true}\n")
    with pytest.raises(OpenCodeProtocolError, match="ended within an event"):
        decoder.finish()


def test_hutch_permission_mapping_never_grants_open_code_always():
    assert permission_reply_body(approve_once=True) == {"decision": "once"}
    assert permission_reply_body(approve_once=False) == {"decision": "reject"}
    assert "always" not in permission_reply_body(approve_once=True).values()


def test_permission_request_preserves_destination_and_exact_resources():
    result = parse_permission_request({
        "id": "per_fixture",
        "sessionID": "ses_fixture",
        "action": "edit",
        "resources": ["src/answer.py", "src/answer.py:1-3"],
        "message": "Write a value",
        "metadata": {"revision": "sha256:abc"},
        "source": {"kind": "tool"},
    })
    assert result == {
        "id": "per_fixture",
        "session_id": "ses_fixture",
        "action": "edit",
        "resources": ("src/answer.py", "src/answer.py:1-3"),
        "message": "Write a value",
        "source": {"kind": "tool"},
        "metadata": {"revision": "sha256:abc"},
    }
    with pytest.raises(OpenCodeProtocolError):
        parse_permission_request({"id": "per_1", "sessionID": "ses_1", "action": "edit", "resources": [1]})
