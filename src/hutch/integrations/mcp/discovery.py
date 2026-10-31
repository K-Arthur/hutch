"""Bounded, fail-closed normalization of untrusted MCP tool catalogs (ADR-0017 §4.4, §8.4).

Everything a server says is untrusted data. This module is the boundary that turns a
``tools/list`` result into records Hutch is willing to show an owner and, after review, execute:

* names, descriptions and schemas are bounded in size;
* a schema that Hutch's canonical validator cannot certify is retained as *unsupported* with
  diagnostics rather than quietly executed;
* ``default``/``example``/``examples`` are stripped, so a server sample is never mistaken for an
  argument the model supplied;
* server annotations are kept as display evidence only. ``readOnlyHint`` and
  ``destructiveHint`` never classify or authorize anything: a connector is not read-only because
  its server says so (brief §6.6);
* identical tool names are a refusal, because a catalog where two tools answer one name would
  make the grant row ambiguous.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from ...toolcalling.validate import analyze_schema
from ..base import canonical_tool_name, validate_integration_id

MAX_DISCOVERED_TOOLS = 200
MAX_SCHEMA_BYTES = 64 * 1024
MAX_DESCRIPTION_CHARS = 4_096
MAX_TITLE_CHARS = 256
MAX_DIAGNOSTICS = 8
_SAFE_NAME = re.compile(r"^[^\x00-\x1f\x7f]{1,128}$")


class McpToolSchemaError(ValueError):
    """A discovery result cannot be normalized into a bounded, unambiguous catalog."""


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise McpToolSchemaError("MCP tool metadata must contain finite JSON values") from None


def _strip_schema_annotations(value: Any) -> Any:
    """Drop non-validating example/default fields so server samples are never treated as inputs."""
    if isinstance(value, dict):
        return {key: _strip_schema_annotations(item) for key, item in value.items()
                if key not in {"default", "example", "examples", "$comment"}}
    if isinstance(value, list):
        return [_strip_schema_annotations(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise McpToolSchemaError("MCP tool schemas must use finite JSON values")
    return value


def _schema_diagnostics(schema: Any, *, root_object: bool) -> list[str]:
    if not isinstance(schema, dict):
        return ["schema must be a JSON object"]
    errors: list[str] = []
    if root_object and schema.get("type") != "object":
        errors.append("input schema root must declare type: object")
    report = analyze_schema(schema)
    if report.refs:
        errors.append("$ref is unsupported; tool schemas cannot load external or unresolved references")
    for problem in report.unsupported:
        if "$ref" in problem or "reference" in problem:
            continue
        errors.append(problem[:240])
        if len(errors) >= MAX_DIAGNOSTICS:
            break
    return list(dict.fromkeys(errors))[:MAX_DIAGNOSTICS]


def normalize_mcp_tool(integration_id: str, tool: Any) -> dict[str, Any]:
    """Create a stable name and schema digest while retaining diagnostics, never authority."""
    validate_integration_id(integration_id)
    if hasattr(tool, "model_dump"):
        try:
            raw = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
        except Exception:
            raise McpToolSchemaError("MCP tool metadata could not be serialized") from None
    elif isinstance(tool, dict):
        raw = tool
    else:
        raise McpToolSchemaError("MCP server returned a tool without a structured schema")
    if not isinstance(raw, dict):
        raise McpToolSchemaError("MCP server returned a tool without a structured schema")

    source_name = raw.get("name")
    if not isinstance(source_name, str) or not _SAFE_NAME.fullmatch(source_name):
        raise McpToolSchemaError("MCP server returned a tool with an invalid name")
    try:
        exposed_name = canonical_tool_name(integration_id, source_name)
    except ValueError as exc:
        raise McpToolSchemaError(str(exc)) from None

    title = raw.get("title", "")
    description = raw.get("description", "")
    diagnostics: list[str] = []
    if not isinstance(title, str) or len(title) > MAX_TITLE_CHARS:
        diagnostics.append("title is invalid or longer than 256 characters")
        title = ""
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_CHARS:
        diagnostics.append("description is invalid or longer than 4,096 characters")
        description = ""

    input_source = raw.get("inputSchema", raw.get("input_schema"))
    output_source = raw.get("outputSchema", raw.get("output_schema"))
    annotations = raw.get("annotations", {})
    if not isinstance(annotations, dict):
        diagnostics.append("annotations must be a JSON object")
        annotations = {}
    source_record = {"name": source_name, "title": title, "description": description,
                     "inputSchema": input_source, "outputSchema": output_source,
                     "annotations": annotations}
    source_text = _json_text(source_record)
    source_size = len(source_text.encode("utf-8"))
    schema_revision = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] | None = None
    if source_size > MAX_SCHEMA_BYTES:
        diagnostics.append("tool schema metadata exceeds the 64 KiB review limit")
    else:
        if isinstance(input_source, dict):
            input_schema = _strip_schema_annotations(input_source)
        diagnostics.extend(_schema_diagnostics(input_source, root_object=True))
        if output_source is not None:
            if isinstance(output_source, dict):
                output_schema = _strip_schema_annotations(output_source)
            diagnostics.extend(_schema_diagnostics(output_source, root_object=False))

    annotations_text = _json_text(annotations)
    if len(annotations_text.encode("utf-8")) > 8192:
        annotations = {}
        diagnostics.append("annotations exceed the 8 KiB review limit")

    input_schema = input_schema if source_size <= MAX_SCHEMA_BYTES else {}
    output_schema = output_schema if source_size <= MAX_SCHEMA_BYTES else None
    diagnostics = list(dict.fromkeys(diagnostics))[:MAX_DIAGNOSTICS]
    return {
        "server_tool_name": source_name,
        "canonical_name": exposed_name,
        "schema_revision": schema_revision,
        "title": title,
        "description": description,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "annotations": annotations,
        "supported": not diagnostics,
        "diagnostics": diagnostics,
    }


def normalize_mcp_tools(integration_id: str, tools: list[Any]) -> list[dict[str, Any]]:
    """Normalize one fully paginated response and refuse ambiguous tool identities."""
    if not isinstance(tools, list) or len(tools) > MAX_DISCOVERED_TOOLS:
        raise McpToolSchemaError("MCP server returned more than 200 tools")
    normalized = [normalize_mcp_tool(integration_id, tool) for tool in tools]
    names = [item["server_tool_name"] for item in normalized]
    if len(names) != len(set(names)):
        raise McpToolSchemaError("MCP server returned duplicate tool names; the catalog was not updated")
    aliases = [item["canonical_name"] for item in normalized]
    if len(aliases) != len(set(aliases)):
        raise McpToolSchemaError("MCP server tool names collide after namespacing; the catalog was not updated")
    return normalized


__all__ = ["MAX_DESCRIPTION_CHARS", "MAX_DISCOVERED_TOOLS", "MAX_SCHEMA_BYTES", "McpToolSchemaError",
           "normalize_mcp_tool", "normalize_mcp_tools"]
