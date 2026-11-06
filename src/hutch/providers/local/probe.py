"""Bounded HTTP for local runtime introspection.

Every request is plain HTTP to an exact loopback host, carries no credential unless the caller
supplied one for this exact origin, refuses redirects, and reads a bounded body. A 401 or 403 is
a result ("this server needs a key"), not an exception, because a key-protected local server is
alive and must never be reported as a dead port.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_RESPONSE_BYTES = 512 * 1024
DEFAULT_TIMEOUT = 0.8


class ProbeError(Exception):
    """A local endpoint could not be read. ``kind`` is unreachable | bad_url | too_large | not_json."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect from a loopback service could leave the machine; refuse it instead."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - stdlib signature
        return None


def verified_loopback_url(url: str) -> str:
    """Return the URL only when it is plain HTTP to an exact loopback host without embedded credentials."""
    try:
        parts = urlsplit(str(url))
    except ValueError:
        raise ValueError("local endpoint is not a valid URL") from None
    if parts.scheme != "http":
        raise ValueError("local discovery endpoints must use plain HTTP")
    if not parts.hostname or parts.hostname.lower() not in LOOPBACK_HOSTS:
        raise ValueError("local discovery endpoints must use an exact loopback host")
    if parts.username is not None or parts.password is not None:
        raise ValueError("local discovery endpoints must not embed credentials")
    if parts.fragment:
        raise ValueError("local discovery endpoints must not carry a fragment")
    return url


def origin(url: str) -> tuple[str, str, int]:
    """(scheme, host, port) used to scope a credential to one exact origin."""
    parts = urlsplit(str(url))
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return (parts.scheme, (parts.hostname or "").lower(), port)


@dataclass
class HttpResult:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except (ValueError, UnicodeError):
            raise ProbeError("not_json", "the service answered but not with JSON") from None


def _request(url: str, *, method: str, body: bytes = b"", timeout: float,
             bearer: str = "", max_bytes: int) -> HttpResult:
    verified_loopback_url(url)
    headers = {"Accept": "application/json", "User-Agent": "hutch/local-runtime"}
    if body:
        headers["Content-Type"] = "application/json"
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, data=body or None, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read(max_bytes + 1)
            status = response.status
            result_headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        payload = exc.read(max_bytes + 1)
        status = exc.code
        result_headers = dict(exc.headers.items()) if exc.headers else {}
    except (TimeoutError, OSError) as exc:
        raise ProbeError("unreachable", f"no service answered ({type(exc).__name__})") from None
    if len(payload) > max_bytes:
        raise ProbeError("too_large", "the local runtime response exceeds the size limit")
    return HttpResult(status=status, body=payload, headers=result_headers)


def get_json(url: str, timeout: float = DEFAULT_TIMEOUT, bearer: str = "",
             max_bytes: int = MAX_RESPONSE_BYTES) -> HttpResult:
    return _request(url, method="GET", timeout=timeout, bearer=bearer, max_bytes=max_bytes)


def post_json(url: str, payload: dict[str, Any], timeout: float = 30.0, bearer: str = "",
              max_bytes: int = MAX_RESPONSE_BYTES) -> HttpResult:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return _request(url, method="POST", body=body, timeout=timeout, bearer=bearer, max_bytes=max_bytes)
