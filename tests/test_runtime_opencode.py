import json
from pathlib import Path

import pytest

from hutch.models import ApprovalMode, EventType, Limits, RuntimeKind
from hutch.runtime import RunAborted
from hutch.runtime.opencode import OpenCodeRuntime, _agent_definition
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

    def __init__(self, *_args, **kwargs):
        self.process = None
        self.prompt_called = False
        self.permissions_calls = 0
        self.replies: list[tuple[str, str]] = []
        self.assistant: dict = {}
        self.pending: list[dict] = []
        self.fail_after_prompt = False
        self.prompt_text = ""
        self.init_kwargs = dict(kwargs)

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
        self.prompt_text = _text
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


class MultiSessionFakeOpenCodeServer(FakeOpenCodeServer):
    """Session cache fixture that can retain and then lose individual sessions."""

    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.created_sessions: list[str] = []
        self.deleted_sessions: set[str] = set()

    def create_session(self, **_kwargs):
        session_id = f"ses_{len(self.created_sessions) + 1}"
        self.created_sessions.append(session_id)
        return {"id": session_id}

    def session(self, session_id):
        if session_id in self.deleted_sessions:
            raise OpenCodeServerError("session no longer exists", status=404)
        return {"id": session_id}


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
    assert latest.steps == 1 and latest.tokens == 123
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


def test_runtime_uses_the_admitted_context_selection_not_a_native_history_page(
        store, config, tmp_path, monkeypatch):
    ctx, run, _emitted, tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    run.conversation_context = [
        {"role": "user", "content": "same wording", "context_version": 1, "source_kind": "message",
         "source": {"message_id": "msg_one", "conversation_id": "conv", "seq": 61, "high_watermark": 64},
         "truncated": False},
        {"role": "user", "content": "same wording", "context_version": 1, "source_kind": "message",
         "source": {"message_id": "msg_two", "conversation_id": "conv", "seq": 62, "high_watermark": 64},
         "truncated": False},
        {"role": "assistant", "content": "partial", "context_version": 1, "source_kind": "message",
         "source": {"message_id": "msg_partial", "conversation_id": "conv", "seq": 64,
                    "incomplete": True, "reason": "length", "high_watermark": 64}, "truncated": False},
    ]
    fake = FakeOpenCodeServer()
    fake.assistant = completed_assistant("context received")
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)

    assert run_it(OpenCodeRuntime(), run, ctx, tools) == "context received"
    assert "<hutch_conversation_context_json>" in fake.prompt_text
    assert fake.prompt_text.count("same wording") == 2
    assert '"message_id":"msg_one"' in fake.prompt_text
    assert '"message_id":"msg_two"' in fake.prompt_text
    assert '"incomplete":true' in fake.prompt_text and '"reason":"length"' in fake.prompt_text


def test_runtime_brokers_a_shell_permission_once_and_never_emits_always(
        store, config, tmp_path, monkeypatch):
    ctx, run, _emitted, tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.pending = [{"id": "per_1", "sessionID": "ses_fake", "action": "edit",
                     "resources": ["notes.txt"], "message": "change a file"}]
    fake.assistant = completed_assistant()
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)

    run_it(OpenCodeRuntime(), run, ctx, tools)

    assert fake.replies == [("per_1", "once")]
    assert all(decision != "always" for _request, decision in fake.replies)
    assert not store.pending_approvals()


def test_an_auto_bot_still_cannot_auto_approve_a_denied_opencode_shell(
        store, config, tmp_path, monkeypatch):
    ctx, run, _emitted, tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.pending = [{"id": "per_shell", "sessionID": "ses_fake", "action": "bash",
                     "resources": ["rm -rf /"]}]
    fake.assistant = completed_assistant()
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)

    run_it(OpenCodeRuntime(), run, ctx, tools)

    assert fake.replies == [("per_shell", "reject")]
    assert not store.pending_approvals()


def test_opencode_agent_permissions_follow_the_reviewed_tool_list():
    _agent_id, empty = _agent_definition(
        "b", title="B", instructions="help", provider_id="openai", model_id="gpt-test",
        tool_names=set(), workspace="/tmp/ws")
    empty_rules = {(rule["action"], rule["effect"]) for rule in empty["permissions"]}
    assert ("shell", "deny") in empty_rules and ("bash", "deny") in empty_rules
    assert ("edit", "deny") in empty_rules and ("webfetch", "deny") in empty_rules

    _agent_id, allowed = _agent_definition(
        "b", title="B", instructions="help", provider_id="openai", model_id="gpt-test",
        tool_names={"shell", "write_file", "web_fetch"}, workspace="/tmp/ws")
    allowed_rules = {(rule["action"], rule["effect"]) for rule in allowed["permissions"]}
    assert ("shell", "ask") in allowed_rules and ("bash", "ask") in allowed_rules
    assert ("edit", "ask") in allowed_rules and ("webfetch", "ask") in allowed_rules

    _agent_id, documents = _agent_definition(
        "b", title="B", instructions="help", provider_id="test", model_id="model",
        tool_names={"create_document", "revise_document", "create_media", "run_python"}, workspace="/tmp/ws")
    assert all(rule["effect"] == "deny" for rule in documents["permissions"]
               if rule["action"] in {"edit", "write"})

    _agent_id, brokered = _agent_definition(
        "b", title="B", instructions="help", provider_id="test", model_id="model",
        tool_names={"write_file", "shell", "web_fetch"}, workspace="/tmp/ws",
        brokered_tools=frozenset({"write_file", "shell", "web_fetch"}))
    assert all(rule["effect"] == "deny" for rule in brokered["permissions"]
               if rule["action"] in {"edit", "write", "bash", "shell", "webfetch", "websearch"})


@pytest.mark.parametrize("value,expected", [(0, 0.0), (0.001, 0.001), (None, None),
    ("invalid", None), (float("nan"), None), (-1, None), (True, None)])
def test_opencode_reported_zero_cost_is_distinct_from_missing_or_invalid_usage(value, expected):
    from hutch.runtime.opencode import _assistant_usage
    assert _assistant_usage({"tokens": None, "cost": value}) == (0, 0, 0, expected)


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
    submission = store.opencode_submission(run.id)
    # Prompt admission was acknowledged before the later session failure; the
    # use of its subsequent work remains uncertain in the usage reservation.
    assert submission and submission["state"] == "acknowledged"


def test_session_binding_rebuilds_when_context_cursor_is_stale(store, config, tmp_path, monkeypatch):
    ctx, run, _emitted, _tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    run.conversation_id = "conv_cursor"
    run.conversation_context = [{"role": "user", "content": "new canonical turn", "context_version": 1,
                                "source_kind": "message",
                                "source": {"message_id": "msg_new", "conversation_id": "conv_cursor",
                                           "seq": 7, "high_watermark": 7}, "truncated": False}]
    fake = FakeOpenCodeServer()
    runtime = OpenCodeRuntime()
    agent_id, agent = _agent_definition(ctx.bot.id, title=ctx.bot.name, instructions=ctx.bot.instructions,
                                        provider_id="test", model_id="model", tool_names=set(),
                                        workspace=str(ctx.workspace))
    first, created, key = runtime._session_for(fake, ctx, run, "test", "model", agent_id, agent)
    assert first == "ses_fake" and created is True
    binding = store.opencode_session_binding(key)
    assert binding and binding["sync_high_watermark"] == 7
    store.bind_opencode_session(binding_key=key, bot_id=binding["bot_id"], route_hash=binding["route_hash"],
                                workspace=binding["workspace"], policy_hash=binding["policy_hash"],
                                agent_id=binding["agent_id"], session_id=binding["session_id"],
                                sync_high_watermark=6)
    second, rebuilt, _ = runtime._session_for(fake, ctx, run, "test", "model", agent_id, agent)
    assert second == "ses_fake" and rebuilt is True


def test_session_bindings_keep_route_affinity_and_rebuild_deleted_native_sessions(store, config, tmp_path):
    ctx, run, _emitted, _tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    run.conversation_id = "conv-route-affinity"
    runtime = OpenCodeRuntime()
    server = MultiSessionFakeOpenCodeServer()

    agent_a_id, agent_a = _agent_definition(ctx.bot.id, title=ctx.bot.name, instructions=ctx.bot.instructions,
                                             provider_id="test", model_id="model-a", tool_names=set(),
                                             workspace=str(ctx.workspace))
    first_a, created_a, key_a = runtime._session_for(server, ctx, run, "test", "model-a", agent_a_id, agent_a)
    agent_b_id, agent_b = _agent_definition(ctx.bot.id, title=ctx.bot.name, instructions=ctx.bot.instructions,
                                             provider_id="test", model_id="model-b", tool_names=set(),
                                             workspace=str(ctx.workspace))
    first_b, created_b, key_b = runtime._session_for(server, ctx, run, "test", "model-b", agent_b_id, agent_b)
    reused_a, recreated_a, reused_key_a = runtime._session_for(
        server, ctx, run, "test", "model-a", agent_a_id, agent_a)

    assert (first_a, created_a) == ("ses_1", True)
    assert (first_b, created_b) == ("ses_2", True)
    assert key_a != key_b
    assert (reused_a, recreated_a, reused_key_a) == ("ses_1", False, key_a)

    server.deleted_sessions.add(first_a)
    rebuilt_a, rebuilt, rebuilt_key = runtime._session_for(server, ctx, run, "test", "model-a", agent_a_id, agent_a)
    assert (rebuilt_a, rebuilt, rebuilt_key) == ("ses_3", True, key_a)
    assert store.opencode_session_binding(key_a)["session_id"] == "ses_3"


def test_native_cache_cannot_add_history_outside_the_exact_admitted_run(store, config, tmp_path):
    from hutch.models import Run

    ctx, run, _events, _tools = build(store, config, tmp_path, model="opencode/test/model", tools=())
    run.conversation_id = "conv-cache-bound"
    run.conversation_context = [{"role": "user", "content": "first selection"}]
    runtime = OpenCodeRuntime()
    server = MultiSessionFakeOpenCodeServer()
    agent_id, agent = _agent_definition(ctx.bot.id, title=ctx.bot.name, instructions=ctx.bot.instructions,
                                        provider_id="test", model_id="model", tool_names=set(),
                                        workspace=str(ctx.workspace))
    first, _, first_key = runtime._session_for(server, ctx, run, "test", "model", agent_id, agent)
    # Task-state edits and explicit context overrides can change selection
    # without advancing a canonical-message high watermark.
    run.conversation_context = [{"role": "user", "content": "corrected selection"}]
    corrected, rebuilt, corrected_key = runtime._session_for(server, ctx, run, "test", "model", agent_id, agent)
    assert rebuilt and corrected != first and corrected_key != first_key
    other = Run(bot_id=run.bot_id, conversation_id=run.conversation_id, prompt=run.prompt,
                conversation_context=run.conversation_context)
    later, rebuilt, _ = runtime._session_for(server, ctx, other, "test", "model", agent_id, agent)
    assert rebuilt and later != corrected


@pytest.mark.parametrize("state", ["dispatched", "acknowledged", "uncertain"])
def test_adapter_refuses_ambiguous_submission_before_rebinding_or_reserving(
        store, config, tmp_path, monkeypatch, state):
    from hutch.models import RunStatus

    ctx, run, _events, tools = build(store, config, tmp_path, model="opencode/test/model", tools=())
    owned = store.claim_run(run.id, "ambiguous-owner", 120)
    store.transition_run(run.id, RunStatus.running, fence=owned.fence)
    run.fence = owned.fence
    store.prepare_opencode_submission(run_id=run.id, fence=run.fence,
                                      binding_key="old-binding", session_id="deleted-native-session")
    store.mark_opencode_submission(run_id=run.id, fence=run.fence, state="dispatched")
    if state != "dispatched":
        store.mark_opencode_submission(run_id=run.id, fence=run.fence, state=state)
    fake = MultiSessionFakeOpenCodeServer()
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake)

    with pytest.raises(RunAborted) as caught:
        run_it(OpenCodeRuntime(), run, ctx, tools)
    assert caught.value.reason == "outcome_unknown"
    assert not fake.prompt_called and not fake.created_sessions
    assert not store.unresolved_usage_reservations(), "a local refusal must not create another charge hold"
    assert store.opencode_submission(run.id)["session_id"] == "deleted-native-session"


def test_corrupt_binding_row_rebuilds_instead_of_reusing_cache(store, config, tmp_path):
    ctx, run, _events, _tools = build(store, config, tmp_path, model="opencode/test/model", tools=())
    run.conversation_id = "conv-corrupt-binding"
    runtime = OpenCodeRuntime()
    server = MultiSessionFakeOpenCodeServer()
    agent_id, agent = _agent_definition(ctx.bot.id, title=ctx.bot.name, instructions=ctx.bot.instructions,
                                        provider_id="test", model_id="model", tool_names=set(),
                                        workspace=str(ctx.workspace))
    first, _, key = runtime._session_for(server, ctx, run, "test", "model", agent_id, agent)
    # Model a corrupted or tampered affinity row: the derived key still matches,
    # but stored affinity data can no longer be trusted.
    with store._tx() as db:
        db.execute("UPDATE opencode_session_bindings SET policy_hash='corrupt' WHERE binding_key=?", (key,))
    second, rebuilt, same_key = runtime._session_for(server, ctx, run, "test", "model", agent_id, agent)
    assert rebuilt and same_key == key and second != first
    assert store.opencode_session_binding(key)["session_id"] == second
    assert store.opencode_session_binding(key)["policy_hash"] != "corrupt"


def test_submission_state_retains_ambiguity_and_refuses_retransmission(store, config, tmp_path):
    from hutch.models import Bot, Run, RunStatus, Task

    bot = store.create_bot(Bot(name="submission-state", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "submission", idem_key="submission-conversation",
                                                request_hash="submission-conversation")
    run = Run(bot_id=bot.id, prompt="Do the non-idempotent thing")
    store.submit_conversation_message(conversation["id"], run.prompt, run, Task(bot_id=bot.id, prompt=run.prompt),
                                      idem_key="submission-run", request_hash="submission-run")
    claimed = store.claim_run(run.id, "submission-worker", 60)
    assert claimed is not None
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    prepared = store.prepare_opencode_submission(run_id=run.id, fence=claimed.fence,
                                                 binding_key=conversation["id"], session_id="ses_one")
    assert prepared["state"] == "prepared" and prepared["submission_id"].startswith("msg_hutch_")
    store.mark_opencode_submission(run_id=run.id, fence=claimed.fence, state="dispatched")
    retained = store.prepare_opencode_submission(run_id=run.id, fence=claimed.fence,
                                                 binding_key=conversation["id"], session_id="ses_one")
    assert retained["state"] == "dispatched"
    store.mark_opencode_submission(run_id=run.id, fence=claimed.fence, state="uncertain", detail="response lost")
    assert store.opencode_submission(run.id)["state"] == "uncertain"
    with pytest.raises(ValueError, match="cannot become rejected"):
        store.mark_opencode_submission(run_id=run.id, fence=claimed.fence, state="rejected")


def test_stop_between_prepare_and_dispatch_refuses_the_native_call(store, config, tmp_path):
    from hutch.lifecycle import LeaseLost
    from hutch.models import RunStatus

    _ctx, run, _events, _tools = build(store, config, tmp_path, model="opencode/test/model", tools=())
    owned = store.claim_run(run.id, "stop-before-dispatch", 120)
    store.transition_run(run.id, RunStatus.running, fence=owned.fence)
    store.prepare_opencode_submission(run_id=run.id, fence=owned.fence,
                                      binding_key="binding", session_id="session")
    store.request_cancel_tree(run.id)
    with pytest.raises(LeaseLost):
        store.mark_opencode_submission(run_id=run.id, fence=owned.fence, state="dispatched")
    assert store.opencode_submission(run.id)["state"] == "prepared"


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


def test_native_usage_keeps_the_reserved_shared_billing_account_for_every_turn(store, config, tmp_path, monkeypatch):
    from hutch.connections import ConnectionBook
    from hutch.providers.pricing import PriceBook

    ConnectionBook(config.state_dir).add('openai-api', 'opencode', account_id='evaluation-account')
    PriceBook(config.state_dir / 'prices.json').set_price('opencode/test/model', 0, 0,
                                                        source='synthetic known-free fixture')
    store.set_budget_policy(scope_kind='account', scope_id='evaluation-account', reset='lifetime', ceiling_usd=0)
    ctx, run, _events, tools = build(store, config, tmp_path, model='opencode/test/model', tools=(),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    first = completed_assistant('', finish='tool-calls', tokens=(20, 2, 0))
    first['id'] = 'msg_continuation'
    fake.assistant = completed_assistant('Shared account retained', tokens=(30, 3, 0))
    fake.messages = lambda *_args, **_kwargs: [first, fake.assistant] if fake.prompt_called else []
    monkeypatch.setattr('hutch.runtime.opencode.OpenCodeServer', lambda *args, **kwargs: fake)
    assert run_it(OpenCodeRuntime(), run, ctx, tools) == 'Shared account retained'
    assert not store.unresolved_usage_reservations()
    assert store.account_usage_tokens_since('evaluation-account', 3600) == 55
    assert store.account_usage_tokens_since('opencode', 3600) == 0
