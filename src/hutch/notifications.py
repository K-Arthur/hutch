"""Content-free owner notifications for approvals and unattended runs.

The row is written by a SQL trigger in ``notification_schema.py`` in the same
transaction as the fact it describes, so it cannot be lost by a crash and cannot be
duplicated by a retried transition. This module turns a row into a bounded plain-text
message for the existing channel outbox; it stores no prompt, no action arguments and
no provider text, and it never sends anything itself.
"""
from __future__ import annotations

from typing import Any

KIND_LABELS = {
    "approval_needs_you": "Needs you",
    "approval_expired": "Approval expired",
    "approval_denied": "Approval denied",
    "run_failed": "Work failed",
    "run_outcome_unknown": "Outcome unknown",
    "run_succeeded": "Work finished",
}
DECISIONS = {
    "timeout": "the deadline passed",
    "run_ended": "the run ended",
    "stopped": "the run was stopped",
    "owner_expired": "its worker lease expired",
}
MAX_LENGTH = 900


def _one_line(value: Any, limit: int) -> str:
    text = "".join(" " if (ord(character) < 32 or ord(character) == 127) else character
                   for character in str(value or ""))
    return " ".join(text.split())[:limit]


def render_notification(row: dict[str, Any], bot_label: str) -> str:
    """A short message that names the fact, the assistant and where to act.

    There is no action text, no prompt and no fact value: only a machine reason code
    from a bounded column, the assistant's label and the local page to open.
    """
    kind = str(row.get("kind") or "")
    bot = _one_line(bot_label, 80) or "An assistant"
    detail = _one_line(row.get("detail"), 40)
    if kind == "approval_needs_you":
        text = f"Hutch needs you: {bot} is waiting for your decision on an approval."
    elif kind == "approval_expired":
        reason = DECISIONS.get(detail, "the deadline passed")
        text = f"Hutch: an approval for {bot} expired without a decision ({reason}). Nothing was performed."
    elif kind == "approval_denied":
        text = f"Hutch: you denied an approval for {bot}. Nothing was performed."
    elif kind == "run_failed":
        reason = f" ({detail})" if detail else ""
        text = f"Hutch: unattended work for {bot} failed{reason}."
    elif kind == "run_outcome_unknown":
        text = (f"Hutch: work for {bot} ended with an unknown outcome. Check it in Hutch "
                "before retrying; it will not be resent automatically.")
    elif kind == "run_succeeded":
        text = f"Hutch: unattended work for {bot} finished. The result is ready to review."
    else:
        text = f"Hutch has an update for {bot}."
    link = "Open Hutch on this computer to review it."
    return f"{text}\n{link}"[:MAX_LENGTH]


def recent(store, *, limit: int = 20, since: str = "") -> list[dict[str, Any]]:
    """Recent notifications with their outbox state; a read, never a write."""
    with store._lock:
        return [dict(row) for row in store._db.execute(
            "SELECT n.*, d.state AS delivery_state, d.attempts, d.error AS delivery_error "
            "FROM notifications n LEFT JOIN channel_deliveries d ON d.notification_id = n.id "
            "WHERE (? = '' OR n.created_at >= ?) ORDER BY n.created_at DESC, n.rowid DESC LIMIT ?",
            (since, since, max(1, min(limit, 100))))]


def public(row: dict[str, Any], bot_label: str = "") -> dict[str, Any]:
    """The read-only API shape; identifiers and delivery state, never message bodies."""
    return {
        "id": row.get("id"),
        "kind": row.get("kind"),
        "kind_label": KIND_LABELS.get(str(row.get("kind")), "Notification"),
        "bot_id": row.get("bot_id"),
        "bot_label": bot_label or row.get("bot_id"),
        "subject_kind": row.get("subject_kind"),
        "subject_id": row.get("subject_id"),
        "detail": row.get("detail") or "",
        "created_at": row.get("created_at"),
        "delivery": {
            "channel_id": row.get("channel_id") or "",
            "state": row.get("delivery_state") or "pending",
            "attempts": int(row.get("attempts") or 0),
            "error": row.get("delivery_error") or "",
        },
    }
