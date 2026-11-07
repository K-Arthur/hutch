"""Saved model routes: where each one runs, its privacy sentence and its honest status.

Kept apart from the Models view assembly so the page builder stays readable. The
locality label uses the Phase 1 classifier (runtime server signal first, then the
resolved address, then the name only as a fallback); an unknown verdict is shown
as unknown rather than silently treated as local.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .providers.base import ModelMeta
from .providers.locality import LOCAL_PROVIDERS
from .route_problem import model_route_problem


@dataclass
class ConfiguredModelRoute:
    spec: str
    provider: str
    model_id: str
    label: str
    status: str
    is_default: bool
    bots: list[str]
    has_key: bool
    is_local: bool
    locality: str = "cloud"   # machine | network | cloud_via_local | cloud | unknown
    privacy_label: str = ""
    problem: Optional[str] = None


_PRIVACY_LABELS = {
    "machine": "Data stays on this machine.",
    "network": "Data leaves this machine to a service you control.",
    "cloud_via_local": "Data is forwarded to a cloud service through the local runtime.",
    "cloud": "Data is sent to a hosted service.",
    "unknown": "Hutch could not determine where this route runs.",
}


def locality_for_route(spec: str, is_local: bool, conn_base_url: str = "",
                       entry: Optional[dict[str, Any]] = None) -> str:
    if is_local:
        if spec.startswith("ollama/"):
            name = spec.split("/", 1)[-1]
            try:
                from .providers.locality import model_locality
                verdict = model_locality("ollama", name, entry)
                if verdict.local is False:
                    return "cloud_via_local"
                if verdict.local is None:
                    return "unknown"
            except Exception:
                if name.endswith("-cloud") or ":cloud" in name:
                    return "cloud_via_local"
                return "unknown"
        return "machine"
    host = ""
    if conn_base_url:
        try:
            from urllib.parse import urlparse
            host = (urlparse(conn_base_url).hostname or "").lower()
        except Exception:
            host = ""
    if host == "localhost" or host.endswith(".local"):
        return "machine"
    try:
        import ipaddress
        address = ipaddress.ip_address(host)
        if address.is_loopback:
            return "machine"
        if address.is_private:
            return "network"
    except ValueError:
        pass
    return "cloud"


def privacy_label_for(locality: str) -> str:
    return _PRIVACY_LABELS.get(locality, _PRIVACY_LABELS["cloud"])


def _ollama_routes(store: Any, inst: dict[str, ModelMeta], tags_rows: list[dict[str, Any]],
                   used_by: dict[str, list[str]], saved_default: str) -> list[ConfiguredModelRoute]:
    from .providers.locality import find_row
    out: list[ConfiguredModelRoute] = []
    for name in sorted(inst):
        spec = f"ollama/{name}"
        assigned = list(used_by.get(spec, []))
        for b_name in used_by.get(name, []):
            if b_name not in assigned:
                assigned.append(b_name)
        try:
            entry = find_row(tags_rows, name)
        except Exception:
            entry = None
        loc = locality_for_route(spec, True, entry=entry)
        out.append(ConfiguredModelRoute(
            spec=spec, provider="ollama", model_id=name, label=store.kv_get(f"model_label:{spec}") or name,
            status="ready", is_default=spec == saved_default, bots=assigned, has_key=True, is_local=True,
            locality=loc, privacy_label=privacy_label_for(loc),
        ))
    return out


def _connection_routes(store: Any, conn_book: Any, used_by: dict[str, list[str]],
                       saved_default: str) -> list[ConfiguredModelRoute]:
    out: list[ConfiguredModelRoute] = []
    for connection_name, connection in conn_book.configured().items():
        has_key = bool(conn_book.key(connection_name))
        for bot_spec, bot_names in used_by.items():
            if not bot_spec.startswith(f"{connection_name}/"):
                continue
            model_id = bot_spec.split("/", 1)[1]
            loc = locality_for_route(bot_spec, False, connection.base_url)
            out.append(ConfiguredModelRoute(
                spec=bot_spec, provider=connection_name, model_id=model_id,
                label=store.kv_get(f"model_label:{bot_spec}") or f"{connection.title}: {model_id}",
                status="ready" if has_key else "needs_key", is_default=bot_spec == saved_default,
                bots=bot_names, has_key=has_key, is_local=False,
                locality=loc, privacy_label=privacy_label_for(loc),
            ))
    return out


def _extra_routes(store: Any, conn_book: Any, used_by: dict[str, list[str]],
                  saved_default: str, ollama_up: bool, usable_bots: dict[str, bool],
                  seen_specs: set[str]) -> list[ConfiguredModelRoute]:
    out: list[ConfiguredModelRoute] = []
    extra_specs = set(used_by)
    if saved_default:
        extra_specs.add(saved_default)
    extra_specs.update(s.strip() for s in (store.kv_get("configured_model_routes") or "").split(",") if s.strip())
    for bot_spec in sorted(extra_specs):
        if not bot_spec or bot_spec in seen_specs:
            continue
        bot_names = used_by.get(bot_spec, [])
        provider, model_id = bot_spec.split("/", 1) if "/" in bot_spec else ("custom", bot_spec)
        has_key, base_url = True, ""
        if provider in conn_book.names():
            has_key = bool(conn_book.key(provider))
            try:
                base_url = conn_book.get(provider).base_url if conn_book.get(provider) else ""
            except Exception:
                base_url = ""
        problem = model_route_problem(bot_spec)
        usable = any(usable_bots.get(name, False) for name in bot_names)
        if provider == "ollama" and not ollama_up:
            problem = problem or "Ollama is not running, so this route cannot run"
            status = "unusable"
        else:
            status = "unusable" if problem and not usable else ("ready" if has_key else "needs_key")
        is_local = provider in LOCAL_PROVIDERS
        loc = locality_for_route(bot_spec, is_local, base_url)
        out.append(ConfiguredModelRoute(
            spec=bot_spec, provider=provider, model_id=model_id,
            label=store.kv_get(f"model_label:{bot_spec}") or bot_spec,
            status=status, is_default=bot_spec == saved_default, bots=bot_names, has_key=has_key,
            is_local=is_local, locality=loc, privacy_label=privacy_label_for(loc), problem=problem,
        ))
    return out


def _configured_routes(store: Any, conn_book: Any, inst: dict[str, ModelMeta],
                       tags_rows: list[dict[str, Any]], used_by: dict[str, list[str]],
                       saved_default: str, ollama_up: bool,
                       usable_bots: dict[str, bool]) -> list[ConfiguredModelRoute]:
    """Every saved route with its locality, privacy sentence and honest status."""
    ollama = _ollama_routes(store, inst, tags_rows, used_by, saved_default)
    connections = _connection_routes(store, conn_book, used_by, saved_default)
    seen_specs = {route.spec for route in ollama + connections}
    seen_specs.update(route.model_id for route in ollama)
    return ollama + connections + _extra_routes(
        store, conn_book, used_by, saved_default, ollama_up, usable_bots, seen_specs)
