"""Provider identity catalogue: who a provider is, apart from how Hutch talks to it.

The existing layers each answer a narrower question: a Connection names an endpoint and a key, a
protocol adapter speaks one wire format, a runtime executes work, and the compatibility matrix records
request-level behavior for a route. None of them says what a *provider* is, which services and auth
methods it offers, which of those Hutch actually implements, or which routes stay research-only.

This module is that identity layer. It is declarative data (`hutch/data/providers.json`) validated
strictly so it cannot drift into unverified claims:

* one provider may expose several services, protocols and authentication methods;
* an endpoint or subscription service that is billed and credentialed separately keeps its own identity
  (for example OpenCode Go, Bedrock and Google Vertex are separate catalogue entries);
* every entry declares an integration status from a closed vocabulary, and `implemented`/`implemented-
  unverified` requires at least one connection template or runtime that actually exists;
* capability claims live in the evidence-backed capability registry, not here; this catalogue records
  only which service families the provider offers.

Nothing in this module makes a network request, reads a credential, or changes which model runs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

FORMAT_VERSION = 1

#: What kind of service the provider is. A gateway is not a model vendor; an enterprise cloud is not
#: a local runtime; keeping them distinct prevents "supported provider" from implying "verified model".
CATEGORIES = (
    "vendor",               # publishes models and serves them through its own API
    "serving_platform",     # serves models (own or third-party) behind a compatible API
    "gateway",              # routes to other providers and may rewrite the model that answers
    "enterprise_cloud",     # cloud-hosted route with cloud-native credentials and billing
    "subscription_service", # an entitlement/plan rather than a plain API key
    "local_runtime",        # runs inference or media on this machine
    "media_platform",       # image/video/audio/music/speech generation or understanding service
    "compatible_endpoint",  # an operator-supplied endpoint speaking an existing protocol
)

#: How a person authenticates. Values are deliberately mechanism-level: "api_key" and "pkce" are
#: not interchangeable, and a subscription sign-in is not an API key.
AUTH_TYPES = (
    "api_key",
    "oauth",
    "pkce",
    "device_code",
    "cli_managed",
    "service_account",
    "environment",
    "local_service",
    "custom_endpoint",
)

AUTH_STATUSES = ("implemented", "experimental", "documented", "blocked", "retired", "deferred")

#: What the credential pays for. A subscription allowance and per-token API billing are never merged.
BILLING_MODES = ("per_token", "subscription", "credits", "free", "unknown")

PROTOCOLS = ("openai-chat", "openai-responses", "anthropic", "gemini", "ollama-native", "custom")

SERVICE_TAGS = (
    "chat", "responses", "embeddings", "images", "image_editing", "video", "music",
    "audio_generation", "speech", "transcription", "realtime", "search", "grounding",
    "code_execution", "coding_runtime", "coding_cli", "tools", "batch",
)

INTEGRATION_STATUSES = (
    "implemented",            # real code path, focused tests pass, exercised live
    "implemented-unverified", # real code path, no live account was available
    "experimental",           # implemented but explicitly gated / not production-ready
    "documented",             # research only; Hutch has no code path yet
    "blocked",                # legitimate integration is impossible now; reason recorded
    "retired",                # provider removed the flow; Hutch must not recreate it
    "deferred",               # requested, in scope, not delivered in this package
)

#: (short label, one-line meaning) for a person reading a page, not for a schema. The status ids above
#: stay the stored vocabulary; a raw id like "implemented-unverified" is not shown as a badge title.
STATUS_TEXT: dict[str, tuple[str, str]] = {
    "implemented": ("works",
                    "Hutch has a real code path for this route and a dated live account exercised it."),
    "implemented-unverified": ("route only, untested",
                               "Hutch can reach this service, but no live account has run a request through it."),
    "experimental": ("experimental, gated",
                     "Implemented and gated: expected to work, not production-ready, and may change."),
    "documented": ("not built",
                   "Researched only. Hutch has no code path, so there is nothing to connect yet."),
    "blocked": ("blocked by provider",
                "The provider forbids or no longer supports this for Hutch. The reason is recorded; it is not imitated."),
    "retired": ("retired by provider",
                "The provider removed this flow. Hutch does not recreate a retired route."),
    "deferred": ("deferred, not built",
                 "Requested and in scope, but not delivered in this package."),
}

MAX_CATALOG_BYTES = 512 * 1024
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

_PROVIDER_KEYS = {
    "id", "title", "category", "summary", "services", "protocols", "auth", "docs",
    "integration_status", "connection_templates", "regions", "notes",
}
_AUTH_KEYS = {"id", "type", "label", "billing", "status", "docs", "notes"}
_DOC_KEYS = {"title", "url", "observed_on"}


class CatalogError(ValueError):
    """The provider catalogue is malformed or makes an unverifiable claim."""


@dataclass(frozen=True)
class ProviderDoc:
    title: str
    url: str
    observed_on: str


@dataclass(frozen=True)
class AuthMethod:
    id: str
    type: str
    label: str
    billing: str
    status: str
    docs: tuple[ProviderDoc, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class Provider:
    id: str
    title: str
    category: str
    summary: str
    services: tuple[str, ...]
    protocols: tuple[str, ...]
    auth_methods: tuple[AuthMethod, ...]
    docs: tuple[ProviderDoc, ...]
    integration_status: str
    connection_templates: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    notes: str = ""

    @property
    def implemented(self) -> bool:
        return self.integration_status in ("implemented", "implemented-unverified", "experimental")

    @property
    def status_label(self) -> str:
        """Short human label for the integration status; never the stored id."""
        return STATUS_TEXT.get(self.integration_status, (self.integration_status, ""))[0]

    @property
    def status_meaning(self) -> str:
        """One sentence saying what the label claims, so a badge cannot read as a support promise."""
        return STATUS_TEXT.get(self.integration_status, (self.integration_status, ""))[1]

    def auth(self, auth_id: str) -> Optional[AuthMethod]:
        return next((method for method in self.auth_methods if method.id == auth_id), None)


def _require(value: Any, kind: type, what: str) -> Any:
    if not isinstance(value, kind):
        raise CatalogError(f"{what} must be {kind.__name__}")
    return value


def _text(value: Any, what: str, *, limit: int = 400, allow_empty: bool = False) -> str:
    text = _require(value, str, what).strip()
    if (not text and not allow_empty) or len(text) > limit:
        raise CatalogError(f"{what} must be {'at most ' if allow_empty else 'non-empty and at most '}{limit} characters")
    return text


def _slug(value: Any, what: str) -> str:
    text = _text(value, what, limit=41)
    if not _ID.fullmatch(text):
        raise CatalogError(f"{what} must be a lowercase slug: a-z, 0-9 and hyphens")
    return text


def _enum(value: Any, allowed: Iterable[str], what: str) -> str:
    text = _text(value, what, limit=64)
    options = tuple(allowed)
    if text not in options:
        raise CatalogError(f"{what} must be one of: {', '.join(options)}")
    return text


def _date(value: Any, what: str) -> str:
    text = _require(value, str, what)
    if not _DATE.fullmatch(text):
        raise CatalogError(f"{what} must be an ISO date (YYYY-MM-DD)")
    return text


def _https_url(value: Any, what: str) -> str:
    text = _text(value, what, limit=2048)
    try:
        parts = urlsplit(text)
    except ValueError:
        raise CatalogError(f"{what} is not a valid URL") from None
    if parts.scheme != "https" or not parts.hostname:
        raise CatalogError(f"{what} must be an absolute HTTPS URL")
    if parts.username is not None or parts.password is not None:
        raise CatalogError(f"{what} must not embed credentials")
    return text


def _keys(value: Any, allowed: set[str], what: str) -> dict[str, Any]:
    row = _require(value, dict, what)
    unknown = set(row) - allowed
    if unknown:
        raise CatalogError(f"{what} has unknown field(s): {', '.join(sorted(unknown))}")
    return row


def _docs(value: Any, what: str) -> tuple[ProviderDoc, ...]:
    rows = _require(value, list, what)
    out: list[ProviderDoc] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        row = _keys(row, _DOC_KEYS, f"{what}[{index}]")
        url = _https_url(row.get("url"), f"{what}[{index}].url")
        if url in seen:
            raise CatalogError(f"{what} repeats {url}")
        seen.add(url)
        out.append(ProviderDoc(title=_text(row.get("title"), f"{what}[{index}].title", limit=160),
                               url=url, observed_on=_date(row.get("observed_on"), f"{what}[{index}].observed_on")))
    return tuple(out)


def _auth_method(value: Any, provider_id: str, index: int) -> AuthMethod:
    what = f"provider {provider_id!r} auth[{index}]"
    row = _keys(value, _AUTH_KEYS, what)
    billing = row.get("billing", "unknown")
    return AuthMethod(
        id=_slug(row.get("id"), f"{what}.id"),
        type=_enum(row.get("type"), AUTH_TYPES, f"{what}.type"),
        label=_text(row.get("label"), f"{what}.label", limit=120),
        billing=_enum(billing, BILLING_MODES, f"{what}.billing"),
        status=_enum(row.get("status"), AUTH_STATUSES, f"{what}.status"),
        docs=_docs(row.get("docs", []), f"{what}.docs"),
        notes=str(row.get("notes") or "")[:600],
    )


def _provider(value: Any) -> Provider:
    row = _keys(value, _PROVIDER_KEYS, "provider")
    provider_id = _slug(row.get("id"), "provider.id")
    what = f"provider {provider_id!r}"
    services = _require(row.get("services"), list, f"{what}.services")
    if not services:
        raise CatalogError(f"{what} must declare at least one service")
    service_ids = tuple(_enum(item, SERVICE_TAGS, f"{what}.services[]") for item in services)
    if len(set(service_ids)) != len(service_ids):
        raise CatalogError(f"{what} repeats a service")
    protocols = _require(row.get("protocols"), list, f"{what}.protocols")
    protocol_ids = tuple(_enum(item, PROTOCOLS, f"{what}.protocols[]") for item in protocols)
    if len(set(protocol_ids)) != len(protocol_ids):
        raise CatalogError(f"{what} repeats a protocol")
    auth_rows = _require(row.get("auth"), list, f"{what}.auth")
    if not auth_rows:
        raise CatalogError(f"{what} must declare at least one authentication method")
    auth = tuple(_auth_method(item, provider_id, index) for index, item in enumerate(auth_rows))
    auth_ids = [method.id for method in auth]
    if len(set(auth_ids)) != len(auth_ids):
        raise CatalogError(f"{what} repeats an authentication method id")
    templates = _require(row.get("connection_templates", []), list, f"{what}.connection_templates")
    template_ids = tuple(_slug(item, f"{what}.connection_templates[]") for item in templates)
    if len(set(template_ids)) != len(template_ids):
        raise CatalogError(f"{what} repeats a connection template")
    regions = _require(row.get("regions", []), list, f"{what}.regions")
    region_ids = tuple(_text(item, f"{what}.regions[]", limit=40) for item in regions)
    if len(set(region_ids)) != len(region_ids):
        raise CatalogError(f"{what} repeats a region")
    status = _enum(row.get("integration_status"), INTEGRATION_STATUSES, f"{what}.integration_status")
    docs = _docs(row.get("docs", []), f"{what}.docs")
    if status in ("implemented", "implemented-unverified", "experimental") and not template_ids:
        if not any(method.status in ("implemented", "experimental") for method in auth):
            raise CatalogError(f"{what} claims {status} without an implemented route")
    return Provider(
        id=provider_id,
        title=_text(row.get("title"), f"{what}.title", limit=120),
        category=_enum(row.get("category"), CATEGORIES, f"{what}.category"),
        summary=_text(row.get("summary") or "", f"{what}.summary", limit=300, allow_empty=True),
        services=service_ids,
        protocols=protocol_ids,
        auth_methods=auth,
        docs=docs,
        integration_status=status,
        connection_templates=template_ids,
        regions=region_ids,
        notes=str(row.get("notes") or "")[:2000],
    )


@dataclass(frozen=True)
class ProviderCatalog:
    """Validated provider identities, indexed by id and by the connection template that reaches them."""

    providers: tuple[Provider, ...]
    reviewed_on: str

    def get(self, provider_id: str) -> Optional[Provider]:
        return next((provider for provider in self.providers if provider.id == provider_id), None)

    def require(self, provider_id: str) -> Provider:
        provider = self.get(provider_id)
        if provider is None:
            raise CatalogError(f"unknown provider '{provider_id}'")
        return provider

    def by_category(self) -> dict[str, list[Provider]]:
        out: dict[str, list[Provider]] = {}
        for provider in self.providers:
            out.setdefault(provider.category, []).append(provider)
        return out

    def by_service(self, service: str) -> list[Provider]:
        return [provider for provider in self.providers if service in provider.services]

    def implemented(self) -> list[Provider]:
        return [provider for provider in self.providers if provider.implemented]

    def template_owners(self) -> dict[str, Provider]:
        """Every connection template maps to exactly one provider identity."""
        owners: dict[str, Provider] = {}
        for provider in self.providers:
            for template in provider.connection_templates:
                if template in owners:
                    raise CatalogError(
                        f"connection template {template!r} is claimed by both {owners[template].id!r} "
                        f"and {provider.id!r}")
                owners[template] = provider
        return owners

    def provider_for_template(self, template: str) -> Optional[Provider]:
        return self.template_owners().get(template)


def parse_catalog(value: Any) -> ProviderCatalog:
    """Validate one catalogue document. Unknown fields are refused so claims cannot hide in a typo."""
    row = _keys(value, {"version", "reviewed_on", "providers"}, "catalogue")
    if row.get("version") != FORMAT_VERSION:
        raise CatalogError(f"catalogue version must be {FORMAT_VERSION}")
    reviewed_on = _date(row.get("reviewed_on"), "catalogue.reviewed_on")
    entries = _require(row.get("providers"), list, "catalogue.providers")
    if not entries:
        raise CatalogError("catalogue must contain at least one provider")
    providers = tuple(_provider(item) for item in entries)
    ids = [provider.id for provider in providers]
    if len(set(ids)) != len(ids):
        raise CatalogError("catalogue provider ids must be unique")
    catalog = ProviderCatalog(providers=providers, reviewed_on=reviewed_on)
    catalog.template_owners()  # one template cannot reach two provider identities
    if not catalog.implemented():
        raise CatalogError("catalogue must contain at least one implemented provider")
    return catalog


@lru_cache(maxsize=1)
def bundled_catalog() -> ProviderCatalog:
    """Load and validate the bundled catalogue. A broken catalogue fails closed, never half-loads."""
    path = resources.files("hutch").joinpath("data", "providers.json")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CatalogError(f"the provider catalogue cannot be read: {exc}") from exc
    if len(raw) > MAX_CATALOG_BYTES:
        raise CatalogError("the provider catalogue exceeds its size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise CatalogError(f"the provider catalogue is not valid UTF-8 JSON: {exc}") from exc
    return parse_catalog(value)


def provider_for_template(template: str) -> Optional[Provider]:
    """The provider identity behind a connection template, or None for an operator-supplied endpoint."""
    return bundled_catalog().provider_for_template(template)
