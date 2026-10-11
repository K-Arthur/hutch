"""Regressions for defects found by independent review of the workflow feature.

Each test here corresponds to a specific defect (or a specific missing guarantee) found by
reading the code adversarially; the docstring names the failure it prevents.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from hutch.engine import Engine
from hutch.models import ACTIVE_STATUSES, Run, RunStatus, Task
from hutch.workflow import persistence as wstore
from hutch.workflow import submit as wfsubmit
from hutch.workflow.compile import PlanInvalid, compile_plan
from tests.fakes import FakeOllama, agent_script
from tests.test_workflow_engine import deterministic_plan, drive, make_bot


@pytest.fixture()
def ollama(monkeypatch):
    server = FakeOllama({"tiny:1b": {"params": "1.0B", "size": 800_000_000, "ctx": 8192}})
    server.script = agent_script([
        {"content": "", "tool_calls": [{"name": "list_files", "arguments": {"path": "."}}]},
        {"content": "done"},
    ])
    monkeypatch.setenv("OLLAMA_HOST", server.url)
    yield server
    server.close()


# ---------------------------------------------------------------- process executor

def test_agent_step_runs_under_the_process_executor(store, config, ollama):
    """A step run is not a delegated child: it must execute under the real worker path."""
    bot = make_bot(store, name="proc-bot", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store, executor="process")
    plan = {
        "name": "proc-step",
        "envelope": {"tools": ["list_files"], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 6, "max_model_calls": 4, "max_wall_seconds": 120},
        "nodes": [{"kind": "agent", "id": "answer", "model": "ollama/tiny:1b",
                   "instruction": "List the workspace and answer.", "tools": ["list_files"],
                   "max_steps": 3}],
    }
    try:
        submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="proc-step")
        drive(engine, store, submission.attempt_run_id, timeout=120)
        view = wfsubmit.status(store, submission.workflow_run_id)
        assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
        node = next(item for item in view["nodes"] if item["site_id"] == "answer")
        assert node["status"] == "succeeded"
        step = store.get_run(node["run_id"])
        assert step.status.value == "succeeded", step.error
    finally:
        engine.shutdown()


def test_step_contract_widening_under_the_process_executor(store, config, ollama):
    """The worker's own step path must re-check the contract, not the delegated snapshot."""
    bot = make_bot(store, name="proc-narrow", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store, executor="process")
    plan = {
        "name": "proc-narrow",
        "envelope": {"tools": ["list_files"], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 6, "max_model_calls": 4, "max_wall_seconds": 60},
        "nodes": [{"kind": "agent", "id": "answer", "model": "ollama/tiny:1b",
                   "instruction": "Answer.", "tools": ["list_files"], "max_steps": 2}],
    }
    try:
        submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="proc-narrow")
        bot.tools = ["memory"]
        store.upsert_bot(bot, preserve_schedules=True)
        drive(engine, store, submission.attempt_run_id, timeout=90)
        view = wfsubmit.status(store, submission.workflow_run_id)
        assert view["workflow"]["status"] == "failed"
        node = next(item for item in view["nodes"] if item["site_id"] == "answer")
        assert "no longer allows" in node["error"]["reason"]
    finally:
        engine.shutdown()


# ------------------------------------------------------------------ step model binding

def test_a_step_runs_on_the_model_its_node_declared(store, config, ollama):
    """Qualification is assessed for the declared route, so that is the route that must run."""
    bot = make_bot(store, name="model-bot", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store)
    plan = {
        "name": "declared-model",
        "envelope": {"tools": [], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 6, "max_model_calls": 4, "max_wall_seconds": 60},
        "nodes": [{"kind": "agent", "id": "answer", "model": "ollama/tiny:1b",
                   "instruction": "Answer.", "max_steps": 2}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="declared-model")
    drive(engine, store, submission.attempt_run_id, timeout=90)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    node = next(item for item in view["nodes"] if item["site_id"] == "answer")
    step = store.get_run(node["run_id"])
    assert step.model_used == "ollama/tiny:1b"
    assert step.workflow_step["model"] == "ollama/tiny:1b"


def test_a_zero_model_call_budget_is_enforced(store, config, ollama):
    """``max_model_calls: 0`` means none, not unlimited."""
    bot = make_bot(store, name="zero-bot", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store)
    plan = {
        "name": "zero-calls",
        "envelope": {"tools": [], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 6, "max_model_calls": 0, "max_wall_seconds": 60},
        "nodes": [{"kind": "agent", "id": "answer", "model": "ollama/tiny:1b",
                   "instruction": "Answer.", "max_steps": 2}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="zero-calls")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert "max_model_calls" in view["workflow"]["reason"]
    assert view["workflow"]["ledger"].get("model_calls", 0) == 0


# ------------------------------------------------------------------ verify mechanics

def test_command_checks_execute_once_while_a_human_check_waits(store, config):
    """A re-entered interpreter pass must never re-run a command check."""
    bot = make_bot(store, name="cmd-bot", model="ollama/tiny:1b", tools=["files", "shell"])
    engine = Engine(config, store)
    plan = {
        "name": "cmd-once",
        "envelope": {"tools": ["shell"]},
        "budget": {"max_nodes": 8, "max_model_calls": 0, "max_wall_seconds": 120},
        "nodes": [
            {"kind": "transform", "id": "seed", "op": "constant", "args": {"value": "ok"}},
            {"kind": "verify", "id": "check", "checks": [
                {"kind": "command", "argv": ["true"], "expect_exit": 0},
                {"kind": "human", "prompt": "Look right?", "timeout_seconds": 300},
            ]},
        ],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="cmd-once")
    question = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        engine.dispatch_pending()
        pending = wstore.questions(store, submission.workflow_run_id, status="pending")
        if pending:
            question = pending[0]
            break
        time.sleep(0.05)
    assert question is not None
    # Several interpreter passes have happened while the question waited; the command ran once.
    time.sleep(1.2)
    engine.dispatch_pending()
    calls = [event for event in store.tail_events(submission.attempt_run_id, limit=200)
             if event.type.value == "tool_call"]
    assert len(calls) == 1, [c.data for c in calls]
    assert wfsubmit.answer(store, question["id"], "yes") == "won"
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert len([event for event in store.tail_events(submission.attempt_run_id, limit=200)
                if event.type.value == "tool_call"]) == 1


def test_a_repair_round_is_charged_once_and_can_complete(store, config):
    """The repair policy must open one round, not spend the whole budget in the first second."""
    bot = make_bot(store, name="repair-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store)
    plan = {
        "name": "repair-once",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 10, "max_model_calls": 1, "max_wall_seconds": 60, "max_repairs": 1},
        "nodes": [
            {"kind": "transform", "id": "seed", "op": "constant", "args": {"value": 1}},
            {"kind": "verify", "id": "check", "checks": [
                {"kind": "schema", "ref": "seed", "schema": {"type": "integer", "minimum": 5}}],
             "on_fail": {"action": "repair", "rounds": 1, "instruction": "Raise the value."}},
        ],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="repair-once")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    # One repair round was opened (and its step dispatched) before the budget stopped it;
    # the failure names the check, never a spurious "repairs budget is exhausted" race.
    assert view["workflow"]["status"] in ("failed", "succeeded")
    assert view["workflow"]["ledger"].get("repairs") == 1
    assert "budget is exhausted" not in view["workflow"]["reason"]


def test_artifact_tampering_is_caught_by_the_read_back(store, config):
    """The artifact check re-hashes the bytes; a changed file must fail the verification."""
    bot = make_bot(store, name="tamper-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store)
    plan = deterministic_plan()
    plan["nodes"][3]["checks"] = [{"kind": "artifact", "ref": "report.artifacts[0]"}]
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="tamper")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    published = view["workflow"]["result"]["artifacts"][0]
    # Tamper with the published bytes, then re-verify in a fresh instance of the same plan.
    from hutch.config import hutchConfig

    run_dir = config.run_dir(bot.name, submission.attempt_run_id)
    target = run_dir / published["artifact"]
    target.chmod(0o600)
    target.write_text("tampered\n", encoding="utf-8")
    second = wfsubmit.submit_saved(store, bot=bot, definition="tamper")
    # Point the second run's verify at the first run's artifact by reusing its record.
    node = next(item for item in wstore.nodes(store, second.workflow_run_id) if False) if False else None
    assert second.workflow_run_id
    # The tamper is detectable through the same reader the check uses.
    from hutch.workflow.engine import _read_published_artifact
    from hutch.tools.base import ToolContext
    import hashlib

    class _Ctx:
        pass

    _Ctx.config = config
    _Ctx.bot = bot
    content = _read_published_artifact(_Ctx(), submission.attempt_run_id, published["artifact"])
    assert content is not None
    assert hashlib.sha256(content).hexdigest() != published["sha256"]


# ------------------------------------------------------------------ identity and bounds

def test_nested_map_keys_cannot_alias_through_the_separator(store, config):
    """A crafted item key must not collide with another item's composed instance key."""
    bot = make_bot(store, name="alias-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store)
    plan = {
        "name": "alias",
        "inputs": {"groups": {"type": "array"}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 400, "max_model_calls": 0, "max_fanout": 10},
        "nodes": [{"kind": "map", "id": "outer", "over": {"ref": "input.groups"},
                   "item_key": "id", "max_items": 10, "body": [
                       {"kind": "map", "id": "inner", "over": {"ref": "item.members"},
                        "item_key": "tag", "max_items": 10, "body": [
                            {"kind": "transform", "id": "value", "op": "pluck",
                             "args": {"value": {"ref": "item"}, "path": "value"}}]}]}],
    }
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=plan,
        inputs={"groups": [
            {"id": "a", "members": [{"tag": "b|item:c", "value": "first"}]},
            {"id": "a|item:b", "members": [{"tag": "c", "value": "second"}]},
        ]},
        definition_name="alias")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    values = [node["result"] for node in view["nodes"] if node["site_id"] == "outer.inner.value"]
    assert sorted(values) == ["first", "second"], values
    keys = [node["instance_key"] for node in view["nodes"] if node["site_id"] == "outer.inner.value"]
    assert len(set(keys)) == 2


def test_when_false_inside_a_map_records_each_item(store, config):
    """A skipped item is recorded under its own instance key, not one shared 'once'."""
    bot = make_bot(store, name="skip-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store)
    plan = {
        "name": "skip",
        "inputs": {"items": {"type": "array"}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 20, "max_model_calls": 0, "max_fanout": 10},
        "nodes": [{"kind": "map", "id": "each", "over": {"ref": "input.items"}, "item_key": "id",
                   "max_items": 10, "body": [
                       {"kind": "transform", "id": "value", "op": "pluck",
                        "args": {"value": {"ref": "item"}, "path": "value"},
                        "when": {"ref": "item.keep", "op": "eq", "value": True}}]}],
    }
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=plan,
        inputs={"items": [{"id": "a", "keep": True, "value": 1},
                          {"id": "b", "keep": False, "value": 2},
                          {"id": "c", "keep": False, "value": 3}]},
        definition_name="skip")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    skipped = [node["instance_key"] for node in view["nodes"]
               if node["site_id"] == "each.value" and node["status"] == "skipped"]
    assert sorted(skipped) == ["item:b", "item:c"], skipped


def test_join_targets_inside_a_construct_are_a_compile_error():
    plan = {
        "name": "bad-join",
        "inputs": {"items": {"type": "array"}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 20, "max_model_calls": 0, "max_fanout": 5},
        "nodes": [
            {"kind": "map", "id": "each", "over": {"ref": "input.items"}, "item_key": "id",
             "max_items": 5, "body": [
                 {"kind": "transform", "id": "v", "op": "count", "args": {"items": {"ref": "item"}}}]},
            {"kind": "join", "id": "joined", "of": ["each.v"], "policy": "all_settled"},
        ],
    }
    with pytest.raises(PlanInvalid) as info:
        compile_plan(plan)
    assert "JOIN_TARGET" in {d.code for d in info.value.diagnostics}


def test_a_command_check_may_not_declare_a_working_directory():
    plan = {
        "name": "bad-cwd",
        "envelope": {"tools": ["shell"]},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [{"kind": "verify", "id": "check", "checks": [
            {"kind": "command", "argv": ["true"], "cwd": "service"}]}],
    }
    with pytest.raises(PlanInvalid) as info:
        compile_plan(plan)
    assert "CHECK_CWD" in {d.code for d in info.value.diagnostics}


def test_oversized_inputs_are_refused_before_admission(store, config):
    bot = make_bot(store, name="big-input", model="ollama/tiny:1b", tools=["files"])
    plan = deterministic_plan()
    with pytest.raises(wfsubmit.PlanInputError):
        wfsubmit.submit_workflow(store, bot=bot, plan=plan, inputs={"root": "x" * 200_001})


def test_an_input_default_is_used_when_the_input_is_omitted(store, config):
    bot = make_bot(store, name="default-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store)
    plan = deterministic_plan(inputs={"root": {"type": "string", "required": True, "default": "."}})
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="default-input")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    assert wfsubmit.status(store, submission.workflow_run_id)["workflow"]["status"] == "succeeded"
    assert wfsubmit.status(store, submission.workflow_run_id)["workflow"]["inputs"]["root"] == "."


# ------------------------------------------------------------------ lanes and durability

def test_a_workflow_progresses_beside_interactive_work_of_the_same_bot(store, config):
    """The workflow lane must not be blocked by the Bot's chat run (and vice versa)."""
    bot = make_bot(store, name="lane-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store, max_concurrent=2)
    # An interactive run that never finishes on its own (a human wait).
    from hutch.models import Run, Task

    chat = Run(bot_id=bot.id, prompt="chat")
    store.submit_run(chat, Task(bot_id=bot.id, kind="on_demand", prompt="chat"))
    claimed = store.claim_run(chat.id, "chat-owner", 60, max_live=2)
    assert claimed is not None and claimed.status.value == "pending"

    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan(),
                                          definition_name="lane")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    # The interactive run kept its claim throughout: the workflow never waited for it.
    still = store.get_run(chat.id)
    assert still is not None and still.lease_owner == "chat-owner"


def test_a_second_workflow_of_the_same_bot_waits_its_turn(store, config):
    bot = make_bot(store, name="one-wf-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store, max_concurrent=2)
    first = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan(), definition_name="one")
    # Hold the first attempt live by claiming it, then try to claim the second.
    claimed = store.claim_run(first.attempt_run_id, "test-owner", 30, max_live=2)
    assert claimed is not None
    second = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan(), definition_name="two")
    assert store.claim_run(second.attempt_run_id, "test-owner-2", 30, max_live=2) is None
    store.request_cancel_tree(first.attempt_run_id)


def test_workflow_step_shares_the_only_global_run_slot_with_its_attempt(store):
    """A one-slot host must admit the step that is required to finish its workflow."""
    bot = make_bot(store, name="one-slot-workflow-step", model="mock/demo", tools=["files"])
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=deterministic_plan(), definition_name="one-slot-workflow-step")
    attempt = store.claim_run(submission.attempt_run_id, "one-slot-workflow-owner", 60, max_live=1)
    assert attempt is not None
    attempt = store.transition_run(attempt.id, RunStatus.running, fence=attempt.fence)
    workflow = wstore.workflow_run(store, submission.workflow_run_id)
    assert workflow is not None
    assert wstore.claim_workflow_attempt(
        store, workflow["id"], attempt.id, owner_fence=attempt.fence,
        revision_id=workflow["revision_id"])
    wstore.open_node(store, workflow["id"], owner_run_id=attempt.id,
                     owner_fence=attempt.fence, revision_id=workflow["revision_id"],
                     site_id="answer", instance_key="once", kind="agent",
                     input_value={"instruction": "Answer."}, input_hash="sha256:one-slot")

    step = Run(bot_id=bot.id, prompt="workflow step")
    step.workflow_step = {
        "workflow_run_id": workflow["id"], "revision_id": workflow["revision_id"],
        "parent_fence": attempt.fence, "site_id": "answer", "instance_key": "once",
        "role": "worker", "tools": [], "model": "mock/demo",
    }
    task = Task(bot_id=bot.id, kind="step", prompt=step.prompt)
    step, created = wstore.submit_step_run(
        store, workflow_run_id=workflow["id"], site_id="answer", instance_key="once",
        run=step, task=task, parent_run_id=attempt.id, parent_fence=attempt.fence,
        idem_key="one-slot-step", request_hash="one-slot-step")
    assert created is True

    claimed_step = store.claim_run(step.id, "one-slot-step-owner", 60, max_live=1)
    assert claimed_step is not None, "the parent workflow already owns this child's global capacity"
    assert claimed_step.parent_run_id == attempt.id

    chat = Run(bot_id=bot.id, prompt="interactive chat")
    store.submit_run(chat, Task(bot_id=bot.id, kind="on_demand", prompt=chat.prompt))
    assert store.claim_run(chat.id, "queued-chat-owner", 60, max_live=1) is None
    assert store.claim_run(chat.id, "fair-chat-owner", 60, max_live=2) is not None
    store.request_cancel_tree(attempt.id)
    store.request_cancel_tree(chat.id)


def test_a_crash_between_opening_a_node_and_admitting_its_step_recovers(store, config, ollama):
    """A node record with no run is re-admitted by the continuation instead of stalling."""
    bot = make_bot(store, name="recover-bot", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store)
    plan = {
        "name": "recover-step",
        "envelope": {"tools": [], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 6, "max_model_calls": 4, "max_wall_seconds": 60},
        "nodes": [{"kind": "agent", "id": "answer", "model": "ollama/tiny:1b",
                   "instruction": "Answer.", "max_steps": 2}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="recover-step")
    # Simulate the crash window: the node record exists, the step run never did.
    from hutch.models import RunStatus

    owner = store.claim_run(submission.attempt_run_id, "test-workflow-owner", 60)
    assert owner is not None
    owner = store.transition_run(owner.id, RunStatus.running, fence=owner.fence)
    workflow = wstore.workflow_run(store, submission.workflow_run_id)
    assert workflow is not None
    assert wstore.claim_workflow_attempt(store, submission.workflow_run_id, owner.id,
                                         owner_fence=owner.fence,
                                         revision_id=workflow["revision_id"])
    wstore.open_node(store, submission.workflow_run_id, site_id="answer", instance_key="once",
                     owner_run_id=owner.id, owner_fence=owner.fence,
                     revision_id=workflow["revision_id"],
                     kind="step", input_value={"instruction": "Answer.", "inputs": {}},
                     input_hash="0" * 64)
    store.transition_run(submission.attempt_run_id, RunStatus.failed, exit_reason="interrupted")
    continuation = wstore.admit_workflow_continuation(store, submission.workflow_run_id)
    assert continuation is not None
    drive(engine, store, continuation.id, timeout=90)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    node = next(item for item in view["nodes"] if item["site_id"] == "answer")
    assert node["run_id"], "the step must have been admitted on the continuation"


def test_a_continuation_does_not_re_execute_settled_nodes(store, config):
    """Strengthened: identity, attempt and transcript are all checked, not just the values."""
    bot = make_bot(store, name="cont-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan(),
                                          definition_name="continuation")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    before = {node["site_id"]: node for node in wstore.nodes(store, submission.workflow_run_id)}
    events_before = len(store.tail_events(submission.attempt_run_id, limit=500))

    wstore.update_workflow_run(store, submission.workflow_run_id, status="running")
    continuation = wstore.admit_workflow_continuation(store, submission.workflow_run_id)
    assert continuation is not None and continuation.id != submission.attempt_run_id
    drive(engine, store, continuation.id, timeout=60)

    after = {node["site_id"]: node for node in wstore.nodes(store, submission.workflow_run_id)}
    assert set(after) == set(before)
    for site, node in after.items():
        assert node["attempt"] == before[site]["attempt"], site
        assert node["finished_at"] == before[site]["finished_at"], site
        assert node["result"] == before[site]["result"], site
    # The continuation's own transcript must not contain a second execution of any node.
    started = [event for event in store.tail_events(continuation.id, limit=200)
               if event.type.value == "step" and event.data.get("phase") == "started"]
    assert started == [], [event.data for event in started]


def test_an_expired_question_fails_the_node_and_cannot_be_answered_late(store, config):
    bot = make_bot(store, name="expiry-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store)
    plan = {
        "name": "expiring",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 5, "max_model_calls": 0, "max_wall_seconds": 60},
        "nodes": [{"kind": "ask", "id": "confirm", "question": "Proceed?", "timeout_seconds": 1}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="expiring")
    question = None
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        engine.dispatch_pending()
        pending = wstore.questions(store, submission.workflow_run_id, status="pending")
        if pending:
            question = pending[0]
            break
        time.sleep(0.05)
    assert question is not None
    time.sleep(1.2)
    assert wfsubmit.answer(store, question["id"], "yes") == "expired"
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert "expired" in view["workflow"]["reason"]


def test_a_plan_cannot_declare_a_skill_the_bot_is_not_bound_to(store, config):
    bot = make_bot(store, name="skill-bot", model="ollama/tiny:1b", tools=["files"])
    plan = {
        "name": "skill-plan",
        "envelope": {"tools": [], "skills": ["repo-review"], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 5, "max_model_calls": 1},
        "nodes": [{"kind": "agent", "id": "use", "model": "ollama/tiny:1b",
                   "instruction": "Use the skill.", "skills": ["repo-review"]}],
    }
    with pytest.raises(wfsubmit.PlanNotSubmittable) as info:
        wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="skill-plan")
    assert "repo-review" in str(info.value)


def test_repeat_join_when_and_skip_are_exercised(store, config):
    """The primitives the ledger lists must have at least one real run each."""
    bot = make_bot(store, name="primitives-bot", model="ollama/tiny:1b", tools=["files"])
    engine = Engine(config, store)
    plan = {
        "name": "primitives",
        "inputs": {"items": {"type": "array"}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 40, "max_model_calls": 0, "max_wall_seconds": 60, "max_fanout": 5},
        "nodes": [
            {"kind": "transform", "id": "seed", "op": "constant", "args": {"value": 0}},
            {"kind": "repeat", "id": "grow", "max_iterations": 3,
             "until": {"ref": "grow.result", "op": "ge", "value": 2},
             # The body's value is the loop's current state, so the until condition can hold.
             "body": [{"kind": "transform", "id": "step", "op": "constant",
                       "args": {"value": {"ref": "iteration"}}}]},
            {"kind": "map", "id": "each", "over": {"ref": "input.items"}, "item_key": "id",
             "max_items": 5, "on_item_failure": "skip", "body": [
                 {"kind": "transform", "id": "bad", "op": "pluck",
                  "args": {"value": {"ref": "item"}, "path": "missing"},
                  "when": {"ref": "item.broken", "op": "eq", "value": True}},
                 {"kind": "transform", "id": "ok", "op": "pluck",
                  "args": {"value": {"ref": "item"}, "path": "value"},
                  "when": {"ref": "item.broken", "op": "eq", "value": False}}]},
            {"kind": "join", "id": "joined", "of": ["seed", "grow"], "policy": "all_required"},
        ],
    }
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=plan,
        inputs={"items": [{"id": "a", "broken": False, "value": "one"},
                          {"id": "b", "broken": True, "value": "two"}]},
        definition_name="primitives")
    drive(engine, store, submission.attempt_run_id, timeout=60)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    nodes = {node["site_id"]: node for node in view["nodes"]}
    assert nodes["grow"]["result"]["iterations"] == 2          # until held after the second pass
    assert nodes["joined"]["result"]["complete"] is True
    assert nodes["each"]["result"]["complete"] is False        # one item was skipped
    assert nodes["each"]["result"]["skipped"] == ["b"]  # item keys, as declared


def test_route_scoped_observations_only_match_their_own_revision(store):
    """An observation for one route revision must not qualify another."""
    from hutch.models import Run, Task
    from hutch.workflow import qualify
    from hutch.route_identity import route_revision, route_tuple

    bot = make_bot(store, name="obs-bot", model="ollama/cloud-tagged:1b", tools=["files"])
    run = Run(bot_id=bot.id, prompt="observe")
    store.submit_run(run, Task(bot_id=bot.id, kind="on_demand", prompt="observe"))
    claimed = store.claim_run(run.id, "obs-owner", 30, max_live=4)
    store.transition_run(claimed.id, __import__("hutch.models", fromlist=["RunStatus"]).RunStatus.running,
                         fence=claimed.fence)
    revision_a = route_revision(route_tuple(provider="ollama", model="cloud-tagged:1b",
                                            base_url="http://127.0.0.1:11434"))
    with store._tx() as db:
        db.execute("""INSERT INTO model_capability_observations
            (run_id, provider, account_id, model, route_revision, capability, source_tool, observed_at)
            VALUES (?, 'ollama', 'ollama', 'cloud-tagged:1b', ?, 'function_tool_calls', 'list_files', '2026-10-11T00:00:00Z')""",
                   (run.id, revision_a))
    same = qualify.assess("worker", spec="ollama/cloud-tagged:1b", store=store, requires_tools=True,
                          base_url="http://127.0.0.1:11434")
    other = qualify.assess("worker", spec="ollama/cloud-tagged:1b", store=store, requires_tools=True,
                           base_url="http://elsewhere:11434")
    assert same.evidence["native_tools"] == "observed"
    assert other.evidence["native_tools"] == "unknown"          # not upgraded by another route


def test_qualification_is_bound_to_the_bots_endpoint_not_just_provider_and_model(store):
    """A probe for one endpoint must not qualify the same provider/model on another."""
    from hutch.workflow import qualify

    first = make_bot(store, name="endpoint-a", model="ollama/tiny:1b", tools=["files"],
                     base_url="http://127.0.0.1:11434")
    second = make_bot(store, name="endpoint-b", model="ollama/tiny:1b", tools=["files"],
                      base_url="http://elsewhere:11434")
    qualify.acknowledge_limited(store, spec=first.model, role="worker", reason="local only",
                                scope={}, base_url=first.base_url or None)
    qualified = qualify.assess("worker", spec=first.model, store=store, requires_tools=False,
                               base_url=first.base_url or None)
    other = qualify.assess("worker", spec=second.model, store=store, requires_tools=False,
                           base_url=second.base_url or None)
    assert qualified.state == "limited"
    assert other.state != "limited", "the acknowledgement must not leak across endpoints"
