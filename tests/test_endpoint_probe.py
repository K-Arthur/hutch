"""The layered endpoint probe, against real sockets: a real HTTP server, a real TLS server with a real self-signed
certificate (made by the openssl CLI), a closed port and the address policy. ADR-0034."""

from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from hutch.providers.endpoint_probe import probe_endpoint

MODELS = json.dumps({"data": [{"id": "qwen3-4b"}, {"id": "gemma"}]}).encode()


def _serve(routes, tls=None):
    """routes: path -> (status, headers, body). An unknown path is a 404 with a JSON body."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            httpd.seen.append((self.path, self.headers.get("Authorization")))
            status, headers, body = routes.get(self.path, (404, {}, b'{"error":"not found"}'))
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    httpd.seen = []                      # (path, Authorization header) of every request, for assertions
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(*tls)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


@pytest.fixture()
def plain():
    httpd = _serve({"/v1/models": (200, {"Content-Type": "application/json"}, MODELS)})
    yield httpd.server_address[1]
    httpd.shutdown()


@pytest.fixture()
def certificate(tmp_path):
    if not shutil.which("openssl"):
        pytest.skip("openssl is needed to make a real self-signed certificate")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out",
                    str(cert), "-days", "1", "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
    return str(cert), str(key)


def test_every_layer_passes_for_a_working_server(plain):
    report = probe_endpoint(f"http://127.0.0.1:{plain}/v1")
    assert report.ok and report.models == ["qwen3-4b", "gemma"]
    assert [layer.name for layer in report.layers] == ["address", "dns", "connect", "key", "models"]


def test_https_against_a_plain_http_port_names_the_tls_layer_not_a_dead_server(plain):
    report = probe_endpoint(f"https://127.0.0.1:{plain}/v1")
    assert report.failed.name == "tls" and "plain HTTP" in report.failed.detail
    assert "is the server running" not in report.summary()


def test_http_against_a_tls_port_says_the_port_may_expect_https(certificate):
    httpd = _serve({}, tls=certificate)
    try:
        report = probe_endpoint(f"http://127.0.0.1:{httpd.server_address[1]}/v1")
    finally:
        httpd.shutdown()
    assert report.failed.name == "models" and "expect https://" in report.failed.detail


def test_a_self_signed_certificate_is_refused_with_the_fix_and_trusted_once_configured(certificate, monkeypatch):
    routes = {"/v1/models": (200, {"Content-Type": "application/json"}, MODELS)}
    httpd = _serve(routes, tls=certificate)
    url = f"https://localhost:{httpd.server_address[1]}/v1"
    try:
        refused = probe_endpoint(url)
        assert refused.failed.name == "tls" and "not trusted" in refused.failed.detail
        assert "SSL_CERT_FILE" in refused.failed.detail
        monkeypatch.setenv("SSL_CERT_FILE", certificate[0])
        trusted = probe_endpoint(url)
        assert trusted.ok and trusted.models == ["qwen3-4b", "gemma"]
    finally:
        httpd.shutdown()


def test_a_key_the_server_refuses_is_the_key_layer():
    httpd = _serve({"/v1/models": (401, {}, b'{"error":"bad key"}')})
    try:
        report = probe_endpoint(f"http://127.0.0.1:{httpd.server_address[1]}/v1", key="sk-secret")
    finally:
        httpd.shutdown()
    assert report.failed.name == "key" and "sk-secret" not in report.summary()


def test_a_root_url_that_needs_v1_gets_the_exact_suggestion(plain):
    report = probe_endpoint(f"http://127.0.0.1:{plain}")
    assert report.failed.name == "models" and report.suggested_base == f"http://127.0.0.1:{plain}/v1"
    assert f"http://127.0.0.1:{plain}/v1" in report.failed.detail


def test_a_web_page_and_a_redirect_are_not_a_model_list():
    httpd = _serve({"/v1/models": (200, {"Content-Type": "text/html"}, b"<html>welcome</html>"),
                    "/moved/models": (302, {"Location": "https://elsewhere.example/v1/models"}, b"")})
    port = httpd.server_address[1]
    try:
        page = probe_endpoint(f"http://127.0.0.1:{port}/v1")
        moved = probe_endpoint(f"http://127.0.0.1:{port}/moved")
    finally:
        httpd.shutdown()
    assert page.failed.name == "models" and "not a model list" in page.failed.detail
    assert moved.failed.name == "models" and "not followed" in moved.failed.detail


def test_a_closed_port_is_a_connect_failure():
    report = probe_endpoint("http://127.0.0.1:1/v1", timeout=1.0)
    assert report.failed.name == "connect" and "nothing is listening" in report.failed.detail


def test_the_policy_refuses_before_any_socket_is_opened():
    assert probe_endpoint("https://169.254.169.254/v1").failed.name == "address"
    clear = probe_endpoint("http://192.168.1.50:8000/v1", key="sk-secret")
    assert clear.failed.name == "address" and "clear text" in clear.failed.detail
    assert "sk-secret" not in clear.summary()


def test_an_ollama_server_behind_v1_is_named_from_its_own_answer_and_a_plain_one_is_not():
    ollama = _serve({"/v1/models": (200, {}, MODELS), "/api/version": (200, {}, b'{"version":"0.40.13"}')})
    other = _serve({"/v1/models": (200, {}, MODELS)})
    try:
        named = probe_endpoint(f"http://127.0.0.1:{ollama.server_address[1]}/v1", identify=True)
        plain = probe_endpoint(f"http://127.0.0.1:{other.server_address[1]}/v1", identify=True)
    finally:
        ollama.shutdown()
        other.shutdown()
    assert named.engine == "ollama" and "num_ctx" in named.advice
    assert plain.engine == "" and plain.advice == ""


# ---- through `connections test` (the CLI, the Models page and the doctor all call check_connection)

def _custom(tmp_path, monkeypatch, url, template="custom-openai"):
    from hutch.connections import ConnectionBook
    monkeypatch.setenv("CUSTOM_API_KEY", "sk-test-secret")
    book = ConnectionBook(tmp_path)
    book.add(template, name="mine", base_url=url)
    return book


def test_connections_test_names_the_failed_layer_and_never_the_key(tmp_path, monkeypatch, plain):
    from hutch.providers.connection import check_connection
    book = _custom(tmp_path, monkeypatch, f"http://127.0.0.1:{plain}")          # forgot /v1
    result = check_connection(book, "mine")
    assert not result.ok and "models layer" in result.detail and f"http://127.0.0.1:{plain}/v1" in result.detail
    assert "sk-test-secret" not in result.detail
    wrong_scheme = _custom(tmp_path / "b", monkeypatch, f"https://127.0.0.1:{plain}/v1")
    assert "tls layer" in check_connection(wrong_scheme, "mine").detail


def test_connections_test_passes_and_flags_ollama_behind_v1(tmp_path, monkeypatch):
    from hutch.providers.connection import check_connection
    ollama = _serve({"/v1/models": (200, {}, MODELS), "/api/version": (200, {}, b'{"version":"0.40.13"}')})
    try:
        book = _custom(tmp_path, monkeypatch, f"http://127.0.0.1:{ollama.server_address[1]}/v1")
        result = check_connection(book, "mine")
    finally:
        ollama.shutdown()
    assert result.ok and result.verified and "num_ctx" in result.detail
    assert ollama.seen == [("/v1/models", "Bearer sk-test-secret"), ("/api/version", None)]   # the key goes out once
