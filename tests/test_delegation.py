import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest

from hutch.engine import Engine
from hutch.models import Bot, Event, EventType, InferenceMode, Limits, Run, RunStatus, Task, iso, utcnow
from hutch.store import IdempotencyConflict, SCHEMA_VERSION, Store


def _running_parent(store, capability_snapshot=None):
    bot = store.create_bot(Bot(name="delegate-parent", model="mock/demo", tools=[]))
    capability_snapshot = capability_snapshot or {
        "bot_id": bot.id, "tools": [], "risk_tier": bot.risk_tier.value, "sandbox": bot.sandbox}
    parent = store.submit_run(Run(bot_id=bot.id, prompt="coordinate work"),
                              Task(bot_id=bot.id, prompt="coordinate work"))
    claimed = store.claim_run(parent.id, "delegation-test-owner", 60)
    assert claimed is not None
    return bot, store.transition_run(claimed.id, RunStatus.running, fence=claimed.fence,
                                     capability_snapshot=capability_snapshot)


def _child(store, parent, prompt="inspect one bounded area", key="delegate", parent_budget_cost_usd=None):
    return store.submit_delegated_run(
        parent_run_id=parent.id,
        parent_fence=parent.fence,
        run=Run(bot_id=parent.bot_id, prompt=prompt),
        task=Task(bot_id=parent.bot_id, kind="delegated", prompt=prompt),
        idem_key=key,
        request_hash=f"sha256:{key}",
        parent_budget_cost_usd=parent_budget_cost_usd,
    )


def _failed_workspace_task(store, *, effect: str = "", checkpoint: str | None = "Partial written analysis",
                           terminal_status: RunStatus = RunStatus.failed):
    coordinator = store.create_bot(Bot(name="continuation-coordinator", model="mock/demo", tools=[]))
    specialist = store.create_bot(Bot(name="continuation-specialist", model="mock/demo", tools=[]))
    store.set_workspace_coordinator(coordinator.id)
    store.set_workspace_specialists([specialist.id])
    parent, _ = store.create_conversation(coordinator.id, "Coordinator", idem_key="continuation-parent",
                                          request_hash="continuation-parent")
    source_prompt = "Research a bounded public topic and return a short report."
    source_run = Run(bot_id=coordinator.id, prompt=source_prompt, conversation_id=parent["id"])
    source_task = Task(bot_id=coordinator.id, prompt=source_prompt)
    source_run_id, _ = store.submit_conversation_message(
        parent["id"], source_prompt, source_run, source_task,
        idem_key="continuation-source", request_hash="continuation-source")
    owned_source = store.claim_run(source_run_id, "continuation-source-owner", 60)
    assert owned_source is not None
    store.transition_run(source_run_id, RunStatus.running, fence=owned_source.fence)
    store.append_event(Event(run_id=source_run_id, type=EventType.message,
        data={"role": "assistant", "content": "I prepared a public-information research brief.",
              "message_id": "continuation-source-answer"}, owner_fence=owned_source.fence))
    store.flush_events()
    store.transition_run(source_run_id, RunStatus.succeeded, fence=owned_source.fence)
    source_messages = store.list_conversation_messages(parent["id"])
    source_user = next(message for message in source_messages if message["role"] == "user")
    source_assistant = next(message for message in source_messages if message["role"] == "assistant")

    brief = "Compare two public launch approaches and report their trade-offs."
    assumptions = "Use public information only."
    effective_prompt = brief + "\n\nUser-reviewed assumptions and constraints:\n" + assumptions
    specialist_run = Run(bot_id=specialist.id, prompt=effective_prompt, origin="workspace_task")
    specialist_task = Task(bot_id=specialist.id, prompt=effective_prompt)
    child_run_id, _ = store.submit_workspace_task(
        parent_conversation_id=parent["id"], source_run_id=source_run_id,
        source_user_message_id=source_user["id"], source_assistant_message_id=source_assistant["id"],
        target_bot_id=specialist.id, task_brief=brief, assumptions=assumptions,
        run=specialist_run, task=specialist_task, capability_snapshot=Engine.capability_snapshot(specialist),
        idem_key="continuation-task", request_hash="continuation-task")
    owned_child = store.claim_run(child_run_id, "continuation-child-owner", 60)
    assert owned_child is not None
    store.transition_run(child_run_id, RunStatus.running, fence=owned_child.fence)
    if effect:
        action_id = store.begin_action(child_run_id, "browser", "continuation-effect", effect,
            "opened or changed a public page", fence=owned_child.fence,
            arguments={"url": "https://example.test/"}, authority={}, scope={})
        store.finish_action(action_id, "done", expected_fence=owned_child.fence)
    if checkpoint is not None:
        store.append_event(Event(run_id=child_run_id, type=EventType.message,
            data={"role": "assistant", "content": checkpoint, "message_id": "continuation-checkpoint"},
            owner_fence=owned_child.fence))
    store.flush_events()
    store.transition_run(child_run_id, terminal_status, fence=owned_child.fence,
                         exit_reason="interrupted", error="test interruption")
    task = store.list_workspace_tasks(parent["id"])[0]
    return parent["id"], task, specialist


def test_failed_workspace_task_exposes_only_a_no_effect_committed_continuation(store):
    parent_id, task, _ = _failed_workspace_task(store)
    assert task["status"] == "failed"
    assert task["continuation_available"] is True
    assert task["continuation_checkpoint_kind"] == "assistant_message"
    assert task["continuation_checkpoint_preview"] == "Partial written analysis"


def test_failed_workspace_task_with_any_effect_receipt_cannot_continue(store):
    parent_id, task, _ = _failed_workspace_task(store, effect="web")
    assert task["status"] == "failed"
    assert task["continuation_available"] is False
    assert "effect" in task["continuation_reason"].lower()


def test_outcome_unknown_workspace_task_cannot_continue_without_reconciling_effect(store):
    _, task, _ = _failed_workspace_task(store, terminal_status=RunStatus.outcome_unknown)
    assert task["status"] == "outcome_unknown"
    assert task["continuation_available"] is False
    assert "may have happened" in task["continuation_reason"].lower()


def test_workspace_task_without_assistant_checkpoint_continues_only_from_reviewed_brief(store):
    parent_id, previous, specialist = _failed_workspace_task(store, checkpoint=None)
    assert previous["continuation_available"] is True
    assert previous["continuation_checkpoint_kind"] == "task_submitted"
    new_id, created = store.continue_workspace_task(
        previous["id"], run=Run(bot_id=specialist.id, prompt="", origin="workspace_task"),
        task=Task(bot_id=specialist.id, kind="on_demand", prompt=""),
        capability_snapshot=Engine.capability_snapshot(specialist),
        idem_key="continue-no-assistant-checkpoint", request_hash="continue-no-assistant-checkpoint-v1")
    assert created is True
    continued = next(item for item in store.list_workspace_tasks(parent_id) if item["id"] == new_id)
    run = store.get_run(continued["child_run_id"])
    assert run is not None and run.conversation_context == [{
        "role": "user", "content": "Original reviewed task brief:\nCompare two public launch approaches and report their trade-offs.\n\n"
        "User-reviewed constraints:\nUse public information only."}]


def test_safe_workspace_task_continuation_is_a_new_linked_idempotent_attempt(store):
    parent_id, previous, specialist = _failed_workspace_task(store)
    run = Run(bot_id=specialist.id, prompt="", origin="workspace_task")
    task = Task(bot_id=specialist.id, kind="on_demand", prompt="")
    new_id, created = store.continue_workspace_task(
        previous["id"], run=run, task=task, capability_snapshot=Engine.capability_snapshot(specialist),
        idem_key="continue-workspace-task", request_hash="continue-workspace-task-v1")

    assert created is True
    items = store.list_workspace_tasks(parent_id)
    continued = next(item for item in items if item["id"] == new_id)
    assert continued["continuation_of_task_id"] == previous["id"]
    assert continued["continuation_checkpoint_event_id"] is not None
    assert continued["status"] == "pending"
    assert continued["shared_facts"] == []
    continued_run = store.get_run(continued["child_run_id"])
    assert continued_run is not None and continued_run.status is RunStatus.pending
    assert "Original reviewed task brief:" in continued_run.conversation_context[0]["content"]
    assert "Use public information only." in continued_run.conversation_context[0]["content"]
    assert "untrusted progress" in continued_run.conversation_context[1]["content"]
    assert "Partial written analysis" in continued_run.conversation_context[1]["content"]
    assert "Continue this owner-reviewed task" in continued_run.prompt

    replay, inserted = store.continue_workspace_task(
        previous["id"], run=Run(bot_id=specialist.id, prompt="", origin="workspace_task"),
        task=Task(bot_id=specialist.id, kind="on_demand", prompt=""),
        capability_snapshot=Engine.capability_snapshot(specialist),
        idem_key="continue-workspace-task", request_hash="continue-workspace-task-v1")
    assert inserted is False and replay == new_id
    with pytest.raises(IdempotencyConflict):
        store.continue_workspace_task(
            previous["id"], run=Run(bot_id=specialist.id, prompt="", origin="workspace_task"),
            task=Task(bot_id=specialist.id, kind="on_demand", prompt=""),
            capability_snapshot=Engine.capability_snapshot(specialist),
            idem_key="continue-workspace-task", request_hash="changed-continuation-v2")


def test_workspace_task_with_changed_bot_policy_cannot_continue(store):
    parent_id, previous, specialist = _failed_workspace_task(store)
    changed_bot = specialist.model_copy(update={"tools": ["web_fetch"]})
    store.upsert_bot(changed_bot)
    candidate = store.workspace_task_continuation_candidate(previous["id"])
    assert candidate["available"] is False
    assert "permissions changed" in candidate["reason"].lower()


def _remove_later_conversation_schema(db):
    """Remove schema added after the simulated legacy version before lowering user_version."""
    for trigger in (
        "workspace_task_checkpoint_event_insert", "messages_workspace_task_result_insert",
        "messages_workspace_task_result_update", "messages_pending_question_result_insert",
        "messages_pending_question_result_update", "messages_choice_question_insert",
        "messages_choice_question_update", "conversation_question_definition_immutable",
        "conversation_question_resolve_once", "messages_reply_target_insert", "messages_reply_target_update",
        "workspace_task_fact_share_source_guard", "workspace_task_fact_share_immutable",
        "workspace_task_fact_share_no_delete", "workspace_task_continuation_source_guard",
        "workspace_task_continuation_immutable", "workspace_task_continuation_no_delete",
        "workspace_specialists_reject_coordinator_insert", "workspace_specialists_reject_coordinator_update",
        "workspace_settings_remove_promoted_specialist",
        "conversations_assistant_message_unread", "conversations_user_message_read",
        "resource_outbox_conversations_insert", "resource_outbox_conversations_update",
        "resource_outbox_conversations_delete",
    ):
        db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    db.execute("DROP INDEX IF EXISTS idx_messages_workspace_task_result")
    db.execute("DROP INDEX IF EXISTS idx_conversations_bot_pin_update")
    db.execute("DROP INDEX IF EXISTS idx_documents_conversation")
    db.execute("DROP INDEX IF EXISTS idx_documents_bot")
    db.execute("DROP INDEX IF EXISTS idx_document_versions_run")
    for table in ("document_versions", "documents",
                  "workspace_task_continuations", "workspace_task_fact_shares", "workspace_task_checkpoints",
                  "workspace_tasks", "workspace_specialists", "workspace_settings",
                  "conversation_questions", "google_calendar_grants", "memory_fact_shares", "code_handoffs",
                  "task_templates"):
        db.execute(f"DROP TABLE IF EXISTS {table}")
    columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
    for column in ("workspace_task_result_id", "workspace_task_result_message_id",
                   "workspace_task_result_display_name", "workspace_task_result_content",
                   "workspace_task_result_truncated", "choice_question_id", "reply_to_message_id"):
        if column in columns:
            db.execute(f"ALTER TABLE messages DROP COLUMN {column}")
    conversation_columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
    for column in ("section", "read_seq", "unread", "pinned"):
        if column in conversation_columns:
            db.execute(f"ALTER TABLE conversations DROP COLUMN {column}")


def test_delegated_run_creation_persists_parent_and_replays_exact_command(store):
    bot, parent = _running_parent(store)
    child = Run(bot_id=bot.id, prompt="inspect one bounded area", parent_run_id=parent.id)
    task = Task(bot_id=bot.id, kind="delegated", prompt=child.prompt)

    created, inserted = store.submit_delegated_run(
        parent_run_id=parent.id,
        parent_fence=parent.fence,
        run=child,
        task=task,
        idem_key="delegate-command-1",
        request_hash="sha256:request-one",
    )

    assert inserted is True
    assert created.parent_run_id == parent.id
    assert store.get_run(created.id).parent_run_id == parent.id
    with pytest.raises(sqlite3.IntegrityError, match="run parent is immutable"):
        with store._tx() as db:
            db.execute("UPDATE runs SET parent_run_id = NULL WHERE id = ?", (created.id,))
    replayed, inserted = store.submit_delegated_run(
        parent_run_id=parent.id,
        parent_fence=parent.fence,
        run=Run(bot_id=bot.id, prompt=child.prompt),
        task=Task(bot_id=bot.id, kind="delegated", prompt=child.prompt),
        idem_key="delegate-command-1",
        request_hash="sha256:request-one",
    )
    assert inserted is False
    assert replayed.id == created.id
    store.transition_run(parent.id, RunStatus.succeeded, fence=parent.fence, exit_reason="completed")
    replayed, inserted = store.submit_delegated_run(
        parent_run_id=parent.id,
        parent_fence=parent.fence,
        run=Run(bot_id=bot.id, prompt=child.prompt),
        task=Task(bot_id=bot.id, kind="delegated", prompt=child.prompt),
        idem_key="delegate-command-1",
        request_hash="sha256:request-one",
    )
    assert inserted is False and replayed.id == created.id
    with pytest.raises(IdempotencyConflict):
        store.submit_delegated_run(
            parent_run_id=parent.id,
            parent_fence=parent.fence,
            run=Run(bot_id=bot.id, prompt="changed arguments"),
            task=Task(bot_id=bot.id, kind="delegated", prompt="changed arguments"),
            idem_key="delegate-command-1",
            request_hash="sha256:different-request",
        )


def test_delegated_child_keeps_parent_conversation_attachment_and_context(store):
    bot = store.create_bot(Bot(name="delegate-chat", model="mock/demo", tools=[]))
    conversation, _ = store.create_conversation(
        bot.id, "Delegation", idem_key="conversation-create", request_hash="sha256:conversation")
    parent_run = Run(bot_id=bot.id, prompt="coordinate a short task")
    parent_task = Task(bot_id=bot.id, prompt=parent_run.prompt)
    parent_id, inserted = store.submit_conversation_message(
        conversation["id"], parent_run.prompt, parent_run, parent_task,
        idem_key="conversation-message", request_hash="sha256:message")
    assert inserted is True
    claimed = store.claim_run(parent_id, "delegation-chat-owner", 60)
    assert claimed is not None
    parent = store.transition_run(claimed.id, RunStatus.running, fence=claimed.fence,
                                  capability_snapshot={"bot_id": bot.id, "tools": bot.tools})

    child, _ = _child(store, parent, key="conversation-child")

    assert child.conversation_id == conversation["id"]
    assert child.conversation_context == []
    assert store.get_run(child.id).conversation_context == []
    assert store._db.execute(
        "SELECT 1 FROM conversation_runs WHERE conversation_id = ? AND run_id = ?",
        (conversation["id"], child.id),
    ).fetchone()


def test_delegation_rejects_stale_parent_authority_and_cross_bot_children(store):
    _, parent = _running_parent(store)
    with pytest.raises(ValueError, match="current, live run owner"):
        store.submit_delegated_run(
            parent_run_id=parent.id,
            parent_fence=parent.fence - 1,
            run=Run(bot_id=parent.bot_id, prompt="stale"),
            task=Task(bot_id=parent.bot_id, kind="delegated", prompt="stale"),
            idem_key="stale-delegate",
            request_hash="sha256:stale",
        )

    other = store.create_bot(Bot(name="delegate-other", model="mock/demo", tools=[]))
    with pytest.raises(ValueError, match="bot permissions"):
        store.submit_delegated_run(
            parent_run_id=parent.id,
            parent_fence=parent.fence,
            run=Run(bot_id=other.id, prompt="cross bot"),
            task=Task(bot_id=other.id, kind="delegated", prompt="cross bot"),
            idem_key="cross-bot-delegate",
            request_hash="sha256:cross-bot",
        )
    assert store._db.execute("SELECT COUNT(*) FROM runs WHERE parent_run_id = ?", (parent.id,)).fetchone()[0] == 0


def test_delegation_cannot_link_a_run_to_itself(store):
    _, parent = _running_parent(store)
    task = Task(bot_id=parent.bot_id, kind="delegated", prompt="self link")
    with pytest.raises(sqlite3.IntegrityError, match="runs.id"):
        store.submit_delegated_run(
            parent_run_id=parent.id,
            parent_fence=parent.fence,
            run=Run(id=parent.id, bot_id=parent.bot_id, prompt="self link", parent_run_id=parent.id),
            task=task,
            idem_key="self-link",
            request_hash="sha256:self-link",
        )
    assert store.get_run(parent.id).parent_run_id is None
    assert store._db.execute("SELECT 1 FROM tasks WHERE id = ?", (task.id,)).fetchone() is None


def test_descendants_share_the_root_cost_reservation_and_keep_its_limit(store):
    from hutch.store import UsageBudgetRefusal

    bot, root = _running_parent(store)
    root_reservation = store.reserve_usage(
        run_id=root.id, bot_id=bot.id, provider="vendor-a", account_id="budget-account", model="model-a",
        reserved_tokens=100, reserved_cost_usd=0.70, max_run_cost_usd=1.0, expected_fence=root.fence)
    store.add_usage(root.id, bot.id, "vendor-a", "model-a", 100, 0, cost_usd=0.70,
                    account_id="budget-account", reservation_id=root_reservation, expected_fence=root.fence)
    child, _ = store.submit_delegated_run(
        parent_run_id=root.id,
        parent_fence=root.fence,
        run=Run(bot_id=bot.id, prompt="bounded child work"),
        task=Task(bot_id=bot.id, kind="delegated", prompt="bounded child work"),
        idem_key="budget-child",
        request_hash="sha256:budget-child",
        parent_budget_cost_usd=1.0,
    )
    assert child.delegation_budget_cost_usd == 1.0
    assert store.get_run(child.id).delegation_budget_cost_usd == 1.0
    with pytest.raises(sqlite3.IntegrityError, match="delegation budget is immutable"):
        with store._tx() as db:
            db.execute("UPDATE runs SET delegation_budget_cost_usd = 5 WHERE id = ?", (child.id,))

    store.transition_run(root.id, RunStatus.succeeded, fence=root.fence, exit_reason="completed")
    claimed = store.claim_run(child.id, "delegation-budget-child", 60)
    assert claimed is not None
    child = store.transition_run(claimed.id, RunStatus.running, fence=claimed.fence)
    with pytest.raises(UsageBudgetRefusal, match=r"delegated run tree.*\$1.00 cap"):
        store.reserve_usage(
            run_id=child.id, bot_id=bot.id, provider="vendor-a", account_id="budget-account", model="model-a",
            reserved_tokens=100, reserved_cost_usd=0.31, max_run_cost_usd=5.0, expected_fence=child.fence)

    child_reservation = store.reserve_usage(
        run_id=child.id, bot_id=bot.id, provider="vendor-a", account_id="budget-account", model="model-a",
        reserved_tokens=100, reserved_cost_usd=0.25, max_run_cost_usd=5.0, expected_fence=child.fence)
    store.mark_usage_uncertain(child_reservation, "provider response missing", expected_fence=child.fence)

    grandchild, _ = _child(store, child, prompt="verify the bounded result", key="budget-grandchild",
                           parent_budget_cost_usd=5.0)
    assert grandchild.delegation_budget_cost_usd == 1.0
    store.transition_run(child.id, RunStatus.succeeded, fence=child.fence, exit_reason="completed")
    claimed_grandchild = store.claim_run(grandchild.id, "delegation-budget-grandchild", 60)
    assert claimed_grandchild is not None
    grandchild = store.transition_run(claimed_grandchild.id, RunStatus.running, fence=claimed_grandchild.fence)
    with pytest.raises(UsageBudgetRefusal, match=r"delegated run tree.*\$1.00 cap"):
        store.reserve_usage(
            run_id=grandchild.id, bot_id=bot.id, provider="vendor-a", account_id="budget-account", model="model-a",
            reserved_tokens=100, reserved_cost_usd=0.06, max_run_cost_usd=5.0, expected_fence=grandchild.fence)
    store.reserve_usage(
        run_id=grandchild.id, bot_id=bot.id, provider="vendor-a", account_id="budget-account", model="model-a",
        reserved_tokens=100, reserved_cost_usd=0.05, max_run_cost_usd=5.0, expected_fence=grandchild.fence)


def test_delegated_children_inherit_immutable_parent_capabilities_after_bot_edits(store):
    original = {"tools": ["read_file"], "risk_tier": "supervised", "sandbox": "strict",
                "shell_network": False, "limits": {"max_steps": 4}}
    bot, parent = _running_parent(store, capability_snapshot=original)
    store.upsert_bot(bot.model_copy(update={"tools": ["shell"], "sandbox": "off", "shell_network": True}))

    child, _ = _child(store, parent, key="capability-snapshot-child")
    assert store.run_capability_snapshot(parent.id) == original
    assert store.run_capability_snapshot(child.id) == original
    with pytest.raises(sqlite3.IntegrityError, match="run capabilities are immutable"):
        with store._tx() as db:
            db.execute("UPDATE runs SET capability_snapshot_json = ? WHERE id = ?",
                       ('{"tools":["shell"]}', child.id))


def test_delegated_bot_reconstructs_start_policy_and_narrows_shared_state(store):
    from hutch.models import InferenceMode

    original = store.create_bot(Bot(
        name="snapshot-worker", model="ollama/qwen3:8b", instructions="Inspect only the supplied task.",
        description="offline analysis", inference_mode=InferenceMode.offline,
        tools=["shell", "files", "memory", "browser", "web_fetch"],
        base_url="http://127.0.0.1:11434/api?local-token-not-for-snapshot",
    ))
    snapshot = Engine.capability_snapshot(original)
    assert snapshot["snapshot_version"] == 1
    assert "local-token-not-for-snapshot" not in str(snapshot)
    changed = original.model_copy(update={
        "model": "openai/gpt-current", "tools": ["shell", "browser"], "sandbox": "off",
        "shell_network": True,
    })

    delegated = Engine._delegated_bot(changed, snapshot)

    assert delegated.model == "ollama/qwen3:8b"
    assert delegated.instructions == original.instructions
    assert delegated.sandbox == original.sandbox
    assert delegated.shell_network is False
    assert delegated.inference_mode is InferenceMode.offline
    assert "browser" not in delegated.tools and "web_fetch" not in delegated.tools
    assert "remember" not in delegated.tools and "recall" not in delegated.tools
    assert delegated.workspace_mode == "fresh" and delegated.workdir is None
    assert delegated.local_browser_handoff is False
    assert delegated.limits.max_steps == 8
    assert delegated.limits.timeout_seconds == 600
    assert delegated.base_url == original.base_url


def test_delegated_bot_refuses_changed_prompt_identity_or_custom_route(store):
    original = store.create_bot(Bot(name="snapshot-identity", model="ollama/qwen3:8b",
                                    description="analysis", instructions="Use local data only."))
    snapshot = Engine.capability_snapshot(original)
    changed_instructions = original.model_copy(update={"instructions": "Use a hosted tool instead."})
    changed_endpoint = original.model_copy(update={"base_url": "http://127.0.0.1:11435"})
    changed_identity = original.model_copy(update={"description": "new task"})
    for changed in (changed_instructions, changed_endpoint, changed_identity):
        with pytest.raises(ValueError, match="changed after the parent started"):
            Engine._delegated_bot(changed, snapshot)

    with pytest.raises(ValueError, match="Strict Offline"):
        Engine._delegated_bot(original, {**snapshot, "inference_mode": "hybrid"})


def test_delegated_child_claim_can_share_only_its_parent_capacity(store):
    bot, parent = _running_parent(store)
    child, _ = _child(store, parent, key="claim-child")

    claimed = store.claim_run(child.id, "child-owner", 60, max_live=3)

    assert claimed is not None
    assert claimed.parent_run_id == parent.id
    unrelated = store.submit_run(Run(bot_id=bot.id, prompt="unrelated work"),
                                 Task(bot_id=bot.id, prompt="unrelated work"))
    assert store.claim_run(unrelated.id, "unrelated-owner", 60, max_live=3) is None

    sibling, _ = _child(store, parent, key="claim-sibling")
    sibling_claim = store.claim_run(sibling.id, "sibling-owner", 60, max_live=3)
    assert sibling_claim is not None

    other_bot = store.create_bot(Bot(name="claim-other-bot", model="mock/demo", tools=[]))
    other = store.submit_run(Run(bot_id=other_bot.id, prompt="use another global slot"),
                             Task(bot_id=other_bot.id, prompt="use another global slot"))
    assert store.claim_run(other.id, "other-bot-owner", 60, max_live=3) is None


def test_delegated_child_can_share_the_only_global_slot(store):
    _, parent = _running_parent(store)
    child, _ = _child(store, parent, key="one-slot-child")
    store.transition_run(parent.id, RunStatus.waiting_child, fence=parent.fence,
                         child_wait=(child.id, {"version": 1, "messages": [], "tool_call": {}}))

    claimed = store.claim_run(child.id, "one-slot-child-owner", 60, max_live=1)

    assert claimed is not None
    assert claimed.parent_run_id == parent.id
    other_bot = store.create_bot(Bot(name="one-slot-unrelated", model="mock/demo", tools=[]))
    unrelated = store.submit_run(Run(bot_id=other_bot.id, prompt="unrelated"),
                                 Task(bot_id=other_bot.id, prompt="unrelated"))
    assert store.claim_run(unrelated.id, "one-slot-unrelated-owner", 60, max_live=1) is None


def test_supervised_delegation_admits_private_child_and_returns_verified_result(store, config):
    bot = store.create_bot(Bot(name="offline-supervisor", model="ollama/qwen3:8b",
                               base_url="http://127.0.0.1:11434", inference_mode=InferenceMode.offline,
                               tools=["delegate_task"], limits=Limits(max_cost_usd=1.0)))
    root = store.submit_run(Run(bot_id=bot.id, prompt="coordinate privately"), Task(bot_id=bot.id,
                                                                                      prompt="coordinate privately"))
    claimed = store.claim_run(root.id, "delegation-parent", 60, max_live=2)
    assert claimed is not None
    parent = store.transition_run(root.id, RunStatus.running, fence=claimed.fence,
                                  capability_snapshot=Engine.capability_snapshot(bot))
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext
    ctx = ToolContext(bot=bot, run=parent, store=store, policy=PolicyEngine(),
                      gate=ApprovalGate(store, bot, parent, PolicyEngine(), lambda _event: None),
                      config=config, workspace=config.run_dir(bot.name, root.id) / "workspace")
    engine = Engine(config, store, max_concurrent=2, executor="process", owner_id="delegation-supervisor", light=True)

    def finish_child():
        import time
        child = None
        until = time.monotonic() + 4
        while time.monotonic() < until:
            child = next((run for run in store.active_runs() if run.parent_run_id == root.id), None)
            if child:
                break
            time.sleep(0.01)
        assert child is not None
        child = store.claim_run(child.id, "delegation-fixture", 60, max_live=2)
        assert child is not None
        child = store.transition_run(child.id, RunStatus.running, fence=child.fence)
        assert child.conversation_context == []
        store.append_event(Event(run_id=child.id, owner_fence=child.fence, type=EventType.message,
                                 data={"role": "assistant", "content": "Reviewed result from isolated child."}))
        store.transition_run(child.id, RunStatus.succeeded, fence=child.fence, exit_reason="completed")

    import threading
    import time
    fixture = threading.Thread(target=finish_child)
    fixture.start()
    result = engine._run_delegated_task(ctx, "Inspect the supplied file and summarize its risks.",
                                        "step-1-test", "sha256:task", time.monotonic() + 5)
    fixture.join(5)
    assert result.data["child_wait_pending"] and result.data["child_run_id"]
    completed = engine._delegated_child_result(result.data["child_run_id"])
    assert completed.ok and "Reviewed result from isolated child." in completed.output
    child = next(run for run in store.list_runs() if run.parent_run_id == root.id)
    assert child.delegation_budget_cost_usd == 1.0
    assert child.conversation_context == []


def test_strict_offline_delegation_runs_as_child_after_explicit_approval(store, config):
    """Exercise approval, child process, private context and result return with a local HTTP fixture."""
    import threading
    import time

    from hutch import sandbox
    from hutch.approvals import resolve_approval
    from hutch.models import ApprovalMode
    from tests.fakes import FakeOllama, agent_script

    if not sandbox.status().ok or not sandbox.offline_egress_status(refresh=True).ok:
        pytest.skip("host lacks a verified resource-limited offline worker")

    fake = FakeOllama({"fake:1b": {"params": "1B", "size": 200_000_000}})
    fake.script = agent_script([
        {"content": "", "tool_calls": [{"name": "delegate_task", "arguments": {
            "task": "Return a short independent summary of the supplied task."}}]},
        {"content": "Child result: the requested summary is verified."},
        {"content": "Parent result includes the verified child summary."},
    ])
    fake.chat_delay = 0.75
    bot = store.create_bot(Bot(
        name="offline-delegation-e2e", model="ollama/fake:1b", base_url=fake.url,
        inference_mode=InferenceMode.offline, sandbox="strict", tools=["delegate_task"],
        approval_mode=ApprovalMode.auto, selfcheck=False, num_ctx=4096,
        limits=Limits(max_steps=8, timeout_seconds=60, max_cost_usd=1.0),
    ))
    root = Run(bot_id=bot.id, prompt="Coordinate the task.",
               conversation_context=[{"role": "user", "content": "PRIVATE ROOT HISTORY"}])
    root = store.submit_run(root, Task(bot_id=bot.id, prompt=root.prompt))
    engine = Engine(config, store, max_concurrent=1, executor="process", light=True,
                    owner_id="delegation-process-e2e")
    stop_dispatch = threading.Event()

    def dispatch_children():
        while not stop_dispatch.is_set():
            engine.tick()
            stop_dispatch.wait(0.02)

    dispatcher = threading.Thread(target=dispatch_children, name="delegation-test-dispatcher")
    dispatcher.start()
    try:
        deadline = time.monotonic() + 45
        pending = []
        while time.monotonic() < deadline:
            pending = store.pending_approvals(bot_id=bot.id)
            if pending:
                break
            current = store.get_run(root.id)
            if current is None or current.terminal:
                events = [event.data for event in store.tail_events(root.id, limit=40)]
                raise AssertionError((current.status if current else None, current.error if current else None,
                                      current.exit_reason if current else None, events, fake.of("/api/chat")))
            time.sleep(0.05)

        assert pending, "root did not request human approval for delegation"
        request = pending[0]
        assert request.run_id == root.id and request.tool == "delegate_task"
        assert request.outward and request.detail["task"] == "Return a short independent summary of the supplied task."
        assert list(store.hub.dir.glob("*.sock")), "worker listener must be visible before approval is published"
        resolved = resolve_approval(store, request.id, True, by="fixture-reviewer")
        assert resolved.status.value == "approved"

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = store.get_run(root.id)
            children = [run for run in store.list_runs() if run.parent_run_id == root.id]
            if (current is not None and current.status is RunStatus.waiting_child and children
                    and children[0].status in (RunStatus.pending, RunStatus.running)):
                break
            time.sleep(0.02)
        assert store.get_run(root.id).status is RunStatus.waiting_child
        assert children and children[0].status in (RunStatus.pending, RunStatus.running)
        assert store.live_procs(root.id) == [], "the parked parent worker must exit before child inference continues"

        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            current = store.get_run(root.id)
            if current is not None and current.terminal:
                break
            time.sleep(0.05)

        final = store.get_run(root.id)
        assert final is not None and final.status is RunStatus.succeeded, (
            final.status if final else None, final.error if final else None,
            final.exit_reason if final else None,
        )
        children = [run for run in store.list_runs() if run.parent_run_id == root.id]
        assert len(children) == 1
        child = children[0]
        assert child.status is RunStatus.succeeded, (child.status, child.error, child.exit_reason)
        assert child.conversation_context == []
        assert "Child result: the requested summary is verified." in "\n".join(
            str(event.data.get("content") or "") for event in store.tail_events(child.id, limit=100)
        )

        calls = fake.of("/api/chat")
        assert len(calls) == 3, "root approval, child completion, then parent completion should each use one call"
        root_request = calls[0]["body"]
        child_request = calls[1]["body"]
        assert "PRIVATE ROOT HISTORY" in str(root_request["messages"])
        assert "PRIVATE ROOT HISTORY" not in str(child_request["messages"])
        assert "Return a short independent summary of the supplied task." in str(child_request["messages"])
        assert "Child result: the requested summary is verified." in str(calls[2]["body"]["messages"])
    finally:
        stop_dispatch.set()
        dispatcher.join(timeout=5)
        if dispatcher.is_alive():
            raise RuntimeError("delegation test dispatcher did not stop")
        engine.stop_all()
        engine.shutdown(timeout=10)
        fake.close()


def test_nested_delegation_stops_at_its_depth_limit_even_with_one_slot(store, config):
    bot = store.create_bot(Bot(name="nested-offline", model="ollama/qwen3:8b",
                               base_url="http://127.0.0.1:11434", inference_mode=InferenceMode.offline,
                               tools=["delegate_task"]))
    root_run = store.submit_run(Run(bot_id=bot.id, prompt="root"), Task(bot_id=bot.id, prompt="root"))
    root_claim = store.claim_run(root_run.id, "root-owner", 60, max_live=3)
    root = store.transition_run(root_run.id, RunStatus.running, fence=root_claim.fence,
                                capability_snapshot=Engine.capability_snapshot(bot))
    child, _ = _child(store, root, key="nested-parent")
    store.transition_run(root.id, RunStatus.waiting_child, fence=root.fence,
                         child_wait=(child.id, {"version": 1, "messages": [], "tool_call": {}}))
    child_claim = store.claim_run(child.id, "child-owner", 60, max_live=3)
    parent = store.transition_run(child.id, RunStatus.running, fence=child_claim.fence)
    grandchild, _ = _child(store, parent, key="nested-grandchild")
    store.transition_run(parent.id, RunStatus.waiting_child, fence=parent.fence,
                         child_wait=(grandchild.id, {"version": 1, "messages": [], "tool_call": {}}))
    grandchild_claim = store.claim_run(grandchild.id, "grandchild-owner", 60, max_live=1)
    assert grandchild_claim is not None
    grandchild = store.transition_run(grandchild.id, RunStatus.running, fence=grandchild_claim.fence)
    engine = Engine(config, store, max_concurrent=1, executor="process", owner_id="one-slot", light=True)
    ctx = type("Context", (), {"bot": bot, "run": grandchild, "store": store})()
    result = engine._run_delegated_task(ctx, "a bounded task", "step-1", "sha256:task", 10**9)
    assert not result.ok and "delegation depth limit is two" in result.output
    assert not any(run.parent_run_id == grandchild.id for run in store.list_runs())


def test_direct_child_worker_fails_before_runtime_or_tools_start(store, config, monkeypatch):
    import hutch.engine as engine_module

    bot, parent = _running_parent(store)
    child, _ = _child(store, parent, key="unavailable-child-executor")
    # Ordinary claim admission correctly refuses a concurrent run for this same bot.
    # Simulate a worker that was given a forged/stale claim to test the last boundary.
    with store._tx() as db:
        db.execute("UPDATE runs SET lease_owner = ?, lease_expires_at = ?, fence = fence + 1 WHERE id = ?",
                   ("direct-child-worker", iso(utcnow() + timedelta(seconds=60)), child.id))
    claimed = store.get_run(child.id)
    monkeypatch.setattr(engine_module, "get_runtime",
                        lambda *_: pytest.fail("delegated worker reached model runtime"))

    engine = Engine(config, store, light=True)
    # Even a stale/corrupt caller projection cannot hide the database lineage link.
    engine._execute(bot, claimed.model_copy(update={"parent_run_id": None}), threading.Event())

    failed = store.get_run(child.id)
    assert failed.status is RunStatus.failed
    assert failed.exit_reason == "delegation_unavailable"
    assert "capability snapshot is missing or unsupported" in failed.error
    assert store.list_events(child.id)[-1].data["reason"] == "delegation_unavailable"


def test_process_worker_refuses_child_before_recording_process_group(store, config, monkeypatch):
    import hutch.worker as worker

    _, parent = _running_parent(store)
    child, _ = _child(store, parent, key="worker-child-entrypoint")
    with store._tx() as db:
        db.execute("UPDATE runs SET lease_owner = ?, lease_expires_at = ?, fence = fence + 1 WHERE id = ?",
                   ("process-child-worker", iso(utcnow() + timedelta(seconds=60)), child.id))
    claimed = store.get_run(child.id)
    observer = Store(config)
    monkeypatch.setattr(worker, "get_config", lambda: config)
    monkeypatch.setattr(worker, "Store", lambda _: observer)

    try:
        result = worker.main([child.id, "--owner", claimed.lease_owner, "--fence", str(claimed.fence)])
    finally:
        observer.close()

    failed = store.get_run(child.id)
    assert result == 0
    assert failed.status is RunStatus.failed
    assert failed.exit_reason == "delegation_unavailable"
    assert failed.pgid == 0


def test_delegation_enforces_depth_fanout_and_active_child_limits(store):
    _, root = _running_parent(store)
    child1, _ = _child(store, root, key="child-1")
    child2, _ = _child(store, root, key="child-2")
    with pytest.raises(ValueError, match="concurrent-child limit"):
        _child(store, root, key="child-3")

    store.transition_run(child1.id, RunStatus.stopped, fence=child1.fence, exit_reason="stopped")
    child3, _ = _child(store, root, key="child-3")
    with pytest.raises(ValueError, match="fan-out limit"):
        _child(store, root, key="child-4")

    # Descendants count toward a fixed root-relative depth even after the parent completes.
    store.transition_run(root.id, RunStatus.succeeded, fence=root.fence, exit_reason="completed")
    claimed2 = store.claim_run(child2.id, "delegation-child-owner", 60)
    assert claimed2 is not None
    running2 = store.transition_run(claimed2.id, RunStatus.running, fence=claimed2.fence)
    grandchild, _ = _child(store, running2, key="grandchild")
    store.transition_run(running2.id, RunStatus.succeeded, fence=running2.fence, exit_reason="completed")
    claimed_grandchild = store.claim_run(grandchild.id, "delegation-grandchild-owner", 60)
    assert claimed_grandchild is not None
    running_grandchild = store.transition_run(
        claimed_grandchild.id, RunStatus.running, fence=claimed_grandchild.fence)
    with pytest.raises(ValueError, match="depth limit"):
        _child(store, running_grandchild, key="great-grandchild")


def test_cancelling_a_run_cancels_all_existing_descendants_and_blocks_new_children(store):
    _, root = _running_parent(store)
    child, _ = _child(store, root, key="cancel-child")

    store.transition_run(root.id, RunStatus.succeeded, fence=root.fence, exit_reason="completed")
    claimed_child = store.claim_run(child.id, "delegation-cancel-child", 60)
    assert claimed_child is not None
    child = store.transition_run(claimed_child.id, RunStatus.running, fence=claimed_child.fence)
    grandchild, _ = _child(store, child, key="cancel-grandchild")

    cancelled = store.request_cancel_tree(root.id, idem_key="stop-delegation-tree",
                                         request_hash="sha256:stop-tree")
    assert cancelled is not None
    states = {run.id: run for run in cancelled}
    assert states[child.id].status is RunStatus.cancelling
    assert states[child.id].cancel_requested is True
    assert states[grandchild.id].status is RunStatus.stopped

    replay = store.request_cancel_tree(root.id, idem_key="stop-delegation-tree",
                                       request_hash="sha256:stop-tree")
    assert replay is not None
    with pytest.raises(IdempotencyConflict):
        store.request_cancel_tree(root.id, idem_key="stop-delegation-tree",
                                  request_hash="sha256:changed-stop-tree")
    with pytest.raises(ValueError, match="current, live run owner"):
        _child(store, child, key="too-late-child")


def test_child_admission_racing_with_tree_stop_cannot_escape_cancellation(store, config):
    _, parent = _running_parent(store)
    gate = Barrier(2)

    def submit_child():
        contender = Store(config)
        try:
            gate.wait(timeout=10)
            try:
                child, _ = _child(contender, parent, key="stop-race-child")
                return child.id
            except ValueError as exc:
                assert "current, live run owner" in str(exc)
                return None
        finally:
            contender.close()

    def stop_tree():
        stopper = Store(config)
        try:
            gate.wait(timeout=10)
            assert stopper.request_cancel_tree(parent.id) is not None
        finally:
            stopper.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        submission = pool.submit(submit_child)
        stopping = pool.submit(stop_tree)
        child_id = submission.result(timeout=15)
        stopping.result(timeout=15)

    children = store._db.execute("SELECT id FROM runs WHERE parent_run_id = ?", (parent.id,)).fetchall()
    assert len(children) == (1 if child_id else 0)
    if child_id:
        child = store.get_run(child_id)
        assert child is not None
        assert child.cancel_requested or child.status in (RunStatus.cancelling, RunStatus.stopped)


def test_engine_stop_signals_owned_processes_for_descendants(store, config):
    _, root = _running_parent(store)
    child, _ = _child(store, root, key="signal-child")
    store.transition_run(root.id, RunStatus.succeeded, fence=root.fence, exit_reason="completed")
    claimed = store.claim_run(child.id, "signal-child-owner", 60)
    assert claimed is not None
    child = store.transition_run(claimed.id, RunStatus.running, fence=claimed.fence)
    grandchild, _ = _child(store, child, key="signal-grandchild")

    class LiveProcess:
        def poll(self):
            return None

    engine = Engine(config, store, light=True)
    process = LiveProcess()
    engine._procs[child.id] = process
    signalled = []
    engine._signal_group = lambda owned, _sig: signalled.append(owned)

    assert engine.stop_run(root.id) is True
    assert signalled == [process]
    assert store.get_run(child.id).status is RunStatus.cancelling
    assert store.get_run(grandchild.id).status is RunStatus.stopped


def test_dispatcher_fails_closed_for_children_with_unenforceable_snapshots(store, config):
    _, root = _running_parent(store)
    child, _ = _child(store, root, key="not-yet-executable")
    store.transition_run(root.id, RunStatus.succeeded, fence=root.fence, exit_reason="completed")

    engine = Engine(config, store, light=True, executor="thread")
    assert engine.dispatch_pending() == 0
    failed = store.get_run(child.id)
    assert failed is not None and failed.status is RunStatus.failed
    assert failed.exit_reason == "delegation_unavailable"
    assert "snapshot" in failed.error


def test_delegated_run_uses_private_workspace_instead_of_bot_folder(store, config, tmp_path):
    bot, parent = _running_parent(store)
    shared = tmp_path / "user-project"
    shared.mkdir()
    bot.workspace_mode = "folder"
    bot.workdir = str(shared)
    engine = Engine(config, store, light=True)
    parent_run = Run(bot_id=bot.id, prompt="parent")
    child_run = Run(bot_id=bot.id, prompt="child", parent_run_id=parent.id)

    _, parent_workspace, parent_error = engine._prepare_workspace(bot, parent_run)
    assert parent_workspace == shared
    assert parent_error is None
    shared.rmdir()

    _, child_workspace, child_error = engine._prepare_workspace(bot, child_run)
    assert child_workspace == config.workspace(bot.name, child_run.id)
    assert child_workspace != shared
    assert child_error is None
    assert child_workspace.stat().st_mode & 0o777 == 0o700

    external = tmp_path / "outside"
    external.mkdir()
    planted_run = Run(bot_id=bot.id, prompt="symlink child", parent_run_id=parent.id)
    planted_workspace = config.workspace(bot.name, planted_run.id)
    planted_workspace.parent.mkdir(parents=True, exist_ok=True)
    planted_workspace.symlink_to(external, target_is_directory=True)
    _, _, planted_error = engine._prepare_workspace(bot, planted_run)
    assert planted_error and "not a private directory" in planted_error


def test_delegation_admission_is_atomic_across_independent_sqlite_connections(store, config):
    _, parent = _running_parent(store)
    count = 8
    gate = Barrier(count)

    def submit(index):
        contender = Store(config)
        try:
            gate.wait(timeout=10)
            try:
                _child(contender, parent, prompt=f"inspect area {index}", key=f"racer-{index}")
                return "created"
            except ValueError as exc:
                assert "concurrent-child limit" in str(exc)
                return "limited"
        finally:
            contender.close()

    with ThreadPoolExecutor(max_workers=count) as pool:
        outcomes = list(pool.map(submit, range(count)))
    assert outcomes.count("created") == 2
    assert outcomes.count("limited") == count - 2
    children = store._db.execute("SELECT COUNT(*) FROM runs WHERE parent_run_id = ?", (parent.id,)).fetchone()[0]
    assert children == 2


def test_schema_v21_migrates_existing_runs_with_no_parent_link(config):
    store = Store(config)
    bot = store.create_bot(Bot(name="legacy-delegation", model="mock/demo", tools=[]))
    run = store.submit_run(Run(bot_id=bot.id, prompt="legacy"), Task(bot_id=bot.id, prompt="legacy"))
    store.close()

    db = sqlite3.connect(config.db_path)
    db.execute("DROP TRIGGER runs_capability_snapshot_immutable")
    db.execute("ALTER TABLE runs DROP COLUMN capability_snapshot_json")
    db.execute("DROP TRIGGER runs_delegation_budget_immutable")
    db.execute("ALTER TABLE runs DROP COLUMN delegation_budget_cost_usd")
    db.execute("DROP TRIGGER runs_parent_run_id_immutable")
    db.execute("DROP INDEX idx_runs_parent")
    db.execute("ALTER TABLE runs DROP COLUMN parent_run_id")
    _remove_later_conversation_schema(db)
    db.execute("PRAGMA user_version = 21")
    db.commit()
    db.close()

    upgraded = Store(config)
    try:
        legacy = upgraded.get_run(run.id)
        assert upgraded.schema_version == SCHEMA_VERSION
        assert legacy.parent_run_id is None
        assert legacy.delegation_budget_cost_usd is None
        assert (config.db_path.parent / "hutch.db.bak-v21").exists()
    finally:
        upgraded.close()


def test_schema_v22_migration_preserves_lineage_without_inventing_a_budget(store, config):
    bot, parent = _running_parent(store)
    child, _ = _child(store, parent, key="migrate-v22-child")
    store.close()

    db = sqlite3.connect(config.db_path)
    db.execute("DROP TRIGGER runs_capability_snapshot_immutable")
    db.execute("ALTER TABLE runs DROP COLUMN capability_snapshot_json")
    db.execute("DROP TRIGGER runs_delegation_budget_immutable")
    db.execute("ALTER TABLE runs DROP COLUMN delegation_budget_cost_usd")
    _remove_later_conversation_schema(db)
    db.execute("PRAGMA user_version = 22")
    db.commit()
    db.close()

    upgraded = Store(config)
    try:
        restored = upgraded.get_run(child.id)
        assert upgraded.schema_version == SCHEMA_VERSION
        assert restored.parent_run_id == parent.id
        assert restored.delegation_budget_cost_usd is None
        assert (config.db_path.parent / "hutch.db.bak-v22").exists()
    finally:
        upgraded.close()


def test_schema_v23_migration_adds_empty_capability_snapshots(config):
    store = Store(config)
    bot = store.create_bot(Bot(name="legacy-v23-run", model="mock/demo", tools=[]))
    run = store.submit_run(Run(bot_id=bot.id, prompt="legacy"), Task(bot_id=bot.id, prompt="legacy"))
    store.close()

    db = sqlite3.connect(config.db_path)
    db.execute("DROP TRIGGER runs_capability_snapshot_immutable")
    db.execute("ALTER TABLE runs DROP COLUMN capability_snapshot_json")
    _remove_later_conversation_schema(db)
    db.execute("PRAGMA user_version = 23")
    db.commit()
    db.close()

    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION
        assert upgraded.run_capability_snapshot(run.id) is None
        assert (config.db_path.parent / "hutch.db.bak-v23").exists()
    finally:
        upgraded.close()


def _offline_parent_with_conversation(store):
    """A live Strict Offline parent attached to a conversation, able to admit children."""
    bot = store.create_bot(Bot(name="choice-parent", model="ollama/qwen3:8b",
                               base_url="http://127.0.0.1:11434", inference_mode=InferenceMode.offline,
                               tools=["delegate_task"], limits=Limits(max_cost_usd=1.0)))
    conversation, _ = store.create_conversation(bot.id, "Choice parent",
                                                idem_key="choice-parent-conversation",
                                                request_hash="choice-parent-conversation")
    run = Run(bot_id=bot.id, prompt="coordinate work", conversation_id=conversation["id"])
    parent_id, _ = store.submit_conversation_message(
        conversation["id"], "coordinate work", run, Task(bot_id=bot.id, prompt="coordinate work"),
        idem_key="choice-parent-run", request_hash="choice-parent-run")
    claimed = store.claim_run(parent_id, "choice-parent-owner", 60, max_live=2)
    assert claimed is not None
    parent = store.transition_run(parent_id, RunStatus.running, fence=claimed.fence,
                                  capability_snapshot=Engine.capability_snapshot(bot))
    return bot, parent, conversation


def _tool_context(store, config, bot, run):
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext
    return ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(),
                       gate=ApprovalGate(store, bot, run, PolicyEngine(), lambda _event: None),
                       config=config, workspace=config.run_dir(bot.name, run.id) / "workspace")


def test_delegation_invocation_keys_are_app_owned_and_position_distinct():
    from hutch.tools.delegation import delegation_invocation_key

    same = "inspect one bounded area"
    assert delegation_invocation_key(3, 0, same) != delegation_invocation_key(3, 1, same)
    assert delegation_invocation_key(3, 0, same) == delegation_invocation_key(3, 0, same)
    assert delegation_invocation_key(3, 0, same) != delegation_invocation_key(4, 0, same)
    assert delegation_invocation_key(3, None, same) != delegation_invocation_key(3, 5, same)


def test_delegate_task_uses_the_application_owned_call_index(store, config, tmp_path):
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext, ToolResult
    from hutch.tools.delegation import DelegateTaskTool

    bot = store.create_bot(Bot(name="call-index-parent", model="ollama/qwen3:8b",
                               base_url="http://127.0.0.1:11434", inference_mode=InferenceMode.offline,
                               tools=["delegate_task"], limits=Limits(max_steps=8, timeout_seconds=60)))
    run = store.create_run(Run(bot_id=bot.id, prompt="coordinate"))

    class AllowingGate:
        last_authorization = None

        def decide(self, *args, **kwargs):
            return None

    submitted: list[str] = []
    ctx = ToolContext(bot=bot, run=run, store=store, policy=PolicyEngine(), gate=AllowingGate(),
                      config=config, workspace=tmp_path / "ws")
    ctx.delegation_submit = lambda task, idem_key, request_hash: (
        submitted.append(idem_key), ToolResult(ok=True, output="child accepted", data={}))[1]
    tool = DelegateTaskTool()

    ctx.tool_call_index = 0
    assert tool.run({"task": "inspect one bounded area"}, ctx).ok
    ctx.tool_call_index = 1
    assert tool.run({"task": "inspect one bounded area"}, ctx).ok
    assert len(submitted) == 2 and len(set(submitted)) == 2, submitted
    ctx.tool_call_index = 0
    assert tool.run({"task": "inspect one bounded area"}, ctx).ok
    assert submitted[2] == submitted[0], "an exact retry of the same call position must reuse its identity"


def test_delegated_child_tools_exclude_structured_questions(store, config):
    """A synchronous child cannot prompt the owner: its conversation belongs to the parent."""
    from hutch.tools import build_tools

    bot, parent, _ = _offline_parent_with_conversation(store)
    child, inserted = _child(store, parent, prompt="inspect one bounded area", key="choice-child")
    assert inserted is True
    claimed = store.claim_run(child.id, "choice-child-owner", 60, max_live=2)
    assert claimed is not None
    child = store.transition_run(child.id, RunStatus.running, fence=claimed.fence)

    assert "ask_user_choice" in build_tools(["memory"], _tool_context(store, config, bot, parent))
    child_tools = build_tools(["memory"], _tool_context(store, config, bot, child))
    assert "ask_user_choice" not in child_tools
    assert "delegate_task" not in child_tools


def test_delegated_child_question_is_not_reported_as_success(store, config):
    """If a child somehow records a question, the parent sees needs-input, never 'completed'."""
    import time

    bot, parent, conversation = _offline_parent_with_conversation(store)
    engine = Engine(config, store, max_concurrent=2, executor="process",
                    owner_id="choice-supervisor", light=True)
    ctx = _tool_context(store, config, bot, parent)

    def finish_child():
        until = time.monotonic() + 4
        child = None
        while time.monotonic() < until:
            child = next((run for run in store.active_runs()
                          if run.parent_run_id == parent.id), None)
            if child:
                break
            time.sleep(0.01)
        assert child is not None
        owned = store.claim_run(child.id, "choice-child-fixture", 60, max_live=2)
        assert owned is not None
        child = store.transition_run(child.id, RunStatus.running, fence=owned.fence)
        store.create_conversation_question(child.id, "Which option should I take?", "single",
                                           ["Alpha", "Beta"], fence=owned.fence)
        store.transition_run(child.id, RunStatus.succeeded, fence=owned.fence, exit_reason="completed")

    fixture = threading.Thread(target=finish_child)
    fixture.start()
    try:
        result = engine._run_delegated_task(ctx, "Pick one option for the report.", "step-1-choice",
                                            "sha256:choice", time.monotonic() + 5)
    finally:
        fixture.join(5)
    assert result.data["child_wait_pending"] and result.data["child_run_id"]
    completed = engine._delegated_child_result(result.data["child_run_id"])
    assert completed.ok is False
    assert completed.data.get("needs_input") is True
    assert "question" in completed.output.lower()
    assert "completed" not in completed.output.lower()
