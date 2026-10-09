from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.outlook_calendar import OAuthStart
from hutch.server.app import create_app


class FixtureOutlookMailBook:
    callback_scopes = []
    accounts_rows = [{"id": "msmail_0123456789abcdef01234567", "label": "Work",
                      "created_at": "2026-10-09T00:00:00+00:00", "scopes": ["Mail.Read"],
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
        cls.callback_scopes.append((request.scope.get("query_string"), request.scope.get("hutch_oauth_query")))
        return f"http://localhost:{request.scope['server'][1]}/api/v1/connections/outlook-mail/callback"

    def start(self, label, callback):
        assert label == "Work" and callback.startswith("http://localhost:")
        return OAuthStart("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=fixture", "fixture")

    def _account(self, account_id):
        assert account_id == "msmail_0123456789abcdef01234567"
        return self.accounts_rows[0]

    @staticmethod
    def disconnect(account_id):
        assert account_id == "msmail_0123456789abcdef01234567"
        return {"removed": True, "provider_revocation": "unavailable"}

    @staticmethod
    def cancel(state):
        assert state == "single-use-fixture-state-000000000000"


def test_outlook_mail_connection_and_bot_grant_are_explicit_and_revocable(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")
    app = create_app()
    with TestClient(app) as client:
        monkeypatch.setattr("hutch.outlook_mail.OutlookMailBook", FixtureOutlookMailBook)
        bot = client.app.state.store.create_bot(Bot(name="mail-reviewer", model="mock/demo", tools=[]))

        state = client.get("/api/v1/connections/outlook-mail")
        assert state.status_code == 200
        assert state.json() == {"configured": True, "secret_store_available": True,
                                "accounts": FixtureOutlookMailBook.accounts_rows, "grants": []}

        start = client.post("/api/v1/connections/outlook-mail/sign-in", json={"label": "Work"})
        assert start.status_code == 200
        assert start.headers["cache-control"] == "no-store"
        assert start.headers["referrer-policy"] == "no-referrer"
        assert urlsplit(start.json()["authorization_url"]).hostname == "login.microsoftonline.com"

        granted = client.post("/api/v1/connections/outlook-mail/grants", json={
            "bot": bot.id, "account_id": "msmail_0123456789abcdef01234567"})
        assert granted.status_code == 200, granted.text
        assert "Mail.Read account consent" in granted.json()["detail"]
        assert "in Work" in granted.json()["detail"]
        assert "msmail_0123456789abcdef01234567" not in granted.json()["detail"]
        assert "cannot send, change, delete or forward" in granted.json()["detail"]
        assert client.app.state.store.outlook_mail_grant(bot.id)["account_id"] == "msmail_0123456789abcdef01234567"

        removed = client.delete(f"/api/v1/connections/outlook-mail/grants/{bot.id}")
        assert removed.status_code == 200 and removed.json() == {"removed": True}
        client.app.state.store.set_outlook_mail_grant(bot.id, "msmail_0123456789abcdef01234567")
        disconnected = client.post("/api/v1/connections/outlook-mail/accounts/msmail_0123456789abcdef01234567/disconnect", json={})
        assert disconnected.status_code == 200 and disconnected.json()["provider_revocation"] == "unavailable"
        assert "does not offer a revocation endpoint" in disconnected.json()["detail"]
        assert client.app.state.store.list_outlook_mail_grants() == []


def test_outlook_mail_oauth_denial_is_consumed_and_credentials_stay_out_of_redirect(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")
    app = create_app()
    FixtureOutlookMailBook.callback_scopes.clear()
    with TestClient(app) as client:
        monkeypatch.setattr("hutch.outlook_mail.OutlookMailBook", FixtureOutlookMailBook)
        result = client.get(
            "/api/v1/connections/outlook-mail/callback?state=single-use-fixture-state-000000000000&error=access_denied",
            headers={"host": "127.0.0.1"}, follow_redirects=False)
    assert result.status_code == 303
    values = parse_qs(urlsplit(result.headers["location"]).query)
    assert values["outlook_mail_result"] == ["error"]
    assert values["detail"] == ["Outlook Mail access was not granted; no account was connected"]
    assert "access_denied" not in result.headers["location"]
    scope_query, saved_fields = FixtureOutlookMailBook.callback_scopes[-1]
    assert scope_query == b""
    assert saved_fields == {"state": ["single-use-fixture-state-000000000000"], "error": ["access_denied"]}
