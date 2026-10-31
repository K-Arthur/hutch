#!/usr/bin/env python3
"""Fail fast when a registered Hutch tool breaks the canonical LLM tool contract.

The tool-calling layer is already strong (toolcalling/contracts.py,
toolcalling/validate.py, toolcalling/schemas.py); this script enforces the
existing contract on the live registry instead of inventing a second one:

* unique, non-empty, provider-safe tool name;
* non-empty reviewed description;
* parameters is a JSON-Schema object, JSON-serializable, and certifiable by the
  bounded analyzer (no unsupported keywords, no remote $ref);
* spec() is an OpenAI-style function object whose name and parameters match the
  canonical registered values;
* ToolDefinition.from_tool() snapshots the tool and analyze_for_plan() completes
  for every supported backend without a severity=error diagnostic, so a schema
  cannot enter the planning/lowering path broken;
* registry assembly stays consistent: ALL_TOOL_NAMES matches the catalog plus the
  lazy browser/computer tools, every group member is registered, and every
  grant-gated connection spec constructs with a full synthetic grant.

Registry coverage: the static catalog, the lazy browser/computer tools, the
conversational/runtime-injected tools (ask_user_choice, use_skill,
recommend_workflow), the eight grant-gated calendar/mail tools through their
real constructor, and representative bindings for the provider-discovered Notion
and KDE Connect tools (their live schemas come from the provider catalog and are
revalidated at grant time, so these synthetic bindings only exercise the class
contract).

Usage: uv run --frozen --no-sync python scripts/audit_tool_contracts.py
Exit codes: 0 pass, 1 contract violation, 2 the registry could not be assembled.
Tests: tests/test_tool_contracts.py.
"""
from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from hutch.toolcalling.contracts import ToolDefinition, canonical_json, schema_revision  # noqa: E402
from hutch.toolcalling.schemas import BACKENDS, analyze_for_plan  # noqa: E402
from hutch.toolcalling.validate import analyze_schema  # noqa: E402
from hutch.tools.base import Tool  # noqa: E402

#: Provider-visible identifiers: letters, digits, underscore, dot, hyphen.
NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,96}")
MIN_DESCRIPTION_CHARS = 8
MAX_REPORTED = 40


class ContractAssemblyError(RuntimeError):
    """The registry itself could not be built or imported."""


def _check_spec(tool: Tool, parameters: dict) -> list[str]:
    try:
        spec = tool.spec()
    except Exception as exc:  # noqa: BLE001 - a broken spec() is the finding
        return [f"spec() raised {type(exc).__name__}: {exc}"]
    if not isinstance(spec, dict) or spec.get("type") != "function":
        return ["spec() must return an OpenAI-style {type: function, function: {...}} object"]
    function = spec.get("function")
    if not isinstance(function, dict):
        return ["spec() has no function object"]
    findings: list[str] = []
    if function.get("name") != tool.name:
        findings.append(
            f"spec name {function.get('name')!r} does not match registered name {tool.name!r}")
    if function.get("parameters") != parameters:
        findings.append("spec parameters differ from the canonical Tool.parameters")
    if not isinstance(function.get("description"), str) or not function["description"].strip():
        findings.append("spec description is empty")
    return findings


def _check_planning(tool: Tool) -> list[str]:
    try:
        definition = ToolDefinition.from_tool(tool)
    except Exception as exc:  # noqa: BLE001 - inability to snapshot is the finding
        return [f"ToolDefinition.from_tool failed: {type(exc).__name__}: {exc}"]
    findings: list[str] = []
    expected_revision = schema_revision(definition.canonical_schema())
    if definition.revision != expected_revision:
        findings.append("ToolDefinition revision does not hash the canonical schema")
    for backend in BACKENDS:
        _lowered, diagnostics = analyze_for_plan(definition, backend)
        for diagnostic in diagnostics:
            if diagnostic.severity == "error":
                findings.append(
                    f"{backend} planning failed: {diagnostic.code} at "
                    f"{diagnostic.field or '<root>'}: {diagnostic.detail}")
    return findings


def check_tool(tool: Tool) -> list[str]:
    """Contract findings for one Tool instance (empty list means valid)."""
    findings: list[str] = []
    name = getattr(tool, "name", None)
    if not isinstance(name, str) or not name.strip():
        findings.append("name must be a non-empty string")
    elif not NAME_PATTERN.fullmatch(name):
        findings.append(
            f"name {name!r} is not a provider-safe identifier "
            "([A-Za-z0-9_.-], at most 96 characters)")
    description = getattr(tool, "description", None)
    if not isinstance(description, str) or len(description.strip()) < MIN_DESCRIPTION_CHARS:
        findings.append(
            f"description must be a string of at least {MIN_DESCRIPTION_CHARS} characters")
    parameters = getattr(tool, "parameters", None)
    if not isinstance(parameters, dict):
        return findings + ["parameters must be a JSON Schema object"]
    if parameters.get("type") != "object":
        findings.append("parameters must declare type 'object' at the root")
    try:
        canonical_json(parameters)
    except (TypeError, ValueError) as exc:
        return findings + [f"parameters are not JSON-serializable: {exc}"]
    report = analyze_schema(parameters)
    if not report.certifiable:
        findings.append(
            "parameters cannot be certified by the bounded validator: "
            + "; ".join(report.unsupported[:3]))
    findings.extend(_check_spec(tool, parameters))
    findings.extend(_check_planning(tool))
    return findings


def check_entries(entries: list[tuple[str, Tool]]) -> list[str]:
    """Per-tool findings plus name uniqueness and registry-name agreement."""
    findings: list[str] = []
    seen: dict[str, str] = {}
    for registry_name, tool in entries:
        for finding in check_tool(tool):
            findings.append(f"{registry_name}: {finding}")
        name = getattr(tool, "name", "")
        if not isinstance(name, str) or not name:
            continue
        if registry_name != name:
            findings.append(
                f"{registry_name}: registered name does not match Tool.name {name!r}")
        key = name.casefold()
        if key in seen:
            findings.append(
                f"{registry_name}: duplicate tool name {name!r} (also {seen[key]})")
        else:
            seen[key] = registry_name
    return findings


def check_registry_consistency() -> list[str]:
    """The catalog/group/connection enumerations must agree with each other."""
    from hutch.integrations.catalog import CONNECTION_TOOL_SPECS, known_tool_names
    from hutch.tools import ALL_TOOL_NAMES, GROUPS, _CATALOG

    findings: list[str] = []
    expected = sorted(_CATALOG) + ["browser", "computer"]
    if expected != ALL_TOOL_NAMES:
        missing = sorted(set(expected) - set(ALL_TOOL_NAMES))
        extra = sorted(set(ALL_TOOL_NAMES) - set(expected))
        findings.append(
            f"ALL_TOOL_NAMES drifted from the catalog (missing={missing}, extra={extra})")
    for group, members in sorted(GROUPS.items()):
        unknown = sorted(member for member in members if member not in ALL_TOOL_NAMES)
        if unknown:
            findings.append(
                f"group {group!r} names tools that are not registered: {unknown}")
    known = known_tool_names()
    for spec in CONNECTION_TOOL_SPECS:
        if spec.name not in known:
            findings.append(
                f"connection tool {spec.name!r} is not in known_tool_names()")
    return findings


class _ResolvedSkillsStub:
    """UseSkillTool.spec() only needs .catalog while the registry is enumerated."""

    catalog: list = []


class _GrantStore:
    """Every reviewable account grant is present for construction purposes."""

    def __getattr__(self, attribute: str):
        if attribute.endswith("_grant"):
            return lambda bot_id: {
                "account_id": "account-fixture",
                "calendar_id": "calendar-fixture",
                "calendar_name": "Fixture calendar",
                "account_label": "Fixture account",
                "allow_event_creation": True,
            }
        raise AttributeError(attribute)


class _GrantBot:
    id = "bot-fixture"


def _provider_tools() -> list[tuple[str, Tool]]:
    """Representative bindings for provider-discovered Notion and KDE tools."""
    from hutch.integrations.base import canonical_tool_name
    from hutch.tools.kdeconnect import KDEConnectStatusTool
    from hutch.tools.notion import NotionReadTool

    notion_name = canonical_tool_name("notionfixture", "notion-search")
    notion_binding = {
        "account_id": "notion_0123456789abcdef01234567",
        "name": "notion-search",
        "canonical_name": notion_name,
        "schema_revision": "0" * 16,
        "item": {
            "name": "notion-search",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 200}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }
    kde_name = canonical_tool_name("kdeconnectfixture", "kdeconnect-status")
    kde_binding = {"canonical_name": kde_name, "device_id": "device-fixture",
                   "revision": "0" * 16}
    return [(notion_name, NotionReadTool(notion_binding)),
            (kde_name, KDEConnectStatusTool(kde_binding))]


def registered_tools() -> list[tuple[str, Tool]]:
    """Every tool the runtime can register, as (registered name, instance)."""
    from hutch.integrations.catalog import CONNECTION_TOOL_SPECS, construct_connection_tools
    from hutch.tools import _CATALOG
    from hutch.tools.browser import BrowserTool
    from hutch.tools.assistant_proposal import ProposeAssistantTool
    from hutch.tools.choice import AskUserChoiceTool
    from hutch.tools.computer import ComputerTool
    from hutch.tools.skill import UseSkillTool
    from hutch.tools.workflow_route import WorkflowRouteTool

    entries: list[tuple[str, Tool]] = [(name, cls())
                                       for name, cls in sorted(_CATALOG.items())]
    entries.extend([
        ("browser", BrowserTool()),
        ("computer", ComputerTool()),
        ("ask_user_choice", AskUserChoiceTool()),
        ("propose_assistant", ProposeAssistantTool()),
        ("use_skill", UseSkillTool(_ResolvedSkillsStub())),
        (WorkflowRouteTool.name, WorkflowRouteTool()),
    ])
    connection_tools = construct_connection_tools(
        _GrantStore(), _GrantBot(), local_gmail_ok=True)
    entries.extend((name, connection_tools[name]) for name in sorted(connection_tools))
    missing = sorted(spec.name for spec in CONNECTION_TOOL_SPECS
                     if spec.name not in connection_tools)
    if missing:
        raise ContractAssemblyError(
            "grant-gated tools did not construct from a full synthetic grant: "
            + ", ".join(missing))
    entries.extend(_provider_tools())
    return entries


def audit() -> list[str]:
    """Registry-wide contract findings; empty list means compliant."""
    findings = check_registry_consistency()
    entries = registered_tools()
    findings.extend(check_entries(entries))
    return findings


def main() -> int:
    try:
        entries = registered_tools()
        findings = check_registry_consistency() + check_entries(entries)
    except ContractAssemblyError as exc:
        print(f"Tool contract check failed to assemble the registry: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - import/construction failures are infrastructure
        print(f"Tool contract check could not run ({type(exc).__name__}: {exc})", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 2
    if findings:
        print(f"Tool contract violations ({len(findings)} across {len(entries)} tools):",
              file=sys.stderr)
        for finding in findings[:MAX_REPORTED]:
            print(f"  {finding}", file=sys.stderr)
        if len(findings) > MAX_REPORTED:
            print(f"  ... and {len(findings) - MAX_REPORTED} more", file=sys.stderr)
        return 1
    print(f"Tool contract check passed ({len(entries)} registered tools; canonical "
          "schemas certifiable; specs match).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
