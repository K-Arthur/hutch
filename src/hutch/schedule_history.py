"""Per-schedule diffs over the append-only revision journal.

The journal stores a bot's extracted schedule JSON at each change. This module
answers the question the UI asks: what changed in this one routine, and which
values are safe to show? Prompts and workflow inputs are hash-only; every other
top-level scalar is bounded and returned with hashes so a reader can verify the
diff without trusting the display text.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

#: The API scans at most this many recent bot revisions. The journal is bounded
#: by schedule edits, not by run volume; the cap only protects a pathological
#: document editor.
MAX_SCANNED_REVISIONS = 2_000
MAX_DIFF_VALUE_CHARS = 200
REDACTED_FIELDS = frozenset({"prompt", "workflow_inputs"})
SCALAR_TYPES = (str, int, float, bool, type(None))


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def schedule_snapshot(snapshot: str | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    try:
        data = json.loads(snapshot)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def extract_schedule(snapshot: str | None, schedule_id: str) -> dict[str, Any] | None:
    """Return one schedule from a stored snapshot, including the legacy singular field."""
    data = schedule_snapshot(snapshot)
    if data is None:
        return None
    schedules = data.get("schedules")
    if not isinstance(schedules, list) or not schedules:
        legacy = data.get("schedule")
        schedules = [legacy] if isinstance(legacy, dict) else []
    for item in schedules:
        if isinstance(item, dict) and str(item.get("id") or "") == schedule_id:
            return item
    return None


def _bounded(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str) and len(value) > MAX_DIFF_VALUE_CHARS:
        return value[:MAX_DIFF_VALUE_CHARS], True
    return value, False


def _change(field: str, before: Any, after: Any) -> dict[str, Any]:
    redacted = (field in REDACTED_FIELDS
                or not isinstance(before, SCALAR_TYPES)
                or not isinstance(after, SCALAR_TYPES))
    item: dict[str, Any] = {
        "field": field,
        "before": None,
        "after": None,
        "before_hash": canonical_hash(before),
        "after_hash": canonical_hash(after),
        "redacted": redacted,
        "truncated": False,
    }
    if not redacted:
        item["before"], before_truncated = _bounded(before)
        item["after"], after_truncated = _bounded(after)
        item["truncated"] = before_truncated or after_truncated
    return item


def schedule_diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Top-level field changes in deterministic order; nested values stay hash-only."""
    before = before or {}
    after = after or {}
    fields = sorted(set(before) | set(after))
    return [_change(field, before.get(field), after.get(field))
            for field in fields if before.get(field) != after.get(field)]


def list_revisions(store, bot_id: str, schedule_id: str, *, limit: int = 50,
                   offset: int = 0) -> list[dict[str, Any]]:
    """Recent revisions that actually changed this schedule, newest first."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    with store._lock:
        rows = store._db.execute(
            "SELECT id, bot_id, bot_name, revision, change_type, schedules_json, "
            "prev_schedules_json, changed_at FROM schedule_revisions "
            "WHERE bot_id = ? ORDER BY revision DESC LIMIT ?",
            (bot_id, MAX_SCANNED_REVISIONS),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        before = extract_schedule(row["prev_schedules_json"], schedule_id)
        after = extract_schedule(row["schedules_json"], schedule_id)
        if before is None and after is None:
            continue
        if before is None or after is None:
            changes = []
        else:
            changes = schedule_diff(before, after)
            if not changes:
                continue
        change_type = "created" if before is None else "removed" if after is None else "updated"
        out.append({
            "id": row["id"],
            "bot_id": row["bot_id"],
            "bot_name": row["bot_name"],
            "schedule_id": schedule_id,
            "revision": row["revision"],
            "change_type": change_type,
            "changed_at": row["changed_at"],
            "changes": changes,
            "before_hash": canonical_hash(before) if before is not None else None,
            "after_hash": canonical_hash(after) if after is not None else None,
        })
    return out[offset:offset + limit]


def schedule_identity_exists(store, bot_id: str, schedule_id: str) -> bool:
    """A removed routine keeps its reserved identity, so its history stays reachable."""
    with store._lock:
        row = store._db.execute(
            "SELECT 1 FROM schedule_identities WHERE schedule_id = ? AND bot_id = ?",
            (schedule_id, bot_id),
        ).fetchone()
    return row is not None
