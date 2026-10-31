"""Deterministic Today briefing: projections of persisted state, never a model summary.

Every line this module returns is derived from a row that exists. It makes no model
call, fetches no external service and never writes. Each item carries its source and
a link to the page that owns it, and the response names what was not considered, so
the UI cannot present a partial picture as complete.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models import RunStatus, iso, utcnow
from ..scheduler import InvalidScheduleZone, Scheduler
from .models import CommitmentStatus, CompletionKind
from .store import PersonalStore, public

MAX_ITEMS = 200


class InvalidTimezone(ValueError):
    """The requested IANA timezone cannot be used; never fall back to UTC silently."""


def resolve_zone(name: Optional[str], now: datetime) -> tuple[ZoneInfo, str]:
    requested = (name or "").strip()
    if not requested:
        raise InvalidTimezone("a timezone is required (an IANA name such as America/Vancouver)")
    try:
        return ZoneInfo(requested), requested
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezone(f"unknown IANA timezone: {requested[:64]}") from exc


def day_bounds(now: datetime, zone: ZoneInfo) -> tuple[datetime, datetime, datetime]:
    """(local midnight, next local midnight, one-week horizon) as UTC-aware instants.

    Each boundary is built from its own local date and converted separately, so a
    23- or 25-hour DST day is measured correctly instead of being assumed to be 24h.
    """
    local_date = now.astimezone(zone).date()
    start = datetime.combine(local_date, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    horizon = datetime.combine(local_date + timedelta(days=7), time.min, tzinfo=zone).astimezone(timezone.utc)
    return start, end, horizon


def _bot_labels(store) -> dict[str, str]:
    labels: dict[str, str] = {}
    for bot in store.list_bots():
        labels[bot.id] = bot.display_name or bot.name
    return labels


def _commitment_item(item, *, bot_labels: dict[str, str], href: str = "#/today") -> dict[str, Any]:
    data = public(item)
    data.update({
        "kind": "commitment",
        "source_label": "Shared space" if item.space_id else "Personal",
        "href": href,
        "detail": item.detail,
        "space_id": item.space_id,
        "blocked": data.get("blocked", False),
    })
    return data


def _run_item(run, *, bot_labels: dict[str, str]) -> dict[str, Any]:
    return {
        "kind": "run",
        "id": run.id,
        "bot_id": run.bot_id,
        "bot_label": bot_labels.get(run.bot_id, run.bot_id),
        "status": run.status.value,
        "status_label": run.status_label,
        "needs_person": run.needs_person,
        "prompt": (run.prompt or "").strip()[:160],
        "exit_reason": run.exit_reason,
        "missed_windows": run.missed_windows,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "href": f"#/run/{run.id}",
    }


def _approval_item(approval, *, bot_labels: dict[str, str]) -> dict[str, Any]:
    return {
        "kind": "approval",
        "id": approval.id,
        "bot_id": approval.bot_id,
        "bot_label": bot_labels.get(approval.bot_id, approval.bot_id),
        "tool": approval.tool,
        "action": (approval.action or "").strip()[:200],
        "risk": approval.risk,
        "expires_at": approval.expires_at,
        "href": "#/approvals",
    }


def _document_item(row: dict[str, Any], *, bot_labels: dict[str, str]) -> dict[str, Any]:
    run_id = str(row.get("run_id") or "")
    return {
        "kind": "document",
        "id": row.get("id"),
        "filename": row.get("cur_filename") or row.get("filename") or "Untitled document",
        "mime": row.get("cur_mime") or "",
        "bytes": int(row.get("cur_bytes") or 0),
        "validation": row.get("cur_validation") or "unverified",
        "version": row.get("cur_version"),
        "bot_label": bot_labels.get(row.get("bot_id"), row.get("bot_id") or "Assistant"),
        "created_at": row.get("created_at"),
        "href": f"#/run/{run_id}" if run_id else "",
    }


def _schedules(store, *, now: datetime, start: datetime, end: datetime) -> dict[str, Any]:
    scheduler = Scheduler(store)
    labels = _bot_labels(store)
    control = store.workspace_schedule_control()
    upcoming: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for bot in store.list_bots():
        schedules = list(bot.schedules or [])
        if bot.schedule is not None:
            schedules.append(bot.schedule)
        seen: set[str] = set()
        for scheduled in schedules:
            if scheduled.id in seen:
                continue  # the legacy primary schedule may also appear in the list
            seen.add(scheduled.id)
            if not scheduled.enabled:
                continue
            blocked_state = scheduler.blocked(scheduled)
            if blocked_state:
                blocked.append({"schedule_id": scheduled.id, "bot_id": bot.id,
                                "bot_label": labels.get(bot.id, bot.name), "name": scheduled.name,
                                "reason": str(blocked_state.get("reason") or "")[:200],
                                "at": blocked_state.get("at"), "href": "#/schedules"})
            next_at = scheduler.next_fire(bot, now, scheduled)
            if next_at is not None and start <= next_at <= end:
                upcoming.append({
                    "kind": "schedule", "schedule_id": scheduled.id, "bot_id": bot.id,
                    "bot_label": labels.get(bot.id, bot.name), "name": scheduled.name,
                    "next_at": iso(next_at), "timezone": scheduled.timezone,
                    "href": "#/schedules",
                })
    upcoming.sort(key=lambda item: item["next_at"])
    return {"paused": bool(control["paused"]), "upcoming_today": upcoming, "blocked": blocked}


def build_today(store, *, now: Optional[datetime] = None, timezone_name: Optional[str] = None) -> dict[str, Any]:
    """Compose the Today briefing from real persisted rows (read-only)."""
    now = (now or utcnow()).astimezone(timezone.utc)
    zone, zone_name = resolve_zone(timezone_name, now)
    start, end, horizon = day_bounds(now, zone)
    start_iso, end_iso, horizon_iso = iso(start), iso(end), iso(horizon)
    now_iso = iso(now)
    personal = PersonalStore(store)
    labels = _bot_labels(store)

    rows = personal.commitments.list(include_proposed=True, limit=MAX_ITEMS)
    blocked_map = personal.commitments.blocked_map([row.id for row in rows])
    items = [_commitment_item(row, bot_labels=labels) for row in rows]
    items = [{**item, "blocked": blocked_map.get(item["id"], False)} for item in items]

    open_items = [item for item in items
                  if item["status"] == CommitmentStatus.open.value and item["confirmation"] == "confirmed"]
    overdue = [item for item in open_items if item["due_at"] and item["due_at"] < now_iso]
    due_today = [item for item in open_items
                 if item["due_at"] and start_iso <= item["due_at"] < end_iso]
    upcoming = [item for item in open_items
                if item["due_at"] and end_iso <= item["due_at"] < horizon_iso]
    undated = [item for item in open_items if not item["due_at"]]
    proposed = [item for item in items
                if item["confirmation"] == "proposed" and item["status"] == CommitmentStatus.open.value]
    reported_done = [item for item in items
                     if item["status"] == CommitmentStatus.done.value
                     and item["completion_kind"] == CompletionKind.unverified.value]
    completed_today = [item for item in items
                       if item["status"] == CommitmentStatus.done.value and item["completed_at"]
                       and start_iso <= item["completed_at"] < end_iso]

    active_runs = store.active_runs()
    recent_runs = store.list_runs(limit=100)
    # A run waiting for approval is not "working": its decision is in the approvals section.
    working = [_run_item(run, bot_labels=labels) for run in active_runs
               if run.status not in (RunStatus.waiting_approval, RunStatus.waiting_human)]
    needs_attention = [_run_item(run, bot_labels=labels) for run in recent_runs
                       if (run.terminal and (run.status is RunStatus.failed
                                             or run.status is RunStatus.outcome_unknown))
                       or run.status is RunStatus.waiting_human]
    needs_attention = needs_attention[:12]
    finished_today = [_run_item(run, bot_labels=labels) for run in recent_runs
                      if run.terminal and run.status is RunStatus.succeeded and run.finished_at
                      and start_iso <= run.finished_at < end_iso][:12]

    approvals = [_approval_item(approval, bot_labels=labels)
                 for approval in store.pending_approvals(limit=20)]

    documents = []
    try:
        for row in store.list_documents(limit=20):
            created = str(row.get("created_at") or "")
            if start_iso <= created < end_iso:
                documents.append(_document_item(row, bot_labels=labels))
    except Exception:
        # A documents projection failure must not hide commitments, approvals or runs.
        documents = []

    spaces = personal.spaces.summary()
    schedules = _schedules(store, now=now, start=start, end=end)

    return {
        "generated_at": now_iso,
        "timezone": zone_name,
        "local_date": now.astimezone(zone).date().isoformat(),
        "day_start": start_iso,
        "day_end": end_iso,
        "counts": {
            "overdue": len(overdue),
            "due_today": len(due_today),
            "upcoming": len(upcoming),
            "proposed": len(proposed),
            "reported_done": len(reported_done),
            "completed_today": len(completed_today),
            "approvals": len(approvals),
            "working": len(working),
            "needs_attention": len(needs_attention),
            "upcoming_schedules": len(schedules["upcoming_today"]),
            "spaces": len(spaces),
        },
        "sections": {
            "commitments": {"overdue": overdue, "due_today": due_today, "upcoming": upcoming,
                            "undated": undated, "proposed": proposed,
                            "reported_done": reported_done, "completed_today": completed_today},
            "schedules": schedules,
            "approvals": {"count": len(approvals), "items": approvals},
            "runs": {"working": working, "needs_attention": needs_attention,
                     "completed_today": finished_today},
            "deliverables": documents,
            "spaces": spaces,
        },
        "not_included": [
            "Calendar events and email are not read automatically for this view. Assistants add them "
            "through their connected tools, schedules and commitments.",
            "Only the most recent 200 commitments, 100 runs and 20 documents are considered.",
            "A reported completion is not verified work; it is listed separately until you confirm it.",
        ],
    }
