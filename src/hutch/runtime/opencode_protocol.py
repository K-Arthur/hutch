"""Bounded helpers for the installed OpenCode server and permission contract.

Parsing the wire format is not sufficient to enable this runtime. In particular,
OpenCode 2.0.24 documents its event stream as volatile; Hutch keeps execution
disabled until it can retain/reconcile every action and enforce containment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class OpenCodeProtocolError(ValueError):
    """OpenCode returned an event or permission record Hutch cannot verify."""


@dataclass(frozen=True)
class ServerEvent:
    event: str
    data: str
    event_id: str | None = None

    def json_payload(self) -> dict[str, Any]:
        """Decode the OpenAPI `contentMediaType: application/json` data field."""
        try:
            value: Any = json.loads(self.data)
            # OpenCode's OpenAPI marks event data as a JSON-encoded string. Some
            # server builds serialize the JSON value a second time for SSE.
            if isinstance(value, str):
                value = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise OpenCodeProtocolError("OpenCode SSE data is not JSON") from exc
        if not isinstance(value, dict):
            raise OpenCodeProtocolError("OpenCode event payload must be a JSON object")
        return value


class SseDecoder:
    """Incrementally decode bounded UTF-8 Server-Sent Event frames."""

    def __init__(self, *, max_event_bytes: int = 262_144):
        if max_event_bytes < 1:
            raise ValueError("max_event_bytes must be positive")
        self.max_event_bytes = max_event_bytes
        self._line = bytearray()
        self._data: list[str] = []
        self._event = ""
        self._last_id: str | None = None
        self._event_bytes = 0
        self._first_line = True

    def feed(self, chunk: bytes) -> list[ServerEvent]:
        if not isinstance(chunk, bytes):
            raise TypeError("SSE input must be bytes")
        events: list[ServerEvent] = []
        for byte in chunk:
            if byte != 0x0A:
                self._line.append(byte)
                if len(self._line) + self._event_bytes > self.max_event_bytes:
                    self._reset_frame()
                    raise OpenCodeProtocolError("OpenCode SSE event exceeded its byte limit")
                continue
            raw = bytes(self._line)
            self._line.clear()
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                self._reset_frame()
                raise OpenCodeProtocolError("OpenCode SSE stream contains invalid UTF-8") from exc
            if self._first_line:
                self._first_line = False
                line = line.removeprefix("\ufeff")
            self._event_bytes += len(raw) + 1
            if self._event_bytes > self.max_event_bytes:
                self._reset_frame()
                raise OpenCodeProtocolError("OpenCode SSE event exceeded its byte limit")
            if not line:
                event = self._dispatch()
                if event is not None:
                    events.append(event)
                continue
            if line.startswith(":"):
                continue
            field, sep, value = line.partition(":")
            if sep and value.startswith(" "):
                value = value[1:]
            if field == "data":
                self._data.append(value)
            elif field == "event":
                self._event = value
            elif field == "id" and "\x00" not in value:
                self._last_id = value
            # `retry` and extension fields do not affect frame decoding.
        return events

    def _dispatch(self) -> ServerEvent | None:
        event = None
        if self._data:
            event = ServerEvent(self._event or "message", "\n".join(self._data), self._last_id)
        self._data.clear()
        self._event = ""
        self._event_bytes = 0
        return event

    def _reset_frame(self) -> None:
        self._line.clear()
        self._data.clear()
        self._event = ""
        self._event_bytes = 0

    def finish(self) -> None:
        """Reject an incomplete frame so callers can reconcile a disconnect."""
        if self._line or self._data:
            self._reset_frame()
            raise OpenCodeProtocolError("OpenCode SSE stream ended within an event")


@dataclass(frozen=True)
class OpenCodeContract:
    api_version: str
    api_experimental: bool
    event_stream_volatile: bool
    permission_replies: tuple[str, ...]
    permission_fields: tuple[str, ...]

    @classmethod
    def from_openapi(cls, spec: dict[str, Any]) -> "OpenCodeContract":
        """Extract the small set of routes Hutch relies on; fail closed on drift."""
        try:
            paths = spec["paths"]
            schemas = spec["components"]["schemas"]
            info = spec["info"]
            stream = paths["/api/event"]["get"]
            stream_schema = stream["responses"]["200"]["content"]["text/event-stream"]["schema"]
            data_ref = stream_schema["properties"]["data"]["$ref"].rsplit("/", 1)[-1]
            data_schema = schemas[data_ref]
            permission = schemas["Permission.Request"]
            reply = schemas["Permission.Reply"]
            # Also require the installed HTTP API paths, not only detached schemas.
            paths["/api/session/{sessionID}/permission/{requestID}/reply"]["post"]
            paths["/api/session/{sessionID}/prompt"]["post"]
            paths["/api/session/{sessionID}/interrupt"]["post"]
        except (KeyError, TypeError, AttributeError) as exc:
            raise OpenCodeProtocolError("installed OpenCode API is missing a required contract") from exc
        description = str(info.get("description", "")).lower()
        stream_description = str(stream.get("description", "")).lower()
        if data_schema.get("contentMediaType") != "application/json":
            raise OpenCodeProtocolError("OpenCode event data is not declared as JSON")
        fields = tuple(sorted(permission.get("required", [])))
        required_fields = ("action", "id", "resources", "sessionID")
        if not set(required_fields).issubset(fields):
            raise OpenCodeProtocolError("OpenCode permission request omits identity or reviewed arguments")
        decisions = tuple(reply.get("enum", ()))
        if not {"once", "always", "reject"}.issubset(decisions):
            raise OpenCodeProtocolError("OpenCode permission reply vocabulary changed")
        return cls(
            api_version=str(info.get("version", "")),
            api_experimental="experimental" in description,
            event_stream_volatile="volatile" in stream_description and "missed" in stream_description,
            permission_replies=decisions,
            permission_fields=fields,
        )

    @property
    def safe_for_durable_hutch_execution(self) -> bool:
        """A disconnected/overflowed event stream cannot uphold Hutch's receipts."""
        return not self.api_experimental and not self.event_stream_volatile


def permission_reply_body(*, approve_once: bool) -> dict[str, str]:
    """Map one Hutch decision to OpenCode; persistent `always` is never emitted."""
    return {"decision": "once" if approve_once else "reject"}


def parse_permission_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate exact reviewed destination and arguments from Permission.Request."""
    if not isinstance(payload, dict):
        raise OpenCodeProtocolError("OpenCode permission request must be an object")
    for key in ("id", "sessionID", "action"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise OpenCodeProtocolError(f"OpenCode permission request has no {key}")
    resources = payload.get("resources")
    if not isinstance(resources, list) or any(not isinstance(item, str) for item in resources):
        raise OpenCodeProtocolError("OpenCode permission resources must be strings")
    return {
        "id": payload["id"],
        "session_id": payload["sessionID"],
        "action": payload["action"],
        "resources": tuple(resources),
        "message": payload.get("message") if isinstance(payload.get("message"), str) else "",
        "source": payload.get("source"),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }
