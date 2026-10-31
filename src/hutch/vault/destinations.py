"""Destination bindings: which origins a secret may be presented to.

A grant answers *who* may use a secret. A binding answers *where* the value may go. Both are
required: a bot with ``use`` for an API key cannot send it to an origin the owner never named, and
a binding without a grant helps nobody.

The origin grammar is deliberately narrower than a URL. Bindings are scheme + host + port only;
paths, queries, fragments and embedded credentials are refused rather than stripped, because
normalising them away is how two different destinations end up sharing one row.

The vault does not resolve or screen the host here. ``netguard`` refuses private addresses at
request time, so a binding to a local name is syntactically valid but cannot carry a credential
until Hutch's network policy deliberately permits that origin.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from . import audit as audit_mod
from .core import OWNER
from .model import SecretNotFound, VaultError
from .refs import Principal, parse_secret_id

#: Longest DNS name, plus scheme and a port.
MAX_ORIGIN_CHARS = 253
_DEFAULT_PORTS = {"http": 80, "https": 443}
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class DestinationError(ValueError):
    """An origin is malformed or is not an origin at all. Never carries request content."""


def _host(value: str) -> str:
    """Canonicalise a host: IPv6 in brackets, otherwise lowercase ASCII DNS."""
    value = value.strip().rstrip(".")
    if not value:
        raise DestinationError("A destination needs a host.")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        address = None
    if address is not None:
        return f"[{value.lower()}]" if address.version == 6 else str(address)
    try:
        ascii_host = value.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise DestinationError("That destination host is not a valid name.") from None
    if len(ascii_host) > 253 or any(not _LABEL.fullmatch(label) for label in ascii_host.split(".")):
        raise DestinationError("That destination host is not a valid name.")
    return ascii_host


def _parse(value: object, *, allow_path: bool) -> tuple[str, str, int]:
    if not isinstance(value, str):
        raise DestinationError("A destination must be text.")
    text = value.strip()
    if not text or len(text) > 2048:
        raise DestinationError("A destination must be a non-empty URL.")
    try:
        parts = urlsplit(text)
        _ = parts.port                                  # ValueError on a malformed port
    except ValueError:
        raise DestinationError("That destination has a malformed port.") from None
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise DestinationError("A destination must use http or https.")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise DestinationError("A destination cannot contain credentials.")
    if any(ord(char) < 32 for char in text):
        raise DestinationError("A destination cannot contain control characters.")
    if not allow_path and (parts.path not in ("", "/") or parts.query or parts.fragment):
        raise DestinationError("A destination binding is an origin, not a URL with a path or query.")
    host = _host(parts.hostname or "")
    port = parts.port or _DEFAULT_PORTS[scheme]
    if not 1 <= port <= 65535:
        raise DestinationError("That destination has an invalid port.")
    return scheme, host, port


def canonical_origin(value: object) -> str:
    """A binding or audit form such as ``https://api.example.com`` or ``http://[::1]:8080``."""
    scheme, host, port = _parse(value, allow_path=False)
    suffix = "" if port == _DEFAULT_PORTS[scheme] else f":{port}"
    origin = f"{scheme}://{host}{suffix}"
    if len(origin) > MAX_ORIGIN_CHARS:
        raise DestinationError("That destination is too long.")
    return origin


def request_origin(value: object) -> str:
    """The origin of a request URL. Paths and queries are allowed here and dropped from the audit."""
    scheme, host, port = _parse(value, allow_path=True)
    suffix = "" if port == _DEFAULT_PORTS[scheme] else f":{port}"
    return f"{scheme}://{host}{suffix}"


class DestinationsMixin:
    """Requires ``_VaultCore`` state and ``_secret_row``."""

    def bind_destination(self, secret_id: str, origin: str, *, actor: Principal = OWNER) -> str:
        """Allow this secret to be presented to ``origin``. Owner-only; idempotent."""
        if not actor.is_owner:
            raise VaultError("Only the owner can bind a secret to a destination.")
        sid = parse_secret_id(secret_id)
        canonical = canonical_origin(origin)
        row = self._secret_row(sid)
        if row is None or row["deleted_at"]:
            raise SecretNotFound("That secret does not exist.")
        stamp = self._stamp()
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            db.execute("INSERT OR IGNORE INTO vault_destinations(secret_id, origin, created_at) "
                       "VALUES (?, ?, ?)", (sid, canonical, stamp))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="bind_destination",
                             outcome="ok", reason="ok", secret_id=sid, scope=row["scope"],
                             destination=canonical, at=stamp)
        return canonical

    def unbind_destination(self, secret_id: str, origin: str, *, actor: Principal = OWNER) -> str:
        if not actor.is_owner:
            raise VaultError("Only the owner can unbind a secret from a destination.")
        sid = parse_secret_id(secret_id)
        canonical = canonical_origin(origin)
        row = self._secret_row(sid)
        if row is None:
            raise SecretNotFound("That secret does not exist.")
        stamp = self._stamp()
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            db.execute("DELETE FROM vault_destinations WHERE secret_id = ? AND origin = ?",
                       (sid, canonical))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id,
                             action="unbind_destination", outcome="ok", reason="ok",
                             secret_id=sid, scope=row["scope"], destination=canonical, at=stamp)
        return canonical

    def destinations(self, secret_id: str) -> list[str]:
        sid = parse_secret_id(secret_id)
        with self.store._lock:
            rows = self.store._db.execute(
                "SELECT origin FROM vault_destinations WHERE secret_id = ? ORDER BY origin",
                (sid,)).fetchall()
        return [row["origin"] for row in rows]

    def destination_bound(self, secret_id: str, origin: str) -> bool:
        sid = parse_secret_id(secret_id)
        canonical = canonical_origin(origin)
        with self.store._lock:
            return self.store._db.execute(
                "SELECT 1 FROM vault_destinations WHERE secret_id = ? AND origin = ?",
                (sid, canonical)).fetchone() is not None


__all__ = [
    "DestinationError",
    "DestinationsMixin",
    "canonical_origin",
    "request_origin",
]
