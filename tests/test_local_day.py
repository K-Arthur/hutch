"""'Today' for every daily figure is the LOCAL calendar day, in one place (found by a test that failed 17:00-24:00 in
a UTC-7 timezone: the daily token cap compared a local-date prefix with UTC timestamps and counted nothing)."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from hutch.models import Bot, Run, iso, local_day_bounds


@pytest.fixture()
def tz():
    old = os.environ.get("TZ")

    def set_tz(name):
        os.environ["TZ"] = name
        time.tzset()
    yield set_tz
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_the_day_is_the_local_day_converted_to_utc(tz):
    tz("America/Los_Angeles")                                  # UTC-7 in October
    start, end = local_day_bounds(utc(2026, 10, 8, 0, 11))     # 17:11 on Oct 7 locally, but Oct 8 in UTC
    assert (start, end) == ("2026-10-07T07:00:00+00:00", "2026-10-08T07:00:00+00:00")
    tz("Asia/Tokyo")                                           # UTC+9: 09:11 on Oct 8 locally
    assert local_day_bounds(utc(2026, 10, 8, 0, 11)) == ("2026-10-07T15:00:00+00:00", "2026-10-08T15:00:00+00:00")
    tz("UTC")
    assert local_day_bounds(utc(2026, 10, 8, 0, 11)) == ("2026-10-08T00:00:00+00:00", "2026-10-09T00:00:00+00:00")


def test_a_daylight_saving_day_is_25_hours_long(tz):
    tz("America/Los_Angeles")
    start, end = local_day_bounds(utc(2026, 11, 1, 12, 0))     # clocks go back on 1 Nov 2026
    hours = (datetime.fromisoformat(end) - datetime.fromisoformat(start)) / timedelta(hours=1)
    assert hours == 25
    start, end = local_day_bounds(utc(2026, 3, 8, 20, 0))      # and forward on 8 Mar 2026
    assert (datetime.fromisoformat(end) - datetime.fromisoformat(start)) / timedelta(hours=1) == 23


@pytest.mark.parametrize("zone", ["America/Los_Angeles", "UTC", "Asia/Tokyo", "Pacific/Kiritimati"])
@pytest.mark.parametrize("hour", [0, 3, 7, 12, 16, 17, 23])
def test_a_run_created_now_always_counts_toward_today(store, tz, zone, hour):
    tz(zone)
    now = utc(2026, 10, 8, hour, 11)
    bot = store.create_bot(Bot(name="b"))
    run = store.create_run(Run(bot_id=bot.id, prompt="x", tokens=500, cost_usd=0.25, created_at=iso(now)))
    assert store.tokens_today(bot.id, now) == 500 and store.cost_today(bot.id, now) == pytest.approx(0.25)


def test_yesterday_and_tomorrow_do_not_count(store, tz):
    tz("America/Los_Angeles")
    now = utc(2026, 10, 8, 0, 11)                              # Oct 7, 17:11 local
    bot = store.create_bot(Bot(name="b"))
    for dt, tok in ((utc(2026, 10, 7, 6, 59), 1), (utc(2026, 10, 7, 7, 0), 10), (utc(2026, 10, 8, 6, 59), 100),
                    (utc(2026, 10, 8, 7, 0), 1000)):
        store.create_run(Run(bot_id=bot.id, prompt="x", tokens=tok, created_at=iso(dt)))
    assert store.tokens_today(bot.id, now) == 110, "only 07:00Z on Oct 7 up to 06:59Z on Oct 8 is Oct 7 in Los Angeles"


def test_other_bots_are_not_counted(store, tz):
    tz("UTC")
    a, b = store.create_bot(Bot(name="a")), store.create_bot(Bot(name="b"))
    store.create_run(Run(bot_id=a.id, prompt="x", tokens=7, cost_usd=1.0))
    store.create_run(Run(bot_id=b.id, prompt="x", tokens=9, cost_usd=2.0))
    assert store.tokens_today(a.id) == 7 and store.cost_today(a.id) == 1.0 and store.cost_today() == 3.0


def test_the_daily_cost_cap_uses_the_same_day(store, tz):
    from hutch.providers.pricing import PriceBook
    from hutch.runtime.ladder import SpendGuard
    tz("America/Los_Angeles")
    bot = store.create_bot(Bot(name="b"))
    run = Run(bot_id=bot.id, prompt="x")
    store.create_run(Run(bot_id=bot.id, prompt="x", cost_usd=0.4))
    assert SpendGuard(store, bot, run, PriceBook()).spent_today() == pytest.approx(0.4)
