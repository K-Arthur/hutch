"""Runtime wiring for budget bands: warn, pause-for-approval, ceiling, unknown price (SR-2)."""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from hutch.models import ApprovalMode, Limits, RunStatus
from hutch.runtime import RunAborted
from hutch.runtime.builtin import reset_connection_cache
from hutch.runtime.ladder import reset_provider_cache

from tests.test_runtime_builtin import build, factory, kinds, run_it, runtime


@pytest.fixture(autouse=True)
def _fresh_providers():
    reset_provider_cache()
    reset_connection_cache()


@pytest.fixture()
def oai():
    from tests.fakes import FakeOpenAI
    server = FakeOpenAI()
    yield server
    server.close()


def _running(store, ctx, run):
    """Unit tests call the runtime directly; approvals need the claimed, running run the engine creates."""
    claimed = store.claim_run(run.id, "budget-gate-test", 120)
    assert claimed is not None
    run = store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    ctx.run = ctx.gate.run = run
    return run


def _serve(oai, text="ok from the paid model"):
    oai.script = lambda b: {"content": text, "prompt_tokens": 1000, "completion_tokens": 100}


def _answer_pause(store, *, approve: bool, seen: list, checks=None) -> threading.Thread:
    def worker():
        from hutch.approvals import resolve_approval
        for _ in range(600):
            try:
                pending = store.pending_approvals()
            except sqlite3.ProgrammingError:
                return  # the database closed while a failing test was tearing down
            if pending:
                if checks:
                    checks(pending[0])
                seen.append(pending[0].tool)
                resolve_approval(store, pending[0].id, approve=approve, by="test")
                return
            time.sleep(0.02)

    thread = threading.Thread(target=worker)
    thread.start()
    return thread


def test_pause_threshold_asks_and_continues_after_approval(store, config, tmp_path, oai):
    _serve(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", mode=ApprovalMode.auto)
    run = _running(store, ctx, run)
    store.set_budget_policy(scope_kind="bot", scope_id=ctx.bot.id, pause_usd=0.001)

    seen: list[str] = []

    def checks(approval):
        assert "pause threshold" in approval.action
        assert approval.detail["pause_usd"] == 0.001
        assert approval.detail["scope_kind"] == "bot"

    worker = _answer_pause(store, approve=True, seen=seen, checks=checks)
    try:
        assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "ok from the paid model"
    finally:
        worker.join(timeout=5)
    assert seen == ["budget_pause"]
    assert oai.of("/v1/chat/completions"), "the approved call reached the provider"


def test_denied_pause_aborts_before_the_provider_call(store, config, tmp_path, oai):
    _serve(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", mode=ApprovalMode.auto)
    run = _running(store, ctx, run)
    store.set_budget_policy(scope_kind="bot", scope_id=ctx.bot.id, pause_usd=0.001)

    worker = _answer_pause(store, approve=False, seen=[])
    try:
        with pytest.raises(RunAborted) as failure:
            run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools)
    finally:
        worker.join(timeout=5)
    assert failure.value.reason == "cost_cap"
    assert not oai.of("/v1/chat/completions"), "a denied pause must never reach the provider"


def test_ceiling_stops_the_run_in_preflight_without_starting_the_model(store, config, tmp_path, oai):
    _serve(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", mode=ApprovalMode.auto)
    run = _running(store, ctx, run)
    store.set_budget_policy(scope_kind="bot", scope_id=ctx.bot.id, ceiling_usd=0.001)

    with pytest.raises(RunAborted) as failure:
        run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools)
    assert failure.value.reason == "cost_cap"
    assert "ceiling" in failure.value.detail
    assert not oai.of("/v1/chat/completions"), "the capped run must never reach the provider"


def test_warn_band_logs_once_and_does_not_stop_the_run(store, config, tmp_path, oai):
    _serve(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", mode=ApprovalMode.auto)
    run = _running(store, ctx, run)
    store.set_budget_policy(scope_kind="bot", scope_id=ctx.bot.id, warn_usd=0.0001)

    assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "ok from the paid model"
    warnings = kinds(emitted, "budget")
    assert warnings and warnings[0]["threshold_usd"] == 0.0001
    assert "$0.0001" in warnings[0]["note"]


def test_unpriced_hosted_call_is_refused_under_a_default_policy(store, config, tmp_path, oai):
    _serve(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-unpriced", mode=ApprovalMode.auto)
    run = _running(store, ctx, run)
    store.set_budget_policy(scope_kind="bot", scope_id=ctx.bot.id, warn_usd=0.10)

    with pytest.raises(RunAborted) as failure:
        run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools)
    assert "no price basis" in failure.value.detail
    assert not oai.of("/v1/chat/completions")


def test_unknown_price_may_be_marked_under_a_soft_band_and_is_recorded_unknown(store, config, tmp_path, oai):
    _serve(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-unpriced", mode=ApprovalMode.auto)
    run = _running(store, ctx, run)
    store.set_budget_policy(scope_kind="bot", scope_id=ctx.bot.id, warn_usd=0.10, unknown_price="mark")

    assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "ok from the paid model"
    row = store._db.execute("SELECT status, cost_unknown, quote_source FROM usage_reservations WHERE run_id = ?",
                            (run.id,)).fetchone()
    assert row["status"] == "settled"
    assert row["cost_unknown"] == 1  # recorded as unknown, never as verified zero
    assert run.cost_usd == 0.0      # no charge was invented from an unknown price


def test_legacy_run_cap_still_wins_before_a_band(store, config, tmp_path, oai):
    _serve(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o", mode=ApprovalMode.auto,
                                     limits=Limits(max_cost_usd=0.00001))
    run = _running(store, ctx, run)
    store.set_budget_policy(scope_kind="bot", scope_id=ctx.bot.id, ceiling_usd=100.0)

    with pytest.raises(RunAborted) as failure:
        run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools)
    assert failure.value.reason == "cost_cap"
    assert not oai.of("/v1/chat/completions")
