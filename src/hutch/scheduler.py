"""Cron scheduling with timezone and missed-window correctness.

Answers the two most-cited scheduler failures (docs/research/complaints.md):

- "my laptop was asleep and the run silently never happened"
    -> every scheduled bot records its last dispatched window; on wake, the
       engine sees N missed windows and (by policy) coalesces them into one
       catch-up run, recorded on the run itself (`missed_windows`).
- "2:30 schedules fire twice or never across DST"
    -> cron math happens in the bot's IANA zone with zoneinfo-aware
       conversion; we never compare naive local times across zones.

All timestamps stored as ISO-8601 UTC with offset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from croniter import croniter

from .models import Bot, CatchUpPolicy, iso, utcnow
from .store import Store

MAX_CATCHUP_WINDOWS = 50


@dataclass(frozen=True)
class DueClaim:
    """One schedule occurrence that is due: what to run, how many windows it stands for, and the marker value it was
    computed against (the claim only succeeds if nobody advanced the marker since: optimistic concurrency)."""

    bot: Bot
    missed: int
    occurrence: datetime
    marker: Optional[str]


class Scheduler:
    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _zone(bot: Bot) -> ZoneInfo:
        try:
            return ZoneInfo(bot.schedule.timezone if bot.schedule else "UTC")
        except Exception:
            return ZoneInfo("UTC")

    @staticmethod
    def _to_local(dt_utc: datetime, zone: ZoneInfo) -> datetime:
        return dt_utc.astimezone(zone).replace(tzinfo=None)

    @staticmethod
    def _to_utc(dt_local_naive: datetime, zone: ZoneInfo) -> datetime | None:
        """Localize a naive local time; None if it doesn't exist (DST spring-forward gap).

        Vixie-cron semantics: times skipped by the clock jump simply don't fire;
        ambiguous fall-back times fire once (first occurrence, fold=0).
        """
        aware = dt_local_naive.replace(tzinfo=zone)
        roundtrip = aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        if roundtrip != dt_local_naive:
            return None
        return aware.astimezone(timezone.utc)

    def _last_fire_key(self, bot: Bot) -> str:
        return f"schedule:{bot.id}:last_fire"

    # ------------------------------------------------------------ next fire

    def next_fire(self, bot: Bot, now: datetime | None = None) -> datetime | None:
        """Next fire time (UTC-aware) for a scheduled bot, or None."""
        if not bot.schedule:
            return None
        now = now or utcnow()
        zone = self._zone(bot)
        local = self._to_local(now, zone)
        try:
            itr = croniter(bot.schedule.cron, local)
            for _ in range(3):  # skip at most a couple of DST-gap times
                nxt = itr.get_next(datetime)
                utc = self._to_utc(nxt, zone)
                if utc is not None:
                    return utc
        except (croniter.CroniterBadCronError, ValueError):
            return None
        return None

    # ---------------------------------------------------------- due checks

    def due(self, now: datetime | None = None) -> list[tuple[Bot, int]]:
        """Scheduled bots whose window has passed since their last dispatch.

        Returns (bot, missed_windows) pairs - missed_windows counts the windows
        that elapsed beyond the newest one (machine asleep, daemon down, ...).
        This only *reads*; the engine claims an occurrence with ``due_claims`` and ``Store.submit_scheduled``.
        """
        return [(d.bot, d.missed) for d in self.due_claims(now)]

    def due_claims(self, now: datetime | None = None) -> list[DueClaim]:
        """``due()`` with the newest window and the marker value it was judged against, for an atomic claim."""
        now = now or utcnow()
        due: list[DueClaim] = []
        for bot in self.store.list_bots():
            if bot.paused or not bot.schedule:
                continue
            zone = self._zone(bot)
            marker = self.store.kv_get(self._last_fire_key(bot))
            last_utc = self._parse_marker(marker, bot)
            windows = self._windows_between(bot, last_utc, now, zone)
            if not windows:
                continue
            newest = windows[-1]
            missed = min(len(windows) - 1, MAX_CATCHUP_WINDOWS)
            if bot.schedule.catch_up is CatchUpPolicy.skip:
                # Only run if the newest window is recent; otherwise note & skip.
                if (now - newest).total_seconds() > 1800:
                    self.store.kv_set(self._last_fire_key(bot), iso(newest))
                    self._note_skipped(bot, len(windows))
                    continue
            due.append(DueClaim(bot=bot, missed=missed, occurrence=newest, marker=marker))
        return due

    def _windows_between(self, bot: Bot, last_utc: datetime, now: datetime, zone: ZoneInfo) -> list[datetime]:
        """All fire times in (last, now], computed in the bot's zone."""
        local_last = self._to_local(last_utc, zone)
        local_now = self._to_local(now, zone)
        try:
            itr = croniter(bot.schedule.cron, local_last)  # type: ignore[union-attr]
        except (croniter.CroniterBadCronError, ValueError):
            return []
        out: list[datetime] = []
        for _ in range(MAX_CATCHUP_WINDOWS + 3):
            nxt = itr.get_next(datetime)
            if nxt > local_now:
                break
            utc = self._to_utc(nxt, zone)
            if utc is not None:  # None = DST gap, time never happened
                out.append(utc)
        return out

    def _last_dispatched(self, bot: Bot) -> datetime:
        return self._parse_marker(self.store.kv_get(self._last_fire_key(bot)), bot)

    @staticmethod
    def _parse_marker(raw: Optional[str], bot: Bot) -> datetime:
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(bot.created_at)
        except ValueError:
            return utcnow()

    def mark_dispatched(self, bot: Bot, now: datetime | None = None) -> None:
        self.store.kv_set(self._last_fire_key(bot), iso(now or utcnow()))

    def _note_skipped(self, bot: Bot, n_windows: int) -> None:
        """Silent non-runs are the #1 scheduler complaint — record skips visibly."""
        import json
        self.store.kv_set(
            f"schedule:{bot.id}:last_skip",
            json.dumps({"at": iso(utcnow()), "windows": n_windows}),
        )

    def last_skip(self, bot: Bot) -> dict | None:
        raw = self.store.kv_get(f"schedule:{bot.id}:last_skip")
        if not raw:
            return None
        try:
            import json
            return json.loads(raw)
        except ValueError:
            return None
