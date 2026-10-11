"""Compilation: authoritative catalog + resolved profile -> immutable per-turn plan.

Compilation is pure: it never invokes a tool, reads a credential, or mutates the canonical
registry. The plan snapshots the authorized catalog for one model turn; a catalog change
requires a new compilation, and an in-flight call or approval is always executed against
the snapshot it was validated with.

Caching is keyed by canonical schema content, profile fingerprint, strategy, protocol,
compiler version, and the validator engine. Only immutable plans are cached - never a
per-request decoder or grammar state - and the cache is bounded.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any, Mapping, Optional, Sequence

from .contracts import COMPILER_VERSION, CompilationPlan, Diagnostic, ToolDefinition, canonical_json
from .envelope import EnvelopeUnavailable, build_envelope, render_contract
from .profiles import ModelCapabilityProfile, strategy_eligibility
from .schemas import backend_for_protocol
from .validate import schema_engine

MAX_CACHED_PLANS = 64


class ToolProtocolUnavailable(Exception):
    """The explicitly requested generation strategy cannot serve this catalog/profile."""


_PLAN_CACHE: "OrderedDict[tuple, CompilationPlan]" = OrderedDict()
#: In-process fast path: a tool instance is immutable once built, so the identity of the
#: objects in the snapshot plus the resolved profile/strategy is a valid plan key. The
#: content-keyed cache below still covers identical catalogs rebuilt in a later run.
_IDENTITY_CACHE: "OrderedDict[tuple, CompilationPlan]" = OrderedDict()
MAX_IDENTITY_PLANS = 128


def clear_plan_cache() -> None:
    _PLAN_CACHE.clear()
    _IDENTITY_CACHE.clear()


def openai_function_spec(definition: ToolDefinition) -> dict[str, Any]:
    """The Chat Completions / compatible function envelope for one definition."""
    return {
        "type": "function",
        "function": {
            "name": definition.visible_name,
            "description": definition.description,
            "parameters": definition.canonical_schema(),
        },
    }


def build_definitions(tools: Mapping[str, Any], *, protocol: str, scope: str = ""
                      ) -> tuple[ToolDefinition, ...]:
    """Snapshot the authorized tool registry; deterministic order, no shared mutable state."""
    return tuple(ToolDefinition.from_tool(tools[name], owner="builtin", scope=scope, protocol=protocol)
                 for name in sorted(tools))


def catalog_fingerprint(definitions: Sequence[ToolDefinition], scope: str = "") -> str:
    payload = [{"name": d.name, "revision": d.revision, "alias": d.alias, "owner": d.owner, "scope": d.scope}
               for d in definitions]
    return hashlib.sha256(canonical_json({"tools": payload, "scope": scope}).encode()).hexdigest()[:16]


def compile_plan(*, tools: Mapping[str, Any], profile: ModelCapabilityProfile, strategy: str = "auto",
                 scope: str = "", validator: Optional[str] = None) -> CompilationPlan:
    """Compile the catalog for one profile/strategy. Raises ToolProtocolUnavailable on request."""
    requested = (strategy or "auto").strip().lower()
    if requested not in ("auto", "native", "constrained", "prompt", "disabled"):
        raise ToolProtocolUnavailable(f"unknown tool protocol choice {requested!r}")
    validator = validator or schema_engine()
    started = time.perf_counter()
    if requested == "auto":
        chosen = "native"
    else:
        eligibility = strategy_eligibility(profile)
        available, why = eligibility.get(requested, (False, "unknown strategy"))
        if not available:
            raise ToolProtocolUnavailable(
                f"this route cannot use the {requested!r} tool protocol: {why}")
        chosen = requested

    identity_key = (tuple(sorted((name, id(tool)) for name, tool in tools.items())),
                    profile.fingerprint(), profile.protocol, chosen, validator, COMPILER_VERSION)
    fast = _IDENTITY_CACHE.get(identity_key)
    if fast is not None:
        _IDENTITY_CACHE.move_to_end(identity_key)
        return CompilationPlan(**{**fast.__dict__, "cache_hit": True,
                                  "compiled_ms": round((time.perf_counter() - started) * 1000, 3)})

    definitions = build_definitions(tools, protocol=profile.protocol, scope=scope)
    diagnostics: list[Diagnostic] = []
    backend = backend_for_protocol(profile.protocol, profile.provider)
    wire_tools: tuple[dict[str, Any], ...] = ()
    envelope_schema = None
    contract = ""

    if chosen == "native":
        wire_tools = tuple(openai_function_spec(d) for d in definitions)
        if not profile.native_tools.supports:
            diagnostics.append(Diagnostic(
                "strategy.native.unverified", "warning", "", "", "locally_enforced",
                "native tool support is not verified for this exact route/model; Hutch will still validate "
                "every call locally and reject malformed, unknown, or schema-invalid calls"))
        if profile.strict_tool_schema.state == "documented":
            diagnostics.append(Diagnostic(
                "strategy.strict.available", "info", "", "", "locally_enforced",
                "the backend documents strict tool schemas, but Hutch sends best-effort schemas; enabling strict "
                "requires schema rewrites (additionalProperties=false, all fields required) and is left explicit"))
    elif chosen == "constrained":
        try:
            envelope_schema, env_diags = build_envelope(definitions, backend)
        except EnvelopeUnavailable as exc:
            raise ToolProtocolUnavailable(str(exc)) from exc
        diagnostics.extend(env_diags)
        contract = render_contract(definitions, grammar_enforced=True)
        diagnostics.append(Diagnostic(
            "strategy.constrained.attachment", "info", "", "", "equivalent",
            f"schema constraints attach through {profile.constrained_attachment or 'the protocol default'} "
            f"({backend} conversion family); the canonical validator still decides execution"))
    elif chosen == "prompt":
        contract = render_contract(definitions, grammar_enforced=False)
        diagnostics.append(Diagnostic(
            "strategy.prompt.best_effort", "warning", "", "", "locally_enforced",
            "prompt-only generation is best-effort: output is not grammar-enforced, and Hutch runs only calls "
            "that exactly match the versioned contract and pass full canonical validation"))
    else:  # disabled
        diagnostics.append(Diagnostic(
            "strategy.disabled", "warning", "", "", "equivalent",
            "tools are not offered to the model for this run"))

    aliases = {d.visible_name: d.name for d in definitions if d.visible_name != d.name}
    catalog_hash = catalog_fingerprint(definitions, scope)
    plan_body = {
        "strategy": chosen, "protocol": profile.protocol, "profile": profile.fingerprint(),
        "catalog": catalog_hash, "compiler": COMPILER_VERSION, "validator": validator,
        "wire": wire_tools, "envelope": envelope_schema, "contract": contract, "aliases": aliases,
    }
    plan_hash = hashlib.sha256(canonical_json(plan_body).encode()).hexdigest()[:16]

    cache_key = (catalog_hash, profile.fingerprint(), profile.protocol, chosen, validator, COMPILER_VERSION)
    cached = _PLAN_CACHE.get(cache_key)
    if cached is not None:
        _PLAN_CACHE.move_to_end(cache_key)
        return CompilationPlan(**{**cached.__dict__, "cache_hit": True,
                                  "compiled_ms": round((time.perf_counter() - started) * 1000, 3)})

    plan = CompilationPlan(
        strategy=chosen, protocol=profile.protocol, profile_fingerprint=profile.fingerprint(),
        profile_key=profile.key, tools=definitions, wire_tools=wire_tools, prompt_contract=contract,
        envelope_schema=envelope_schema, aliases=aliases, diagnostics=tuple(diagnostics),
        catalog_hash=catalog_hash, plan_hash=plan_hash, compiler_version=COMPILER_VERSION,
        validator=validator, compiled_ms=round((time.perf_counter() - started) * 1000, 3))
    _PLAN_CACHE[cache_key] = plan
    while len(_PLAN_CACHE) > MAX_CACHED_PLANS:
        _PLAN_CACHE.popitem(last=False)
    _IDENTITY_CACHE[identity_key] = plan
    while len(_IDENTITY_CACHE) > MAX_IDENTITY_PLANS:
        _IDENTITY_CACHE.popitem(last=False)
    return plan


def plan_event(plan: CompilationPlan, profile: ModelCapabilityProfile) -> dict[str, Any]:
    """A bounded, redacted event payload for the transcript and diagnostics UI."""
    return {
        "strategy": plan.strategy,
        "protocol": plan.protocol,
        "profile": profile.capabilities_view(),
        "catalog_hash": plan.catalog_hash,
        "plan_hash": plan.plan_hash,
        "compiler_version": plan.compiler_version,
        "validator": plan.validator,
        "cache_hit": plan.cache_hit,
        "compiled_ms": plan.compiled_ms,
        "tools": [{"name": d.name, "visible": d.visible_name, "revision": d.revision} for d in plan.tools],
        "aliases": dict(plan.aliases),
        "diagnostics": [d.as_event() for d in plan.diagnostics],
    }
