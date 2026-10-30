"""Contract guard for the registered LLM tools: tmp fixtures plus the real registry.

Fixtures build Tool instances to exercise each failure mode; the final test runs
the audit over the actual registry, so drift (a bad name, description, schema or
spec, or an assembly disagreement) fails CI.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "audit_tool_contracts", ROOT / "scripts" / "audit_tool_contracts.py")
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)

from hutch.tools.base import Tool  # noqa: E402

VALID_PARAMETERS = {
    "type": "object",
    "properties": {"path": {"type": "string", "minLength": 1}},
    "required": ["path"],
    "additionalProperties": False,
}


class GoodTool(Tool):
    name = "good_tool"
    description = "Read one file and return its contents for a focused contract test."
    parameters = VALID_PARAMETERS

    def run(self, args, ctx):
        raise AssertionError("contract checks must never execute a tool")


class EmptyNameTool(GoodTool):
    name = ""


class UnsafeNameTool(GoodTool):
    name = "bad tool/name"


class EmptyDescriptionTool(GoodTool):
    description = ""


class NonObjectParametersTool(GoodTool):
    parameters = {"type": "string"}


class UncertifiableParametersTool(GoodTool):
    parameters = {
        "type": "object",
        "patternProperties": {"^x": {"type": "string"}},
    }


class NonSerializableParametersTool(GoodTool):
    parameters = {"type": "object", "properties": {"path": object()}}


class WrongSpecNameTool(GoodTool):
    def spec(self):
        specification = super().spec()
        specification["function"]["name"] = "other_tool"
        return specification


class HugeSchemaTool(GoodTool):
    parameters = {
        "type": "object",
        "properties": {f"p{index}": {"type": "string"} for index in range(2000)},
    }


def test_valid_tool_passes():
    assert contracts.check_tool(GoodTool()) == []


def test_invalid_names_are_rejected():
    empty = contracts.check_tool(EmptyNameTool())
    assert any("non-empty string" in finding for finding in empty)
    unsafe = contracts.check_tool(UnsafeNameTool())
    assert any("provider-safe" in finding for finding in unsafe)


def test_missing_description_is_rejected():
    findings = contracts.check_tool(EmptyDescriptionTool())
    assert any("description" in finding for finding in findings)


def test_parameters_must_be_an_object_schema():
    findings = contracts.check_tool(NonObjectParametersTool())
    assert any("type 'object'" in finding for finding in findings)


def test_uncertifiable_schema_is_rejected():
    findings = contracts.check_tool(UncertifiableParametersTool())
    assert any("cannot be certified" in finding for finding in findings)


def test_non_json_serializable_parameters_are_rejected():
    findings = contracts.check_tool(NonSerializableParametersTool())
    assert any("JSON-serializable" in finding for finding in findings)


def test_spec_must_match_the_registered_tool():
    findings = contracts.check_tool(WrongSpecNameTool())
    assert any("does not match registered name" in finding for finding in findings)


def test_duplicate_names_and_registry_name_drift_are_rejected():
    duplicates = contracts.check_entries([("good_tool", GoodTool()),
                                          ("good_tool", GoodTool())])
    assert any("duplicate tool name" in finding for finding in duplicates)
    drifted = contracts.check_entries([("renamed", GoodTool())])
    assert any("does not match Tool.name" in finding for finding in drifted)


def test_schema_too_large_for_planning_is_rejected():
    findings = contracts.check_tool(HugeSchemaTool())
    assert any("planning failed" in finding and "schema.size" in finding
               for finding in findings), findings


def test_real_registry_assembly_is_consistent():
    assert contracts.check_registry_consistency() == []


def test_real_registry_satisfies_the_contract():
    """CI drift guard for the tools Hutch actually registers."""
    findings = contracts.audit()
    assert findings == []
    entries = contracts.registered_tools()
    names = [name for name, _tool in entries]
    assert len(names) == len(set(names))
    assert len(entries) >= 30
    assert {
        "shell",
        "browser",
        "computer",
        "ask_user_choice",
        "use_skill",
        "recommend_workflow",
        "google_calendar_events",
        "google_mail_search",
    } <= set(names)
    assert any(name.startswith("mcp__notionfixture__") for name in names)
    assert any(name.startswith("mcp__kdeconnectfixture__") for name in names)
