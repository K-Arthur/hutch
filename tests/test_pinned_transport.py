"""The pinned transport: real sockets where a real server can answer, an in-memory inner transport where the
assertion is about the rewritten request (a resolver cannot be told to rebind on demand, so failure injection is
the only use of a fake here). ADR-0034."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from hutch.providers.endpoint_policy import EndpointRefused
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.providers.pinned_transport import PinnedTransport, guarded_options


class _Echo(BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):
        type(self).seen.append({"host": self.headers.get("Host"), "auth": self.headers.get("Authorization")})
        body = b'{"data": [{"id": "echo"}]}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture()
def server():
    _Echo.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), _Echo)           # IPv4 only: a dual-stack "localhost" must fall back
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _answers(*ips):
    def resolve(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]
    return resolve


def _client(**kw):
    return httpx.Client(transport=PinnedTransport(**kw), timeout=3.0)


def test_a_real_loopback_request_keeps_the_host_name_and_falls_back_across_address_families(server):
    with _client() as client:
        response = client.get(f"http://localhost:{server}/v1/models")
    assert response.status_code == 200
    assert _Echo.seen == [{"host": f"localhost:{server}", "auth": None}]


def test_a_rebound_name_is_refused_before_any_connection(server):
    with _client(resolver=_answers("127.0.0.1")) as client:
        with pytest.raises(EndpointRefused, match="looks like a public name"):
            client.get(f"http://models.example.test:{server}/v1/models")
    assert _Echo.seen == []


def test_a_listed_name_is_reached_over_its_validated_address(server):
    with _client(resolver=_answers("127.0.0.1"), env={"HUTCH_PRIVATE_HOSTS": "models.example.test"}) as client:
        assert client.get(f"http://models.example.test:{server}/v1/models").status_code == 200
    assert _Echo.seen[0]["host"] == f"models.example.test:{server}"


def test_the_request_is_rewritten_to_the_address_and_the_tls_name_is_kept():
    captured = []

    class Inner:
        def handle_request(self, request):
            captured.append(request)
            return httpx.Response(200, request=request)

        def close(self):
            pass

    with httpx.Client(transport=PinnedTransport(inner=Inner(), resolver=_answers("8.8.8.8"))) as client:
        client.get("https://api.example.test/v1/models")
    request = captured[0]
    assert request.url.host == "8.8.8.8" and request.headers["host"] == "api.example.test"
    assert request.extensions["sni_hostname"] == "api.example.test"


@pytest.mark.parametrize("url,message", [
    ("https://169.254.169.254/v1/models", "never a model endpoint"),
    ("https://[fe80::1]/v1/models", "never a model endpoint"),
    ("http://8.8.8.8/v1/models", "plain HTTP is only allowed"),
])
def test_blocked_and_clear_text_public_destinations_are_refused_without_a_socket(url, message):
    with _client() as client:
        with pytest.raises(EndpointRefused, match=message):
            client.get(url)


def test_a_key_is_never_sent_in_clear_text_off_this_computer():
    with _client(resolver=_answers("192.168.1.50"), env={}) as client:
        with pytest.raises(EndpointRefused, match="never sent in clear text"):
            client.get("http://nas.lan:8000/v1/models", headers={"Authorization": "Bearer sk-secret"})
        with pytest.raises(EndpointRefused, match="never sent in clear text"):
            client.get("http://nas.lan:8000/v1/models", headers={"x-api-key": "sk-secret"})


def test_a_keyless_private_server_over_http_is_allowed_and_a_key_over_loopback_http_is_allowed(server):
    captured = []

    class Inner:
        def handle_request(self, request):
            captured.append(request.url.host)
            return httpx.Response(200, request=request)

        def close(self):
            pass

    with httpx.Client(transport=PinnedTransport(inner=Inner(), resolver=_answers("192.168.1.50"))) as client:
        assert client.get("http://nas.lan:8000/v1/models").status_code == 200
    assert captured == ["192.168.1.50"]
    with _client() as client:
        assert client.get(f"http://127.0.0.1:{server}/v1/models",
                          headers={"Authorization": "Bearer k"}).status_code == 200
    assert _Echo.seen[-1]["auth"] == "Bearer k"


def test_a_provider_reports_the_refusal_in_words_not_as_an_unreachable_server():
    ok, detail, models = OpenAICompatProvider("https://169.254.169.254/v1", "k").probe_models()
    assert not ok and models == [] and "never a model endpoint" in detail and "is the server running" not in detail
    ok, detail, _ = OpenAICompatProvider("http://192.168.1.50:8000/v1", "sk-secret").probe_models()
    assert not ok and "never sent in clear text" in detail and "sk-secret" not in detail


def test_with_an_environment_proxy_the_address_cannot_be_pinned_but_a_blocked_literal_is_still_refused(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    assert guarded_options("https://api.example.test/v1") == ("https://api.example.test/v1", None, True)
    with pytest.raises(EndpointRefused):
        guarded_options("https://169.254.169.254/v1")


def test_the_anthropic_sdk_client_is_pinned_too_and_the_refusal_keeps_its_words():
    pytest.importorskip("anthropic")
    from hutch.providers.claude import ClaudeProvider
    from hutch.providers.base import ProviderError
    provider = ClaudeProvider(api_key="sk-secret", base_url="https://169.254.169.254")
    with pytest.raises(ProviderError) as raised:
        provider.list_models()
    assert "never a model endpoint" in str(raised.value) and "sk-secret" not in str(raised.value)
    clear = ClaudeProvider(api_key="sk-secret", base_url="http://192.168.1.50:9000")
    with pytest.raises(ProviderError, match="never sent in clear text"):
        clear.list_models()
