from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.outlook_calendar import OAuthStart
from hutch.outlook_mail import MAIL_SEND_SCOPE
from hutch.server.app import create_app


class FixtureOutlookMailSendBook:
    callback_queries = []
    accounts_rows = [{"id": "mssend_0123456789abcdef01234567", "label": "Work sender",
                      "created_at": "2026-10-10T00:00:00+00:00", "scopes": [MAIL_SEND_SCOPE],
                      "status": "connected"}]

    class Secrets:
        @staticmethod
        def available():
            return True

    def __init__(self, state_dir, client_id):
        self.secrets = self.Secrets()
        self.client_id = client_id

    def accounts(self):
        return self.accounts_rows

    @classmethod
    def callback_uri(cls, request):
        cls.callback_queries.append((request.scope.get("query_string"), request.scope.get("hutch_oauth_query")))
        return f"http://localhost:{request.scope['server'][1]}/api/v1/connections/outlook-mail-send/callback"

    def start(self, label, callback):
        assert label == "Work sender" and callback.startswith("http://localhost:")
        return OAuthStart("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=fixture", "fixture")

    def _account(self, account_id):
        return next(account for account in self.accounts_rows if account["id"] == account_id)

    @staticmethod
    def disconnect(account_id):
        assert account_id == "mssend_0123456789abcdef01234567"
        return {"removed": True, "provider_revocation": "unavailable"}

    @staticmethod
    def cancel(state):
        assert state == "single-use-fixture-state-000000000000"


def test_outlook_mail_send_connection_grant_and_disconnect_are_explicit_and_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")
    app = create_app()
    with TestClient(app) as client:
        monkeypatch.setattr("hutch.outlook_mail.OutlookMailSendBook", FixtureOutlookMailSendBook)
        bot = client.app.state.store.create_bot(Bot(name="outlook-sender", model="mock/demo", tools=[]))

        state = client.get("/api/v1/connections/outlook-mail-send")
        assert state.status_code == 200
        assert state.json() == {"configured": True, "secret_store_available": True,
                                "accounts": FixtureOutlookMailSendBook.accounts_rows, "grants": []}

        start = client.post("/api/v1/connections/outlook-mail-send/sign-in", json={"label": "Work sender"})
        assert start.status_code == 200
        assert start.headers["cache-control"] == "no-store"
        assert start.headers["referrer-policy"] == "no-referrer"
        assert urlsplit(start.json()["authorization_url"]).hostname == "login.microsoftonline.com"

        granted = client.post("/api/v1/connections/outlook-mail-send/grants", json={
            "bot": bot.id, "account_id": "mssend_0123456789abcdef01234567"})
        assert granted.status_code == 200, granted.text
        assert granted.json()["grant"]["account_label"] == "Work sender"
        assert granted.json()["grant"]["account_id"] == "mssend_0123456789abcdef01234567"
        detail = granted.json()["detail"]
        assert "Every send requires your exact approval" in detail
        assert "never retries an ambiguous result" in detail
        assert "mssend_0123456789abcdef01234567" not in detail
        assert client.app.state.store.outlook_mail_send_grant(bot.id)["account_id"] == "mssend_0123456789abcdef01234567"
        assert client.get("/api/v1/connections/outlook-mail-send").json()["grants"][0]["bot_name"] == "outlook-sender"

        removed = client.delete(f"/api/v1/connections/outlook-mail-send/grants/{bot.id}")
        assert removed.status_code == 200 and removed.json() == {"removed": True}
        client.app.state.store.set_outlook_mail_send_grant(bot.id, "mssend_0123456789abcdef01234567", "Work sender")
        disconnected = client.post(
            "/api/v1/connections/outlook-mail-send/accounts/mssend_0123456789abcdef01234567/disconnect", json={})
        assert disconnected.status_code == 200
        assert "does not offer a revocation endpoint" in disconnected.json()["detail"]
        assert client.app.state.store.list_outlook_mail_send_grants() == []


def test_outlook_mail_send_rejects_read_scope_and_redacts_oauth_denial(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")
    app = create_app()
    FixtureOutlookMailSendBook.callback_queries.clear()
    with TestClient(app) as client:
        monkeypatch.setattr("hutch.outlook_mail.OutlookMailSendBook", FixtureOutlookMailSendBook)
        bot = client.app.state.store.create_bot(Bot(name="outlook-sender-no-scope", model="mock/demo", tools=[]))
        FixtureOutlookMailSendBook.accounts_rows = [{**FixtureOutlookMailSendBook.accounts_rows[0], "scopes": ["Mail.Read"]}]
        rejected = client.post("/api/v1/connections/outlook-mail-send/grants", json={
            "bot": bot.id, "account_id": "mssend_0123456789abcdef01234567"})
        assert rejected.status_code == 422
        assert "did not grant Mail.Send" in rejected.json()["detail"]
        assert client.app.state.store.outlook_mail_send_grant(bot.id) is None

        FixtureOutlookMailSendBook.accounts_rows = [{**FixtureOutlookMailSendBook.accounts_rows[0], "scopes": [MAIL_SEND_SCOPE]}]
        result = client.get(
            "/api/v1/connections/outlook-mail-send/callback?state=single-use-fixture-state-000000000000&error=access_denied",
            headers={"host": "127.0.0.1"}, follow_redirects=False)
        assert result.status_code == 303
        assert "outlook_mail_send_result=error" in result.headers["location"]
        assert "access_denied" not in result.headers["location"]
        assert FixtureOutlookMailSendBook.callback_queries[-1] == (
            b"", {"state": ["single-use-fixture-state-000000000000"], "error": ["access_denied"]})
