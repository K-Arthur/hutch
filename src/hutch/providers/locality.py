"""Is this model route local? Server signal first, resolved address second, name suffix only as a fallback.

An Ollama server on loopback can list a model whose inference runs on ollama.com (a cloud stub, a renamed copy of one).
The name is therefore a hint, not evidence. The authoritative fields are `remote_host` / `remote_model` on the model's
`/api/tags` entry (checked 2026-11-06 on Ollama 0.40.13 and 0.40.15; see docs/research/2026-11-offline-models/).

Verdicts are tri-state on purpose: ``local=None`` means "could not tell", and callers that enforce a boundary treat
that as not-local while callers that only label may say so in words.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlsplit

#: Providers whose models run on this computer when the endpoint is loopback.
LOCAL_PROVIDERS = {"ollama", "lmstudio", "llamacpp", "llama.cpp", "vllm"}
CLOUD_TAG = re.compile(r"(?:^|[:_-])cloud(?:$|[-_.])", re.IGNORECASE)
_PROBE_TIMEOUT = 2.0


@dataclass(frozen=True)
class Locality:
    local: Optional[bool]       # True, False, or None when unknown
    source: str                 # server_signal | name | endpoint | provider
    reason: str

    def __bool__(self) -> bool:  # `if locality:` is only ever true for a positive local verdict
        return self.local is True


def entry_is_remote(entry: Optional[dict[str, Any]]) -> bool:
    """True when a `/api/tags` entry says the model is served by a remote host."""
    return bool(entry) and bool(entry.get("remote_host") or entry.get("remote_model"))


def model_locality(provider: str, model: str, entry: Optional[dict[str, Any]] = None) -> Locality:
    """Classify one model. ``entry`` is the runtime's own listing row when the caller has it."""
    if provider not in LOCAL_PROVIDERS:
        return Locality(False, "provider", f"{provider} is a hosted provider")
    if entry is not None and entry_is_remote(entry):
        host = entry.get("remote_host") or "a remote host"
        return Locality(False, "server_signal", f"the runtime reports this model is served by {host}")
    if provider == "ollama" and CLOUD_TAG.search(model or ""):
        # No server row to contradict the name: treat as cloud. A renamed cloud copy is caught by the row above.
        return Locality(False, "name", "the model name carries a cloud tag")
    if entry is not None:
        return Locality(True, "server_signal", "the runtime lists this model without a remote host")
    return Locality(True, "provider", f"{provider} runs models on this computer")


def _addresses(host: str) -> list[str]:
    try:
        return [ipaddress.ip_address(host).compressed]
    except ValueError:
        pass
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


def endpoint_locality(base_url: str) -> Locality:
    """Loopback only when the host is, or every address it resolves to is, loopback (EC-02).

    A hostname that resolves is judged by its addresses, not its spelling: `*.localhost` mapped away in /etc/hosts
    or a name that resolves to a LAN or public address is not local. Resolution failure is "unknown".
    """
    host = (urlsplit(base_url or "").hostname or "").lower()
    if not host:
        return Locality(None, "endpoint", "the endpoint has no host")
    try:
        addresses = _addresses(host)
    except OSError:
        return Locality(None, "endpoint", f"{host} did not resolve")
    if addresses and all(ipaddress.ip_address(a.split("%")[0]).is_loopback for a in addresses):
        return Locality(True, "endpoint", f"{host} resolves only to loopback")
    return Locality(False, "endpoint", f"{host} resolves to {', '.join(addresses) or 'nothing'}, not loopback")


def fetch_ollama_entry(base_url: str, model: str, timeout: float = _PROBE_TIMEOUT) -> Optional[dict[str, Any]]:
    """The model's row from the runtime's own `/api/tags`, or None if the runtime is down or lacks the model."""
    try:
        import httpx
        r = httpx.get(base_url.rstrip("/") + "/api/tags", timeout=timeout)
        r.raise_for_status()
        rows = r.json().get("models", [])
    except Exception:
        return None
    wanted = _with_tag(model)
    for row in rows:
        if _with_tag(row.get("name") or row.get("model") or "") == wanted:
            return row
    return None


def _with_tag(name: str) -> str:
    return name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"


def route_locality(provider: str, model: str, base_url: Optional[str]) -> Locality:
    """Full verdict for one route: endpoint address, then the model's own row where the runtime has one."""
    if provider not in LOCAL_PROVIDERS:
        return model_locality(provider, model)
    if base_url:
        where = endpoint_locality(base_url)
        if where.local is not True:
            return where
    entry = fetch_ollama_entry(base_url or "http://127.0.0.1:11434", model) if provider == "ollama" else None
    return model_locality(provider, model, entry)
