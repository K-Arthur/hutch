"""Notion's public DCR/PKCE path without external accounts, tokens or paid models."""
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hutch.google_calendar import _b64url
from hutch.integrations.notion import NotionBook, NotionError, ORIGIN
from tests.test_google_calendar import MemorySecrets

CALLBACK = "http://127.0.0.1:18787/api/v1/connections/notion/callback"


@pytest.fixture
def notion(tmp_path):
    state = {"now": 1000, "calls": [], "rotation": 0, "revocation": 204}
    def handler(request):
        assert str(request.url).startswith(ORIGIN + "/")
        path = request.url.path
        if path == "/.well-known/oauth-authorization-server":
            return httpx.Response(200, json={"issuer": ORIGIN, "authorization_endpoint": ORIGIN + "/authorize",
                "token_endpoint": ORIGIN + "/token", "registration_endpoint": ORIGIN + "/register",
                "code_challenge_methods_supported": ["S256"]})
        if path == "/register":
            body = json.loads(request.content)
            state["registration"] = body
            return httpx.Response(201, json={"client_id": "public-dynamic-client", "token_endpoint_auth_method": "none"})
        assert path == "/token"
        body = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        state["calls"].append(body)
        if "token" in body:
            return httpx.Response(state["revocation"])
        if body["grant_type"] == "refresh_token":
            assert body["refresh_token"] == "REFRESH-" + str(state["rotation"])
            state["rotation"] += 1
        return httpx.Response(200, json={"access_token": "ACCESS-" + str(state["rotation"]),
            "refresh_token": "REFRESH-" + str(state["rotation"]), "expires_in": 3600,
            "token_type": "bearer", "scope": "default", "workspace_name": "Fixture Workspace",
            "workspace_id": "fixture-workspace-id"})
    secret_store = MemorySecrets()
    book = NotionBook(tmp_path, transport=httpx.MockTransport(handler), secrets_store=secret_store,
                      clock=lambda: state["now"])
    return book, state, secret_store


def connect(book):
    start = book.start("Notion", CALLBACK)
    return book.finish(start.state, "fixture-code", CALLBACK)


def test_dcr_and_pkce_bind_the_registered_callback_and_keep_verifier_private(notion):
    book, state, secrets = notion
    start = book.start("Work", CALLBACK)
    query = parse_qs(urlsplit(start.url).query)
    assert query["client_id"] == ["public-dynamic-client"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["default"]
    assert query["resource"] == [ORIGIN + "/mcp"]
    assert state["registration"]["redirect_uris"] == [CALLBACK]
    assert state["registration"]["token_endpoint_auth_method"] == "none"
    pending_path = book.pending_dir / (start.state + ".json")
    pending = json.loads(pending_path.read_text())
    assert pending_path.stat().st_mode & 0o777 == 0o600
    assert query["code_challenge"] == [_b64url(hashlib.sha256(pending["verifier"].encode()).digest())]
    assert pending["verifier"] not in start.url
    account = book.finish(start.state, "fixture-code", CALLBACK, issuer=ORIGIN)
    assert account["workspace_id"] == "fixture-workspace-id"
    assert "ACCESS-" not in book.accounts_path.read_text()
    assert "REFRESH-" not in book.accounts_path.read_text()
    assert json.loads(secrets.get(account["id"]))["access_token"] == "ACCESS-0"
    assert state["calls"][0]["code_verifier"] == pending["verifier"]
    with pytest.raises(NotionError, match="already used"):
        book.finish(start.state, "fixture-code", CALLBACK)


@pytest.mark.parametrize("change", ["callback", "issuer", "expired", "cancelled"])
def test_callback_mismatch_expiry_and_cancellation_precede_token_exchange(notion, change):
    book, state, _ = notion
    start = book.start("Work", CALLBACK)
    callback, issuer = CALLBACK, ORIGIN
    if change == "callback":
        callback = CALLBACK.replace(":18787", ":18788")
    elif change == "issuer":
        issuer = "https://attacker.example"
    elif change == "expired":
        state["now"] += 601
    else:
        book.cancel(start.state)
    with pytest.raises(NotionError):
        book.finish(start.state, "fixture-code", callback, issuer=issuer)
    assert not state["calls"]


def test_refresh_rotation_is_saved_and_disconnect_invalidates_all_local_access(notion):
    book, state, secrets = notion
    account = connect(book)
    assert book.access_token(account["id"]) == "ACCESS-0"
    assert len(state["calls"]) == 1
    state["now"] += 3601
    assert book.access_token(account["id"]) == "ACCESS-1"
    assert json.loads(secrets.get(account["id"]))["refresh_token"] == "REFRESH-1"
    state["now"] += 3601
    assert book.access_token(account["id"]) == "ACCESS-2"
    assert book.disconnect(account["id"])["provider_revocation"] == "confirmed"
    assert not book.accounts() and secrets.get(account["id"]) is None
    with pytest.raises(NotionError, match="disconnected"):
        book.access_token(account["id"])


def test_failed_provider_revocation_is_honest_but_local_disconnect_still_completes(notion):
    book, state, _ = notion
    account = connect(book)
    state["revocation"] = 503
    assert book.disconnect(account["id"]) == {"removed": True, "provider_revocation": "not_confirmed"}
    assert book.accounts() == []


def test_fixed_metadata_rejects_redirected_endpoints_without_registering_or_leaking(tmp_path):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"issuer": ORIGIN, "authorization_endpoint": "https://attacker.example/authorize"})
    book = NotionBook(tmp_path, secrets_store=MemorySecrets(), transport=httpx.MockTransport(handler))
    with pytest.raises(NotionError, match="configuration changed"):
        book.start("Work", CALLBACK)
    assert seen == [ORIGIN + "/.well-known/oauth-authorization-server"]


def test_token_error_body_is_never_returned_and_redirects_are_not_followed(tmp_path):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://attacker.example"}, text="TOKEN-SENTINEL")
    book = NotionBook(tmp_path, secrets_store=MemorySecrets(), transport=httpx.MockTransport(handler))
    with pytest.raises(NotionError) as error:
        book._request("/token", data={"code": "PRIVATE-CODE"})
    assert "TOKEN-SENTINEL" not in str(error.value) and "PRIVATE-CODE" not in str(error.value)
    assert seen == [ORIGIN + "/token"]


def test_response_cap_and_unexpected_scope_fail_closed(tmp_path):
    book = NotionBook(tmp_path, secrets_store=MemorySecrets(), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 64_001)))
    with pytest.raises(NotionError, match="size limit"):
        book._request("/token", data={})
    with pytest.raises(NotionError, match="unexpected authorization scope"):
        book._token_bundle({"access_token": "A", "refresh_token": "R", "token_type": "bearer",
                            "scope": "default ema_issuer:manage"}, client_id="client")


def test_advertised_issuer_parameter_is_required_before_exchanging_a_code(notion, monkeypatch):
    book, state, _ = notion
    original = book._request
    def request(path, **kwargs):
        result = original(path, **kwargs)
        if path.startswith("/.well-known/"):
            result["authorization_response_iss_parameter_supported"] = True
        return result
    monkeypatch.setattr(book, "_request", request)
    start = book.start("Work", CALLBACK)
    with pytest.raises(NotionError, match="did not match"):
        book.finish(start.state, "fixture-code", CALLBACK)
    assert not state["calls"]
