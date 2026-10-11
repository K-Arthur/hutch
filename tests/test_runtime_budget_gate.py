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


def test_guard_prefers_a_live_quote_then_the_price_file_then_unknown(store, monkeypatch):
    from datetime import datetime, timezone
    from decimal import Decimal

    from hutch.models import Bot, Run
    from hutch.providers.openrouter_pricing import EndpointQuote, ModelQuote
    from hutch.providers.pricing import PriceBook
    from hutch.runtime.ladder import SpendGuard, make_rung

    bot = store.create_bot(Bot(name="router-quote-bot", model="openrouter/anthropic/claude-sonnet-4"))
    run = store.create_run(Run(bot_id=bot.id, prompt="quote"))

    class FakeConn:
        template = "openrouter"
        base_url = "https://router.example/api/v1"
        account_id = "acct-live"

    class FakeConnections:
        def get(self, provider):
            return FakeConn() if provider == "openrouter" else None

        def account_policy(self, account_id):
            return 0.0, []  # the ConnectionBook contract: (cap, shared token windows)

    endpoint = EndpointQuote(name="Vendor", provider_name="Vendor",
                             input_per_million=Decimal("2"), output_per_million=Decimal("10"))
    live = ModelQuote(model="anthropic/claude-sonnet-4", endpoints=(endpoint,),
                      fetched_at=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc), source="test")

    class FakeService:
        def quote(self, model, allow_stale=True):
            return live

    class NoQuote:
        def quote(self, model, *, allow_stale=True):
            return None

    guard = SpendGuard(store, bot, run, PriceBook(), FakeConnections())
    monkeypatch.setattr("hutch.providers.openrouter_pricing.live_pricing", lambda *a, **k: FakeService())
    quoted = guard.worst_case(make_rung("openrouter/anthropic/claude-sonnet-4", "primary"), 1000, 500)
    assert quoted.source == "openrouter"
    assert quoted.usd == pytest.approx(0.007)  # 1000*$2/M + 500*$10/M, rounded up

    monkeypatch.setattr("hutch.providers.openrouter_pricing.live_pricing", lambda *a, **k: NoQuote())
    priced_spec = PriceBook().rows()[0].model
    file_quote = guard.worst_case(make_rung(priced_spec, "primary"), 1000, 500)
    assert file_quote.source == "price_file" and file_quote.usd is not None

    unknown = guard.worst_case(make_rung("openai/gpt-unpriced", "primary"), 1000, 500)
    assert unknown.source == "unknown" and unknown.usd is None


def test_strict_openrouter_ceiling_fails_closed_on_stale_quote(store, monkeypatch):
    from datetime import datetime, timezone
    from decimal import Decimal

    from hutch.models import Bot, Limits, Run
    from hutch.providers.openrouter_pricing import EndpointQuote, ModelQuote
    from hutch.providers.pricing import PriceBook
    from hutch.runtime.ladder import SpendGuard, make_rung

    bot = store.create_bot(Bot(name="strict-router-bot", model="openrouter/acme/model",
                               limits=Limits(max_cost_usd=0.15)))
    run = store.create_run(Run(bot_id=bot.id, prompt="strict quote"))

    class FakeConn:
        template = "openrouter"
        base_url = "https://router.example/api/v1"
        account_id = "acct-strict"

    class FakeConnections:
        def get(self, provider):
            return FakeConn() if provider == "openrouter" else None

        def account_policy(self, account_id):
            return 0.0, []

    endpoint = EndpointQuote(name="Vendor", provider_name="Vendor",
                             input_per_million=Decimal("2"), output_per_million=Decimal("10"),
                             context_length=128000, supports_tools=True)
    stale = ModelQuote(model="acme/model", endpoints=(endpoint,),
                       fetched_at=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc), source="test",
                       stale=True, snapshot_digest="a" * 64)

    class FakeService:
        def quote(self, model, *, allow_stale=True):
            assert allow_stale is False
            return stale

    monkeypatch.setattr("hutch.providers.openrouter_pricing.live_pricing", lambda *a, **k: FakeService())
    guard = SpendGuard(store, bot, run, PriceBook(), FakeConnections())
    quote = guard.worst_case(make_rung("openrouter/acme/model", "primary"), 1000, 500)
    assert quote.source == "openrouter_unavailable" and quote.usd is None
    assert quote.snapshot_digest == "a" * 64
