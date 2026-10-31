"""Provider, account and model readiness from local facts only.

Readiness answers "what would happen if this route were selected now?" without executing inference,
refreshing a token or spending money. It never upgrades a state from a listing, and unknown evidence is
reported as capability_unverified rather than available.

States are deliberately explicit so the UI can explain a blocked choice instead of hiding it:
available, needs_authentication, authentication_expired, subscription_restricted, model_unavailable,
endpoint_unavailable, capability_unverified, unsupported_runtime, needs_configuration, blocked_by_policy.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any, Optional

from ..connections import ConnectionBook
from .accounts import account_profile
from .catalog import bundled_catalog
from .pricing import is_local_route
from .registry import parse_spec

STATES = (
    "available", "needs_authentication", "authentication_expired", "subscription_restricted",
    "model_unavailable", "endpoint_unavailable", "capability_unverified", "unsupported_runtime",
    "needs_configuration", "blocked_by_policy",
)

#: Ambient (environment) credentials are accepted only for providers whose own official host is used.
_AMBIENT_VARS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


@dataclass(frozen=True)
class Readiness:
    state: str
    subject: str
    scope: str
    detail: str
    next_action: str = ""

    @property
    def ready(self) -> bool:
        return self.state in ("available", "capability_unverified")


def _make(state: str, subject: str, scope: str, detail: str, next_action: str = "") -> Readiness:
    if state not in STATES:
        raise ValueError("unknown readiness state")
    return Readiness(state=state, subject=subject, scope=scope, detail=detail, next_action=next_action)


def account_readiness(book: ConnectionBook, name: str, *, catalog=None) -> Readiness:
    catalog = catalog or bundled_catalog()
    profile = account_profile(book, name, catalog)
    if profile.status == "needs_configuration":
        return _make("needs_configuration", name, "account", profile.detail)
    provider = catalog.get(profile.provider_id)
    if provider is not None and provider.integration_status == "blocked":
        return _make("blocked_by_policy", name, "account",
                     "Hutch records this provider route as blocked: no supported integration exists.",
                     "Read the research register for the documented alternative.")
    if profile.status == "needs_key":
        env = ""
        conn = book.get(name)
        if conn is not None and conn.api_key_env:
            env = conn.api_key_env
        action = ("Set " + env + " where Hutch starts, or store a key on the connection page."
                  if env else "Store a key on the connection page.")
        return _make("needs_authentication", name, "account", profile.detail, action)
    if profile.status == "needs_sign_in":
        return _make("needs_authentication", name, "account", profile.detail,
                     "Authorize plan use for this account on Connections.")
    if profile.status == "local_service":
        return _make("available", name, "account",
                     "No credential is required; local service availability is checked separately.")
    if profile.billing == "subscription":
        return _make("available", name, "account",
                     "Subscription-backed account configured locally. Plan eligibility and unattended use are the provider's call; Hutch does not claim them here.",
                     "Reserve spend and review the plan terms before scheduling unattended work.")
    return _make("available", name, "account",
                 "Local configuration is complete. This is not a live-availability or capability claim.")


def route_readiness(book: ConnectionBook, spec: str, *, catalog=None,
                    local_services: Optional[dict[str, Any]] = None, env: Optional[dict] = None) -> Readiness:
    catalog = catalog or bundled_catalog()
    env = os.environ if env is None else env
    subject = (spec or "").strip()
    if not subject:
        return _make("needs_configuration", subject, "model",
                     "No model route is selected.", "Choose a model route explicitly.")
    provider_id, _, model = subject.partition("/")
    provider_id = provider_id.strip().lower()
    model = model.strip()
    if provider_id in book.names():
        account = account_readiness(book, provider_id, catalog=catalog)
        if account.state != "available":
            return _make(account.state, subject, "model", account.detail, account.next_action)
        if not model:
            return _make("model_unavailable", subject, "model",
                         "The connection is configured but the route names no model.",
                         "Choose a model id for this connection.")
        return _make("capability_unverified", subject, "model",
                     "Account configuration is complete, but no live request or evidence has verified this "
                     "model on this route in this build.",
                     "Exercise the route through a normal Hutch run; a successful run records tool evidence.")
    if provider_id in _AMBIENT_VARS:
        variable = _AMBIENT_VARS[provider_id]
        if env.get(variable):
            return _make("capability_unverified", subject, "model",
                         "An ambient " + variable + " is present for the official host. Model capability is unverified.",
                         "Prefer a named connection so the account and billing source are explicit.")
        return _make("needs_authentication", subject, "model",
                     "No " + variable + " is set and no named connection provides this provider.",
                     "Add a named connection with its own key, or set " + variable + " for the official host.")
    if provider_id == "opencode":
        # The OpenCode tool resolves these routes on this computer; no Hutch connection or key is involved, and its free
        # models need no account. Nothing is probed here (local facts only), so capability stays unverified.
        if not shutil.which("opencode"):
            return _make("needs_configuration", subject, "model",
                         "The OpenCode command line tool was not found on this computer, so this route cannot run.",
                         "Install OpenCode, or choose a model from another service.")
        return _make("capability_unverified", subject, "model",
                     "Runs through the OpenCode tool on this computer, not a Hutch connection. Models whose name says free "
                     "need no account; what you send them goes to OpenCode's service.",
                     "Exercise the route through a normal Hutch run to verify it.")
    provider = catalog.get(provider_id)
    if provider is not None and provider.integration_status in ("blocked", "retired"):
        return _make("blocked_by_policy", subject, "model",
                     "This provider route is recorded as " + provider.integration_status + ".",
                     "Use a documented alternative; Hutch does not recreate a retired or unsupported flow.")
    if provider is not None and provider.integration_status in ("documented", "deferred"):
        return _make("needs_configuration", subject, "model",
                     "This provider is researched but has no implemented route in this Hutch build.",
                     "See docs/research/2026-10-provider-platform/03-PROVIDER-CAPABILITY-MATRIX.md.")
    if is_local_route(provider_id, model):
        if local_services is None:
            return _make("capability_unverified", subject, "model",
                         "Local route: the service was not probed in this request.")
        detected = local_services.get(provider_id) or {}
        if not detected.get("reachable"):
            return _make("endpoint_unavailable", subject, "model",
                         "No local service answered on the expected loopback endpoint.",
                         "Start the local inference server, or point a custom connection at its endpoint.")
        return _make("capability_unverified", subject, "model",
                     "The local service answered. Model presence and inference capability are not verified by this check.")
    if provider is not None:
        return _make("needs_configuration", subject, "model",
                     "The provider is known but no account or ambient credential resolves this route.",
                     "Add a connection for this provider or correct the model spec.")
    return _make("needs_configuration", subject, "model",
                 "Unknown provider in the model spec.", "Correct the provider prefix; the catalogue lists known identities.")


def provider_readiness(book: ConnectionBook, provider_id: str, *, catalog=None) -> dict:
    catalog = catalog or bundled_catalog()
    provider = catalog.get(provider_id)
    accounts = [name for name, conn in book.configured().items()
                if account_profile(book, name, catalog).provider_id == provider_id]
    states = [account_readiness(book, name, catalog=catalog) for name in sorted(accounts)]
    return {
        "provider": provider_id,
        "title": provider.title if provider else provider_id,
        "category": provider.category if provider else "unknown",
        "integration_status": provider.integration_status if provider else "documented",
        "accounts": [{"name": state.subject, "state": state.state, "detail": state.detail,
                      "next_action": state.next_action} for state in states],
    }


def readiness_json(readiness: Readiness) -> dict:
    return {"state": readiness.state, "subject": readiness.subject, "scope": readiness.scope,
            "detail": readiness.detail, "next_action": readiness.next_action, "ready": readiness.ready}
