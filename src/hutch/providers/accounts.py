"""Authentication profiles: which named account a provider request would use, and its local state.

A Connection already names one endpoint/key pair. This module adds the identity layer the provider
catalogue does not cover: which provider identity that connection belongs to, which authentication
method it represents, what the credential state is, what billing relationship applies, and what a
person can do next. It reads local configuration only: it never refreshes a token, calls a provider,
or spends money.

Multiple accounts for one provider are ordinary named connections (for example `openai-personal` and
`openai-work`). Grouping them by provider identity is a view, not a second credential store, so a
selection stays explicit in every model spec (`connection/model`) and survives restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..connections import Connection, ConnectionBook, load_templates
from .catalog import Provider, bundled_catalog

#: Local account states. None of these claims the provider works; they describe local readiness.
ACCOUNT_STATES = ("ready", "needs_key", "needs_sign_in", "needs_configuration", "local_service")

_BILLING_LABELS = {
    "per_token": "Per-token API billing",
    "subscription": "Subscription allowance",
    "credits": "Credits",
    "free": "Local or free service",
    "unknown": "Billing not reported",
}
_AUTH_LABELS = {
    "api_key": "API key",
    "pkce": "OAuth sign-in (PKCE)",
    "oauth": "OAuth sign-in",
    "device_code": "Device code",
    "cli_managed": "CLI-managed sign-in",
    "service_account": "Cloud service credentials",
    "custom_endpoint": "Endpoint credential",
    "local_service": "Loopback service",
}


@dataclass(frozen=True)
class AccountProfile:
    """One named account, resolved against the provider catalogue. No secret is ever included."""

    name: str
    title: str
    provider_id: str
    provider_title: str
    provider_category: str
    provider_status: str
    auth_method: str
    auth_label: str
    billing: str
    billing_label: str
    credential: str          # present | missing | not_required
    credential_source: str   # human-readable source, never the value
    endpoint: str
    protocol: str
    status: str              # one of ACCOUNT_STATES
    detail: str

    @property
    def usable_locally(self) -> bool:
        """Local configuration is complete. This is not a provider availability or capability claim."""
        return self.status == "ready"


@dataclass(frozen=True)
class ProviderAccounts:
    """All configured accounts for one provider identity, plus the provider entry when it is known."""

    provider_id: str
    provider: Optional[Provider]
    accounts: tuple[AccountProfile, ...]


def auth_method_for_connection(conn: Connection) -> str:
    """The mechanism label for a connection, from its template metadata or its auth flow."""
    if conn.auth_type == "chatgpt-siws":
        return "pkce"
    template = load_templates().get(conn.template) or {}
    return str(template.get("auth_method") or "api_key")


def provider_for_connection(conn: Connection, catalog=None) -> Optional[Provider]:
    """Resolve the provider identity behind a connection without inventing one.

    The bundled connection template is the single identity authority for a connection; row-level
    metadata cannot mint a second one. Known special cases cover the supported ChatGPT route and custom
    compatible endpoints. An unknown identity returns None so the account is reported as needing
    configuration instead of being guessed.
    """
    catalog = catalog or bundled_catalog()
    by_template = catalog.provider_for_template(conn.template)
    if by_template is not None:
        return by_template
    if conn.auth_type == "chatgpt-siws":
        return catalog.get("openai")
    if conn.template.startswith("custom-"):
        return catalog.get("custom-compatible")
    return None


def _credential(book: ConnectionBook, conn: Connection) -> tuple[str, str]:
    """(state, source label). Source labels name where a credential lives, never the secret."""
    if conn.billing == "free":
        return "not_required", "no credential: local or free route"
    if conn.auth_type == "chatgpt-siws":
        present = book.has_key(conn.name)
        return ("present", "protected ChatGPT account credential") if present else ("missing", "missing")
    if book.has_key(conn.name):
        return "present", book.key_source(conn.name)
    return "missing", "missing"


def account_profile(book: ConnectionBook, name: str, catalog=None) -> AccountProfile:
    """Resolve one configured connection into an explicit account profile. Raises KeyError if absent."""
    conn = book.get(name)
    if conn is None:
        raise KeyError(name)
    catalog = catalog or bundled_catalog()
    provider = provider_for_connection(conn, catalog)
    credential, source = _credential(book, conn)
    auth_method = auth_method_for_connection(conn)
    auth_label = _AUTH_LABELS.get(auth_method, auth_method)
    if provider is not None:
        # Catalogue auth ids are provider-specific ("api-key", "chatgpt-sign-in"); the connection
        # carries a mechanism ("api_key", "pkce"). Match by id first, then by declared mechanism.
        declared = provider.auth(auth_method) or next(
            (method for method in provider.auth_methods if method.type == auth_method), None)
        if declared is not None:
            auth_label = declared.label
    if provider is None:
        status = "needs_configuration"
        detail = ("Hutch cannot map this connection to a known provider identity. Keep using it as an explicit "
                  "connection, or recreate it from a template so its accounts can be grouped and reported.")
        provider_id, provider_title, category, provider_status = "unknown", "Unknown provider", "compatible_endpoint", "documented"
    else:
        provider_id, provider_title = provider.id, provider.title
        category, provider_status = provider.category, provider.integration_status
        if conn.auth_type == "chatgpt-siws" and credential == "missing":
            status = "needs_sign_in"
            detail = "Plan-use permission is missing for this ChatGPT account. Authorize it on Connections."
        elif credential == "missing":
            env_hint = f"set {conn.api_key_env} where Hutch starts, or store a key on Connections" if conn.api_key_env \
                else "store a key on Connections"
            status = "needs_key"
            detail = f"No local credential found: {env_hint}."
        elif conn.billing == "free":
            status = "local_service"
            detail = "No credential is required. Service availability depends on the local process, not on this account."
        else:
            status = "ready"
            detail = f"Credential source: {source}. A configured credential is not a live-availability claim."
    return AccountProfile(
        name=conn.name, title=conn.title, provider_id=provider_id, provider_title=provider_title,
        provider_category=category, provider_status=provider_status, auth_method=auth_method,
        auth_label=auth_label, billing=conn.billing, billing_label=_BILLING_LABELS.get(conn.billing, conn.billing),
        credential=credential, credential_source=source, endpoint=conn.base_url, protocol=conn.protocol,
        status=status, detail=detail,
    )


def account_profiles(book: ConnectionBook, catalog=None) -> list[AccountProfile]:
    """Every configured account, ordered by provider identity then account title."""
    catalog = catalog or bundled_catalog()
    profiles = [account_profile(book, name, catalog) for name in sorted(book.names())]
    return sorted(profiles, key=lambda profile: (profile.provider_title.lower(), profile.title.lower(), profile.name))


def provider_groups(book: ConnectionBook, catalog=None) -> list[ProviderAccounts]:
    """Configured accounts grouped under their provider identity, in provider-title order."""
    catalog = catalog or bundled_catalog()
    grouped: dict[str, list[AccountProfile]] = {}
    for profile in account_profiles(book, catalog):
        grouped.setdefault(profile.provider_id, []).append(profile)
    groups = [
        ProviderAccounts(provider_id=provider_id, provider=catalog.get(provider_id),
                         accounts=tuple(accounts))
        for provider_id, accounts in grouped.items()
    ]
    return sorted(groups, key=lambda group: ((group.provider.title if group.provider else group.provider_id).lower(),
                                             group.provider_id))


def rename_account(book: ConnectionBook, name: str, title: str) -> Connection:
    """Change the local display name of an account. The connection name (used in specs) is unchanged."""
    conn = book.get(name)
    if conn is None:
        raise KeyError(name)
    cleaned = " ".join(str(title or "").split())
    if not cleaned or len(cleaned) > 120:
        raise ValueError("account name must be non-empty and at most 120 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        raise ValueError("account name must not contain control characters")
    return book.update(name, title=cleaned)


def disconnect_local(book: ConnectionBook, name: str) -> dict:
    """Remove Hutch's local credential for one account and report exactly what was and was not done.

    Provider-side revocation is a separate act. Hutch requests it only where an official revoke endpoint
    is implemented for that account type; this function never pretends a key was revoked upstream.
    """
    conn = book.get(name)
    if conn is None:
        raise KeyError(name)
    if conn.auth_type == "chatgpt-siws":
        return {
            "name": name,
            "local_credentials_removed": False,
            "provider_revocation_requested": False,
            "detail": ("ChatGPT plan credentials belong to the Sign in with ChatGPT account store. Disconnect the "
                       "account from the ChatGPT account section so Hutch can clear the protected credential and ask "
                       "the provider to revoke it."),
        }
    had_key = bool(book.has_key(name))
    book.clear_key(name)
    if had_key:
        detail = ("Hutch removed its local key only. Revoke that key in the provider's console if you cannot account "
                  "for what it could have reached.")
    else:
        detail = "No local key was stored for this connection; nothing was removed."
    return {"name": name, "local_credentials_removed": had_key,
            "provider_revocation_requested": False, "detail": detail}
