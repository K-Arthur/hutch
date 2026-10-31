"""Contract tests for the provider identity catalogue (no network, no provider account)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hutch.providers.catalog import (
    CATEGORIES,
    AUTH_TYPES,
    BILLING_MODES,
    INTEGRATION_STATUSES,
    PROTOCOLS,
    SERVICE_TAGS,
    CatalogError,
    bundled_catalog,
    parse_catalog,
    provider_for_template,
)

ROOT = Path(__file__).resolve().parents[1]
CONNECTIONS = ROOT / "src" / "hutch" / "data" / "connections.json"

#: Every provider named by the delivery request. The catalogue must account for each one, even when
#: the honest outcome is "documented", "blocked" or "deferred".
REQUIRED_PROVIDER_IDS = (
    "openai", "anthropic", "google", "minimax", "moonshot", "qwen", "xai", "zai", "opencode",
    "opencode-go", "mistral", "deepseek", "github-copilot", "alibaba-model-studio", "xiaomi",
    "stepfun", "volcengine", "tencent-cloud", "qianfan", "cohere", "synthetic", "venice", "arcee",
    "vydra", "gmi-cloud", "claude-max-proxy", "bedrock", "bedrock-mantle", "google-vertex",
    "anthropic-vertex", "cloudflare-ai-gateway", "vercel-ai-gateway", "openrouter", "clawrouter",
    "litellm", "microsoft-foundry", "groq", "cerebras", "together", "fireworks", "nvidia",
    "huggingface", "deepinfra", "chutes", "novita", "kilocode", "byteplus", "ollama-cloud",
    "ollama", "lmstudio", "vllm", "sglang", "inferrs", "ds4", "llamacpp", "custom-compatible",
    "fal", "comfyui", "runway", "pixverse", "deepgram", "elevenlabs",
)


def _method(**overrides):
    row = {"id": "api-key", "type": "api_key", "label": "API key", "billing": "per_token",
           "status": "documented", "docs": []}
    row.update(overrides)
    return row


def _provider(**overrides):
    row = {
        "id": "example-provider",
        "title": "Example",
        "category": "vendor",
        "services": ["chat"],
        "protocols": ["openai-chat"],
        "auth": [_method()],
        "docs": [],
        "integration_status": "documented",
        "connection_templates": [],
        "regions": [],
    }
    row.update(overrides)
    return row


def _catalog(*providers):
    return {"version": 1, "reviewed_on": "2026-10-30", "providers": list(providers)}


def _implemented():
    return _provider(
        id="local-example",
        category="local_runtime",
        integration_status="implemented-unverified",
        auth=[_method(id="local-service", type="local_service", label="Loopback service", billing="free",
                      status="implemented")],
    )


def test_bundled_catalog_accounts_for_every_requested_provider():
    catalog = bundled_catalog()
    ids = {provider.id for provider in catalog.providers}
    missing = [provider_id for provider_id in REQUIRED_PROVIDER_IDS if provider_id not in ids]
    assert missing == []
    assert len(ids) == len(REQUIRED_PROVIDER_IDS)
    assert catalog.reviewed_on == "2026-10-30"


def test_bundled_catalog_values_are_from_closed_vocabularies():
    catalog = bundled_catalog()
    for provider in catalog.providers:
        assert provider.category in CATEGORIES
        assert provider.integration_status in INTEGRATION_STATUSES
        assert set(provider.services) <= set(SERVICE_TAGS)
        assert set(provider.protocols) <= set(PROTOCOLS)
        assert provider.auth_methods
        for method in provider.auth_methods:
            assert method.type in AUTH_TYPES
            assert method.billing in BILLING_MODES
            assert method.status in ("implemented", "experimental", "documented", "blocked", "retired", "deferred")


def test_every_connection_template_maps_to_exactly_one_provider():
    catalog = bundled_catalog()
    owners = catalog.template_owners()
    templates = set(json.loads(CONNECTIONS.read_text())["templates"])
    assert set(owners) <= templates
    # Every authentication-mode template must belong to a provider; custom endpoints map to the
    # explicit operator-supplied identity rather than to whatever service is behind them.
    assert set(templates) - set(owners) == set()
    assert owners["openai-api"].id == "openai"
    assert owners["chatgpt-plan"].id == "openai"
    assert owners["anthropic-api"].id == "anthropic"
    assert owners["opencode-go"].id == "opencode-go"
    assert owners["openrouter"].id == "openrouter"
    assert owners["xiaomi-token-plan-cn"].id == "xiaomi"
    assert owners["custom-openai"].id == "custom-compatible"


def test_implemented_claims_have_a_real_route():
    catalog = bundled_catalog()
    for provider in catalog.providers:
        if provider.integration_status in ("implemented", "implemented-unverified", "experimental"):
            implemented_auth = [method for method in provider.auth_methods
                                if method.status in ("implemented", "experimental")]
            assert provider.connection_templates or implemented_auth, provider.id


def test_retired_and_blocked_routes_are_not_implemented():
    catalog = bundled_catalog()
    retired = catalog.require("qwen").auth("portal-oauth")
    assert retired is not None and retired.status == "retired"
    blocked = catalog.require("github-copilot")
    assert blocked.integration_status == "blocked"
    proxy = catalog.require("claude-max-proxy")
    assert proxy.integration_status == "blocked"
    assert proxy.auth("unofficial-proxy").status == "blocked"


def test_local_identities_are_local_services_not_ambient_api_keys():
    catalog = bundled_catalog()
    for provider_id in ("ollama", "lmstudio", "vllm", "llamacpp", "comfyui"):
        provider = catalog.require(provider_id)
        assert provider.category == "local_runtime"
        assert provider.auth_methods[0].type == "local_service"
        assert provider.connection_templates == ()
    custom = catalog.require("custom-compatible")
    assert custom.auth_methods[0].type == "custom_endpoint"
    assert custom.integration_status == "implemented-unverified"


def test_provider_lookup_helpers():
    catalog = bundled_catalog()
    assert {provider.id for provider in catalog.by_service("video")} >= {
        "google", "minimax", "xai", "fal", "runway", "pixverse"}
    gateways = {provider.id for provider in catalog.by_category()["gateway"]}
    assert {"openrouter", "litellm", "clawrouter", "cloudflare-ai-gateway", "vercel-ai-gateway"} <= gateways
    assert provider_for_template("anthropic-api").id == "anthropic"
    assert provider_for_template("not-a-template") is None
    with pytest.raises(CatalogError):
        catalog.require("not-a-provider")


def test_duplicate_provider_ids_are_refused():
    with pytest.raises(CatalogError, match="unique"):
        parse_catalog(_catalog(_provider(), _provider()))


def test_one_template_cannot_reach_two_providers():
    with pytest.raises(CatalogError, match="claimed by both"):
        parse_catalog(_catalog(
            _provider(id="one", connection_templates=["tpl"]),
            _provider(id="two", connection_templates=["tpl"]),
        ))


@pytest.mark.parametrize("overrides, message", [
    ({"category": "not-a-category"}, "category"),
    ({"integration_status": "supported"}, "integration_status"),
    ({"services": ["telepathy"]}, "services"),
    ({"protocols": ["magic"]}, "protocols"),
    ({"auth": []}, "authentication"),
    ({"auth": [_method(type="cookie_scrape")]}, r"auth\[0\]\.type"),
    ({"auth": [_method(billing="free-ish")]}, "billing"),
    ({"auth": [_method(status="live-verified")]}, r"auth\[0\]\.status"),
    ({"id": "Bad ID"}, "provider.id"),
    ({"unexpected": 1}, "unknown field"),
    ({"docs": [{"title": "x", "url": "http://example.com/doc", "observed_on": "2026-10-30"}]}, "HTTPS"),
    ({"docs": [{"title": "x", "url": "https://example.com/doc", "observed_on": "30-10-2026"}]}, "ISO date"),
    ({"docs": [{"title": "x", "url": "https://user:pw@example.com/doc", "observed_on": "2026-10-30"}]}, "credentials"),
])
def test_malformed_provider_rows_are_refused(overrides, message):
    with pytest.raises(CatalogError, match=message):
        parse_catalog(_catalog(_provider(**overrides)))


def test_implemented_status_without_route_is_refused():
    with pytest.raises(CatalogError, match="without an implemented route"):
        parse_catalog(_catalog(_provider(integration_status="implemented-unverified")))


def test_unknown_top_level_or_version_is_refused():
    with pytest.raises(CatalogError, match="version"):
        parse_catalog({"version": 2, "reviewed_on": "2026-10-30", "providers": [_required()]})
    with pytest.raises(CatalogError, match="unknown field"):
        parse_catalog({"version": 1, "reviewed_on": "2026-10-30", "providers": [_required()],
                       "extra": True})


def _required():
    return _implemented()


def test_duplicate_service_protocol_and_auth_ids_are_refused():
    with pytest.raises(CatalogError, match="repeats a service"):
        parse_catalog(_catalog(_provider(services=["chat", "chat"])))
    with pytest.raises(CatalogError, match="repeats a protocol"):
        parse_catalog(_catalog(_provider(protocols=["openai-chat", "openai-chat"])))
    with pytest.raises(CatalogError, match="repeats an authentication method"):
        parse_catalog(_catalog(_provider(auth=[_method(), _method()])))


def test_provider_docs_are_ordered_and_unique():
    docs = [{"title": "A", "url": "https://example.com/a", "observed_on": "2026-10-30"}]
    catalog = parse_catalog(_catalog(_provider(docs=docs), _implemented()))
    assert catalog.require("example-provider").docs[0].url == "https://example.com/a"
    with pytest.raises(CatalogError, match="repeats"):
        parse_catalog(_catalog(_provider(docs=docs + docs), _implemented()))
