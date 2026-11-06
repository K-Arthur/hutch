"""Locality truth: the server's own signal beats the model name (EC-01), addresses beat spelling (EC-02)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from hutch.providers.locality import (endpoint_locality, entry_is_remote, model_locality, route_locality)
from hutch.providers.model_install import validate_model_name
from hutch.providers.registry import validate_offline_route

ROWS = [
    {"name": "qwen3:4b", "digest": "a"},
    {"name": "gpt-oss:120b-cloud", "remote_host": "https://ollama.com:443", "remote_model": "gpt-oss:120b"},
    {"name": "mycopy:latest", "remote_host": "https://ollama.com:443", "remote_model": "gpt-oss:120b"},
]


@pytest.fixture()
def tags_server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"models": ROWS}).encode()
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_server_signal_marks_a_renamed_cloud_copy_as_remote():
    assert entry_is_remote(ROWS[2]) and not entry_is_remote(ROWS[0])
    verdict = model_locality("ollama", "mycopy:latest", ROWS[2])
    assert verdict.local is False and verdict.source == "server_signal"


def test_name_is_only_a_fallback():
    assert model_locality("ollama", "gpt-oss:120b-cloud").source == "name"
    assert model_locality("ollama", "qwen3:4b", ROWS[0]).local is True
    assert model_locality("openai", "gpt-4o").local is False


def test_route_locality_reads_the_runtime_row(tags_server):
    assert route_locality("ollama", "qwen3:4b", tags_server).local is True
    assert route_locality("ollama", "mycopy", tags_server).local is False
    assert route_locality("ollama", "gpt-oss:120b-cloud", tags_server).local is False


def test_offline_route_refuses_renamed_cloud_copy_but_accepts_local(tags_server):
    validate_offline_route("ollama/qwen3:4b", tags_server)
    with pytest.raises(ValueError, match="runtime reports"):
        validate_offline_route("ollama/mycopy", tags_server)


@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1:11434", True), ("http://localhost:11434", True), ("http://[::1]:11434", True),
    ("http://192.168.1.20:11434", False), ("http://0.0.0.0:11434", False), ("http://8.8.8.8", False),
    ("http://no-such-host.invalid", None),
])
def test_endpoint_is_judged_by_address(url, expected):
    assert endpoint_locality(url).local is expected


def test_cloud_tags_are_refused_at_install_unless_confirmed():
    with pytest.raises(ValueError, match="cloud model"):
        validate_model_name("gpt-oss:120b-cloud")
    assert validate_model_name("gpt-oss:120b-cloud", allow_cloud=True) == "gpt-oss:120b-cloud"
    assert validate_model_name("qwen3:4b") == "qwen3:4b"
