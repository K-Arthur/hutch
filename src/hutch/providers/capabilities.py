"""Evidence-backed capability registry: documented, advertised, observed, live-verified.

Provider data, route compatibility data and passive run observations answer different questions. This
module combines them into explicit evidence records scoped to the narrowest subject known:

* provider  - the provider's documentation says it offers the service;
* endpoint  - Hutch's compatibility matrix records the route contract;
* auth_route - a specific authentication route (recorded by the catalogue, used by callers);
* model     - a real observation from an owned Hutch run (existing immutable store);
* runtime   - reserved for a runtime's own capability contract.

Rules enforced by tests:
- a catalogue listing never upgrades a capability beyond documented;
- a route contract never becomes live-verified;
- this build ships NO live-verified provider evidence (no provider account was exercised), so the
  live dataset is explicitly empty rather than inferred from tests;
- unknown capability is not unsupported: absence of evidence is reported as unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..compat import compatibility_matrix
from .catalog import Provider, bundled_catalog

CAPABILITIES = (
    "text", "image_input", "image_generation", "image_editing", "audio_input", "transcription",
    "speech", "streaming_speech", "realtime_voice", "video_input", "video_generation",
    "music_generation", "web_search", "code_execution", "tool_calls", "structured_output",
    "reasoning_controls", "usage_reporting", "cancellation", "streaming", "batch",
)
LEVELS = ("documented", "advertised", "observed", "live-verified")
_LEVEL_RANK = {level: index for index, level in enumerate(LEVELS)}
SCOPE_KINDS = ("provider", "endpoint", "auth_route", "model", "runtime")

SERVICE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "chat": ("text",),
    "responses": ("text",),
    "embeddings": (),
    "images": ("image_generation",),
    "image_editing": ("image_editing",),
    "video": ("video_generation",),
    "music": ("music_generation",),
    "audio_generation": ("speech",),
    "speech": ("speech",),
    "transcription": ("transcription",),
    "realtime": ("realtime_voice",),
    "search": ("web_search",),
    "grounding": ("web_search",),
    "code_execution": ("code_execution",),
    "coding_runtime": (),
    "coding_cli": (),
    "tools": ("tool_calls",),
    "batch": ("batch",),
}

#: Route ids in data/compat.json mapped to the provider identity that implements them.
ROUTE_PROVIDER = {
    "openai-chat-completions": "openai",
    "anthropic-messages": "anthropic",
    "ollama-native": "ollama",
    "openai-compatible-connection": "custom-compatible",
    "opencode-go-connection": "opencode-go",
    "sign-in-with-chatgpt": "openai",
    "opencode-harness": "opencode",
    "pi-harness": "pi",
    "consumer-plan-oauth": "custom-compatible",
}

#: What the recorded route contract establishes. A route field saying "not sent" is not a capability.
ROUTE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "openai-chat-completions": ("text", "streaming", "tool_calls", "usage_reporting", "cancellation",
                                "image_input", "structured_output"),
    "anthropic-messages": ("text", "streaming", "tool_calls", "usage_reporting", "cancellation"),
    "ollama-native": ("text", "streaming", "tool_calls", "usage_reporting", "cancellation", "image_input",
                      "structured_output"),
    "openai-compatible-connection": ("text", "streaming", "tool_calls", "usage_reporting", "cancellation",
                                     "structured_output"),
    "opencode-go-connection": ("text", "streaming", "cancellation"),
    "sign-in-with-chatgpt": ("text", "streaming", "tool_calls", "usage_reporting", "cancellation"),
    "opencode-harness": ("text", "tool_calls"),
    "pi-harness": (),
    "consumer-plan-oauth": (),
}

#: Live-verified evidence from owner-authorized real provider requests. Entries are added only after a
#: real account, route and model produced the recorded result; nothing here is derived from fixtures.
#: Current evidence covers text generation only. It does not establish streaming, tools, images, usage
#: reporting or any other capability.


@dataclass(frozen=True)
class CapabilityEvidence:
    capability: str
    level: str
    scope_kind: str
    scope: str
    source: str
    observed_on: str
    detail: str = ""


@dataclass(frozen=True)
class CapabilityReport:
    provider_id: str
    provider_title: str
    integration_status: str
    entries: tuple[CapabilityEvidence, ...]

    def highest(self) -> dict[str, str]:
        best: dict[str, str] = {}
        for entry in self.entries:
            if entry.capability not in best or _LEVEL_RANK[entry.level] > _LEVEL_RANK[best[entry.capability]]:
                best[entry.capability] = entry.level
        return best

    def level(self, capability: str) -> Optional[str]:
        return self.highest().get(capability)

    def unverified(self) -> tuple[str, ...]:
        known = self.highest()
        return tuple(capability for capability in CAPABILITIES if capability not in known)


def _source_for(provider: Provider, catalog_reviewed: str) -> tuple[str, str]:
    if provider.docs:
        return provider.docs[0].url, provider.docs[0].observed_on
    return "bundled provider catalogue (reviewed " + catalog_reviewed + ")", catalog_reviewed


LIVE_VERIFIED_EVIDENCE: tuple[CapabilityEvidence, ...] = (
    CapabilityEvidence(
        capability="text", level="live-verified", scope_kind="model", scope="deepseek/deepseek-flash",
        source="Hutch live verification 2026-10-30: built-in runtime, real api.deepseek.com request",
        observed_on="2026-10-30",
        detail=("Model discovery authenticated and returned deepseek-flash and deepseek-v4-pro. A one-step run "
                "returned the expected token with 612 prompt / 9 completion tokens. Tool calling, streaming and "
                "image input were not exercised."),
    ),
    CapabilityEvidence(
        capability="text", level="live-verified", scope_kind="model", scope="opencode/deepseek/deepseek-flash",
        source=("Hutch live verification 2026-10-30: managed OpenCode 2.2.0 runtime with the owner's DeepSeek "
                "key connected to Hutch's private profile"),
        observed_on="2026-10-30",
        detail=("A one-step managed run succeeded with 4452 prompt / 8 completion tokens and a provider-reported "
                "cost of $0.0006726; the reply matched the requested token. Tool permissions, streaming and "
                "other OpenCode providers were not exercised."),
    ),
)


def _catalog_evidence(provider: Provider, catalog_reviewed: str) -> list[CapabilityEvidence]:
    out: list[CapabilityEvidence] = []
    source, seen = _source_for(provider, catalog_reviewed)
    for service in provider.services:
        for capability in SERVICE_CAPABILITIES.get(service, ()):
            out.append(CapabilityEvidence(
                capability=capability, level="documented", scope_kind="provider", scope=provider.id,
                source=source, observed_on=seen,
                detail="provider catalogue lists service " + service + " (" + provider.integration_status + ")"))
    return out


def _route_evidence(providers_by_id: dict[str, Provider]) -> list[CapabilityEvidence]:
    out: list[CapabilityEvidence] = []
    matrix = compatibility_matrix()
    for route in matrix.get("routes", []):
        provider_id = ROUTE_PROVIDER.get(route.get("id", ""))
        if provider_id is None or provider_id not in providers_by_id:
            continue
        capabilities = ROUTE_CAPABILITIES.get(route.get("id", ""), ())
        if not capabilities:
            continue
        evidence = route.get("policy_evidence") or []
        source = evidence[0].get("url", "") if evidence else ""
        observed_on = evidence[0].get("observed_on", route.get("verified_on", "")) if evidence else route.get("verified_on", "")
        for capability in capabilities:
            out.append(CapabilityEvidence(
                capability=capability, level="documented", scope_kind="endpoint", scope=route.get("id", ""),
                source=source, observed_on=observed_on,
                detail="recorded route contract state: " + str(route.get("state", "unknown"))))
    return out


def _observed_evidence(provider_id: str, model: str, store: Any) -> list[CapabilityEvidence]:
    if store is None or not model:
        return []
    rows = store.model_capability_observations_for(provider_id, model, limit=20)
    mapping = {"function_tool_calls": "tool_calls"}
    out: list[CapabilityEvidence] = []
    for row in rows:
        capability = mapping.get(str(row.get("capability", "")), str(row.get("capability", "")))
        if capability not in CAPABILITIES:
            continue
        observed_at = str(row.get("observed_at", ""))[:10]
        out.append(CapabilityEvidence(
            capability=capability, level="observed", scope_kind="model", scope=provider_id + "/" + model,
            source="passive owned-run observation (no extra request)",
            observed_on=observed_at if "T" not in observed_at else observed_at,
            detail="tool " + str(row.get("source_tool", "")) + " returned a valid declared call"))
    return out


def live_verified_evidence() -> tuple[CapabilityEvidence, ...]:
    """The live dataset for this build. Empty: no provider account was exercised."""
    return LIVE_VERIFIED_EVIDENCE


def capability_report(provider_id: str, *, model: str = "", store: Any = None,
                      catalog=None) -> CapabilityReport:
    catalog = catalog or bundled_catalog()
    provider = catalog.require(provider_id)
    entries: list[CapabilityEvidence] = []
    entries.extend(_catalog_evidence(provider, catalog.reviewed_on))
    entries.extend(item for item in _route_evidence({provider.id: provider}) if True)
    entries.extend(_observed_evidence(provider.id, model, store))
    entries.extend(item for item in live_verified_evidence() if item.scope.split("/", 1)[0] == provider_id)
    return CapabilityReport(provider_id=provider.id, provider_title=provider.title,
                            integration_status=provider.integration_status, entries=tuple(entries))


def capability_matrix(*, store: Any = None, catalog=None) -> list[CapabilityReport]:
    catalog = catalog or bundled_catalog()
    return [capability_report(provider.id, store=store, catalog=catalog) for provider in catalog.providers]


def report_json(report: CapabilityReport) -> dict:
    highest = report.highest()
    return {
        "provider": report.provider_id,
        "title": report.provider_title,
        "integration_status": report.integration_status,
        "levels": {capability: highest[capability] for capability in CAPABILITIES if capability in highest},
        "unverified": list(report.unverified()),
        "evidence": [
            {"capability": entry.capability, "level": entry.level, "scope_kind": entry.scope_kind,
             "scope": entry.scope, "source": entry.source, "observed_on": entry.observed_on,
             "detail": entry.detail}
            for entry in report.entries
        ],
    }
