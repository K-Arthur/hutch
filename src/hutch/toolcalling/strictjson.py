"""Strict JSON decoding for model-emitted tool arguments.

Plain ``json.loads`` is deliberately permissive in ways that turn a broken model
turn into a different executable call:

* duplicate object keys silently keep the last value (the executed arguments are
  not the ones the transcript shows);
* ``NaN`` / ``Infinity`` are accepted even though they are not JSON;
* leading/trailing content around a value can be truncated away by memoized
  "repair" helpers.

Research / failure classes this guards (see docs/realignment/tool-calling.md):
- vLLM #39380: a streaming parser corrupted decimal argument text; the fix on
  Hutch's side is to *preserve raw text exactly* and reject what does not decode,
  never to reformat numbers.
- Anthropic's fine-grained tool streaming documentation: accumulated tool input
  may be invalid or incomplete JSON and must not be executed.

Numbers are decoded with Python semantics (arbitrary-precision int, IEEE float);
the raw string is kept alongside the decoded value so re-encoding cannot round a
19-digit identifier through a float.
"""

from __future__ import annotations

import json
from typing import Any

#: Bounded parse limits: tool arguments are model output and must not be able to
#: pin a worker with megabyte JSON or deep nesting before validation refuses them.
MAX_ARGUMENT_CHARS = 1_000_000
MAX_NESTING = 64


class JSONProblem(ValueError):
    """The raw text is not one strict JSON value."""

    def __init__(self, message: str, *, kind: str = "invalid"):
        super().__init__(message)
        self.kind = kind


def _reject_constant(token: str) -> Any:
    # json.loads accepts these by default; RFC 8259 does not define them, and a
    # model emitting NaN into a numeric argument is a malformed call, not 0.0.
    raise JSONProblem(f"'{token}' is not valid JSON; numeric arguments must be finite numbers")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise JSONProblem(f"duplicate object key {key!r}; the call is ambiguous")
        seen.add(key)
        out[key] = value
    return out


def loads_strict(text: str, *, max_chars: int = MAX_ARGUMENT_CHARS) -> Any:
    """Decode exactly one strict JSON value or raise :class:`JSONProblem`."""
    if not isinstance(text, str):
        raise JSONProblem("expected JSON text")
    if len(text) > max_chars:
        raise JSONProblem(f"arguments exceed {max_chars:,} characters")
    stripped = text.strip()
    if not stripped:
        raise JSONProblem("no JSON value was provided", kind="empty")
    try:
        value = json.loads(stripped, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    except JSONProblem:
        raise
    except RecursionError as exc:
        raise JSONProblem("arguments are nested too deeply to decode") from exc
    except json.JSONDecodeError as exc:
        raise JSONProblem(f"arguments are not valid JSON ({exc.msg} at char {exc.pos})") from exc
    _check_depth(value)
    return value


def _check_depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_NESTING:
        raise JSONProblem(f"arguments are nested more than {MAX_NESTING} levels deep")
    if isinstance(value, dict):
        for item in value.values():
            _check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, depth + 1)
