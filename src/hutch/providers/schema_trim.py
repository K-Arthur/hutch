"""Drop tool-schema keywords a host rejects from the wire copy only.

Some hosts answer HTTP 400 when a tool's JSON Schema carries bound keywords such as ``maxLength`` (Volcengine's
tool-call API, per the OpenClaw Volcengine page read 2026-11-06; not reproduced against a live account). The
canonical schema in ``Tool.parameters`` stays the execution contract: ``toolcalling.validate.validate_call``
checks every model call against it before dispatch, so a trimmed wire schema never loosens what runs. A template
opts in with ``tool_schema_unsupported_keywords``; nothing is trimmed by default.
"""

from __future__ import annotations

from typing import Any

from .base import ChatRequest
from .openai_compat import OpenAICompatProvider

#: Keywords whose value is one schema, a list of schemas, or a name -> schema map. Everything else (``enum``,
#: ``const``, ``default``, ``required``) is data and is never walked, so a value that merely looks like a keyword
#: survives.
_ONE = ("items", "additionalProperties", "contains", "not", "if", "then", "else", "propertyNames",
        "unevaluatedItems", "unevaluatedProperties")
_MANY = ("anyOf", "oneOf", "allOf", "prefixItems")
_MAPS = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")


def trim_schema(schema: Any, drop: frozenset[str]) -> Any:
    """A copy of ``schema`` without the ``drop`` keywords at any schema depth; the input is not modified."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in drop:
            continue
        if key in _MAPS and isinstance(value, dict):
            out[key] = {name: trim_schema(child, drop) for name, child in value.items()}
        elif key in _MANY and isinstance(value, list):
            out[key] = [trim_schema(child, drop) for child in value]
        elif key in _ONE:
            out[key] = trim_schema(value, drop)
        else:
            out[key] = value
    return out


def trim_tools(tools: list[dict[str, Any]], drop: frozenset[str]) -> list[dict[str, Any]]:
    """OpenAI-format tool list with each ``function.parameters`` trimmed; the list is returned as is if ``drop`` is empty."""
    if not drop:
        return tools
    trimmed = []
    for tool in tools:
        function = tool.get("function") if isinstance(tool, dict) else None
        if isinstance(function, dict) and "parameters" in function:
            tool = {**tool, "function": {**function, "parameters": trim_schema(function["parameters"], drop)}}
        trimmed.append(tool)
    return trimmed


class SchemaTrimmedProvider(OpenAICompatProvider):
    """OpenAI-compatible provider that sends trimmed tool schemas and leaves the caller's request intact."""

    def __init__(self, *args: Any, dropped_keywords: frozenset[str] = frozenset(), **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._dropped_keywords = frozenset(dropped_keywords)

    def chat(self, req: ChatRequest):
        if not (req.tools and self._dropped_keywords):
            return super().chat(req)
        original = req.tools
        req.tools = trim_tools(original, self._dropped_keywords)
        try:
            return super().chat(req)
        finally:
            req.tools = original
