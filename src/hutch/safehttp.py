"""One-hop HTTP requests for a credential mediator.

``netguard.safe_get`` is deliberately a read-only fetch that follows a validated redirect chain.
A mediated credential request needs the opposite defaults: any method, one destination, no redirect
following, and caller headers that cannot rewrite the framing. Those rules live here rather than in
``netguard.py`` so the guard stays a pure address policy and this module stays small enough to audit.

The connection is pinned to an address ``resolve_public`` approved, while ``Host`` and SNI keep the
name the URL asked for. A 3xx response is returned as an ordinary result; presenting the credential
to the redirect target is a separate decision made by the caller and the vault's binding.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from .netguard import DEFAULT_MAX_BYTES, Fetched, NetGuardError, resolve_public, screen_url

REQUEST_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})

#: Request bodies are bounded separately from the response cap; a caller that wants a bigger one can
#: raise this deliberately rather than by widening the response limit.
MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024

#: Headers a caller may never set: they change message framing or the destination.
FORBIDDEN_REQUEST_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection", "te", "trailer",
    "upgrade", "proxy-authorization", "proxy-connection", "expect",
})

_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
_CHARSET = re.compile(r"charset=([\w-]+)", re.IGNORECASE)


def checked_request_headers(headers: Optional[dict[str, str]]) -> dict[str, str]:
    """Validate caller-supplied headers; refuse anything that could rewrite the request framing."""
    out: dict[str, str] = {}
    for name, value in (headers or {}).items():
        if not isinstance(name, str) or len(name) > 64 or not _HEADER_NAME.fullmatch(name):
            raise NetGuardError("a request header name is not valid")
        if name.lower() in FORBIDDEN_REQUEST_HEADERS:
            raise NetGuardError(f"the {name.lower()} header may not be set by a caller")
        if not isinstance(value, str) or len(value) > 8192:
            raise NetGuardError(f"the {name.lower()} header has an invalid value")
        if any(char in value for char in "\r\n\x00"):
            raise NetGuardError(f"the {name.lower()} header has an invalid value")
        out[name] = value
    return out


def _decode(body: bytes, content_type: str) -> str:
    match = _CHARSET.search(content_type or "")
    for encoding in ([match.group(1)] if match else []) + ["utf-8"]:
        try:
            return body.decode(encoding, "replace")
        except LookupError:
            continue
    return body.decode("utf-8", "replace")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def safe_request(method: str, url: str, *, timeout: float = 20.0, max_bytes: int = DEFAULT_MAX_BYTES,
                 headers: Optional[dict[str, str]] = None, content: bytes = b"",
                 resolver: Optional[Callable[..., list]] = None,
                 transport: Any = None) -> Fetched:
    """One request to one validated public address, with no redirect following.

    ``resolver`` and ``transport`` exist so tests can supply a fake DNS and an in-memory server;
    production calls use the system resolver and a real HTTP transport.
    """
    import httpx

    verb = (method or "").upper() if isinstance(method, str) else ""
    if verb not in REQUEST_METHODS:
        raise NetGuardError(f"method '{verb or '(none)'}' is not allowed")
    if not isinstance(content, (bytes, bytearray)):
        raise NetGuardError("a request body must be bytes")
    if content and verb in ("GET", "HEAD"):
        raise NetGuardError(f"a {verb} request cannot carry a body")
    if len(content) > MAX_REQUEST_BODY_BYTES:
        raise NetGuardError(f"a request body must be at most {MAX_REQUEST_BODY_BYTES} bytes")
    reason = screen_url(url)
    if reason:
        raise NetGuardError(reason)
    parts = urlsplit(url.strip())
    https = parts.scheme.lower() == "https"
    host = (parts.hostname or "").rstrip(".")
    port = parts.port or (443 if https else 80)
    ip = resolve_public(host, port, resolver)[0]
    netloc = f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
    pinned = parts._replace(netloc=netloc).geturl()
    default_port = (port == (443 if https else 80))
    # Destination headers are applied last: a caller cannot override Host.
    hdrs = {**checked_request_headers(headers), "Host": host if default_port else f"{host}:{port}"}
    ext = {"sni_hostname": host} if https and not _is_ip(host) else {}
    body, truncated = b"", False
    with httpx.Client(transport=transport or httpx.HTTPTransport(), timeout=timeout,
                      follow_redirects=False) as client:
        with client.stream(verb, pinned, headers=hdrs, content=bytes(content) or None,
                           extensions=ext) as resp:
            status, reason_phrase, rheaders = resp.status_code, resp.reason_phrase, dict(resp.headers)
            for chunk in resp.iter_bytes():
                body += chunk
                if len(body) >= max_bytes:
                    body, truncated = body[:max_bytes], True
                    break
    return Fetched(status=status, reason=reason_phrase, headers=rheaders,
                   text=_decode(body, rheaders.get("content-type", "")), url=url.strip(),
                   redirects=[], truncated=truncated, address=ip, body=body)


__all__ = [
    "FORBIDDEN_REQUEST_HEADERS",
    "MAX_REQUEST_BODY_BYTES",
    "REQUEST_METHODS",
    "checked_request_headers",
    "safe_request",
]
