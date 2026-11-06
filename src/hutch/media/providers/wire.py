"""Pure rules for table-driven media routes: templating, path extraction, error reading.

No HTTP and no state live here, so every rule is testable without a network. A route in
``data/media-routes.json`` is data; this module is the small, fixed vocabulary that data may use:

* ``fill`` substitutes ``{name}`` placeholders in a JSON template. A value that is exactly one
  placeholder keeps its JSON type (an integer stays an integer); one that resolves to ``None`` is
  dropped from its object or list, so an optional field is simply absent instead of ``null``.
* ``dig_all`` / ``dig`` read a dotted path; ``*`` expands every element of a list or object.
* ``media_item`` picks the media out of a decoded response using the route's ``media`` block.
* ``envelope_problem`` reads a provider's in-body status (MiniMax answers HTTP 200 with the failure
  in ``base_resp``), because an HTTP 200 is not evidence of success.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote

_WHOLE = re.compile(r"^\{([a-z_][a-z0-9_]*)\}$")
_PART = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_MAX_DETAIL = 400


class WireError(ValueError):
    """A response did not have the shape the route declares."""


# ------------------------------------------------------------------ templating


def fill(template: Any, values: dict[str, Any]) -> Any:
    """Substitute placeholders in a JSON-like template (see module docstring)."""
    if isinstance(template, dict):
        out = {}
        for key, value in template.items():
            filled = fill(value, values)
            if filled is not _DROP:
                out[key] = filled
        return out
    if isinstance(template, list):
        return [item for item in (fill(v, values) for v in template) if item is not _DROP]
    if isinstance(template, str):
        whole = _WHOLE.match(template)
        if whole:
            value = values.get(whole.group(1))
            return _DROP if value is None else value
        return _PART.sub(lambda m: _text(values.get(m.group(1))), template)
    return template


class _Drop:
    def __repr__(self) -> str:      # pragma: no cover - debugging aid
        return "<drop>"


_DROP: Any = _Drop()


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def fill_path(path: str, values: dict[str, Any]) -> str:
    """A URL path with each placeholder percent-encoded, so a value can never add a segment."""
    missing = [m.group(1) for m in _PART.finditer(path) if values.get(m.group(1)) is None]
    if missing:
        raise WireError(f"the route path needs {', '.join(missing)}, which is not known")
    return _PART.sub(lambda m: quote(str(values[m.group(1)]), safe="/" if m.group(1) in _SLASHED
                                     else ""), path)


#: placeholders whose value is itself a path fragment (fal model ids are ``owner/app``)
_SLASHED = frozenset({"model", "model_app"})


# ------------------------------------------------------------------ extraction


def dig_all(obj: Any, path: str) -> list[Any]:
    """Every value at ``path``. ``*`` expands a list's elements or an object's values; an integer
    segment indexes a list. A path that leads nowhere yields an empty list, not an error."""
    frontier = [obj]
    for segment in (s for s in (path or "").split(".") if s):
        nxt: list[Any] = []
        for node in frontier:
            if segment == "*":
                if isinstance(node, list):
                    nxt.extend(node)
                elif isinstance(node, dict):
                    nxt.extend(node.values())
            elif isinstance(node, dict) and segment in node:
                nxt.append(node[segment])
            elif isinstance(node, list) and segment.lstrip("-").isdigit():
                index = int(segment)
                if -len(node) <= index < len(node):
                    nxt.append(node[index])
        frontier = nxt
    return frontier


def dig(obj: Any, path: str, default: Any = None) -> Any:
    found = dig_all(obj, path)
    return found[0] if found else default


def media_item(body: Any, spec: dict[str, Any]) -> Optional[str]:
    """The encoded media string selected by a route's ``media`` block, or None when absent.

    ``path`` may fan out with ``*``; ``where`` keeps dict elements whose fields match; ``pick``
    is ``first`` or ``last``; ``key`` names the field holding the data when elements are dicts.
    A list found at the end of the path contributes its elements as candidates."""
    candidates: list[Any] = []
    for value in dig_all(body, spec.get("path", "")):
        candidates.extend(value if isinstance(value, list) else [value])
    where = spec.get("where") or {}
    if where:
        candidates = [c for c in candidates if isinstance(c, dict)
                      and all(c.get(k) == v for k, v in where.items())]
    if not candidates:
        return None
    chosen = candidates[-1] if spec.get("pick") == "last" else candidates[0]
    if isinstance(chosen, dict):
        chosen = chosen.get(spec.get("key", "data"))
    return chosen if isinstance(chosen, str) and chosen else None


# ------------------------------------------------------------------ errors


def envelope_problem(body: Any, envelope: dict[str, Any]) -> Optional[tuple[str, bool]]:
    """``(message, refused)`` when the in-body status says the call failed, else None.

    ``envelope`` is ``{"code_path", "ok", "message_path", "refusal_codes"}``. A missing code is
    treated as a problem: a route that declares an envelope must receive one."""
    if not envelope:
        return None
    code = dig(body, envelope.get("code_path", ""))
    if code is None:
        return ("the response carried no status envelope, so success cannot be confirmed", False)
    if code == envelope.get("ok", 0):
        return None
    message = str(dig(body, envelope.get("message_path", ""), "") or "no message")
    refused = code in (envelope.get("refusal_codes") or [])
    return (f"provider status {code}: {message[:_MAX_DETAIL]}", refused)


def error_detail(body: Any, status: int) -> str:
    """The most specific human sentence a provider error body offers."""
    if isinstance(body, dict):
        for path in ("error.message", "error.param", "detail.message", "detail", "message",
                     "error", "base_resp.status_msg", "msg"):
            found = dig(body, path)
            if isinstance(found, str) and found.strip():
                return " ".join(found.split())[:_MAX_DETAIL]
            if isinstance(found, list) and found and isinstance(found[0], dict):
                first = found[0].get("msg")
                if isinstance(first, str) and first.strip():
                    return " ".join(first.split())[:_MAX_DETAIL]
    return f"HTTP {status}"


def classify_status(status: int) -> str:
    """auth | credit | rate | client | server for an HTTP failure status."""
    if status in (401, 403):
        return "auth"
    if status == 402:
        return "credit"
    if status == 429:
        return "rate"
    return "server" if status >= 500 else "client"
