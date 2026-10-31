"""Retirement must hold on the live specialist-assignment path, not just the store helper.

`POST /api/v1/workspace/tasks` reaches `coordinator_tasks.submit_workspace_task`, which inserts the
specialist's conversation, task and run itself. Guarding only `Store.submit_workspace_task` (a
method production code does not call) left the real route open, so this test drives the same
function the route uses.
"""
from __future__ import annotations

import pytest

from hutch import coordinator_tasks
from hutch.bot_lifecycle import BotArchived, archive_bot
from hutch.engine import Engine
from hutch.models import Bot, Event, EventType, Run, RunStatus, Task


def _seed(store):
    coordinator = store.create_bot(Bot(name="retire-coordinator", model="mock/demo", tools=[]))
    specialist = store.create_bot(Bot(name="retire-specialist", model="mock/demo", tools=[]))
    store.set_workspace_coordinator(coordinator.id)
    store.set_workspace_specialists([specialist.id])
    parent, _ = store.create_conversation(coordinator.id, "Coordinator",
                                          idem_key="rc-parent", request_hash="rc-parent")
    prompt = "Plan the launch."
    run_id, _ = store.submit_conversation_message(
        parent["id"], prompt, Run(bot_id=coordinator.id, prompt=prompt, conversation_id=parent["id"]),
        Task(bot_id=coordinator.id, prompt=prompt), idem_key="rc-src", request_hash="rc-src")
    owned = store.claim_run(run_id, "rc-owner", 60)
    store.transition_run(run_id, RunStatus.running, fence=owned.fence)
    store.append_event(Event(run_id=run_id, type=EventType.message, owner_fence=owned.fence,
                             data={"role": "assistant", "content": "Draft.", "message_id": "rc-answer"}))
    store.flush_events()
    store.transition_run(run_id, RunStatus.succeeded, fence=owned.fence)
    messages = store.list_conversation_messages(parent["id"])
    user = next(m for m in messages if m["role"] == "user")
    answer = next(m for m in messages if m["role"] == "assistant")
    return coordinator, specialist, parent, run_id, user, answer


def _assign(store, specialist, parent, run_id, user, answer, brief="Research the market."):
    return coordinator_tasks.submit_workspace_task(
        store, parent_conversation_id=parent["id"], source_run_id=run_id,
        source_user_message_id=user["id"], source_assistant_message_id=answer["id"],
        target_bot_id=specialist.id, task_brief=brief, assumptions="",
        run=Run(bot_id=specialist.id, prompt=brief, origin="workspace_task"),
        task=Task(bot_id=specialist.id, kind="on_demand", prompt=brief),
        capability_snapshot=Engine.capability_snapshot(specialist),
        idem_key="assign-1", request_hash="assign-1")


def test_archived_specialist_cannot_be_assigned_a_task(store):
    _, specialist, parent, run_id, user, answer = _seed(store)
    archive_bot(store, specialist.name, True, idem_key="retire-spec", request_hash="h1")

    with pytest.raises(BotArchived):
        _assign(store, specialist, parent, run_id, user, answer)

    # Nothing was admitted: no specialist task and no run for the retired assistant.
    assert coordinator_tasks.list_tasks(store, parent["id"]) == []
    assert store.active_run_for_bot(specialist.id) is None


def test_restored_specialist_can_be_assigned_again(store):
    _, specialist, parent, run_id, user, answer = _seed(store)
    archive_bot(store, specialist.name, True, idem_key="retire-spec2", request_hash="h1")
    archive_bot(store, specialist.name, False, idem_key="restore-spec2", request_hash="h2")
    coordinator_tasks.submit_workspace_task(
        store, parent_conversation_id=parent["id"], source_run_id=run_id,
        source_user_message_id=user["id"], source_assistant_message_id=answer["id"],
        target_bot_id=specialist.id, task_brief="Research the market.", assumptions="",
        run=Run(bot_id=specialist.id, prompt="Research the market.", origin="workspace_task"),
        task=Task(bot_id=specialist.id, kind="on_demand", prompt="Research the market."),
        capability_snapshot=Engine.capability_snapshot(specialist),
        idem_key="assign-2", request_hash="assign-2")
    assert len(coordinator_tasks.list_tasks(store, parent["id"])) == 1
