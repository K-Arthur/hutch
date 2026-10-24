"""Runtime fitting/compaction: overflow after tool results, opt-out honored, manifests durable (LM-3)."""

from __future__ import annotations

import pytest

from hutch.models import ApprovalMode, Escalation
from hutch.runtime import RunAborted

from tests.fakes import FakeOllama, agent_script
from tests.test_runtime_budget_gate import _running
from tests.test_runtime_builtin import build, factory, run_it, runtime


def _overflow_bot(store, config, tmp_path, *, compaction: str = "auto", rounds: int = 8,
                  ctx_tokens: int = 16384, replies_extra: list | None = None):
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    files = []
    for index in range(rounds):
        path = workspace / f"big_{index:02}.txt"
        path.write_text(f"file {index}: a line of readable text for the model to ingest\n" * 1000)  # ~40k chars
        files.append(path.name)
    ol = FakeOllama({"fake:8b": {}})
    replies = [{"tool_calls": [{"name": "read_file", "arguments": {"path": files[index]}}]}
               for index in range(rounds)]
    replies.extend(replies_extra or [{"content": "done after compaction"}])
    base = agent_script(replies)

    def script(body):
        if any("compact part of a conversation" in str(message.get("content", ""))
               for message in body.get("messages", []) if isinstance(message, dict)):
            return {"content": "Summary: the goal is inspecting the files; several reads completed; constraints "
                               "and open questions are unchanged."}
        return base(body)

    ol.script = script
    ctx, run, emitted, tools = build(store, config, tmp_path, mode=ApprovalMode.auto, model="ollama/fake:8b",
                                     num_ctx=ctx_tokens, compaction=compaction)
    return ol, ctx, run, emitted, tools


def _chat_requests(ol: FakeOllama) -> list[dict]:
    return [request["body"] for request in ol.requests if request["path"] == "/api/chat"]


def test_overflow_after_tool_results_compacts_then_continues(store, config, tmp_path):
    ol, ctx, run, emitted, tools = _overflow_bot(store, config, tmp_path)
    run = _running(store, ctx, run)
    assert run_it(runtime(provider_factory=factory(ollama=ol)), run, ctx, tools) == "done after compaction"

    manifests = store.run_compactions(run.id)
    assert manifests and manifests[0]["status"] in ("compacted", "compact_failed")
    assert manifests[0]["status"] == "compacted"
    assert manifests[0]["before_tokens"] > manifests[0]["after_tokens"] > 0
    assert manifests[0]["summary_text"] and manifests[0]["summary_digest"]
    assert manifests[0]["reservation_id"]

    compaction_calls = store._db.execute(
        "SELECT COUNT(*), COALESCE(SUM(cost_usd), 0) FROM usage WHERE run_id = ? AND kind = 'compaction'",
        (run.id,)).fetchone()
    assert compaction_calls[0] >= 1

    final_messages = _chat_requests(ol)[-1]["messages"]
    assert any("<compacted_history>" in str(message.get("content", "")) for message in final_messages)
    seen_calls = False
    for message in final_messages:
        if message.get("tool_calls"):
            seen_calls = True
        if message.get("role") == "tool":
            assert seen_calls, "a tool result survived without its declaring assistant message"


def test_compaction_off_blocks_with_options_and_preserves_history(store, config, tmp_path):
    ol, ctx, run, emitted, tools = _overflow_bot(store, config, tmp_path, compaction="off", rounds=14)
    run = _running(store, ctx, run)
    with pytest.raises(RunAborted) as failure:
        run_it(runtime(provider_factory=factory(ollama=ol)), run, ctx, tools)
    assert failure.value.reason == "context"
    assert "Options:" in failure.value.detail and "history are intact" in failure.value.detail
    assert store.run_compactions(run.id) == []
    # no summarizer request was ever sent: every chat call carried tools from the main loop
    assert all(request.get("tools") for request in _chat_requests(ol))



def test_repeated_compaction_records_every_cycle_and_keeps_canonical_originals(store, config, tmp_path):
    """A4: one run may compact repeatedly; only the model view shrinks, never canonical evidence."""
    from hutch.models import EventType

    ol, ctx, run, emitted, tools = _overflow_bot(store, config, tmp_path, rounds=8)
    run = _running(store, ctx, run)
    assert run_it(runtime(provider_factory=factory(ollama=ol)), run, ctx, tools) == "done after compaction"

    manifests = store.run_compactions(run.id)
    assert len(manifests) >= 2, "one run must record each of its repeated compaction cycles"
    assert store.compaction_count(run.id) == len(manifests)
    for manifest in manifests:
        assert manifest["status"] == "compacted"
        assert manifest["before_tokens"] > manifest["after_tokens"] > 0
        assert manifest["summary_text"] and manifest["summary_digest"] and manifest["reservation_id"]
        assert manifest["actions"], "every cycle keeps its unit-action provenance"

    # Canonical evidence is append-only: compaction rewrote only this run's model view.
    tool_results = [event for event in store.list_events(run.id)
                    if event.type is EventType.tool_result and event.data.get("ok")]
    assert len(tool_results) >= 8, "every read's original tool result stays in the event history"
    assert any("file 0: a line of readable text" in str(event.data.get("output", ""))
               for event in tool_results), "the first read must survive as canonical evidence"

    final_view = str(_chat_requests(ol)[-1]["messages"])
    assert "file 0: a line of readable text" not in final_view, \
        "the oldest read must leave the model view after repeated compaction"
    assert any(f"file {index}: a line of readable text" in final_view for index in (6, 7)), \
        "recent reads must remain in the model view"
    assert run.prompt in final_view, "the initial request survives every compaction verbatim"
    assert "<compacted_history>" in final_view


def test_compaction_stops_at_the_run_cap_and_fails_honestly_with_history_intact(store, config, tmp_path):
    """A4: repeated compaction is bounded; at the cap the run fails loudly instead of fabricating a fit."""
    from hutch.models import EventType
    from hutch.runtime.builtin import MAX_COMPACTIONS_PER_RUN

    ol, ctx, run, emitted, tools = _overflow_bot(store, config, tmp_path, rounds=18)
    run = _running(store, ctx, run)
    with pytest.raises(RunAborted) as failure:
        run_it(runtime(provider_factory=factory(ollama=ol)), run, ctx, tools)
    assert failure.value.reason == "context"
    assert "Options:" in failure.value.detail and "history are intact" in failure.value.detail

    manifests = store.run_compactions(run.id)
    assert len(manifests) == MAX_COMPACTIONS_PER_RUN
    assert all(manifest["status"] == "compacted" for manifest in manifests)
    assert any(event.type.value == "log" and "already compacted" in str(event.data)
               for event in store.list_events(run.id)), "the cap itself must be stated, not silent"

    # The failed fit never rewrites originals: the earliest read's result is still canonical.
    tool_results = [event for event in store.list_events(run.id)
                    if event.type is EventType.tool_result and event.data.get("ok")]
    assert any("file 0: a line of readable text" in str(event.data.get("output", ""))
               for event in tool_results)


def test_known_overflow_after_tool_result_escalates_before_sending_to_small_model(store, config, tmp_path, monkeypatch):
    from tests.fakes import FakeOpenAI

    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    payload = "bounded context escalation evidence " * 275
    (workspace / "large.txt").write_text(payload)
    ol = FakeOllama({"fake:8b": {}, "tiny:1b": {"params": "1.0B", "size": 800_000_000, "ctx": 8192}})

    def script(body):
        if body.get("model") == "fake:8b":
            return {"tool_calls": [{"name": "read_file", "arguments": {"path": "large.txt"}}]}
        return {"content": "escalated answer"}

    ol.script = script
    oai = FakeOpenAI()
    oai.script = lambda body: {"content": "escalated answer"}
    ctx, run, emitted, tools = build(store, config, tmp_path, mode=ApprovalMode.auto,
                                     model="ollama/fake:8b", num_ctx=4096, compaction="off",
                                     escalation=Escalation(to=["openai/gpt-4o-mini"], on_context_overflow=True))
    store.allow_sticky(ctx.bot.id, "escalate:hosted")
    monkeypatch.setattr(ctx.gate, "decide", lambda *args, **kwargs: None)
    run = _running(store, ctx, run)
    try:
        assert run_it(runtime(provider_factory=factory(ollama=ol, oai=oai)), run, ctx, tools) == "escalated answer"
        local_chats = _chat_requests(ol)
        hosted_chats = oai.of("/v1/chat/completions")
        assert len(local_chats) == 1, "the overflowing request must never be sent to the smaller primary"
        assert len(hosted_chats) == 1
        assert payload in str(hosted_chats[0]["body"]["messages"]), "the larger rung must receive the intact tool result"
        assert any(event.type.value == "log" and event.data.get("kind") == "escalation"
                   for event in emitted)
    finally:
        ol.close()
        oai.close()

def test_wrong_window_route_gets_an_honest_block_instead_of_silent_truncation(store, config, tmp_path):
    ol, ctx, run, emitted, tools = _overflow_bot(store, config, tmp_path, rounds=2, ctx_tokens=4096,
                                                 replies_extra=[{"content": "answer"}])
    run = _running(store, ctx, run)
    # 4096-token window, 2048-token reply reserve: the summary input cannot fit, so it must block
    with pytest.raises(RunAborted) as failure:
        run_it(runtime(provider_factory=factory(ollama=ol)), run, ctx, tools)
    assert failure.value.reason == "context"
    assert "does not fit" in failure.value.detail


def test_a_hosted_destination_without_a_known_window_runs_best_effort_without_compaction(store, config, tmp_path):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    oai.script = lambda body: {"content": "ok despite size", "prompt_tokens": 10, "completion_tokens": 2}
    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o",
                                         mode=ApprovalMode.auto, prompt="x" * 200_000)
        run = _running(store, ctx, run)
        assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "ok despite size"
    finally:
        oai.close()
    assert store.run_compactions(run.id) == []
    note = [call for call in emitted if call.type.value == "log" and call.data.get("kind") == "compaction"]
    assert not note, "an unknown window must not silently compact"
