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

    expired = ModelQuote(model="acme/model", endpoints=(endpoint,),
                         fetched_at=datetime(2020, 1, 1, tzinfo=timezone.utc), source="test",
                         stale=False, snapshot_digest="b" * 64,
                         expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))

    class ExpiredService:
        def quote(self, model, *, allow_stale=True):
            assert allow_stale is False
            return expired

    monkeypatch.setattr("hutch.providers.openrouter_pricing.live_pricing", lambda *a, **k: ExpiredService())
    expired_quote = guard.worst_case(make_rung("openrouter/acme/model", "primary"), 1000, 500)
    assert expired_quote.source == "openrouter_unavailable" and expired_quote.usd is None


def test_capped_openrouter_reserves_context_capacity_instead_of_optimistic_token_estimate(store, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from types import SimpleNamespace
    from hutch.models import Bot, Run
    from hutch.providers.openrouter_pricing import EndpointQuote, ModelQuote
    from hutch.providers.pricing import PriceBook
    from hutch.runtime.ladder import SpendGuard, make_rung
    from hutch.store import UsageBudgetRefusal

    bot = store.create_bot(Bot(name='capacity-budget', model='router/acme/model'))
    run = store.create_run(Run(bot_id=bot.id, prompt='Short estimate, potentially different provider tokenization'))
    store.set_budget_policy(scope_kind='account', scope_id='capacity-account', reset='lifetime', ceiling_usd=.2)
    now = datetime.now(timezone.utc)
    endpoints = (
        EndpointQuote(name='large', provider_name='large', input_per_million=Decimal('2'),
                      output_per_million=Decimal('10'), context_length=128000, supports_tools=True),
        EndpointQuote(name='limited', provider_name='limited', input_per_million=Decimal('20'),
                      output_per_million=Decimal('10'), context_length=128000, max_prompt_tokens=4000,
                      supports_tools=True),
    )
    quote = ModelQuote(model='acme/model', endpoints=endpoints, fetched_at=now,
                       expires_at=now + timedelta(minutes=5), snapshot_digest='c' * 64)
    service = SimpleNamespace(quote=lambda *args, **kwargs: quote)
    monkeypatch.setattr('hutch.providers.openrouter_pricing.live_pricing', lambda *args, **kwargs: service)
    connection = SimpleNamespace(template='openrouter', base_url='https://router.example/api/v1',
                                 account_id='capacity-account')
    connections = SimpleNamespace(get=lambda name: connection, account_policy=lambda account: (0.0, []))
    guard = SpendGuard(store, bot, run, PriceBook(), connections)
    rung = make_rung('router/acme/model', 'primary')
    reserved = guard.worst_case(rung, 1000, 500)
    # Each endpoint is bounded separately. Larger context: .256 + .005;
    # smaller prompt limit at higher rate: .080 + .005. Never mix rates/limits.
    assert reserved.usd == pytest.approx(.261)
    assert reserved.billing_unit == 'USD/context-capacity-reserve'
    with pytest.raises(UsageBudgetRefusal):
        guard.reserve(rung, 1000, 500)
    assert not store.unresolved_usage_reservations()


def test_named_openrouter_route_uses_fresh_quote_without_a_duplicate_manual_price_row(store, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from types import SimpleNamespace
    from hutch.models import Bot, Run
    from hutch.providers.openrouter_pricing import EndpointQuote, ModelQuote
    from hutch.providers.pricing import PriceBook
    from hutch.runtime.ladder import SpendGuard, make_rung

    bot = store.create_bot(Bot(name='named-live-quote', model='research-router/acme/current-model'))
    run = store.create_run(Run(bot_id=bot.id, prompt='Known fresh quote, no manual prices row'))
    store.set_budget_policy(scope_kind='account', scope_id='named-account', reset='lifetime', ceiling_usd=1)
    now = datetime.now(timezone.utc)
    quote = ModelQuote(model='acme/current-model', endpoints=(EndpointQuote(
        name='provider', provider_name='provider', input_per_million=Decimal('2'),
        output_per_million=Decimal('10'), context_length=128000, supports_tools=True),),
        fetched_at=now, expires_at=now + timedelta(minutes=5))
    service = SimpleNamespace(quote=lambda *args, **kwargs: quote)
    monkeypatch.setattr('hutch.providers.openrouter_pricing.live_pricing', lambda *args, **kwargs: service)
    connection = SimpleNamespace(template='openrouter', base_url='https://router.example/api/v1',
                                 account_id='named-account', auth_type='api_key',
                                 quota=SimpleNamespace(tokens=0))
    connections = SimpleNamespace(get=lambda name: connection, account_policy=lambda account: (0.0, []))
    prices = PriceBook()
    assert not prices.has_price('research-router', 'acme/current-model')
    guard = SpendGuard(store, bot, run, prices, connections)
    assert guard.refusal(make_rung(bot.model, 'primary'), 1000, 512) is None
    service.quote = lambda *args, **kwargs: None
    assert 'refresh eligible endpoint pricing' in guard.refusal(make_rung(bot.model, 'primary'), 1000, 512)
    assert not store.unresolved_usage_reservations()


@pytest.mark.parametrize('reported_cost', [None, True, -1, float('nan'), 0.0, .02])
def test_openrouter_missing_billed_cost_holds_the_quote_before_tools_and_zero_is_valid(
        store, config, tmp_path, monkeypatch, oai, reported_cost):
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    from types import SimpleNamespace
    from hutch.connections import ConnectionBook
    from hutch.providers.openrouter_pricing import EndpointQuote, ModelQuote

    book = ConnectionBook(config.state_dir)
    book.add('openrouter', 'budget-router', base_url=oai.url + '/v1', account_id='router-account')
    book.set_key('budget-router', 'synthetic-fixture-credential', prefer_stored=True)
    now = datetime.now(timezone.utc)
    quote = ModelQuote(model='acme/current', endpoints=(EndpointQuote(name='vendor', provider_name='vendor',
        input_per_million=Decimal('2'), output_per_million=Decimal('10'), context_length=128000,
        supports_tools=True),), fetched_at=now, expires_at=now + timedelta(minutes=5))
    monkeypatch.setattr('hutch.providers.openrouter_pricing.live_pricing',
                        lambda *args, **kwargs: SimpleNamespace(quote=lambda *args, **kwargs: quote))
    store.set_budget_policy(scope_kind='account', scope_id='router-account', reset='lifetime', ceiling_usd=1)
    ctx, run, _events, tools = build(store, config, tmp_path, model='budget-router/acme/current',
        mode=ApprovalMode.auto, tools=('files',), limits=Limits(max_steps=4, max_turn_tokens=512))
    calls = []

    def reply(body):
        calls.append(body)
        result = {'prompt_tokens': 100, 'completion_tokens': 20}
        if len(calls) == 1:
            result['tool_calls'] = [{'name': 'write_file', 'arguments': {'path': 'result.txt', 'content': 'verified'}}]
        else:
            result['content'] = 'Done'
        if reported_cost is not None:
            result['cost'] = reported_cost
        return result

    oai.script = reply
    import math
    valid_cost = type(reported_cost) in (int, float) and math.isfinite(reported_cost) and reported_cost >= 0
    if not valid_cost:
        with pytest.raises(RunAborted, match='billed cost') as missing:
            run_it(runtime(), run, ctx, tools)
        assert missing.value.reason == 'usage_unknown'
        assert len(calls) == 1 and not (ctx.workspace / 'result.txt').exists()
        holds = store.unresolved_usage_reservations()
        assert len(holds) == 1 and holds[0]['status'] == 'uncertain' and holds[0]['reserved_cost_usd'] > 0
        assert not store.list_actions(run.id)
    else:
        assert run_it(runtime(), run, ctx, tools) == 'Done'
        assert len(calls) == 2 and (ctx.workspace / 'result.txt').read_text() == 'verified'
        assert not store.unresolved_usage_reservations()
        assert store.scope_spend(scope_kind='account', scope_id='router-account') == pytest.approx((reported_cost * 2, 0))
