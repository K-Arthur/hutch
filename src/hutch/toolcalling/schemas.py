"""Schema analysis and lowering for constrained generation - canonical schemas are never mutated.

Two backend families are recognized (research, docs/realignment/tool-calling.md):

* ``xgrammar``-family (vLLM ``response_format`` / ``structured_outputs``): broad Draft
  2020-12 coverage; still, every transformation away from the canonical schema is reported.
* ``gbnf``-family (llama.cpp ``response_format``, Ollama ``format``): JSON Schema -> GBNF
  conversion with documented gaps - ``additionalProperties`` defaults to **false**,
  unsupported keywords are skipped silently, ``pattern`` must be anchored ``^...$``,
  nested ``$ref`` is broken, and remote references are not fetched by the C++ server.

The lowering pipeline is deterministic and bounded: inline local references (depth/cycle
bounded), materialize ``additionalProperties: true`` where the *canonical* schema left it
open but the backend's default would close it, and drop keywords the backend cannot honor
while marking them ``locally_enforced`` so the canonical validator still enforces them.
Nothing here may widen the canonical contract, and no remote reference is ever resolved.
"""

from __future__ import annotations

import copy
import hashlib
import json

from .contracts import Diagnostic, ToolDefinition
from .validate import analyze_schema

#: Bound the generated grammar/structured-output work (assignment section 6).
MAX_SCHEMA_BYTES = 32_000
MAX_ENVELOPE_SCHEMA_BYTES = 192_000
MAX_SCHEMA_DEPTH = 24
MAX_REF_INLINE_DEPTH = 8

BACKENDS = ("xgrammar", "gbnf")


def backend_for_protocol(protocol: str, provider: str) -> str:
    """Which schema-conversion family the destination server uses."""
    if provider in ("ollama", "llamacpp", "llama.cpp", "lmstudio"):
        return "gbnf"
    return "xgrammar"


def _inline_refs(node, root, *, depth: int, prefix: str) -> tuple[object, list[Diagnostic], bool]:
    diagnostics: list[Diagnostic] = []
    ok = True

    def resolve(ref: str):
        if not ref.startswith("#/"):
            return None
        target = root
        for token in ref[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or token not in target:
                return None
            target = target[token]
        return target

    def walk(value, path: str, level: int, seen: frozenset[str]):
        nonlocal ok
        if level > MAX_REF_INLINE_DEPTH:
            diagnostics.append(Diagnostic("schema.ref.depth", "error", prefix, path, "unsupported",
                                          f"reference nesting exceeds {MAX_REF_INLINE_DEPTH} levels"))
            ok = False
            return value
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str):
                if ref in seen:
                    diagnostics.append(Diagnostic("schema.ref.cycle", "error", prefix, path, "unsupported",
                                                  f"cyclic local reference {ref!r} cannot be lowered for generation"))
                    ok = False
                    return value
                target = resolve(ref)
                if target is None:
                    diagnostics.append(Diagnostic("schema.ref.unresolvable", "error", prefix, path, "unsupported",
                                                  f"reference {ref!r} does not resolve inside this schema"))
                    ok = False
                    return value
                diagnostics.append(Diagnostic("schema.ref.inlined", "info", prefix, path, "reversibly_encoded",
                                              f"local reference {ref!r} was inlined; canonical validation is unchanged"))
                merged = {k: v for k, v in value.items() if k != "$ref"}
                inlined = walk(copy.deepcopy(target), path, level + 1, seen | {ref})
                if merged:
                    # Sibling keywords alongside $ref are valid 2020-12; keep both.
                    return {"allOf": [inlined, walk(merged, path, level + 1, seen)]}
                return inlined
            return {key: walk(item, f"{path}/{key}", level, seen) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item, f"{path}[{index}]", level, seen) for index, item in enumerate(value)]
        return value

    return walk(node, "", depth, frozenset()), diagnostics, ok


def lower_for_backend(schema: dict, backend: str, *, tool: str = "",
                      epicenter: str = "") -> tuple[dict, tuple[Diagnostic, ...]]:
    """Return a backend-safe copy plus field-level diagnostics. Canonical schema untouched."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend family {backend!r}")
    lowered, ref_diags, refs_ok = _inline_refs(copy.deepcopy(schema), schema, depth=0, prefix=tool)
    diagnostics: list[Diagnostic] = list(ref_diags)
    if not refs_ok:
        return lowered, tuple(diagnostics)

    def walk(node: dict, path: str) -> None:
        if backend == "gbnf":
            if "additionalProperties" not in node:
                node["additionalProperties"] = True
                if node.get("type") == "object" or "properties" in node:
                    diagnostics.append(Diagnostic(
                        "schema.additionalProperties.materialized", "warning", tool, path, "reversibly_encoded",
                        "canonical JSON Schema allows extra properties by default; the GBNF converter defaults to "
                        "false, so the lowered schema sets true explicitly and the canonical validator still decides"))
            elif isinstance(node.get("additionalProperties"), dict):
                diagnostics.append(Diagnostic(
                    "schema.additionalProperties.map", "warning", tool, path, "narrowed",
                    "map-style additionalProperties has no verified GBNF conversion; the generation schema allows "
                    "open keys while local validation enforces the value schema"))
                node["additionalProperties"] = True
        if "format" in node:
            node.pop("format")
            diagnostics.append(Diagnostic("schema.format.unchecked", "info", tool, path, "locally_enforced",
                                          "format is an annotation; the canonical validator does not enforce it"))
        pattern = node.get("pattern")
        if isinstance(pattern, str) and backend == "gbnf" and not (pattern.startswith("^") and pattern.endswith("$")):
            node.pop("pattern")
            diagnostics.append(Diagnostic("schema.pattern.unanchored", "warning", tool, path, "locally_enforced",
                                          "the GBNF converter requires anchored patterns; the canonical validator "
                                          "still applies the pattern"))
        for key, item in list(node.items()):
            child_path = f"{path}/{key}"
            if key == "properties" and isinstance(item, dict):
                for name, child in item.items():
                    if isinstance(child, dict):
                        walk(child, f"{child_path}/{name}")
            elif key in ("items", "additionalProperties") and isinstance(item, dict):
                walk(item, child_path)
            elif key in ("allOf", "anyOf", "oneOf") and isinstance(item, list):
                for index, child in enumerate(item):
                    if isinstance(child, dict):
                        walk(child, f"{child_path}/{index}")

    walk(lowered, "")
    return lowered, tuple(diagnostics)


def analyze_for_plan(tool: ToolDefinition, backend: str) -> tuple[dict, tuple[Diagnostic, ...]]:
    """Full per-tool pipeline: static analysis + bounded lowering for one backend."""
    canonical = tool.canonical_schema()
    report = analyze_schema(canonical)
    diagnostics: list[Diagnostic] = []
    for path in report.format_fields:
        diagnostics.append(Diagnostic("schema.format.annotation", "info", tool.name, path, "locally_enforced",
                                      "format is not enforced by Hutch's canonical validator"))
    for path in report.default_fields:
        diagnostics.append(Diagnostic("schema.default.metadata", "info", tool.name, path, "locally_enforced",
                                      "default values are metadata; they are never injected into a call"))
    if report.uses_unions:
        diagnostics.append(Diagnostic("schema.union", "info", tool.name, "", "reversibly_encoded",
                                      "union branches are preserved for generation and re-validated canonically"))
    if report.uses_maps:
        diagnostics.append(Diagnostic("schema.map", "info", tool.name, "", "reversibly_encoded",
                                      "map-style objects are validated canonically; the backend may only approximate"))
    if not report.certifiable:
        for detail in report.unsupported:
            diagnostics.append(Diagnostic("schema.unsupported", "error", tool.name, "",
                                          "unsupported", detail))
        return canonical, tuple(diagnostics)

    lowered, lower_diags = lower_for_backend(canonical, backend, tool=tool.name)
    diagnostics.extend(lower_diags)
    encoded = json.dumps(lowered, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode()) > MAX_SCHEMA_BYTES:
        diagnostics.append(Diagnostic("schema.size", "error", tool.name, "", "unsupported",
                                      f"lowered schema exceeds {MAX_SCHEMA_BYTES:,} bytes for generation"))
    if analyze_schema(lowered).max_depth > MAX_SCHEMA_DEPTH:
        diagnostics.append(Diagnostic("schema.depth", "error", tool.name, "", "unsupported",
                                      f"lowered schema exceeds {MAX_SCHEMA_DEPTH} levels"))
    return lowered, tuple(diagnostics)


def schema_digest(schema: dict) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode()).hexdigest()[:16]


__all__ = ["BACKENDS", "backend_for_protocol", "lower_for_backend", "analyze_for_plan",
           "schema_digest", "MAX_SCHEMA_BYTES", "MAX_ENVELOPE_SCHEMA_BYTES"]
