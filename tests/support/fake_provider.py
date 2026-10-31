"""A scripted OpenAI-compatible fake provider for readiness tests.

Separate from tests/fakes.py (frozen). Each scenario sets the status, body, headers
and delay of ``GET /models`` and ``POST /chat/completions`` independently, so a test
can say "200 model list but 401 generation". Every request is recorded with its
headers and body so tests can prove the server, not a browser, made the call.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OK_MODELS = {"data": [{"id": "model-a"}, {"id": "model-b"}]}
OK_CHAT = {"id": "x", "object": "chat.completion", "model": "model-a",
           "choices": [{"index": 0, "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ready"}}],
           "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}}


def error_body(message: str, code: str = "") -> dict:
    return {"error": {"message": message, "code": code}}


class Step:
    """One scripted response for one endpoint."""

    def __init__(self, status=200, body=None, headers=None, delay=0.0, hang=False):
        self.status, self.body, self.headers = status, body, headers or {}
        self.delay, self.hang = delay, hang


class FakeProvider:
    def __init__(self, models: Step | None = None, chat: Step | None = None):
        self.models = models or Step(200, OK_MODELS)
        self.chat = chat or Step(200, OK_CHAT)
        self.requests: list[dict] = []
        self._release = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _send(self, step: Step):
                if step.hang:
                    outer._release.wait(30)
                    return
                if step.delay:
                    time.sleep(step.delay)
                raw = json.dumps(step.body if step.body is not None else {}).encode()
                self.send_response(step.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for key, value in step.headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(raw)

            def _record(self, body: bytes):
                outer.requests.append({"method": self.command, "path": self.path,
                                       "headers": {k.lower(): v for k, v in self.headers.items()},
                                       "body": body.decode("utf-8", "replace")})

            def do_GET(self):
                self._record(b"")
                self._send(outer.models)

            def do_POST(self):
                size = int(self.headers.get("content-length") or 0)
                self._record(self.rfile.read(size) if size else b"")
                self._send(outer.chat)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def paths(self) -> list[str]:
        return [f"{r['method']} {r['path']}" for r in self.requests]

    def close(self) -> None:
        self._release.set()
        self.httpd.shutdown()
        self.httpd.server_close()


def closed_port_url() -> str:
    """A loopback URL nothing is listening on (connection refused)."""
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}/v1"
