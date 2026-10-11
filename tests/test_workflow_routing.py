"""Routing policy, auto scope, and the model-facing authoring gate.

These pin the mission's routing rules: no over-orchestration, explainable recommendations,
Auto only inside a preauthorized scope, and authoring that never starts work.
"""
from __future__ import annotations

from hutch.models import Bot
from hutch.workflow import routing
from hutch.workflow.qualify import acknowledge_limited


def bot(store, **overrides) -> Bot:
    fields = {"name": "route-bot", "model": "ollama/qwen3:4b", "tools": []}
    fields.update(overrides)
    instance = Bot(**fields)
    store.upsert_bot(instance)
    return store.get_bot(instance.id) or instance


def test_greetings_and_simple_edits_stay_direct():
    for signals in ({}, {"conversational": True}, {"single_step": True}):
        rec = routing.recommend(signals=signals)
        assert rec.route == "direct", signals
        assert rec.simpler
    # A workflow-shaped signal without established inputs asks rather than inventing steps.
    assert routing.recommend(signals={"independent_items": True}).route == "clarify"


def test_repeatable_procedure_prefers_a_saved_workflow():
    rec = routing.recommend(signals={"repeatable_procedure": True, "known_inputs": True},
                            saved_workflow="weekly-report")
    assert rec.route == "saved_workflow" and "weekly-report" in rec.why
    assert "reviewed method" in rec.why


def test_fanout_and_branching_need_structure_not_length():
    fan = routing.recommend(signals={"independent_items": True, "known_inputs": True})
    assert fan.route == "bounded_fanout" and fan.bounds["max_fanout"] == 8
    branch = routing.recommend(signals={"independent_items": True, "depends_on_results": True,
                                        "known_inputs": True})
    assert branch.route == "dynamic_branch"
    verify = routing.recommend(signals={"needs_verification": True, "repeatable_procedure": True,
                                        "known_inputs": True})
    assert verify.route == "verify_loop" and verify.bounds["max_repairs"] == 2


def test_missing_inputs_clarify_instead_of_inventing_steps():
    rec = routing.recommend(signals={"needs_verification": True})
    assert rec.route == "clarify"
    assert "not established" in rec.why


def test_auto_is_refused_unless_the_operator_opted_in(store):
    bot_off = bot(store)
    allowed, why = routing.check_auto(bot=bot_off, definition={"active": True},
                                      budget={"max_nodes": 5}, plan_name="p")
    assert not allowed and "off" in why

    suggest = bot(store, name="route-suggest", workflow_mode="suggest")
    allowed, why = routing.check_auto(bot=suggest, definition={"active": True},
                                      budget={"max_nodes": 5}, plan_name="p")
    assert not allowed and "suggest" in why


def test_auto_respects_definitions_activation_and_caps(store):
    auto = bot(store, name="route-auto", workflow_mode="auto",
               workflow_limits={"definitions": ["weekly-report"], "max_nodes": 50,
                                "max_model_calls": 5, "max_tokens": 48_000,
                                "max_wall_seconds": 600, "max_fanout": 10})
    ok, why = routing.check_auto(bot=auto, definition={"active": True},
                                 budget={"max_nodes": 20, "max_model_calls": 2,
                                         "max_tokens": 32_000, "max_wall_seconds": 60, "max_fanout": 5},
                                 plan_name="weekly-report")
    assert ok, why
    refused, why = routing.check_auto(bot=auto, definition={"active": True},
                                      budget={"max_nodes": 200, "max_model_calls": 2,
                                              "max_wall_seconds": 60, "max_fanout": 5},
                                      plan_name="weekly-report")
    assert not refused and "max_nodes" in why
    refused, why = routing.check_auto(bot=auto, definition={"active": True},
                                      budget={"max_nodes": 5, "max_tokens": 64_000},
                                      plan_name="weekly-report")
    assert not refused and "max_tokens" in why
    refused, why = routing.check_auto(bot=auto, definition={"active": True},
                                      budget={"max_nodes": 5}, plan_name="something-else")
    assert not refused and "preauthorized definitions" in why
    refused, why = routing.check_auto(bot=auto, definition={"active": False},
                                      budget={"max_nodes": 5}, plan_name="weekly-report")
    assert not refused and "not activated" in why


def test_auto_scope_is_enforced_on_submission(store, config):
    """A submission that declares itself automatic must fit the preauthorized scope."""
    import pytest

    from hutch.models import Bot
    from hutch.workflow import submit as wfsubmit
    from tests.test_workflow_engine import deterministic_plan, make_bot

    bot = make_bot(store, name="auto-bot", model="ollama/qwen3:4b", tools=["files"])
    plan = deterministic_plan()
    plan["budget"] = {"max_nodes": 30, "max_model_calls": 0, "max_fanout": 5}
    # Off by default: an automatic start is refused.
    with pytest.raises(wfsubmit.PlanNotSubmittable) as info:
        wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="auto-plan", auto=True)
    assert "automatic start was refused" in str(info.value)
    # A person's explicit start of the same plan is fine.
    wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="auto-plan")
    # With an auto scope that names the definition and fits the budget, auto is allowed
    # once the definition itself is activated (activation is a separate, explicit act).
    from hutch.workflow import persistence as wstore

    entry = wstore.definition(store, "auto-plan")
    assert entry is not None
    wstore.set_active(store, str(entry["id"]), True)
    bot.workflow_mode = "auto"
    bot.workflow_limits = {"definitions": ["auto-plan"], "max_nodes": 50, "max_model_calls": 5}
    store.upsert_bot(bot, preserve_schedules=True)
    allowed = wfsubmit.submit_saved(store, bot=bot, definition="auto-plan", auto=True)
    assert allowed.workflow_run_id.startswith("wrun_")
    # A tighter cap refuses it again.
    bot.workflow_limits = {"definitions": ["auto-plan"], "max_nodes": 5}
    store.upsert_bot(bot, preserve_schedules=True)
    with pytest.raises(wfsubmit.PlanNotSubmittable) as info:
        wfsubmit.submit_saved(store, bot=bot, definition="auto-plan", auto=True)
    assert "max_nodes" in str(info.value)


def test_blocked_role_explanation_names_the_options():
    lines = routing.explain_block(None, [{"role": "author", "allowed": False,
                                          "reasons": ["no probed evidence"],
                                          "route": {"spec": "ollama/qwen3:4b"}}])
    assert lines and "Options:" in lines[0] and "bounded worker role" in lines[0]


def test_authoring_tool_is_refused_without_probed_evidence(store, config):
    from hutch.tools import build_tools
    from hutch.tools.base import ToolContext
    from hutch.safety import PolicyEngine
    from hutch.approvals import ApprovalGate
    from hutch.models import Run

    instance = bot(store, name="author-bot")
    run = Run(bot_id=instance.id, prompt="draft")
    store.submit_run(run, __import__("hutch.models", fromlist=["Task"]).Task(
        bot_id=instance.id, kind="on_demand", prompt="draft"))
    ctx = ToolContext(bot=instance, run=run, store=store, policy=PolicyEngine(instance.risk_tier, []),
                      gate=ApprovalGate(store, instance, run, PolicyEngine(instance.risk_tier, []), lambda e: None),
                      config=config, workspace=config.run_dir(instance.name, run.id))
    tools = build_tools(["draft_workflow"], ctx)
    tool = tools["draft_workflow"]
    plan = {"name": "x", "envelope": {"tools": []}, "budget": {"max_nodes": 3},
            "nodes": [{"kind": "transform", "id": "t", "op": "constant", "args": {"value": 1}}]}
    refused = tool.run({"plan": plan}, ctx)
    assert refused.ok is False
    assert "not qualified to author" in refused.output
    assert refused.data["qualification"]["allowed"] is False

    # A passed probe unlocks authoring for that exact route; the tool still never starts work.
    from tests.support.workflow_probes import seed_passed_probe

    execution_hash = "d" * 64
    seed_passed_probe(store, spec=instance.model, role="author", profile_hash=execution_hash)
    ctx.model_execution_profile = {"fingerprint": execution_hash}
    accepted = tool.run({"plan": plan, "save": True, "name": "drafted-by-model"}, ctx)
    assert accepted.ok is True and accepted.data["started"] is False
    from hutch.workflow import persistence as wstore

    saved = wstore.definition(store, "drafted-by-model")
    assert saved is not None and saved["active"] == 0


def _revision(store, instance) -> str:
    from hutch.workflow.qualify import route_ref

    return route_ref(instance.model).revision
