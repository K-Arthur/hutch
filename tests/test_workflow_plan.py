"""Plan schema, reference/condition evaluation and compilation contracts.

These are deterministic, offline contract tests: they pin identity, reference scope,
envelope membership, cardinality expansion, fail-closed schema certification and the
strictness rules that keep a malformed plan from silently becoming a no-op.
"""
from __future__ import annotations

import copy

import pytest

from hutch.workflow import compile as wf_compile
from hutch.workflow.expr import EvalError, Scope, evaluate, render_template, resolve_value
from hutch.workflow.plan import CEILINGS, Condition, Plan


def minimal(**overrides) -> dict:
    plan = {
        "name": "demo",
        "inputs": {"topic": {"type": "string"}},
        "envelope": {"tools": ["list_files", "read_file"], "models": ["ollama/qwen3:4b"]},
        "budget": {"max_nodes": 50, "max_model_calls": 5, "max_fanout": 5},
        "nodes": [
            {"kind": "tool", "id": "scan", "tool": "list_files", "args": {"path": "."}},
            {"kind": "agent", "id": "summarize", "instruction": "Summarize {{topic}} from {{scan.files}}",
             "inputs": {"topic": {"ref": "input.topic"}, "files": {"ref": "scan.files"}},
             "tools": ["read_file"], "model": "ollama/qwen3:4b"},
            {"kind": "publish", "id": "done", "artifacts": [
                {"name": "summary", "ref": "summarize.output", "primary": True}]},
        ],
    }
    plan.update(overrides)
    return plan


def compile_ok(raw: dict) -> wf_compile.CompiledPlan:
    return wf_compile.compile_plan(copy.deepcopy(raw))


def codes(exc: wf_compile.PlanInvalid) -> set[str]:
    return {d.code for d in exc.diagnostics}


def test_minimal_plan_compiles_with_stable_identity_and_hash():
    compiled = compile_ok(minimal())
    assert [n.site_id for n in compiled.top_level()] == ["scan", "summarize", "done"]
    assert compiled.by_site["summarize"].deps == ("scan",)
    assert compiled.by_site["done"].deps == ("summarize",)
    assert compiled.by_site["done"].kind == "publish"
    again = compile_ok(minimal())
    assert again.plan_hash == compiled.plan_hash
    changed = minimal()
    changed["description"] = "different"
    assert compile_ok(changed).plan_hash != compiled.plan_hash


def test_plan_is_strict_about_unknown_fields():
    raw = minimal()
    raw["nodes"][0]["toolz"] = "typo"
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert codes(info.value) == {"PLAN_SCHEMA"}


def test_kind_specific_fields_are_rejected_not_ignored():
    raw = minimal()
    raw["nodes"][0]["body"] = [{"kind": "tool", "id": "nested", "tool": "list_files", "args": {}}]
    with pytest.raises(wf_compile.PlanInvalid):
        compile_ok(raw)


def test_reference_scope_rules():
    raw = minimal()
    raw["nodes"][1]["inputs"]["files"] = {"ref": "later.files"}  # forward reference
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "REF_UNKNOWN" in codes(info.value)

    raw = minimal()
    raw["nodes"][1]["inputs"]["files"] = {"ref": "input.missing"}
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "REF_INPUT" in codes(info.value)

    raw = minimal()
    raw["nodes"][1]["inputs"]["files"] = {"ref": "item.path"}  # local outside a map
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "REF_LOCAL" in codes(info.value)


def test_container_children_are_not_addressable_from_outside():
    raw = minimal()
    raw["nodes"].insert(1, {
        "kind": "map", "id": "each", "over": {"ref": "scan.files"}, "item_key": "path",
        "max_items": 3, "body": [
            {"kind": "agent", "id": "read", "instruction": "Read {{item.path}}",
             "inputs": {"item": {"ref": "item"}}, "tools": ["read_file"],
             "model": "ollama/qwen3:4b"}]})
    raw["nodes"][2]["inputs"]["files"] = {"ref": "each.read.output"}  # inner node id
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "REF_CONTAINER_PATH" in codes(info.value)


def test_nested_map_ids_are_namespaced_and_instances_multiply():
    raw = minimal()
    raw["budget"]["max_nodes"] = 500
    raw["nodes"].insert(1, {
        "kind": "map", "id": "each", "over": {"ref": "scan.files"}, "item_key": "path",
        "max_items": 4, "body": [
            {"kind": "transform", "id": "pick", "op": "pluck",
             "args": {"value": {"ref": "item"}, "path": "path"}}]})
    compiled = compile_ok(raw)
    assert "each.pick" in compiled.by_site
    assert compiled.by_site["each.pick"].body_of == "each"
    assert compiled.by_site["each.pick"].deps == ()
    assert compiled.by_site["each"].instances == 1 + 4 * 1


def test_budget_nodes_expansion_is_checked_statically():
    raw = minimal()
    raw["budget"]["max_nodes"] = 10
    raw["nodes"].insert(1, {
        "kind": "map", "id": "outer", "over": {"ref": "scan.files"}, "item_key": "path",
        "max_items": 5, "body": [
            {"kind": "map", "id": "inner", "over": {"ref": "item.children"}, "item_key": "path",
             "max_items": 5, "body": [
                 {"kind": "transform", "id": "t", "op": "count", "args": {"items": {"ref": "item"}}}]}]})
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "BUDGET_NODES" in codes(info.value)


def test_default_workflow_bounds_match_the_initial_chat_limits():
    plan = compile_ok({"name": "defaults", "nodes": [
        {"kind": "transform", "id": "done", "op": "constant", "args": {"value": True}},
    ]}).plan
    assert plan.budget.model_dump() == {
        "max_nodes": 40, "max_model_calls": 12, "max_tokens": 64_000,
        "max_wall_seconds": 900, "max_fanout": 8, "max_repairs": 2,
    }
    assert plan.envelope.max_parallel_steps == 2


def test_envelope_membership_is_enforced():
    raw = minimal()
    raw["nodes"][1]["tools"] = ["shell"]  # not in the workflow envelope
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "AGENT_TOOLS" in codes(info.value)

    raw = minimal()
    raw["nodes"][1]["model"] = "openai/gpt-x"
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "AGENT_MODEL" in codes(info.value)

    raw = minimal()
    raw["nodes"].insert(1, {
        "kind": "map", "id": "each", "over": {"ref": "scan.files"}, "item_key": "k",
        "concurrency": 3, "max_items": 2, "body": [
            {"kind": "transform", "id": "t", "op": "count", "args": {"items": {"ref": "item"}}}]})
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "MAP_CONCURRENCY" in codes(info.value)


def test_verify_requires_independent_evidence():
    raw = minimal()
    raw["nodes"].insert(2, {
        "kind": "verify", "id": "check", "checks": [
            {"kind": "agent_review", "instruction": "review it", "ref": "summarize.output"}]})
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "VERIFY_NO_EVIDENCE" in codes(info.value)

    raw["nodes"][2]["checks"] = [{"kind": "schema", "ref": "summarize.output",
                                  "schema": {"type": "object", "required": ["summary"],
                                             "properties": {"summary": {"type": "string"}}}}]
    compiled = compile_ok(raw)
    assert compiled.by_site["check"].deps == ("summarize",)


def test_uncertifiable_output_schema_is_refused():
    raw = minimal()
    raw["nodes"][1]["output_schema"] = {"if": {"type": "object"}, "then": {"required": ["x"]}}
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "OUTPUT_SCHEMA_UNCERTIFIABLE" in codes(info.value)


def test_unknown_transform_op_and_args_are_errors():
    raw = minimal()
    raw["nodes"].insert(0, {"kind": "transform", "id": "t", "op": "eval_python", "args": {}})
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "UNKNOWN_OP" in codes(info.value)

    raw = minimal()
    raw["nodes"].insert(0, {"kind": "transform", "id": "t", "op": "count",
                            "args": {"items": [], "extra": 1}})
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "OP_ARGS" in codes(info.value)


def test_nesting_depth_is_bounded():
    raw = minimal()
    raw["budget"]["max_nodes"] = CEILINGS["max_nodes"]
    body = [{"kind": "transform", "id": "leaf", "op": "count", "args": {"items": {"ref": "item"}}}]
    for level in range(4):
        body = [{"kind": "map", "id": f"m{level}", "over": {"ref": "item"}, "item_key": "k",
                 "max_items": 2, "body": body}]
    raw["nodes"] = body + raw["nodes"]
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "NESTING_TOO_DEEP" in codes(info.value)


def test_duplicate_site_ids_and_primary_artifacts_are_errors():
    raw = minimal()
    raw["nodes"].append({"kind": "tool", "id": "scan", "tool": "list_files", "args": {}})
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "NODE_ID_DUPLICATE" in codes(info.value)

    raw = minimal()
    raw["nodes"].append({"kind": "publish", "id": "done2", "artifacts": [
        {"name": "other", "ref": "summarize.output", "primary": True}]})
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "ARTIFACT_PRIMARY" in codes(info.value)


def test_instruction_placeholders_must_match_declared_inputs():
    raw = minimal()
    raw["nodes"][1]["instruction"] = "Summarize {{missing}}"
    with pytest.raises(wf_compile.PlanInvalid) as info:
        compile_ok(raw)
    assert "INSTRUCTION_PLACEHOLDER" in codes(info.value)


def test_map_without_item_key_warns_instead_of_failing():
    raw = minimal()
    raw["nodes"].insert(1, {
        "kind": "map", "id": "each", "over": {"ref": "scan.files"}, "max_items": 2, "body": [
            {"kind": "transform", "id": "t", "op": "count", "args": {"items": {"ref": "item"}}}]})
    compiled = compile_ok(raw)
    assert {"MAP_NO_ITEM_KEY"} == {w.code for w in compiled.warnings}


def test_condition_evaluation_is_strict():
    scope = Scope({"input": {"n": 3, "name": "alpha", "empty": []}, "n1": {"items": [1, 2, 3]}})
    assert evaluate(Condition(ref="input.n", op="gt", value=2), scope)
    assert evaluate(Condition(ref="input.n", op="in", value=[1, 2, 3]), scope)
    assert evaluate(Condition(ref="input.name", op="matches", value="^alp"), scope)
    assert evaluate(Condition(ref="input.empty", op="is_empty"), scope)
    assert evaluate(Condition(all=[Condition(ref="input.n", op="ge", value=3),
                                   Condition(ref="input.name", op="ne", value="beta")]), scope)
    assert evaluate(Condition(not_=Condition(ref="input.n", op="lt", value=3)), scope)
    assert evaluate(Condition(ref="input.missing", op="exists"), scope) is False

    with pytest.raises(EvalError):
        evaluate(Condition(ref="input.missing", op="eq", value=1), scope)
    with pytest.raises(EvalError):
        evaluate(Condition(ref="input.name", op="gt", value=1), scope)
    with pytest.raises(EvalError):
        evaluate(Condition(ref="input.name", op="matches", value="("), scope)
    # booleans never compare equal to numbers
    truthy = Scope({"v": True})
    assert evaluate(Condition(ref="v", op="ne", value=1), truthy)


def test_value_resolution_and_templates():
    scope = Scope({"input": {"topic": "birds"}, "n1": {"items": [{"path": "a"}, {"path": "b"}]}})
    assert resolve_value({"ref": "n1.items[1].path"}, scope) == "b"
    assert resolve_value({"ref": "n1.items[-1].path"}, scope) == "b"
    assert resolve_value([{"ref": "input.topic"}, 3], scope) == ["birds", 3]
    assert resolve_value({"template": "topic is {{t}}", "values": {"t": {"ref": "input.topic"}}},
                         scope) == "topic is birds"
    with pytest.raises(EvalError):
        resolve_value({"ref": "n1.items[9].path"}, scope)
    with pytest.raises(EvalError):
        resolve_value({"template": "{{nope}}", "values": {}}, scope)
    with pytest.raises(EvalError):
        render_template("{{a}}", {})
    assert render_template("no placeholders", {}) == "no placeholders"


def test_compiled_plan_is_json_serializable_through_the_plan_model():
    compiled = compile_ok(minimal())
    dumped = compiled.plan.model_dump(by_alias=True, exclude_none=True, mode="json")
    assert wf_compile.plan_hash(Plan.model_validate(dumped)) == compiled.plan_hash
