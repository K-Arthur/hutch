"""Provider usage reservations serialize budgets across runs and survive uncertain outcomes."""

from __future__ import annotations

import threading
import uuid
from datetime import timedelta

import pytest

from hutch.models import Bot, Run, RunStatus, utcnow
from hutch.store import LeaseLost, Store, UsageBudgetRefusal
from typer.testing import CliRunner


def _run(store: Store, status: RunStatus = RunStatus.pending) -> tuple[Bot, Run]:
    bot = store.create_bot(Bot(name=f"budget-{status.value}-{uuid.uuid4().hex[:8]}"))
    run = store.create_run(Run(bot_id=bot.id, prompt="budget test", status=status))
    return bot, run


def _reserve(store: Store, bot: Bot, run: Run, *, account: str = "shared-account",
             tokens: int = 20, cost: float = 0.75, **caps) -> str:
    return store.reserve_usage(run_id=run.id, bot_id=bot.id, provider="vendor-a", account_id=account,
                               model="model-a", reserved_tokens=tokens, reserved_cost_usd=cost, **caps)


def test_two_process_connections_cannot_overreserve_a_shared_daily_account(config, store):
    bots_and_runs = [_run(store), _run(store)]
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def compete(bot: Bot, run: Run) -> None:
        other = Store(config)
        try:
            barrier.wait(timeout=5)
            try:
                _reserve(other, bot, run, daily_account_cost_cap_usd=1.0)
                result = "reserved"
            except UsageBudgetRefusal:
                result = "refused"
            with lock:
                results.append(result)
        finally:
            other.close()

    workers = [threading.Thread(target=compete, args=pair) for pair in bots_and_runs]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert all(not worker.is_alive() for worker in workers)
    assert sorted(results) == ["refused", "reserved"]
    reservations = store.unresolved_usage_reservations()
    assert len(reservations) == 1 and reservations[0]["reserved_cost_usd"] == pytest.approx(0.75)


def test_shared_account_token_windows_count_reservations_across_connections(store):
    first_bot, first_run = _run(store)
    second_bot, second_run = _run(store)
    _reserve(store, first_bot, first_run, tokens=70, cost=0.0, account_quotas=[(100, 3600)])

    with pytest.raises(UsageBudgetRefusal, match="allowance"):
        _reserve(store, second_bot, second_run, tokens=31, cost=0.0, account_quotas=[(100, 3600)])


def test_migrated_run_counters_still_consume_run_and_daily_limits(store):
    bot, run = _run(store)
    # Versions before schema v10 stored accounting only on the Run document.
    run.cost_usd = 0.90
    run.tokens = 90
    store.update_run(run)

    with pytest.raises(UsageBudgetRefusal, match=r"run's \$1.00 cap"):
        _reserve(store, bot, run, cost=0.20, max_run_cost_usd=1.0)
    with pytest.raises(UsageBudgetRefusal, match="daily cap"):
        _reserve(store, bot, run, tokens=20, cost=0.0, daily_token_cap=100)


def test_terminal_run_cannot_acquire_a_new_usage_reservation(store):
    bot, run = _run(store, RunStatus.running)
    store.transition_run(run.id, RunStatus.failed, exit_reason="test_failure")
    with pytest.raises(LeaseLost, match="terminal failed"):
        _reserve(store, bot, run)


def test_stale_fence_cannot_acquire_a_usage_reservation(store):
    bot, run = _run(store)
    first = store.claim_run(run.id, owner="first", lease_seconds=1)
    assert first is not None
    replacement = store.claim_run(run.id, owner="replacement", lease_seconds=30,
                                  now=utcnow() + timedelta(seconds=5))
    assert replacement is not None and replacement.fence > first.fence
    with pytest.raises(LeaseLost, match="fence .* is stale"):
        _reserve(store, bot, replacement, expected_fence=first.fence)


def test_settlement_is_atomic_idempotent_and_charges_actual_usage(store):
    bot, run = _run(store)
    reservation = _reserve(store, bot, run)

    store.add_usage(run.id, bot.id, "vendor-a", "model-a", 12, 3, cached_tokens=2,
                    cost_usd=0.12, account_id="ignored-after-reservation", reservation_id=reservation)
    store.add_usage(run.id, bot.id, "vendor-a", "model-a", 12, 3, cached_tokens=2,
                    cost_usd=0.12, reservation_id=reservation)

    row = store._db.execute("SELECT status, actual_prompt_tokens, actual_completion_tokens, actual_cached_tokens, "
                            "actual_cost_usd FROM usage_reservations WHERE id = ?", (reservation,)).fetchone()
    assert tuple(row) == ("settled", 12, 3, 2, pytest.approx(0.12))
    ledger = store._db.execute("SELECT COUNT(*), SUM(cost_usd), SUM(prompt_tokens + completion_tokens), "
                               "MIN(account_id) FROM usage WHERE reservation_id = ?", (reservation,)).fetchone()
    assert tuple(ledger) == (1, pytest.approx(0.12), 15, "shared-account")


def test_budget_snapshot_separates_measured_usage_from_held_estimates(store):
    bot, run = _run(store)
    store.add_usage(run.id, bot.id, "vendor-a", "model-a", 12, 3, cost_usd=0.12)
    reservation = _reserve(store, bot, run, tokens=40, cost=0.35)
    store.mark_usage_uncertain(reservation, "provider timed out")
    assert store.bot_budget_today(bot.id) == (15, 40, pytest.approx(0.12), pytest.approx(0.35))


def test_uncertain_usage_stays_held_until_terminal_run_is_reconciled(store):
    bot, run = _run(store, RunStatus.running)
    reservation = _reserve(store, bot, run, tokens=80, cost=0.80,
                           daily_account_cost_cap_usd=1.0)
    assert store.mark_usage_uncertain(reservation, "provider disconnected after request write")
    with pytest.raises(UsageBudgetRefusal, match="daily cap"):
        _reserve(store, *_run(store), cost=0.30, daily_account_cost_cap_usd=1.0)
    with pytest.raises(ValueError, match="still active"):
        store.resolve_usage_reservation(reservation, not_charged=True, reason="provider console checked")

    store.transition_run(run.id, RunStatus.failed, exit_reason="provider_error")
    assert store.resolve_usage_reservation(reservation, not_charged=True,
                                           reason="provider usage page confirmed no charge") == "released"
    assert store.resolve_usage_reservation(reservation, not_charged=True,
                                           reason="repeat verified no-charge resolution") == "released"
    assert store.unresolved_usage_reservations() == []
    retry_bot, retry = _run(store)
    assert _reserve(store, retry_bot, retry, tokens=80, cost=0.80,
                    daily_account_cost_cap_usd=1.0)


def test_terminal_recovery_marks_a_stranded_reservation_uncertain(store):
    bot, run = _run(store, RunStatus.running)
    reservation = _reserve(store, bot, run, tokens=48, cost=0.22)
    store.transition_run(run.id, RunStatus.outcome_unknown, exit_reason="worker_lost")
    row = store._db.execute("SELECT status, reason FROM usage_reservations WHERE id = ?", (reservation,)).fetchone()
    assert row["status"] == "uncertain" and "before provider usage was settled" in row["reason"]


def test_reconciliation_records_actual_usage_once_and_rejects_changed_outcome(store):
    bot, run = _run(store, RunStatus.running)
    reservation = _reserve(store, bot, run, tokens=100, cost=0.90)
    store.mark_usage_uncertain(reservation, "provider timed out")
    store.transition_run(run.id, RunStatus.outcome_unknown, exit_reason="action_outcome_unknown")

    kwargs = dict(prompt_tokens=48, completion_tokens=12, cached_tokens=8, actual_cost_usd=0.26,
                  reason="provider dashboard checked")
    assert store.resolve_usage_reservation(reservation, **kwargs) == "settled"
    assert store.resolve_usage_reservation(reservation, **kwargs) == "settled"
    with pytest.raises(ValueError, match="different outcome"):
        store.resolve_usage_reservation(reservation, prompt_tokens=49, completion_tokens=12,
                                        cached_tokens=8, actual_cost_usd=0.26, reason="changed")
    assert store._db.execute("SELECT COUNT(*) FROM usage WHERE reservation_id = ?", (reservation,)).fetchone()[0] == 1


def test_usage_store_rejects_nonfinite_or_negative_accounting(store):
    bot, run = _run(store)
    with pytest.raises(ValueError, match="finite and non-negative"):
        _reserve(store, bot, run, cost=float("nan"))
    with pytest.raises(ValueError, match="non-negative"):
        _reserve(store, bot, run, tokens=-1)
    with pytest.raises(ValueError, match="usage must contain"):
        store.add_usage(run.id, bot.id, "vendor-a", "model-a", 1, 1, cost_usd=float("inf"))


def test_cli_lists_and_reconciles_an_uncertain_terminal_reservation(config, monkeypatch):
    from hutch.cli import app

    monkeypatch.setenv("HUTCH_STATE_DIR", str(config.state_dir))
    store = Store(config)
    try:
        bot, run = _run(store, RunStatus.running)
        reservation = _reserve(store, bot, run, tokens=50, cost=0.2)
        store.mark_usage_uncertain(reservation, "provider disconnected")
        store.transition_run(run.id, RunStatus.failed, exit_reason="provider_error")
    finally:
        store.close()

    runner = CliRunner()
    listed = runner.invoke(app, ["usage", "reservations"])
    assert listed.exit_code == 0 and reservation in listed.output and "uncertain" in listed.output
    reconciled = runner.invoke(app, ["usage", "reconcile", reservation, "--not-charged",
                                    "--reason", "provider usage page confirms no charge"])
    assert reconciled.exit_code == 0 and "released" in reconciled.output
