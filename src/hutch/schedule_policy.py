"""Schedule approval policy: read, compare-and-swap write, and the workflow limit.

Policy lives in a sidecar table so the frozen ``Schedule`` model does not grow.
Conditions are validated here and again in the admission path. A linked saved
workflow keeps its own step approvals; setting a schedule-level pre-approval on
one is refused rather than half-implemented.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import Bot, iso, utcnow
from .schedule_conditions import ConditionError, validate_conditions
from .store import RevisionConflict


class PolicyUnsupported(ValueError):
    """The selected schedule cannot carry this policy in the current phase."""


@dataclass(frozen=True)
class SchedulePolicy:
    bot_id: str
    schedule_id: str
    approval_required: bool = False
    conditions: list[dict[str, Any]] = field(default_factory=list)
    revision: int = 0
    updated_at: str = ""

    def as_dict(self, *, bot_name: str = "") -> dict[str, Any]:
        payload = {
            "bot_id": self.bot_id,
            "schedule_id": self.schedule_id,
            "approval_required": self.approval_required,
            "conditions": self.conditions,
            "revision": self.revision,
            "updated_at": self.updated_at,
        }
        if bot_name:
            payload["bot_name"] = bot_name
        return payload


def default_policy(bot_id: str, schedule_id: str) -> SchedulePolicy:
    return SchedulePolicy(bot_id=bot_id, schedule_id=schedule_id)


def _schedule_for(bot: Bot, schedule_id: str):
    for schedule in bot.schedules or ([bot.schedule] if bot.schedule else []):
        if schedule.id == schedule_id:
            return schedule
    return None


def _policy_from_row(row) -> SchedulePolicy:
    conditions = validate_conditions(json.loads(row["conditions_json"]))
    return SchedulePolicy(
        bot_id=str(row["bot_id"]),
        schedule_id=str(row["schedule_id"]),
        approval_required=bool(row["approval_required"]),
        conditions=conditions,
        revision=int(row["revision"]),
        updated_at=str(row["updated_at"]),
    )


def get_policy(store, bot_id: str, schedule_id: str) -> SchedulePolicy:
    """Return the saved policy, or an explicit default when none was set."""
    with store._lock:
        row = store._db.execute(
            "SELECT bot_id, schedule_id, approval_required, conditions_json, revision, updated_at "
            "FROM schedule_policies WHERE bot_id = ? AND schedule_id = ?",
            (bot_id, schedule_id),
        ).fetchone()
    return _policy_from_row(row) if row is not None else default_policy(bot_id, schedule_id)


def all_policies(store, *, limit: int = 500) -> list[dict[str, Any]]:
    """Every saved policy with its assistant name, bounded for the schedules page."""
    with store._lock:
        rows = store._db.execute(
            "SELECT p.bot_id, b.name AS bot_name, p.schedule_id, p.approval_required, "
            "p.conditions_json, p.revision, p.updated_at FROM schedule_policies p "
            "JOIN bots b ON b.id = p.bot_id ORDER BY b.name, p.schedule_id LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [_policy_from_row(row).as_dict(bot_name=str(row["bot_name"])) for row in rows]


def put_policy(store, bot_id: str, schedule_id: str, *, approval_required: bool,
               conditions: Any, expected_revision: Optional[int] = None) -> SchedulePolicy:
    """Validate, check the schedule still exists, then write with optional CAS."""
    normalized = validate_conditions(conditions)
    with store._tx() as db:
        bot_row = db.execute("SELECT doc FROM bots WHERE id = ?", (bot_id,)).fetchone()
        if bot_row is None:
            raise KeyError(bot_id)
        bot = Bot.from_store_json(bot_row["doc"])
        schedule = _schedule_for(bot, schedule_id)
        if schedule is None:
            raise KeyError(schedule_id)
        if approval_required and schedule.workflow_definition_id:
            raise PolicyUnsupported(
                "Linked saved workflows keep their own step approvals; a schedule-level "
                "pre-check is not available for this routine."
            )
        row = db.execute(
            "SELECT revision FROM schedule_policies WHERE bot_id = ? AND schedule_id = ?",
            (bot_id, schedule_id),
        ).fetchone()
        current = int(row["revision"]) if row is not None else 0
        if expected_revision is not None and int(expected_revision) != current:
            raise RevisionConflict(f"schedule policy revision changed (current {current})")
        revision = current + 1
        updated_at = iso(utcnow())
        db.execute(
            "INSERT INTO schedule_policies "
            "(bot_id, schedule_id, approval_required, conditions_json, revision, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(bot_id, schedule_id) DO UPDATE SET "
            "approval_required=excluded.approval_required, conditions_json=excluded.conditions_json, "
            "revision=excluded.revision, updated_at=excluded.updated_at",
            (bot_id, schedule_id, int(bool(approval_required)),
             json.dumps(normalized, ensure_ascii=False, separators=(",", ":")), revision, updated_at),
        )
    store.bus.notify("work", "bots")
    return SchedulePolicy(bot_id=bot_id, schedule_id=schedule_id, approval_required=bool(approval_required),
                          conditions=normalized, revision=revision, updated_at=updated_at)


__all__ = ["ConditionError", "PolicyUnsupported", "SchedulePolicy", "all_policies", "default_policy",
           "get_policy", "put_policy"]
