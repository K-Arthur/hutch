"""Canonical tool-argument validation: strict decoding, bounded schema checks, repair rules.

These are parser/contract tests with scripted inputs, not live-model evidence. They pin the
failure classes recorded in docs/realignment/tool-calling.md (vLLM #39380 numeric corruption,
Ollama #11662 call-looking content, Anthropic fine-grained invalid JSON).
"""

from __future__ import annotations

import json

import pytest

from hutch.providers.base import parse_tool_args, parse_tool_args_state
from hutch.runtime.toolrepair import coerce_args, validate_args
from hutch.toolcalling.strictjson import JSONProblem, loads_strict
from hutch.toolcalling.validate import analyze_schema, required_fields, schema_engine, validate_call


# ------------------------------------------------------------------ strict JSON


def test_strict_json_accepts_one_plain_object_and_preserves_big_integers():
    value = loads_strict('{"id": 9007199254740993, "n": 0.45, "e": 1.1}')
    assert value["id"] == 9007199254740993 and isinstance(value["id"], int)
    assert value["n"] == 0.45 and value["e"] == 1.1


def test_strict_json_rejects_duplicate_keys_instead_of_keeping_the_last():
    with pytest.raises(JSONProblem, match="duplicate object key"):
        loads_strict('{"path": "safe.txt", "path": "/etc/passwd"}')


def test_strict_json_rejects_nan_and_infinity():
    for raw in ('{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}'):
        with pytest.raises(JSONProblem, match="not valid JSON"):
            loads_strict(raw)


def test_strict_json_rejects_trailing_content_and_deep_nesting():
    with pytest.raises(JSONProblem, match="not valid JSON"):
        loads_strict('{"a": 1} trailing')
    deep = "[" * 80 + "]" * 80
    with pytest.raises(JSONProblem):
        loads_strict(deep)


def test_strict_json_rejects_empty_and_oversized_text():
    with pytest.raises(JSONProblem, match="no JSON value"):
        loads_strict("   ")
    with pytest.raises(JSONProblem, match="exceed"):
        loads_strict('{"a": "' + "x" * 100 + '"}', max_chars=50)


# ------------------------------------------------------- provider argument parsing


def test_argument_states_distinguish_absent_invalid_and_present():
    assert parse_tool_args_state({"a": 1}) == ({"a": 1}, "", "json_object", False)
    assert parse_tool_args_state('{"a": 1}')[2] == "json_object"
    assert parse_tool_args_state("")[2] == "empty"
    assert parse_tool_args_state(None)[2] == "empty"
    assert parse_tool_args_state('{"a": ')[2] == "invalid"
    assert parse_tool_args_state("[1, 2]")[2] == "invalid"
    args, err, state, double = parse_tool_args_state('"{\\"a\\": 1}"')
    assert (args, err, state, double) == ({"a": 1}, "", "json_object", True)


def test_invalid_json_message_is_precise_and_never_decodes_to_arguments():
    args, err, state, _ = parse_tool_args_state('{"a": NaN}')
    assert args == {} and state == "invalid" and "not valid JSON" in err


def test_legacy_wrapper_still_returns_dict_and_error():
    assert parse_tool_args({"a": 1}) == ({"a": 1}, "")
    assert parse_tool_args("") == ({}, "")
    assert parse_tool_args('{"a": 1}') == ({"a": 1}, "")


# ------------------------------------------------------------- canonical validation


def test_required_missing_and_unknown_arguments_are_rejected():
    schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"],
              "additionalProperties": False}
    assert "missing required argument 'path'" in validate_call(schema, {"content": "x"})[0]
    assert any("unknown argument 'extra'" in p for p in validate_call(schema, {"path": "a", "extra": 1}))


def test_additional_properties_false_with_empty_properties_rejects_everything():
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    assert validate_call(schema, {"x": 1}) == ["unknown argument 'x' (allowed: (none))"]
    assert validate_call(schema, {}) == []


def test_types_are_checked_without_boolean_integer_confusion():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}, "b": {"type": "boolean"}},
              "required": ["n", "b"]}
    assert validate_call(schema, {"n": True, "b": False}) != []
    assert validate_call(schema, {"n": 2, "b": "yes"}) != []
    assert validate_call(schema, {"n": 2, "b": False}) == []


def test_union_types_and_nulls_follow_json_schema_presence_rules():
    schema = {"type": "object", "properties": {"note": {"type": ["string", "null"]}}, "required": ["note"]}
    assert validate_call(schema, {"note": None}) == []
    assert validate_call(schema, {"note": "hi"}) == []
    assert validate_call(schema, {}) != []                     # omission is not null
    assert validate_call(schema, {"note": 3}) != []


def test_nested_arrays_items_bounds_and_enum_are_checked():
    schema = {"type": "object",
              "properties": {"mode": {"type": "string", "enum": ["single", "multiple"]},
                             "options": {"type": "array", "minItems": 2, "maxItems": 3,
                                         "items": {"type": "string", "minLength": 1}}},
              "required": ["mode", "options"], "additionalProperties": False}
    assert validate_call(schema, {"mode": "single", "options": ["a", "b"]}) == []
    assert validate_call(schema, {"mode": "both", "options": ["a", "b"]}) != []
    assert validate_call(schema, {"mode": "single", "options": ["a"]}) != []
    assert validate_call(schema, {"mode": "single", "options": ["a", 2]}) != []


def test_annotations_are_ignored_and_defaults_never_become_arguments():
    schema = {"type": "object", "properties": {"path": {"type": "string", "default": "/tmp", "description": "p"}},
              "required": []}
    assert validate_call(schema, {}) == []
    assert validate_args(schema, {}) == []                     # default is metadata, not a value


def test_unsupported_or_unknown_keywords_refuse_to_certify_instead_of_widening():
    unsupported = analyze_schema({"type": "object", "patternProperties": {"^x": {"type": "string"}}})
    assert not unsupported.certifiable and "patternProperties" in unsupported.unsupported[0]
    assert "cannot be fully checked" in validate_call(
        {"type": "object", "patternProperties": {"^x": {"type": "string"}}}, {"x": 1})[0]
    unknown = analyze_schema({"type": "object", "requred": ["a"]})
    assert not unknown.certifiable and "unknown schema keyword" in unknown.unsupported[0]


def test_recursive_or_remote_references_are_never_resolved():
    remote = analyze_schema({"type": "object", "properties": {"a": {"$ref": "https://example.test/s.json"}}})
    assert not remote.certifiable and "remote reference" in remote.unsupported[0]
    local = {"$defs": {"node": {"type": "object", "properties": {"next": {"$ref": "#/$defs/node"}}}},
             "type": "object", "properties": {"root": {"$ref": "#/$defs/node"}}}
    report = analyze_schema(local)
    assert report.refs and set(report.refs) == {"#/$defs/node"}
    # A cyclic local reference cannot be certified by the bounded validator: fail closed.
    assert validate_call(local, {"root": {"next": {}}}) != []


def test_analyze_reports_maps_unions_and_formats_for_planners():
    report = analyze_schema({
        "type": "object",
        "properties": {"labels": {"type": "object", "additionalProperties": {"type": "string"}},
                       "which": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                       "when": {"type": "string", "format": "date-time"}},
    })
    assert report.uses_maps and report.uses_unions
    assert report.format_fields and report.certifiable


def test_declared_catalog_schemas_are_certifiable_by_the_bounded_engine():
    """The shipped tools must not rely on keywords this install cannot check."""
    from hutch.tools import _CATALOG
    from hutch.tools.choice import AskUserChoiceTool

    tools = [cls() for cls in _CATALOG.values()] + [AskUserChoiceTool()]
    for tool in tools:
        report = analyze_schema(tool.parameters)
        assert report.certifiable, f"{tool.name}: {report.unsupported}"


def test_required_fields_helper_is_top_level_only():
    assert required_fields({"required": ["a", "b"]}) == ["a", "b"]
    assert required_fields({"properties": {"a": {"required": ["x"]}}}) == []


# ---------------------------------------------------------------------- coercion


def test_coercion_is_typed_and_never_guesses_across_unions():
    changed, notes = coerce_args({"properties": {"n": {"type": "integer"}}}, {"n": "5"})
    assert changed == {"n": 5} and notes
    ambiguous, notes = coerce_args({"properties": {"n": {"type": ["integer", "string"]}}}, {"n": "5"})
    assert ambiguous == {"n": "5"} and not notes
    untouched, notes = coerce_args({"properties": {"s": {"type": "string"}}}, {"s": "007"})
    assert untouched == {"s": "007"} and not notes


def test_coercion_does_not_turn_booleans_into_integers():
    result, notes = coerce_args({"properties": {"n": {"type": "integer"}}}, {"n": True})
    assert result == {"n": True} and not notes


def test_repaired_values_still_pass_the_canonical_validator():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    fixed, _ = coerce_args(schema, {"n": "5"})
    assert validate_call(schema, fixed) == []


def test_engine_name_is_available_for_diagnostics():
    assert schema_engine() in ("jsonschema-2020-12", "hutch-bounded-v1")


@pytest.mark.parametrize("full_validator", [False, True])
def test_value_repair_diagnostics_stay_stable_when_sdk_installs_jsonschema(monkeypatch, full_validator):
    import hutch.toolcalling.validate as validation
    monkeypatch.setattr(validation, "_HAVE_JSONSCHEMA", full_validator)
    problems = validation.validate_value({"type": "integer", "minimum": 300}, 2)
    assert len(problems) == 1 and ">= 300" in problems[0]
    assert validation.validate_value({"type": "integer", "minimum": 300}, 301) == []
