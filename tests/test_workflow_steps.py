"""Workflow model steps run for real against a local HTTP model server.

These tests exercise the part the deterministic tests cannot: an ``agent`` node becomes an
ordinary child run, executed by the real builtin runtime against a real local HTTP server
(Ollama's wire protocol), with its own workspace, tool seam, output contract and settlement
back into the workflow's node record. The server's replies are scripted - the *model* is
simulated, everything Hutch does around it is not.
"""
from __future__ import annotations

import time

import pytest

from hutch.engine import Engine
from hutch.models import ACTIVE_STATUSES
from hutch.workflow import persistence as wstore
from hutch.workflow import submit as wfsubmit
from tests.fakes import FakeOllama, agent_script
from tests.test_workflow_engine import drive, make_bot


@pytest.fixture()
def ollama(monkeypatch):
    server = FakeOllama({"tiny:1b": {"params": "1.0B", "size": 800_000_000, "ctx": 8192}})
    server.script = agent_script([
        {"content": "", "tool_calls": [{"name": "list_files", "arguments": {"path": "."}}]},
        {"content": "The workspace listing is what it is; here is the answer."},
    ])
    monkeypatch.setenv("OLLAMA_HOST", server.url)
    yield server
    server.close()


def agent_plan(**overrides) -> dict:
    plan = {
        "name": "agent-step",
        "inputs": {"question": {"type": "string", "default": "What is the plan?"}},
        "envelope": {"tools": ["list_files"], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 10, "max_model_calls": 2, "max_wall_seconds": 120},
        "nodes": [
            {"kind": "agent", "id": "answer", "role": "worker", "model": "ollama/tiny:1b",
             "instruction": "Answer this: {{question}}",
             "inputs": {"question": {"ref": "input.question"}},
             "tools": ["list_files"], "max_steps": 4},
            {"kind": "publish", "id": "deliver", "artifacts": [
                {"name": "answer", "ref": "answer.text", "primary": True}]},
        ],
    }
    plan.update(overrides)
    return plan


def test_agent_node_releases_its_slot_while_its_child_step_runs(store, config, ollama):
    bot = make_bot(store, name="step-bot", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store, max_concurrent=1)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=agent_plan(),
                                          definition_name="agent-step")
    drive(engine, store, submission.attempt_run_id, timeout=90)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    node = next(item for item in view["nodes"] if item["site_id"] == "answer")
    assert node["status"] == "succeeded"
    step_run_id = node["run_id"]
    assert step_run_id, "the node must record the step run that produced it"

    # The step is an ordinary Hutch run: its own transcript, its own tool calls.
    step = store.get_run(step_run_id)
    assert step is not None and step.status.value == "succeeded"
    assert step.parent_run_id == submission.attempt_run_id
    assert store.run_kind(step_run_id) == "step"
    kinds = [event.type.value for event in store.tail_events(step_run_id, limit=50)]
    assert "message" in kinds
    assert "tool_call" in kinds, "the step's own tool use must be in the step's transcript"
    # The step ran in its own workspace, not the Bot's shared one.
    assert step.workspace and step.workspace != store.get_run(submission.attempt_run_id).workspace
    # The frozen contract is what the step actually got.
    assert step.workflow_step["tools"] == ["list_files"]
    assert step.workflow_step["max_steps"] == 4

    # The published artifact carries the step's answer.
    published = view["workflow"]["result"]["artifacts"]
    assert published and published[0]["name"] == "answer"
    assert published[0]["bytes"] > 0
    # Every provider request (the tool-call turn and the post-result turn) is charged
    # to the root workflow, rather than counting this worker node as one call.
    assert view["workflow"]["ledger"].get("model_calls", 0) == 2


def test_stopping_workflow_cancels_active_step_and_drains_its_process(store, config, ollama):
    """Workflow Stop reaches a live model child and waits for verified process cleanup."""
    bot = make_bot(store, name="stop-step-bot", model="ollama/tiny:1b", tools=[], selfcheck=False)
    engine = Engine(config, store, executor="process")
    ollama.script = agent_script([{"content": "This response is deliberately delayed."}])
    ollama.stall_once = 2.0
    plan = {
        "name": "stop-active-step",
        "envelope": {"tools": [], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 4, "max_model_calls": 2, "max_wall_seconds": 60},
        "nodes": [{"kind": "agent", "id": "answer", "role": "worker",
                   "model": "ollama/tiny:1b", "instruction": "Answer briefly.",
                   "tools": [], "max_steps": 2}],
    }
    try:
        submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan,
                                              definition_name="stop-active-step")
        child_id = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            engine.tick()
            node = next((item for item in wstore.nodes(store, submission.workflow_run_id)
                         if item["site_id"] == "answer"), None)
            if node and node.get("run_id"):
                child = store.get_run(str(node["run_id"]))
                if (child is not None and child.status.value == "running"
                        and ollama.of("/api/chat")):
                    child_id = child.id
                    break
            time.sleep(0.05)

        assert child_id is not None, "the scripted model step did not enter its live request"
        child = store.get_run(child_id)
        assert child is not None and child.status.value == "running"
        stopped = wfsubmit.stop_workflow(store, submission.workflow_run_id,
                                         expected_revision_id=submission.revision_id)
        assert stopped["stop_requested"] is True
        assert store.get_run(child_id).cancel_requested is True

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            engine.tick()
            view = wfsubmit.status(store, submission.workflow_run_id)
            child = store.get_run(child_id)
            attempt = store.get_run(submission.attempt_run_id)
            if (view["workflow"]["status"] == "stopped" and child is not None
                    and child.status.value == "stopped" and attempt is not None
                    and attempt.status.value == "stopped"
                    and not store.live_procs(child_id)
                    and not store.live_procs(submission.attempt_run_id)):
                break
            time.sleep(0.05)

        view = wfsubmit.status(store, submission.workflow_run_id)
        child = store.get_run(child_id)
        attempt = store.get_run(submission.attempt_run_id)
        assert view["workflow"]["status"] == "stopped", view["workflow"]
        assert child is not None and child.status.value == "stopped", child
        assert attempt is not None and attempt.status.value == "stopped", attempt
        assert not store.live_procs(child_id)
        assert not store.live_procs(submission.attempt_run_id)
        assert all(question["status"] != "pending"
                   for question in wstore.questions(store, submission.workflow_run_id))
    finally:
        engine.shutdown()


def test_agent_step_output_contract_is_enforced_and_fails_honestly(store, config, ollama):
    """A reply that does not satisfy the node's contract fails that node with the reason."""
    bot = make_bot(store, name="contract-bot", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store)
    plan = agent_plan()
    plan["nodes"][0]["output_schema"] = {
        "type": "object", "required": ["summary", "confidence"],
        "properties": {"summary": {"type": "string"}, "confidence": {"type": "number"}},
        "additionalProperties": False}
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan,
                                          definition_name="agent-contract")
    drive(engine, store, submission.attempt_run_id, timeout=90)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    node = next(item for item in view["nodes"] if item["site_id"] == "answer")
    assert node["status"] == "failed"
    assert "output contract" in node["error"]["reason"]
    # The step run itself completed; it was the *contract* that failed, and that is recorded
    # separately so a person can see the difference between "the model answered" and
    # "the answer was acceptable".
    assert store.get_run(node["run_id"]).status.value == "succeeded"


def test_a_text_only_step_needs_no_tools_and_still_records_its_model(store, config, ollama):
    bot = make_bot(store, name="text-bot", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store)
    plan = agent_plan()
    plan["nodes"][0]["tools"] = []
    plan["envelope"]["tools"] = []
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="agent-text")
    drive(engine, store, submission.attempt_run_id, timeout=90)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    node = next(item for item in view["nodes"] if item["site_id"] == "answer")
    assert node["result"]["text"]
    assert store.get_run(node["run_id"]).model_used


def test_step_contract_is_re_checked_when_the_step_starts(store, config, ollama):
    """A Bot edited after admission cannot widen an admitted step."""
    bot = make_bot(store, name="narrow-bot", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=agent_plan(),
                                          definition_name="agent-narrow")
    # Remove the tool the admitted step needs, then drive: the step must fail closed.
    bot.tools = ["memory"]
    store.upsert_bot(bot, preserve_schedules=True)
    drive(engine, store, submission.attempt_run_id, timeout=90)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    node = next(item for item in view["nodes"] if item["site_id"] == "answer")
    assert node["status"] == "failed"
    assert "no longer allows" in node["error"]["reason"]
