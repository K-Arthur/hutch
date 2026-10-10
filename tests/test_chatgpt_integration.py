from __future__ import annotations

import base64
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from hutch.chatgpt_auth import AUTH_ORIGIN, PLAN_SCOPE, RESOURCE, ChatGPTAuthBook
from hutch.server.app import create_app


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def test_local_chatgpt_signin_callback_creates_a_secret_free_connection_api(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_ENABLE_CHATGPT_PLAN", "1")
    app = create_app()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = time.time()
    requests: list[str] = []
    nonce: list[str] = [""]

    def jwt(claims):
        header = b64url(json.dumps({"alg": "RS256", "kid": "fixture-key"}, separators=(",", ":")).encode())
        body = b64url(json.dumps(claims, separators=(",", ":")).encode())
        signing_input = f"{header}.{body}".encode("ascii")
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{body}.{b64url(signature)}"

    numbers = private_key.public_key().public_numbers()
    key = {"kty": "RSA", "kid": "fixture-key", "use": "sig",
           "n": b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
           "e": b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big"))}

    def handler(request):
        requests.append(str(request.url))
        if request.url == httpx.URL(AUTH_ORIGIN + "/api/accounts/oauth/token"):
            form = parse_qs(request.content.decode())
            assert form["resource"] == [RESOURCE]
            assert "client_secret" not in form
            claims = {"iss": AUTH_ORIGIN, "aud": form["client_id"][0], "sub": "integration-account",
                      "email": "operator@example.test", "email_verified": True,
                      "nonce": nonce[0], "iat": now, "exp": now + 3600}
            return httpx.Response(200, json={"access_token": "fixture-access-secret",
                                             "refresh_token": "fixture-refresh-secret",
                                             "id_token": jwt(claims), "expires_in": 3600,
                                             "token_type": "Bearer",
                                             "scope": f"openid profile email offline_access resource.invoke {PLAN_SCOPE}"})
        if request.url == httpx.URL(AUTH_ORIGIN + "/.well-known/openid-configuration"):
            return httpx.Response(200, json={"issuer": AUTH_ORIGIN,
                "jwks_uri": AUTH_ORIGIN + "/.well-known/jwks.json"})
        if request.url == httpx.URL(AUTH_ORIGIN + "/.well-known/jwks.json"):
            return httpx.Response(200, json={"keys": [key]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(ChatGPTAuthBook, "_http", lambda _self: httpx.Client(
        timeout=httpx.Timeout(20), trust_env=False, follow_redirects=False, transport=transport))

    with TestClient(app, base_url="http://127.0.0.1") as client:
        started = client.post("/api/chatgpt/sign-in", json={})
        assert started.status_code == 200, started.text
        authorization_url = started.json()["authorization_url"]
        params = parse_qs(urlsplit(authorization_url).query)
        pending = json.loads(next((tmp_path / "state/chatgpt/pending").glob("*.json")).read_text())
        nonce[0] = pending["nonce"]

        callback = client.get("/auth/callback", params={"state": params["state"][0],
            "code": "fixture-code", "client_id": "oaiapp_integration"}, follow_redirects=False)
        assert callback.status_code == 303
        assert callback.headers["location"].startswith("/?chatgpt_result=connected#/connections")
        assert "fixture-code" not in callback.headers["location"]
        assert "state" not in callback.headers["location"]
        assert callback.headers["cache-control"] == "no-store"
        assert callback.headers["referrer-policy"] == "no-referrer"

        listing = client.get("/api/connections").json()
        assert listing["chatgpt_enabled"] is True
        assert "chatgpt-plan" not in {row["key"] for row in listing["templates"]}
        assert listing["chatgpt_accounts"][0]["email"] == "operator@example.test"
        assert listing["chatgpt_accounts"][0]["plan_usage"] is True
        connection = listing["connections"][0]
        assert connection["auth_type"] == "chatgpt-siws"
        assert connection["protocol"] == "openai-responses"
        assert connection["has_key"] is True
        assert connection["output_token_limit_enforced"] is False
        assert client.post(f"/api/connections/{connection['name']}/set-key", json={"key": "not-an-api-key"}).status_code == 422
        assert client.post(f"/api/connections/{connection['name']}/clear-key", json={}).status_code == 422
        page = client.get("/legacy/connections")
        csrf = re.search(r'<meta name="csrf" content="([^"]+)"', page.text).group(1)
        page_set_key = client.post(f"/connections/{connection['name']}/key",
                                   data={"csrf": csrf, "key": "not-an-api-key"}, follow_redirects=False)
        assert page_set_key.status_code == 303
        from hutch.connections import ConnectionBook
        assert not ConnectionBook(tmp_path / "state").key_file(connection["name"]).exists()
        assert "fixture-access-secret" not in client.get("/api/connections").text
        assert "fixture-refresh-secret" not in client.get("/api/connections").text
        assert "fixture-code" not in client.get("/api/connections").text
        saved_record = json.loads((tmp_path / "state/chatgpt/accounts.json").read_text())["accounts"][
            listing["chatgpt_accounts"][0]["account_id"]]
        assert saved_record["access_token"] == "fixture-access-secret"
        assert oct((tmp_path / "state/chatgpt/accounts.json").stat().st_mode & 0o777) == "0o600"

        typed = client.get("/api/v1/connections")
        assert typed.status_code == 200, typed.text
        assert typed.json()[0]["auth_type"] == "chatgpt-siws"
        assert typed.json()[0]["output_token_limit_enforced"] is False

    assert requests == [
        "https://auth.openai.com/api/accounts/oauth/token",
        "https://auth.openai.com/.well-known/openid-configuration",
        "https://auth.openai.com/.well-known/jwks.json",
    ]


def test_chatgpt_preview_is_opt_in_and_generic_connection_add_cannot_forge_it(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("HUTCH_ENABLE_CHATGPT_PLAN", raising=False)
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.post("/api/chatgpt/sign-in", json={}).status_code == 409
        listing = client.get("/api/connections").json()
        assert listing["chatgpt_enabled"] is False
        assert listing["chatgpt_accounts"] == []
        forged = client.post("/api/connections", json={"template": "chatgpt-plan"})
        assert forged.status_code == 422
        assert client.post("/api/chatgpt/accounts/acct_000000000000000000000000/disconnect",
                           json={}).status_code == 404


def test_loopback_oauth_cannot_start_from_remote_peer(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_ENABLE_CHATGPT_PLAN", "1")
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.20", 10000)) as client:
        response = client.post("/api/chatgpt/sign-in", json={})
        assert response.status_code == 421
    assert not (tmp_path / "state/chatgpt/pending").exists()
