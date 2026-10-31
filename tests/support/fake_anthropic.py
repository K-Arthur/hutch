"""The Anthropic Messages API double, split out of tests/fakes.py (a frozen file). Import it from `tests.fakes`, which re-exports it."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional

from tests.fakes import _Server, messages_text, tokens_of


class FakeAnthropic(_Server):
    """/v1/messages, enough of it for the official SDK: SSE message_start .. message_stop."""

    def __init__(self):
        self.script: Callable[[dict], dict] = lambda body: {"content": "ok"}
        self.force_status: Optional[tuple[int, dict, dict]] = None
        self.stall_once = 0.0
        self.first_event_delay_once = 0.0
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
        stop = reply.get("stop_override") or ("refusal" if reply.get("refusal") else
                                              ("tool_use" if calls else "end_turn"))
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
        if self.first_event_delay_once:
            delay, self.first_event_delay_once = self.first_event_delay_once, 0.0
            time.sleep(delay)
        ev("message_start", {"type": "message_start", "message": {**message, "content": [], "stop_reason": None,
                                                                  "usage": {**usage, "output_tokens": 1}}})
        for i, b in enumerate(blocks):
            if b["type"] == "text":
                ev("content_block_start", {"type": "content_block_start", "index": i,
                                           "content_block": {"type": "text", "text": ""}})
                if self.stall_once:
                    delay, self.stall_once = self.stall_once, 0.0
                    time.sleep(delay)
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
