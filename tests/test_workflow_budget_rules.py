"""The workflow currency ceiling (budget.max_cost_usd): plan validation, amendment rules, fail-closed use."""
from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from hutch.store import UsageBudgetRefusal
from hutch.workflow import budget_rules, usage_budget
from hutch.workflow import persistence as wstore
from hutch.workflow.plan import CEILINGS, Budget
from tests.test_workflow_usage_budget import _active_workflow


# ------------------------------------------------------------------ plan schema

@pytest.mark.parametrize("value", [0, 0.0, 0.05, 12, CEILINGS["max_cost_usd"]])
def test_plan_accepts_a_zero_or_positive_ceiling_up_to_the_operator_limit(value):
    assert Budget(max_cost_usd=value).max_cost_usd == float(value)


@pytest.mark.parametrize("value", [-0.01, CEILINGS["max_cost_usd"] + 1, float("nan"), float("inf"), "cheap"])
def test_plan_rejects_a_negative_excessive_or_non_finite_ceiling(value):
    with pytest.raises(ValidationError):
        Budget(max_cost_usd=value)


def test_an_unset_ceiling_is_absent_from_every_persisted_budget_form():
    budget = Budget()
    assert budget.max_cost_usd is None
    assert "max_cost_usd" not in budget.model_dump(mode="json", exclude_none=True)


def test_a_workflow_without_a_ceiling_stores_no_currency_key(store):
    _, _, workflow = _active_workflow(store, name="no-ceiling", max_calls=10, max_tokens=100)
    assert "max_cost_usd" not in wstore.workflow_run(store, workflow["id"])["budget"]
    assert "max_cost_usd" in wstore.workflow_run(
        store, _active_workflow(store, name="with-ceiling", max_calls=10, max_tokens=100, max_usd=.05)[2]["id"])["budget"]


# ------------------------------------------------------- adoption can only tighten

def test_adoption_never_widens_or_drops_an_existing_ceiling():
    assert budget_rules.bound_budget({"max_cost_usd": .05}, {"max_cost_usd": .50})["max_cost_usd"] == .05
    assert budget_rules.bound_budget({"max_cost_usd": .05}, {"max_cost_usd": .02})["max_cost_usd"] == .02
    assert budget_rules.bound_budget({"max_cost_usd": .05}, {"max_cost_usd": None})["max_cost_usd"] == .05
    assert budget_rules.bound_budget({"max_cost_usd": .05}, {})["max_cost_usd"] == .05
    assert budget_rules.bound_budget({"max_cost_usd": 0}, {"max_cost_usd": 3})["max_cost_usd"] == 0


def test_adoption_may_add_a_ceiling_and_leaves_budgets_without_one_unchanged():
    assert budget_rules.bound_budget({}, {"max_cost_usd": .05})["max_cost_usd"] == .05
    assert "max_cost_usd" not in budget_rules.bound_budget({}, {"max_cost_usd": None, "max_tokens": 5})
    assert budget_rules.bound_budget({"max_tokens": 10}, {"max_tokens": 50})["max_tokens"] == 10


# ------------------------------------------------------------- amendment preview

def test_amendment_preview_blocks_raising_or_removing_the_ceiling():
    entry, reason = budget_rules.amendment_entry("max_cost_usd", .05, .10, {})
    assert reason == "the amendment cannot increase the root max_cost_usd ceiling"
    assert entry["effective_if_adopted"] == .05
    entry, reason = budget_rules.amendment_entry("max_cost_usd", .05, None, {})
    assert reason == "the amendment cannot remove the root max_cost_usd ceiling"
    assert entry["effective_if_adopted"] == .05


def test_amendment_preview_allows_lowering_or_adding_a_ceiling():
    entry, reason = budget_rules.amendment_entry("max_cost_usd", .05, .02, {})
    assert reason is None and entry["effective_if_adopted"] == .02
    entry, reason = budget_rules.amendment_entry("max_cost_usd", None, .02, {})
    assert reason is None and entry == {"current": None, "proposed": .02, "effective_if_adopted": .02}


def test_amendment_preview_keeps_the_integer_allowance_rules_exactly():
    entry, reason = budget_rules.amendment_entry("max_tokens", 100, 150, {"model_tokens": 30})
    assert reason == "the amendment cannot increase the root max_tokens allowance"
    assert entry == {"current": 100, "proposed": 150, "effective_if_adopted": 100, "used": 30, "remaining_now": 70}
    entry, reason = budget_rules.amendment_entry("max_fanout", 8, 4, {})
    assert reason is None and entry == {"current": 8, "proposed": 4, "effective_if_adopted": 4}


def test_a_candidate_that_drops_the_ceiling_is_compared_as_a_removal():
    assert budget_rules.proposed_budget(Budget(), {"max_cost_usd": .05})["max_cost_usd"] is None
    assert "max_cost_usd" not in budget_rules.proposed_budget(Budget(), {})


# ------------------------------------------------------------ fail-closed admission

def _ledger_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE usage_reservations (
        workflow_run_id TEXT, status TEXT, request_started_at TEXT, reserved_tokens INTEGER,
        reserved_cost_usd REAL, actual_prompt_tokens INTEGER, actual_completion_tokens INTEGER,
        actual_cost_usd REAL)""")
    return db


@pytest.mark.parametrize("bad", [-1, "0.05", True, float("nan")])
def test_a_malformed_stored_ceiling_refuses_the_call_instead_of_being_ignored(bad):
    scope = {"id": "wf", "budget": {"max_model_calls": 5, "max_tokens": 1000, "max_cost_usd": bad}}
    with pytest.raises(UsageBudgetRefusal, match="malformed"):
        usage_budget.enforce(_ledger_db(), scope, reserved_tokens=1, quote_usd=0.01)


def test_no_ceiling_means_an_unpriced_call_is_not_refused_by_the_workflow():
    scope = {"id": "wf", "budget": {"max_model_calls": 5, "max_tokens": 1000}}
    usage_budget.enforce(_ledger_db(), scope, reserved_tokens=1, quote_usd=None)


def test_settled_without_an_actual_counts_its_reserved_worst_case():
    db = _ledger_db()
    db.execute("INSERT INTO usage_reservations VALUES ('wf', 'settled', 'now', 1, .03, 1, 1, NULL)")
    db.execute("INSERT INTO usage_reservations VALUES ('wf', 'released', NULL, 1, .50, NULL, NULL, NULL)")
    assert usage_budget.cost_totals(db, "wf") == (.03, 0.0)
