"""Vault routes exercised through the real app, real middleware and real database.

No mocks: ``create_app`` builds the same FastAPI application the dashboard uses, and requests pass
through ``SecurityMiddleware`` (Host/origin checks, CSRF, owner authentication).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.server.app import create_app

HEADERS = {"X-Hutch-Request": "1"}
PASSPHRASE = "a-long-enough-vault-passphrase"
CANARY = "[redacted]"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:18787", follow_redirects=False) as client:
        yield client, app.state.store, app.state.vault


def create(client) -> dict:
    response = client.post("/api/v1/vault/create", json={"passphrase": PASSPHRASE}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def test_status_reports_an_uninitialised_vault(api):
    client, _store, _vault = api
    response = client.get("/api/v1/vault")
    assert response.status_code == 200
    body = response.json()
    assert body["initialized"] is False
    assert body["unlocked"] is False
    assert response.headers["cache-control"] == "no-store"


def test_create_returns_the_recovery_key_once_and_never_again(api):
    client, _store, _vault = api
    created = create(client)
    assert created["initialized"] is True and created["unlocked"] is True
    assert created["recovery_key_shown_once"] is True
    assert created["recovery_key"]

    later = client.get("/api/v1/vault").json()
    assert "recovery_key" not in later
    assert CANARY not in client.get("/api/v1/vault").text


def test_a_second_create_is_refused(api):
    client, _store, _vault = api
    create(client)
    response = client.post("/api/v1/vault/create", json={"passphrase": PASSPHRASE}, headers=HEADERS)
    assert response.status_code == 409


def test_mutations_require_the_browser_request_header(api):
    client, _store, _vault = api
    response = client.post("/api/v1/vault/create", json={"passphrase": PASSPHRASE})
    assert response.status_code == 403
    assert "browser request verification" in response.json()["detail"] or "authentication" in response.text


def test_cross_site_origin_is_refused(api):
    client, _store, _vault = api
    response = client.post("/api/v1/vault/create", json={"passphrase": PASSPHRASE},
                           headers={**HEADERS, "Origin": "http://evil.example"})
    assert response.status_code == 403
    assert "cross-site" in response.text


def test_secret_lifecycle_over_http(api):
    client, _store, _vault = api
    create(client)

    created = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "api_key", "name": "Notion", "value": CANARY,
        "description": "workspace integration"})
    assert created.status_code == 200, created.text
    meta = created.json()
    assert CANARY not in created.text
    assert meta["name"] == "Notion"

    listing = client.get("/api/v1/vault/secrets")
    assert listing.status_code == 200
    assert CANARY not in listing.text
    assert [item["id"] for item in listing.json()["secrets"]] == [meta["id"]]

    detail = client.get(f"/api/v1/vault/secrets/{meta['id']}")
    assert CANARY not in detail.text

    updated = client.put(f"/api/v1/vault/secrets/{meta['id']}", headers=HEADERS,
                         json={"value": "rotated-value"})
    assert updated.status_code == 200
    assert updated.json()["current_version"] == 2

    revealed = client.post(f"/api/v1/vault/secrets/{meta['id']}/reveal", headers=HEADERS)
    assert revealed.status_code == 200
    assert revealed.json()["value"] == "rotated-value"
    assert revealed.headers["cache-control"] == "no-store"

    deleted = client.delete(f"/api/v1/vault/secrets/{meta['id']}", headers=HEADERS)
    assert deleted.status_code == 200
    assert client.get("/api/v1/vault/secrets").json()["secrets"] == []
    assert client.post(f"/api/v1/vault/secrets/{meta['id']}/reveal", headers=HEADERS).status_code == 404


def test_lock_and_unlock_round_trip_over_http(api):
    client, _store, _vault = api
    create(client)
    meta = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "api_key", "name": "n", "value": CANARY}).json()

    assert client.post("/api/v1/vault/lock", headers=HEADERS).json()["unlocked"] is False
    blocked = client.post(f"/api/v1/vault/secrets/{meta['id']}/reveal", headers=HEADERS)
    assert blocked.status_code == 423

    wrong = client.post("/api/v1/vault/unlock", headers=HEADERS, json={"passphrase": "not-the-passphrase"})
    assert wrong.status_code == 403

    ok = client.post("/api/v1/vault/unlock", headers=HEADERS, json={"passphrase": PASSPHRASE})
    assert ok.status_code == 200 and ok.json()["unlocked"] is True
    assert client.post(f"/api/v1/vault/secrets/{meta['id']}/reveal", headers=HEADERS).json()["value"] == CANARY


def test_grants_are_managed_over_http_and_audited(api):
    client, _store, _vault = api
    create(client)
    meta = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "api_key", "name": "n", "value": CANARY}).json()

    granted = client.post(f"/api/v1/vault/secrets/{meta['id']}/grants", headers=HEADERS, json={
        "principal_kind": "bot", "principal_id": "bot_0123456789ab", "permission": "use"})
    assert granted.status_code == 200, granted.text

    detail = client.get(f"/api/v1/vault/secrets/{meta['id']}").json()
    assert detail["grants"] == [{"principal_kind": "bot", "principal_id": "bot_0123456789ab",
                                 "permission": "use", "granted_at": detail["grants"][0]["granted_at"]}]

    revoked = client.request("DELETE", f"/api/v1/vault/secrets/{meta['id']}/grants", headers=HEADERS,
                             json={"principal_kind": "bot", "principal_id": "bot_0123456789ab",
                                   "permission": "use"})
    assert revoked.status_code == 200
    assert client.get(f"/api/v1/vault/secrets/{meta['id']}").json()["grants"] == []

    actions = [entry["action"] for entry in client.get("/api/v1/vault/audit").json()["entries"]]
    assert "grant" in actions and "revoke" in actions


def test_audit_never_returns_a_value(api):
    client, _store, _vault = api
    create(client)
    meta = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "api_key", "name": "n", "value": CANARY}).json()
    client.post(f"/api/v1/vault/secrets/{meta['id']}/reveal", headers=HEADERS)
    audit = client.get("/api/v1/vault/audit")
    assert audit.status_code == 200
    assert CANARY not in audit.text
    assert any(entry["action"] == "reveal" for entry in audit.json()["entries"])


def test_unknown_fields_and_bad_categories_are_refused(api):
    client, _store, _vault = api
    create(client)
    extra = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "api_key", "name": "n", "value": "v", "surprise": 1})
    assert extra.status_code == 422
    bad_category = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "passwords", "name": "n", "value": "v"})
    assert bad_category.status_code == 422
    bad_scope = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "user:1", "category": "api_key", "name": "n", "value": "v"})
    assert bad_scope.status_code == 422


def test_the_value_never_appears_in_the_response_of_a_write(api):
    client, _store, _vault = api
    create(client)
    response = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "api_key", "name": "n", "value": CANARY})
    assert response.status_code == 200
    assert CANARY not in response.text


def test_destination_bindings_are_managed_over_http_and_listed(api):
    client, _store, _vault = api
    create(client)
    meta = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "api_key", "name": "n", "value": CANARY}).json()

    bound = client.post(f"/api/v1/vault/secrets/{meta['id']}/destinations", headers=HEADERS,
                        json={"origin": "https://api.notion.com"})
    assert bound.status_code == 200, bound.text
    assert bound.json()["origin"] == "https://api.notion.com"

    detail = client.get(f"/api/v1/vault/secrets/{meta['id']}").json()
    assert detail["destinations"] == ["https://api.notion.com"]
    assert CANARY not in client.get(f"/api/v1/vault/secrets/{meta['id']}").text

    bad = client.post(f"/api/v1/vault/secrets/{meta['id']}/destinations", headers=HEADERS,
                      json={"origin": "https://api.notion.com/v1/pages?x=1"})
    assert bad.status_code == 422

    removed = client.request("DELETE", f"/api/v1/vault/secrets/{meta['id']}/destinations",
                             headers=HEADERS, json={"origin": "https://api.notion.com"})
    assert removed.status_code == 200
    assert client.get(f"/api/v1/vault/secrets/{meta['id']}").json()["destinations"] == []

    actions = [entry["action"] for entry in client.get("/api/v1/vault/audit").json()["entries"]]
    assert "bind_destination" in actions and "unbind_destination" in actions


def test_destination_mutations_require_the_browser_request_header(api):
    client, _store, _vault = api
    create(client)
    meta = client.post("/api/v1/vault/secrets", headers=HEADERS, json={
        "scope": "workspace", "category": "api_key", "name": "n", "value": CANARY}).json()
    response = client.post(f"/api/v1/vault/secrets/{meta['id']}/destinations",
                           json={"origin": "https://api.notion.com"})
    assert response.status_code == 403


def test_the_http_surface_and_a_run_share_one_unlock_state(api):
    """Unlocking in Settings must make a mediated use possible in the run loop, not a second vault."""
    _client, store, vault = api
    from hutch.vault import vault_for
    assert vault_for(store) is vault
    assert vault.is_unlocked is False
    create(_client)
    assert vault.is_unlocked is True
    assert vault_for(store).is_unlocked is True
