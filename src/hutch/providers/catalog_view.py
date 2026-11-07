"""Row and facet view models for the provider catalogue index.

The Providers page is a route-level index, not a wall of cards: one compact row per provider with its
verification status, the routes (auth methods) it offers and the services it lists. Everything here is
derived from the catalogue so the page cannot say more than the data does. A route is labeled by whether
Hutch has a code path for it ("built" or "not built"); whether anything was ever run through it is the
provider's own status chip, which is the only place the word "works" can appear.
"""

from __future__ import annotations

import re
from typing import Any

from .accounts import AUTH_LABELS
from .catalog import CATEGORIES, INTEGRATION_STATUSES, STATUS_TEXT, Provider, ProviderCatalog

CATEGORY_LABELS = {
    "vendor": "Model vendors",
    "serving_platform": "Model-serving platforms",
    "gateway": "Gateways and routers",
    "enterprise_cloud": "Enterprise clouds",
    "subscription_service": "Subscription services",
    "local_runtime": "Local and self-hosted runtimes",
    "media_platform": "Media, speech and music",
    "compatible_endpoint": "Custom compatible endpoints",
}

AUTH_TYPE_LABELS = dict(AUTH_LABELS, environment="Environment variable")

SERVICE_LABELS = {
    "chat": "Chat", "responses": "Responses API", "embeddings": "Embeddings", "images": "Images",
    "image_editing": "Image editing", "video": "Video", "music": "Music",
    "audio_generation": "Audio generation", "speech": "Speech out", "transcription": "Speech to text",
    "realtime": "Realtime", "search": "Search", "grounding": "Grounding",
    "code_execution": "Code execution", "coding_runtime": "Coding runtime", "coding_cli": "Coding CLI",
    "tools": "Tool calls", "batch": "Batch",
}

#: What a route's code path is. Never "works": only a dated live run earns that, on the provider chip.
CODE_LABELS = {
    "implemented": "built", "experimental": "built, gated", "documented": "not built",
    "blocked": "blocked", "retired": "retired", "deferred": "not built",
}

_CHIP = {
    "implemented": "st-succeeded", "implemented-unverified": "st-waiting_approval",
    "experimental": "st-waiting_approval", "blocked": "st-failed", "retired": "st-failed",
    "documented": "st-stopped", "deferred": "st-stopped",
}


def status_chip_class(status: str) -> str:
    """The existing chip colour class for a catalogue or route status; neutral for an unknown one."""
    return _CHIP.get(status, "st-stopped")


def route_chips(provider: Provider) -> list[dict[str, Any]]:
    """One chip per auth method: its mechanism, whether a code path exists, and its recorded status."""
    return [
        {"id": method.id, "type": method.type, "type_label": AUTH_TYPE_LABELS.get(method.type, method.type),
         "status": method.status, "code_label": CODE_LABELS.get(method.status, method.status),
         "chip_class": status_chip_class(method.status)}
        for method in provider.auth_methods
    ]


def _service_chips(provider: Provider) -> list[dict[str, str]]:
    return [{"id": tag, "label": SERVICE_LABELS.get(tag, tag)} for tag in provider.services]


def _search_text(provider: Provider, routes: list[dict[str, Any]], services: list[dict[str, str]]) -> str:
    label = STATUS_TEXT.get(provider.integration_status, (provider.integration_status, ""))[0]
    parts = [provider.title, provider.id, provider.integration_status, label, provider.category.replace("_", " "),
             *[chip["label"] for chip in services], *[route["type_label"] for route in routes]]
    return " ".join(parts).lower()


def catalog_rows(catalog: ProviderCatalog, account_counts: dict[str, int]) -> list[dict[str, Any]]:
    """Every provider, in catalogue order, as the dict the index template and filter script read."""
    rows = []
    for provider in catalog.providers:
        routes, services = route_chips(provider), _service_chips(provider)
        label, meaning = STATUS_TEXT.get(provider.integration_status, (provider.integration_status, ""))
        rows.append({
            "id": provider.id, "title": provider.title, "href": f"/providers/{provider.id}",
            "category": provider.category, "category_label": CATEGORY_LABELS.get(provider.category, provider.category),
            "status": provider.integration_status, "status_label": label, "status_meaning": meaning,
            "chip_class": status_chip_class(provider.integration_status),
            "summary": provider.summary, "services": services, "routes": routes,
            "auth_types": " ".join(sorted({route["type"] for route in routes})),
            "service_ids": " ".join(chip["id"] for chip in services),
            "account_count": account_counts.get(provider.id, 0),
            "search": _search_text(provider, routes, services),
        })
    return rows


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def distinct_next_action(detail: str, next_action: str) -> str:
    """The next action only when it adds something the detail did not already say.

    Readiness often states the problem and then restates it as an instruction ("No local credential
    found: set X where Hutch starts, or store a key on Connections." followed by "Set X where Hutch
    starts, or store a key on the connection page."). When most of the action's words are already in the
    detail it is a repeat and is dropped; a genuinely new instruction is kept."""
    detail_words, action_words = _words(detail), _words(next_action)
    if not action_words:
        return ""
    covered = len(action_words & detail_words) / len(action_words)
    return "" if covered >= 0.7 else next_action


def _counted(order: tuple[str, ...], values: list[list[str]], labels: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for value in order:
        count = sum(1 for group in values if value in group)
        if count:
            out.append({"id": value, "label": labels.get(value, value), "count": count})
    return out


def catalog_facets(catalog: ProviderCatalog) -> dict[str, list[dict[str, Any]]]:
    """Filter options that exist in the catalogue, each with how many providers it selects."""
    providers = catalog.providers
    status_labels = {key: value[0] for key, value in STATUS_TEXT.items()}
    auth_order = tuple(AUTH_TYPE_LABELS)
    service_order = tuple(SERVICE_LABELS)
    return {
        "categories": _counted(CATEGORIES, [[p.category] for p in providers], CATEGORY_LABELS),
        "statuses": _counted(INTEGRATION_STATUSES, [[p.integration_status] for p in providers], status_labels),
        "auth_types": _counted(auth_order, [[m.type for m in p.auth_methods] for p in providers], AUTH_TYPE_LABELS),
        "services": _counted(service_order, [list(p.services) for p in providers], SERVICE_LABELS),
    }
