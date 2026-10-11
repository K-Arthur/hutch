"""Compiler, capability profiles, schema lowering, and the hutch-action envelope.

Unit-level: no model calls. The loop-level behavior (constrained/prompt runs, native
mismatch diagnostics) lives in tests/test_runtime_builtin.py.
"""

from __future__ import annotations

import json

import pytest

from hutch.toolcalling.compiler import (ToolProtocolUnavailable, build_definitions, clear_plan_cache,
                                        compile_plan, openai_function_spec)
from hutch.toolcalling.contracts import ToolDefinition, canonical_json
from hutch.toolcalling.envelope import (EnvelopeUnavailable, build_envelope, decode_action, render_contract)
from hutch.toolcalling.profiles import (Evidence, classify_endpoint, protocol_for_provider, resolve_profile,
                                        strategy_eligibility)
from hutch.toolcalling.schemas import analyze_for_plan, backend_for_protocol, lower_for_backend
from hutch.tools import _CATALOG


def tool_def(name: str = "read_file", schema: dict | None = None) -> ToolDefinition:
    class _T:
        pass

    _T.name = name
    _T.description = "Read a file"
    _T.parameters = schema or {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    return ToolDefinition.from_tool(_T())


def plan_for(provider: str = "ollama", model: str = "fake:8b", *, strategy: str = "auto",
             endpoint: str = "http://localhost:11434", tools: dict | None = None):
    clear_plan_cache()
    profile = resolve_profile(provider=provider, endpoint=endpoint, model=model)
    catalog = tools if tools is not None else {t.name: t for t in [cls() for cls in _CATALOG.values()]}
    return compile_plan(tools=catalog, profile=profile, strategy=strategy), profile


# ------------------------------------------------------------------ profiles


def test_protocol_and_endpoint_classification_is_by_exact_authority():
    assert protocol_for_provider("anthropic") == "anthropic-messages"
    assert protocol_for_provider("ollama") == "ollama-native"
    assert protocol_for_provider("vllm") == "openai-chat"
    assert classify_endpoint("http://localhost:11434") == "local"
    assert classify_endpoint("http://127.0.0.1:8000/v1") == "local"
    assert classify_endpoint("https://api.openai.com/v1") == "official"
    assert classify_endpoint("https://api.openai.com.evil.test/v1") == "custom"
    assert classify_endpoint("") == "unknown"


def test_known_profiles_report_states_instead_of_assuming_family_support():
    ollama = resolve_profile(provider="ollama", endpoint="http://localhost:11434", model="mistral:7b")
    assert ollama.native_tools.state == "documented"
    assert ollama.constrained_schema.supports and ollama.constrained_attachment == "format_field"
    assert "Cloud" in " ".join(ollama.notes)
    cloud = resolve_profile(provider="ollama", endpoint="https://ollama.example", model="qwen3:480b-cloud")
    assert cloud.endpoint_class == "cloud" and not cloud.constrained_schema.supports
    anthropic = resolve_profile(provider="anthropic", endpoint="https://api.anthropic.com", model="claude-opus-5-5")
    assert anthropic.native_tools.supports and not anthropic.constrained_schema.supports
    family_note_only = resolve_profile(provider="ollama", endpoint="http://localhost:11434", model="llama3.2:8b")
    assert family_note_only.native_tools.state == "documented"   # no family-based downgrade exists


def test_observations_upgrade_native_but_not_from_documented_states():
    unknown = resolve_profile(provider="openai-compatible", endpoint="https://example.test/v1", model="m")
    assert unknown.native_tools.state == "advertised"
    observed = resolve_profile(provider="openai-compatible", endpoint="https://example.test/v1", model="m",
                               observations=[{"provider": "openai-compatible", "model": "m",
                                              "route_revision": "x", "observed_at": "2026-10-10"}])
    assert observed.native_tools.state == "observed"
    other_model = resolve_profile(provider="openai-compatible", endpoint="https://example.test/v1", model="n",
                                  observations=[{"provider": "openai-compatible", "model": "m"}])
    assert other_model.native_tools.state == "advertised"


def test_strategy_eligibility_explains_prerequisites():
    ollama = resolve_profile(provider="ollama", endpoint="http://localhost:11434", model="fake:8b")
    ok, why = strategy_eligibility(ollama)["constrained"]
    assert ok and "schema-constrained" in why
    claude = resolve_profile(provider="anthropic", endpoint="https://api.anthropic.com", model="m")
    ok, why = strategy_eligibility(claude)["constrained"]
    assert not ok and why
    for profile in (ollama, claude):
        assert strategy_eligibility(profile)["native"][0]


def test_profile_fingerprint_changes_with_model_and_mode_state():
    a = resolve_profile(provider="ollama", endpoint="http://localhost:11434", model="a")
    b = resolve_profile(provider="ollama", endpoint="http://localhost:11434", model="b")
    assert a.fingerprint() != b.fingerprint()
    view = a.capabilities_view()
    assert "native_tools" in view and view["provider"] == "ollama"


# ------------------------------------------------------------------ safety of evidence


def test_evidence_rejects_unknown_states():
    with pytest.raises(ValueError):
        Evidence(state="vibes")


# ------------------------------------------------------------------ compiler


def test_native_plan_serializes_the_canonical_schema_without_mutating_it():
    definition = tool_def()
    spec = openai_function_spec(definition)
    assert spec["type"] == "function" and spec["function"]["name"] == "read_file"
    assert spec["function"]["parameters"]["required"] == ["path"]
    spec["function"]["parameters"]["required"].append("mutated")
    assert definition.canonical_schema()["required"] == ["path"]     # canonical schema untouched


def test_compiler_defaults_to_native_and_caches_immutable_plans():
    clear_plan_cache()
    profile = resolve_profile(provider="ollama", endpoint="http://localhost:11434", model="fake:8b")
    catalog = {t.name: t for t in [cls() for cls in _CATALOG.values()]}
    plan = compile_plan(tools=catalog, profile=profile, strategy="auto")
    assert plan.strategy == "native" and plan.wire_tools and plan.cache_hit is False
    again = compile_plan(tools=catalog, profile=profile, strategy="auto")
    assert again.cache_hit is True and again.plan_hash == plan.plan_hash
    assert again.tools == plan.tools


def test_a_catalog_change_produces_a_new_plan_hash():
    plan, _ = plan_for()
    other = plan_for(tools={"read_file": _CATALOG["read_file"]()}, strategy="native")[0]
    assert other.catalog_hash != plan.catalog_hash and other.plan_hash != plan.plan_hash


def test_explicitly_unavailable_strategy_refuses_with_the_prerequisite():
    with pytest.raises(ToolProtocolUnavailable, match="constrained"):
        plan_for(provider="anthropic", model="claude-opus-5-5", endpoint="https://api.anthropic.com",
                 strategy="constrained")


def test_disabled_plan_sends_no_tools_and_says_so():
    plan, _ = plan_for(strategy="disabled")
    assert plan.strategy == "disabled" and plan.wire_tools == ()
    assert any(d.code == "strategy.disabled" for d in plan.diagnostics)


def test_constrained_plan_builds_the_discriminated_envelope():
    plan, _ = plan_for(strategy="constrained")
    schema = plan.envelope_schema
    assert schema is not None and "oneOf" in schema
    branches = schema["oneOf"]
    call_branches = [b for b in branches if b["properties"]["action"]["enum"] == ["call"]]
    assert call_branches and call_branches[0]["properties"]["arguments"]["type"] == "object"
    assert any(b["properties"]["action"]["enum"] == ["final"] for b in branches)
    assert plan.prompt_contract and "hutch-action-v1" in plan.prompt_contract
    assert plan.wire_tools == ()


def test_prompt_plan_is_marked_best_effort():
    plan, _ = plan_for(strategy="prompt")
    assert plan.strategy == "prompt" and plan.envelope_schema is None
    assert "contract, not an enforcement" in plan.prompt_contract
    assert any(d.code == "strategy.prompt.best_effort" for d in plan.diagnostics)


def test_aliases_are_reversible_and_plan_resolution_never_fuzzes():
    schema = {"type": "object", "properties": {}}
    weird = tool_def(name="tool with spaces", schema=schema)
    assert weird.visible_name.startswith("tool_")
    plan = compile_plan(tools={"tool with spaces": type("T2", (), {
        "name": "tool with spaces", "description": "", "parameters": schema})()},
        profile=resolve_profile(provider="ollama", endpoint="http://localhost:11434", model="m"))
    visible = plan.tools[0].visible_name
    assert plan.resolve_name(visible).name == "tool with spaces"
    assert plan.resolve_name("tool with space") is None              # no fuzzy match
    assert plan.aliases[visible] == "tool with spaces"


# ------------------------------------------------------------------ lowering


def test_gbnf_lowering_materializes_additional_properties_and_reports_it():
    schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    lowered, diagnostics = lower_for_backend(schema, "gbnf", tool="read_file")
    assert lowered["additionalProperties"] is True
    assert any(d.code == "schema.additionalProperties.materialized" for d in diagnostics)
    assert schema.get("additionalProperties") is None                 # canonical untouched


def test_gbnf_lowering_reports_maps_and_unanchored_patterns_as_local_checks():
    schema = {"type": "object", "properties": {
        "labels": {"type": "object", "additionalProperties": {"type": "string"}},
        "name": {"type": "string", "pattern": "[a-z]+"}}}
    lowered, diagnostics = lower_for_backend(schema, "gbnf", tool="t")
    assert lowered["properties"]["labels"]["additionalProperties"] is True
    assert "pattern" not in lowered["properties"]["name"]
    codes = {d.code for d in diagnostics}
    assert {"schema.additionalProperties.map", "schema.pattern.unanchored"} <= codes


def test_format_is_never_silently_enforced_and_local_refs_inline():
    schema = {"type": "object", "properties": {"when": {"type": "string", "format": "date-time"},
                                               "child": {"$ref": "#/$defs/child"}},
              "$defs": {"child": {"type": "object", "properties": {"x": {"type": "integer"}}}}}
    lowered, diagnostics = lower_for_backend(schema, "xgrammar", tool="t")
    assert "format" not in lowered["properties"]["when"]
    assert "$ref" not in lowered["properties"]["child"]
    assert lowered["properties"]["child"]["properties"]["x"]["type"] == "integer"
    assert any(d.code == "schema.format.unchecked" for d in diagnostics)


def test_cyclic_references_are_refused_for_generation_not_silently_broken():
    schema = {"type": "object", "properties": {"node": {"$ref": "#/$defs/n"}},
              "$defs": {"n": {"type": "object", "properties": {"next": {"$ref": "#/$defs/n"}}}}}
    lowered, diagnostics = lower_for_backend(schema, "gbnf", tool="t")
    assert any(d.code == "schema.ref.cycle" and d.severity == "error" for d in diagnostics)
    definition = tool_def(schema=schema)
    _, tool_diags = analyze_for_plan(definition, "gbnf")
    assert any(d.classification == "unsupported" for d in tool_diags)


def test_backend_family_mapping_follows_the_server_not_the_client():
    assert backend_for_protocol("openai-chat", "vllm") == "xgrammar"
    assert backend_for_protocol("openai-chat", "llamacpp") == "gbnf"
    assert backend_for_protocol("ollama-native", "ollama") == "gbnf"
    assert backend_for_protocol("openai-chat", "openai") == "xgrammar"


def test_envelope_refuses_a_catalog_with_an_unsupported_schema():
    schema = {"type": "object", "properties": {"x": {"$ref": "https://example.test/s.json"}}}
    definition = tool_def(schema=schema)
    with pytest.raises(EnvelopeUnavailable, match="cannot be represented"):
        build_envelope([definition], "gbnf")


# ------------------------------------------------------------------ envelope decode


def decode(content: str, *, names=("read_file", "write_file"), aliases=None):
    return decode_action(content, aliases=aliases or {}, canonical_names=names)


def test_decode_accepts_a_typed_call_and_preserves_exact_numbers():
    candidate = decode('{"action": "call", "tool": "read_file", '
                       '"arguments": {"path": "a.txt", "offset": 9007199254740993, "ratio": 0.45}}')
    assert candidate.kind == "call" and candidate.tool == "read_file"
    assert candidate.arguments["offset"] == 9007199254740993 and candidate.arguments["ratio"] == 0.45
    assert json.loads(candidate.raw_arguments)["ratio"] == 0.45


def test_decode_treats_prose_and_unrelated_json_as_plain_text():
    assert decode("I could not fetch that page.").kind == "plain"
    assert decode('{"name": "read_file", "arguments": {"path": "a"}}').kind == "plain"
    assert decode('["action", "call"]').kind == "invalid"            # a JSON array is not the contract


def test_decode_rejects_contract_violations_with_reasons():
    assert decode('{"action": "call", "tool": "read_file"}').kind == "invalid"
    violation = decode('{"action": "call", "tool": "teleport", "arguments": {}}')
    assert violation.kind == "invalid" and "no tool named" in violation.error
    assert decode('{"action": "call", "tool": "read_file", "arguments": [], "extra": 1}').kind == "invalid"
    assert decode('{"action": "final", "content": 3}').kind == "invalid"
    assert "duplicate" in decode('{"action":"call","tool":"read_file","tool":"write_file",'
                                 '"arguments":{}}').error


def test_decode_resolves_aliases_reversibly():
    candidate = decode('{"action":"call","tool":"tool_abc","arguments":{}}',
                       names=("canonical name",), aliases={"tool_abc": "canonical name"})
    assert candidate.kind == "call" and candidate.tool == "canonical name"


def test_decode_final_and_clarify_branches_are_plain_values():
    final = decode('{"action": "final", "content": "done"}')
    assert (final.kind, final.content) == ("final", "done")
    clarify = decode('{"action": "clarify", "question": "Which file?"}')
    assert (clarify.kind, clarify.content) == ("clarify", "Which file?")
    assert decode('{"action": "clarify", "question": "  "}').kind == "invalid"
