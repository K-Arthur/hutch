from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Run
from hutch.providers.pricing import PriceBook
from hutch.runtime.ladder import SpendGuard, make_rung
from hutch.server.app import create_app


ACCOUNT = "acct_0123456789abcdef01234567"
PROVIDER = "chatgpt-0123456789abcdef01234567"


class ChatGPTConnection:
    name = PROVIDER
    auth_type = "chatgpt-siws"
    auth_account_id = ACCOUNT
    account_id = PROVIDER
    quota = SimpleNamespace(tokens=0, seconds=0, window="month")


class ConnectionBook:
    def __init__(self, account_id=ACCOUNT):
        self.connection = ChatGPTConnection()
        self.connection.auth_account_id = account_id

    def get(self, name):
        return self.connection if name == PROVIDER else None

    def account_policy(self, _account_id):
        return 0.0, []


class UsageStore:
    def cost_today(self, _bot_id):
        return 0.0


class RevocableUsageStore(UsageStore):
    def __init__(self, current_bot):
        self.current_bot = current_bot

    def get_bot(self, _bot_id):
        return self.current_bot


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as browser:
        yield browser


def test_chatgpt_plan_route_is_blocked_for_scheduled_use_without_bot_consent():
    bot = Bot(name="weekly-review", model=f"{PROVIDER}/gpt-preview", tools=[])
    run = Run(bot_id=bot.id, prompt="review", origin="schedule")
    guard = SpendGuard(UsageStore(), bot, run, PriceBook(Path("/missing-prices.json")), ConnectionBook())

    refusal = guard.refusal(make_rung(bot.model, "primary"), 100, 100)

    assert refusal and "express consent" in refusal.lower()
    assert "scheduled" in refusal.lower()


def test_chatgpt_plan_route_is_blocked_for_specialist_runs_without_consent():
    bot = Bot(name="specialist", model=f"{PROVIDER}/gpt-preview", tools=[])
    run = Run(bot_id=bot.id, prompt="review", origin="workspace_task")
    guard = SpendGuard(UsageStore(), bot, run, PriceBook(Path("/missing-prices.json")), ConnectionBook())

    refusal = guard.refusal(make_rung(bot.model, "primary"), 100, 100)

    assert refusal and "specialist" in refusal.lower()


def test_chatgpt_fallback_route_is_also_blocked_for_scheduled_use_without_consent():
    bot = Bot(name="weekly-review", model="ollama/local-model",
              fallbacks=[f"{PROVIDER}/gpt-preview"], tools=[])
    run = Run(bot_id=bot.id, prompt="review", origin="schedule")
    guard = SpendGuard(UsageStore(), bot, run, PriceBook(Path("/missing-prices.json")), ConnectionBook())

    refusal = guard.refusal(make_rung(bot.fallbacks[0], "fallback"), 100, 100)

    assert refusal and "express consent" in refusal.lower()


def test_manual_chatgpt_use_keeps_the_existing_per_run_authorization_path():
    bot = Bot(name="direct-chat", model=f"{PROVIDER}/gpt-preview", tools=[])
    run = Run(bot_id=bot.id, prompt="answer", origin="manual:api:v1")
    guard = SpendGuard(UsageStore(), bot, run, PriceBook(Path("/missing-prices.json")), ConnectionBook())

    assert guard.refusal(make_rung(bot.model, "primary"), 100, 100) is None


def test_background_consent_for_another_local_account_does_not_authorize_current_route():
    bot = Bot(name="weekly-review", model=f"{PROVIDER}/gpt-preview", tools=[])
    run = Run(bot_id=bot.id, prompt="review", origin="schedule")
    guard = SpendGuard(UsageStore(), bot, run, PriceBook(Path("/missing-prices.json")),
                       ConnectionBook("acct_fedcba9876543210fedcba98"))

    refusal = guard.refusal(make_rung(bot.model, "primary"), 100, 100)

    assert refusal and "express consent" in refusal.lower()


def test_revocation_after_run_start_is_checked_again_before_the_next_provider_request():
    from hutch.chatgpt_consent import CHATGPT_TERMS_REVISION, background_route_fingerprint
    from hutch.models import BackgroundProviderConsent

    bot = Bot(name="weekly-review", model=f"{PROVIDER}/gpt-preview", tools=[])
    consented = bot.model_copy(update={"background_provider_consents": [BackgroundProviderConsent(
        provider=PROVIDER, account_id=ACCOUNT, route_fingerprint=background_route_fingerprint(bot),
        terms_revision=CHATGPT_TERMS_REVISION,
    )]})
    run = Run(bot_id=bot.id, prompt="review", origin="schedule")
    guard = SpendGuard(RevocableUsageStore(consented), consented, run, PriceBook(Path("/missing-prices.json")),
                       ConnectionBook())

    assert guard.refusal(make_rung(bot.model, "primary"), 100, 100) is None
    guard.store.current_bot = bot
    refusal = guard.refusal(make_rung(bot.model, "primary"), 100, 100)

    assert refusal and "express consent" in refusal.lower()


@pytest.fixture()
def chatgpt_connection(client):
    from hutch.chatgpt_auth import ChatGPTAuthBook, PLAN_SCOPE
    from hutch.connections import ConnectionBook as LocalConnectionBook

    config, store = client.app.state.config, client.app.state.store
    account_id = ACCOUNT
    auth = ChatGPTAuthBook(config.state_dir)
    auth._write_accounts({"version": 1, "host_id": "fixture-host", "accounts": {
        account_id: {"access_token": "fixture-token", "refresh_token": "", "expires_at": 9_999_999_999,
                    "scopes": [PLAN_SCOPE], "client_id": "fixture-client", "subject": "fixture-subject"}
    }})
    connection = LocalConnectionBook(config.state_dir).add_chatgpt_account(account_id, "Fixture account")
    bot = store.create_bot(Bot(name="weekly-review", model=f"{connection.name}/gpt-preview", tools=[]))
    return bot, connection, account_id


def test_background_consent_is_explicit_account_scoped_and_route_bound(client, chatgpt_connection):
    from hutch.chatgpt_consent import background_route_fingerprint

    bot, connection, account_id = chatgpt_connection
    initial = client.get(f"/api/bots/{bot.name}").json()["chatgpt_background"][0]
    assert initial["state"] == "needs_consent"
    assert "account_id" not in initial

    granted = client.put(
        f"/api/v1/bots/{bot.id}/background-provider-consents/{connection.name}",
        json={"route_fingerprint": initial["route_fingerprint"]},
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["state"] == "allowed"

    saved = client.app.state.store.get_bot(bot.id)
    consent = next(item for item in saved.background_provider_consents if item.provider == connection.name)
    assert consent.account_id == account_id
    assert consent.terms_revision == "2026-09-29"

    changed = saved.model_copy(update={"fallbacks": ["ollama/local-model"]})
    client.app.state.store.upsert_bot(changed)
    stale = client.get(f"/api/bots/{bot.name}").json()["chatgpt_background"][0]
    assert stale["state"] == "needs_consent"
    assert stale["route_fingerprint"] == background_route_fingerprint(changed)

    renewed = client.put(
        f"/api/v1/bots/{bot.id}/background-provider-consents/{connection.name}",
        json={"route_fingerprint": initial["route_fingerprint"]},
    )
    assert renewed.status_code == 409
    removed = client.delete(f"/api/v1/bots/{bot.id}/background-provider-consents/{connection.name}")
    assert removed.status_code == 204
    assert not client.app.state.store.get_bot(bot.id).background_provider_consents


def test_chatgpt_disconnect_clears_background_consents(client, chatgpt_connection):
    bot, connection, _ = chatgpt_connection
    initial = client.get(f"/api/bots/{bot.name}").json()["chatgpt_background"][0]
    granted = client.put(
        f"/api/v1/bots/{bot.id}/background-provider-consents/{connection.name}",
        json={"route_fingerprint": initial["route_fingerprint"]},
    )
    assert granted.status_code == 200, granted.text

    disconnected = client.post(f"/api/chatgpt/accounts/{connection.auth_account_id}/disconnect")
    assert disconnected.status_code == 200, disconnected.text
    assert not client.app.state.store.get_bot(bot.id).background_provider_consents


def test_concurrent_disconnect_does_not_leave_a_dormant_background_grant(client, chatgpt_connection, monkeypatch):
    bot, connection, _ = chatgpt_connection
    initial = client.get(f"/api/bots/{bot.name}").json()["chatgpt_background"][0]
    monkeypatch.setattr("hutch.chatgpt_consent.chatgpt_background_view", lambda saved, book: [{
        "provider": connection.name, "title": connection.title, "state": "sign_in_required",
        "route_fingerprint": initial["route_fingerprint"],
    }])

    response = client.put(
        f"/api/v1/bots/{bot.id}/background-provider-consents/{connection.name}",
        json={"route_fingerprint": initial["route_fingerprint"]},
    )

    assert response.status_code == 409
    assert not client.app.state.store.get_bot(bot.id).background_provider_consents


def test_snapshot_never_exposes_local_chatgpt_account_ids(client, chatgpt_connection):
    bot, connection, account_id = chatgpt_connection
    initial = client.get(f"/api/bots/{bot.name}").json()["chatgpt_background"][0]
    granted = client.put(
        f"/api/v1/bots/{bot.id}/background-provider-consents/{connection.name}",
        json={"route_fingerprint": initial["route_fingerprint"]},
    )
    assert granted.status_code == 200, granted.text

    snapshot = client.get("/api/v1/snapshot").json()
    serialized = str(snapshot)
    saved = next(item for item in snapshot["items"]["bots"] if item["id"] == bot.id)
    assert "background_provider_consents" not in saved
    assert account_id not in serialized
