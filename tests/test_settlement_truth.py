"""Settlement truth: provider-reported charges are recorded, labeled, and preserved (SR-2)."""

from __future__ import annotations

import pytest

from hutch.models import ApprovalMode

from tests.test_runtime_budget_gate import _running, build, factory, run_it, runtime


def _usage_row(store, run_id: int | str) -> dict:
    row = store._db.execute("SELECT cost_usd, cost_source, reported_cost_usd, kind, provider, model "
                            "FROM usage WHERE run_id = ?", (run_id,)).fetchone()
    assert row is not None, "the call was not settled into the usage ledger"
    return dict(row)


def test_openrouter_usage_cost_becomes_the_recorded_charge(store, config, tmp_path):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    oai.script = lambda b: {"content": "paid answer", "prompt_tokens": 1000, "completion_tokens": 100,
                            "cost": "0.000421"}
    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", mode=ApprovalMode.auto)
        run = _running(store, ctx, run)
        assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "paid answer"
    finally:
        oai.close()
    row = _usage_row(store, run.id)
    assert row["cost_usd"] == pytest.approx(0.000421)
    assert row["cost_source"] == "provider"
    assert row["reported_cost_usd"] == pytest.approx(0.000421)
    assert run.cost_usd == pytest.approx(0.000421)


def test_estimated_charge_is_labeled_when_the_provider_reports_no_cost(store, config, tmp_path):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    oai.script = lambda b: {"content": "answer", "prompt_tokens": 1000, "completion_tokens": 100}
    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", mode=ApprovalMode.auto)
        run = _running(store, ctx, run)
        assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "answer"
    finally:
        oai.close()
    row = _usage_row(store, run.id)
    assert row["cost_source"] == "estimated"
    assert row["reported_cost_usd"] is None
    assert row["cost_usd"] == pytest.approx((1000 * 2.5 + 100 * 10) / 1e6)


def test_no_price_and_no_provider_cost_is_recorded_unknown_not_invented(store, config, tmp_path):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    oai.script = lambda b: {"content": "answer", "prompt_tokens": 10, "completion_tokens": 5}
    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-unpriced",
                                         mode=ApprovalMode.auto)
        run = _running(store, ctx, run)
        assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "answer"
    finally:
        oai.close()
    row = _usage_row(store, run.id)
    assert row["cost_usd"] == 0.0 and row["cost_source"] == "unknown"
    assert run.cost_usd == 0.0


def test_provider_cost_is_quantized_half_up_to_micro_usd(store, config, tmp_path):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    oai.script = lambda b: {"content": "answer", "prompt_tokens": 10, "completion_tokens": 5,
                            "cost": "0.00000055"}
    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", mode=ApprovalMode.auto)
        run = _running(store, ctx, run)
        assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "answer"
    finally:
        oai.close()
    row = _usage_row(store, run.id)
    assert row["cost_usd"] == pytest.approx(0.000001)          # half-up at the ledger unit
    assert row["reported_cost_usd"] == pytest.approx(0.00000055)  # the raw reported value is preserved
