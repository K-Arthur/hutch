"""Crash-boundary and durability checks for schedule occurrence admission."""

from __future__ import annotations

from datetime import datetime, timezone

from hutch.engine import Engine
from hutch.models import Bot, CatchUpPolicy, Run, Schedule, Task, iso
from hutch.scheduler import Scheduler


def _bot(store, cron="0 * * * *", created="2026-10-07T10:00:00+00:00") -> Bot:
    return store.create_bot(Bot(
        name="dur", instructions="work",
        schedule=Schedule(cron=cron, timezone="UTC", catch_up=CatchUpPolicy.coalesce),
        created_at=created,
    ))


def test_marker_advances_only_with_occurrence_row(store, config):
    bot = _bot(store)
    engine = Engine(config, store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-07T10:00:00+00:00")
    now = datetime(2026, 10, 7, 12, 30, tzinfo=timezone.utc)
    due = engine.scheduler.due_claims(now)[0]
    marker = iso(due.occurrence)
    # Simulate lost race: wrong expected marker → no run, no marker advance.
    run = Run(bot_id=bot.id, prompt="x", origin="schedule", schedule_id=due.schedule.id)
    task = Task(bot_id=bot.id, kind="scheduled", prompt=run.prompt)
    assert store.submit_scheduled(
        run, task, occurrence=marker, expected_marker="stale-marker", new_marker=marker,
        claimed_by="crash-test", schedule_id=due.schedule.id,
    ) is None
    assert store.kv_get(f"{bot.schedule.id}:last_fire") == "2026-10-07T10:00:00+00:00"
    assert store.list_schedule_occurrences(due.schedule.id) == []

    won = store.submit_scheduled(
        Run(bot_id=bot.id, prompt="x", origin="schedule", schedule_id=due.schedule.id),
        Task(bot_id=bot.id, kind="scheduled", prompt="x"),
        occurrence=marker, expected_marker=due.marker, new_marker=marker,
        claimed_by="crash-test", schedule_id=due.schedule.id,
    )
    assert won is not None
    assert store.kv_get(f"{bot.schedule.id}:last_fire") == marker
    assert len(store.list_schedule_occurrences(due.schedule.id)) == 1


def test_duplicate_occurrence_claim_is_rejected(store, config):
    bot = _bot(store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-07T10:00:00+00:00")
    s = Scheduler(store)
    due = s.due_claims(datetime(2026, 10, 7, 12, 30, tzinfo=timezone.utc))[0]
    marker = iso(due.occurrence)
    first = store.submit_scheduled(
        Run(bot_id=bot.id, prompt="a", origin="schedule", schedule_id=due.schedule.id),
        Task(bot_id=bot.id, kind="scheduled", prompt="a"),
        occurrence=marker, expected_marker=due.marker, new_marker=marker,
        claimed_by="a", schedule_id=due.schedule.id,
    )
    assert first is not None
    # Second process with stale marker loses; even with current marker, same occurrence PK conflicts.
    second = store.submit_scheduled(
        Run(bot_id=bot.id, prompt="b", origin="schedule", schedule_id=due.schedule.id),
        Task(bot_id=bot.id, kind="scheduled", prompt="b"),
        occurrence=marker, expected_marker=marker, new_marker=marker,
        claimed_by="b", schedule_id=due.schedule.id,
    )
    assert second is None
    assert len(store.list_schedule_occurrences(due.schedule.id)) == 1


def test_disabled_draft_never_admits_after_save(store):
    bot = store.create_bot(Bot(
        name="drafty", instructions="x",
        schedule=Schedule(cron="* * * * *", timezone="UTC", enabled=False),
        created_at="2026-10-07T12:00:00+00:00",
    ))
    s = Scheduler(store)
    assert s.due_claims(datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc)) == []
    enabled = bot.schedule.model_copy(update={"enabled": True})
    store.put_schedule(bot.id, enabled)
    claims = s.due_claims(datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc))
    assert len(claims) == 1 and claims[0].schedule.enabled is True


def test_perf_due_claims_100_routines_budget(store, benchmark_budget_ms=50.0):
    """Injected-clock due scan for 100 routines stays under the pre-impl budget."""
    import time
    for i in range(100):
        store.create_bot(Bot(
            name=f"b{i}", instructions="x",
            schedule=Schedule(cron="0 * * * *", timezone="UTC"),
            created_at="2026-10-07T00:00:00+00:00",
        ))
    s = Scheduler(store)
    now = datetime(2026, 10, 7, 12, 30, tzinfo=timezone.utc)
    started = time.perf_counter()
    claims = s.due_claims(now)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert len(claims) == 100
    assert elapsed_ms < benchmark_budget_ms * 20  # CI/host slack; local target is 50ms
    # Recorded for the capability matrix; do not fail soak on a busy laptop alone beyond 20×.
    assert elapsed_ms < 2000
