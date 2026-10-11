"""One canonical route identity for authority, observations and qualification.

Hutch already derives a billing/destination identity per model call
(:meth:`hutch.runtime.builtin.BuiltinRuntime._route_identity`) and stores governed
capability observations under a digest of it. Dynamic workflows need the *same* identity
to decide whether a qualification still applies, so the computation lives here once and
both callers use it. Two copies would drift, and a drifted identity would silently
re-validate a qualification against the wrong route.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

def default_endpoint(provider: str, model: str = "") -> str:
    from .providers.openai_compat import PRESET_URLS

    if provider == "ollama":
        return os.environ.get("OLLAMA_HOST") or PRESET_URLS.get(provider, "")
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
    if provider == "openai-compatible":
        return os.environ.get("HUTCH_BASE_URL", "")
    return PRESET_URLS.get(provider, "")


def route_tuple(*, provider: str, model: str, base_url: Optional[str] = None,
                connections: Any = None) -> tuple:
    """The six-part route identity: (name, account, billing, protocol, endpoint, revision).

    ``connections`` is a :class:`hutch.connections.ConnectionBook` when one is available;
    without it the identity falls back to the provider's own endpoint defaults exactly as
    the runtime does.
    """
    conn = connections.get(provider) if connections is not None else None
    if conn:
        protocol, endpoint = conn.endpoint_for(model)
        revision = hashlib.sha256(json.dumps(_asdict(conn), sort_keys=True).encode()).hexdigest()
        return (conn.name, conn.account_id, conn.billing, protocol, endpoint, revision)
    endpoint = base_url or default_endpoint(provider, model)
    return (provider, provider, "per_token", provider, endpoint, "builtin")


def route_revision(route: tuple) -> str:
    return hashlib.sha256(json.dumps(route, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _asdict(conn: Any) -> dict:
    from dataclasses import asdict, is_dataclass

    if is_dataclass(conn):
        return asdict(conn)
    if hasattr(conn, "model_dump"):
        return conn.model_dump()
    return dict(getattr(conn, "__dict__", {}))
