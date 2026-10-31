"""Shared connection services for onboarding and dashboard connections.

Handles secret key normalisation, storage in private 0600 files, provider terms
acknowledgement, and readiness probes through route_readiness. No credentials
are ever logged, echoed, or stored in SQLite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .connections import ConnectionBook
from .models import iso, utcnow
from .providers.connection import probe_connection_typed
from .route_readiness import MODE_METADATA, ProbeResult

MAX_KEY_BYTES = 4096
BEARER_PREFIX = re.compile(r"^bearer(\s+|$)", re.IGNORECASE)


@dataclass(frozen=True)
class KeyCheck:
    kind: str  # "ok", "empty", "too_long", "malformed"
    value: str = ""
    message: str = ""


@dataclass(frozen=True)
class StoreResult:
    kind: str  # "stored", "invalid", "permission_denied"
    message: str = ""


@dataclass(frozen=True)
class TermsResult:
    kind: str  # "not_needed", "required", "acknowledged", "stale_acknowledged"
    message: str = ""


@dataclass(frozen=True)
class TermsView:
    status: str  # "consent.not_needed", "consent.required", "consent.current", "consent.stale"
    notice: str = ""
    url: str = ""
    digest: str = ""
    acknowledged_at: str = ""


def normalise_and_validate_key(raw: str) -> KeyCheck:
    """Trim whitespace and single Bearer prefix, cap at 4 KiB, reject control chars."""
    if not isinstance(raw, str):
        return KeyCheck("empty", message="API key is required.")
    trimmed = raw.strip()
    if not trimmed:
        return KeyCheck("empty", message="API key cannot be blank.")
    
    # Strip exactly one leading "Bearer " prefix if present
    match = BEARER_PREFIX.match(trimmed)
    if match:
        trimmed = trimmed[match.end():].strip()
    
    if not trimmed:
        return KeyCheck("empty", message="API key cannot be blank.")
    
    encoded = trimmed.encode("utf-8")
    if len(encoded) > MAX_KEY_BYTES:
        return KeyCheck("too_long", message=f"API key is too long (maximum {MAX_KEY_BYTES} bytes).")
    
    # Reject embedded carriage return, newline, or unprintable control characters
    for char in trimmed:
        if ord(char) < 32 and char not in ("\t",):
            return KeyCheck("malformed", message="API key contains invalid control or newline characters.")
            
    return KeyCheck("ok", value=trimmed)


def store_key(book: ConnectionBook, name: str, raw: str, *, prefer_stored: bool = True) -> StoreResult:
    """Validate and store API key into a private 0600 file."""
    check = normalise_and_validate_key(raw)
    if check.kind != "ok":
        return StoreResult("invalid", message=check.message)
    try:
        book.set_key(name, check.value, prefer_stored=prefer_stored)
        return StoreResult("stored")
    except (OSError, PermissionError) as exc:
        return StoreResult("permission_denied", message=f"Could not save key to disk: {exc}")
    except KeyError:
        return StoreResult("invalid", message=f"No connection named '{name}'.")


def probe_connection(book: ConnectionBook, name: str, *, mode: str = MODE_METADATA, model: str = "") -> ProbeResult:
    """Perform a typed probe delegating to providers/connection."""
    return probe_connection_typed(book, name, mode=mode, model=model)


def terms_view(book: ConnectionBook, store: Any, name: str) -> TermsView:
    """Inspect terms acknowledgement status for a connection."""
    conn = book.get(name)
    if conn is None or not conn.terms.requires_ack:
        return TermsView(status="consent.not_needed")
    
    status = book.ack_status(store, name)
    ack_time = ""
    raw = store.kv_get(f"connection_ack:{name}") if hasattr(store, "kv_get") else None
    if raw:
        import json
        try:
            ack_time = json.loads(raw).get("at", "")
        except Exception:
            pass
            
    if status == "ok":
        return TermsView(status="consent.current", notice=conn.terms.notice, url=conn.terms.url,
                         digest=conn.terms.digest, acknowledged_at=ack_time)
    elif status == "stale":
        return TermsView(status="consent.stale", notice=conn.terms.notice, url=conn.terms.url,
                         digest=conn.terms.digest, acknowledged_at=ack_time)
    else:
        return TermsView(status="consent.required", notice=conn.terms.notice, url=conn.terms.url,
                         digest=conn.terms.digest)


def acknowledge_terms(book: ConnectionBook, store: Any, name: str, *, agree: bool) -> TermsResult:
    """Enforce terms agreement and record timestamp + digest."""
    conn = book.get(name)
    if conn is None or not conn.terms.requires_ack:
        return TermsResult("not_needed")
    
    if not agree:
        return TermsResult("required", message="You must agree to the provider terms to proceed.")
        
    book.acknowledge(store, name)
    return TermsResult("acknowledged")


def key_source_view(book: ConnectionBook, name: str) -> str:
    """Return safe descriptor of key source (never the secret)."""
    conn = book.get(name)
    if conn is None:
        return "missing"
    src = book.key_source(name)
    if src.startswith("environment variable"):
        return "secret.operator_managed"
    elif book.has_key(name):
        return "secret.stored"
    return "secret.missing"
