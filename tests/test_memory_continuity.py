"""A1–A5 continuity boundaries, using only disposable SQLite state."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from hutch.lifecycle import IllegalTransition, LeaseLost
from hutch.models import Bot, Event, EventType, Run, RunStatus, Task
from hutch.store import RevisionConflict, Store
from tests.test_delegated_wait import _parent_and_child


def _conversation_run(store):
    bot = store.create_bot(Bot(name="continuity-boundaries", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(bot.id, "continuity", idem_key="continuity-create",
                                                request_hash="continuity-create")
    run = Run(bot_id=bot.id, prompt="Keep the original constraint.")
    store.submit_conversation_message(conversation["id"], run.prompt, run, Task(bot_id=bot.id, prompt=run.prompt),
                                      idem_key="continuity-run", request_hash="continuity-run")
    source = store.list_conversation_messages(conversation["id"])[0]
    return conversation, run, source


@pytest.mark.parametrize("dispatched", [False, True], ids=["before-acceptance", "after-dispatch-before-ack"])
def test_a2_submission_identity_and_ambiguity_survive_store_restart(store, config, dispatched):
    _conversation, run, _source = _conversation_run(store)
    claimed = store.claim_run(run.id, "continuity-worker", 120)
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    before = store.prepare_opencode_submission(run_id=run.id, fence=claimed.fence,
                                               binding_key="binding", session_id="native-session")
    if dispatched:
        store.mark_opencode_submission(run_id=run.id, fence=claimed.fence, state="dispatched")
    store.close()

    reopened = Store(config)
    try:
        after = reopened.prepare_opencode_submission(run_id=run.id, fence=claimed.fence,
                                                     binding_key="binding", session_id="native-session")
        assert after["submission_id"] == before["submission_id"]
        assert after["state"] == ("dispatched" if dispatched else "prepared")
        if dispatched:
            with pytest.raises(ValueError, match="reconcile"):
                reopened.prepare_opencode_submission(run_id=run.id, fence=claimed.fence,
                                                       binding_key="other", session_id="replacement")
        else:
            rebound = reopened.prepare_opencode_submission(run_id=run.id, fence=claimed.fence,
                                                           binding_key="binding", session_id="replacement")
            assert rebound["submission_id"] == before["submission_id"]
    finally:
        reopened.close()


def test_a4_failed_checkpoint_pointer_write_preserves_revision_and_canonical_history(store):
    conversation, _run, source = _conversation_run(store)
    original = {"constraints": [{"text": "Keep the original constraint.", "message_id": source["id"]}]}
    store.update_conversation_task_state(conversation["id"], original, expected_revision=0)
    messages = store.list_conversation_messages(conversation["id"])
    with store._tx() as db:
        db.execute("CREATE TRIGGER fail_task_state_pointer BEFORE UPDATE ON conversation_task_state "
                   "BEGIN SELECT RAISE(ABORT, 'injected checkpoint storage failure'); END")

    with pytest.raises(sqlite3.IntegrityError, match="checkpoint storage failure"):
        store.update_conversation_task_state(conversation["id"], {"constraints": []}, expected_revision=1)
    current = store.conversation_task_state(conversation["id"])
    assert current["revision"] == 1 and current["state"]["constraints"] == original["constraints"]
    assert store._db.execute("SELECT COUNT(*) FROM conversation_task_state_revisions").fetchone()[0] == 1
    assert store.list_conversation_messages(conversation["id"]) == messages


def test_a4_concurrent_corrections_supersede_once_without_rewriting_old_state(store, config):
    conversation, _run, source = _conversation_run(store)
    original = {"constraints": [{"text": "Original constraint.", "message_id": source["id"]}]}
    store.update_conversation_task_state(conversation["id"], original, expected_revision=0)
    old_revision = tuple(store._db.execute("SELECT * FROM conversation_task_state_revisions").fetchone())
    peer = Store(config)
    try:
        def correct(connection, text):
            try:
                return connection.update_conversation_task_state(conversation["id"], {
                    "constraints": [{"text": text, "message_id": source["id"]}]}, expected_revision=1)
            except RevisionConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(correct, store, "Correction one."), pool.submit(correct, peer, "Correction two.")]
            winners = [result for future in futures if (result := future.result()) is not None]
        assert len(winners) == 1
        assert winners[0]["revision"] == 2 and winners[0]["supersedes_revision"] == 1
        assert tuple(store._db.execute("SELECT * FROM conversation_task_state_revisions WHERE revision=1").fetchone()) == old_revision
    finally:
        peer.close()


def test_a4_results_require_same_conversation_done_receipts_not_commitment_text(store):
    conversation, run, source = _conversation_run(store)
    claimed = store.claim_run(run.id, "continuity-result-owner", 120)
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    pending = {"commitments": [{"text": "Produce a result.", "message_id": source["id"]}]}
    store.update_conversation_task_state(conversation["id"], pending, expected_revision=0)
    result = {"results": [{"text": "Result produced.", "message_id": source["id"]}]}
    with pytest.raises(ValueError, match="receipt"):
        store.update_conversation_task_state(conversation["id"], result, expected_revision=1)
    action = store.begin_action(run.id, "fixture", "continuity-result", "fs", fence=claimed.fence,
                                arguments={"operation": "synthetic-result"}, authority={}, scope={})
    result["results"][0]["receipt_id"] = action
    with pytest.raises(ValueError, match="not succeeded"):
        store.update_conversation_task_state(conversation["id"], result, expected_revision=1)
    store.finish_action(action, "done", expected_fence=claimed.fence)
    saved = store.update_conversation_task_state(conversation["id"], result, expected_revision=1)
    assert saved["revision"] == 2 and saved["state"]["results"][0]["receipt_id"] == action
    assert store.list_conversation_messages(conversation["id"])[0]["content"] == run.prompt
    other, _ = store.create_conversation(run.bot_id, "isolated", idem_key="isolated", request_hash="isolated")
    other_run = Run(bot_id=run.bot_id, prompt="An unrelated task.")
    store.submit_conversation_message(other["id"], other_run.prompt, other_run,
                                      Task(bot_id=run.bot_id, prompt=other_run.prompt),
                                      idem_key="isolated-run", request_hash="isolated-run")
    other_source = store.list_conversation_messages(other["id"])[0]
    with pytest.raises(ValueError, match="not succeeded in this conversation"):
        store.update_conversation_task_state(other["id"], {"results": [{
            "text": "Claim another conversation's result.", "message_id": other_source["id"], "receipt_id": action}]},
            expected_revision=0)
    assert store.conversation_task_state(other["id"]) is None


def test_a5_committed_child_result_delivers_logically_once_after_parent_restart(store, config):
    parent, child = _parent_and_child(store)
    store.transition_run(parent.id, RunStatus.waiting_child, fence=parent.fence,
                         child_wait=(child.id, {"version": 1, "messages": [], "tool_call": {"id": "once"}}))
    owner = store.claim_run(child.id, "completed-child", 120)
    store.transition_run(child.id, RunStatus.running, fence=owner.fence)
    store.append_event(Event(run_id=child.id, type=EventType.message, owner_fence=owner.fence,
                             data={"role": "assistant", "content": "Committed child result."}))
    store.flush_events()
    store.transition_run(child.id, RunStatus.succeeded, fence=owner.fence)
    store.close()  # result is committed; the parent has not consumed it

    reopened = Store(config)
    try:
        assert reopened.promote_child_wait(parent.id) is not None
        assert reopened.promote_child_wait(parent.id) is None
        resumed = reopened.claim_run(parent.id, "resumed-parent", 120)
        reopened.transition_run(parent.id, RunStatus.running, fence=resumed.fence)
        assert reopened.mark_child_wait_resuming(parent.id, resumed.fence)["child_run_id"] == child.id
        assert reopened.complete_child_wait(parent.id, resumed.fence) is True
        assert reopened.complete_child_wait(parent.id, resumed.fence) is False
        assert sum(event.type is EventType.message for event in reopened.list_events(child.id)) == 1
        with pytest.raises(LeaseLost):
            reopened.transition_run(parent.id, RunStatus.succeeded, fence=parent.fence)
        assert reopened.get_run(child.id).status is RunStatus.succeeded
    finally:
        reopened.close()


def test_a2_opencode_builtin_opencode_share_one_persisted_context(store, config, tmp_path, monkeypatch):
    """An operator switching the Bot's runtime keeps one canonical conversation history."""
    from hutch.approvals import ApprovalGate
    from hutch.models import ApprovalMode, Limits, RuntimeKind
    from hutch.runtime.builtin import BuiltinRuntime, reset_connection_cache
    from hutch.runtime.ladder import reset_provider_cache
    from hutch.runtime.opencode import OpenCodeRuntime
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext
    from tests.fakes import FakeOllama, agent_script
    from tests.test_runtime_builtin import run_it
    from tests.test_runtime_opencode import FakeOpenCodeServer, completed_assistant

    reset_provider_cache()
    reset_connection_cache()
    bot = store.create_bot(Bot(name="cross-runtime-continuity", model="opencode/test/model",
                               runtime=RuntimeKind.opencode, tools=[], approval_mode=ApprovalMode.auto,
                               selfcheck=False,
                               limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000)))
    conversation, _ = store.create_conversation(bot.id, "cross-runtime", idem_key="cross-create",
                                                request_hash="cross-create")
    workspace = tmp_path / "cross-ws"
    workspace.mkdir(exist_ok=True)

    def turn(prompt: str, key: str) -> Run:
        run = Run(bot_id=bot.id, prompt=prompt)
        store.submit_conversation_message(conversation["id"], prompt, run, Task(bot_id=bot.id, prompt=prompt),
                                          idem_key=key, request_hash=key)
        return run

    def context_for(run: Run) -> ToolContext:
        current = store.get_bot(bot.id)

        def emit(event):
            store.append_event(event)

        gate = ApprovalGate(store, current, run, PolicyEngine(), emit, poll_seconds=0.05)
        return ToolContext(bot=current, run=run, store=store, policy=gate.policy, gate=gate,
                           config=config, workspace=workspace, emit=emit)

    def assistant_of(run: Run) -> dict:
        return next(message for message in store.list_conversation_messages(conversation["id"])
                    if message["run_id"] == run.id and message["role"] == "assistant")

    # Turn 1: OpenCode answers and commits canonical assistant history.
    first = turn("First request.", "cross-first")
    fake_one = FakeOpenCodeServer()
    fake_one.assistant = completed_assistant("OpenCode answer one.")
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake_one)
    run_it(OpenCodeRuntime(), first, context_for(first), {})
    store.flush_events()
    first_answer = assistant_of(first)
    assert first_answer["content"] == "OpenCode answer one."

    # Turn 2: the same Bot switches to Builtin; it must receive OpenCode's history.
    bot.runtime = RuntimeKind.builtin
    bot.model = "ollama/fake:8b"
    store.upsert_bot(bot, preserve_schedules=True)
    second = turn("Second request.", "cross-second")
    second_context = store.get_run(second.id).conversation_context
    assert any(item.get("source", {}).get("message_id") == first_answer["id"] for item in second_context)
    assert any(item.get("source_kind") == "message" for item in second_context)
    ollama = FakeOllama({"fake:8b": {}})
    monkeypatch.setenv("OLLAMA_HOST", ollama.url)
    ollama.script = agent_script([{"content": "Builtin answer two."}])
    try:
        run_it(BuiltinRuntime(), second, context_for(second), {})
    finally:
        ollama.close()
    store.flush_events()
    request_messages = ollama.of("/api/chat")[0]["body"]["messages"]
    assert any(message.get("role") == "assistant" and "OpenCode answer one." in message.get("content", "")
               for message in request_messages)
    second_answer = assistant_of(second)
    assert second_answer["content"] == "Builtin answer two."

    # Turn 3: switch back to OpenCode; both prior answers arrive as one
    # provenance-labelled selection, with the current request exactly once.
    bot.runtime = RuntimeKind.opencode
    bot.model = "opencode/test/model"
    store.upsert_bot(bot, preserve_schedules=True)
    third = turn("Third request.", "cross-third")
    fake_two = FakeOpenCodeServer()
    fake_two.assistant = completed_assistant("OpenCode answer two.")
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer", lambda *a, **k: fake_two)
    run_it(OpenCodeRuntime(), third, context_for(third), {})
    assert "OpenCode answer one." in fake_two.prompt_text
    assert "Builtin answer two." in fake_two.prompt_text
    assert fake_two.prompt_text.count("Third request.") == 1
    assert '"source_kind":"message"' in fake_two.prompt_text
    third_context = store.get_run(third.id).conversation_context
    source_ids = {item.get("source", {}).get("message_id") for item in third_context}
    assert {first_answer["id"], second_answer["id"]} <= source_ids


def test_a4_artifact_references_are_canonical_and_hostile_paths_are_rejected(store):
    conversation, _run, source = _conversation_run(store)
    valid = {"artifacts": [{"text": "Launch report artifact.", "message_id": source["id"],
                            "artifact": "artifacts/004-launch-report.txt"}]}
    saved = store.update_conversation_task_state(conversation["id"], valid, expected_revision=0)
    assert saved["state"]["artifacts"][0]["artifact"] == "artifacts/004-launch-report.txt"
    assert store.conversation_task_state(conversation["id"])["state"]["artifacts"][0]["artifact"] == \
        "artifacts/004-launch-report.txt"
    manifest = next(item for item in store.preview_conversation_context(conversation["id"])
                    if item["source_kind"] == "task_state_snapshot")
    assert "artifacts/004-launch-report.txt" in manifest["content"]
    for hostile in ("artifacts/../secret.txt", "artifacts/004-UPPER.txt", "files/004-a.txt",
                    "artifacts/004-a.txt.exe", "/absolute/004-a.txt"):
        with pytest.raises(ValueError, match="bounded run artifact"):
            store.update_conversation_task_state(conversation["id"], {"artifacts": [{
                "text": "Hostile reference.", "message_id": source["id"], "artifact": hostile}]},
                expected_revision=1)
    assert store.conversation_task_state(conversation["id"])["revision"] == 1
    assert store._db.execute("SELECT COUNT(*) FROM conversation_task_state_revisions").fetchone()[0] == 1


def test_a5_cancelled_parent_never_resumes_from_a_late_child_result(store):
    parent, child = _parent_and_child(store)
    store.transition_run(parent.id, RunStatus.waiting_child, fence=parent.fence,
                         child_wait=(child.id, {"version": 1, "messages": [], "tool_call": {}}))
    owner = store.claim_run(child.id, "late-child", 120)
    store.transition_run(child.id, RunStatus.running, fence=owner.fence)
    store.request_cancel_tree(parent.id)
    store.transition_run(child.id, RunStatus.stopped, fence=owner.fence)
    assert store.finalize_child_wait_cancel(parent.id).status is RunStatus.stopped
    with pytest.raises(IllegalTransition):
        store.transition_run(child.id, RunStatus.succeeded, fence=owner.fence)
    store.append_event(Event(run_id=child.id, type=EventType.message, owner_fence=owner.fence,
                             data={"role": "assistant", "content": "Late answer must not be delivered."}))
    assert not any(event.type is EventType.message for event in store.list_events(child.id))
    assert store.promote_child_wait(parent.id) is None
    assert store.child_wait_continuation(parent.id)["state"] == "cancelled"
