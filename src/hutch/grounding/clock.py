"""One authoritative clock for every time-sensitive Hutch path.

Why this module exists (grounding slice):

* **UTC instants order events; IANA zones express civil intent; monotonic time measures
  durations.** Mixing these is the root cause of DST double-fires, "ten minutes ago"
  drift, and answers that silently move relative timestamps.
* Timezone rules come from the host's zoneinfo data at call time. Hutch does not hardcode
  political DST history, and it does not assume the host and a browser agree: callers that
  render another device's civil time ask for the zone explicitly.
* A clock is *injected* into parser, planner, tool and test code. Tests freeze it; the
  product never re-reads the wall clock behind a parser's back.

This is deliberately tiny. Everything else in ``grounding`` takes a ``Clock`` parameter.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc


class Clock(Protocol):
    """The two time sources the product may use. Nothing else calls ``datetime``/``time``."""

    def now(self) -> datetime:  # aware, UTC
        ...

    def monotonic(self) -> float:  # seconds, process-relative
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return _time.monotonic()


@dataclass(frozen=True)
class FrozenClock:
    """Deterministic clock for tests and historical replay.

    ``advance`` returns a NEW clock; a frozen instant is never mutated in place, so a
    test cannot accidentally change a timestamp it already handed to a parser.
    """

    instant: datetime
    _monotonic: float = 0.0

    def __post_init__(self):
        if self.instant.tzinfo is None:
            raise ValueError("FrozenClock requires an aware UTC instant")

    def now(self) -> datetime:
        return self.instant

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> "FrozenClock":
        return FrozenClock(self.instant + timedelta(seconds=seconds), self._monotonic + seconds)

    @classmethod
    def at(cls, iso_text: str) -> "FrozenClock":
        return cls(datetime.fromisoformat(iso_text.replace("Z", "+00:00")))


SYSTEM_CLOCK: Clock = SystemClock()

#: how far in the future an instant may look before Hutch labels the source as clock-skewed
FUTURE_TOLERANCE = timedelta(minutes=5)


class UnknownZone(ValueError):
    """The requested IANA zone name is not in the host's timezone database."""


def load_zone(name: str) -> ZoneInfo:
    """Resolve an IANA zone from the current tzdata; never guess or fall back silently."""
    if not name or not isinstance(name, str):
        raise UnknownZone("a timezone name is required")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise UnknownZone(f"unknown timezone {name!r}; use an IANA name like 'America/Vancouver'") from exc


def utc_iso(dt: datetime) -> str:
    """Store and order every instant in UTC with an explicit offset."""
    if dt.tzinfo is None:
        raise ValueError("naive datetimes may not be stored: a missing offset is unknown, not UTC")
    return dt.astimezone(UTC).isoformat()


def civil(instant: datetime, zone_name: str) -> str:
    """A civil display string for one instant in one zone, with the numeric offset shown.

    Relative-time rendering is a presentation concern layered on top of this; the exact
    representation never depends on "now" so a saved answer does not drift when reopened.
    """
    zone = load_zone(zone_name)
    local = instant.astimezone(zone)
    offset = local.utcoffset() or timedelta(0)
    sign = "+" if offset >= timedelta(0) else "-"
    offset = abs(offset)
    hours, minutes = divmod(int(offset.total_seconds()) // 60, 60)
    return f"{local.strftime('%Y-%m-%d %H:%M:%S')} {zone_name} ({sign}{hours:02d}:{minutes:02d})"


def fold_note(instant: datetime, zone_name: str) -> str:
    """A short, honest note when a civil time is ambiguous (DST fold); the resolved offset disambiguates."""
    zone = load_zone(zone_name)
    local = instant.astimezone(zone)
    try:
        first = local.replace(fold=0).utcoffset()
        second = local.replace(fold=1).utcoffset()
    except (ValueError, OverflowError):  # pragma: no cover - extreme dates
        return ""
    if first != second:
        offset = local.utcoffset() or timedelta(0)
        sign = "+" if offset >= timedelta(0) else "-"
        hours, minutes = divmod(int(abs(offset).total_seconds()) // 60, 60)
        return (f"this civil time is ambiguous in {zone_name} (daylight-saving fold); the resolved "
                f"offset {sign}{hours:02d}:{minutes:02d} disambiguates it")
    return ""


@dataclass(frozen=True)
class ClockRef:
    """The reference instant of one request, packaged for parsers and rendering.

    ``instant`` is when the request was received (UTC); ``monotonic`` is the process
    duration marker for in-process budgets.
    """

    instant: datetime
    monotonic: float
    timezone_name: str = "UTC"
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_clock(cls, clock: Clock, timezone_name: str = "UTC") -> "ClockRef":
        if timezone_name:
            load_zone(timezone_name)  # fail fast on a bad zone at the boundary
        return cls(clock.now(), clock.monotonic(), timezone_name)

    def civil_now(self) -> str:
        return civil(self.instant, self.timezone_name)
