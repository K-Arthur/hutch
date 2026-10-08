from __future__ import annotations

import time

from hutch.models import (
    ApprovalRequest,
    ApprovalStatus,
    Bot,
    Event,
    EventType,
    Run,
    RunStatus,
    Schedule,
    Task,
)


def make_bot(name="researcher", **kw) -> Bot:
    defaults = dict(
        name=name,
        instructions="Summarize things.",
        tools=["shell", "files", "memory"],
    )
    defaults.update(kw)
    return Bot(**defaults)


def test_bot_crud(store):
    bot = store.create_bot(make_bot())
    assert store.get_bot("researcher").id == bot.id
    assert store.get_bot(bot.id).name == "researcher"
    assert len(store.list_bots()) == 1

    bot.paused = True
    store.upsert_bot(bot)
    assert store.get_bot("researcher").paused is True

    assert store.delete_bot("researcher") is True
    assert store.get_bot("researcher") is None


def test_bot_name_conflicts_use_upsert(store):
    store.create_bot(make_bot("alpha"))
    updated = make_bot("alpha", instructions="v2")
    store.upsert_bot(updated)
    bots = store.list_bots()
    assert len(bots) == 1
    assert bots[0].instructions == "v2"


def test_task_queue_fifo_per_bot(store):
    bot = store.create_bot(make_bot())
    t1 = store.enqueue_task(Task(bot_id=bot.id, prompt="first"))
    t2 = store.enqueue_task(Task(bot_id=bot.id, prompt="second"))
    assert store.next_task(bot.id).id == t1.id
    store.finish_task(t1.id)
    assert store.next_task(bot.id).id == t2.id
    store.finish_task(t2.id)
    assert store.next_task(bot.id) is None


def test_run_lifecycle_and_events(store):
    bot = store.create_bot(make_bot())
    run = store.create_run(Run(bot_id=bot.id, prompt="do it"))
    assert run.status is RunStatus.pending

    run.status = RunStatus.running
    run.steps = 3
    run.tokens = 1500
    store.update_run(run)
    fetched = store.get_run(run.id)
    assert fetched.status is RunStatus.running and fetched.steps == 3

    for i in range(3):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    events = store.list_events(run.id)
    assert [e.data["i"] for e in events] == [0, 1, 2]
    assert len(store.list_events(run.id, after_id=events[0].id)) == 2
    assert len(store.list_events(run.id, after_seq=events[0].seq)) == 2


def test_active_runs_and_last_success(store):
    bot = store.create_bot(make_bot())
    r1 = store.create_run(Run(bot_id=bot.id, prompt="a"))
    r1.status = RunStatus.succeeded
    store.update_run(r1)
    r2 = store.create_run(Run(bot_id=bot.id, prompt="b"))
    r2.status = RunStatus.running
    store.update_run(r2)

    active = store.active_runs()
    assert [r.id for r in active] == [r2.id]
    assert store.active_run_for_bot(bot.id).id == r2.id
    assert store.last_successful_run(bot.id).id == r1.id


def test_bot_status_prefers_execution_or_human_wait_over_an_older_queue_entry(store):
    bot = store.create_bot(make_bot())
    queued = store.create_run(Run(bot_id=bot.id, prompt="queued first"))
    waiting = store.create_run(Run(bot_id=bot.id, prompt="already waiting", status=RunStatus.waiting_human))
    assert store.active_run_for_bot(bot.id).id == waiting.id
    store.transition_run(waiting.id, RunStatus.failed, error="fixture ended")
    assert store.active_run_for_bot(bot.id).id == queued.id


def test_approvals_and_sticky_allows(store):
    bot = store.create_bot(make_bot())
    run = store.create_run(Run(bot_id=bot.id, prompt="x"))
    req = store.create_approval(
        ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="shell", action="rm -rf build/", sticky_key="shell:rm")
    )
    assert len(store.pending_approvals()) == 1

    assert store.is_sticky_allowed(bot.id, "shell:rm") is False
    store.allow_sticky(bot.id, "shell:rm")
    assert store.is_sticky_allowed(bot.id, "shell:rm") is True

    req.status = ApprovalStatus.approved
    store.update_approval(req)
    assert store.pending_approvals() == []
    assert store.get_approval(req.id).status.value == "approved"

    store.revoke_sticky(bot.id, "shell:rm")
    assert store.is_sticky_allowed(bot.id, "shell:rm") is False


def test_memory_roundtrip(store):
    bot = store.create_bot(make_bot())
    store.remember(bot.id, " preference", "concise answers")
    store.remember(bot.id, " preference", "verbose answers")
    items = store.recall_all(bot.id)
    assert len(items) == 1 and items[0].value == "verbose answers"
    assert store.forget(bot.id, " preference") is True
    assert store.recall_all(bot.id) == []


def test_tokens_today_counts_only_today(store):
    bot = store.create_bot(make_bot())
    run = Run(bot_id=bot.id, prompt="x", tokens=500)
    store.create_run(run)
    run.status = RunStatus.succeeded
    store.update_run(run)
    assert store.tokens_today(bot.id) == 500


def test_schedule_json_roundtrip(store):
    bot = make_bot(schedule=Schedule(cron="0 9 * * mon", timezone="Europe/Berlin"))
    store.create_bot(bot)
    fetched = store.get_bot("researcher")
    assert fetched.schedule.cron == "0 9 * * mon"
    assert fetched.schedule.timezone == "Europe/Berlin"
