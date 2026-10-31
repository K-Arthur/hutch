"""Read-only agenda projection for Today: calendar events and a bounded mail digest.

Every value here comes from a provider read made through one explicit assistant grant
the owner selected. The projection never writes to SQLite, never calls a model, and
never persists provider text beyond the bounded in-memory snapshot used to mark a
source stale instead of silently emptying it.

Provider text is untrusted data. It is bounded, control characters are removed, and it
is returned as data only. Nothing in this module interprets it, and no field of the
response is ever treated as an instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..models import iso, utcnow
from .today import day_bounds, resolve_zone

FRESH_SECONDS = 300            # a snapshot younger than this is still "fresh"
MAX_STALE_SECONDS = 3600       # older than this, a cached snapshot is not shown at all
MAX_EVENTS = 25
MAX_MESSAGES = 10
MAX_CACHE_ENTRIES = 8
PROVIDER_TEXT = 500            # hard bound before the per-field bounds below

REASONS = {
    "not_configured": "No connection is selected for this source.",
    "grant_missing": "No assistant currently holds a read grant for this connection.",
    "grant_expired": "The saved permission is no longer valid. Reconnect the account and grant it again.",
    "mail_requires_local": "Mailbox previews are only read for assistants that use Local inference.",
    "provider_error": "The provider could not be read. Nothing was invented to fill the gap.",
}

#: reasons that end access; no cached reading may survive them
HARD_UNAVAILABLE = frozenset({"grant_missing", "grant_expired", "mail_requires_local"})


class AgendaUnavailable(RuntimeError):
    """A selected source cannot be read; the reason is shown, never an empty list."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason if reason in REASONS else "provider_error"
        self.detail = clean(detail, 200)
        super().__init__(self.detail or REASONS[self.reason])


def clean(value: Any, limit: int) -> str:
    """Bound provider text to plain single-line characters; keep it as data."""
    text = str(value or "")[:PROVIDER_TEXT * 4]
    text = "".join(" " if (ord(character) < 32 or ord(character) == 127) else character
                   for character in text)
    return " ".join(text.split())[:limit]


@dataclass(frozen=True)
class AgendaSource:
    """One selected read-only source, with the bounded reader the owner's grant proves.

    ``unavailable`` carries a reason code when the grant itself cannot be used; in that
    case ``fetch`` is never called and no provider request is made.
    """

    kind: str                      # "calendar" | "mail"
    source: str                    # "google_calendar" | "gmail"
    source_label: str
    bot_id: str = ""
    bot_label: str = ""
    account_id: str = ""
    calendar_id: str = ""
    calendar_name: str = ""
    fetch: Optional[Callable[[datetime, datetime], list[dict[str, Any]]]] = None
    unavailable: str = ""
    unavailable_detail: str = ""

    @property
    def key(self) -> str:
        return "|".join((self.kind, self.bot_id, self.account_id, self.calendar_id))

    @classmethod
    def missing(cls, *, kind: str, source: str, source_label: str, reason: str,
                detail: str = "", bot_id: str = "", bot_label: str = "",
                account_id: str = "") -> "AgendaSource":
        return cls(kind=kind, source=source, source_label=source_label, bot_id=bot_id,
                   bot_label=bot_label, account_id=account_id, unavailable=reason,
                   unavailable_detail=detail)


def _event_item(row: dict[str, Any], *, selected: AgendaSource, fetched_at: str,
                stale: bool) -> dict[str, Any]:
    return {
        "kind": "event",
        "title": clean(row.get("summary"), 200) or "(untitled event)",
        "starts_at": clean(row.get("start"), 64),
        "ends_at": clean(row.get("end"), 64),
        "location": clean(row.get("location"), 200),
        "source": selected.source,
        "source_label": selected.source_label,
        "bot_id": selected.bot_id,
        "bot_label": selected.bot_label,
        "fetched_at": fetched_at,
        "stale": stale,
        "untrusted": True,
    }


def _message_item(row: dict[str, Any], *, selected: AgendaSource, fetched_at: str,
                  stale: bool) -> dict[str, Any]:
    return {
        "kind": "message",
        "title": clean(row.get("subject"), 200) or "(no subject)",
        "from": clean(row.get("from"), 200) or "(unknown sender)",
        "received_at": clean(row.get("received_at"), 64),
        "preview": clean(row.get("preview"), 300),
        "source": selected.source,
        "source_label": selected.source_label,
        "bot_id": selected.bot_id,
        "bot_label": selected.bot_label,
        "fetched_at": fetched_at,
        "stale": stale,
        "untrusted": True,
    }


def _empty(kind: str, status: str, reason_kind: str, reason: str,
           selected: Optional[AgendaSource] = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": status,
        "source": selected.source if selected else "",
        "source_label": selected.source_label if selected else "",
        "bot_id": selected.bot_id if selected else "",
        "bot_label": selected.bot_label if selected else "",
        "fetched_at": "",
        "age_seconds": None,
        "stale": False,
        "reason_kind": reason_kind,
        "reason": clean(reason, 240),
        "items": [],
    }


def _remember(cache: dict[str, dict[str, Any]], selected: AgendaSource, now: datetime,
              items: list[dict[str, Any]]) -> None:
    """Keep a small bounded snapshot per selection; expired entries go first."""
    cache.pop(selected.key, None)
    cache[selected.key] = {"fetched_at": now, "items": [dict(item) for item in items]}
    _prune(cache, now)
    while len(cache) > MAX_CACHE_ENTRIES:
        cache.pop(next(iter(cache)), None)


def _prune(cache: dict[str, dict[str, Any]], now: datetime) -> None:
    """A snapshot that can no longer be shown is not kept: the cache is not an archive."""
    for key, cached in list(cache.items()):
        if (now - cached["fetched_at"]).total_seconds() > MAX_STALE_SECONDS:
            cache.pop(key, None)


def _evict(cache: dict[str, dict[str, Any]], selected: AgendaSource) -> None:
    """Remove every snapshot for this assistant and kind.

    The cache key includes the calendar id, and a source whose grant was removed no longer
    carries one, so deleting by exact key would miss precisely the entry the owner just
    revoked. Matching the assistant and kind instead keeps that guarantee true.
    """
    prefix = f"{selected.kind}|{selected.bot_id}|"
    for key in [key for key in cache if key.startswith(prefix)]:
        cache.pop(key, None)


def _fallback(selected: AgendaSource, *, kind: str, now: datetime, cache: dict[str, dict[str, Any]],
              reason: str, detail: str) -> dict[str, Any]:
    """A failed refresh shows a recent snapshot as stale, or says the source is unavailable.

    Only a provider failure may reuse a snapshot. A grant that is gone, expired or no
    longer permitted is a hard stop: the last reading is discarded, because the owner's
    decision to stop sharing must take effect immediately, not in an hour.
    """
    if reason in HARD_UNAVAILABLE:
        _evict(cache, selected)
        return _empty(kind, "unavailable", reason, detail or REASONS.get(reason, ""), selected)
    _prune(cache, now)
    cached = cache.get(selected.key)
    if cached is not None:
        age = int((now - cached["fetched_at"]).total_seconds())
        if 0 <= age <= MAX_STALE_SECONDS:
            fetched_at = iso(cached["fetched_at"])
            items = [{**item, "stale": True} for item in cached["items"]]
            return {
                "kind": kind,
                "status": "stale",
                "source": selected.source,
                "source_label": selected.source_label,
                "bot_id": selected.bot_id,
                "bot_label": selected.bot_label,
                "fetched_at": fetched_at,
                "age_seconds": age,
                "stale": True,
                "reason_kind": reason if reason in REASONS else "provider_error",
                "reason": clean(detail or REASONS.get(reason, ""), 240),
                "items": items,
            }
    return _empty(kind, "unavailable", reason, detail or REASONS.get(reason, ""), selected)


def _source_result(selected: Optional[AgendaSource], *, kind: str, now: datetime,
                   start: datetime, end: datetime, cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if selected is None:
        return _empty(kind, "not_configured", "not_configured", REASONS["not_configured"])
    if selected.unavailable:
        # A grant that cannot be used discards any snapshot: revoking access is immediate.
        _evict(cache, selected)
        return _empty(kind, "unavailable", selected.unavailable,
                      selected.unavailable_detail or REASONS.get(selected.unavailable, ""), selected)
    if selected.fetch is None:
        return _empty(kind, "not_configured", "not_configured", REASONS["not_configured"], selected)
    limit = MAX_EVENTS if kind == "calendar" else MAX_MESSAGES
    try:
        rows = selected.fetch(start, end)
    except AgendaUnavailable as exc:
        return _fallback(selected, kind=kind, now=now, cache=cache, reason=exc.reason, detail=exc.detail)
    except Exception:
        # Never serialize a raw provider or network exception into the response.
        return _fallback(selected, kind=kind, now=now, cache=cache, reason="provider_error",
                         detail=REASONS["provider_error"])
    if not isinstance(rows, list):
        return _fallback(selected, kind=kind, now=now, cache=cache, reason="provider_error",
                         detail="The provider returned an unexpected shape; nothing is shown from it.")
    fetched_at = iso(now)
    normalize = _event_item if kind == "calendar" else _message_item
    items = [normalize(row, selected=selected, fetched_at=fetched_at, stale=False)
             for row in rows[:limit] if isinstance(row, dict)]
    if kind == "calendar":
        items.sort(key=lambda item: item["starts_at"])
    else:
        items.sort(key=lambda item: item["received_at"], reverse=True)
    _remember(cache, selected, now, items)
    return {
        "kind": kind,
        "status": "ok",
        "source": selected.source,
        "source_label": selected.source_label,
        "bot_id": selected.bot_id,
        "bot_label": selected.bot_label,
        "fetched_at": fetched_at,
        "age_seconds": 0,
        "stale": False,
        "reason_kind": "",
        "reason": "",
        "items": items,
    }


def build_agenda(*, now: Optional[datetime] = None, timezone_name: Optional[str] = None,
                 calendar: Optional[AgendaSource] = None, mail: Optional[AgendaSource] = None,
                 cache: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    """Compose the owner's agenda from selected, grant-backed readers (read-only)."""
    now = (now or utcnow()).astimezone(timezone.utc)
    zone, zone_name = resolve_zone(timezone_name, now)
    start, end, _ = day_bounds(now, zone)
    cache = cache if cache is not None else {}
    sources = {
        "calendar": _source_result(calendar, kind="calendar", now=now, start=start, end=end, cache=cache),
        "mail": _source_result(mail, kind="mail", now=now, start=start, end=end, cache=cache),
    }
    items = sources["calendar"]["items"] + sources["mail"]["items"]
    stale = any(source["status"] == "stale" for source in sources.values())
    return {
        "generated_at": iso(now),
        "timezone": zone_name,
        "local_date": now.astimezone(zone).date().isoformat(),
        "day_start": iso(start),
        "day_end": iso(end),
        "stale": stale,
        "counts": {
            "events": len(sources["calendar"]["items"]),
            "messages": len(sources["mail"]["items"]),
            "unavailable": sum(1 for source in sources.values() if source["status"] == "unavailable"),
        },
        "sources": sources,
        "items": items,
        "not_included": [
            "Agenda text comes from your calendar and mailbox and is shown as data. Hutch never "
            "treats it as an instruction, and no model reads it for this view.",
            "Provider text is not written to Hutch's database. A recent snapshot is kept in memory "
            "only so a failed refresh can be shown as stale instead of as an empty day.",
            "Only the connection you select is read. Events are limited to today and mail to the "
            "last 24 hours; other calendars and mailboxes are not touched.",
        ],
    }
