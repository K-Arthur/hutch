"""Scripted fake model servers: Ollama (native API), OpenAI-compatible, and Anthropic /v1/messages.

They speak each wire format as documented, record every request (so tests can assert what was SENT, e.g. that
num_ctx was always present), and can inject the failures that matter: a stream that dies mid-flight, a stall, a
slow cold load, a 500 out-of-memory, a refusal, a 429. They also emulate Ollama's silent front-truncation, so the
context self-check can be exercised for real.

Real-model validation is out of reach on the dev machine (no GPU, no runtime installed); these fakes are the
stand-in, and `docs/local-models.md` says so.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

CHARS_PER_TOKEN = 4


def tokens_of(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def messages_text(messages: list[dict]) -> str:
    return "\n".join(str(m.get("content") or "") for m in messages)


class _Server:
    """Threaded HTTP server base with request recording."""

    def __init__(self):
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def handle(self):
                try:
                    super().handle()
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    # Test clients intentionally close keep-alive/streaming sockets; this is not a server failure.
                    pass

            def log_message(self, *a):  # silence
                pass

            def _body(self) -> dict:
                n = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(n) if n else b"{}"
                try:
                    return json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    return {}

            def do_GET(self):
                outer._route(self, "GET", self.path, {})

            def do_POST(self):
                outer._route(self, "POST", self.path, self._body())

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise RuntimeError("fake provider HTTP server did not stop")

    def record(self, method, path, body, headers=None):
        with self.lock:
            self.requests.append({"method": method, "path": path, "body": body,
                                  "headers": {k.lower(): v for k, v in dict(headers or {}).items()}})

    def of(self, path: str) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["path"] == path]

    # -- response helpers
    @staticmethod
    def send_json(h, obj, status=200, headers=None):
        data = json.dumps(obj).encode()
        h.send_response(status)
        h.send_header("content-type", "application/json")
        h.send_header("content-length", str(len(data)))
        for k, v in (headers or {}).items():
            h.send_header(k, v)
        h.end_headers()
        h.wfile.write(data)

    @staticmethod
    def start_stream(h, ctype):
        h.send_response(200)
        h.send_header("content-type", ctype)
        h.send_header("transfer-encoding", "chunked")
        h.end_headers()

    @staticmethod
    def chunk(h, data: bytes):
        h.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        h.wfile.flush()

    @staticmethod
    def end_stream(h):
        h.wfile.write(b"0\r\n\r\n")
        h.wfile.flush()


# ====================================================================== Ollama

class FakeOllama(_Server):
    """Ollama's native API. ``models`` maps name -> info; ``script`` decides each chat reply."""

    def __init__(self, models: Optional[dict[str, dict]] = None, max_loaded: int = 1, load_delay: float = 0.05):
        self.models = models or {"fake:8b": {}}
        for name, m in self.models.items():
            m.setdefault("params", "8.0B")
            m.setdefault("quant", "Q4_K_M")
            m.setdefault("ctx", 40960)
            m.setdefault("caps", ["completion", "tools"])
            m.setdefault("layers", 36)
            m.setdefault("kv_heads", 8)
            m.setdefault("head_dim", 128)
            m.setdefault("size", 5_000_000_000)
            m.setdefault("template", "{{ .Prompt }}")
        self.loaded: list[str] = []
        self.max_loaded = max_loaded
        self.load_delay = load_delay
        self.script: Callable[[dict], dict] = lambda body: {"content": "ok"}
        self.fail_stream_once = False          # die mid-stream on the first streaming chat
        self.stall_once = 0.0                  # sleep this long mid-stream on the first streaming chat
        self.force_status: Optional[tuple[int, str]] = None
        self.chat_delay = 0.0                  # simulated generation time per call
        self.truncate = True                   # emulate Ollama's silent front-truncation
        self.version = "0.0-fake"
        self.loads: list[tuple[str, float]] = []
        super().__init__()

    # ---- state
    def _ensure_loaded(self, name: str) -> float:
        if name in self.loaded:
            return 0.0
        while len(self.loaded) >= self.max_loaded:
            self.loaded.pop(0)
        time.sleep(self.load_delay)
        self.loaded.append(name)
        self.loads.append((name, self.load_delay))
        return self.load_delay

    def _route(self, h, method, path, body):
        self.record(method, path, body, h.headers)
        if self.force_status and path in ("/api/chat", "/api/generate"):
            code, msg = self.force_status
            return self.send_json(h, {"error": msg}, status=code)
        if path == "/api/version":
            return self.send_json(h, {"version": self.version})
        if path == "/api/tags":
            return self.send_json(h, {"models": [
                {"name": n, "model": n, "size": m["size"], "digest": "sha256:fake",
                 "details": {"parameter_size": m["params"], "quantization_level": m["quant"], "family": "llama"}}
                for n, m in self.models.items()]})
        if path == "/api/ps":
            return self.send_json(h, {"models": [
                {"name": n, "model": n, "size": self.models[n]["size"], "size_vram": 0,
                 "expires_at": "2099-01-01T00:00:00Z"} for n in self.loaded if n in self.models]})
        if path == "/api/show":
            m = self.models.get(body.get("model"))
            if m is None:
                return self.send_json(h, {"error": f"model '{body.get('model')}' not found"}, status=404)
            return self.send_json(h, {
                "license": "Apache License 2.0\nVersion 2.0", "template": m["template"], "capabilities": m["caps"],
                "details": {"parameter_size": m["params"], "quantization_level": m["quant"], "family": "llama"},
                "model_info": {"general.architecture": "llama", "llama.context_length": m["ctx"],
                               "llama.block_count": m["layers"], "llama.attention.head_count": 32,
                               "llama.attention.head_count_kv": m["kv_heads"], "llama.embedding_length": 4096,
                               "llama.attention.key_length": m["head_dim"]}})
        if path == "/api/generate":
            name = body.get("model")
            if name not in self.models:
                return self.send_json(h, {"error": f"model '{name}' not found"}, status=404)
            if body.get("keep_alive") == 0:
                if name in self.loaded:
                    self.loaded.remove(name)
                return self.send_json(h, {"model": name, "done": True, "done_reason": "unload"})
            load = self._ensure_loaded(name)
            return self.send_json(h, {"model": name, "done": True, "done_reason": "load",
                                      "load_duration": int(load * 1e9)})
        if path == "/api/chat":
            return self._chat(h, body)
        self.send_json(h, {"error": "not found"}, status=404)

    def _chat(self, h, body):
        name = body.get("model")
        if name not in self.models:
            return self.send_json(h, {"error": f"model '{name}' not found, try pulling it first"}, status=404)
        load = self._ensure_loaded(name)
        opts = body.get("options") or {}
        num_ctx = int(opts.get("num_ctx") or 4096)       # what real Ollama would default to, silently
        messages = body.get("messages", [])
        full = messages_text(messages)
        evaluated = tokens_of(full)
        seen_text = full
        if self.truncate and evaluated > num_ctx:        # silent truncation from the FRONT
            seen_text = full[-num_ctx * CHARS_PER_TOKEN:]
            evaluated = num_ctx
        reply = self.script({**body, "_seen_text": seen_text, "_full_text": full, "_evaluated": evaluated})
        if self.chat_delay:
            time.sleep(self.chat_delay)
        content = reply.get("content", "")
        calls = [{"function": {"name": c["name"], "arguments": c.get("arguments", {})}}
                 for c in reply.get("tool_calls", [])]
        out_tokens = reply.get("completion_tokens") or tokens_of(content or json.dumps(calls))
        final = {"model": name, "done": True, "done_reason": "length" if reply.get("length") else "stop",
                 "prompt_eval_count": reply.get("prompt_tokens", evaluated), "eval_count": out_tokens,
                 "load_duration": int(load * 1e9), "total_duration": int((load + 0.01) * 1e9),
                 "eval_duration": int(max(out_tokens, 1) / 50.0 * 1e9)}
        if not body.get("stream", True):
            return self.send_json(h, {**final, "message": {"role": "assistant", "content": content,
                                                           **({"tool_calls": calls} if calls else {})}})
        self.start_stream(h, "application/x-ndjson")
        try:
            half = max(1, len(content) // 2)
            self.chunk(h, (json.dumps({"model": name, "message": {"role": "assistant", "content": content[:half]},
                                       "done": False}) + "\n").encode())
            if self.fail_stream_once:
                self.fail_stream_once = False
                h.wfile.flush()
                h.connection.shutdown(2)                 # the connection dies mid-stream
                return
            if self.stall_once:
                t, self.stall_once = self.stall_once, 0.0
                time.sleep(t)
            self.chunk(h, (json.dumps({"model": name, "message": {"role": "assistant", "content": content[half:],
                                                                  **({"tool_calls": calls} if calls else {})},
                                       "done": False}) + "\n").encode())
            self.chunk(h, (json.dumps({**final, "message": {"role": "assistant", "content": ""}}) + "\n").encode())
            self.end_stream(h)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


# =================================================================== OpenAI

class FakeOpenAI(_Server):
    def __init__(self):
        self.script: Callable[[dict], dict] = lambda body: {"content": "ok"}
        self.require_key: Optional[str] = None
        self.reject_stream_options = False
        self.fail_stream_once = False
        self.force_status: Optional[tuple[int, dict, dict]] = None   # status, body, headers
        super().__init__()

    def _route(self, h, method, path, body):
        self.record(method, path, body, h.headers)
        if self.require_key and h.headers.get("authorization") != f"Bearer {self.require_key}":
            return self.send_json(h, {"error": {"message": "Incorrect API key provided"}}, status=401)
        if self.force_status:
            code, obj, hdrs = self.force_status
            return self.send_json(h, obj, status=code, headers=hdrs)
        if path == "/v1/models" or path == "/models":
            return self.send_json(h, {"data": [{"id": "fake-model"}]})
        if path in ("/v1/chat/completions", "/chat/completions"):
            if body.get("stream") and body.get("stream_options") and self.reject_stream_options:
                return self.send_json(h, {"error": {"message": "stream_options is not supported"}}, status=400)
            reply = self.script(body)
            content = reply.get("content", "")
            calls = reply.get("tool_calls", [])
            usage = {"prompt_tokens": reply.get("prompt_tokens", tokens_of(messages_text(body.get("messages", [])))),
                     "completion_tokens": reply.get("completion_tokens", tokens_of(content or "x")),
                     "prompt_tokens_details": {"cached_tokens": reply.get("cached_tokens", 0)}}
            finish = "tool_calls" if calls else ("length" if reply.get("length") else "stop")
            if not body.get("stream"):
                msg = {"role": "assistant", "content": content or None}
                if calls:
                    msg["tool_calls"] = [{"id": f"call_{i}", "type": "function",
                                          "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments", {}))
                                          if not isinstance(c.get("arguments"), str) else c["arguments"]}}
                                         for i, c in enumerate(calls)]
                return self.send_json(h, {"model": body["model"], "choices": [{"message": msg, "finish_reason": finish}],
                                          "usage": usage})
            self.start_stream(h, "text/event-stream")
            ev = lambda obj: self.chunk(h, f"data: {json.dumps(obj)}\n\n".encode())
            if self.fail_stream_once:
                self.fail_stream_once = False
                ev({"choices": [{"delta": {"content": "partial fixture answer"}}]})
                h.connection.shutdown(2)
                return
            half = max(1, len(content) // 2)
            if content:
                ev({"model": body["model"], "choices": [{"delta": {"content": content[:half]}}]})
                ev({"model": body["model"], "choices": [{"delta": {"content": content[half:]}}]})
            for i, c in enumerate(calls):
                raw = c["arguments"] if isinstance(c.get("arguments"), str) else json.dumps(c.get("arguments", {}))
                mid = max(1, len(raw) // 2)          # arguments arrive split across chunks, as in the wild
                ev({"choices": [{"delta": {"tool_calls": [{"index": i, "id": f"call_{i}", "type": "function",
                                                           "function": {"name": c["name"], "arguments": raw[:mid]}}]}}]})
                ev({"choices": [{"delta": {"tool_calls": [{"index": i, "function": {"arguments": raw[mid:]}}]}}]})
            ev({"choices": [{"delta": {}, "finish_reason": finish}]})
            ev({"choices": [], "usage": usage})
            self.chunk(h, b"data: [DONE]\n\n")
            self.end_stream(h)
            return
        self.send_json(h, {"error": {"message": "not found"}}, status=404)


# ================================================================= Anthropic

class FakeAnthropic(_Server):
    """/v1/messages, enough of it for the official SDK: SSE message_start .. message_stop."""

    def __init__(self):
        self.script: Callable[[dict], dict] = lambda body: {"content": "ok"}
        self.force_status: Optional[tuple[int, dict, dict]] = None
        super().__init__()

    def _route(self, h, method, path, body):
        self.record(method, path, body, h.headers)
        if h.headers.get("x-api-key") in (None, "", "bad-key"):
            return self.send_json(h, {"type": "error", "error": {"type": "authentication_error",
                                                                 "message": "invalid x-api-key"}}, status=401)
        if self.force_status:
            code, obj, hdrs = self.force_status
            return self.send_json(h, obj, status=code, headers=hdrs)
        if path != "/v1/messages":
            return self.send_json(h, {"type": "error", "error": {"type": "not_found_error", "message": "nope"}},
                                  status=404)
        reply = self.script(body)
        text = reply.get("content", "")
        calls = reply.get("tool_calls", [])
        usage = {"input_tokens": reply.get("input_tokens", 50), "output_tokens": reply.get("output_tokens", 20),
                 "cache_read_input_tokens": reply.get("cache_read", 0),
                 "cache_creation_input_tokens": reply.get("cache_write", 0)}
        stop = "refusal" if reply.get("refusal") else ("tool_use" if calls else "end_turn")
        blocks: list[dict] = []
        if text:
            blocks.append({"type": "text", "text": text})
        for i, c in enumerate(calls):
            blocks.append({"type": "tool_use", "id": f"toolu_{i}", "name": c["name"], "input": c.get("arguments", {})})
        message = {"id": "msg_fake", "type": "message", "role": "assistant", "model": body["model"],
                   "content": blocks, "stop_reason": stop, "stop_sequence": None, "usage": usage}
        if reply.get("refusal"):
            message["stop_details"] = {"type": "refusal", "category": reply["refusal"], "explanation": "declined"}
        if not body.get("stream"):
            return self.send_json(h, message)
        self.start_stream(h, "text/event-stream")
        ev = lambda name, obj: self.chunk(h, f"event: {name}\ndata: {json.dumps(obj)}\n\n".encode())
        ev("message_start", {"type": "message_start", "message": {**message, "content": [], "stop_reason": None,
                                                                  "usage": {**usage, "output_tokens": 1}}})
        for i, b in enumerate(blocks):
            if b["type"] == "text":
                ev("content_block_start", {"type": "content_block_start", "index": i,
                                           "content_block": {"type": "text", "text": ""}})
                ev("content_block_delta", {"type": "content_block_delta", "index": i,
                                           "delta": {"type": "text_delta", "text": b["text"]}})
            else:
                ev("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                    "type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}})
                raw = json.dumps(b["input"])
                ev("content_block_delta", {"type": "content_block_delta", "index": i,
                                           "delta": {"type": "input_json_delta", "partial_json": raw}})
            ev("content_block_stop", {"type": "content_block_stop", "index": i})
        delta: dict[str, Any] = {"stop_reason": stop, "stop_sequence": None}
        if reply.get("refusal"):
            delta["stop_details"] = message["stop_details"]
        ev("message_delta", {"type": "message_delta", "delta": delta, "usage": {"output_tokens": usage["output_tokens"]}})
        ev("message_stop", {"type": "message_stop"})
        self.end_stream(h)


# ============================================================ scripted agents

def agent_script(replies: list, recall: bool = True):
    """A fake model for the Ollama server: auto-answers the context self-check like a well-behaved long-context
    model (recalling only what survived truncation), and plays ``replies`` in order for everything else.

    A reply is a dict like {"content": "...", "tool_calls": [{"name": ..., "arguments": {...}}]}; the last one
    repeats forever. Returns the script function; ``script.calls`` counts the non-self-check turns.
    """
    import re

    def script(body):
        full = body.get("_full_text", "")
        if "secret code word for this check is" in full:
            m = re.search(r"code word for this check is ([A-Z0-9-]+)", body.get("_seen_text", ""))
            return {"content": m.group(1) if (m and recall) else "I do not know."}
        i = min(script.calls, len(replies) - 1)
        script.calls += 1
        return dict(replies[i])
    script.calls = 0
    return script
