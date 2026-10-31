"""Mediated egress: a real vault value, a real HTTP request shape, and no value in the result."""

from __future__ import annotations

import httpx
import pytest

from hutch.netguard import NetGuardError
from hutch.safehttp import safe_request
from hutch.vault.destinations import DestinationError
from hutch.vault.egress import EgressError, mediate_http
from hutch.vault.refs import Permission, Principal
from hutch.vault.vault import AccessDenied
from tests.support.vault_fixtures import BOT_A, CANARY, DESTINATION, unlocked

API = "https://api.example.com"
API_IP = "93.184.216.34"


def _resolver(mapping):
    def resolve(host, port, *a, **kw):
        ips = mapping[host] if isinstance(mapping, dict) else mapping(host)
        return [(2 if ":" not in ip else 10, 1, 6, "", (ip, port)) for ip in ips]
    return resolve


def _ready(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, API)
    return vault, meta


class Recorder:
    def __init__(self, response):
        self.requests: list[httpx.Request] = []
        self.response = response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response


def test_a_bound_credential_is_presented_at_the_network_boundary_and_not_returned(store):
    vault, meta = _ready(store)
    recorder = Recorder(httpx.Response(200, json={"pages": []},
                                       headers={"content-type": "application/json"}))
    response = mediate_http(
        vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET",
        url=f"{API}/v1/pages?page_size=1", transport=httpx.MockTransport(recorder),
        resolver=_resolver({"api.example.com": [API_IP]}))

    assert response.ok and response.status == 200
    assert response.destination == API
    assert response.url == f"{API}/v1/pages?page_size=1"
    assert '"pages"' in response.body
    assert CANARY not in repr(response) and CANARY not in response.body
    [request] = recorder.requests
    assert request.url.host == API_IP                      # pinned, not looked up twice
    assert request.headers["host"] == "api.example.com"
    assert request.headers["authorization"] == f"Bearer {CANARY}"
    assert request.extensions.get("sni_hostname") == "api.example.com"

    use = next(entry for entry in vault.audit_log() if entry.action == "use")
    assert use.actor == f"bot:{BOT_A}"
    assert use.secret_id == meta.id
    assert use.destination == API
    assert use.outcome == "ok"


def test_an_unbound_destination_is_refused_before_any_request(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=CANARY)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    recorder = Recorder(httpx.Response(200, text="should not happen"))
    with pytest.raises(AccessDenied):
        mediate_http(vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET",
                     url=f"{API}/v1/pages", transport=httpx.MockTransport(recorder),
                     resolver=_resolver({"api.example.com": [API_IP]}))
    assert recorder.requests == []
    denied = [entry for entry in vault.audit_log() if entry.outcome == "denied"]
    assert denied and denied[0].reason == "no_destination"


def test_binding_one_origin_does_not_authorize_another(store):
    vault, meta = _ready(store)
    recorder = Recorder(httpx.Response(200, text="should not happen"))
    mapping = {"api.example.com": [API_IP], "evil.example": ["93.184.216.35"]}
    with pytest.raises(AccessDenied):
        mediate_http(vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET",
                     url="https://evil.example/collect", transport=httpx.MockTransport(recorder),
                     resolver=_resolver(mapping))
    assert recorder.requests == []


def test_a_redirect_is_returned_not_followed_with_the_credential(store):
    vault, meta = _ready(store)
    recorder = Recorder(httpx.Response(302, headers={"location": "https://evil.example/collect"}))
    response = mediate_http(
        vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET", url=f"{API}/start",
        transport=httpx.MockTransport(recorder),
        resolver=_resolver({"api.example.com": [API_IP], "evil.example": ["93.184.216.35"]}))
    assert response.status == 302
    assert response.headers["location"] == "https://evil.example/collect"
    assert len(recorder.requests) == 1
    assert recorder.requests[0].url.host == API_IP


def test_a_service_that_echoes_the_credential_cannot_return_it(store):
    vault = unlocked(store)
    token = "sk-live-9f3c2b7a1d4e6f8c"
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=token)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, API)
    recorder = Recorder(httpx.Response(
        401, text=f"bad token {token}",
        headers={"content-type": "text/plain", "x-debug-auth": f"Bearer {token}",
                 "set-cookie": f"session={token}"}))
    response = mediate_http(vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET",
                            url=f"{API}/v1/pages", transport=httpx.MockTransport(recorder),
                            resolver=_resolver({"api.example.com": [API_IP]}))
    assert response.status == 401
    assert token not in response.body
    assert token not in repr(response.headers)
    assert "[redacted]" in response.body
    assert "set-cookie" not in {name.lower() for name in response.headers}


@pytest.mark.parametrize("prefix, header", [
    ("Bearer \r\nX-Evil: 1", "Authorization"),
    ("Bearer ", "Host"),
    ("Bearer ", "Content-Length"),
    ("Bearer ", "bad header"),
])
def test_header_injection_is_refused_before_the_vault_is_touched(store, prefix, header):
    vault, meta = _ready(store)
    recorder = Recorder(httpx.Response(200, text="should not happen"))
    with pytest.raises(EgressError):
        mediate_http(vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET",
                     url=f"{API}/v1/pages", header_name=header, value_prefix=prefix,
                     transport=httpx.MockTransport(recorder),
                     resolver=_resolver({"api.example.com": [API_IP]}))
    assert recorder.requests == []


def test_the_status_line_is_scrubbed_too(store):
    """A hostile service can echo the credential in a reason phrase, which is not a header or a body."""
    vault = unlocked(store)
    token = "sk-live-4c1d9a7e2b8f6031"
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value=token)
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, API)
    recorder = Recorder(httpx.Response(403, text="no",
                                       extensions={"reason_phrase": f"denied {token}".encode()}))
    response = mediate_http(vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET",
                            url=f"{API}/v1/pages", transport=httpx.MockTransport(recorder),
                            resolver=_resolver({"api.example.com": [API_IP]}))
    assert response.status == 403
    assert token not in response.reason
    assert "[redacted]" in response.reason


def test_a_url_with_embedded_credentials_is_refused(store):
    vault, meta = _ready(store)
    recorder = Recorder(httpx.Response(200, text="should not happen"))
    with pytest.raises(DestinationError):
        mediate_http(vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET",
                     url="https://user:pass@api.example.com/v1/pages",
                     transport=httpx.MockTransport(recorder),
                     resolver=_resolver({"api.example.com": [API_IP]}))
    assert recorder.requests == []


def test_a_post_body_and_content_type_reach_the_service(store):
    vault, meta = _ready(store)
    recorder = Recorder(httpx.Response(201, json={"id": "page_1"},
                                       headers={"content-type": "application/json"}))
    response = mediate_http(
        vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="POST",
        url=f"{API}/v1/pages", body='{"title": "hello"}', content_type="application/json",
        transport=httpx.MockTransport(recorder),
        resolver=_resolver({"api.example.com": [API_IP]}))
    assert response.status == 201
    [request] = recorder.requests
    assert request.method == "POST"
    assert request.content == b'{"title": "hello"}'
    assert request.headers["content-type"] == "application/json"
    assert request.headers["authorization"] == f"Bearer {CANARY}"


def test_a_non_ascii_credential_is_refused_rather_than_mangled(store):
    vault = unlocked(store)
    meta = vault.put_secret(scope="workspace", category="api_key", name="api", value="caf\u00e9-token")
    vault.grant(meta.id, Principal.bot(BOT_A), Permission.USE)
    vault.bind_destination(meta.id, API)
    recorder = Recorder(httpx.Response(200, text="should not happen"))
    with pytest.raises(EgressError):
        mediate_http(vault, ref=meta.ref, principal=Principal.bot(BOT_A), method="GET",
                     url=f"{API}/v1/pages", transport=httpx.MockTransport(recorder),
                     resolver=_resolver({"api.example.com": [API_IP]}))
    assert recorder.requests == []


def test_safe_request_refuses_a_caller_supplied_host_header():
    with pytest.raises(NetGuardError):
        safe_request("GET", "https://example.com/", headers={"Host": "evil.example"},
                     resolver=_resolver({"example.com": [API_IP]}),
                     transport=httpx.MockTransport(lambda request: httpx.Response(200)))


def test_safe_request_never_follows_a_redirect():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(301, headers={"location": "https://evil.example/"})

    response = safe_request("GET", "https://example.com/", resolver=_resolver({"example.com": [API_IP]}),
                            transport=httpx.MockTransport(handler))
    assert response.status == 301 and response.redirects == []
    assert len(seen) == 1
