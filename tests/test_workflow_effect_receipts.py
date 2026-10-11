"""Stable workflow effect identities prevent dispatch after a process replacement."""
from __future__ import annotations

import hashlib

import pytest

from hutch import action_receipts
from hutch.approvals import ApprovalGate
from hutch.models import RunStatus
from hutch.runtime import steps
from hutch.safety import PolicyEngine
from hutch.tools.base import Tool, ToolContext, ToolResult
from hutch.workflow import persistence as wstore
from hutch.workflow import submit as wfsubmit
from tests.test_workflow_engine import make_bot


def _plan() -> dict:
    return {
        "name": "receipt-replay",
        "envelope": {"tools": ["shell"]},
        "budget": {"max_nodes": 8, "max_model_calls": 0},
        "nodes": [{"kind": "tool", "id": "effect", "tool": "shell",
                   "args": {"command": "fixture-effect"}}],
    }


def _owner(store, wf_id: str, attempt_id: str, owner: str, *, node_kind: str = "tool"):
    run = store.claim_run(attempt_id, owner, 60)
    assert run is not None
    run = store.transition_run(run.id, RunStatus.running, fence=run.fence)
    workflow = wstore.workflow_run(store, wf_id)
    assert workflow is not None
    assert wstore.claim_workflow_attempt(store, wf_id, owner_fence=run.fence,
                                         revision_id=workflow["revision_id"], attempt_run_id=run.id)
    wstore.open_node(store, wf_id, owner_run_id=run.id, owner_fence=run.fence,
                     revision_id=workflow["revision_id"], site_id="effect", instance_key="once",
                     kind=node_kind, input_value={"command": "fixture-effect"}, input_hash="a" * 64)
    return run, workflow


def _context(store, config, bot, run, workflow, sink, *, use_context_identity: bool = True):
    policy = PolicyEngine(bot.risk_tier, bot.command_rules)
    gate = ApprovalGate(store, bot, run, policy, lambda _event: None)
    workspace = config.run_dir(bot.name, run.id) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=policy, gate=gate,
                      config=config, workspace=workspace, emit=lambda _event: None)
    if use_context_identity:
        ctx.workflow_action_identity = {
            "workflow_run_id": workflow["id"], "revision_id": workflow["revision_id"],
            "site_id": "effect", "instance_key": "once", "slot": "tool",
        }

    class AppendOnce(Tool):
        name = "shell"

        def effect(self, _args, _ctx):
            return "process"

        def run(self, _args, tool_ctx):
            if refusal := tool_ctx.begin_effect():
                return ToolResult(ok=False, output=refusal)
            with sink.open("a", encoding="utf-8") as stream:
                stream.write("effect\n")
                stream.flush()
            return ToolResult(ok=True, output="finished", data={"receipt": "durable-result"})

    return ctx, {"shell": AppendOnce()}


def test_completed_effect_result_replays_without_a_second_dispatch(store, config, tmp_path):
    bot = make_bot(store, name="effect-replay", tools=["shell"])
    plan = _plan()
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    first, workflow = _owner(store, submission.workflow_run_id, submission.attempt_run_id, "owner-one")
    sink = tmp_path / "append-only-effects.log"
    ctx, tools = _context(store, config, bot, first, workflow, sink)

    first_result = steps.call_tool(first, ctx, tools, "shell", {"command": "fixture-effect"})
    assert first_result.ok and first_result.data == {"receipt": "durable-result"}
    assert sink.read_text(encoding="utf-8") == "effect\n"
    [receipt] = store.list_actions(first.id)
    assert store.get_action(receipt["id"])["status"] == "done"
    assert "result_json" not in store.get_action(receipt["id"])

    # Model a process loss after finish_action committed, before the workflow node settled.
    store.transition_run(first.id, RunStatus.failed, fence=first.fence,
                         exit_reason="interrupted", error="crash after action receipt")
    continuation = wstore.admit_workflow_continuation(store, submission.workflow_run_id)
    assert continuation is not None
    second, workflow = _owner(store, submission.workflow_run_id, continuation.id, "owner-two")
    ctx, tools = _context(store, config, bot, second, workflow, sink)
    replay = steps.call_tool(second, ctx, tools, "shell", {"command": "fixture-effect"})

    assert replay.ok is True
    assert replay.output == "finished"
    assert replay.data == {"receipt": "durable-result"}
    assert sink.read_text(encoding="utf-8") == "effect\n"
    assert len(store.list_actions(unresolved=False)) == 1
    with pytest.raises(action_receipts.ActionConflict, match="changed operation semantics"):
        store.begin_action(second.id, "shell", "changed-input", "process", fence=second.fence,
                           arguments={"command": "different-effect"},
                           workflow_identity=ctx.workflow_action_identity)
    with pytest.raises(action_receipts.ActionConflict, match="changed operation semantics"):
        store.begin_action(second.id, "shell", "changed-scope", "process", fence=second.fence,
                           arguments={"command": "fixture-effect"},
                           scope={"workspace": str(config.run_dir(bot.name, second.id) / "workspace"),
                                  "model": "different/model", "browser_profile": None},
                           workflow_identity=ctx.workflow_action_identity)
    assert sink.read_text(encoding="utf-8") == "effect\n"


def test_uncertain_effect_requires_reconciliation_before_retry(store, config):
    bot = make_bot(store, name="effect-uncertain", tools=["shell"])
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=_plan())
    first, workflow = _owner(store, submission.workflow_run_id, submission.attempt_run_id, "owner-one")
    identity = {"workflow_run_id": workflow["id"], "revision_id": workflow["revision_id"],
                "site_id": "effect", "instance_key": "once", "slot": "tool"}
    action_id = store.begin_action(first.id, "shell", "first", "process", fence=first.fence,
                                   arguments={"command": "fixture-effect"}, workflow_identity=identity)
    store.transition_run(first.id, RunStatus.failed, fence=first.fence,
                         exit_reason="interrupted", error="effect may have happened")
    assert store.get_run(first.id).status is RunStatus.outcome_unknown

    continuation = wstore.admit_workflow_continuation(store, submission.workflow_run_id)
    assert continuation is not None
    second, _workflow = _owner(store, submission.workflow_run_id, continuation.id, "owner-two")
    with pytest.raises(action_receipts.ActionUnresolved, match="reconcile it before retrying"):
        store.begin_action(second.id, "shell", "retry", "process", fence=second.fence,
                           arguments={"command": "fixture-effect"}, workflow_identity=identity)

    recorded, created = store.reconcile_action(
        action_id, intent_hash=store.get_action(action_id)["intent_hash"], outcome="not_applied",
        evidence="The independent effect sink has no matching entry", by="operator",
        idem_key="effect-reconciliation", request_hash="not-applied")
    assert created and recorded["reconciliation"]["outcome"] == "not_applied"

    retried = store.begin_action(second.id, "shell", "retry-after-reconcile", "process",
                                 fence=second.fence, arguments={"command": "fixture-effect"},
                                 workflow_identity=identity)
    store.finish_action(retried, "done", hashlib.sha256(b"result").hexdigest()[:16],
                        expected_fence=second.fence,
                        result={"ok": True, "output": "finished", "data": {"receipt": "new"}})
    assert store.get_action(retried)["status"] == "done"


def test_model_step_effect_identity_is_bound_to_the_parked_parent_generation(store, config, tmp_path):
    bot = make_bot(store, name="step-effect-identity", tools=["shell"])
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=_plan())
    parent, workflow = _owner(store, submission.workflow_run_id, submission.attempt_run_id,
                              "owner-parent", node_kind="step")
    from hutch.models import Run, Task

    child = Run(bot_id=bot.id, prompt="effect step")
    child.workflow_step = {
        "workflow_run_id": workflow["id"], "revision_id": workflow["revision_id"],
        "parent_fence": parent.fence, "site_id": "effect", "instance_key": "once",
        "role": "worker", "tools": ["shell"], "skills": [], "model": bot.model,
        "max_steps": 1, "timeout_seconds": 30, "instruction_hash": "b" * 64,
    }
    child, inserted = wstore.submit_step_run(
        store, workflow_run_id=workflow["id"], site_id="effect", instance_key="once",
        run=child, task=Task(bot_id=bot.id, kind="step", prompt="effect step"),
        parent_run_id=parent.id, parent_fence=parent.fence,
        idem_key="effect-step", request_hash="step-input")
    assert inserted
    assert wstore.update_workflow_run(
        store, workflow["id"], attempt_run_id=parent.id, owner_fence=parent.fence,
        revision_id=workflow["revision_id"], status="waiting", reason="waiting for child")
    store.transition_run(parent.id, RunStatus.waiting_workflow, fence=parent.fence)
    child = store.claim_run(child.id, "owner-child", 60)
    assert child is not None
    child = store.transition_run(child.id, RunStatus.running, fence=child.fence)
    ctx, tools = _context(store, config, bot, child, workflow, tmp_path / "step-effects.log",
                          use_context_identity=False)

    result = steps.call_tool(child, ctx, tools, "shell", {"command": "fixture-effect"})
    assert result.ok and result.data["receipt"] == "durable-result"
    assert (tmp_path / "step-effects.log").read_text(encoding="utf-8") == "effect\n"
    [action] = store.list_actions(child.id)
    persisted = store.get_action(action["id"])
    assert persisted["intent"]["workflow_identity"] == {
        "workflow_run_id": workflow["id"], "revision_id": workflow["revision_id"],
        "site_id": "effect", "instance_key": "once", "slot": "turn:0:call:0:shell",
    }
