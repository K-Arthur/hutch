"""Workflow-scope usage admission: call, token and currency allowances.

``Store.admit_and_reserve`` calls :func:`enforce` inside its single ``BEGIN IMMEDIATE`` transaction, so
concurrent workers, and separate store handles on one database, cannot multiply a workflow's allowance.
Every total comes from the ``usage_reservations`` rows of the whole workflow tree: held (reserved or
uncertain) and settled. Currency is estimated; provider billing stays authoritative.
"""
from __future__ import annotations

import sqlite3
from math import isfinite
from typing import Any, Optional

#: Float slack when summing quoted USD amounts. Small enough that a one-ten-billionth-dollar overrun of a
#: zero (free-only) ceiling is still refused.
CURRENCY_EPSILON = 1e-12


def usage_totals(db: sqlite3.Connection, workflow_id: str, *, held: bool) -> tuple[int, int]:
    """Return request and token commitments (or started usage) for the whole workflow tree."""
    if held:
        request_condition = "request_started_at IS NOT NULL OR status IN ('reserved','uncertain','settled')"
        token_condition = "status IN ('reserved','uncertain') OR request_started_at IS NOT NULL"
    else:
        request_condition = "request_started_at IS NOT NULL"
        token_condition = "request_started_at IS NOT NULL"
    row = db.execute(
        f"""SELECT COUNT(*) AS calls,
                   COALESCE(SUM(CASE
                     WHEN status = 'settled' AND actual_prompt_tokens IS NOT NULL
                          AND actual_completion_tokens IS NOT NULL
                       THEN actual_prompt_tokens + actual_completion_tokens
                     WHEN {token_condition} THEN reserved_tokens ELSE 0 END), 0) AS tokens
            FROM usage_reservations WHERE workflow_run_id = ? AND ({request_condition})""",
        (workflow_id,)).fetchone()
    return int(row["calls"] or 0), int(row["tokens"] or 0)


def cost_totals(db: sqlite3.Connection, workflow_id: str) -> tuple[float, float]:
    """Return ``(settled, held)`` USD for the whole workflow tree.

    Settled is the recorded actual cost, or the reserved worst case when no actual was recorded. Held is
    every reservation still in flight or uncertain; released reservations never reached a provider.
    """
    row = db.execute(
        """SELECT COALESCE(SUM(CASE WHEN status = 'settled'
                                    THEN COALESCE(actual_cost_usd, reserved_cost_usd) ELSE 0 END), 0) AS settled,
                  COALESCE(SUM(CASE WHEN status IN ('reserved','uncertain')
                                    THEN reserved_cost_usd ELSE 0 END), 0) AS held
           FROM usage_reservations WHERE workflow_run_id = ?""", (workflow_id,)).fetchone()
    return float(row["settled"] or 0.0), float(row["held"] or 0.0)


def ledger_cost_fields(db: sqlite3.Connection, workflow_id: str) -> dict[str, float]:
    """Currency fields for the workflow ledger (rounded so summed floats do not show noise)."""
    settled, held = cost_totals(db, workflow_id)
    return {"model_cost_usd": round(settled, 9), "model_held_usd": round(held, 9)}


def currency_ceiling(budget: dict[str, Any]) -> Optional[float]:
    """The plan's ``max_cost_usd``; ``None`` when the plan sets none. Raises ValueError when malformed."""
    raw = budget.get("max_cost_usd")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(float(raw)) or float(raw) < 0:
        raise ValueError("max_cost_usd must be a finite non-negative number")
    return float(raw)


def enforce(db: sqlite3.Connection, scope: dict[str, Any], *, reserved_tokens: int,
            quote_usd: Optional[float]) -> None:
    """Refuse a model request that could pass the workflow's call, token or currency allowance.

    ``scope`` is the validated workflow scope (its id and persisted budget). ``quote_usd`` is the call's
    verified worst-case USD price, or ``None`` when no price basis exists. A currency ceiling of zero means
    free-only: any positive quote is refused and an unknown price is refused.
    """
    from ..store import UsageBudgetRefusal, UsageQuoteUnavailable

    budget = scope["budget"]
    used_calls, used_tokens = usage_totals(db, scope["id"], held=True)
    call_limit = int(budget.get("max_model_calls", 12))
    token_limit = int(budget.get("max_tokens", 64_000))
    if used_calls + 1 > call_limit:
        raise UsageBudgetRefusal(
            f"the workflow's max_model_calls budget is exhausted ({call_limit} actual requests; "
            f"{used_calls} used or reserved)")
    if used_tokens + reserved_tokens > token_limit:
        raise UsageBudgetRefusal(
            f"the next model request could pass the workflow's max_tokens budget "
            f"({used_tokens:,} used or reserved + {reserved_tokens:,} estimated; limit {token_limit:,})")
    try:
        ceiling = currency_ceiling(budget)
    except ValueError:
        raise UsageBudgetRefusal("the workflow's max_cost_usd ceiling is malformed; provider call refused") from None
    if ceiling is None:
        return
    if quote_usd is None:
        raise UsageQuoteUnavailable(
            "the workflow has a max_cost_usd ceiling, but this call has no verified USD price basis; "
            "no paid request was sent")
    settled, held = cost_totals(db, scope["id"])
    if settled + held + float(quote_usd) > ceiling + CURRENCY_EPSILON:
        raise UsageBudgetRefusal(
            f"the next model request could pass the workflow's max_cost_usd ceiling (${ceiling:.4f}); "
            f"${settled + held:.4f} is spent or reserved")
