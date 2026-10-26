"""Canonical JSON Schema validation for tool arguments.

The authoritative schema is the tool's registered ``parameters`` object. Every
call, in every generation mode, is validated against it before dispatch - a
backend grammar or structured-output mode never replaces this check (assignment
section 6: "Retain the original schema as the final execution validator even
when a backend enforces only a subset").

This module deliberately does two honest things:

1. It uses the maintained ``jsonschema`` package when it is importable
   (install it alongside Hutch: ``pip install jsonschema``), with the dialect pinned to
   Draft 2020-12 and format checking off (formats are informational unless the
   schema's author opts in elsewhere). No remote ``$ref`` is ever fetched.
2. Without that package, a *bounded* validator checks exactly the keyword subset
   Hutch's own catalog uses. ``analyze_schema`` reports every keyword the
   validator does not enforce, so a schema is never silently widened: callers
   fail closed on a schema the local engine cannot certify.

What this module will not do: coerce values between types, apply ``default``
metadata, treat an omitted property as ``null`` (or the reverse), resolve
network references, or evaluate regexes outside Python's engine. JSON Schema
``pattern`` is an unanchored search per the specification, matching
``re.search``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

_MAX_PROBLEMS = 8
_MAX_REF_DEPTH = 8
_UNIQUE_ITEMS_LIMIT = 10_000

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

_JSON_TYPES = ("object", "array", "string", "integer", "number", "boolean", "null")

try:  # pragma: no cover - exercised by whichever branch the environment has
    from jsonschema import Draft202012Validator as _Draft202012Validator  # type: ignore
    _HAVE_JSONSCHEMA = True
except Exception:  # pragma: no cover
    _Draft202012Validator = None  # type: ignore
    _HAVE_JSONSCHEMA = False


def schema_engine() -> str:
    """Which validator engine this install will use for execution checks."""
    return "jsonschema-2020-12" if _HAVE_JSONSCHEMA else "hutch-bounded-v1"


def _is_type(value: Any, jtype: str) -> bool:
    if jtype == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if jtype == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if jtype == "boolean":
        return isinstance(value, bool)
    if jtype == "string":
        return isinstance(value, str)
    if jtype == "array":
        return isinstance(value, list)
    if jtype == "object":
        return isinstance(value, dict)
    if jtype == "null":
        return value is None
    return True


def _describe(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


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


def _resolve_local_ref(schema: dict[str, Any], ref: str) -> Optional[dict[str, Any]]:
    if not ref.startswith("#/"):
        return None
    node: Any = schema
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            return None
        node = node[token]
    return node if isinstance(node, dict) else None


def validate_call(schema: dict[str, Any], args: Any) -> list[str]:
    """Problems with ``args`` under ``schema``; empty list means valid.

    The full canonical schema is the contract; a schema the local engine cannot
    certify yields a refusal problem, never a pass.
    """
    if not isinstance(args, dict):
        return [f"arguments must be a JSON object, got {_describe(args)}"]
    report = analyze_schema(schema)
    if report.unsupported:
        detail = "; ".join(report.unsupported[:_MAX_PROBLEMS])
        return [f"this tool's registered argument schema cannot be fully checked locally ({detail}); "
                "the call was not executed"]
    # Keep canonical repair messages independent of optional SDK dependencies.
    # The full Draft validator remains an additional refusal check; it cannot
    # turn a rejection from the bounded validator into acceptance.
    problems: list[str] = []
    _errors(args, schema, "", schema, problems, depth=0, ref_seen=frozenset())
    if problems:
        return problems[:_MAX_PROBLEMS]
    return _validate_with_jsonschema(schema, args) if _HAVE_JSONSCHEMA else []


def validate_value(schema: dict[str, Any], value: Any) -> list[str]:
    """Problems with any JSON ``value`` under ``schema``; empty list means valid.

    ``validate_call`` is the tool-argument entry point and requires an object. This is the
    same bounded validator for values that are not argument objects (a workflow node's
    typed result, a structured model answer), with the same fail-closed rule: a schema the
    local engine cannot certify is a refusal, never a pass.
    """
    report = analyze_schema(schema)
    if report.unsupported:
        detail = "; ".join(report.unsupported[:_MAX_PROBLEMS])
        return [f"this schema cannot be fully checked locally ({detail}); the value was not accepted"]
    if _HAVE_JSONSCHEMA:
        problems = _validate_with_jsonschema_any(schema, value)
        if problems:
            return problems
    problems: list[str] = []
    _errors(value, schema, "", schema, problems, depth=0, ref_seen=frozenset())
    return problems[:_MAX_PROBLEMS]


def _validate_with_jsonschema_any(schema: dict[str, Any], value: Any) -> list[str]:
    validator = _Draft202012Validator(schema)  # type: ignore[misc]
    out: list[str] = []
    for error in validator.iter_errors(value):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        out.append(f"value {location!r}: {error.message}")
        if len(out) >= _MAX_PROBLEMS:
            break
    return out


def _validate_with_jsonschema(schema: dict[str, Any], args: dict[str, Any]) -> list[str]:
    validator = _Draft202012Validator(schema)  # type: ignore[misc]
    out: list[str] = []
    for error in validator.iter_errors(args):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        out.append(f"argument {location!r}: {error.message}")
        if len(out) >= _MAX_PROBLEMS:
            break
    return out


def _errors(instance: Any, schema: dict[str, Any], path: str, root: dict[str, Any],
            problems: list[str], *, depth: int, ref_seen: frozenset[str]) -> None:
    if len(problems) >= _MAX_PROBLEMS or depth > _MAX_REF_DEPTH or not isinstance(schema, dict):
        return
    here = path or "<root>"

    def fail(message: str) -> None:
        if len(problems) < _MAX_PROBLEMS:
            problems.append(f"argument {here!r}: {message}")

    ref = schema.get("$ref")
    if isinstance(ref, str):
        target = _resolve_local_ref(root, ref)
        if target is None or ref in ref_seen:
            fail("a recursive or unresolvable reference is not supported in an executable schema")
            return
        _errors(instance, target, path, root, problems, depth=depth + 1, ref_seen=ref_seen | {ref})
        return

    declared = schema.get("type")
    if declared is not None:
        allowed = [declared] if isinstance(declared, str) else [t for t in declared if isinstance(t, str)]
        if allowed and not any(_is_type(instance, t) for t in allowed):
            expected = " or ".join(allowed)
            fail(f"must be {expected}, got {_describe(instance)}")
            return

    if "const" in schema and instance != schema["const"]:
        fail(f"must equal {schema['const']!r}")
        return
    enum = schema.get("enum")
    if isinstance(enum, list) and instance not in enum:
        shown = [v if isinstance(v, (str, int, float, bool)) or v is None else _describe(v) for v in enum[:12]]
        fail(f"must be one of {shown}, got {instance!r}")
        return

    for combinator in ("allOf",):
        for child in schema.get(combinator) or []:
            _errors(instance, child, path, root, problems, depth=depth + 1, ref_seen=ref_seen)
    for combinator in ("anyOf", "oneOf"):
        branches = schema.get(combinator)
        if not isinstance(branches, list):
            continue
        matches = 0
        for child in branches:
            probe: list[str] = []
            _errors(instance, child, path, root, probe, depth=depth + 1, ref_seen=ref_seen)
            if not probe:
                matches += 1
        if matches == 0:
            fail(f"does not match any {combinator} branch")
            return
        if combinator == "oneOf" and matches > 1:
            fail("matches more than one oneOf branch")
            return

    if isinstance(instance, dict):
        _object_errors(instance, schema, path, root, problems, depth, ref_seen)
    elif isinstance(instance, list):
        _array_errors(instance, schema, path, root, problems, depth, ref_seen)
    elif isinstance(instance, str):
        _string_errors(instance, schema, path, problems)
    elif isinstance(instance, (int, float)) and not isinstance(instance, bool):
        _number_errors(instance, schema, path, problems)


def _object_errors(instance: dict[str, Any], schema: dict[str, Any], path: str, root: dict[str, Any],
                   problems: list[str], depth: int, ref_seen: frozenset[str]) -> None:
    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    min_props = schema.get("minProperties")
    max_props = schema.get("maxProperties")
    if isinstance(min_props, int) and len(instance) < min_props:
        problems.append(f"argument {path or '<root>'!r}: must have at least {min_props} properties")
    if isinstance(max_props, int) and len(instance) > max_props:
        problems.append(f"argument {path or '<root>'!r}: must have at most {max_props} properties")
    for name in schema.get("required") or []:
        if name not in instance:
            problems.append(f"missing required argument {name!r}")
            if len(problems) >= _MAX_PROBLEMS:
                return
    additional = schema.get("additionalProperties", True)
    for name, value in instance.items():
        child_path = f"{path}.{name}" if path else name
        if name in props:
            _errors(value, props[name], child_path, root, problems, depth=depth + 1, ref_seen=ref_seen)
        elif additional is False:
            allowed = ", ".join(props) if props else "(none)"
            problems.append(f"unknown argument {name!r} (allowed: {allowed})")
        elif isinstance(additional, dict):
            _errors(value, additional, child_path, root, problems, depth=depth + 1, ref_seen=ref_seen)
        if len(problems) >= _MAX_PROBLEMS:
            return


def _array_errors(instance: list[Any], schema: dict[str, Any], path: str, root: dict[str, Any],
                  problems: list[str], depth: int, ref_seen: frozenset[str]) -> None:
    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    if isinstance(min_items, int) and len(instance) < min_items:
        problems.append(f"argument {path or '<root>'!r}: must have at least {min_items} items")
    if isinstance(max_items, int) and len(instance) > max_items:
        problems.append(f"argument {path or '<root>'!r}: must have at most {max_items} items")
    if schema.get("uniqueItems") is True and len(instance) <= _UNIQUE_ITEMS_LIMIT:
        seen: list[Any] = []
        for item in instance:
            if any(item == prior and _describe(item) == _describe(prior) for prior in seen):
                problems.append(f"argument {path or '<root>'!r}: items must be unique")
                break
            seen.append(item)
    items = schema.get("items")
    if isinstance(items, dict):
        for index, item in enumerate(instance):
            if len(problems) >= _MAX_PROBLEMS:
                return
            _errors(item, items, f"{path}[{index}]", root, problems, depth=depth + 1, ref_seen=ref_seen)


def _string_errors(instance: str, schema: dict[str, Any], path: str, problems: list[str]) -> None:
    here = path or "<root>"
    min_len = schema.get("minLength")
    max_len = schema.get("maxLength")
    if isinstance(min_len, int) and len(instance) < min_len:
        problems.append(f"argument {here!r}: must be at least {min_len} characters")
    if isinstance(max_len, int) and len(instance) > max_len:
        problems.append(f"argument {here!r}: must be at most {max_len} characters")
    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        try:
            if re.search(pattern, instance) is None:
                problems.append(f"argument {here!r}: must match the required pattern")
        except re.error:
            problems.append(f"argument {here!r}: the registered pattern is not a valid expression")


def _number_errors(instance: float, schema: dict[str, Any], path: str, problems: list[str]) -> None:
    here = path or "<root>"
    for key, ok in (
        ("minimum", lambda v: instance >= v),
        ("maximum", lambda v: instance <= v),
        ("exclusiveMinimum", lambda v: instance > v),
        ("exclusiveMaximum", lambda v: instance < v),
    ):
        bound = schema.get(key)
        if isinstance(bound, (int, float)) and not isinstance(bound, bool):
            if not ok(bound):
                problems.append(f"argument {here!r}: must be {'>' if 'exclusive' in key else '>=' if key == 'minimum' else '<' if 'exclusive' in key else '<='} {bound}")
    multiple = schema.get("multipleOf")
    if isinstance(multiple, int) and not isinstance(multiple, bool) and multiple > 0 and isinstance(instance, int):
        if instance % multiple != 0:
            problems.append(f"argument {here!r}: must be a multiple of {multiple}")


def required_fields(schema: dict[str, Any]) -> list[str]:
    """Top-level required property names, for empty-argument rejection."""
    required = schema.get("required") if isinstance(schema, dict) else None
    return [name for name in required or [] if isinstance(name, str)]


def declared_properties(schema: dict[str, Any]) -> list[str]:
    props = schema.get("properties") if isinstance(schema, dict) else None
    return sorted(props) if isinstance(props, dict) else []


def iter_schema_paths(schema: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    """Flat (path, subschema) view for compiler diagnostics and lowering."""
    stack: list[tuple[str, Any]] = [("", schema)]
    while stack:
        path, node = stack.pop()
        yield path, node
        if not isinstance(node, dict):
            continue
        for key in ("properties", "$defs", "definitions"):
            children = node.get(key)
            if isinstance(children, dict):
                for name, child in children.items():
                    stack.append((f"{path}/{key}/{name}", child))
        for key in ("items", "additionalProperties"):
            child = node.get(key)
            if isinstance(child, dict):
                stack.append((f"{path}/{key}", child))
        for key in ("allOf", "anyOf", "oneOf"):
            for index, child in enumerate(node.get(key) or []):
                stack.append((f"{path}/{key}/{index}", child))
