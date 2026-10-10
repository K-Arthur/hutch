from __future__ import annotations

from fastapi.testclient import TestClient

from hutch.google_calendar import OAuthStart
from hutch.server.app import create_app


class FakeOutlookCalendarWriteBook:
    account_id = "mscalw_0123456789abcdef01234567"
    accounts_rows = [{"id": account_id, "label": "Work events", "status": "connected",
                      "created_at": "2026-10-10T00:00:00+00:00", "scopes": ["Calendars.ReadWrite"]}]
    callback_fields = []

    class _Secrets:
        def available(self):
            return True

    def __init__(self, state_dir, client_id):
        self.state_dir = state_dir
        self.client_id = client_id
        self.secrets = self._Secrets()

    @staticmethod
    def callback_uri(request):
        if request.headers.get("host", "").startswith("127.0.0.1"):
            return "http://localhost:18787/api/v1/connections/outlook-calendar-write/callback"
        from hutch.outlook_calendar import OutlookCalendarError
        raise OutlookCalendarError("Outlook sign-in must start from loopback")

    def start(self, label, callback):
        FakeOutlookCalendarWriteBook.callback_fields.append((label, callback))
        return OAuthStart("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?scope=Calendars.ReadWrite", "state")

    def accounts(self):
        return list(self.accounts_rows)

    def list_calendars(self, account_id):
        if account_id != self.account_id:
            from hutch.outlook_calendar import OutlookCalendarError
            raise OutlookCalendarError("No event-creation account")
        return [{"id": "calendar-1", "name": "Work", "primary": True}]

    def finish(self, state, code, callback):
        self.callback_fields.append((state, code, callback))
        return self.accounts_rows[0]

    def cancel(self, state):
        self.callback_fields.append((state, "cancelled", ""))

    def disconnect(self, account_id):
        return {"removed": account_id == self.account_id, "provider_revocation": "unavailable"}


def test_outlook_calendar_write_api_keeps_write_account_separate_and_revocable(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "microsoft-public-client")
    monkeypatch.setattr("hutch.outlook_calendar_write.OutlookCalendarWriteBook", FakeOutlookCalendarWriteBook)
    FakeOutlookCalendarWriteBook.callback_fields.clear()
    with TestClient(create_app(), base_url="http://127.0.0.1:18787", follow_redirects=False) as client:
        resources = client.get("/api/v1/connections/outlook-calendar-write")
        assert resources.status_code == 200 and resources.json()["accounts"][0]["id"].startswith("mscalw_")
        assert resources.json()["grants"] == []

        sign_in = client.post("/api/v1/connections/outlook-calendar-write/sign-in", json={"label": "Work events"})
        assert sign_in.status_code == 200
        assert sign_in.headers["cache-control"] == "no-store"
        assert sign_in.headers["referrer-policy"] == "no-referrer"
        assert "Calendars.ReadWrite" in sign_in.json()["authorization_url"]
        assert FakeOutlookCalendarWriteBook.callback_fields[-1] == (
            "Work events", "http://localhost:18787/api/v1/connections/outlook-calendar-write/callback")

        bot = client.post("/api/bots", json={"name": "outlook-event-helper", "model": "mock/demo", "tools": []}).json()
        bad = client.post("/api/v1/connections/outlook-calendar-write/grants", json={
            "bot": bot["id"], "account_id": FakeOutlookCalendarWriteBook.account_id, "calendar_id": "forged"})
        assert bad.status_code == 422
        grant = client.post("/api/v1/connections/outlook-calendar-write/grants", json={
            "bot": bot["id"], "account_id": FakeOutlookCalendarWriteBook.account_id, "calendar_id": "calendar-1"})
        assert grant.status_code == 200
        assert grant.json()["grant"]["calendar_name"] == "Work"
        assert "create a guest-free event" in grant.json()["detail"]
        assert "changing, and deleting" in grant.json()["detail"]
        assert client.get("/api/v1/connections/outlook-calendar-write").json()["grants"][0]["bot_name"] == bot["name"]

        removed = client.delete(f"/api/v1/connections/outlook-calendar-write/grants/{bot['id']}")
        assert removed.status_code == 200 and removed.json()["removed"] is True
        assert client.app.state.store.outlook_calendar_write_grant(bot["id"]) is None

        deleted = client.post(f"/api/v1/connections/outlook-calendar-write/accounts/{FakeOutlookCalendarWriteBook.account_id}/disconnect")
        assert deleted.status_code == 200 and deleted.json()["provider_revocation"] == "unavailable"
        assert "revoke the provider permission" in deleted.json()["detail"]

        callback = client.get("/api/v1/connections/outlook-calendar-write/callback?state=one-time&code=auth-code")
        assert callback.status_code == 303
        assert callback.headers["location"].endswith("outlook_calendar_write_result=connected#/connections")
    assert FakeOutlookCalendarWriteBook.callback_fields[-1][0:2] == ("one-time", "auth-code")
