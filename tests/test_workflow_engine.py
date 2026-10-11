"""End-to-end workflow execution contracts.

These run the real engine: submission, admission, claim, the owned worker, the
deterministic interpreter, the canonical tool seam, artifact publication and the
verification vocabulary. The model side uses the harness's deterministic scenario runtime
(never product code), so what is proven here is the *engine*, not model quality.
"""
from __future__ import annotations

import time

import pytest

from hutch.engine import Engine
from hutch.models import ACTIVE_STATUSES, Bot, Task
from hutch.store import Store
from hutch.workflow import persistence as wstore
from hutch.workflow import submit as wfsubmit


def make_bot(store: Store, **overrides) -> Bot:
    fields = {"name": "wf-bot", "model": "mock/demo", "tools": ["files"],
              "instructions": "You are a careful worker."}
    fields.update(overrides)
    bot = Bot(**fields)
    store.upsert_bot(bot)
    return store.get_bot(bot.id) or bot


def drive(engine: Engine, store: Store, attempt_run_id: str, timeout: float = 30.0) -> None:
    """The same watch loop the CLI uses: dispatch while work is outstanding."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        engine.dispatch_pending()
        run = store.get_run(attempt_run_id)
        if run is None or run.status not in ACTIVE_STATUSES:
            return
        time.sleep(0.05)
    raise AssertionError("the workflow did not settle in time")


def deterministic_plan(**overrides) -> dict:
    plan = {
        "name": "collect-and-report",
        "inputs": {"root": {"type": "string", "default": "."}},
        "envelope": {"tools": ["list_files", "read_file"]},
        "budget": {"max_nodes": 30, "max_model_calls": 0, "max_fanout": 5},
        "nodes": [
            {"kind": "tool", "id": "scan", "tool": "list_files", "args": {"path": {"ref": "input.root"}}},
            {"kind": "transform", "id": "count", "op": "pluck",
             "args": {"value": {"ref": "scan.data"}, "path": "count"}},
            {"kind": "publish", "id": "report", "artifacts": [
                {"name": "summary", "ref": "count", "primary": True}]},
            {"kind": "verify", "id": "check", "checks": [
                {"kind": "schema", "ref": "count", "schema": {"type": "integer", "minimum": 0}},
                {"kind": "artifact", "ref": "report.artifacts[0]"}]},
        ],
    }
    plan.update(overrides)
    return plan


def test_deterministic_workflow_runs_publishes_and_verifies(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    drive(engine, store, submission.attempt_run_id)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view
    attempt = store.get_run(submission.attempt_run_id)
    assert attempt.status.value == "succeeded"
    assert attempt.kind == "workflow"
    states = {node["site_id"]: node["status"] for node in view["nodes"]}
    assert states == {"scan": "succeeded", "count": "succeeded", "report": "succeeded",
                      "check": "succeeded"}
    published = view["workflow"]["result"]["artifacts"]
    assert published and published[0]["name"] == "summary"
    assert len(published[0]["sha256"]) == 64
    # The verification node recorded independent evidence, not a model claim.
    check = next(node for node in view["nodes"] if node["site_id"] == "check")
    assert check["result"]["verified"] is True
    assert {item["kind"] for item in check["result"]["checks"]} == {"schema", "artifact"}
    # The published artifact is reachable through the canonical artifact API.
    records = store.artifact_records(submission.attempt_run_id)
    assert any(kind == "tool_output" for _event, kind in records)


def test_reused_results_are_not_re_executed_on_continuation(store, config):
    """A crashed attempt continues: settled nodes are read back, never run again."""
    bot = make_bot(store)
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    drive(engine, store, submission.attempt_run_id)
    first = wstore.nodes(store, submission.workflow_run_id)
    before = {node["site_id"]: node["result"] for node in first}

    # Force a continuation of the same instance: a fresh attempt re-walks the plan.
    wstore.update_workflow_run(store, submission.workflow_run_id, status="running")
    continuation = wstore.admit_workflow_continuation(store, submission.workflow_run_id)
    assert continuation is not None and continuation.id != submission.attempt_run_id
    drive(engine, store, continuation.id)

    after = wstore.nodes(store, submission.workflow_run_id)
    assert {node["site_id"]: node["result"] for node in after} == before
    assert store.get_run(continuation.id).status.value == "succeeded"


def test_recovery_query_uses_cutoff_before_terminal_status_values(store):
    """The first terminal state must not be consumed as the timestamp cutoff."""
    from hutch.store import _TERMINAL_VALUES

    bot = make_bot(store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    with store._tx() as db:
        db.execute("UPDATE workflow_runs SET status='running', updated_at='2000-01-01T00:00:00+00:00' "
                   "WHERE id=?", (submission.workflow_run_id,))
        db.execute("UPDATE runs SET status=?, cancel_requested=0 WHERE id=?",
                   (_TERMINAL_VALUES[0], submission.attempt_run_id))

    rows = wstore.workflow_runs_needing_attempt(store, quiet_seconds=0)
    assert submission.workflow_run_id in {row["id"] for row in rows}


def test_stale_workflow_attempt_cannot_replace_the_current_owner(store):
    bot = make_bot(store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    old_attempt = submission.attempt_run_id
    assert wstore.claim_workflow_attempt(store, submission.workflow_run_id, old_attempt)

    with store._tx() as db:
        db.execute("UPDATE workflow_runs SET attempt_run_id='replacement-attempt' WHERE id=?",
                   (submission.workflow_run_id,))

    assert not wstore.claim_workflow_attempt(store, submission.workflow_run_id, old_attempt)
    assert wstore.workflow_run(store, submission.workflow_run_id)["attempt_run_id"] == "replacement-attempt"


def test_failed_node_fails_the_workflow_with_a_reason(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = deterministic_plan()
    plan["nodes"][1] = {"kind": "transform", "id": "count", "op": "sum",
                        "args": {"items": {"ref": "scan.data.files"}}}
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    drive(engine, store, submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert "count" in view["workflow"]["reason"]
    assert store.get_run(submission.attempt_run_id).status.value == "failed"


def test_verify_failure_stops_and_records_the_evidence(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = deterministic_plan()
    plan["nodes"][3]["checks"] = [{"kind": "schema", "ref": "count",
                                   "schema": {"type": "integer", "minimum": 1_000_000}}]
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    drive(engine, store, submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    check = next(node for node in view["nodes"] if node["site_id"] == "check")
    assert check["status"] == "failed"
    assert ">= 1000000" in check["error"]["reason"]


def test_verify_can_continue_unverified_when_the_plan_says_so(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = deterministic_plan()
    plan["nodes"][3]["checks"] = [{"kind": "schema", "ref": "count",
                                   "schema": {"type": "integer", "minimum": 1_000_000}}]
    plan["nodes"][3]["on_fail"] = {"action": "continue"}
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    drive(engine, store, submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded"
    check = next(node for node in view["nodes"] if node["site_id"] == "check")
    assert check["result"]["verified"] is False
    assert "unverified" in check["result"]["note"]


def test_submission_refuses_tools_the_bot_does_not_allow(store, config):
    bot = make_bot(store, tools=["files"])
    plan = deterministic_plan()
    plan["envelope"]["tools"] = ["list_files", "shell"]
    with pytest.raises(wfsubmit.PlanNotSubmittable) as info:
        wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    assert "shell" in str(info.value)


def test_submission_refuses_a_model_role_that_is_not_qualified(store, config):
    bot = make_bot(store, tools=["files"])
    plan = {
        "name": "needs-an-author",
        "envelope": {"tools": [], "models": ["ollama/qwen3:4b"]},
        "budget": {"max_nodes": 5, "max_model_calls": 1},
        "nodes": [{"kind": "agent", "id": "think", "instruction": "Think about it",
                   "model": "ollama/qwen3:4b"}],
    }
    # A worker role without tools on a documented local route is allowed...
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="needs-an-author")
    assert submission.verdicts and submission.verdicts[0]["allowed"] is True

    # ...but an authoring role never is without probed evidence.
    with pytest.raises(wfsubmit.PlanNotSubmittable) as info:
        wfsubmit.submit_workflow(store, bot=bot, plan=plan, source="model",
                                 planning_model="ollama/qwen3:4b")
    assert "qualified to author" in str(info.value)


def test_local_model_only_plans_refuse_hosted_routes(store, config):
    bot = make_bot(store, model="anthropic/claude-sonnet-4-5", tools=["files"])
    plan = {
        "name": "local-only",
        "envelope": {"tools": [], "models": [], "network": "local_model_only"},
        "budget": {"max_nodes": 5, "max_model_calls": 1},
        "nodes": [{"kind": "agent", "id": "think", "instruction": "Think"}],
    }
    with pytest.raises(wfsubmit.PlanNotSubmittable) as info:
        wfsubmit.submit_workflow(store, bot=bot, plan=plan, definition_name="local-only")
    assert "not local" in str(info.value)


def test_inputs_are_validated_without_coercion(store, config):
    bot = make_bot(store)
    plan = deterministic_plan(inputs={"root": {"type": "string", "required": True}})
    with pytest.raises(wfsubmit.PlanInputError):
        wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    with pytest.raises(wfsubmit.PlanInputError):
        wfsubmit.submit_workflow(store, bot=bot, plan=plan, inputs={"root": 5})
    with pytest.raises(wfsubmit.PlanInputError):
        wfsubmit.submit_workflow(store, bot=bot, plan=plan, inputs={"root": ".", "extra": 1})


def test_stop_request_stops_the_instance_and_prevents_continuation(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    wfsubmit.stop_workflow(store, submission.workflow_run_id)
    engine.continue_workflow_runs()
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["stop_requested"] is True
    assert wstore.admit_workflow_continuation(store, submission.workflow_run_id) is None


def test_a_cancelled_attempt_is_not_continued(store, config):
    """Ordinary stop of the attempt run must not resurrect the instance as a new attempt."""
    bot = make_bot(store)
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    store.request_cancel_tree(submission.attempt_run_id)
    assert wstore.admit_workflow_continuation(store, submission.workflow_run_id) is None
    engine.continue_workflow_runs()
    assert wfsubmit.status(store, submission.workflow_run_id)["workflow"]["status"] == "stopped"


def test_branch_and_map_execute_with_stable_item_identity(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = {
        "name": "fan-out-branch",
        "inputs": {"files": {"type": "array"}},
        "envelope": {"tools": [], "max_parallel_steps": 2},
        "budget": {"max_nodes": 40, "max_model_calls": 0, "max_fanout": 4},
        "nodes": [
            {"kind": "map", "id": "each", "over": {"ref": "input.files"}, "item_key": "path",
             "max_items": 4, "on_item_failure": "skip", "body": [
                 {"kind": "transform", "id": "size", "op": "pluck",
                  "args": {"value": {"ref": "item"}, "path": "size"}}]},
            {"kind": "transform", "id": "total", "op": "sum", "args": {"items": {"ref": "each.items"}}},
            {"kind": "branch", "id": "route", "condition": {"ref": "total", "op": "gt", "value": 10},
             "then": [{"kind": "transform", "id": "big", "op": "constant", "args": {"value": "big"}}],
             "else": [{"kind": "transform", "id": "small", "op": "constant", "args": {"value": "small"}}]},
            {"kind": "join", "id": "joined", "of": ["total", "route"], "policy": "all_settled"},
        ],
    }
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=plan,
        inputs={"files": [{"path": "a", "size": 6}, {"path": "b", "size": 7}]})
    drive(engine, store, submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    nodes = {node["site_id"]: node for node in view["nodes"]}
    assert nodes["each"]["result"]["keys"] == ["a", "b"]
    assert nodes["each"]["result"]["complete"] is True
    assert nodes["total"]["result"] == 13
    assert nodes["route"]["result"]["taken"] == "then"
    assert nodes["joined"]["result"]["complete"] is True


def test_fanout_over_the_cap_fails_loudly(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = {
        "name": "too-many",
        "inputs": {"files": {"type": "array"}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 40, "max_model_calls": 0, "max_fanout": 2},
        "nodes": [{"kind": "map", "id": "each", "over": {"ref": "input.files"}, "item_key": "path",
                   "max_items": 2, "body": [
                       {"kind": "transform", "id": "t", "op": "count", "args": {"items": {"ref": "item"}}}]}],
    }
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=plan, inputs={"files": [{"path": "a"}, {"path": "b"}, {"path": "c"}]})
    drive(engine, store, submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert "exceeds the allowed 2" in view["workflow"]["reason"]


def test_question_waits_and_is_answered_by_its_own_id(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = {
        "name": "ask-first",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 10, "max_model_calls": 0},
        "nodes": [
            {"kind": "ask", "id": "confirm", "question": "Proceed with the report?",
             "options": ["yes", "no"], "timeout_seconds": 600},
            {"kind": "transform", "id": "after", "op": "constant",
             "args": {"value": {"ref": "confirm.answer"}}},
        ],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    deadline = time.monotonic() + 15
    question = None
    while time.monotonic() < deadline:
        engine.dispatch_pending()
        pending = wstore.questions(store, submission.workflow_run_id, status="pending")
        if pending:
            question = pending[0]
            break
        time.sleep(0.05)
    assert question is not None and question["question"] == "Proceed with the report?"
    assert wfsubmit.status(store, submission.workflow_run_id)["workflow"]["status"] == "waiting"
    assert wfsubmit.answer(store, question["id"], "yes") == "won"
    drive(engine, store, submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded"
    nodes = {node["site_id"]: node for node in view["nodes"]}
    assert nodes["after"]["result"] == "yes"


def test_saved_definition_runs_without_any_planning_call(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan(),
                             definition_name="collect-and-report")
    submission = wfsubmit.submit_saved(store, bot=bot, definition="collect-and-report",
                                       inputs={"root": "."})
    drive(engine, store, submission.attempt_run_id)
    assert wfsubmit.status(store, submission.workflow_run_id)["workflow"]["status"] == "succeeded"
    entry = wstore.definition(store, "collect-and-report")
    assert entry is not None and entry["revisions"] == 1
    assert len(wstore.list_workflow_runs(store)) == 2
