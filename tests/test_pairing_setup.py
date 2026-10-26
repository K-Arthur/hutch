"""Host-side phone setup never widens the paired device's administration rights."""
import json
from fastapi.testclient import TestClient

from hutch.server.app import create_app, REMOTE_ROUTE_CAPABILITIES
from hutch.server.security import SESSION_COOKIE
from tests.test_remote_pairing import _enroll_test_passkey, _phone_headers


def configure(monkeypatch, tmp_path):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_REMOTE_ENABLED", "1")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_RP_ID", "hutch.example")
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example")


def test_pairing_setup_requires_explicit_private_access_and_canonical_passkey_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("HUTCH_REMOTE_ENABLED", raising=False)
    with TestClient(create_app(), base_url="http://127.0.0.1:18787") as client:
        assert not client.get("/api/v1/pairing/setup").json()["ready"]
        assert client.post("/api/v1/pairing/codes", json={}).status_code == 409
        assert not client.app.state.store._db.execute("SELECT 1 FROM pairing_codes").fetchall()
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "http://hutch.example")
    with TestClient(create_app(), base_url="http://127.0.0.1:18787") as client:
        assert not client.get("/api/v1/pairing/setup").json()["ready"]
        assert client.post("/api/v1/pairing/codes", json={}).status_code == 409
    monkeypatch.setenv("HUTCH_WEBAUTHN_ORIGIN", "https://hutch.example")
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "other.example")
    with TestClient(create_app(), base_url="http://127.0.0.1:18787") as client:
        assert not client.get("/api/v1/pairing/setup").json()["ready"]


def test_host_creates_one_use_code_with_review_only_default_and_explicit_start(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)
    with TestClient(create_app(), base_url="http://127.0.0.1:18787") as client:
        setup = client.get("/api/v1/pairing/setup")
        assert setup.json()["pair_url"] == "https://hutch.example/pair"
        assert setup.headers["cache-control"] == "no-store"
        response = client.post("/api/v1/pairing/codes", json={})
        assert response.status_code == 200
        result = response.json()
        assert result["capabilities"] == ["monitor", "review"]
        assert result["expires_in_seconds"] == 60
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert result["code"] not in result["pair_url"]
        store = client.app.state.store
        row = store._db.execute("SELECT * FROM pairing_codes").fetchone()
        assert result["code"].replace("-", "") not in json.dumps(dict(row))
        enrollment, outcome = store.exchange_pairing_code(result["code"], "Phone", "fixture")
        assert outcome == "ok" and enrollment
        assert store.exchange_pairing_code(result["code"], "Phone", "fixture")[0] is None
        start = client.post("/api/v1/pairing/codes", json={"allow_start": True}).json()
        assert start["capabilities"] == ["monitor", "review", "start"]
        assert client.post("/api/v1/pairing/codes", json={"admin": True}).status_code == 422


def test_paired_phone_cannot_read_setup_or_issue_codes(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)
    app = create_app()
    phone = _enroll_test_passkey(app.state.store, app.state.store.create_pairing_code())
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(SESSION_COOKIE, phone["session_token"])
        assert client.get("/api/v1/pairing/setup", headers=_phone_headers()).status_code == 403
        assert client.post("/api/v1/pairing/codes", json={}, headers=_phone_headers()).status_code == 403
    assert REMOTE_ROUTE_CAPABILITIES[("GET", "/api/v1/pairing/setup")] is None
    assert REMOTE_ROUTE_CAPABILITIES[("POST", "/api/v1/pairing/codes")] is None
