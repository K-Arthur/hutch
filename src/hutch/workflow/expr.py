"""Bounded reference resolution, templates and condition evaluation.

This module is the only place a plan's ``{"ref": ...}``, ``{"template": ...}`` and
:class:`~hutch.workflow.plan.Condition` values are interpreted. It never calls
``eval``/``exec``, never imports, never touches the filesystem or the network, and never
calls a function named by data: every operation is one of the fixed cases implemented
here. That is what makes a plan safe to execute in the orchestration process.

Resolution is deliberately strict about missing data:

* ``exists``, ``is_null``, ``is_empty`` and ``not_empty`` are the only operations that
  tolerate a missing path; everything else raises :class:`EvalError`, so a missing value
  can never quietly become ``0``, ``""`` or ``False`` in a condition.
* Type confusion is an error, not a coercion: ``gt``/``lt`` compare numbers with numbers
  and strings with strings, and nothing else.
* ``matches`` uses a length-capped pattern and a length-capped subject; patterns are
  matched with :func:`re.search` as JSON Schema does, on the caller's own strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

MAX_PATTERN = 300
MAX_SUBJECT = 20_000
MAX_RESOLVED_BYTES = 4 * 1024 * 1024
MAX_TEMPLATE_VALUES = 64
MAX_PATH_DEPTH = 32

#: A missing key or index; distinguishable from a stored ``None``.
MISSING = object()


class EvalError(ValueError):
    """A value could not be resolved or a condition could not be evaluated."""


@dataclass
class Scope:
    """Named values visible to a plan node: ``input``, node results and map locals."""

    values: dict[str, Any] = field(default_factory=dict)

    def with_locals(self, **locals_: Any) -> "Scope":
        merged = dict(self.values)
        merged.update(locals_)
        return Scope(merged)

    def get_path(self, path: str) -> Any:
        """Resolve a dotted/indexed path against this scope; ``MISSING`` when absent.

        A path may start with a *site id that contains dots* (``shape.then.packed``), so the
        longest prefix that is an actual scope key wins. That is what lets a node inside a
        bounded construct reference a sibling by its full site id.
        """
        if not path or len(path) > 400:
            raise EvalError("empty or oversized reference")
        parts = path.split(".")
        value: Any = MISSING
        rest = ""
        for cut in range(len(parts), 0, -1):
            candidate = ".".join(parts[:cut])
            if candidate in self.values:
                value = self.values[candidate]
                rest = path[len(candidate):]
                break
        if value is MISSING:
            return MISSING
        rest = rest[1:] if rest.startswith(".") else rest
        if rest:
            segments = _split_path(rest)
            for kind, part in segments:
                if kind == "attr":
                    if isinstance(value, dict):
                        if part not in value:
                            return MISSING
                        value = value[part]
                    else:
                        return MISSING
                else:
                    if isinstance(value, (list, tuple)) and -len(value) <= part < len(value):
                        value = value[part]
                    else:
                        return MISSING
                if _depth_guard(value) is None:
                    raise EvalError("resolved value is too large or too deeply nested")
        return value


def _depth_guard(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 24:
        return None
    if isinstance(value, dict):
        if len(value) > 50_000:
            return None
        for item in value.values():
            if _depth_guard(item, _depth=_depth + 1) is None:
                return None
    elif isinstance(value, (list, tuple)):
        if len(value) > 50_000:
            return None
        for item in value:
            if _depth_guard(item, _depth=_depth + 1) is None:
                return None
    return value


def _split_path(path: str) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    index = 0
    buffer = ""
    length = len(path)
    while index < length:
        char = path[index]
        if char == ".":
            if buffer:
                out.append(("attr", buffer))
                buffer = ""
            index += 1
            continue
        if char == "[":
            if buffer:
                out.append(("attr", buffer))
                buffer = ""
            end = path.find("]", index)
            if end < 0:
                raise EvalError(f"unterminated index in reference {path!r}")
            raw = path[index + 1:end].strip()
            if not raw or not (raw.lstrip("-").isdigit()):
                raise EvalError(f"only integer indices are supported in {path!r}")
            out.append(("index", int(raw)))
            index = end + 1
            continue
        if char in " *?{}":
            raise EvalError(f"unsupported character {char!r} in reference {path!r}")
        buffer += char
        index += 1
    if buffer:
        out.append(("attr", buffer))
    if len(out) > MAX_PATH_DEPTH:
        raise EvalError("reference path is too deep")
    return out


def is_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value.keys()) == {"ref"} and isinstance(value.get("ref"), str)


def is_template(value: Any) -> bool:
    return (isinstance(value, dict) and "template" in value
            and set(value.keys()) <= {"template", "values"} and isinstance(value.get("template"), str))


def resolve_value(value: Any, scope: Scope) -> Any:
    """Resolve refs/templates recursively; other JSON values pass through unchanged."""
    if is_ref(value):
        resolved = scope.get_path(value["ref"])
        if resolved is MISSING:
            raise EvalError(f"reference resolves to nothing: {value['ref']}")
        return resolved
    if is_template(value):
        values = value.get("values") or {}
        if len(values) > MAX_TEMPLATE_VALUES:
            raise EvalError("too many template values")
        rendered: dict[str, str] = {}
        for name, raw in values.items():
            if not isinstance(name, str) or not name.isidentifier():
                raise EvalError("template value names must be identifiers")
            resolved = resolve_value(raw, scope)
            if resolved is MISSING:
                raise EvalError(f"template value {name!r} is missing")
            rendered[name] = _to_text(resolved)
        return render_template(value["template"], rendered)
    if isinstance(value, dict):
        return {key: resolve_value(item, scope) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, scope) for item in value]
    return value


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return "null" if value is None else ("true" if value is True else ("false" if value is False else str(value)))
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)[:MAX_SUBJECT]


_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def render_template(template: str, values: dict[str, str]) -> str:
    """Replace ``{{ name }}`` placeholders once; unknown names are an error."""
    if len(template) > MAX_SUBJECT:
        raise EvalError("template is too large")

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise EvalError(f"template references unknown value {name!r}")
        return values[name]

    return _PLACEHOLDER.sub(substitute, template)


def evaluate(condition: Any, scope: Scope) -> bool:
    """Evaluate a validated :class:`~hutch.workflow.plan.Condition` tree."""
    from .plan import Condition

    if not isinstance(condition, Condition):
        raise EvalError("not a compiled condition")
    if condition.all:
        return all(evaluate(child, scope) for child in condition.all)
    if condition.any:
        return any(evaluate(child, scope) for child in condition.any)
    if condition.not_ is not None:
        return not evaluate(condition.not_, scope)

    left = scope.get_path(condition.ref)
    op = condition.op
    if op == "exists":
        return left is not MISSING
    if op == "is_null":
        return left is None
    if op == "is_empty":
        return left is MISSING or left is None or left == "" or left == [] or left == {}
    if op == "not_empty":
        return not (left is MISSING or left is None or left == "" or left == [] or left == {})
    if left is MISSING:
        raise EvalError(f"condition references a missing value: {condition.ref}")

    right = resolve_value(condition.value, scope) if condition.requires_value() else None
    if right is MISSING:
        raise EvalError("condition value is missing")
    return _compare(left, op, right, condition.ref)


def _compare(left: Any, op: str, right: Any, ref: str) -> bool:
    if op == "eq":
        return _typed_eq(left, right)
    if op == "ne":
        return not _typed_eq(left, right)
    if op in ("gt", "ge", "lt", "le"):
        if isinstance(left, bool) or isinstance(right, bool):
            raise EvalError(f"{op} does not compare booleans ({ref})")
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            pairs = {"gt": left > right, "ge": left >= right, "lt": left < right, "le": left <= right}
        elif isinstance(left, str) and isinstance(right, str):
            pairs = {"gt": left > right, "ge": left >= right, "lt": left < right, "le": left <= right}
        else:
            raise EvalError(f"{op} compares numbers with numbers or strings with strings ({ref})")
        return bool(pairs[op])
    if op == "in":
        return _membership(left, right, ref, invert=False)
    if op == "not_in":
        return _membership(left, right, ref, invert=True)
    if op == "contains":
        return _membership(right, left, ref, invert=False)
    if op == "matches":
        if not isinstance(left, str) or not isinstance(right, str):
            raise EvalError(f"matches needs strings ({ref})")
        if len(right) > MAX_PATTERN or len(left) > MAX_SUBJECT:
            raise EvalError("matches pattern or subject is too large")
        try:
            return re.search(right, left) is not None
        except re.error as exc:
            raise EvalError(f"invalid pattern in {ref}: {exc}") from None
    raise EvalError(f"unsupported operator {op!r}")


def _typed_eq(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    return left == right


def _membership(item: Any, container: Any, ref: str, *, invert: bool) -> bool:
    if isinstance(container, (list, tuple)):
        found = any(_typed_eq(item, candidate) for candidate in container)
    elif isinstance(container, str):
        found = isinstance(item, str) and item in container
    elif isinstance(container, dict):
        found = isinstance(item, str) and item in container
    else:
        raise EvalError(f"in/contains needs a list, string or object ({ref})")
    return (not found) if invert else found
