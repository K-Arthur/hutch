from __future__ import annotations

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from hutch.chatgpt_auth import AUTH_ORIGIN, PLAN_SCOPE, RESOURCE, ChatGPTAuthBook, ChatGPTAuthError


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def jwt(private_key, claims):
    head = b64url(json.dumps({"alg": "RS256", "kid": "test-key"}, separators=(",", ":")).encode())
    body = b64url(json.dumps(claims, separators=(",", ":")).encode())
    message = f"{head}.{body}".encode()
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{b64url(signature)}"


def jwk(private_key):
    numbers = private_key.public_key().public_numbers()
    return {"kty": "RSA", "kid": "test-key", "use": "sig", "alg": "RS256",
            "n": b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
            "e": b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big"))}


def setup_auth(tmp_path, *, scope=f"openid profile email offline_access resource.invoke {PLAN_SCOPE}",
               email_verified=True):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = time.time()

    def handler(request):
        if request.url == httpx.URL(AUTH_ORIGIN + "/.well-known/openid-configuration"):
            return httpx.Response(200, json={"issuer": AUTH_ORIGIN,
                                             "jwks_uri": AUTH_ORIGIN + "/.well-known/jwks.json",
                                             "revocation_endpoint": AUTH_ORIGIN + "/api/accounts/oauth/revoke"})
        if request.url == httpx.URL(AUTH_ORIGIN + "/.well-known/jwks.json"):
            return httpx.Response(200, json={"keys": [jwk(private_key)]})
        if request.url == httpx.URL(AUTH_ORIGIN + "/api/accounts/oauth/token"):
            form = parse_qs(request.content.decode())
            assert "client_secret" not in form
            if form.get("grant_type") == ["authorization_code"]:
                assert form["resource"] == [RESOURCE]
                claims = {"iss": AUTH_ORIGIN, "aud": form["client_id"][0], "sub": "acct-sub-1",
                          "email": "owner@example.test", "email_verified": email_verified,
                          "nonce": callback_nonce[0], "iat": now, "exp": now + 3600}
                return httpx.Response(200, json={"access_token": "access-1", "refresh_token": "refresh-1",
                                                 "id_token": jwt(private_key, claims), "expires_in": 3600,
                                                 "token_type": "Bearer", "scope": scope})
            if form.get("grant_type") == ["refresh_token"]:
                assert form["refresh_token"] == ["refresh-1"]
                return httpx.Response(200, json={"access_token": "access-2", "refresh_token": "refresh-2",
                                                 "token_type": "Bearer", "expires_in": 3600, "scope": scope})
        if request.url == httpx.URL(AUTH_ORIGIN + "/api/accounts/oauth/revoke"):
            assert b"refresh-2" in request.content
            return httpx.Response(200)
        if request.url == httpx.URL("https://api.openai.com/v1/models"):
            assert request.headers["authorization"] == "Bearer access-2"
            return httpx.Response(200, json={"models": [
                {"slug": "gpt-fixture", "display_name": "GPT fixture", "visibility": "list"},
                {"slug": "hidden", "display_name": "Hidden", "visibility": "hidden"},
            ]})
        return httpx.Response(404)

    callback_nonce = [""]
    transport = httpx.MockTransport(handler)
    auth = ChatGPTAuthBook(tmp_path / "state", transport=transport, clock=lambda: now)
    return auth, callback_nonce, now


def test_signin_uses_dynamic_registration_pkce_and_exact_loopback_callback(tmp_path):
    auth = ChatGPTAuthBook(tmp_path / "state", clock=lambda: 1000.0)
    with pytest.raises(ChatGPTAuthError, match="127.0.0.1"):
        auth.start("http://localhost:8787/auth/callback")
    with pytest.raises(ChatGPTAuthError, match="127.0.0.1"):
        auth.start("https://127.0.0.1:8787/auth/callback")

    url = auth.start("http://127.0.0.1:8787/auth/callback")
    params = parse_qs(urlsplit(url).query)
    assert url.startswith(AUTH_ORIGIN + "/api/accounts/authorize?")
    assert params["client_id"] == ["dynamic_agent_client"]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == ["http://127.0.0.1:8787/auth/callback"]
    assert params["ext_agent_host_id"][0].startswith("urn:uuid:")
    assert params["agent_name_hint"] == ["Hutch"]
    assert PLAN_SCOPE in params["scope"][0].split()
    pending = json.loads(next((tmp_path / "state/chatgpt/pending").glob("*.json")).read_text())
    assert params["code_challenge"] == [b64url(hashlib.sha256(pending["verifier"].encode()).digest())]
    assert params["code_challenge_method"] == ["S256"]
    assert oct((tmp_path / "state/chatgpt/accounts.json").stat().st_mode & 0o777) == "0o600"
    assert oct((tmp_path / "state/chatgpt").stat().st_mode & 0o777) == "0o700"


def test_callback_validates_identity_saves_private_account_refreshes_and_revokes(tmp_path):
    auth, callback_nonce, now = setup_auth(tmp_path)
    url = auth.start("http://127.0.0.1:8787/auth/callback")
    params = parse_qs(urlsplit(url).query)
    callback_nonce[0] = params["nonce"][0]
    result = auth.finish(state=params["state"][0], code="one-time-code", returned_client_id="oaiapp_fixture")
    account_id = result["account_id"]
    assert result["email"] == "owner@example.test"
    assert result["plan_usage"] == "enabled"
    assert auth.has_plan_usage(account_id)
    assert auth.access_token(account_id) == "access-1"
    assert auth.accounts()[0]["email"] == "owner@example.test"

    path = tmp_path / "state/chatgpt/accounts.json"
    record = json.loads(path.read_text())["accounts"][account_id]
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    record["expires_at"] = now + 1
    path.write_text(json.dumps({"version": 1, "host_id": record["ext_agent_host_id"], "accounts": {account_id: record}}))
    assert auth.access_token(account_id) == "access-2"
    assert auth.list_models(account_id) == [{"slug": "gpt-fixture", "display_name": "GPT fixture"}]
    assert auth.disconnect(account_id) is True
    assert auth.disconnect(account_id) is True
    assert auth.has_plan_usage(account_id) is False
    assert auth.accounts()[0]["connected"] is False
    with pytest.raises(ChatGPTAuthError, match="Connect ChatGPT"):
        auth.access_token(account_id)
    with pytest.raises(ChatGPTAuthError, match="already been used"):
        auth.finish(state=params["state"][0], code="replay", returned_client_id="oaiapp_fixture")


def test_reauthorization_reuses_issued_client_and_verified_identity_hints(tmp_path):
    auth, callback_nonce, _ = setup_auth(tmp_path)
    initial = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback")).query)
    callback_nonce[0] = initial["nonce"][0]
    account_id = auth.finish(state=initial["state"][0], code="first-code",
                             returned_client_id="oaiapp_fixture")["account_id"]
    saved_id_token = json.loads((tmp_path / "state/chatgpt/accounts.json").read_text())["accounts"][account_id]["id_token"]

    reauth = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback",
                                         account_id=account_id)).query)
    assert reauth["client_id"] == ["oaiapp_fixture"]
    assert reauth["ext_agent_host_id"] == initial["ext_agent_host_id"]
    assert reauth["id_token_hint"] == [saved_id_token]
    assert reauth["login_hint"] == ["owner@example.test"]
    assert "agent_name_hint" not in reauth


def test_unverified_email_is_not_shown_or_used_as_login_hint(tmp_path):
    auth, callback_nonce, _ = setup_auth(tmp_path, email_verified=False)
    initial = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback")).query)
    callback_nonce[0] = initial["nonce"][0]
    account_id = auth.finish(state=initial["state"][0], code="first-code",
                             returned_client_id="oaiapp_fixture")["account_id"]

    path = tmp_path / "state/chatgpt/accounts.json"
    saved = json.loads(path.read_text())
    saved["accounts"][account_id]["email"] = "stale-unverified@example.test"
    path.write_text(json.dumps(saved))  # Simulate an older record that retained an unverified claim.
    assert auth.accounts()[0]["email"] == ""
    reauth = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback",
                                         account_id=account_id)).query)
    assert "login_hint" not in reauth
    assert "id_token_hint" in reauth


def test_identity_only_signin_is_saved_without_enabling_plan_inference(tmp_path):
    auth, callback_nonce, _ = setup_auth(tmp_path, scope="openid profile email")
    params = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback")).query)
    callback_nonce[0] = params["nonce"][0]
    result = auth.finish(state=params["state"][0], code="one-time-code", returned_client_id="oaiapp_fixture")
    assert result["plan_usage"] == "identity-only"
    assert auth.accounts()[0]["connected"] is True
    assert auth.has_plan_usage(result["account_id"]) is False
    with pytest.raises(ChatGPTAuthError, match="authorize plan usage"):
        auth.access_token(result["account_id"])


def test_bad_nonce_or_registration_never_replaces_account_credentials(tmp_path):
    auth, callback_nonce, _ = setup_auth(tmp_path)
    params = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback")).query)
    callback_nonce[0] = "wrong-nonce"
    with pytest.raises(ChatGPTAuthError, match="nonce"):
        auth.finish(state=params["state"][0], code="one-time-code", returned_client_id="oaiapp_fixture")
    assert auth.accounts() == []

    with pytest.raises(ChatGPTAuthError, match="already been used"):
        auth.finish(state=params["state"][0], code="replay", returned_client_id="oaiapp_other")

    params = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback")).query)
    callback_nonce[0] = params["nonce"][0]
    account_id = auth.finish(state=params["state"][0], code="one-time-code",
                             returned_client_id="oaiapp_fixture")["account_id"]
    original = auth.access_token(account_id)
    params = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback", account_id=account_id)).query)
    with pytest.raises(ChatGPTAuthError, match="did not match"):
        auth.finish(state=params["state"][0], code="wrong-registration", returned_client_id="oaiapp_other")
    assert auth.access_token(account_id) == original


def test_callback_rejects_duplicate_or_expired_state(tmp_path):
    auth = ChatGPTAuthBook(tmp_path / "state", clock=lambda: 1000.0)
    params = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback")).query)
    path = next((tmp_path / "state/chatgpt/pending").glob("*.json"))
    record = json.loads(path.read_text())
    record["expires_at"] = 999
    path.write_text(json.dumps(record))
    with pytest.raises(ChatGPTAuthError, match="expired"):
        auth.finish(state=params["state"][0], code="code", returned_client_id="oaiapp_fixture")


def test_bad_jwks_location_is_rejected(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"issuer": AUTH_ORIGIN,
                                         "jwks_uri": "https://attacker.invalid/keys"})
    auth = ChatGPTAuthBook(tmp_path / "state", transport=httpx.MockTransport(handler))
    with pytest.raises(ChatGPTAuthError, match="unexpected signing-key location"):
        auth._jwks()


def test_id_token_multiple_audiences_requires_authorized_party(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = {"iss": AUTH_ORIGIN, "aud": ["client-12345", "other-client"], "sub": "account",
              "nonce": "expected", "iat": 1000, "exp": 2000}
    with pytest.raises(ChatGPTAuthError, match="authorized party"):
        ChatGPTAuthBook._verify_id_token(jwt(private_key, claims), client_id="client-12345", nonce="expected",
                                         jwks={"keys": [jwk(private_key)]}, now=1500)
    claims["azp"] = "client-12345"
    assert ChatGPTAuthBook._verify_id_token(jwt(private_key, claims), client_id="client-12345", nonce="expected",
                                            jwks={"keys": [jwk(private_key)]}, now=1500)["sub"] == "account"


def test_disconnect_does_not_claim_or_repeat_an_unconfirmed_remote_revocation(tmp_path):
    auth, callback_nonce, _ = setup_auth(tmp_path)
    params = parse_qs(urlsplit(auth.start("http://127.0.0.1:8787/auth/callback")).query)
    callback_nonce[0] = params["nonce"][0]
    account_id = auth.finish(state=params["state"][0], code="one-time-code",
                             returned_client_id="oaiapp_fixture")["account_id"]
    requests = []

    def unsafe_discovery(request):
        requests.append(str(request.url))
        return httpx.Response(200, json={
            "issuer": AUTH_ORIGIN,
            "revocation_endpoint": "https://operator:secret@auth.openai.com/api/accounts/oauth/revoke",
        })

    revoker = ChatGPTAuthBook(tmp_path / "state", transport=httpx.MockTransport(unsafe_discovery))
    assert revoker.disconnect(account_id) is False
    assert revoker.disconnect(account_id) is False
    assert requests == [AUTH_ORIGIN + "/.well-known/openid-configuration"]
    record = json.loads((tmp_path / "state/chatgpt/accounts.json").read_text())["accounts"][account_id]
    assert record["refresh_token"] == ""
    assert record["revocation_status"] == "unconfirmed"
