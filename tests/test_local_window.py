"""vLLM and SGLang publish the window they serve as `max_model_len` on every /v1/models entry (vLLM and SGLang
`ModelCard`, checked 2026-11-06). Hutch reports it as the applied window only when `owned_by` names the server.

The servers here are minimal HTTP stand-ins shaped like those responses over real sockets: no vLLM or SGLang is
installed on this host, so this proves Hutch's reading of the documented shape, not a live engine (status stays
implemented-unverified)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from hutch.hardware import Hardware
from hutch.providers.local import adapter_for
from hutch.providers.local.admission import admit_local


def _engine(owner: str, window=8192, model="served-model"):
    body = json.dumps({"object": "list", "data": [{"id": model, "object": "model", "owned_by": owner,
                                                    "root": model, "parent": None, "max_model_len": window}]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.path == "/v1/models"
            payload = body if ok else b"{}"
            self.send_response(200 if ok else 404)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _admit(provider_id, httpd, want=16384):
    return admit_local(provider_id, provider=None, base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                       model="served-model", want=want, min_ctx=4096,
                       hardware=Hardware(ram_total_gb=64, ram_available_gb=48))


@pytest.mark.parametrize("engine", ["vllm", "sglang"])
def test_the_served_window_is_the_applied_window_when_the_server_names_itself(engine):
    httpd = _engine(engine)
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}"
        assert adapter_for(engine, url).loaded()["served-model"].applied_context == 8192
        admission = _admit(engine, httpd)
    finally:
        httpd.shutdown()
    assert not admission.blocked and admission.num_ctx == 8192 and admission.applied == 8192
    assert "8,192 tokens applied" in admission.note and "wanted 16,384" in admission.note


@pytest.mark.parametrize("provider_id,owner", [("vllm", "somebody-else"), ("vllm", "sglang"), ("sglang", "vllm")])
def test_a_window_is_not_claimed_when_the_server_is_not_the_one_asked_for(provider_id, owner):
    httpd = _engine(owner)
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}"
        assert adapter_for(provider_id, url).loaded() == {}
        admission = _admit(provider_id, httpd)
    finally:
        httpd.shutdown()
    assert admission.num_ctx is None and admission.state == "unknown"
    assert "does not report the window" in admission.note


def test_a_window_that_is_not_a_positive_integer_is_not_trusted():
    for window in (None, 0, -5, "8192", True):
        httpd = _engine("vllm", window=window)
        try:
            assert adapter_for("vllm", f"http://127.0.0.1:{httpd.server_address[1]}").loaded() == {}
        finally:
            httpd.shutdown()
