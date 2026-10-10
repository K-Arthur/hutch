from __future__ import annotations

from fastapi.testclient import TestClient

from hutch.google_calendar import OAuthStart
from hutch.server.app import create_app


class FakeGoogleCalendarBook:
    accounts_rows = [{"id": "gcal_0123456789abcdef01234567", "label": "Personal", "status": "connected",
                      "created_at": "2026-10-09T00:00:00+00:00", "scopes": ["calendar.events.readonly"]}]
    calendars = [{"id": "primary", "name": "Primary", "primary": True, "access_role": "owner"}]

    class _Secrets:
        def available(self):
            return True

    callback_scopes = []
    finish_calls = []
    sign_in_calls = []
    can_write = False

    def __init__(self, state_dir, client_id):
        self.secrets = self._Secrets()
        self.client_id = client_id

    def accounts(self):
        return list(self.accounts_rows)

    @staticmethod
    def callback_uri(request):
        FakeGoogleCalendarBook.callback_scopes.append((request.scope.get("query_string"),
                                                       request.scope.get("hutch_oauth_query")))
        if request.headers.get("host", "").startswith("127.0.0.1"):
            return "http://127.0.0.1:18787/api/v1/connections/google-calendar/callback"
        from hutch.google_calendar import GoogleCalendarError
        raise GoogleCalendarError("Google Calendar sign-in must start and finish from Hutch on this computer at 127.0.0.1")

    def start(self, label, callback, *, allow_event_creation=False):
        self.sign_in_calls.append((label, allow_event_creation))
        return OAuthStart("https://accounts.google.com/o/oauth2/v2/auth?state=test", "test")

    def finish(self, state, code, callback):
        self.finish_calls.append((state, code, callback))
        return {"id": "gcal_0123456789abcdef01234567", "label": "Work", "status": "connected"}

    def cancel(self, state):
        self.finish_calls.append((state, "cancelled", ""))

    def list_calendars(self, account_id):
        return self.calendars

    def can_create_events(self, account_id):
        return self.can_write

    @staticmethod
    def account_can_create_events(account):
        return bool(account.get("can_create_events"))

    def disconnect(self, account_id):
        return {"removed": True, "provider_revocation": "not_confirmed"}


def test_connections_api_exposes_calendar_readiness_but_never_token_values(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "public-client.apps.googleusercontent.com")
    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FakeGoogleCalendarBook)
    with TestClient(create_app()) as client:
        response = client.get("/api/connections")
        assert response.status_code == 200
        data = response.json()["google_calendar"]
        assert data["configured"] is True
        assert data["secret_store_available"] is True
        assert data["accounts"][0]["label"] == "Personal"
        assert data["accounts"][0]["can_create_events"] is False
        assert "refresh_token" not in response.text and "access_token" not in response.text
        resource = client.get("/api/v1/connections/google-calendar")
        assert resource.status_code == 200
        assert resource.json()["accounts"][0]["id"] == data["accounts"][0]["id"]
        assert resource.json()["accounts"][0]["can_create_events"] is False


def test_calendar_sign_in_only_starts_from_local_hutch_host(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "public-client.apps.googleusercontent.com")
    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FakeGoogleCalendarBook)
    with TestClient(create_app(), base_url="http://127.0.0.1:18787") as client:
        response = client.post("/api/v1/connections/google-calendar/sign-in", json={"label": "Work"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.json()["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    with TestClient(create_app()) as remote:
        rejected = remote.post("/api/v1/connections/google-calendar/sign-in", json={"label": "Work"})
        assert rejected.status_code == 409 and "127.0.0.1" in rejected.text


def test_calendar_write_sign_in_is_separate_and_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "public-client.apps.googleusercontent.com")
    FakeGoogleCalendarBook.sign_in_calls.clear()
    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FakeGoogleCalendarBook)
    with TestClient(create_app(), base_url="http://127.0.0.1:18787") as client:
        read = client.post("/api/v1/connections/google-calendar/sign-in", json={"label": "Read only"})
        write = client.post("/api/v1/connections/google-calendar/sign-in", json={"label": "Create events",
                                                                                 "allow_event_creation": True})
    assert read.status_code == 200 and write.status_code == 200
    assert FakeGoogleCalendarBook.sign_in_calls[-2:] == [("Read only", False), ("Create events", True)]


def test_oauth_callback_keeps_code_out_of_the_asgi_query_string(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "public-client.apps.googleusercontent.com")
    FakeGoogleCalendarBook.callback_scopes.clear()
    FakeGoogleCalendarBook.finish_calls.clear()
    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FakeGoogleCalendarBook)
    with TestClient(create_app(), base_url="http://127.0.0.1:18787", follow_redirects=False) as client:
        response = client.get("/api/v1/connections/google-calendar/callback?state=one-time-state&code=one-time-code")
        assert response.status_code == 303
        assert response.headers["location"].endswith("google_calendar_result=connected#/connections")
    scope_query, saved_fields = FakeGoogleCalendarBook.callback_scopes[-1]
    assert scope_query == b""
    assert saved_fields == {"state": ["one-time-state"], "code": ["one-time-code"]}
    assert FakeGoogleCalendarBook.finish_calls[-1][0:2] == ("one-time-state", "one-time-code")


def test_calendar_grant_must_choose_connected_calendar_and_disconnect_revokes_bot_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "public-client.apps.googleusercontent.com")
    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FakeGoogleCalendarBook)
    with TestClient(create_app()) as client:
        bot = client.post("/api/bots", json={"name": "calendar-helper", "model": "mock/demo", "tools": []})
        assert bot.status_code == 201, bot.text
        bot_id = bot.json()["id"]
        bad = client.post("/api/v1/connections/google-calendar/grants", json={"bot": bot_id,
            "account_id": "gcal_0123456789abcdef01234567", "calendar_id": "forged-calendar"})
        assert bad.status_code == 422
        granted = client.post("/api/v1/connections/google-calendar/grants", json={"bot": bot_id,
            "account_id": "gcal_0123456789abcdef01234567", "calendar_id": "primary"})
        assert granted.status_code == 200, granted.text
        assert granted.json()["grant"]["calendar_name"] == "Primary"
        detail = granted.json()["detail"]
        assert "read events" in detail and "sent to the selected model" in detail
        assert "run history" in detail and "Descriptions and attendee details" in detail
        assert client.get("/api/connections").json()["google_calendar"]["grants"][0]["bot_name"] == "calendar-helper"
        resource = client.get("/api/v1/connections/google-calendar")
        assert resource.status_code == 200
        assert resource.json()["grants"][0]["allow_event_creation"] is False
        disconnected = client.post("/api/v1/connections/google-calendar/accounts/gcal_0123456789abcdef01234567/disconnect")
        assert disconnected.status_code == 200
        assert disconnected.json()["removed"] is True
        assert client.app.state.store.google_calendar_grant(bot_id) is None
        assert "did not confirm remote revocation" in disconnected.json()["detail"]


def test_calendar_event_creation_grant_requires_account_scope_and_writable_calendar(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "public-client.apps.googleusercontent.com")
    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook", FakeGoogleCalendarBook)
    monkeypatch.setattr(FakeGoogleCalendarBook, "can_write", False)
    monkeypatch.setattr(FakeGoogleCalendarBook, "calendars", [{"id": "primary", "name": "Primary", "primary": True,
                                                               "access_role": "owner"}])
    with TestClient(create_app()) as client:
        bot = client.post("/api/bots", json={"name": "calendar-helper", "model": "mock/demo", "tools": []}).json()
        body = {"bot": bot["id"], "account_id": "gcal_0123456789abcdef01234567", "calendar_id": "primary",
                "allow_event_creation": True}
        denied_scope = client.post("/api/v1/connections/google-calendar/grants", json=body)
        assert denied_scope.status_code == 422 and "Reconnect" in denied_scope.text

        FakeGoogleCalendarBook.can_write = True
        FakeGoogleCalendarBook.calendars = [{"id": "primary", "name": "Primary", "primary": True,
                                             "access_role": "reader"}]
        denied_role = client.post("/api/v1/connections/google-calendar/grants", json=body)
        assert denied_role.status_code == 422 and "calendars you own" in denied_role.text

        FakeGoogleCalendarBook.calendars = [{"id": "primary", "name": "Primary", "primary": True,
                                             "access_role": "writer"}]
        denied_writer = client.post("/api/v1/connections/google-calendar/grants", json=body)
        assert denied_writer.status_code == 422 and "calendars you own" in denied_writer.text

        FakeGoogleCalendarBook.calendars = [{"id": "primary", "name": "Primary", "primary": True,
                                             "access_role": "owner"}]
        granted = client.post("/api/v1/connections/google-calendar/grants", json=body)
        assert granted.status_code == 200, granted.text
        assert granted.json()["grant"]["allow_event_creation"] is True
        assert "Each creation" in granted.json()["detail"]
        assert "edit, delete" in granted.json()["detail"]

        read_only = client.post("/api/v1/connections/google-calendar/grants", json={**body,
                                                                                     "allow_event_creation": False})
        assert read_only.status_code == 200
        assert read_only.json()["grant"]["allow_event_creation"] is False
        assert "account-level scope also permits changing and deleting" in read_only.json()["detail"]
        assert "this Bot's Hutch grant remains read-only" in read_only.json()["detail"]
