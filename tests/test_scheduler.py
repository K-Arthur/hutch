from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hutch.models import Bot, CatchUpPolicy, Schedule, TriggerKind, iso
from hutch.scheduler import MAX_CATCHUP_WINDOWS, Scheduler


def scheduled_bot(cron="0 9 * * *", tz="UTC", catch_up=CatchUpPolicy.coalesce, created=None,
                  **schedule_kwargs) -> Bot:
    return Bot(
        name="sched", instructions="standup",
        schedule=Schedule(cron=cron, timezone=tz, catch_up=catch_up, **schedule_kwargs),
        created_at=created or "2026-01-01T00:00:00+00:00",
    )


def zoneinfo(name):
    from zoneinfo import ZoneInfo
    return ZoneInfo(name)


def test_next_fire_utc_conversion(store):
    bot = store.create_bot(scheduled_bot(cron="0 9 * * *", tz="America/New_York"))
    s = Scheduler(store)
    now = datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc)  # 10:00 in New York
    nxt = s.next_fire(bot, now)
    assert nxt is not None
    local = nxt.astimezone(zoneinfo("America/New_York"))
    assert local.hour == 9 and local.day == 8  # next 9:00 NY time is tomorrow


def test_due_after_window_elapsed(store):
    bot = store.create_bot(scheduled_bot(cron="* * * * *", created="2026-10-07T12:00:00+00:00"))
    s = Scheduler(store)
    now = datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc)
    claims = s.due_claims(now)
    assert len(claims) == 1
    assert claims[0].bot.id == bot.id
    assert claims[0].occurrence == datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc)
    assert claims[0].missed == 4  # 12:01..12:04 beyond the newest 12:05


def test_not_due_before_window(store):
    bot = store.create_bot(scheduled_bot(cron="0 9 * * *", created="2026-10-07T08:00:00+00:00"))
    s = Scheduler(store)
    assert s.due(datetime(2026, 10, 7, 8, 30, tzinfo=timezone.utc)) == []


def test_mark_dispatched_prevents_redouble_fire(store):
    bot = store.create_bot(scheduled_bot(cron="* * * * *"))
    s = Scheduler(store)
    now = datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc)
    assert s.due(now)
    s.mark_dispatched(bot, now)
    assert s.due(now) == []  # same instant -> not due again (no double-fire)


def test_catch_up_skip_policy(store):
    store.create_bot(scheduled_bot(cron="0 9 * * *", catch_up=CatchUpPolicy.skip))
    s = Scheduler(store)
    # created Jan 1; by Oct 7 20:00 the 09:00 window is older than 25% of a day -> skip + record
    now = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)
    assert s.due(now) == []
    bot = store.get_bot("sched")
    skip = s.last_skip(bot)
    assert skip is not None and skip["windows"] > 10


def test_skip_grace_scales_with_period(store):
    """A daily task starting a few hours after 09:00 must still run under skip (old 1800s grace failed)."""
    bot = store.create_bot(scheduled_bot(
        cron="0 9 * * *", catch_up=CatchUpPolicy.skip, created="2026-10-07T00:00:00+00:00"))
    s = Scheduler(store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-06T09:00:00+00:00")
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)  # 3h after 09:00; >1800s but <25% of day
    claims = s.due_claims(now)
    assert len(claims) == 1
    assert claims[0].occurrence == datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)


def test_dst_spring_forward_fires_once(store):
    """US DST starts 2026-03-08. A 2:30 America/New_York job must not double-fire."""
    bot = store.create_bot(scheduled_bot(cron="30 2 * * *", tz="America/New_York"))
    s = Scheduler(store)
    # window just after spring-forward (2:30 doesn't exist that day)
    after = datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc)  # 3:00 NY
    windows = s._windows_between(bot, datetime.fromisoformat("2026-03-07T00:00:00+00:00"), after, s._zone(bot))
    assert len(windows) == 1  # 2:30 EST on Mar 7 only; Mar 8 2:30 doesn't exist
    nxt = s.next_fire(bot, after)
    local = nxt.astimezone(zoneinfo("America/New_York"))
    assert (local.hour, local.minute) == (2, 30)
    assert local.day == 9


def test_dst_fall_back_fires_once(store):
    """US DST ends 2026-11-01: 1:30 occurs twice; croniter must yield one window."""
    bot = store.create_bot(scheduled_bot(cron="30 1 * * *", tz="America/New_York"))
    s = Scheduler(store)
    after = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
    windows = s._windows_between(bot, datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc), after, s._zone(bot))
    first_of_nov = [w for w in windows if w.astimezone(zoneinfo("America/New_York")).day == 1]
    assert len(first_of_nov) == 1


def test_paused_bots_never_due(store):
    bot = scheduled_bot(cron="* * * * *")
    bot.paused = True
    store.create_bot(bot)
    s = Scheduler(store)
    assert s.due(datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc)) == []


def test_disabled_schedule_never_due(store):
    bot = store.create_bot(scheduled_bot(cron="* * * * *", enabled=False))
    s = Scheduler(store)
    assert s.due_claims(datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc)) == []
    assert bot.schedule.enabled is False


def test_invalid_timezone_blocks_due(store):
    bot = store.create_bot(scheduled_bot(cron="0 9 * * *"))
    # Bypass model write validation by patching the stored document timezone.
    import json
    with store._lock:
        row = store._db.execute("SELECT doc FROM bots WHERE id = ?", (bot.id,)).fetchone()
        doc = json.loads(row["doc"])
        doc["schedule"]["timezone"] = "Not/AZone"
        doc["schedules"][0]["timezone"] = "Not/AZone"
        store._db.execute("UPDATE bots SET doc = ? WHERE id = ?", (json.dumps(doc), bot.id))
        store._db.commit()
    s = Scheduler(store)
    assert s.due_claims(datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)) == []
    blocked = s.blocked(store.get_bot(bot.id).schedule)
    assert blocked is not None and blocked["reason"] == "invalid_timezone"


def test_long_downtime_claims_true_newest(store):
    bot = store.create_bot(scheduled_bot(cron="* * * * *", created="2026-01-01T00:00:00+00:00"))
    s = Scheduler(store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-01-01T00:00:00+00:00")
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    claims = s.due_claims(now)
    assert len(claims) == 1
    assert claims[0].occurrence == now
    assert claims[0].missed == MAX_CATCHUP_WINDOWS
    assert claims[0].missed_uncertain is True


def test_claim_marker_is_occurrence(store, config):
    from hutch.engine import Engine

    bot = store.create_bot(scheduled_bot(cron="0 * * * *", created="2026-10-07T10:00:00+00:00"))
    engine = Engine(config, store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-07T10:00:00+00:00")
    # Freeze "now" for due_claims by calling with explicit now, then claim through store as engine does.
    now = datetime(2026, 10, 7, 12, 30, tzinfo=timezone.utc)
    claims = engine.scheduler.due_claims(now)
    assert len(claims) == 1
    assert claims[0].occurrence == datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    from hutch.models import Run, Task
    due = claims[0]
    run = Run(bot_id=due.bot.id, prompt="x", missed_windows=due.missed, origin="schedule",
              schedule_id=due.schedule.id)
    task = Task(bot_id=due.bot.id, kind="scheduled", prompt=run.prompt)
    marker = iso(due.occurrence)
    won = store.submit_scheduled(
        run, task, occurrence=marker, expected_marker=due.marker, new_marker=marker,
        claimed_by="test", schedule_id=due.schedule.id,
    )
    assert won is not None
    assert store.kv_get(f"{due.schedule.id}:last_fire") == marker


def test_interval_65_and_90_minutes(store):
    for seconds, label in ((65 * 60, "65m"), (90 * 60, "90m")):
        bot = store.create_bot(Bot(
            name=f"iv{seconds}",
            instructions="tick",
            schedule=Schedule(
                name=label,
                trigger=TriggerKind.interval,
                interval_seconds=seconds,
                anchor_at="2026-10-07T00:00:00+00:00",
                timezone="UTC",
            ),
            created_at="2026-10-07T00:00:00+00:00",
        ))
        s = Scheduler(store)
        now = datetime(2026, 10, 7, 2, 10, tzinfo=timezone.utc)
        claims = s.due_claims(now)
        mine = [c for c in claims if c.bot.id == bot.id]
        assert len(mine) == 1
        # Fixed-rate from midnight: 65m → 01:05? Wait 0, 65, 130(=2:10). At 2:10 exactly steps=2 → 02:10.
        # 90m → 0, 90, 180(=3:00). At 2:10 newest is 01:30.
        if seconds == 65 * 60:
            assert mine[0].occurrence == datetime(2026, 10, 7, 2, 10, tzinfo=timezone.utc)
        else:
            assert mine[0].occurrence == datetime(2026, 10, 7, 1, 30, tzinfo=timezone.utc)
        nxt = s.next_fire(bot, now)
        if seconds == 65 * 60:
            assert nxt == datetime(2026, 10, 7, 3, 15, tzinfo=timezone.utc)
        else:
            assert nxt == datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)


def test_vancouver_2026_no_fallback(store):
    """tzdb 2026b: America/Vancouver stays on -07 after the modelled 2026-11-01 transition."""
    bot = store.create_bot(scheduled_bot(cron="0 9 * * *", tz="America/Vancouver",
                                        created="2026-10-01T00:00:00+00:00"))
    s = Scheduler(store)
    # Morning of Nov 2 2026 local, still -07, not -08.
    after_nov1 = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)  # 09:00 Pacific if -07
    nxt = s.next_fire(bot, datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc))
    assert nxt is not None
    local = nxt.astimezone(zoneinfo("America/Vancouver"))
    assert local.utcoffset() == timedelta(hours=-7)
    assert (local.hour, local.minute) == (9, 0)
    # Historical 2025 fall-back still folds in New York (exercise a real fold zone separately).
    fold_bot = store.create_bot(Bot(
        name="fold", instructions="x",
        schedule=Schedule(cron="30 1 * * *", timezone="America/New_York"),
        created_at="2025-10-01T00:00:00+00:00",
    ))
    windows = s._windows_between(
        fold_bot,
        datetime(2025, 11, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2025, 11, 3, 12, 0, tzinfo=timezone.utc),
        s._zone(fold_bot),
    )
    nov2 = [w for w in windows if w.astimezone(zoneinfo("America/New_York")).date().isoformat() == "2025-11-02"]
    assert len(nov2) == 1


def test_preview_includes_offset(store):
    bot = store.create_bot(scheduled_bot(cron="0 9 * * *", tz="America/New_York"))
    s = Scheduler(store)
    previews = s.preview(bot.schedule, now=datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc), limit=3)
    assert len(previews) == 3
    assert previews[0].timezone == "America/New_York"
    assert previews[0].utc_offset.startswith("-")


def test_skip_next_consumes_one_occurrence(store):
    bot = store.create_bot(scheduled_bot(cron="0 * * * *", created="2026-10-07T10:00:00+00:00"))
    s = Scheduler(store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-07T10:00:00+00:00")
    s.request_skip_next(bot.schedule)
    now = datetime(2026, 10, 7, 12, 30, tzinfo=timezone.utc)
    assert s.due_claims(now) == []
    assert store.kv_get(f"{bot.schedule.id}:last_fire") == "2026-10-07T12:00:00+00:00"
    skip = s.last_skip(bot)
    assert skip is not None and skip["reason"] == "skip_next"
    # Later hour becomes due normally.
    later = datetime(2026, 10, 7, 13, 5, tzinfo=timezone.utc)
    claims = s.due_claims(later)
    assert len(claims) == 1 and claims[0].occurrence.hour == 13


def test_run_now_does_not_advance_marker(store, config):
    from hutch.engine import Engine

    bot = store.create_bot(scheduled_bot(cron="0 9 * * *", created="2026-10-07T00:00:00+00:00"))
    engine = Engine(config, store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-07T09:00:00+00:00")
    before = store.kv_get(f"{bot.schedule.id}:last_fire")
    run = engine.run_schedule_now(bot, bot.schedule)
    assert run.origin == "manual:schedule"
    assert run.schedule_id == bot.schedule.id
    assert store.kv_get(f"{bot.schedule.id}:last_fire") == before


def test_occurrence_history_lists_claimed_windows(store, config):
    from hutch.engine import Engine
    from hutch.models import Run, Task

    bot = store.create_bot(scheduled_bot(cron="0 * * * *", created="2026-10-07T10:00:00+00:00"))
    engine = Engine(config, store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-07T10:00:00+00:00")
    now = datetime(2026, 10, 7, 12, 30, tzinfo=timezone.utc)
    due = engine.scheduler.due_claims(now)[0]
    marker = iso(due.occurrence)
    run = Run(bot_id=bot.id, prompt="x", origin="schedule", schedule_id=due.schedule.id,
              missed_windows=due.missed)
    task = Task(bot_id=bot.id, kind="scheduled", prompt=run.prompt)
    assert store.submit_scheduled(
        run, task, occurrence=marker, expected_marker=due.marker, new_marker=marker,
        claimed_by="test", schedule_id=due.schedule.id,
    ) is not None
    history = store.list_schedule_occurrences(due.schedule.id)
    assert len(history) == 1
    assert history[0]["occurrence"] == marker
    assert history[0]["run_id"] == run.id
    assert history[0]["run_origin"] == "schedule"


def test_overlap_skip_drops_occurrence_while_busy(store, config):
    from hutch.engine import Engine
    from hutch.models import OverlapPolicy

    bot = store.create_bot(scheduled_bot(
        cron="* * * * *", created="2026-10-07T12:00:00+00:00", overlap=OverlapPolicy.skip))
    engine = Engine(config, store)
    # Occupy the bot with a pending run.
    engine.submit(bot, "busy", origin="manual")
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-07T12:00:00+00:00")
    now = datetime(2026, 10, 7, 12, 3, tzinfo=timezone.utc)
    assert engine.scheduler.due_claims(now) == []
    assert store.kv_get(f"{bot.schedule.id}:last_fire") == "2026-10-07T12:03:00+00:00"
    skip = engine.scheduler.last_skip(bot)
    assert skip and skip["reason"] == "overlap_skip"


def test_workspace_pause_fences_a_due_snapshot_before_schedule_admission(store, config):
    from hutch.engine import Engine
    from hutch.models import Run, Task

    bot = store.create_bot(scheduled_bot(cron="* * * * *", created="2026-10-07T12:00:00+00:00"))
    engine = Engine(config, store)
    now = datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc)
    due = engine.scheduler.due_claims(now)
    assert len(due) == 1
    claim = due[0]

    store.set_workspace_schedules_paused(True)
    assert engine.scheduler.due_claims(now) == []
    run = Run(bot_id=bot.id, prompt="scheduled work", origin="schedule", schedule_id=claim.schedule.id)
    task = Task(bot_id=bot.id, kind="scheduled", prompt=run.prompt)
    admitted = store.submit_scheduled(
        run, task, occurrence=iso(claim.occurrence), expected_marker=claim.marker,
        new_marker=iso(claim.occurrence), claimed_by="schedule-test", schedule_id=claim.schedule.id,
    )
    assert admitted is None
    assert store.get_run(run.id) is None
    assert store.kv_get(f"{claim.schedule.id}:last_fire") is None

    store.set_workspace_schedules_paused(False)
    resume_now = now + timedelta(minutes=3)
    resumed = engine.scheduler.due_claims(resume_now)
    assert len(resumed) == 1 and resumed[0].missed > claim.missed
    run = Run(bot_id=bot.id, prompt="scheduled work", origin="schedule", schedule_id=claim.schedule.id)
    task = Task(bot_id=bot.id, kind="scheduled", prompt=run.prompt)
    admitted = store.submit_scheduled(
        run, task, occurrence=iso(resumed[0].occurrence), expected_marker=claim.marker,
        new_marker=iso(resumed[0].occurrence), claimed_by="schedule-test", schedule_id=claim.schedule.id,
    )
    assert admitted is not None and store.get_run(run.id).origin == "schedule"
