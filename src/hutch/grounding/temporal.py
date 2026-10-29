"""Timestamp semantics: distinct roles, honest precision, and anchored relative phrases.

The rules this module enforces (mission sections 7):

* **A timestamp is (raw text, role, method, precision, zone), not a float.** Parsing
  keeps the raw string; the parsed instant is a convenience with recorded uncertainty.
* **Unknown is not UTC and not now.** A date without an offset, a date without a year,
  or a `-0000` RFC-822 zone stay marked unknown/uncertain.
* **Every relative phrase is anchored to its own speaker/document.** "Ten minutes ago"
  in the user's request is anchored to the request clock; the same phrase inside a
  three-month-old quote is anchored to that document's timestamp, that is why
  ``parse_relative`` takes an explicit ``reference``.
* **Roles never collapse.** Run/transcript time is not the event time; GDELT's
  ``seendate`` is an index observation; EXIF is a capture clue, not proof of when an
  event happened. Callers pass the role; this module never infers occurrence time from
  retrieval time.

Deliberately small and dependency-free (stdlib only) so it can be unit-tested against
frozen clocks and reused by adapters, tools, and rendering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Iterable, Optional

from .clock import UTC, Clock, UnknownZone, load_zone, utc_iso

_ISO_RE = re.compile(
    r"^(?P<y>\d{4})-(?P<m>\d{2})(?:-(?P<d>\d{2}))?"
    r"(?:[T ](?P<H>\d{2}):(?P<M>\d{2})(?::(?P<S>\d{2})(?:\.(?P<f>\d{1,9}))?)?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?)?$"
)
_GDELT_RE = re.compile(r"^(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})T(?P<H>\d{2})(?P<M>\d{2})(?P<S>\d{2})Z$")
_SLASH_RE = re.compile(r"^(?P<a>\d{1,2})/(?P<b>\d{1,2})/(?P<y>\d{4})$")
_MONTH_DAY_RE = re.compile(
    r"^(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(?P<y>\d{4}))?(?:\s+(?P<H>\d{1,2}):(?P<M>\d{2})(?:\s*(?P<ampm>am|pm))?)?$",
    re.IGNORECASE,
)

_REL_UNITS = {
    "second": timedelta(seconds=1), "sec": timedelta(seconds=1),
    "minute": timedelta(minutes=1), "min": timedelta(minutes=1),
    "hour": timedelta(hours=1), "hr": timedelta(hours=1),
    "day": timedelta(days=1), "week": timedelta(weeks=1), "month": timedelta(days=30),
    "year": timedelta(days=365),
}
_REL_RE = re.compile(
    r"\b(?P<n>\d{1,3}|an?|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?P<u>second|sec|minute|min|hour|hr|day|week|month|year)s?\s+ago\b",
    re.IGNORECASE,
)
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
          "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


class TimestampRole(str, Enum):
    """What a timestamp is evidence OF. These are never averaged together."""

    occurrence = "occurrence"          # when the reported event happened / its validity interval
    announcement = "announcement"      # when something was announced or claimed
    publication = "publication"        # source-declared publish time
    modification = "modification"      # source-declared update/edited time
    capture = "capture"                # device/EXIF-style capture clue
    upload = "upload"                  # platform upload/creation time
    index = "index"                    # crawler/stream/API observation of an item
    retrieval = "retrieval"            # when Hutch fetched it
    verification = "verification"      # when a check was performed or a fact check was published
    extraction = "extraction"          # when a passage was extracted from a page


class Precision(str, Enum):
    second = "second"
    minute = "minute"
    hour = "hour"
    day = "day"
    month = "month"
    year = "year"
    unknown = "unknown"


@dataclass
class TimestampValue:
    """One timestamp produced by one method, with its uncertainty preserved.

    ``instant``/``end_instant`` are UTC ISO strings; for coarse precision ``end_instant``
    closes the civil interval (a date-only value spans [start, next-day-start)). None of
    the parsers will ever invent seconds the source did not provide.
    """

    raw: str
    role: str = TimestampRole.index.value
    method: str = "unknown"
    instant: Optional[str] = None
    end_instant: Optional[str] = None
    precision: str = Precision.unknown.value
    timezone_name: Optional[str] = None   # IANA name when the offset is trustworthy
    uncertain: bool = False
    future: bool = False
    note: str = ""

    @property
    def parsed(self) -> Optional[datetime]:
        return datetime.fromisoformat(self.instant) if self.instant else None

    def ordering_key(self) -> tuple:
        """Sort key: parsed instants first (oldest first), unknown values last (never 'now')."""
        if self.instant is None:
            return (1, "")
        return (0, self.instant)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"raw": self.raw, "role": self.role, "method": self.method,
                               "precision": self.precision}
        for key in ("instant", "end_instant", "timezone_name", "note"):
            value = getattr(self, key)
            if value:
                out[key] = value
        if self.uncertain:
            out["uncertain"] = True
        if self.future:
            out["future"] = True
        return out

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TimestampValue":
        return cls(
            raw=str(data.get("raw", "")), role=str(data.get("role", TimestampRole.index.value)),
            method=str(data.get("method", "unknown")), instant=data.get("instant"),
            end_instant=data.get("end_instant"), precision=str(data.get("precision", Precision.unknown.value)),
            timezone_name=data.get("timezone_name"), uncertain=bool(data.get("uncertain")),
            future=bool(data.get("future")), note=str(data.get("note", "")))

    def describe(self) -> str:
        """A one-line, honest description suitable for the model brief and the UI."""
        parts = [f"{self.role} {self.instant or 'time unknown'}"]
        if self.end_instant and self.end_instant != self.instant:
            parts.append(f"until {self.end_instant}")
        parts.append(f"precision={self.precision}")
        if self.timezone_name:
            parts.append(f"tz={self.timezone_name}")
        if self.uncertain:
            parts.append("uncertain")
        if self.future:
            parts.append("future-dated")
        if self.note:
            parts.append(self.note)
        return "; ".join(parts)


def _finish(ts: TimestampValue, clock: Optional[Clock]) -> TimestampValue:
    if ts.instant and clock is not None:
        try:
            if datetime.fromisoformat(ts.instant) > clock.now():
                ts.future = True
        except ValueError:  # pragma: no cover - instant always comes from utc_iso
            pass
    return ts


def parse_iso(raw: str, *, role: str = TimestampRole.index.value, default_tz: Optional[str] = None,
              method: str = "iso8601", clock: Optional[Clock] = None) -> Optional[TimestampValue]:
    """Parse ISO-8601 into a role-tagged value. Returns None when the text is not ISO-like.

    * offset present (``Z``/``+02:00``) -> exact instant, trustworthy zone
    * offset absent -> parsed in ``default_tz`` when given; otherwise kept with
      ``uncertain=True`` and no civil resolution (never silently UTC)
    * date-only ``YYYY-MM-DD`` / month-only ``YYYY-MM`` -> civil-day/month interval
    """
    text = (raw or "").strip()
    m = _ISO_RE.match(text)
    if not m:
        return None
    y, mo = int(m["y"]), int(m["m"])
    d = int(m["d"]) if m["d"] else None
    tz_part, h, mi = m["tz"], m["H"], m["M"]
    frac = m["f"] or ""
    if d is None:
        # month precision
        start = datetime(y, mo, 1, tzinfo=_tz_or(default_tz, None)[0])
        end = datetime(y + (mo == 12), (mo % 12) + 1, 1, tzinfo=start.tzinfo)
        ts = TimestampValue(raw=text, role=role, method=method, instant=utc_iso(start),
                            end_instant=utc_iso(end), precision=Precision.month.value,
                            timezone_name=_tz_or(default_tz, None)[1])
        return _finish(ts, clock)
    if tz_part:
        if tz_part == "Z":
            tzinfo, tz_name, tz_note = timezone.utc, None, ""
        else:
            tzinfo = _fixed_offset(tz_part)
            tz_name = None
            tz_note = f"literal UTC offset {tz_part} in the source (not an IANA zone)"
        dt = datetime(y, mo, d, int(h or 0), int(mi or 0), int(m["S"] or 0),
                      int((frac + "000000")[:6]), tzinfo=tzinfo)
        precision = Precision.second if m["S"] else Precision.minute
        return _finish(TimestampValue(raw=text, role=role, method=method, instant=utc_iso(dt),
                                      precision=precision.value, timezone_name=tz_name, note=tz_note), clock)
    if h is not None:
        if default_tz:
            zone = load_zone(default_tz)
            dt = datetime(y, mo, d, int(h), int(mi or 0), 0, tzinfo=zone)
            return _finish(TimestampValue(raw=text, role=role, method=method, instant=utc_iso(dt),
                                          precision=Precision.minute.value, timezone_name=default_tz), clock)
        dt = datetime(y, mo, d, int(h), int(mi or 0), 0, tzinfo=UTC)
        return _finish(TimestampValue(raw=text, role=role, method=method, instant=utc_iso(dt),
                                      precision=Precision.minute.value, uncertain=True,
                                      note="no UTC offset in the source; the civil time is unresolved"), clock)
    # date-only -> civil-day interval
    zone_name = default_tz
    zone = load_zone(default_tz) if default_tz else UTC
    start = datetime(y, mo, d, tzinfo=zone)
    end = start + timedelta(days=1)
    note = "" if default_tz else "date-only value with no timezone; the day interval is shown in UTC civil time"
    return _finish(TimestampValue(raw=text, role=role, method=method, instant=utc_iso(start),
                                  end_instant=utc_iso(end), precision=Precision.day.value,
                                  timezone_name=zone_name, note=note), clock)


def _fixed_offset(text: str) -> timezone:
    sign = 1 if text[0] == "+" else -1
    digits = text[1:].replace(":", "")
    hours, minutes = int(digits[:2]), int(digits[2:] or 0)
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _tz_or(value: str, fallback: Optional[str]) -> tuple[Any, Optional[str]]:
    name = value or fallback
    if not name:
        return UTC, None
    try:
        return load_zone(name), name
    except UnknownZone:
        return UTC, None


def parse_rfc822(raw: str, *, role: str = TimestampRole.publication.value,
                 method: str = "rfc822", clock: Optional[Clock] = None) -> Optional[TimestampValue]:
    """Parse feed-style RFC 822/1123 dates (``Tue, 08 Oct 2026 05:30:00 GMT``).

    ``-0000`` means "offset unknown" per RFC 2822; that stays marked uncertain rather than
    being dressed up as UTC.
    """
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    unknown_zone = text.endswith("-0000") or parsed.tzinfo is None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    precision = Precision.second if re.search(r"\d{2}:\d{2}:\d{2}", text) else Precision.minute
    note = "the source declared an unknown offset (-0000); treated as UTC for ordering only" if unknown_zone else ""
    return _finish(TimestampValue(raw=text, role=role, method=method, instant=utc_iso(parsed),
                                  precision=precision.value, uncertain=unknown_zone, note=note), clock)


def parse_gdelt(raw: str, *, role: str = TimestampRole.index.value,
                clock: Optional[Clock] = None) -> Optional[TimestampValue]:
    """GDELT ``YYYYMMDDTHHMMSSZ``: an index/crawl observation of the article, not the
    publisher's own declared publication time."""
    m = _GDELT_RE.match((raw or "").strip())
    if not m:
        return None
    dt = datetime(int(m["y"]), int(m["m"]), int(m["d"]), int(m["H"]), int(m["M"]), int(m["S"]), tzinfo=UTC)
    return _finish(TimestampValue(raw=raw, role=role, method="gdelt_seendate", instant=utc_iso(dt),
                                  precision=Precision.second.value,
                                  note="GDELT's crawl/seen time; the publisher's own date may differ"), clock)


def parse_epoch(value: Any, *, unit: str, role: str = TimestampRole.upload.value,
                method: str = "epoch", clock: Optional[Clock] = None) -> Optional[TimestampValue]:
    """Unix epoch seconds/milliseconds/microseconds, the unit must be stated, never guessed
    from magnitude alone (Jetstream's v1/v2 cursor split shows what guessing does)."""
    scale = {"seconds": 1, "milliseconds": 1_000, "microseconds": 1_000_000}.get(unit)
    if scale is None:
        raise ValueError(f"unknown epoch unit {unit!r}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    dt = datetime.fromtimestamp(number / scale, tz=UTC)
    return _finish(TimestampValue(raw=str(value), role=role, method=method, instant=utc_iso(dt),
                                  precision=Precision.second.value), clock)


def parse_slash_date(raw: str, *, role: str, default_order: Optional[str] = None,
                     method: str = "slash_date", clock: Optional[Clock] = None) -> Optional[TimestampValue]:
    """``03/04/2026`` is ambiguous between US (Mar 4) and most-of-world (Apr 3).

    With ``default_order='mdy'|'dmy'`` the ambiguity is resolved as stated; otherwise the
    value is returned with ``uncertain=True`` and both readings recorded in the note.
    """
    m = _SLASH_RE.match((raw or "").strip())
    if not m:
        return None
    a, b, y = int(m["a"]), int(m["b"]), int(m["y"])
    if a > 12 and b > 12:
        return None
    ambiguous = a <= 12 and b <= 12
    if ambiguous and default_order is None:
        return TimestampValue(raw=raw, role=role, method=method, uncertain=True,
                              note=f"ambiguous date; could be {y:04d}-{a:02d}-{b:02d} (MDY) "
                                   f"or {y:04d}-{b:02d}-{a:02d} (DMY); not resolved")
    order = default_order or ("mdy" if b > 12 else "dmy" if a > 12 else "mdy")
    if order == "mdy":
        month, day, swapped = a, b, ambiguous
    else:
        month, day, swapped = b, a, ambiguous
    try:
        start = datetime(y, month, day, tzinfo=UTC)
    except ValueError:
        return None
    note = "interpreted as day/month/year because the first number cannot be a month" if not ambiguous and a > 12 else ""
    if swapped:
        note = "interpreted with the stated default order despite an ambiguous value"
    return _finish(TimestampValue(raw=raw, role=role, method=method, instant=utc_iso(start),
                                  end_instant=utc_iso(start + timedelta(days=1)),
                                  precision=Precision.day.value, uncertain=ambiguous, note=note), clock)


def parse_month_day(raw: str, *, reference: datetime, role: str = TimestampRole.publication.value,
                    default_tz: Optional[str] = None, clock: Optional[Clock] = None) -> Optional[TimestampValue]:
    """``Oct 8`` / ``October 8, 2026`` / ``Oct 8 17:30``: a missing year anchors to the
    reference's year, rolling back one year when that would land in the future."""
    m = _MONTH_DAY_RE.match((raw or "").strip())
    if not m:
        return None
    month = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(
        m["mon"][:3].lower()) + 1
    day = int(m["d"])
    zone = load_zone(default_tz) if default_tz else UTC
    year = int(m["y"]) if m["y"] else reference.astimezone(zone).year
    hour, minute = int(m["H"] or 0), int(m["M"] or 0)
    if m["ampm"]:
        hour = hour % 12 + (12 if m["ampm"].lower() == "pm" else 0)
    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=zone)
    except ValueError:
        return None
    if not m["y"] and dt > reference.astimezone(zone):
        dt = dt.replace(year=year - 1)
    note = "" if m["y"] else f"no year in the source; anchored to {dt.year} from the document reference"
    precision = Precision.day if not m["H"] else Precision.minute
    return _finish(TimestampValue(raw=raw, role=role, method="month_day", instant=utc_iso(dt),
                                  precision=precision.value, uncertain=not m["y"], note=note,
                                  timezone_name=default_tz), clock)


def _relative_amount(token: str) -> Optional[int]:
    token = token.lower()
    if token.isdigit():
        return int(token)
    return _WORDS.get(token)


def parse_relative(text: str, *, reference: datetime, role: str = TimestampRole.occurrence.value,
                   clock: Optional[Clock] = None) -> Optional[TimestampValue]:
    """Resolve one bounded English relative phrase (``ten minutes ago``, ``3 days ago``).

    The ONLY correct reference is the speaker's own document/request instant, never the
    reader's now. The result is marked uncertain because "ago" is approximate by nature.
    """
    m = _REL_RE.search(text or "")
    if not m:
        return None
    amount = _relative_amount(m["n"])
    if amount is None:
        return None
    delta = _REL_UNITS[m["u"].lower()] * amount
    dt = reference - delta
    return _finish(TimestampValue(raw=m.group(0), role=role, method="relative_phrase",
                                  instant=utc_iso(dt), precision=Precision.minute.value, uncertain=True,
                                  note=f"relative to {utc_iso(reference)} (the speaker's reference), not to now"), clock)


def find_relative_phrases(text: str, *, reference: datetime) -> list[TimestampValue]:
    """All bounded relative phrases in a passage, anchored to the passage's own reference."""
    found: list[TimestampValue] = []
    for m in _REL_RE.finditer(text or ""):
        amount = _relative_amount(m["n"])
        if amount is None:
            continue
        dt = reference - _REL_UNITS[m["u"].lower()] * amount
        found.append(TimestampValue(
            raw=m.group(0), role=TimestampRole.occurrence.value, method="relative_phrase",
            instant=utc_iso(dt), precision=Precision.minute.value, uncertain=True,
            note=f"anchored to the document reference {utc_iso(reference)}"))
    return found


@dataclass(frozen=True)
class EvidenceCutoff:
    """The time frame of one investigation request.

    ``as_of`` is the requested evidence boundary (None = now). Both historical modes stay
    available and distinct:
      * available_by(cutoff): "what evidence could Hutch have seen by T" (retrieval <= T)
      * about_events_before(cutoff): "what is known now about events before T"
    """

    reference_instant: datetime
    as_of: Optional[datetime] = None
    timezone_name: str = "UTC"
    horizon_hours: Optional[float] = None

    def __post_init__(self):
        if self.reference_instant.tzinfo is None or (self.as_of and self.as_of.tzinfo is None):
            raise ValueError("cutoffs require aware instants (UTC instants for ordering)")

    @property
    def effective(self) -> datetime:
        return self.as_of or self.reference_instant

    def describe(self) -> str:
        if self.as_of:
            return (f"as of {utc_iso(self.as_of)} (evidence available by that instant), "
                    f"requested at {utc_iso(self.reference_instant)}, zone {self.timezone_name}")
        return f"as of the request instant {utc_iso(self.reference_instant)}, zone {self.timezone_name}"

    def contains(self, ts: Optional[TimestampValue]) -> bool:
        """True when a value intersects [cutoff-horizon, cutoff]; unknown values are False."""
        instant = ts.parsed if ts else None
        if instant is None:
            return False
        if instant > self.effective:
            return False
        if self.horizon_hours is not None:
            return instant >= self.effective - timedelta(hours=self.horizon_hours)
        return True

    @classmethod
    def from_clock(cls, clock: Clock, *, as_of: Optional[str] = None, timezone_name: str = "UTC",
                   horizon_hours: Optional[float] = None) -> "EvidenceCutoff":
        reference = clock.now()
        boundary = None
        if as_of:
            parsed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=load_zone(timezone_name) if timezone_name else UTC)
            boundary = parsed.astimezone(UTC)
        return cls(reference_instant=reference, as_of=boundary, timezone_name=timezone_name,
                   horizon_hours=horizon_hours)

    def available_by(self, ts: Optional[TimestampValue]) -> bool:
        """Mode 1: was this evidence observed by the cutoff? (retrieval role required.)"""
        instant = ts.parsed if ts else None
        return bool(instant and self.as_of and instant <= self.as_of)

    def events_before(self, ts: Optional[TimestampValue]) -> bool:
        """Mode 2: did the underlying event occur before the cutoff? Unknown time is not True."""
        instant = ts.parsed if ts else None
        return bool(instant and instant < self.effective)


def parse_any(raw: str, *, role: str = TimestampRole.index.value, default_tz: Optional[str] = None,
              method: str = "auto", reference: Optional[datetime] = None,
              clock: Optional[Clock] = None) -> Optional[TimestampValue]:
    """Best-effort dispatch across the supported formats, keeping the winning parser's method name."""
    value = parse_iso(raw, role=role, default_tz=default_tz, clock=clock)
    if value is None:
        value = parse_gdelt(raw, role=role, clock=clock)
    if value is None:
        value = parse_rfc822(raw, role=role, clock=clock)
    if value is None:
        value = parse_slash_date(raw, role=role, clock=clock)
    if value is None and reference is not None:
        value = parse_month_day(raw, reference=reference, role=role, default_tz=default_tz, clock=clock)
    return value


def newest_first(values: Iterable[TimestampValue]) -> list[TimestampValue]:
    """Order values by parsed instant, newest first; unknown-time values sort last (never as 'now')."""
    known = sorted((v for v in values if v.instant), key=lambda v: v.instant, reverse=True)
    unknown = [v for v in values if not v.instant]
    return known + unknown
