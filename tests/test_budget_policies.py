"""Warn / pause / ceiling budget bands: explicit zero, atomic admission, scope aggregation (SR-2)."""

from __future__ import annotations

import threading
import uuid

import pytest

from hutch.models import Bot, Run
from hutch.store import (
    CallQuote,
    Store,
    UsageBudgetRefusal,
    UsagePauseRequired,
    UsageQuoteUnavailable,
)


def _bot_run(store: Store, *, conversation_id: str = "") -> tuple[Bot, Run]:
    bot = store.create_bot(Bot(name=f"policy-{uuid.uuid4().hex[:8]}"))
    run = store.create_run(Run(bot_id=bot.id, prompt="policy test", conversation_id=conversation_id))
    return bot, run


def _admit(store: Store, bot: Bot, run: Run, *, cost: float | None = 0.09, source: str = "caller",
           route_hash: str = "", account: str = "acct-a"):
    return store.admit_and_reserve(
        run_id=run.id, bot_id=bot.id, provider="vendor-a", account_id=account, model="model-a",
        reserved_tokens=100, quote=CallQuote(usd=cost, source=source), route_hash=route_hash)


def _conversation(store: Store, bot: Bot, title: str = "budget chat") -> str:
    conversation, _ = store.create_conversation(bot.id, title,
                                                idem_key=uuid.uuid4().hex, request_hash="h")
    return conversation["id"]


def test_unset_allows_and_zero_ceiling_refuses_paid_calls(store):
    bot, run = _bot_run(store)
    _admit(store, bot, run, cost=0.75)  # no policy: legacy behaviour unchanged

    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, ceiling_usd=0.0)
    second = store.create_run(Run(bot_id=bot.id, prompt="policy test"))
    with pytest.raises(UsageBudgetRefusal, match=r"\$0\.00 ceiling"):
        _admit(store, bot, second, cost=0.01)
    _admit(store, bot, second, cost=0.0)  # a zero-cost call adds nothing to the capped total

    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, ceiling_usd=None)
    third = store.create_run(Run(bot_id=bot.id, prompt="policy test"))
    _admit(store, bot, third, cost=0.75)


def test_policy_validation_rejects_bad_bands_and_missing_scopes(store):
    bot, _ = _bot_run(store)
    with pytest.raises(ValueError):
        store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=0.3, pause_usd=0.2)
    with pytest.raises(ValueError):
        store.set_budget_policy(scope_kind="bot", scope_id=bot.id, pause_usd=0.3, ceiling_usd=0.2)
    with pytest.raises(ValueError):
        store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=-0.1)
    with pytest.raises(ValueError):
        store.set_budget_policy(scope_kind="run", scope_id="run_missing", ceiling_usd=1.0)
    with pytest.raises(ValueError):
        store.set_budget_policy(scope_kind="bot", scope_id=bot.id, reset="run_lifetime")


def test_warn_fires_once_per_cycle_and_rearms_on_policy_change(store):
    bot, first = _bot_run(store)
    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=0.05)
    reservation = _admit(store, bot, first, cost=0.06)
    assert [w.threshold_usd for w in reservation.warnings] == [0.05]

    second = store.create_run(Run(bot_id=bot.id, prompt="policy test"))
    again = store.admit_and_reserve(
        run_id=second.id, bot_id=bot.id, provider="vendor-a", account_id="acct-a", model="model-a",
        reserved_tokens=100, quote=CallQuote(usd=0.06, source="caller"))
    assert again.warnings == ()  # already warned in this cycle

    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=0.05)  # re-arm
    third = store.create_run(Run(bot_id=bot.id, prompt="policy test"))
    rearmed = store.admit_and_reserve(
        run_id=third.id, bot_id=bot.id, provider="vendor-a", account_id="acct-a", model="model-a",
        reserved_tokens=100, quote=CallQuote(usd=0.06, source="caller"))
    assert [w.threshold_usd for w in rearmed.warnings] == [0.05]


def test_exact_equality_at_a_threshold_is_admissible(store):
    bot, run = _bot_run(store)
    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=0.06, ceiling_usd=0.06)
    reservation = _admit(store, bot, run, cost=0.06)
    assert reservation.warnings == ()


def test_pause_requires_a_human_release_and_never_lifts_the_ceiling(store):
    bot, first = _bot_run(store)
    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=0.05, pause_usd=0.10,
                            ceiling_usd=0.20)
    _admit(store, bot, first, cost=0.09)

    second = store.create_run(Run(bot_id=bot.id, prompt="policy test"))
    with pytest.raises(UsagePauseRequired) as pause:
        _admit(store, bot, second, cost=0.06, route_hash="route-1")
    assert pause.value.scope_kind == "bot" and pause.value.pause_usd == 0.10
    # detection writes nothing: no reservation, no warning update
    assert len(store.unresolved_usage_reservations()) == 1

    # a release for a different route does not lift this route's pause
    store.record_budget_pause_release(scope_kind="bot", scope_id=bot.id, route_hash="route-2",
                                      cycle_key=pause.value.cycle_key,
                                      policy_revision=pause.value.policy_revision, quote_usd=0.06)
    with pytest.raises(UsagePauseRequired):
        _admit(store, bot, second, cost=0.06, route_hash="route-1")

    store.record_budget_pause_release(scope_kind="bot", scope_id=bot.id, route_hash="route-1",
                                      cycle_key=pause.value.cycle_key,
                                      policy_revision=pause.value.policy_revision, quote_usd=0.06)
    _admit(store, bot, second, cost=0.06, route_hash="route-1")

    third = store.create_run(Run(bot_id=bot.id, prompt="policy test"))
    with pytest.raises(UsageBudgetRefusal, match=r"\$0\.20 ceiling"):
        _admit(store, bot, third, cost=0.06, route_hash="route-1")


def test_conversation_ceiling_counts_sibling_runs(store):
    bot, first = _bot_run(store)
    conversation = _conversation(store, bot)
    store.set_budget_policy(scope_kind="conversation", scope_id=conversation, ceiling_usd=0.15)

    first = store.create_run(Run(bot_id=bot.id, prompt="one", conversation_id=conversation))
    second = store.create_run(Run(bot_id=bot.id, prompt="two", conversation_id=conversation))
    elsewhere = store.create_run(Run(bot_id=bot.id, prompt="other", conversation_id="conv_other"))

    _admit(store, bot, first, cost=0.09)
    with pytest.raises(UsageBudgetRefusal, match="conversation"):
        _admit(store, bot, second, cost=0.07)
    _admit(store, bot, elsewhere, cost=0.07)  # a different conversation is unaffected

    measured, held = store.scope_spend(scope_kind="conversation", scope_id=conversation)
    assert (measured, held) == (0.0, 0.09)


def test_shared_ceiling_is_atomic_across_two_store_connections(config, store):
    bot, _ = _bot_run(store)
    first = store.create_run(Run(bot_id=bot.id, prompt="one"))
    second = store.create_run(Run(bot_id=bot.id, prompt="two"))
    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, ceiling_usd=0.15)

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def compete(slug: str, run: Run) -> None:
        other = Store(config)
        try:
            barrier.wait(timeout=5)
            try:
                other.admit_and_reserve(run_id=run.id, bot_id=bot.id, provider="vendor-a",
                                        account_id="acct-a", model="model-a", reserved_tokens=100,
                                        quote=CallQuote(usd=0.09, source="caller"))
                result = "reserved"
            except UsageBudgetRefusal:
                result = "refused"
            with lock:
                results.append(result)
        finally:
            other.close()

    workers = [threading.Thread(target=compete, args=pair) for pair in (("one", first), ("two", second))]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
    assert all(not worker.is_alive() for worker in workers)
    assert sorted(results) == ["refused", "reserved"]
    assert len(store.unresolved_usage_reservations()) == 1


def test_unknown_price_refuses_under_a_ceiling_and_is_marked_under_soft_bands(store):
    bot, run = _bot_run(store)
    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=0.10)
    with pytest.raises(UsageQuoteUnavailable):
        _admit(store, bot, run, cost=None, source="unknown")

    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=0.10, unknown_price="mark")
    reservation = _admit(store, bot, run, cost=None, source="unknown")
    held = {row["id"]: row for row in store.unresolved_usage_reservations()}
    assert held[reservation.id]["cost_unknown"] == 1

    store.set_budget_policy(scope_kind="bot", scope_id=bot.id, warn_usd=0.10, ceiling_usd=1.0,
                            unknown_price="mark")
    with pytest.raises(UsageQuoteUnavailable):
        _admit(store, bot, run, cost=None, source="unknown")


def test_quote_provenance_is_recorded(store):
    bot, run = _bot_run(store)
    reservation = store.admit_and_reserve(
        run_id=run.id, bot_id=bot.id, provider="openrouter", account_id="acct-a", model="vendor/model",
        reserved_tokens=100,
        quote=CallQuote(usd=0.05, source="openrouter", verified_on="2026-10-11T00:00:00+00:00"))
    row = {item["id"]: item for item in store.unresolved_usage_reservations()}[reservation.id]
    assert row["quote_source"] == "openrouter"
    assert row["quote_verified_on"] == "2026-10-11T00:00:00+00:00"


def test_scope_spend_reports_measured_and_held(store):
    bot, run = _bot_run(store)
    reservation = _admit(store, bot, run, cost=0.09)
    assert store.scope_spend(scope_kind="bot", scope_id=bot.id) == (0.0, 0.09)

    store.add_usage(run.id, bot.id, "vendor-a", "model-a", 10, 5, cost_usd=0.05,
                    account_id="acct-a", reservation_id=reservation.id)
    measured, held = store.scope_spend(scope_kind="bot", scope_id=bot.id)
    assert measured == pytest.approx(0.05) and held == 0.0
    run_measured, run_held = store.scope_spend(scope_kind="run", scope_id=run.id)
    assert run_measured == pytest.approx(0.05) or run_measured == pytest.approx(0.09)


def test_migration_creates_policy_tables(store):
    from hutch.store import SCHEMA_VERSION
    version = store._db.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    tables = {row[0] for row in store._db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    assert {"budget_policies", "budget_pause_releases"} <= tables
    columns = {row[1] for row in store._db.execute("PRAGMA table_info(usage_reservations)").fetchall()}
    assert {"cost_unknown", "quote_source", "quote_verified_on"} <= columns
