from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.outlook_calendar import OAuthStart
from hutch.server.app import create_app


class FixtureOutlookCalendarBook:
    callback_scopes = []
    accounts_rows = [{"id": "mscal_0123456789abcdef01234567", "label": "Work",
                      "created_at": "2026-10-09T00:00:00+00:00", "scopes": ["Calendars.ReadBasic"],
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

    @staticmethod
    def callback_uri(request):
        FixtureOutlookCalendarBook.callback_scopes.append((request.scope.get("query_string"),
                                                           request.scope.get("hutch_oauth_query")))
        port = request.scope["server"][1]
        return f"http://localhost:{port}/api/v1/connections/outlook-calendar/callback"

    def start(self, label, callback):
        assert label == "Work" and callback.startswith("http://localhost:")
        return OAuthStart("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=fixture", "fixture")

    @staticmethod
    def list_calendars(account_id):
        assert account_id == "mscal_0123456789abcdef01234567"
        return [{"id": "primary", "name": "Work Calendar", "primary": True},
                {"id": "team", "name": "Team", "primary": False}]

    @staticmethod
    def disconnect(account_id):
        assert account_id == "mscal_0123456789abcdef01234567"
        return {"removed": True, "provider_revocation": "unavailable"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "fixture-public-client")
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def use_fixture_book(monkeypatch):
    monkeypatch.setattr("hutch.outlook_calendar.OutlookCalendarBook", FixtureOutlookCalendarBook)


def test_outlook_calendar_connections_grant_revoke_and_disconnect_are_typed_and_local(client, monkeypatch):
    use_fixture_book(monkeypatch)
    bot = client.app.state.store.create_bot(Bot(name="calendar-research", model="mock/demo", tools=[]))

    state = client.get("/api/v1/connections/outlook-calendar")
    assert state.status_code == 200
    assert state.json() == {"configured": True, "secret_store_available": True,
                            "accounts": FixtureOutlookCalendarBook.accounts_rows, "grants": []}

    start = client.post("/api/v1/connections/outlook-calendar/sign-in", json={"label": "Work"})
    assert start.status_code == 200
    assert start.headers["cache-control"] == "no-store"
    assert start.headers["referrer-policy"] == "no-referrer"
    assert urlsplit(start.json()["authorization_url"]).hostname == "login.microsoftonline.com"

    calendars = client.get("/api/v1/connections/outlook-calendar/calendars",
                           params={"account_id": "mscal_0123456789abcdef01234567"})
    assert calendars.status_code == 200 and calendars.json()["calendars"][0]["primary"]
    granted = client.post("/api/v1/connections/outlook-calendar/grants", json={
        "bot": bot.id, "account_id": "mscal_0123456789abcdef01234567", "calendar_id": "primary"})
    assert granted.status_code == 200, granted.text
    assert "Calendars.ReadBasic account consent" in granted.json()["detail"]
    assert "Bodies and attachments are excluded" in granted.json()["detail"]
    assert client.app.state.store.outlook_calendar_grant(bot.id)["calendar_id"] == "primary"

    removed = client.delete(f"/api/v1/connections/outlook-calendar/grants/{bot.id}")
    assert removed.status_code == 200 and removed.json() == {"removed": True}
    client.app.state.store.set_outlook_calendar_grant(bot.id, "mscal_0123456789abcdef01234567", "primary", "Work Calendar")
    disconnected = client.post("/api/v1/connections/outlook-calendar/accounts/mscal_0123456789abcdef01234567/disconnect", json={})
    assert disconnected.status_code == 200 and disconnected.json()["provider_revocation"] == "unavailable"
    assert "does not offer a revocation endpoint" in disconnected.json()["detail"]
    assert client.app.state.store.list_outlook_calendar_grants() == []


def test_outlook_calendar_oauth_callback_consumes_denial_and_redirects_without_credentials(client, monkeypatch):
    use_fixture_book(monkeypatch)
    cancelled = []
    FixtureOutlookCalendarBook.callback_scopes.clear()

    def cancel(self, state):
        cancelled.append(state)

    monkeypatch.setattr(FixtureOutlookCalendarBook, "cancel", cancel, raising=False)
    result = client.get("/api/v1/connections/outlook-calendar/callback?state=single-use-fixture-state-000000000000&error=access_denied",
                        headers={"host": "127.0.0.1"}, follow_redirects=False)
    assert result.status_code == 303
    assert cancelled == ["single-use-fixture-state-000000000000"]
    location = result.headers["location"]
    assert "outlook_calendar_result=error" in location
    values = parse_qs(urlsplit(location).query)
    assert values["detail"] == ["Outlook Calendar access was not granted; no account was connected"]
    assert "access_denied" not in location
    scope_query, saved_fields = FixtureOutlookCalendarBook.callback_scopes[-1]
    assert scope_query == b""
    assert saved_fields == {"state": ["single-use-fixture-state-000000000000"], "error": ["access_denied"]}
