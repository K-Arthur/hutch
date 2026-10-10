"""Cron and interval scheduling with timezone and missed-window correctness.

Answers the two most-cited scheduler failures (docs/research/complaints.md):

- "my laptop was asleep and the run silently never happened"
    -> every scheduled task records its last claimed/skipped occurrence; on wake,
       the engine sees N missed windows and (by policy) coalesces them into one
       catch-up run, recorded on the run itself (`missed_windows`).
- "2:30 schedules fire twice or never across DST"
    -> calendar math happens in the task's IANA zone with zoneinfo-aware
       conversion; we never compare naive local times across zones.

Long downtime must claim the *true* newest eligible occurrence. Enumerating only a
capped prefix and treating its last element as newest is a silent-miss defect.

All timestamps stored as ISO-8601 UTC with offset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from .models import (
    ACTIVE_STATUSES, Bot, CatchUpPolicy, OverlapPolicy, RunStatus, Schedule, TriggerKind, iso, utcnow,
)
from .store import Store

MAX_CATCHUP_WINDOWS = 50
MAX_PREVIEW_OCCURRENCES = 32
MAX_SCAN_ITERATIONS = 10_000  # hard bound so a pathological expression cannot monopolize the server


class InvalidScheduleZone(ValueError):
    """IANA zone missing or unusable; never silently replaced with UTC."""


@dataclass(frozen=True)
class DueClaim:
    """One schedule occurrence that is due: what to run, how many windows it stands for, and the marker value it was
    computed against (the claim only succeeds if nobody advanced the marker since: optimistic concurrency)."""

    bot: Bot
    schedule: Schedule
    missed: int
    occurrence: datetime
    marker: Optional[str]
    missed_uncertain: bool = False


@dataclass(frozen=True)
class OccurrencePreview:
    at: datetime
    timezone: str
    utc_offset: str
    note: str = ""


class Scheduler:
    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------- helpers

    @staticmethod
    def resolve_zone(name: str) -> ZoneInfo:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise InvalidScheduleZone(f"unknown IANA timezone: {name}") from exc
        except Exception as exc:
            raise InvalidScheduleZone(f"unusable timezone: {name}") from exc

    @staticmethod
    def _zone(scheduled: Bot | Schedule) -> ZoneInfo:
        """Resolve the schedule zone. Raises InvalidScheduleZone — never falls back to UTC."""
        schedule = scheduled.schedule if isinstance(scheduled, Bot) else scheduled
        name = schedule.timezone if schedule else "UTC"
        return Scheduler.resolve_zone(name)

    @staticmethod
    def try_zone(scheduled: Bot | Schedule) -> ZoneInfo | None:
        try:
            return Scheduler._zone(scheduled)
        except InvalidScheduleZone:
            return None

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

    @staticmethod
    def _last_fire_key(schedule: Schedule) -> str:
        return f"{schedule.id}:last_fire"

    def _note_blocked(self, schedule: Schedule, reason: str, detail: str = "") -> None:
        import json
        self.store.kv_set(
            f"{schedule.id}:blocked",
            json.dumps({"at": iso(utcnow()), "reason": reason, "detail": detail}),
        )

    def blocked(self, schedule: Schedule | None) -> dict | None:
        import json
        if schedule is None:
            return None
        raw = self.store.kv_get(f"{schedule.id}:blocked")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    # ---------------------------------------------------- trigger math

    def _newest_on_or_before(self, schedule: Schedule, now: datetime, zone: ZoneInfo) -> datetime | None:
        """Latest fire time in (-∞, now], or None."""
        if schedule.trigger == TriggerKind.interval:
            return self._newest_interval_on_or_before(schedule, now)
        if schedule.trigger == TriggerKind.once:
            when = self._once_at(schedule)
            return when if when is not None and when <= now else None
        local_now = self._to_local(now, zone)
        try:
            # croniter's get_prev from an exact boundary excludes that instant; nudge forward.
            itr = croniter(schedule.cron, local_now + timedelta(microseconds=1))
        except (croniter.CroniterBadCronError, ValueError):
            return None
        for _ in range(8):
            prev = itr.get_prev(datetime)
            utc = self._to_utc(prev, zone)
            if utc is None:
                continue
            if utc <= now:
                return utc
        return None

    def _next_after(self, schedule: Schedule, after: datetime, zone: ZoneInfo) -> datetime | None:
        """Strictly future fire after ``after``."""
        if schedule.trigger == TriggerKind.interval:
            return self._next_interval_after(schedule, after)
        if schedule.trigger == TriggerKind.once:
            when = self._once_at(schedule)
            return when if when is not None and when > after else None
        local = self._to_local(after, zone)
        try:
            itr = croniter(schedule.cron, local)
        except (croniter.CroniterBadCronError, ValueError):
            return None
        for _ in range(MAX_SCAN_ITERATIONS):
            nxt = itr.get_next(datetime)
            utc = self._to_utc(nxt, zone)
            if utc is None:
                continue
            if utc > after:
                return utc
        return None

    @staticmethod
    def _once_at(schedule: Schedule) -> datetime | None:
        raw = schedule.anchor_at
        if not raw:
            return None
        try:
            when = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.astimezone(timezone.utc)

    def _interval_anchor(self, schedule: Schedule) -> datetime:
        raw = schedule.anchor_at
        if raw:
            try:
                when = datetime.fromisoformat(raw)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                return when.astimezone(timezone.utc)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(schedule.created_at)
        except ValueError:
            return utcnow()

    def _newest_interval_on_or_before(self, schedule: Schedule, now: datetime) -> datetime | None:
        seconds = schedule.interval_seconds or 0
        if seconds < 1:
            return None
        anchor = self._interval_anchor(schedule)
        if now < anchor:
            return None
        elapsed = (now - anchor).total_seconds()
        steps = int(elapsed // seconds)
        return anchor + timedelta(seconds=steps * seconds)

    def _next_interval_after(self, schedule: Schedule, after: datetime) -> datetime | None:
        seconds = schedule.interval_seconds or 0
        if seconds < 1:
            return None
        anchor = self._interval_anchor(schedule)
        if after < anchor:
            return anchor
        elapsed = (after - anchor).total_seconds()
        steps = int(elapsed // seconds) + 1
        return anchor + timedelta(seconds=steps * seconds)

    def _count_windows(self, schedule: Schedule, last_utc: datetime, newest: datetime,
                       zone: ZoneInfo) -> tuple[int, bool]:
        """Count fires in (last_utc, newest]. Returns (count, uncertain_because_capped)."""
        if newest <= last_utc:
            return 0, False
        if schedule.trigger == TriggerKind.interval:
            seconds = schedule.interval_seconds or 0
            if seconds < 1:
                return 0, False
            # Fixed-rate grid from anchor; count steps from first fire after last through newest.
            first = self._next_interval_after(schedule, last_utc)
            if first is None or first > newest:
                return 0, False
            span = (newest - first).total_seconds()
            count = int(span // seconds) + 1
            if count > MAX_CATCHUP_WINDOWS:
                return MAX_CATCHUP_WINDOWS, True
            return count, False
        if schedule.trigger == TriggerKind.once:
            return (1, False)

        local_last = self._to_local(last_utc, zone)
        try:
            itr = croniter(schedule.cron, local_last)
        except (croniter.CroniterBadCronError, ValueError):
            return 0, False
        count = 0
        for _ in range(MAX_SCAN_ITERATIONS):
            nxt = itr.get_next(datetime)
            utc = self._to_utc(nxt, zone)
            if utc is None:
                continue
            if utc > newest:
                break
            if utc <= last_utc:
                continue
            count += 1
            if utc == newest:
                return count, False
            if count >= MAX_CATCHUP_WINDOWS and utc < newest:
                return MAX_CATCHUP_WINDOWS, True
        return count, count >= MAX_CATCHUP_WINDOWS and newest > last_utc

    def _estimated_period(self, schedule: Schedule, zone: ZoneInfo, now: datetime) -> float:
        """Seconds between two consecutive fires near ``now``; fallback 86400."""
        if schedule.trigger == TriggerKind.interval and schedule.interval_seconds:
            return float(schedule.interval_seconds)
        if schedule.trigger == TriggerKind.once:
            return 86400.0
        prev = self._newest_on_or_before(schedule, now, zone)
        if prev is None:
            nxt = self._next_after(schedule, now, zone)
            nxt2 = self._next_after(schedule, nxt, zone) if nxt else None
            if nxt and nxt2:
                return max(1.0, (nxt2 - nxt).total_seconds())
            return 86400.0
        nxt = self._next_after(schedule, prev, zone)
        if nxt is None:
            return 86400.0
        return max(1.0, (nxt - prev).total_seconds())

    def skip_grace(self, schedule: Schedule, zone: ZoneInfo, now: datetime) -> timedelta:
        """How late the newest window may be and still run under catch_up=skip."""
        period = self._estimated_period(schedule, zone, now)
        seconds = min(max(period * 0.25, 60.0), period)
        return timedelta(seconds=seconds)

    # ------------------------------------------------------------ next fire

    def next_fire(self, bot: Bot, now: datetime | None = None,
                  schedule: Schedule | None = None) -> datetime | None:
        """Next fire time for one recurring task (UTC-aware), or None."""
        schedule = schedule or bot.schedule
        if not schedule:
            return None
        now = now or utcnow()
        zone = self.try_zone(schedule)
        if zone is None:
            return None
        return self._next_after(schedule, now, zone)

    def preview(self, schedule: Schedule, now: datetime | None = None,
                limit: int = 8) -> list[OccurrencePreview]:
        """Concrete upcoming occurrences with zone and UTC offset (server-authoritative)."""
        now = now or utcnow()
        limit = max(1, min(limit, MAX_PREVIEW_OCCURRENCES))
        zone = self.try_zone(schedule)
        if zone is None:
            return []
        out: list[OccurrencePreview] = []
        cursor = now
        for _ in range(limit):
            nxt = self._next_after(schedule, cursor, zone)
            if nxt is None:
                break
            local = nxt.astimezone(zone)
            offset = local.utcoffset() or timedelta(0)
            total = int(offset.total_seconds())
            sign = "+" if total >= 0 else "-"
            total = abs(total)
            hh, mm = divmod(total // 60, 60)
            out.append(OccurrencePreview(
                at=nxt,
                timezone=schedule.timezone,
                utc_offset=f"{sign}{hh:02d}:{mm:02d}",
                note="schedule-local",
            ))
            cursor = nxt
        return out

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
        if self.store.workspace_schedule_control()["paused"]:
            return []
        now = now or utcnow()
        due: list[DueClaim] = []
        for bot in self.store.list_bots():
            if bot.paused:
                continue
            for schedule in bot.schedules or ([bot.schedule] if bot.schedule else []):
                if not schedule.enabled:
                    continue
                zone = self.try_zone(schedule)
                if zone is None:
                    self._note_blocked(schedule, "invalid_timezone", schedule.timezone)
                    continue
                marker = self.store.kv_get(self._last_fire_key(schedule))
                last_utc = self._parse_marker(marker, schedule, fallback_created_at=bot.created_at)
                newest = self._newest_on_or_before(schedule, now, zone)
                if newest is None or newest <= last_utc:
                    continue
                if self.consume_skip_next(schedule, newest):
                    self.store.kv_set(self._last_fire_key(schedule), iso(newest))
                    self._note_skipped(bot, 1, schedule, reason="skip_next")
                    continue
                count, uncertain = self._count_windows(schedule, last_utc, newest, zone)
                if count < 1:
                    continue
                # missed_windows = fires coalesced beyond the newest. When the counter hits the
                # bound before reaching newest, report the bound as a lower limit (uncertain).
                missed = MAX_CATCHUP_WINDOWS if uncertain else max(count - 1, 0)
                if schedule.catch_up is CatchUpPolicy.skip:
                    grace = self.skip_grace(schedule, zone, now)
                    if (now - newest) > grace:
                        self.store.kv_set(self._last_fire_key(schedule), iso(newest))
                        self._note_skipped(bot, count if not uncertain else MAX_CATCHUP_WINDOWS,
                                           schedule, uncertain=uncertain, reason="catch_up_skip")
                        continue
                if schedule.overlap is OverlapPolicy.skip and self._bot_busy(bot.id):
                    self.store.kv_set(self._last_fire_key(schedule), iso(newest))
                    self._note_skipped(bot, 1, schedule, reason="overlap_skip")
                    continue
                if schedule.overlap is OverlapPolicy.buffer_one and self._schedule_has_pending(schedule.id):
                    # Keep the existing pending run; do not advance the marker so a later tick
                    # can coalesce once that pending attempt finishes or fails.
                    continue
                due.append(DueClaim(
                    bot=bot, schedule=schedule, missed=missed, occurrence=newest,
                    marker=marker, missed_uncertain=uncertain,
                ))
        return due

    def _bot_busy(self, bot_id: str) -> bool:
        if self.store.active_run_for_bot(bot_id) is not None:
            return True
        return any(run.status is RunStatus.pending for run in self.store.list_runs(bot_id=bot_id, limit=20))

    def _schedule_has_pending(self, schedule_id: str) -> bool:
        for run in self.store.list_runs(limit=50):
            if run.schedule_id == schedule_id and run.status in ACTIVE_STATUSES:
                return True
        return False

    def request_skip_next(self, schedule: Schedule) -> None:
        """Skip the next due occurrence once; does not change the recurring definition."""
        self.store.kv_set(f"{schedule.id}:skip_next", "1")

    def consume_skip_next(self, schedule: Schedule, occurrence: datetime) -> bool:
        raw = self.store.kv_get(f"{schedule.id}:skip_next")
        if not raw:
            return False
        self.store.kv_set(f"{schedule.id}:skip_next", "")
        self.store.kv_set(
            f"{schedule.id}:last_skip_next",
            iso(occurrence),
        )
        return True

    def _windows_between(self, scheduled: Bot | Schedule, last_utc: datetime, now: datetime,
                         zone: ZoneInfo | None = None) -> list[datetime]:
        """Fire times in (last, now], newest-accurate.

        For short ranges returns every window. When more than ``MAX_CATCHUP_WINDOWS`` fires
        exist, returns ``[first_after_last, … up to cap-1 …, true_newest]`` so callers that
        take ``windows[-1]`` as newest remain correct. Prefer ``due_claims`` for dispatch.
        """
        schedule = scheduled.schedule if isinstance(scheduled, Bot) else scheduled
        if schedule is None:
            return []
        zone = zone or self.try_zone(schedule)
        if zone is None:
            return []
        newest = self._newest_on_or_before(schedule, now, zone)
        if newest is None or newest <= last_utc:
            return []
        if schedule.trigger in (TriggerKind.interval, TriggerKind.once):
            out: list[datetime] = []
            cursor = last_utc
            for _ in range(MAX_CATCHUP_WINDOWS):
                nxt = self._next_after(schedule, cursor, zone)
                if nxt is None or nxt > newest:
                    break
                out.append(nxt)
                cursor = nxt
            if out and out[-1] != newest:
                if len(out) >= MAX_CATCHUP_WINDOWS:
                    out[-1] = newest
                else:
                    out.append(newest)
            elif not out:
                out = [newest]
            return out

        local_last = self._to_local(last_utc, zone)
        try:
            itr = croniter(schedule.cron, local_last)
        except (croniter.CroniterBadCronError, ValueError):
            return []
        out = []
        for _ in range(MAX_CATCHUP_WINDOWS):
            nxt = itr.get_next(datetime)
            utc = self._to_utc(nxt, zone)
            if utc is None:
                continue
            if utc > newest:
                break
            if utc > last_utc:
                out.append(utc)
            if utc == newest:
                return out
        if out and out[-1] != newest:
            out[-1] = newest
        elif not out:
            out = [newest]
        return out

    def _last_dispatched(self, bot: Bot, schedule: Schedule | None = None) -> datetime:
        schedule = schedule or bot.schedule
        return self._parse_marker(self.store.kv_get(self._last_fire_key(schedule)), schedule)

    @staticmethod
    def _parse_marker(raw: Optional[str], scheduled: Bot | Schedule,
                      fallback_created_at: str | None = None) -> datetime:
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(fallback_created_at or scheduled.created_at)
        except ValueError:
            return utcnow()

    def mark_dispatched(self, bot: Bot, now: datetime | None = None, schedule: Schedule | None = None) -> None:
        """Advance the progress marker. Prefer the claimed occurrence instant, not processing time."""
        schedule = schedule or bot.schedule
        self.store.kv_set(self._last_fire_key(schedule), iso(now or utcnow()))

    def _note_skipped(self, bot: Bot, n_windows: int, schedule: Schedule | None = None,
                      *, uncertain: bool = False, reason: str = "catch_up_skip") -> None:
        """Silent non-runs are the #1 scheduler complaint — record skips visibly."""
        import json
        schedule = schedule or bot.schedule
        self.store.kv_set(
            f"{schedule.id}:last_skip",
            json.dumps({"at": iso(utcnow()), "windows": n_windows, "uncertain": uncertain,
                        "reason": reason}),
        )

    def last_skip(self, bot: Bot, schedule: Schedule | None = None) -> dict | None:
        import json
        schedule = schedule or bot.schedule
        if schedule is None:
            return None
        raw = self.store.kv_get(f"{schedule.id}:last_skip")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None
