"""Fleet roll-call for scheduled work, computed from stored rows only.

The summary answers the operator's four questions: what is active, what is
blocked, what failed recently, and what is due next. Spend and cap state come
from the same budget rows the rest of the dashboard uses; a missing cap is
reported as ``no_cap`` rather than hidden behind a zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .models import iso, utcnow
from .schedule_history import list_occurrences

MAX_ROUTINES = 200
FAILURE_WINDOW = timedelta(hours=24)


def _pending_schedule_ids(store) -> set[str]:
    with store._lock:
        rows = store._db.execute(
            "SELECT DISTINCT s.schedule_id FROM schedule_approval_requests s "
            "JOIN approvals a ON a.id = s.approval_id "
            "WHERE s.reconciled_at = '' AND a.status = 'pending'",
        ).fetchall()
    return {str(row["schedule_id"]) for row in rows}


def _budget_summary(store, bots) -> dict[str, Any]:
    budgets = store.bot_budgets_today()
    measured_tokens = reserved_tokens = 0
    measured_cost = reserved_cost = 0.0
    token_cap = 0
    cost_cap = 0.0
    for bot in bots:
        m_tokens, h_tokens, m_cost, h_cost = budgets.get(bot.id, (0, 0, 0.0, 0.0))
        measured_tokens += m_tokens
        reserved_tokens += h_tokens
        measured_cost += m_cost
        reserved_cost += h_cost
        token_cap += int(bot.limits.daily_token_cap or 0)
        cost_cap += float(bot.limits.daily_cost_cap_usd or 0.0)
    used_cost = measured_cost + reserved_cost
    if cost_cap <= 0:
        state = "no_cap"
    elif used_cost > cost_cap:
        state = "over"
    elif used_cost >= cost_cap * 0.8:
        state = "near"
    else:
        state = "ok"
    return {
        "measured_cost_usd": round(measured_cost, 6),
        "reserved_cost_usd": round(reserved_cost, 6),
        "configured_cost_cap_usd": round(cost_cap, 6),
        "state": state,
        "tokens_today": measured_tokens + reserved_tokens,
        "configured_token_cap": token_cap,
    }


def _failed_within(last: dict[str, Any] | None, now: datetime) -> bool:
    if not last or last["run_status"] not in ("failed", "outcome_unknown"):
        return False
    try:
        occurrence = datetime.fromisoformat(last["occurrence"])
    except (TypeError, ValueError):
        return True
    if occurrence.tzinfo is None:
        occurrence = occurrence.replace(tzinfo=timezone.utc)
    return occurrence >= now - FAILURE_WINDOW


def _routine(store, scheduler, bot, schedule, *, workspace_paused: bool,
             pending_ids: set[str], now: datetime) -> dict[str, Any]:
    last = list_occurrences(store, schedule.id, limit=1)
    last_row = last[0] if last else None
    blocked = scheduler.blocked(schedule) or {}
    if blocked or bot.paused or workspace_paused:
        state = "blocked"
    elif not schedule.enabled:
        state = "draft"
    else:
        state = "active"
    try:
        next_fire = scheduler.next_fire(bot, schedule=schedule)
    except Exception:
        next_fire = None
    pending = schedule.id in pending_ids
    return {
        "bot_id": bot.id,
        "bot_name": bot.name,
        "bot_display_name": bot.display_name,
        "schedule_id": schedule.id,
        "name": schedule.name,
        "next_fire": iso(next_fire) if next_fire else None,
        "state": state,
        "blocked_reason": str(blocked.get("reason") or ""),
        "pending_approval": pending,
        "needs_attention": bool(blocked) or _failed_within(last_row, now) or pending,
        "last_run_status": last_row["run_status"] if last_row else "",
        "last_occurrence": last_row,
    }


def roll_call(store, scheduler) -> dict[str, Any]:
    now = utcnow()
    workspace_paused = bool(store.workspace_schedule_control()["paused"])
    pending_ids = _pending_schedule_ids(store)
    bots = store.list_bots()
    routines: list[dict[str, Any]] = []
    for bot in bots:
        for schedule in bot.schedules or ([bot.schedule] if bot.schedule else []):
            if len(routines) >= MAX_ROUTINES:
                break
            routines.append(_routine(store, scheduler, bot, schedule, workspace_paused=workspace_paused,
                                     pending_ids=pending_ids, now=now))
        if len(routines) >= MAX_ROUTINES:
            break
    routines.sort(key=lambda row: (row["next_fire"] or "9999", row["bot_name"], row["name"]))
    next_due = next((row for row in routines if row["state"] == "active" and row["next_fire"]), None)
    return {
        "generated_at": iso(now),
        "totals": {
            "routines": len(routines),
            "active": sum(1 for row in routines if row["state"] == "active"),
            "blocked": sum(1 for row in routines if row["state"] == "blocked"),
            "needs_attention": sum(1 for row in routines if row["needs_attention"]),
            "pending_approvals": len(pending_ids),
            "failed_last_24h": sum(1 for row in routines if _failed_within(row["last_occurrence"], now)),
            "next_due": ({"bot_name": next_due["bot_name"], "name": next_due["name"],
                          "schedule_id": next_due["schedule_id"], "at": next_due["next_fire"]}
                         if next_due else None),
            "spend": _budget_summary(store, bots),
        },
        "routines": routines,
    }
