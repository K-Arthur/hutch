from __future__ import annotations

from datetime import datetime, timedelta, timezone

from openbot.models import Bot, CatchUpPolicy, Schedule
from openbot.scheduler import Scheduler


def scheduled_bot(cron="0 9 * * *", tz="UTC", catch_up=CatchUpPolicy.coalesce, created=None) -> Bot:
    return Bot(
        name="sched", instructions="standup",
        schedule=Schedule(cron=cron, timezone=tz, catch_up=catch_up),
        created_at=created or "2026-01-01T00:00:00+00:00",
    )


def test_next_fire_utc_conversion(store):
    bot = store.create_bot(scheduled_bot(cron="0 9 * * *", tz="America/New_York"))
    s = Scheduler(store)
    now = datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc)  # 10:00 in New York
    nxt = s.next_fire(bot, now)
    assert nxt is not None
    local = nxt.astimezone(zoneinfo("America/New_York"))
    assert local.hour == 9 and local.day == 8  # next 9:00 NY time is tomorrow


def zoneinfo(name):
    from zoneinfo import ZoneInfo
    return ZoneInfo(name)


def test_due_after_window_elapsed(store):
    bot = store.create_bot(scheduled_bot(cron="* * * * *"))  # every minute
    s = Scheduler(store)
    now = datetime(2026, 10, 7, 12, 5, tzinfo=timezone.utc)
    due = s.due(now)
    assert len(due) == 1
    assert due[0][0].id == bot.id
    assert due[0][1] >= 4  # ~5 minutes of windows since creation -> 4+ missed


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
    # created Jan 1; by Oct 7 the 9:00 windows are long past -> skip + record
    now = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)
    assert s.due(now) == []
    bot = store.get_bot("sched")
    skip = s.last_skip(bot)
    assert skip is not None and skip["windows"] > 10


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
    """US DST ends 2026-11-01: 1:30 occurs twice — croniter must yield one window."""
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
