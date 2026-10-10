from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from hutch.google_calendar import OAuthStart
from hutch.google_mail import GOOGLE_MAIL_SCOPE
from hutch.google_mail_send import GOOGLE_MAIL_SEND_SCOPE
from hutch.models import Bot, InferenceMode
from hutch.server.app import REMOTE_ROUTE_CAPABILITIES, create_app


ACCOUNT_ID = "gmail_0123456789abcdef01234567"
SEND_ACCOUNT_ID = "gmail_send_0123456789abcdef01234567"


class FixtureGoogleMailBook:
    callback_scopes = []
    constructed_client_ids = []
    accounts_rows = [{"id": ACCOUNT_ID, "label": "Personal Gmail", "created_at": "2026-10-09T00:00:00+00:00",
                      "scopes": [GOOGLE_MAIL_SCOPE], "status": "connected"}]

    class Secrets:
        @staticmethod
        def available():
            return True

    def __init__(self, state_dir, client_id):
        self.secrets = self.Secrets()
        self.client_id = client_id
        type(self).constructed_client_ids.append(client_id)

    def accounts(self):
        return list(self.accounts_rows)

    @classmethod
    def callback_uri(cls, request):
        cls.callback_scopes.append((request.scope.get("query_string"), request.scope.get("hutch_oauth_query")))
        if request.headers.get("host", "").startswith("127.0.0.1"):
            return "http://127.0.0.1:18787/api/v1/connections/google-mail/callback"
        from hutch.google_calendar import GoogleCalendarError
        raise GoogleCalendarError("Gmail sign-in must start and finish from Hutch on this computer at 127.0.0.1")

    def start(self, label, callback):
        return OAuthStart("https://accounts.google.com/o/oauth2/v2/auth?state=fixture", "fixture")

    def _account(self, account_id):
        from hutch.google_calendar import GoogleCalendarError
        account = next((row for row in self.accounts_rows if row["id"] == account_id), None)
        if account is None:
            raise GoogleCalendarError("Gmail account is not connected; reconnect it from Connections")
        return account

    def finish(self, state, code, callback):
        self.callback_scopes.append(("finish", state, code, callback))
        return self.accounts_rows[0]

    def cancel(self, state):
        self.callback_scopes.append(("cancel", state))

    def disconnect(self, account_id):
        return {"removed": True, "provider_revocation": "confirmed"}


class FixtureGoogleMailSendBook:
    callback_scopes = []
    accounts_rows = [{"id": SEND_ACCOUNT_ID, "label": "Work sender", "from_address": "owner@example.test",
                      "created_at": "2026-10-10T00:00:00+00:00", "scopes": [GOOGLE_MAIL_SEND_SCOPE],
                      "status": "connected"}]

    class Secrets:
        @staticmethod
        def available():
            return True

    def __init__(self, state_dir, client_id):
        self.secrets = self.Secrets()
        self.client_id = client_id

    def accounts(self):
        return list(self.accounts_rows)

    @classmethod
    def callback_uri(cls, request):
        if request.headers.get("host", "").startswith("127.0.0.1"):
            return "http://127.0.0.1:18787/api/v1/connections/google-mail-send/callback"
        from hutch.google_calendar import GoogleCalendarError
        raise GoogleCalendarError("Gmail sending sign-in must start and finish at 127.0.0.1")

    def start(self, label, callback, from_address):
        self.callback_scopes.append((label, callback, from_address))
        from urllib.parse import urlencode
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"scope": GOOGLE_MAIL_SEND_SCOPE})
        return OAuthStart(url, "fixture-send-state")

    def _account(self, account_id):
        from hutch.google_calendar import GoogleCalendarError
        account = next((row for row in self.accounts_rows if row["id"] == account_id), None)
        if account is None:
            raise GoogleCalendarError("Gmail sending account is not connected")
        return account

    def disconnect(self, account_id):
        return {"removed": True, "provider_revocation": "confirmed"}

    def finish(self, state, code, callback):
        self.callback_scopes.append(("finish", state, code, callback))
        return self.accounts_rows[0]

    def cancel(self, state):
        self.callback_scopes.append(("cancel", state))


def test_gmail_connection_and_grant_require_local_inference_and_are_revocable(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "fixture-desktop-client.apps.googleusercontent.com")
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:18787") as client:
        monkeypatch.setattr("hutch.google_mail.GoogleMailBook", FixtureGoogleMailBook)
        local = client.app.state.store.create_bot(Bot(name="local-mail-reviewer", display_name="Mail Reviewer",
            model="ollama/qwen3:4b", inference_mode=InferenceMode.local, tools=[]))
        hybrid = client.app.state.store.create_bot(Bot(name="hybrid-mail-reviewer", model="mock/demo", tools=[]))
        remote_local = client.app.state.store.create_bot(Bot(name="remote-local-mail-reviewer", model="ollama/qwen3:4b",
            inference_mode=InferenceMode.local, base_url="https://models.example.test/v1", tools=[]))

        resource = client.get("/api/v1/connections/google-mail")
        assert resource.status_code == 200
        assert resource.json() == {"configured": True, "secret_store_available": True,
                                   "accounts": FixtureGoogleMailBook.accounts_rows, "grants": []}
        assert client.get("/api/connections").json()["google_mail"]["accounts"][0]["label"] == "Personal Gmail"

        start = client.post("/api/v1/connections/google-mail/sign-in", json={"label": "Personal Gmail"})
        assert start.status_code == 200, start.text
        assert start.headers["cache-control"] == "no-store"
        assert start.headers["referrer-policy"] == "no-referrer"
        assert urlsplit(start.json()["authorization_url"]).hostname == "accounts.google.com"

        blocked = client.post("/api/v1/connections/google-mail/grants", json={"bot": hybrid.id,
            "account_id": ACCOUNT_ID})
        assert blocked.status_code == 409
        assert "Local inference" in blocked.text and "hosted routes" in blocked.text
        remote_blocked = client.post("/api/v1/connections/google-mail/grants", json={"bot": remote_local.id,
            "account_id": ACCOUNT_ID})
        assert remote_blocked.status_code == 409
        assert "loopback-only Local model endpoints" in remote_blocked.text
        granted = client.post("/api/v1/connections/google-mail/grants", json={"bot": local.id,
            "account_id": ACCOUNT_ID})
        assert granted.status_code == 200, granted.text
        assert granted.json()["grant"]["account_id"] == ACCOUNT_ID
        assert "sender, subject, date" in granted.json()["detail"]
        assert "loopback endpoint" in granted.json()["detail"]
        assert "Hybrid and hosted routes are blocked" in granted.json()["detail"]
        assert "account-wide" in granted.json()["detail"]
        assert client.app.state.store.google_mail_grant(local.id)["account_id"] == ACCOUNT_ID

        removed = client.delete(f"/api/v1/connections/google-mail/grants/{local.id}")
        assert removed.status_code == 200 and removed.json() == {"removed": True}
        client.app.state.store.set_google_mail_grant(local.id, ACCOUNT_ID)
        disconnected = client.post(f"/api/v1/connections/google-mail/accounts/{ACCOUNT_ID}/disconnect", json={})
        assert disconnected.status_code == 200
        assert disconnected.json()["provider_revocation"] == "confirmed"
        assert client.app.state.store.list_google_mail_grants() == []


def test_google_oauth_client_setup_is_local_persisted_and_environment_managed(tmp_path, monkeypatch):
    assert REMOTE_ROUTE_CAPABILITIES.get(("GET", "/api/v1/connections/google-oauth-client")) is None
    assert REMOTE_ROUTE_CAPABILITIES.get(("PUT", "/api/v1/connections/google-oauth-client")) is None
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", raising=False)
    FixtureGoogleMailBook.constructed_client_ids = []
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:18787") as client:
        monkeypatch.setattr("hutch.google_mail.GoogleMailBook", FixtureGoogleMailBook)
        initial = client.get("/api/v1/connections/google-oauth-client")
        assert initial.status_code == 200
        assert initial.json() == {
            "client_id": "", "source": "unset", "editable": True, "configured": False,
            "valid": False,
            "detail": "Enter a Google Desktop OAuth client ID ending in .apps.googleusercontent.com.",
        }
        invalid = client.put("/api/v1/connections/google-oauth-client", json={"client_id": "not-a-client"})
        assert invalid.status_code == 422

        saved = client.put("/api/v1/connections/google-oauth-client", json={
            "client_id": "local-preview.apps.googleusercontent.com"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["source"] == "hutch" and saved.json()["editable"] and saved.json()["configured"]
        assert client.get("/api/connections").json()["google_oauth_client"] == saved.json()

        start = client.post("/api/v1/connections/google-mail/sign-in", json={"label": "Personal Gmail"})
        assert start.status_code == 200, start.text
        assert FixtureGoogleMailBook.constructed_client_ids
        assert set(FixtureGoogleMailBook.constructed_client_ids) == {"local-preview.apps.googleusercontent.com"}

        monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "invalid-operator-value")
        malformed_override = client.get("/api/v1/connections/google-oauth-client").json()
        assert malformed_override["source"] == "environment" and not malformed_override["valid"]
        assert client.get("/api/v1/connections/google-calendar").json()["configured"] is False
        assert client.get("/api/v1/connections/google-mail").json()["configured"] is False

        monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "operator.apps.googleusercontent.com")
        overridden = client.get("/api/v1/connections/google-oauth-client").json()
        assert overridden["client_id"] == "operator.apps.googleusercontent.com"
        assert overridden["source"] == "environment" and not overridden["editable"]
        assert client.put("/api/v1/connections/google-oauth-client", json={
            "client_id": "another.apps.googleusercontent.com"}).status_code == 409
        assert client.delete("/api/v1/connections/google-oauth-client").status_code == 409

    monkeypatch.delenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", raising=False)
    reopened = create_app()
    with TestClient(reopened, base_url="http://127.0.0.1:18787") as client:
        assert client.get("/api/v1/connections/google-oauth-client").json()["client_id"] == \
            "local-preview.apps.googleusercontent.com"


def test_gmail_callback_strips_authorization_code_from_access_log_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "fixture-desktop-client.apps.googleusercontent.com")
    FixtureGoogleMailBook.callback_scopes.clear()
    with TestClient(create_app(), base_url="http://127.0.0.1:18787", follow_redirects=False) as client:
        monkeypatch.setattr("hutch.google_mail.GoogleMailBook", FixtureGoogleMailBook)
        response = client.get("/api/v1/connections/google-mail/callback?state=one-time-state&code=one-time-code")
    assert response.status_code == 303
    assert response.headers["location"].endswith("google_mail_result=connected#/connections")
    scope_query, values = FixtureGoogleMailBook.callback_scopes[0]
    assert scope_query == b""
    assert values == {"state": ["one-time-state"], "code": ["one-time-code"]}
    assert FixtureGoogleMailBook.callback_scopes[1][0:3] == ("finish", "one-time-state", "one-time-code")


def test_gmail_send_connection_has_a_separate_authorization_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "fixture-desktop-client.apps.googleusercontent.com")
    with TestClient(create_app(), base_url="http://127.0.0.1:18787") as client:
        monkeypatch.setattr("hutch.google_mail_send.GoogleMailSendBook", FixtureGoogleMailSendBook)
        response = client.post("/api/v1/connections/google-mail-send/sign-in", json={
            "label": "Work sender", "from_address": "owner@example.test"})

    assert response.status_code == 200, response.text
    assert urlsplit(response.json()["authorization_url"]).hostname == "accounts.google.com"
    assert response.headers["cache-control"] == "no-store"
    assert parse_qs(urlsplit(response.json()["authorization_url"]).query)["scope"] == [GOOGLE_MAIL_SEND_SCOPE]


def test_gmail_send_connection_and_grants_are_separate_from_read_access(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "fixture-desktop-client.apps.googleusercontent.com")
    FixtureGoogleMailSendBook.callback_scopes.clear()
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:18787") as client:
        monkeypatch.setattr("hutch.google_mail_send.GoogleMailSendBook", FixtureGoogleMailSendBook)
        bot = client.app.state.store.create_bot(Bot(name="mail-sender", model="mock/demo", tools=[]))
        client.app.state.store.set_google_mail_grant(bot.id, ACCOUNT_ID)

        resource = client.get("/api/v1/connections/google-mail-send")
        assert resource.status_code == 200
        assert resource.json()["accounts"] == FixtureGoogleMailSendBook.accounts_rows
        assert resource.json()["grants"] == []
        assert client.get("/api/connections").json()["google_mail_send"]["accounts"] == \
            FixtureGoogleMailSendBook.accounts_rows

        sign_in = client.post("/api/v1/connections/google-mail-send/sign-in", json={
            "label": "Work sender", "from_address": "owner@example.test"})
        assert sign_in.status_code == 200, sign_in.text
        assert sign_in.headers["cache-control"] == "no-store"
        assert FixtureGoogleMailSendBook.callback_scopes == [
            ("Work sender", "http://127.0.0.1:18787/api/v1/connections/google-mail-send/callback",
             "owner@example.test")]

        grant = client.post("/api/v1/connections/google-mail-send/grants", json={
            "bot": bot.id, "account_id": SEND_ACCOUNT_ID})
        assert grant.status_code == 200, grant.text
        assert "Every message" in grant.json()["detail"]
        assert "does not confirm delivery" in grant.json()["detail"]
        assert client.app.state.store.google_mail_send_grant(bot.id)["account_id"] == SEND_ACCOUNT_ID
        assert client.app.state.store.google_mail_grant(bot.id)["account_id"] == ACCOUNT_ID

        removed = client.delete(f"/api/v1/connections/google-mail-send/grants/{bot.id}")
        assert removed.status_code == 200 and removed.json() == {"removed": True}
        client.app.state.store.set_google_mail_send_grant(bot.id, SEND_ACCOUNT_ID, "Work sender")
        disconnected = client.post(f"/api/v1/connections/google-mail-send/accounts/{SEND_ACCOUNT_ID}/disconnect", json={})
        assert disconnected.status_code == 200
        assert client.app.state.store.google_mail_send_grant(bot.id) is None
        assert client.app.state.store.google_mail_grant(bot.id)["account_id"] == ACCOUNT_ID


def test_gmail_denied_callback_consumes_state_without_echoing_provider_error(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "fixture-desktop-client.apps.googleusercontent.com")
    FixtureGoogleMailBook.callback_scopes.clear()
    with TestClient(create_app(), base_url="http://127.0.0.1:18787", follow_redirects=False) as client:
        monkeypatch.setattr("hutch.google_mail.GoogleMailBook", FixtureGoogleMailBook)
        response = client.get("/api/v1/connections/google-mail/callback?state=one-time-state&error=access_denied")
    values = parse_qs(urlsplit(response.headers["location"]).query)
    assert response.status_code == 303
    assert values["google_mail_result"] == ["error"]
    assert values["detail"] == ["Gmail access was not granted; no account was connected"]
    assert "access_denied" not in response.headers["location"]
    assert FixtureGoogleMailBook.callback_scopes[-1] == ("cancel", "one-time-state")
