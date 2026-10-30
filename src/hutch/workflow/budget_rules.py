"""How a workflow's root budget may change across amendments.

An amendment or a re-adoption can only tighten the root allowances: it may lower a limit, and it may add a
currency ceiling, but it can never raise a limit or remove the currency ceiling. The integer allowances were
already guarded; ``max_cost_usd`` is a float that is absent unless the plan sets it, so it needs its own rule.
"""
from __future__ import annotations

from typing import Any, Optional

#: Integer allowances that a root budget bounds with ``min()`` on adoption.
INTEGER_ALLOWANCES = ("max_nodes", "max_model_calls", "max_tokens", "max_wall_seconds",
                      "max_fanout", "max_repairs", "max_steps_per_node", "max_step_seconds")

#: The ledger counter that measures each integer allowance, where one exists.
LEDGER_KEYS = {"max_nodes": "nodes", "max_model_calls": "model_calls",
               "max_tokens": "model_tokens", "max_repairs": "repairs"}

CURRENCY_KEY = "max_cost_usd"


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def bound_budget(prior: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """The effective root budget after adoption: never wider than the prior one."""
    bounded = dict(new)
    for key in INTEGER_ALLOWANCES:
        if isinstance(prior.get(key), int) and isinstance(bounded.get(key), int):
            bounded[key] = min(int(prior[key]), int(bounded[key]))
    cap = prior.get(CURRENCY_KEY)
    if _number(cap):
        proposed = bounded.get(CURRENCY_KEY)
        bounded[CURRENCY_KEY] = float(cap) if not _number(proposed) else min(float(cap), float(proposed))
    elif bounded.get(CURRENCY_KEY) is None:
        bounded.pop(CURRENCY_KEY, None)
    return bounded


def proposed_budget(plan_budget: Any, old_budget: dict[str, Any]) -> dict[str, Any]:
    """The candidate plan's allowances, with an explicit ``None`` for a ceiling it drops.

    Unset optional fields are left out so a workflow without a currency ceiling compares exactly as before.
    """
    proposed = plan_budget.model_dump(mode="json", exclude_none=True)
    if old_budget.get(CURRENCY_KEY) is not None:
        proposed.setdefault(CURRENCY_KEY, None)
    return proposed


def _currency_entry(current: Any, proposed: Any) -> tuple[dict[str, Any], Optional[str]]:
    if not _number(current):                       # adding a ceiling only tightens the root allowance
        return {"current": None, "proposed": proposed, "effective_if_adopted": proposed}, None
    cap = float(current)
    if not _number(proposed):
        return ({"current": cap, "proposed": None, "effective_if_adopted": cap},
                f"the amendment cannot remove the root {CURRENCY_KEY} ceiling")
    wider = float(proposed) > cap
    return ({"current": cap, "proposed": float(proposed), "effective_if_adopted": min(cap, float(proposed))},
            f"the amendment cannot increase the root {CURRENCY_KEY} ceiling" if wider else None)


def amendment_entry(key: str, current: Any, proposed: Any,
                    ledger: dict[str, Any]) -> tuple[dict[str, Any], Optional[str]]:
    """One budget row of an amendment preview, plus the reason the amendment is blocked, if any."""
    if isinstance(current, int) and isinstance(proposed, int):
        ledger_key = LEDGER_KEYS.get(key)
        used = int(ledger.get(ledger_key, 0) or 0) if ledger_key else None
        entry = {"current": current, "proposed": proposed,
                 "effective_if_adopted": min(current, proposed),
                 **({"used": used, "remaining_now": max(0, min(current, proposed) - used)}
                    if used is not None else {})}
        return entry, (f"the amendment cannot increase the root {key} allowance" if proposed > current else None)
    if key == CURRENCY_KEY:
        return _currency_entry(current, proposed)
    return {"current": current, "proposed": proposed, "effective_if_adopted": proposed}, None
