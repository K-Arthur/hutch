"""Bounded, version-independent framing helpers for Pi's documented RPC stream.

This module does not enable Pi as a runtime. Hutch still needs an OS sandbox,
an explicitly restricted tool set, and enforceable usage reservations before
it may start the executable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class PiProtocolError(ValueError):
    """The child process violated Pi's JSONL RPC contract."""


class PiJsonlDecoder:
    """Decode Pi records by LF bytes, never by Unicode line separators."""

    def __init__(self, *, max_record_bytes: int = 1_048_576):
        if max_record_bytes < 1:
            raise ValueError("max_record_bytes must be positive")
        self.max_record_bytes = max_record_bytes
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[dict[str, Any]]:
        if not isinstance(chunk, bytes):
            raise TypeError("Pi RPC input must be bytes")
        self._buffer.extend(chunk)
        records: list[dict[str, Any]] = []
        while True:
            boundary = self._buffer.find(b"\n")
            if boundary < 0:
                if len(self._buffer) > self.max_record_bytes:
                    self._buffer.clear()
                    raise PiProtocolError("Pi RPC record exceeded its byte limit")
                break
            if boundary > self.max_record_bytes:
                del self._buffer[: boundary + 1]
                raise PiProtocolError("Pi RPC record exceeded its byte limit")
            raw = bytes(self._buffer[:boundary])
            del self._buffer[: boundary + 1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            if not raw:
                raise PiProtocolError("empty Pi RPC record")
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PiProtocolError("invalid UTF-8 JSON in Pi RPC stream") from exc
            if not isinstance(value, dict):
                raise PiProtocolError("Pi RPC records must be JSON objects")
            records.append(value)
        return records

    def finish(self) -> None:
        """Reject a truncated final record instead of treating it as complete."""
        if self._buffer:
            self._buffer.clear()
            raise PiProtocolError("Pi RPC stream ended in a partial record")


def encode_command(command: str, request_id: str, **fields: Any) -> bytes:
    """Encode one Pi command using the documented `{type, id, ...}` shape."""
    if not isinstance(command, str) or not command:
        raise ValueError("command must be a non-empty string")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("request_id must be a non-empty string")
    if "type" in fields or "id" in fields:
        raise ValueError("command fields cannot override type or id")
    try:
        return (json.dumps({"type": command, "id": request_id, **fields},
                           ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("command fields must be JSON serializable") from exc


@dataclass(frozen=True)
class PiRecord:
    kind: str
    payload: dict[str, Any]
    text_delta: str = ""


class PiRpcProtocol:
    """Correlate command replies and collect only documented completion events.

    A successful `prompt` response is admission, not completion. The run is
    complete only at `agent_settled`; `agent_end` is intentionally insufficient.
    """

    def __init__(self, *, max_output_chars: int = 1_000_000, max_output_chunks: int = 65_536):
        if max_output_chars < 0:
            raise ValueError("max_output_chars cannot be negative")
        if max_output_chunks < 1:
            raise ValueError("max_output_chunks must be positive")
        self.decoder = PiJsonlDecoder()
        self.max_output_chars = max_output_chars
        self.max_output_chunks = max_output_chunks
        self._next_id = 1
        self._pending: dict[str, str] = {}
        self._text: list[str] = []
        self._text_chars = 0
        self.settled = False
        self.prompt_handled = False

    @property
    def text(self) -> str:
        return "".join(self._text)

    @property
    def pending(self) -> dict[str, str]:
        return dict(self._pending)

    def command(self, command: str, **fields: Any) -> bytes:
        request_id = f"hutch-{self._next_id}"
        if self.settled:
            raise PiProtocolError("cannot send a command after agent_settled")
        line = encode_command(command, request_id, **fields)
        self._next_id += 1
        self._pending[request_id] = command
        return line

    def prompt(self, message: str) -> bytes:
        if not isinstance(message, str):
            raise TypeError("prompt message must be text")
        return self.command("prompt", message=message)

    def cancel(self) -> bytes:
        """Request Pi cancellation using its RPC `abort` command."""
        return self.command("abort")

    def feed(self, chunk: bytes) -> list[PiRecord]:
        return [self.accept(record) for record in self.decoder.feed(chunk)]

    def accept(self, payload: dict[str, Any]) -> PiRecord:
        if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
            raise PiProtocolError("Pi RPC record has no string type")
        kind = payload["type"]
        if kind == "response":
            request_id, command = payload.get("id"), payload.get("command")
            # Pi's uncorrelated parser error is explicitly the `parse` command.
            if request_id is None and command == "parse":
                return PiRecord("response", payload)
            if not isinstance(request_id, str) or request_id not in self._pending:
                raise PiProtocolError("Pi returned a response for an unknown request id")
            expected = self._pending[request_id]
            if command != expected:
                raise PiProtocolError("Pi response command does not match its request id")
            if not isinstance(payload.get("success"), bool):
                raise PiProtocolError("Pi response is missing its success flag")
            del self._pending[request_id]
            if expected == "prompt" and payload["success"]:
                data = payload.get("data")
                self.prompt_handled = isinstance(data, dict) and data.get("disposition") == "handled"
            return PiRecord("response", payload)
        if kind == "message_update":
            update = payload.get("assistantMessageEvent")
            if isinstance(update, dict) and update.get("type") == "text_delta":
                delta = update.get("delta")
                if not isinstance(delta, str):
                    raise PiProtocolError("Pi text_delta must contain string text")
                if self._text_chars + len(delta) > self.max_output_chars:
                    raise PiProtocolError("Pi assistant output exceeded its character limit")
                if delta and len(self._text) >= self.max_output_chunks:
                    raise PiProtocolError("Pi assistant output exceeded its chunk limit")
                self._text.append(delta)
                self._text_chars += len(delta)
                return PiRecord("text_delta", payload, delta)
        if kind == "agent_settled":
            self.settled = True
            return PiRecord("settled", payload)
        return PiRecord("event", payload)
