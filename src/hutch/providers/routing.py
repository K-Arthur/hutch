"""One explicit route resolution: provider, account, runtime and model, never guessed.

A saved model spec already names a provider prefix and a model. This module answers the other
questions a person needs before the first send: which named account (or ambient key, or local
service) would pay, with which billing relationship and protocol, under which execution runtime,
and what is still missing. It reads local configuration only: no token is refreshed, no provider is
contacted, and no model, account, endpoint or runtime is ever substituted.

Readiness owns the state vocabulary. This module adds the resolved tuple and the billing-crossing
check a fallback chain must pass before it can change who pays.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Optional

from ..connections import ConnectionBook
from .accounts import account_profile
from .catalog import bundled_catalog
from .readiness import route_readiness
from .registry import is_official_endpoint, parse_spec, resolve_route_endpoint

AMBIENT_VARS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "google": "GEMINI_API_KEY"}
LOCAL_PROVIDERS = ("ollama", "lmstudio", "llamacpp", "llama.cpp", "vllm", "sglang", "inferrs", "ds4", "comfyui")
METERED_BILLING = ("per_token", "credits")


@dataclass(frozen=True)
class RouteResolution:
    """What a spec resolves to now, from local facts only. ``substituted`` is never true here."""

    spec: str
    provider: str
    provider_title: str
    account: str
    account_source: str
    billing: str
    model: str
    runtime: str
    runtime_status: str
    protocol: str
    endpoint: str
    status: str
    detail: str
    next_action: str = ""
    substituted: bool = False

    def json(self) -> dict:
        return asdict(self)


def _runtime_descriptor(runtime: str):
    from ..runtime.registry import RUNTIMES
    return next((item for item in RUNTIMES if item.id == runtime), None)


def _ambient(provider: str, endpoint: str, env: dict) -> tuple[str, str]:
    """(state, source label): an ambient key is usable only for the provider's official host."""
    variable = AMBIENT_VARS.get(provider, "")
    if not variable or not env.get(variable):
        return "", ""
    if is_official_endpoint(provider, endpoint):
        return "present", "ambient environment (" + variable + ")"
    return "withheld", "ambient " + variable + " withheld: this endpoint is not the official host"


def _accounts_for(book: ConnectionBook, provider_id: str, catalog) -> list[str]:
    names = []
    for name in sorted(book.names()):
        try:
            if account_profile(book, name, catalog).provider_id == provider_id:
                names.append(name)
        except Exception:  # noqa: BLE001 - an unreadable account is not a route candidate
            continue
    return names


def _named_connection(book: ConnectionBook, name: str, model: str, catalog):
    profile = account_profile(book, name, catalog)
    connection = book.get(name)
    protocol, endpoint = connection.endpoint_for(model)
    return {
        "provider": profile.provider_id,
        "provider_title": profile.provider_title,
        "account": name,
        "account_source": "named connection",
        "billing": profile.billing,
        "protocol": protocol,
        "endpoint": endpoint,
    }


def _unresolved_account(book: ConnectionBook, provider_id: str, model: str, endpoint: str, env: dict,
                        catalog):
    provider = catalog.get(provider_id)
    title = provider.title if provider else provider_id
    protocol = provider.protocols[0] if provider and provider.protocols else ""
    accounts = _accounts_for(book, provider_id, catalog)
    if accounts:
        return {
            "provider": provider_id, "provider_title": title, "account": "",
            "account_source": "not chosen: " + str(len(accounts)) + " named account(s)",
            "billing": "unknown", "protocol": protocol, "endpoint": endpoint,
        }
    if provider_id in LOCAL_PROVIDERS:
        return {
            "provider": provider_id, "provider_title": title, "account": "local service",
            "account_source": "loopback service", "billing": "free",
            "protocol": protocol, "endpoint": endpoint,
        }
    state, source = _ambient(provider_id, endpoint, env)
    if state == "present":
        return {
            "provider": provider_id, "provider_title": title, "account": provider_id,
            "account_source": source, "billing": "per_token",
            "protocol": protocol, "endpoint": endpoint,
        }
    if state == "withheld":
        return {
            "provider": provider_id, "provider_title": title, "account": "",
            "account_source": source, "billing": "unknown",
            "protocol": protocol, "endpoint": endpoint,
        }
    return {
        "provider": provider_id, "provider_title": title, "account": "",
        "account_source": "no configured account", "billing": "unknown",
        "protocol": protocol, "endpoint": endpoint,
    }


def resolve_route(book: ConnectionBook, spec: str, *, runtime: Any = "builtin", catalog=None,
                  env: Optional[dict] = None, local_services: Optional[dict] = None,
                  base_url: str = "") -> RouteResolution:
    """Resolve one spec without contacting a provider, choosing an account, or changing the route."""
    catalog = catalog or bundled_catalog()
    env = os.environ if env is None else env
    runtime_id = getattr(runtime, "value", runtime) or "builtin"
    text = str(spec or "").strip()
    provider_id, model = parse_spec(text)
    endpoint = resolve_route_endpoint(provider_id, configured=base_url)
    if book.get(provider_id) is not None:
        resolved = _named_connection(book, provider_id, model, catalog)
    else:
        resolved = _unresolved_account(book, provider_id, model, endpoint, env, catalog)
    readiness = route_readiness(book, text, catalog=catalog, local_services=local_services, env=env)
    status, detail, next_action = readiness.state, readiness.detail, readiness.next_action
    if "withheld" in resolved["account_source"]:
        status = "needs_authentication"
        detail = "The ambient key is withheld because this endpoint is not the provider's official host."
        next_action = "Use the official endpoint or create a named connection with its own key."
    descriptor = _runtime_descriptor(runtime_id)
    if (descriptor is None or not descriptor.enabled) and status in ("available", "capability_unverified"):
        label = runtime_id if descriptor is not None else "unknown runtime"
        status = "unsupported_runtime"
        detail = "Runtime '" + label + "' cannot execute this route in this build."
        next_action = "Select the built-in runtime or a registered selectable runtime."
    return RouteResolution(
        spec=text, provider=resolved["provider"], provider_title=resolved["provider_title"],
        account=resolved["account"], account_source=resolved["account_source"],
        billing=resolved["billing"], model=model, runtime=runtime_id,
        runtime_status=descriptor.status if descriptor else "unknown",
        protocol=resolved["protocol"], endpoint=resolved["endpoint"], status=status,
        detail=detail, next_action=next_action, substituted=False,
    )


def billing_crosses(primary: str, following: str) -> bool:
    """True when a hop moves from a subscription allowance to metered billing."""
    return primary == "subscription" and following in METERED_BILLING


def resolve_chain(book: ConnectionBook, bot: Any, *, catalog=None, env: Optional[dict] = None,
                  local_services: Optional[dict] = None) -> list[dict]:
    """Primary, fallbacks and escalation as explicit tuples with a consent flag per hop."""
    runtime = getattr(bot, "runtime", "builtin")
    specs = [("primary", getattr(bot, "model", ""))]
    specs += [("fallback", spec) for spec in (getattr(bot, "fallbacks", None) or [])]
    escalation = getattr(bot, "escalation", None)
    specs += [("escalation", spec) for spec in (getattr(escalation, "to", None) or [])]
    rows = []
    primary_billing = ""
    for index, (role, spec) in enumerate(specs):
        resolution = resolve_route(book, spec, runtime=runtime, catalog=catalog, env=env,
                                   local_services=local_services)
        if index == 0:
            primary_billing = resolution.billing
        rows.append({
            "role": role,
            "resolution": resolution,
            "requires_consent": index > 0 and billing_crosses(primary_billing, resolution.billing),
        })
    return rows
