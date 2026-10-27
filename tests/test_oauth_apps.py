"""Publisher application setup belongs to builds; users only authorize accounts."""
import json
from urllib.parse import parse_qs, urlsplit
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hutch import oauth_apps
from hutch.google_oauth_config import GOOGLE_OAUTH_CLIENT_ID_KEY, resolve_google_oauth_client_id
from hutch.server.app import create_app
from tests.test_google_calendar import MemorySecrets

GOOGLE = "hutch-public.apps.googleusercontent.com"
MICROSOFT = "01234567-89ab-cdef-0123-456789abcdef"


@pytest.fixture
def publisher_apps(tmp_path, monkeypatch):
    package = tmp_path / "package"
    (package / "data").mkdir(parents=True)
    (package / "data/oauth-apps.json").write_text(json.dumps({"version": 1, "apps": {
        "google": {"client_id": GOOGLE}, "microsoft": {"client_id": MICROSOFT}}}))
    monkeypatch.setattr(oauth_apps, "resources", SimpleNamespace(files=lambda name: package))
    monkeypatch.delenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", raising=False)
    return package


@pytest.mark.parametrize("value", [
    {"version": True, "apps": {}}, {"version": 2, "apps": {}},
    {"version": 1, "apps": {"other": {"client_id": ""}}},
    {"version": 1, "apps": {"google": {"client_id": GOOGLE, "client_secret": "SENTINEL"}}},
    {"version": 1, "apps": {"google": {"client_id": "https://example.test"}}},
    {"version": 1, "apps": {"microsoft": {"client_id": GOOGLE}}},
    {"version": 1, "apps": {"google": {"client_id": None}}},
])
def test_release_input_rejects_unsupported_or_secret_fields(value):
    with pytest.raises(ValueError) as error:
        oauth_apps.validate_oauth_apps(json.dumps(value).encode())
    assert "SENTINEL" not in str(error.value)


def test_release_input_is_bounded_and_can_require_registrations():
    empty = b'{"version":1,"apps":{}}'
    assert oauth_apps.validate_oauth_apps(empty)["apps"] == {}
    with pytest.raises(ValueError, match="publisher's google"):
        oauth_apps.validate_oauth_apps(empty, required=("google",))
    with pytest.raises(ValueError, match="16 KiB"):
        oauth_apps.validate_oauth_apps(b" " * (oauth_apps.MAX_CONFIG_BYTES + 1))
    with pytest.raises(ValueError, match="JSON"):
        oauth_apps.validate_oauth_apps(b"not json")


def test_google_registration_precedence_and_reset_return_to_build_default(publisher_apps, tmp_path, monkeypatch):
    from hutch.store import Store
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    store = Store()
    try:
        assert resolve_google_oauth_client_id(store) == (GOOGLE, "distribution")
        store.kv_set(GOOGLE_OAUTH_CLIENT_ID_KEY, "custom.apps.googleusercontent.com")
        assert resolve_google_oauth_client_id(store) == ("custom.apps.googleusercontent.com", "hutch")
        monkeypatch.setenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", "operator.apps.googleusercontent.com")
        assert resolve_google_oauth_client_id(store) == ("operator.apps.googleusercontent.com", "environment")
        monkeypatch.delenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID")
        store.kv_set(GOOGLE_OAUTH_CLIENT_ID_KEY, "")
        assert resolve_google_oauth_client_id(store) == (GOOGLE, "distribution")
        (publisher_apps / "data/oauth-apps.json").write_text('{"version":1,"apps":{"google":{"client_secret":"SENTINEL"}}}')
        assert resolve_google_oauth_client_id(store) == ("", "unset")
    finally:
        store.close()


def test_publisher_google_connect_needs_no_nickname_and_keeps_pkce_and_read_scope(publisher_apps, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr("hutch.google_calendar.SecretToolStore.available", lambda *_: False)
    monkeypatch.setattr("hutch.google_calendar.GoogleCalendarBook.secret_store_type", MemorySecrets)
    with TestClient(create_app(), base_url="http://127.0.0.1:18787") as client:
        settings = client.get("/api/v1/connections/google-oauth-client").json()
        assert settings["configured"] and settings["source"] == "distribution"
        response = client.post("/api/v1/connections/google-calendar/sign-in", json={})
        assert response.status_code == 200, response.text
        query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
        assert query["client_id"] == [GOOGLE]
        assert query["code_challenge_method"] == ["S256"]
        assert query["redirect_uri"] == ["http://127.0.0.1:18787/api/v1/connections/google-calendar/callback"]
        assert all(scope.endswith("readonly") for scope in query["scope"][0].split())
        assert client.app.state.store.google_calendar_grant("not-granted") is None
        assert client.post("/api/v1/connections/google-calendar/sign-in", json={"label": ""}).status_code == 422
        assert response.headers["cache-control"] == "no-store"


def test_microsoft_worker_uses_same_build_registration_as_server(publisher_apps, tmp_path, monkeypatch):
    from hutch.outlook_calendar import OutlookCalendarBook
    from hutch.outlook_mail import OutlookMailBook
    for cls in (OutlookCalendarBook, OutlookMailBook):
        book = cls(tmp_path, "", secrets_store=MemorySecrets())
        assert book.client_id == MICROSOFT
    monkeypatch.setenv("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", "operator-registration")
    assert OutlookCalendarBook(tmp_path, "", secrets_store=MemorySecrets()).client_id == "operator-registration"
    assert OutlookCalendarBook(tmp_path, "explicit", secrets_store=MemorySecrets()).client_id == "explicit"
