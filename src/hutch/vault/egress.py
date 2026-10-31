"""Mediated credential egress: use a secret without returning it.

This is the only module that takes a decrypted value from ``VaultBook`` and performs an operation
with it. The rules it exists to keep:

* The value is applied to one header of one request to one origin the owner bound to the secret.
* A redirect is never followed. The caller sees the 3xx and must make a new, separately authorized
  request; a credential is therefore never presented to a host the owner did not name.
* The response is scrubbed of the exact credential before it is returned. A service that echoes an
  ``Authorization`` header in an error body must not turn a mediated use into a disclosure.
* Nothing here returns a ``UsableSecret``. The caller receives a ``MediatedResponse`` whose fields
  are status, headers, body and destination.

The mediator is not a network sandbox. An agent with a shell can still make its own requests, and a
service endpoint reachable with a credential is reachable through this tool. Neither claim is made
in the documentation; see ``security-limitations.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..netguard import NetGuardError
from ..safehttp import safe_request
from .destinations import request_origin
from .model import VaultError
from .refs import Principal

MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_HEADER_VALUE_BYTES = 8192
MAX_PREFIX_CHARS = 32

ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
FORBIDDEN_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding", "connection", "te", "trailer",
    "upgrade", "proxy-authorization", "cookie", "set-cookie",
})
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,64}\Z")
_CONTENT_TYPE = re.compile(r"[a-z0-9.+-]+/[a-z0-9.+-]+(?:; ?charset=[a-z0-9._-]+)?\Z")
_DROP_RESPONSE_HEADERS = frozenset({"set-cookie", "authorization", "proxy-authenticate"})


class EgressError(VaultError):
    """A mediated request was refused before or during the operation. Carries no value."""


@dataclass(frozen=True)
class MediatedResponse:
    status: int
    reason: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    url: str = ""
    destination: str = ""
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def __repr__(self) -> str:
        return f"<MediatedResponse {self.status} {self.destination} redacted>"


def _header_value(value: str) -> str:
    if any(char in value for char in "\r\n\x00"):
        raise EgressError("The credential contains characters that cannot be sent in a header.")
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise EgressError("The credential contains non-ASCII characters, which a header cannot carry.") from None
    if len(value) > MAX_HEADER_VALUE_BYTES:
        raise EgressError("The credential is too large for a request header.")
    return value


def _content_type(value: str) -> str:
    if not value:
        return ""
    text = value.strip().lower()
    if len(text) > 100 or not _CONTENT_TYPE.fullmatch(text):
        raise EgressError("That content type is not supported.")
    return text


def _scrub(text: str, secret: str) -> str:
    """Remove the exact credential from a response. A service must not be able to echo it back."""
    return text.replace(secret, "[redacted]") if secret else text


def mediate_http(vault, *, ref, principal: Principal, method: str, url: str,
                 header_name: str = "Authorization", value_prefix: str = "Bearer ",
                 body: str = "", content_type: str = "", timeout: float = 20.0,
                 max_bytes: int = MAX_RESPONSE_BYTES,
                 resolver=None, transport=None) -> MediatedResponse:
    """Present one vault secret to one bound origin and return the service's response.

    ``vault`` is a ``VaultBook``; the caller must have already checked that the principal may use
    the reference and that the URL is acceptable to policy. Those are separate decisions and this
    function does not hide them: it enforces the grant and the destination binding itself, so a
    caller that forgets one still cannot exfiltrate a value.

    The audit row written by ``resolve_for_use`` says the value was **released** to a mediator for
    this origin. It does not say the service accepted it: a network failure after release is
    reported to the caller, not rewritten into the audit. Read the two together when investigating.
    """
    verb = (method or "").upper() if isinstance(method, str) else ""
    if verb not in ALLOWED_METHODS:
        raise EgressError("That HTTP method is not supported.")
    if not isinstance(header_name, str) or not _HEADER_NAME.fullmatch(header_name):
        raise EgressError("That header name is not valid.")
    if header_name.lower() in FORBIDDEN_HEADERS:
        raise EgressError("That header is set by Hutch, not by a credential.")
    if not isinstance(value_prefix, str) or len(value_prefix) > MAX_PREFIX_CHARS:
        raise EgressError("A credential prefix must be at most 32 characters.")
    if any(ord(char) < 32 or ord(char) > 126 for char in value_prefix):
        raise EgressError("A credential prefix must be printable ASCII.")
    if not isinstance(body, str):
        raise EgressError("A request body must be text.")
    payload = body.encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise EgressError(f"A request body must be at most {MAX_REQUEST_BYTES} bytes.")
    if payload and verb in ("GET", "HEAD"):
        raise EgressError(f"A {verb} request cannot carry a body.")
    kind = _content_type(content_type)

    destination = request_origin(url)
    usable = vault.resolve_for_use(ref, principal, destination=destination)
    secret = usable.value()
    try:
        headers = {header_name: _header_value(f"{value_prefix}{secret}")}
        if kind:
            headers["Content-Type"] = kind
        try:
            fetched = safe_request(verb, url, timeout=timeout, max_bytes=max_bytes,
                                   headers=headers, content=payload,
                                   resolver=resolver, transport=transport)
        except NetGuardError as exc:
            raise EgressError(f"The request was blocked: {exc}") from None
        except Exception as exc:  # timeouts, TLS failures; the type is useful, the message is not trusted
            raise EgressError(f"The request failed ({type(exc).__name__}).") from None
        response_headers = {
            name: _scrub(value, secret)
            for name, value in fetched.headers.items()
            if name.lower() not in _DROP_RESPONSE_HEADERS
        }
        return MediatedResponse(
            # The reason phrase is server-controlled text like the body, so it is scrubbed too: a
            # hostile service that echoes an Authorization header would otherwise put it in a
            # status line the model reads.
            status=fetched.status, reason=_scrub(fetched.reason, secret), headers=response_headers,
            body=_scrub(fetched.text, secret), url=fetched.url, destination=destination,
            truncated=fetched.truncated,
        )
    finally:
        # Drop this frame's reference so the string can be collected sooner. Python strings are
        # immutable and cannot be overwritten, so this shortens the lifetime of one reference and
        # is not memory cleansing; ``security-limitations.md`` §12 says the same about key buffers.
        del usable, secret


__all__ = [
    "ALLOWED_METHODS",
    "EgressError",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "MediatedResponse",
    "mediate_http",
]
