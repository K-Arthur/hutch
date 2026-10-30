"""Two-specialist task plans, per-assignment model ownership, redirect and stop-all."""
import pytest

from hutch.engine import Engine
from hutch.models import Bot, Event, EventType, Run, RunStatus, Task
from hutch import coordinator_redirect, coordinator_tasks


def _seed(store):
    coordinator = store.create_bot(Bot(name="plan-coordinator", model="mock/demo", tools=[]))
    specs = [store.create_bot(Bot(name=f"plan-specialist-{n}", model="mock/demo", tools=[])) for n in (1, 2)]
    store.set_workspace_coordinator(coordinator.id)
    store.set_workspace_specialists([s.id for s in specs])
    parent, _ = store.create_conversation(coordinator.id, "Coordinator", idem_key="plan-parent", request_hash="plan-parent")
    prompt = "Plan the launch."
    run_id, _ = store.submit_conversation_message(
        parent["id"], prompt, Run(bot_id=coordinator.id, prompt=prompt, conversation_id=parent["id"]),
        Task(bot_id=coordinator.id, prompt=prompt), idem_key="plan-src", request_hash="plan-src")
    owned = store.claim_run(run_id, "plan-owner", 60)
    store.transition_run(run_id, RunStatus.running, fence=owned.fence)
    store.append_event(Event(run_id=run_id, type=EventType.message, owner_fence=owned.fence,
                             data={"role": "assistant", "content": "Draft.", "message_id": "plan-answer"}))
    store.flush_events()
    store.transition_run(run_id, RunStatus.succeeded, fence=owned.fence)
    messages = store.list_conversation_messages(parent["id"])
    user = next(m for m in messages if m["role"] == "user")
    answer = next(m for m in messages if m["role"] == "assistant")
    return parent, run_id, user, answer, specs


def _assignment(bot, brief, *, override="", source="specialist_default"):
    return {"target_bot_id": bot.id, "task_brief": brief, "capability_snapshot": Engine.capability_snapshot(bot),
            "run": Run(bot_id=bot.id, prompt=brief, origin="workspace_task"),
            "task": Task(bot_id=bot.id, kind="on_demand", prompt=brief),
            "model_override": override, "model_source": source}


def _submit(store, parent, run_id, user, answer, primary, extras, key):
    return coordinator_tasks.submit_workspace_task(
        store, parent_conversation_id=parent["id"], source_run_id=run_id,
        source_user_message_id=user["id"], source_assistant_message_id=answer["id"],
        target_bot_id=primary["target_bot_id"], task_brief=primary["task_brief"], assumptions="",
        run=primary["run"], task=primary["task"], capability_snapshot=primary["capability_snapshot"],
        idem_key=key, request_hash=key, model_override=primary["model_override"],
        model_source=primary["model_source"], additional_assignments=extras)


def test_two_specialists_share_a_plan_with_independent_model_sources(store):
    parent, run_id, user, answer, (first, second) = _seed(store)
    primary = _assignment(first, "Research the market.")
    extra = _assignment(second, "Draft the announcement.", override="ollama/override:1b", source="assignment_override")
    _, created = _submit(store, parent, run_id, user, answer, primary, [extra], "plan-two")
    assert created is True
    tasks = coordinator_tasks.list_tasks(store, parent["id"])
    assert len(tasks) == 2
    by_bot = {t["target_bot_id"]: t for t in tasks}
    assert by_bot[first.id]["model_source"] == "specialist_default" and by_bot[first.id]["model"] == "mock/demo"
    assert by_bot[second.id]["model_source"] == "assignment_override" and by_bot[second.id]["model"] == "ollama/override:1b"
    assert by_bot[first.id]["plan_group_id"] == by_bot[second.id]["plan_group_id"]
    assert by_bot[first.id]["peer_task_ids"] == [by_bot[second.id]["id"]]
    assert by_bot[first.id]["child_conversation_id"] != by_bot[second.id]["child_conversation_id"]
    assert store.get_run(by_bot[second.id]["child_run_id"]).model_override == "ollama/override:1b"
    assert store.get_run(by_bot[first.id]["child_run_id"]).model_override == ""
    assert len(coordinator_tasks.list_tasks(store, None)) == 2


def test_plan_refuses_duplicate_specialist_and_more_than_two(store):
    parent, run_id, user, answer, (first, second) = _seed(store)
    with pytest.raises(ValueError, match="distinct"):
        _submit(store, parent, run_id, user, answer, _assignment(first, "A"), [_assignment(first, "B")], "dup")
    with pytest.raises(ValueError, match="at most 2"):
        _submit(store, parent, run_id, user, answer, _assignment(first, "A"),
                [_assignment(second, "B"), _assignment(second, "C")], "three")
    assert coordinator_tasks.list_tasks(store, parent["id"]) == []


def test_redirect_bumps_revision_and_is_idempotent(store):
    parent, run_id, user, answer, (first, _) = _seed(store)
    _submit(store, parent, run_id, user, answer, _assignment(first, "Original brief."), [], "redirect-src")
    task = coordinator_tasks.list_tasks(store, parent["id"])[0]
    assert task["brief_revision"] == 1

    class _Engine:
        stopped: list[str] = []
        def stop_run(self, run_id): self.stopped.append(run_id)

    engine = _Engine()
    updated, created = coordinator_redirect.redirect_workspace_task(
        store, engine, task["id"], task_brief="Revised brief.", idem_key="redir-1", request_hash="redir-1")
    assert created is True and updated["brief_revision"] == 2 and updated["task_brief"] == "Revised brief."
    assert engine.stopped == [task["current_run_id"]]
    assert any(c["kind"] == "brief_redirected" for c in updated["checkpoints"])
    again, created_again = coordinator_redirect.redirect_workspace_task(
        store, engine, task["id"], task_brief="Revised brief.", idem_key="redir-1", request_hash="redir-1")
    assert created_again is False and again["brief_revision"] == 2


def test_stop_all_stops_every_active_run_in_the_plan(store):
    parent, run_id, user, answer, (first, second) = _seed(store)
    _submit(store, parent, run_id, user, answer, _assignment(first, "A"), [_assignment(second, "B")], "stop-plan")
    tasks = coordinator_tasks.list_tasks(store, parent["id"])

    class _Engine:
        stopped: list[str] = []
        def stop_run(self, run_id): self.stopped.append(run_id)

    engine = _Engine()
    result, _ = coordinator_redirect.stop_workspace_task_group(
        store, engine, tasks[0]["id"], idem_key="stop-1", request_hash="stop-1")
    assert sorted(engine.stopped) == sorted(t["current_run_id"] for t in tasks)
    assert len(result) == 2

