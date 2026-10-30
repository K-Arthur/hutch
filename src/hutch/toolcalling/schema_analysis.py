"""Static analysis of canonical tool/JSON Schemas, with an identity cache for hot validation.

``analyze_schema`` is pure and deterministic: it walks a schema once and reports every
keyword the bounded execution validator cannot certify, plus reference/map/union/depth facts.
The tool-call execution path validates the same registered schema on every model call, so
``analysis_for`` adds a bounded LRU keyed by the schema object's identity with a strong
reference held in the cache. That makes ``id()`` safe to key on (the object cannot be freed and
its id reused while cached) and avoids hashing/serialising the schema on every call.

Invariant: a schema passed to ``analysis_for`` must be treated as immutable after
registration. Hutch's tool catalog schemas are class-level constants created once; the focused
cache tests assert analysis is stable across repeated calls. Arbitrary/ephemeral schemas
(workflow values, lowering, diagnostics) use the uncached ``analyze_schema`` directly.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

#: Keywords the bounded validator enforces.
_BOUNDED_KEYWORDS = frozenset({
    "type", "enum", "const",
    "properties", "required", "additionalProperties", "minProperties", "maxProperties",
    "items", "minItems", "maxItems", "uniqueItems",
    "minLength", "maxLength", "pattern",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "allOf", "anyOf", "oneOf", "$ref",
})

#: Keywords that carry no constraint for execution and are ignored on purpose.
#: ``format`` is informational here: Hutch does not enforce formats unless a schema's
#: author also encodes the constraint (pattern, enum, tool-level policy). It is still
#: reported through ``SchemaReport.format_fields`` so nothing is silently claimed.
_ANNOTATION_KEYWORDS = frozenset({
    "$schema", "$id", "title", "description", "examples", "example", "default",
    "deprecated", "readOnly", "writeOnly", "$comment", "format",
})

#: Keywords that change validation semantics the bounded validator cannot honor.
_UNSUPPORTED_KEYWORDS = frozenset({
    "patternProperties", "propertyNames", "unevaluatedProperties", "unevaluatedItems",
    "if", "then", "else", "dependentSchemas", "dependentRequired",
    "contains", "minContains", "maxContains", "prefixItems", "unevaluatedItems",
    "$dynamicRef", "$dynamicAnchor", "$anchor", "not",
})

@dataclass(frozen=True)
class SchemaReport:
    """Static analysis of one canonical schema for planning and diagnostics."""

    unsupported: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()
    uses_unions: bool = False
    uses_maps: bool = False          # additionalProperties as a schema (map semantics)
    max_depth: int = 0
    format_fields: tuple[str, ...] = ()
    default_fields: tuple[str, ...] = ()
    nullable_fields: tuple[str, ...] = ()

    @property
    def certifiable(self) -> bool:
        return not self.unsupported


def analyze_schema(schema: Any, *, _path: str = "", _depth: int = 0,
                   _refs: list[str] | None = None, _seen: frozenset[str] = frozenset()) -> SchemaReport:
    """Run bounded static analysis; never resolves a reference, even a local one."""
    unsupported: list[str] = []
    refs: list[str] = list(_refs or [])
    formats: list[str] = []
    defaults: list[str] = []
    nullable: list[str] = []
    unions = maps_ = False
    max_depth = _depth

    def walk(node: Any, path: str, depth: int) -> None:
        nonlocal unions, maps_, max_depth
        max_depth = max(max_depth, depth)
        if depth > 32:
            unsupported.append(f"{path or '<root>'}: schema nesting exceeds 32 levels")
            return
        if not isinstance(node, dict):
            return
        if "default" in node:
            defaults.append(path or "<root>")
        if "format" in node:
            formats.append(path or "<root>")
        for key, value in node.items():
            if key in _BOUNDED_KEYWORDS or key in _ANNOTATION_KEYWORDS:
                continue
            if key in _UNSUPPORTED_KEYWORDS:
                unsupported.append(f"{path or '<root>'}: keyword {key!r} is not checked by this validator")
            elif key.startswith("$") or key in ("definitions",):
                continue
            else:
                unsupported.append(f"{path or '<root>'}: unknown schema keyword {key!r}")
        declared = node.get("type")
        if isinstance(declared, list) and "null" in declared:
            nullable.append(path or "<root>")
        if "anyOf" in node or "oneOf" in node:
            unions = True
        addl = node.get("additionalProperties")
        if isinstance(addl, dict):
            maps_ = True
        for ref_key in ("$ref", "$dynamicRef"):
            ref = node.get(ref_key)
            if isinstance(ref, str):
                refs.append(ref)
                if not ref.startswith("#"):
                    unsupported.append(f"{path or '<root>'}: remote reference {ref!r} is not resolved")
        for combinator in ("allOf", "anyOf", "oneOf"):
            for index, child in enumerate(node.get(combinator) or []):
                walk(child, f"{path}/{combinator}/{index}", depth + 1)
        props = node.get("properties")
        if isinstance(props, dict):
            for name, child in props.items():
                walk(child, f"{path}/properties/{name}", depth + 1)
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, f"{path}/items", depth + 1)
        addl = node.get("additionalProperties")
        if isinstance(addl, dict):
            walk(addl, f"{path}/additionalProperties", depth + 1)
        defs = node.get("$defs") if isinstance(node.get("$defs"), dict) else node.get("definitions")
        if isinstance(defs, dict):
            for name, child in defs.items():
                walk(child, f"{path}/$defs/{name}", depth + 1)

    walk(schema, _path, _depth)
    return SchemaReport(unsupported=tuple(dict.fromkeys(unsupported)), refs=tuple(refs),
                        uses_unions=unions, uses_maps=maps_, max_depth=max_depth,
                        format_fields=tuple(formats), default_fields=tuple(defaults),
                        nullable_fields=tuple(nullable))



#: Bounded identity cache: enough for every built-in and connection-scoped tool schema.
_MAX_CACHED_ANALYSES = 128
_ANALYSIS_CACHE: "OrderedDict[int, tuple[Any, SchemaReport]]" = OrderedDict()
_ANALYSIS_HITS = 0
_ANALYSIS_MISSES = 0


def analysis_for(schema: Any) -> SchemaReport:
    """Cached ``analyze_schema`` for an immutable, registered schema object."""
    global _ANALYSIS_HITS, _ANALYSIS_MISSES
    key = id(schema)
    hit = _ANALYSIS_CACHE.get(key)
    if hit is not None and hit[0] is schema:
        _ANALYSIS_CACHE.move_to_end(key)
        _ANALYSIS_HITS += 1
        return hit[1]
    report = analyze_schema(schema)
    _ANALYSIS_CACHE[key] = (schema, report)
    while len(_ANALYSIS_CACHE) > _MAX_CACHED_ANALYSES:
        _ANALYSIS_CACHE.popitem(last=False)
    _ANALYSIS_MISSES += 1
    return report


def clear_analysis_cache() -> None:
    """Drop cached analyses and reset the counters; for tests and catalog replacement."""
    global _ANALYSIS_HITS, _ANALYSIS_MISSES
    _ANALYSIS_CACHE.clear()
    _ANALYSIS_HITS = 0
    _ANALYSIS_MISSES = 0


def analysis_cache_info() -> dict[str, int]:
    """Bounded observability for tests and diagnostics (not a public API)."""
    return {"size": len(_ANALYSIS_CACHE), "hits": _ANALYSIS_HITS, "misses": _ANALYSIS_MISSES}
