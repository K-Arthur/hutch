"""One billing account's total ceiling survives days, Bots and uncertain calls."""
from datetime import timedelta

import pytest

from hutch.models import Bot, Run, utcnow
from hutch.store import CallQuote, UsageBudgetRefusal
from tests.test_budget_api import client  # noqa: F401
from tests.test_budget_policies import _admit, _bot_run


def test_lifetime_account_limit_counts_prior_days_other_bots_and_uncertain_holds(store, monkeypatch):
    bot, previous = _bot_run(store)
    now = utcnow()
    monkeypatch.setattr('hutch.store.utcnow', lambda: now - timedelta(days=2))
    store.add_usage(previous.id, bot.id, 'vendor-a', 'model-a', 100, 10,
                    cost_usd=.8, account_id='shared-evaluation')
    hold = _admit(store, bot, previous, cost=.1, account='shared-evaluation')
    assert store.mark_usage_uncertain(hold.id, 'fixture lost response')
    monkeypatch.setattr('hutch.store.utcnow', lambda: now)
    other = store.create_bot(Bot(name='other-evaluation-bot'))
    next_run = store.create_run(Run(bot_id=other.id, prompt='A separate workflow'))
    store.set_budget_policy(scope_kind='account', scope_id='shared-evaluation',
                            ceiling_usd=1, reset='lifetime')
    assert store.scope_spend(scope_kind='account', scope_id='shared-evaluation') == pytest.approx((.8, .1))
    periods = store.account_budget_periods('shared-evaluation')
    assert periods['local_day'] == pytest.approx({'spent_usd': 0, 'held_usd': .1})
    assert periods['lifetime'] == pytest.approx({'spent_usd': .8, 'held_usd': .1})
    quote = CallQuote(usd=.2, source='caller')
    assert store.budget_admission_block(run_id=next_run.id, quote=quote, account_id='shared-evaluation')
    with pytest.raises(UsageBudgetRefusal, match='ceiling'):
        _admit(store, other, next_run, cost=.2, account='shared-evaluation')
    # Another account and verified free calls remain independent.
    _admit(store, other, next_run, cost=.2, account='independent')
    _admit(store, other, next_run, cost=0, account='shared-evaluation')


def test_stale_budget_form_cannot_replace_a_newer_ceiling(client):  # noqa: F811
    body = {'scope_kind': 'account', 'scope_id': 'evaluation', 'ceiling_usd': 1,
            'expected_revision': 0}
    first = client.put('/api/v1/budgets', json=body)
    assert first.status_code == 200, first.text
    newer = client.put('/api/v1/budgets', json={**body, 'ceiling_usd': .5, 'expected_revision': 1})
    assert newer.status_code == 200 and newer.json()['revision'] == 2
    stale = client.put('/api/v1/budgets', json={**body, 'ceiling_usd': 10, 'expected_revision': 1})
    assert stale.status_code == 409
    assert client.app.state.store.get_budget_policy('account', 'evaluation').ceiling_usd == .5


def test_lifetime_account_limit_and_uncertain_holds_survive_restart(config):
    from hutch.store import Store
    first = Store(config)
    try:
        bot, run = _bot_run(first)
        first.set_budget_policy(scope_kind='account', scope_id='durable-budget', reset='lifetime', ceiling_usd=1)
        reservation = _admit(first, bot, run, cost=.8, account='durable-budget')
        first.mark_usage_uncertain(reservation.id, 'fixture response lost')
    finally:
        first.close()
    restarted = Store(config)
    try:
        assert restarted.get_budget_policy('account', 'durable-budget').reset == 'lifetime'
        assert restarted.scope_spend(scope_kind='account', scope_id='durable-budget') == pytest.approx((0, .8))
        with pytest.raises(UsageBudgetRefusal):
            _admit(restarted, bot, run, cost=.3, account='durable-budget')
    finally:
        restarted.close()


def test_zero_lifetime_ceiling_refuses_unpriced_or_paid_calls(store):
    from hutch.store import UsageQuoteUnavailable
    bot, run = _bot_run(store)
    store.set_budget_policy(scope_kind='account', scope_id='free-only', reset='lifetime', ceiling_usd=0)
    _admit(store, bot, run, cost=0, account='free-only')
    with pytest.raises(UsageBudgetRefusal):
        _admit(store, bot, run, cost=.001, account='free-only')
    with pytest.raises(UsageQuoteUnavailable):
        _admit(store, bot, run, cost=None, account='free-only')


def test_lifetime_budget_is_atomic_across_store_connections_and_bots(store, config):
    import queue
    import threading
    from hutch.store import Store
    first, first_run = _bot_run(store)
    second, second_run = _bot_run(store)
    store.set_budget_policy(scope_kind='account', scope_id='concurrent-budget', reset='lifetime', ceiling_usd=1)
    peer = Store(config)
    barrier, results = threading.Barrier(2), queue.Queue()

    def admit(connection, bot, run):
        barrier.wait(timeout=5)
        try:
            _admit(connection, bot, run, cost=.6, account='concurrent-budget')
            results.put('reserved')
        except UsageBudgetRefusal:
            results.put('refused')

    threads = [threading.Thread(target=admit, args=args) for args in (
        (store, first, first_run), (peer, second, second_run))]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)
            assert not thread.is_alive()
        assert sorted(results.get_nowait() for _ in threads) == ['refused', 'reserved']
        assert store.scope_spend(scope_kind='account', scope_id='concurrent-budget') == pytest.approx((0, .6))
    finally:
        peer.close()


def test_legacy_connection_directory_counts_the_same_shared_account_as_admission(client, monkeypatch):  # noqa: F811
    from hutch.connections import ConnectionBook
    monkeypatch.setattr(client.app.state.engine, 'tick', lambda: None)
    book = ConnectionBook(client.app.state.config.state_dir)
    for name in ('research-budget', 'writing-budget'):
        book.add('openrouter', name, account_id='same-account', quota={'tokens': 1000, 'window': 'day'})
    bot, run = _bot_run(client.app.state.store)
    client.app.state.store.add_usage(run.id, bot.id, 'research-budget', 'fixture', 10, 5, account_id='same-account')
    client.app.state.store.add_usage(run.id, bot.id, 'writing-budget', 'fixture', 20, 5, account_id='same-account')
    rows = client.get('/api/connections').json()['connections']
    assert {item['name']: item['used'] for item in rows} == {'research-budget': 40, 'writing-budget': 40}
