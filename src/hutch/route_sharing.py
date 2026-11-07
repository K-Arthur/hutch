"""Per-assistant data-sharing confirmation for non-local model routes (EC-28).

Switching an assistant to a route that leaves the machine is a data-sharing
change. It needs an explicit, recorded confirmation naming the assistant, the
route and what moves; a local route needs none. The confirmation is consumed by
the save that follows it, so switching back later asks again instead of
silently reusing an old consent.

Locality comes from the Phase 1 classifier (server signal first, address second,
name only as a fallback), so a renamed cloud copy is not mistaken for a local
model just because its tag has no cloud suffix.
"""

from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlsplit

from .models import iso, utcnow

DISCLOSURE_VERSION = "2026-11-06"
SCOPES = ("default", "override")
LOCAL_RUNTIME_PROVIDERS = {"ollama", "lmstudio", "llamacpp", "llama.cpp", "vllm", "sglang"}


@dataclass(frozen=True)
class SharingDisclosure:
    spec: str
    locality: str                 # network | cloud_via_local | cloud
    title: str
    body: str
    digest: str

    def to_json(self) -> dict[str, Any]:
        return {"spec": self.spec, "locality": self.locality, "title": self.title,
                "body": self.body, "digest": self.digest}


class SharingRequired(Exception):
    """A non-local route change without a matching, unused confirmation."""

    def __init__(self, disclosure: SharingDisclosure):
        self.disclosure = disclosure
        super().__init__(
            f"{disclosure.title}: confirm the data-sharing notice for {disclosure.spec} before changing this assistant")


def _endpoint_kind(base_url: str) -> str:
    """machine | network | cloud | unknown for the endpoint host, independent of the provider."""
    if not base_url:
        return "unknown"
    from .providers.locality import endpoint_locality
    verdict = endpoint_locality(base_url)
    if verdict.local is True:
        return "machine"
    if verdict.local is None:
        return "unknown"
    host = (urlsplit(base_url).hostname or "").lower()
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        import ipaddress
        if addresses and all(ipaddress.ip_address(address.split("%")[0]).is_private for address in addresses):
            return "network"
    except (OSError, ValueError):
        pass
    return "cloud"


def _route_kind(spec: str, base_url: str) -> tuple[str, str]:
    provider = spec.split("/", 1)[0] if "/" in spec else ""
    endpoint = _endpoint_kind(base_url)
    if provider in LOCAL_RUNTIME_PROVIDERS:
        from .providers.locality import route_locality
        verdict = route_locality(provider, spec.split("/", 1)[-1], base_url or None)
        if verdict.local is True:
            return "machine", verdict.reason
        if endpoint == "network":
            return "network", verdict.reason
        return "cloud_via_local", verdict.reason
    if endpoint == "machine":
        # A gateway defined on loopback: EC-28's boundary is the non-loopback route.
        return "machine", f"{provider} is reached only on loopback"
    if endpoint == "network":
        return "network", f"{provider} runs on a server on this network"
    return "cloud", f"{provider} is a hosted provider"


def _endpoint(bot: Any, provider: str, config: Any) -> tuple[str, str]:
    """(base url, human label) for the route: a configured connection wins, then the bot's own URL."""
    try:
        from .connections import ConnectionBook
        connection = ConnectionBook(config.state_dir).get(provider)
    except Exception:
        connection = None
    if connection is not None:
        return connection.base_url, connection.title or provider
    if provider in LOCAL_RUNTIME_PROVIDERS:
        return str(getattr(bot, "base_url", "") or ""), provider
    return "", provider


def _copy(kind: str, name: str, provider: str) -> tuple[str, str]:
    if kind == "network":
        return ("This model runs on another machine",
                f"{name} sends this chat, its files and images to {provider} on another machine on your network. "
                "Data leaves this computer; Hutch cannot control what that server keeps.")
    if kind == "cloud_via_local":
        return ("This model runs on a cloud service",
                f"{name} sends this chat, its files and images to {provider} through the model runtime on this "
                "machine. The runtime forwards them to a cloud service; Hutch cannot see what that service keeps.")
    return ("This model runs on a hosted service",
            f"{name} sends this chat, its files and images to {provider}. Data leaves this computer; "
            "Hutch cannot control what that service keeps.")


def disclosure_for(bot: Any, spec: str, config: Any) -> Optional[SharingDisclosure]:
    """The disclosure a non-local route needs, or None when the route stays on this machine."""
    spec = str(spec or "").strip()
    if "/" not in spec:
        return None
    provider = spec.split("/", 1)[0]
    base_url, label = _endpoint(bot, provider, config)
    kind, _reason = _route_kind(spec, base_url)
    if kind == "machine":
        return None
    name = str(getattr(bot, "display_name", "") or getattr(bot, "name", "") or "This assistant")
    title, body = _copy(kind, name, label)
    digest = hashlib.sha256(
        json.dumps({"v": DISCLOSURE_VERSION, "bot": getattr(bot, "id", ""), "spec": spec,
                    "locality": kind, "title": title, "body": body},
                   sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return SharingDisclosure(spec=spec, locality=kind, title=title, body=body, digest=digest)


def _ack_key(bot_id: str, scope: str) -> str:
    return f"model_sharing_ack:{bot_id}:{scope}"


def record_ack(store: Any, bot_id: str, spec: str, scope: str, disclosure: SharingDisclosure) -> None:
    if scope not in SCOPES:
        raise ValueError(f"unknown sharing scope: {scope}")
    store.kv_set(_ack_key(bot_id, scope), json.dumps(
        {"spec": spec, "digest": disclosure.digest, "at": iso(utcnow())}))


def consume_ack(store: Any, bot_id: str, spec: str, scope: str, disclosure: SharingDisclosure) -> bool:
    """Consume one matching confirmation; a missing, stale or mismatched row is a refusal."""
    raw = store.kv_get(_ack_key(bot_id, scope))
    if not raw:
        return False
    try:
        row = json.loads(raw)
    except (ValueError, TypeError):
        store.kv_set(_ack_key(bot_id, scope), "")
        return False
    if row.get("spec") != spec or row.get("digest") != disclosure.digest:
        return False
    store.kv_set(_ack_key(bot_id, scope), "")
    return True


def require_model_sharing(store: Any, bot: Any, spec: str, scope: str, config: Any) -> None:
    """Refuse a non-local route change until the matching confirmation has been recorded."""
    disclosure = disclosure_for(bot, spec, config)
    if disclosure is None:
        return
    if consume_ack(store, bot.id, spec, scope, disclosure):
        return
    raise SharingRequired(disclosure)
