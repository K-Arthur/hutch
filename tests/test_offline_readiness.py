"""Offline readiness (Phase 1.3): a Strict Offline route must be fully on disk, refused early in words."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from hutch.providers.offline_readiness import route_readiness
from hutch.providers.registry import validate_offline_route

ROWS = [{"name": "qwen3:4b", "size": 2497293931},
        {"name": "empty:latest", "size": 0},
        {"name": "gpt-oss:20b-cloud", "size": 306, "remote_host": "https://ollama.com"}]


def _serve(routes: dict[str, tuple[int, dict]]):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            status, payload = routes.get(self.path, (404, {}))
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


@pytest.fixture()
def ollama_like():
    srv, url = _serve({"/api/tags": (200, {"models": ROWS})})
    yield url
    srv.shutdown()


def test_downloaded_model_is_ready(ollama_like):
    assert route_readiness("ollama", "qwen3:4b", ollama_like).ready is True


def test_missing_model_is_not_ready_and_names_the_fix(ollama_like):
    got = route_readiness("ollama", "llama3.2:3b", ollama_like)
    assert got.ready is False and "not downloaded" in got.reason


def test_cloud_row_and_empty_weights_are_not_ready(ollama_like):
    assert route_readiness("ollama", "gpt-oss:20b-cloud", ollama_like).ready is False
    assert route_readiness("ollama", "empty", ollama_like).ready is False


def test_unreachable_server_is_unknown_not_a_pass():
    got = route_readiness("ollama", "qwen3:4b", "http://127.0.0.1:9")
    assert got.ready is None


def test_llamacpp_loading_is_not_ready_and_ready_server_is_disclosed_as_unknown():
    srv, url = _serve({"/health": (503, {"error": {"message": "Loading model"}})})
    try:
        assert route_readiness("llamacpp", "x", url).ready is False
    finally:
        srv.shutdown()
    srv, url = _serve({"/health": (200, {"status": "ok"})})
    try:
        got = route_readiness("llamacpp", "x", url)
        assert got.ready is None and "--offline" in got.reason
    finally:
        srv.shutdown()


def test_strict_offline_refuses_a_model_that_is_not_downloaded(ollama_like):
    validate_offline_route("ollama/qwen3:4b", ollama_like)
    with pytest.raises(ValueError, match="not ready for Strict Offline"):
        validate_offline_route("ollama/llama3.2:3b", ollama_like)


@pytest.mark.skipif(not os.environ.get("HUTCH_LIVE_OLLAMA"), reason="set HUTCH_LIVE_OLLAMA=http://127.0.0.1:11434")
def test_live_ollama_rows_match_readiness():
    url = os.environ["HUTCH_LIVE_OLLAMA"]
    rows = httpx.get(url + "/api/tags", timeout=5).json()["models"]
    for row in rows:
        want = not (row.get("remote_host") or row.get("remote_model")) and row["size"] > 0
        assert (route_readiness("ollama", row["name"], url).ready is True) == want, row["name"]


def test_fallback_to_a_missing_or_cloud_model_is_refused_before_the_run(ollama_like):
    """EC-28: a fallback rung cannot cross the boundary silently."""
    from types import SimpleNamespace
    from hutch.providers.registry import offline_endpoints_for_bot
    for fallback in ("ollama/gpt-oss:20b-cloud", "ollama/llama3.2:3b"):
        bot = SimpleNamespace(model="ollama/qwen3:4b", base_url=ollama_like, fallbacks=[fallback],
                              escalation=None, task_routes={})
        with pytest.raises(ValueError):
            offline_endpoints_for_bot(bot)
