"""End-to-end workflow execution contracts.

These run the real engine: submission, admission, claim, the owned worker, the
deterministic interpreter, the canonical tool seam, artifact publication and the
verification vocabulary. The model side uses the harness's deterministic scenario runtime
(never product code), so what is proven here is the *engine*, not model quality.
"""
from __future__ import annotations

import json
import time

import pytest

from hutch.engine import Engine
from hutch.models import ACTIVE_STATUSES, Bot, EventType, Run, RunStatus, Schedule, Task, TriggerKind
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
    workflow_id = store.get_run(attempt_run_id).workflow_run_id
    current_attempt = attempt_run_id
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        engine.tick()
        workflow = wstore.workflow_run(store, workflow_id)
        if workflow is not None and workflow["attempt_run_id"] != current_attempt:
            current_attempt = workflow["attempt_run_id"]
        run = store.get_run(current_attempt)
        if (workflow is not None and workflow["status"] in ("succeeded", "failed", "stopped", "outcome_unknown")
                and (run is None or run.terminal)):
            return
        if run is None or (run.status not in ACTIVE_STATUSES and run.status.value != "waiting_workflow"):
            engine.tick()
        if run is not None and run.status.value == "waiting_workflow":
            if wstore.questions(store, workflow_id, status="pending"):
                return
        time.sleep(0.05)
    raise AssertionError("the workflow did not settle in time")


def simulate_workflow_crash(store: Store, attempt_run_id: str) -> None:
    """Record the status the supervisor writes after the workflow owner disappears."""
    with store._tx() as db:
        row = db.execute("SELECT doc FROM runs WHERE id = ?", (attempt_run_id,)).fetchone()
        assert row is not None
        document = json.loads(str(row["doc"]))
        document.update(status="failed", exit_reason="interrupted", error="simulated crash")
        db.execute("UPDATE runs SET status='failed', doc=? WHERE id=?",
                   (json.dumps(document), attempt_run_id))


def claim_workflow_owner(store: Store, wf_id: str, attempt_id: str, *, owner: str = "test-workflow-owner"):
    run = store.claim_run(attempt_id, owner, 60)
    assert run is not None
    run = store.transition_run(run.id, RunStatus.running, fence=run.fence)
    workflow = wstore.workflow_run(store, wf_id)
    assert workflow is not None
    assert wstore.claim_workflow_attempt(store, wf_id, attempt_id,
                                         owner_fence=run.fence,
                                         revision_id=workflow["revision_id"])
    return run, workflow


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


def test_existing_scheduler_runs_the_pinned_saved_workflow_once(store, config):
    bot = make_bot(store)
    saved = wstore.save_definition(store, name="scheduled report", plan=deterministic_plan(), activate=True)
    schedule = Schedule(
        id="schedule_workflow_once", name="Weekly report", trigger=TriggerKind.once,
        anchor_at="2026-10-10T00:00:00+00:00", timezone="UTC", enabled=True,
        workflow_definition_id=saved["definition_id"], workflow_revision_id=saved["revision_id"],
        workflow_inputs={"root": "."},
    )
    store.put_schedule(bot.id, schedule)
    store.kv_set(f"{schedule.id}:last_fire", "2026-10-09T00:00:00+00:00")
    engine = Engine(config, store)

    created = engine.scheduler_claims()
    assert len(created) == 1
    attempt = created[0]
    assert attempt.kind == "workflow"
    assert attempt.schedule_id == schedule.id
    assert attempt.workflow_run_id
    drive(engine, store, attempt.id)

    result = wstore.workflow_run(store, attempt.workflow_run_id)
    assert result is not None
    assert result["status"] == "succeeded"
    assert result["definition_id"] == saved["definition_id"]
    assert result["revision_id"] == saved["revision_id"]
    occurrences = store.list_schedule_occurrences(schedule.id, limit=10)
    assert len(occurrences) == 1
    assert occurrences[0]["run_id"] == attempt.id
    assert engine.scheduler_claims() == []
    assert len(store.list_schedule_occurrences(schedule.id, limit=10)) == 1


def test_output_projection_separates_verified_and_partial_from_node_counts(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = deterministic_plan(outputs=["count", "report"])
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)

    drive(engine, store, submission.attempt_run_id)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded"
    result = view["workflow"]["result"]
    assert result["output_outcomes"] == {
        "verified": ["count"], "partial": ["report"], "skipped": [],
        "failed": [], "uncertain": [],
    }
    assert result["counts"]["succeeded"] == 4


def test_later_failed_verification_revokes_an_earlier_output_claim(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = {
        "name": "verification-revocation",
        "budget": {"max_nodes": 8, "max_model_calls": 0},
        "nodes": [
            {"kind": "transform", "id": "value", "op": "constant", "args": {"value": 3}},
            {"kind": "verify", "id": "first", "checks": [
                {"kind": "schema", "ref": "value", "schema": {"type": "integer", "minimum": 1}}]},
            {"kind": "verify", "id": "second", "checks": [
                {"kind": "schema", "ref": "value", "schema": {"type": "integer", "minimum": 4}}]},
        ],
        "outputs": ["value"],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)

    drive(engine, store, submission.attempt_run_id)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert view["workflow"]["result"]["output_outcomes"] == {
        "verified": [], "partial": ["value"], "skipped": [], "failed": [], "uncertain": [],
    }


def test_a_later_pass_does_not_erase_a_continued_failed_criterion(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = {
        "name": "continued-failed-criterion",
        "budget": {"max_nodes": 8, "max_model_calls": 0},
        "nodes": [
            {"kind": "transform", "id": "value", "op": "constant", "args": {"value": 3}},
            {"kind": "verify", "id": "first", "checks": [
                {"kind": "schema", "ref": "value", "schema": {"type": "integer", "minimum": 4}}],
             "on_fail": {"action": "continue"}},
            {"kind": "verify", "id": "second", "checks": [
                {"kind": "schema", "ref": "value", "schema": {"type": "integer", "minimum": 1}}]},
        ],
        "outputs": ["value"],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)

    drive(engine, store, submission.attempt_run_id)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded"
    result = view["workflow"]["result"]
    assert result["output_outcomes"] == {
        "verified": [], "partial": ["value"], "skipped": [], "failed": [], "uncertain": [],
    }


def test_uncertain_child_is_projected_as_uncertain_output(store, monkeypatch):
    from types import SimpleNamespace
    from hutch.workflow.runtime import workflow_result_projection

    bot = make_bot(store)
    plan = {"name": "uncertain-output", "nodes": [
        {"kind": "transform", "id": "value", "op": "constant", "args": {"value": 5}},
    ], "outputs": ["value"]}
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    owner, workflow = claim_workflow_owner(store, submission.workflow_run_id,
                                           submission.attempt_run_id)
    wstore.open_node(store, submission.workflow_run_id, owner_run_id=owner.id,
                     owner_fence=owner.fence, revision_id=workflow["revision_id"],
                     site_id="value", instance_key="once", kind="step",
                     input_value={}, input_hash="0" * 64)
    with store._tx() as db:
        db.execute("UPDATE workflow_nodes SET run_id='unknown-child' WHERE workflow_run_id=?",
                   (submission.workflow_run_id,))
    monkeypatch.setattr(store, "get_run", lambda _run_id: SimpleNamespace(
        status=SimpleNamespace(value="outcome_unknown")))

    result = workflow_result_projection(store, submission.workflow_run_id,
                                        status="outcome_unknown", output_sites=["value"])

    assert result["output_outcomes"] == {
        "verified": [], "partial": [], "skipped": [], "failed": [], "uncertain": ["value"],
    }


def test_all_settled_join_preserves_failed_and_skipped_targets(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = {
        "name": "partial-join",
        "inputs": {"run_skip": {"type": "boolean"}},
        "budget": {"max_nodes": 10, "max_model_calls": 0},
        "nodes": [
            {"kind": "transform", "id": "not_list", "op": "constant", "args": {"value": "no"}},
            {"kind": "transform", "id": "broken", "op": "sum", "args": {"items": {"ref": "not_list"}}},
            {"kind": "transform", "id": "skipped", "op": "constant", "when": {
                "ref": "input.run_skip", "op": "eq", "value": True}, "args": {"value": 2}},
            {"kind": "transform", "id": "good", "op": "constant", "args": {"value": 7}},
            {"kind": "join", "id": "joined", "of": ["broken", "skipped", "good"],
             "policy": "all_settled"},
        ],
        "outputs": ["broken", "skipped", "joined"],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, inputs={"run_skip": False})

    drive(engine, store, submission.attempt_run_id)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    nodes = {node["site_id"]: node for node in view["nodes"]}
    assert nodes["broken"]["status"] == "failed"
    assert nodes["skipped"]["status"] == "skipped"
    assert nodes["joined"]["result"] == {
        "complete": False, "accepted": False, "policy": "all_settled",
        "items": {"good": 7}, "missing": [], "failed": ["broken"],
        "skipped": ["skipped"], "settled": 1, "required": 3,
    }
    result = view["workflow"]["result"]["output_outcomes"]
    assert result == {
        "verified": [], "partial": ["joined"], "skipped": ["skipped"],
        "failed": ["broken"], "uncertain": [],
    }


def test_all_required_join_rejects_a_skipped_target_explicitly(store, config):
    bot = make_bot(store)
    engine = Engine(config, store)
    plan = {
        "name": "required-skipped-join",
        "inputs": {"include": {"type": "boolean"}},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [
            {"kind": "transform", "id": "optional", "op": "constant",
             "when": {"ref": "input.include", "op": "eq", "value": True},
             "args": {"value": "present"}},
            {"kind": "join", "id": "joined", "of": ["optional"], "policy": "all_required"},
        ],
        "outputs": ["optional"],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan, inputs={"include": False})

    drive(engine, store, submission.attempt_run_id)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert "required inputs are missing: ['optional']" in view["workflow"]["reason"]
    assert view["workflow"]["result"]["output_outcomes"]["skipped"] == ["optional"]


def test_reused_results_are_not_re_executed_on_continuation(store, config):
    """A crashed attempt continues: settled nodes are read back, never run again."""
    bot = make_bot(store)
    engine = Engine(config, store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    drive(engine, store, submission.attempt_run_id)
    first = wstore.nodes(store, submission.workflow_run_id)
    before = {node["site_id"]: node["result"] for node in first}

    # Simulate a process loss after the plan's settled rows were recorded.
    simulate_workflow_crash(store, submission.attempt_run_id)
    wstore.update_workflow_run(store, submission.workflow_run_id, status="running")
    continuation = wstore.admit_workflow_continuation(store, submission.workflow_run_id)
    assert continuation is not None and continuation.id != submission.attempt_run_id
    drive(engine, store, continuation.id)

    after = wstore.nodes(store, submission.workflow_run_id)
    assert {node["site_id"]: node["result"] for node in after} == before
    assert store.get_run(continuation.id).status.value == "succeeded"


def test_recovery_query_uses_cutoff_before_terminal_status_values(store):
    """A crash-marked failed attempt is eligible only after the cutoff."""

    bot = make_bot(store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    with store._tx() as db:
        db.execute("UPDATE workflow_runs SET status='running', updated_at='2000-01-01T00:00:00+00:00' "
                   "WHERE id=?", (submission.workflow_run_id,))
    simulate_workflow_crash(store, submission.attempt_run_id)

    rows = wstore.workflow_runs_needing_attempt(store, quiet_seconds=0)
    assert submission.workflow_run_id in {row["id"] for row in rows}


def test_model_unavailable_attempt_fails_workflow_without_retry(store, config):
    bot = make_bot(store)
    engine = Engine(config, store, light=True)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    owner = store.claim_run(submission.attempt_run_id, "unavailable-model-owner", 60)
    assert owner is not None
    owner = store.transition_run(owner.id, RunStatus.running, fence=owner.fence)
    store.transition_run(owner.id, RunStatus.failed, fence=owner.fence,
                         exit_reason="model_unavailable", error="the configured model route is unavailable")

    assert wstore.admit_workflow_continuation(store, submission.workflow_run_id) is None
    engine.continue_workflow_runs()

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert "configured model route is unavailable" in view["workflow"]["reason"]
    assert view["workflow"]["attempt_run_id"] == submission.attempt_run_id
    assert wstore.workflow_runs_needing_attempt(store, quiet_seconds=0) == []


def test_interrupted_attempt_recovery_is_bounded_at_two_continuations(store, config):
    bot = make_bot(store)
    engine = Engine(config, store, light=True)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    attempt_id = submission.attempt_run_id
    for _ in range(2):
        simulate_workflow_crash(store, attempt_id)
        with store._tx() as db:
            db.execute("UPDATE workflow_runs SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                       (submission.workflow_run_id,))
        continuation = wstore.admit_workflow_continuation(store, submission.workflow_run_id)
        assert continuation is not None
        attempt_id = continuation.id

    simulate_workflow_crash(store, attempt_id)
    with store._tx() as db:
        db.execute("UPDATE workflow_runs SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                   (submission.workflow_run_id,))
    assert wstore.admit_workflow_continuation(store, submission.workflow_run_id) is None
    assert wstore.workflow_recovery_exhausted(store, submission.workflow_run_id)
    engine.continue_workflow_runs()

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert view["workflow"]["attempt_run_id"] == attempt_id
    assert view["workflow"]["ledger"]["attempts"] == 2
    assert view["workflow"]["ledger"]["recoveries"] == 2
    assert "recovery limit reached" in view["workflow"]["reason"]


def test_stale_workflow_attempt_cannot_replace_the_current_owner(store):
    bot = make_bot(store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    old_attempt = submission.attempt_run_id
    claim_workflow_owner(store, submission.workflow_run_id, old_attempt)

    with store._tx() as db:
        db.execute("UPDATE workflow_runs SET attempt_run_id='replacement-attempt' WHERE id=?",
                   (submission.workflow_run_id,))

    workflow = wstore.workflow_run(store, submission.workflow_run_id)
    assert workflow is not None
    assert not wstore.claim_workflow_attempt(store, submission.workflow_run_id, old_attempt,
                                             owner_fence=store.get_run(old_attempt).fence,
                                             revision_id=workflow["revision_id"])
    assert wstore.workflow_run(store, submission.workflow_run_id)["attempt_run_id"] == "replacement-attempt"


def test_stale_or_expired_workflow_owner_cannot_mutate_node_or_question(store):
    from hutch.lifecycle import LeaseLost

    bot = make_bot(store)
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=deterministic_plan())
    owner, workflow = claim_workflow_owner(store, submission.workflow_run_id,
                                           submission.attempt_run_id)
    owner_args = {"owner_run_id": owner.id, "owner_fence": owner.fence,
                  "revision_id": workflow["revision_id"]}

    # Replacing the workflow generation immediately fences the still-running old attempt.
    with store._tx() as db:
        db.execute("UPDATE workflow_runs SET attempt_run_id='new-generation' WHERE id=?",
                   (submission.workflow_run_id,))
    with pytest.raises(LeaseLost):
        wstore.open_node(store, submission.workflow_run_id, **owner_args, site_id="scan",
                         instance_key="once", kind="tool", input_value={}, input_hash="0" * 64)
    with pytest.raises(LeaseLost):
        wstore.create_question(store, wf_id=submission.workflow_run_id, **owner_args,
                               site_id="ask", instance_key="once", question="Continue?",
                               options=["yes", "no"], expires_at="2999-01-01T00:00:00+00:00")
    with pytest.raises(LeaseLost):
        wstore.settle_node(store, submission.workflow_run_id, "scan", "once", **owner_args,
                           status="succeeded", result={"data": []})

    # Restore the generation only to prove that an expired lease itself blocks a write.
    with store._tx() as db:
        db.execute("UPDATE workflow_runs SET attempt_run_id=? WHERE id=?",
                   (owner.id, submission.workflow_run_id))
    with pytest.raises(LeaseLost):
        wstore.open_node(store, submission.workflow_run_id,
                         **{**owner_args, "revision_id": "wrong-revision"}, site_id="scan",
                         instance_key="once", kind="tool", input_value={}, input_hash="0" * 64)
    with pytest.raises(LeaseLost):
        wstore.open_node(store, submission.workflow_run_id,
                         **{**owner_args, "owner_fence": owner.fence + 1}, site_id="scan",
                         instance_key="once", kind="tool", input_value={}, input_hash="0" * 64)
    with store._tx() as db:
        db.execute("UPDATE runs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                   (owner.id,))
    with pytest.raises(LeaseLost):
        wstore.open_node(store, submission.workflow_run_id, **owner_args, site_id="scan",
                         instance_key="once", kind="tool", input_value={}, input_hash="0" * 64)


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
        parked = store.get_run(submission.attempt_run_id)
        if pending and parked is not None and parked.status is RunStatus.waiting_workflow:
            question = pending[0]
            break
        time.sleep(0.05)
    assert question is not None and question["question"] == "Proceed with the report?"
    assert wfsubmit.status(store, submission.workflow_run_id)["workflow"]["status"] == "waiting"
    parked = store.get_run(submission.attempt_run_id)
    assert parked.status is RunStatus.waiting_workflow and not parked.terminal
    assert parked.lease_owner == ""
    other = make_bot(store, name="other-bot")
    unrelated = Run(bot_id=other.id, prompt="unrelated work")
    store.submit_run(unrelated, Task(bot_id=other.id, kind="on_demand", prompt=unrelated.prompt))
    assert store.claim_run(unrelated.id, "other-owner", 60, max_live=1) is not None
    assert wfsubmit.answer(store, question["id"], "yes") == "won"
    drive(engine, store, submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded"
    assert view["workflow"]["attempt_run_id"] != submission.attempt_run_id
    nodes = {node["site_id"]: node for node in view["nodes"]}
    assert nodes["after"]["result"] == "yes"


@pytest.mark.parametrize("answer_order", [("first", "second"), ("second", "first")])
def test_independent_questions_are_all_exposed_and_answerable_in_both_orders_after_restart(
        store, config, answer_order):
    bot = make_bot(store, name="parallel-questions")
    engine = Engine(config, store)
    plan = {
        "name": "independent-questions",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 10, "max_model_calls": 0},
        "nodes": [
            {"kind": "ask", "id": "first", "question": "Choose the first setting?",
             "timeout_seconds": 600},
            {"kind": "ask", "id": "second", "question": "Choose the second setting?",
             "timeout_seconds": 600},
            {"kind": "transform", "id": "combined", "op": "to_json",
             "args": {"value": [{"ref": "first.answer"}, {"ref": "second.answer"}]}},
        ],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    drive(engine, store, submission.attempt_run_id)

    questions = wstore.questions(store, submission.workflow_run_id)
    pending = {question["site_id"]: question for question in questions
               if question["status"] == "pending"}
    assert set(pending) == {"first", "second"}
    assert len({question["id"] for question in pending.values()}) == 2
    assert {question["id"] for question in wstore.pending_questions_for_review(store)} == {
        question["id"] for question in pending.values()}

    answer_values = {"first": "alpha", "second": "beta"}
    before_answer_attempt = wstore.workflow_run(store, submission.workflow_run_id)["attempt_run_id"]
    first_site, second_site = answer_order
    assert wfsubmit.answer(store, pending[first_site]["id"], answer_values[first_site]) == "won"
    drive(engine, store, submission.attempt_run_id)

    after_first = wstore.workflow_run(store, submission.workflow_run_id)
    assert after_first["attempt_run_id"] == before_answer_attempt
    still_pending = [question for question in wstore.questions(store, submission.workflow_run_id)
                     if question["status"] == "pending"]
    assert [question["id"] for question in still_pending] == [pending[second_site]["id"]]
    assert after_first["status"] == "waiting"
    assert not any(node["site_id"] == "combined"
                   for node in wstore.nodes(store, submission.workflow_run_id))
    assert {question["id"] for question in wstore.pending_questions_for_review(store)} == {
        pending[second_site]["id"]}

    # A partial answer does not advance the workflow generation or retire its other IDs.
    # Closing the original Store and using a new Engine/SQLite connection models restart.
    store.close()
    store = Store(config)
    engine = Engine(config, store)
    after_restart = wstore.workflow_run(store, submission.workflow_run_id)
    assert after_restart["attempt_run_id"] == before_answer_attempt
    pending_after_restart = wstore.questions(store, submission.workflow_run_id, status="pending")
    assert [question["id"] for question in pending_after_restart] == [pending[second_site]["id"]]
    assert wfsubmit.answer(store, pending[second_site]["id"], answer_values[second_site]) == "won"
    drive(engine, store, submission.attempt_run_id)

    final = wfsubmit.status(store, submission.workflow_run_id)
    assert final["workflow"]["status"] == "succeeded"
    combined = next(node for node in final["nodes"] if node["site_id"] == "combined")["result"]
    assert json.loads(combined) == ["alpha", "beta"]


@pytest.mark.parametrize("answer_order", [("alpha", "beta"), ("beta", "alpha")])
def test_bounded_map_exposes_one_question_per_item_up_to_concurrency_after_restart(
        store, config, answer_order):
    bot = make_bot(store, name="map-questions")
    engine = Engine(config, store)
    plan = {
        "name": "map-item-questions",
        "inputs": {"settings": {"type": "array", "max_items": 2}},
        "envelope": {"tools": [], "max_parallel_steps": 2},
        "budget": {"max_nodes": 12, "max_model_calls": 0, "max_fanout": 2},
        "nodes": [
            {"kind": "map", "id": "review", "over": {"ref": "input.settings"},
             "item_key": "key", "concurrency": 2, "max_items": 2, "body": [
                 {"kind": "ask", "id": "confirm", "inputs": {"label": {"ref": "item.label"}},
                  "question": "How should {{label}} be configured?", "timeout_seconds": 600}]},
            {"kind": "transform", "id": "combined", "op": "to_json",
             "args": {"value": {"ref": "review.items"}}},
        ],
    }
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=plan,
        inputs={"settings": [{"key": "alpha", "label": "Alpha"},
                             {"key": "beta", "label": "Beta"}]})
    drive(engine, store, submission.attempt_run_id)

    pending = wstore.questions(store, submission.workflow_run_id, status="pending")
    assert len(pending) == 2
    assert {question["site_id"] for question in pending} == {"review.confirm"}
    assert {question["question"] for question in pending} == {
        "How should Alpha be configured?", "How should Beta be configured?"}
    assert len({question["instance_key"] for question in pending}) == 2
    assert {question["id"] for question in wstore.pending_questions_for_review(store)} == {
        question["id"] for question in pending}
    ask_nodes = [node for node in wstore.nodes(store, submission.workflow_run_id)
                 if node["site_id"] == "review.confirm"]
    assert len(ask_nodes) == 2
    assert {node["status"] for node in ask_nodes} == {"waiting"}

    pending_by_label = {question["question"].split()[2].lower(): question for question in pending}
    answers = {"alpha": "compact", "beta": "extended"}
    first_label, second_label = answer_order
    generation = wstore.workflow_run(store, submission.workflow_run_id)["attempt_run_id"]
    first_question = pending_by_label[first_label]
    assert wfsubmit.answer(store, first_question["id"], answers[first_label]) == "won"
    drive(engine, store, submission.attempt_run_id)

    still_waiting = wstore.workflow_run(store, submission.workflow_run_id)
    remaining = wstore.questions(store, submission.workflow_run_id, status="pending")
    assert still_waiting["attempt_run_id"] == generation
    assert still_waiting["status"] == "waiting"
    assert still_waiting["reason"] == "waiting for 1 answer(s)"
    assert len(remaining) == 1
    assert remaining[0]["id"] != first_question["id"]
    ask_nodes = [node for node in wstore.nodes(store, submission.workflow_run_id)
                 if node["site_id"] == "review.confirm"]
    assert {node["status"] for node in ask_nodes} == {"waiting"}
    assert wstore.question(store, first_question["id"])["status"] == "answered"
    assert not any(node["site_id"] == "combined"
                   for node in wstore.nodes(store, submission.workflow_run_id))

    store.close()
    store = Store(config)
    engine = Engine(config, store)
    after_restart = wstore.questions(store, submission.workflow_run_id, status="pending")
    assert [question["id"] for question in after_restart] == [remaining[0]["id"]]
    second_question = pending_by_label[second_label]
    assert second_question["id"] == remaining[0]["id"]
    assert wfsubmit.answer(store, second_question["id"], answers[second_label]) == "won"
    drive(engine, store, submission.attempt_run_id)

    final = wfsubmit.status(store, submission.workflow_run_id)
    assert final["workflow"]["status"] == "succeeded"
    combined = json.loads(next(node for node in final["nodes"]
                               if node["site_id"] == "combined")["result"])
    by_question = {item["question_id"]: item["answer"] for item in combined}
    assert by_question == {question["id"]: answers[label]
                           for label, question in pending_by_label.items()}
    settled_asks = [node for node in final["nodes"] if node["site_id"] == "review.confirm"]
    assert len(settled_asks) == 2
    assert {node["status"] for node in settled_asks} == {"succeeded"}
    assert {node["result"]["answer"] for node in settled_asks} == {"compact", "extended"}
    assert {node["result"]["question_id"] for node in settled_asks} == {
        question["id"] for question in pending_by_label.values()}


@pytest.mark.parametrize("answer_order", [("region", "capacity"), ("capacity", "region")])
def test_bounded_map_collects_independent_questions_within_an_item_after_restart(
        store, config, answer_order):
    bot = make_bot(store, name="nested-map-questions")
    engine = Engine(config, store)
    plan = {
        "name": "one-map-item-two-questions",
        "inputs": {"settings": {"type": "array", "max_items": 1}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 8, "max_model_calls": 0, "max_fanout": 1},
        "nodes": [
            {"kind": "map", "id": "review", "over": {"ref": "input.settings"},
             "item_key": "key", "concurrency": 1, "max_items": 1, "body": [
                 {"kind": "ask", "id": "region", "inputs": {"label": {"ref": "item.label"}},
                  "question": "Which region for {{label}}?", "timeout_seconds": 600},
                 {"kind": "ask", "id": "capacity", "inputs": {"label": {"ref": "item.label"}},
                  "question": "How many users for {{label}}?", "timeout_seconds": 600},
                 {"kind": "transform", "id": "summary", "op": "to_json",
                  "args": {"value": [{"ref": "review.region.answer"},
                                      {"ref": "review.capacity.answer"}]}}
             ]},
        ],
    }
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=plan,
        inputs={"settings": [{"key": "alpha", "label": "Alpha"}]})
    drive(engine, store, submission.attempt_run_id)

    pending = wstore.questions(store, submission.workflow_run_id, status="pending")
    assert len(pending) == 2
    assert {question["site_id"] for question in pending} == {"review.region", "review.capacity"}
    assert {question["instance_key"] for question in pending} == {"item:alpha"}
    assert {node["site_id"] for node in wstore.nodes(store, submission.workflow_run_id)} == {
        "review.region", "review.capacity"}
    assert {node["status"] for node in wstore.nodes(store, submission.workflow_run_id)} == {"waiting"}

    questions_by_site = {question["site_id"].removeprefix("review."): question for question in pending}
    answers = {"region": "west", "capacity": "120"}
    first_site, second_site = answer_order
    generation = wstore.workflow_run(store, submission.workflow_run_id)["attempt_run_id"]
    assert wfsubmit.answer(store, questions_by_site[first_site]["id"], answers[first_site]) == "won"
    drive(engine, store, submission.attempt_run_id)
    still_waiting = wstore.workflow_run(store, submission.workflow_run_id)
    assert still_waiting["attempt_run_id"] == generation
    assert still_waiting["reason"] == "waiting for 1 answer(s)"
    assert len(wstore.questions(store, submission.workflow_run_id, status="pending")) == 1
    assert not any(node["site_id"] == "review.summary"
                   for node in wstore.nodes(store, submission.workflow_run_id))

    store.close()
    store = Store(config)
    engine = Engine(config, store)
    assert wfsubmit.answer(store, questions_by_site[second_site]["id"], answers[second_site]) == "won"
    drive(engine, store, submission.attempt_run_id)
    final = wfsubmit.status(store, submission.workflow_run_id)
    assert final["workflow"]["status"] == "succeeded"
    settled_asks = {node["site_id"]: node for node in final["nodes"]
                    if node["site_id"] in {"review.region", "review.capacity"}}
    assert {node["status"] for node in settled_asks.values()} == {"succeeded"}
    assert {site.removeprefix("review."): node["result"]["answer"]
            for site, node in settled_asks.items()} == answers
    assert next(node for node in final["nodes"] if node["site_id"] == "review.summary")["status"] == "succeeded"


def test_bounded_map_holds_dependent_question_until_its_answer_arrives(store, config):
    bot = make_bot(store, name="dependent-map-questions")
    engine = Engine(config, store)
    plan = {
        "name": "dependent-map-questions",
        "inputs": {"settings": {"type": "array", "max_items": 1}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 8, "max_model_calls": 0, "max_fanout": 1},
        "nodes": [
            {"kind": "map", "id": "review", "over": {"ref": "input.settings"},
             "item_key": "key", "concurrency": 1, "max_items": 1, "body": [
                 {"kind": "ask", "id": "region", "question": "Which region should be used?",
                  "timeout_seconds": 600},
                 {"kind": "ask", "id": "capacity", "inputs": {
                     "region": {"ref": "review.region.answer"}},
                  "question": "How many users in {{region}}?", "timeout_seconds": 600}
             ]},
        ],
    }
    submission = wfsubmit.submit_workflow(
        store, bot=bot, plan=plan,
        inputs={"settings": [{"key": "alpha"}]})
    drive(engine, store, submission.attempt_run_id)
    first = wstore.questions(store, submission.workflow_run_id, status="pending")
    assert len(first) == 1 and first[0]["site_id"] == "review.region"
    assert first[0]["question"] == "Which region should be used?"

    assert wfsubmit.answer(store, first[0]["id"], "west") == "won"
    drive(engine, store, submission.attempt_run_id)
    second = wstore.questions(store, submission.workflow_run_id, status="pending")
    assert len(second) == 1 and second[0]["site_id"] == "review.capacity"
    assert second[0]["question"] == "How many users in west?"
    records = {node["site_id"]: node for node in wstore.nodes(store, submission.workflow_run_id)}
    assert records["review.region"]["status"] == "succeeded"
    assert records["review.capacity"]["status"] == "waiting"

    assert wfsubmit.answer(store, second[0]["id"], "120") == "won"
    drive(engine, store, submission.attempt_run_id)
    final = wfsubmit.status(store, submission.workflow_run_id)
    assert final["workflow"]["status"] == "succeeded"
    records = {node["site_id"]: node for node in final["nodes"]}
    assert records["review.region"]["result"]["answer"] == "west"
    assert records["review.capacity"]["result"]["answer"] == "120"


def test_stopping_a_parked_workflow_finishes_after_cleanup_and_cancels_questions(store, config):
    bot = make_bot(store, name="stop-parked")
    engine = Engine(config, store)
    plan = {"name": "stop-parked", "envelope": {"tools": []},
            "budget": {"max_nodes": 5, "max_model_calls": 0},
            "nodes": [{"kind": "ask", "id": "confirm", "question": "Proceed?",
                       "timeout_seconds": 300}]}
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        engine.tick()
        pending = wstore.questions(store, submission.workflow_run_id, status="pending")
        attempt = store.get_run(submission.attempt_run_id)
        if pending and attempt is not None and attempt.status is RunStatus.waiting_workflow:
            break
        time.sleep(0.05)
    assert wstore.questions(store, submission.workflow_run_id, status="pending")
    assert store.get_run(submission.attempt_run_id).status is RunStatus.waiting_workflow

    wstore.request_workflow_stop(store, submission.workflow_run_id)
    engine.tick()
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "stopped"
    assert all(question["status"] == "cancelled" for question in view["questions"])
    ask_node = next(node for node in view["nodes"] if node["site_id"] == "confirm")
    assert ask_node["status"] == "cancelled"
    assert wfsubmit.answer(store, view["questions"][0]["id"], "yes") == "already"
    assert store.get_run(submission.attempt_run_id).status is RunStatus.stopped


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


def test_canonical_event_rejection_fails_the_attempt_then_recovers(store, config, monkeypatch):
    bot = make_bot(store, name="event-delivery-bot")
    engine = Engine(config, store)
    plan = {
        "name": "event-delivery-recovery",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 4, "max_model_calls": 0, "max_wall_seconds": 30},
        "nodes": [
            {"kind": "transform", "id": "first", "op": "constant", "args": {"value": "first"}},
            {"kind": "transform", "id": "second", "op": "constant", "args": {"value": "second"}},
        ],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    append = store.append_event
    rejected = False

    def reject_once(event):
        nonlocal rejected
        if (not rejected and event.type is EventType.step
                and event.data.get("node") == "first"
                and event.data.get("phase") == "started"):
            rejected = True
            raise RuntimeError("injected canonical event queue failure")
        return append(event)

    monkeypatch.setattr(store, "append_event", reject_once)
    drive(engine, store, submission.attempt_run_id, timeout=30)

    failed_attempt = store.get_run(submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert rejected
    assert failed_attempt.status is RunStatus.failed
    assert failed_attempt.exit_reason == "event_delivery_failed"
    assert "canonical workflow event could not be queued" in failed_attempt.error
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert view["workflow"]["attempt_run_id"] != submission.attempt_run_id
    assert {node["site_id"]: node["status"] for node in view["nodes"]} == {
        "first": "succeeded", "second": "succeeded"}


def test_workflow_waits_for_canonical_event_commit_before_continuing(store, config, monkeypatch):
    bot = make_bot(store, name="event-commit-bot")
    engine = Engine(config, store)
    plan = {
        "name": "event-commit-recovery",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 4, "max_model_calls": 0, "max_wall_seconds": 30},
        "nodes": [{"kind": "transform", "id": "first", "op": "constant", "args": {"value": "first"}}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    flush = store.flush_events
    rejected = False

    def reject_commit_once(timeout=10.0):
        nonlocal rejected
        if not rejected:
            rejected = True
            raise RuntimeError("injected canonical event commit failure")
        return flush(timeout)

    monkeypatch.setattr(store, "flush_events", reject_commit_once)
    drive(engine, store, submission.attempt_run_id, timeout=30)

    failed_attempt = store.get_run(submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert rejected
    assert failed_attempt.status is RunStatus.failed
    assert failed_attempt.exit_reason == "event_delivery_failed"
    assert "could not be committed" in failed_attempt.error
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert view["workflow"]["attempt_run_id"] != submission.attempt_run_id
    assert view["nodes"][0]["status"] == "succeeded"


def test_event_failure_after_effect_reuses_receipt_on_recovery(store, config, monkeypatch):
    from hutch.tools import files as file_tools

    bot = make_bot(store, name="effect-event-delivery-bot", risk_tier="trusted")
    engine = Engine(config, store)
    plan = {
        "name": "effect-event-delivery-recovery",
        "envelope": {"tools": ["write_file"]},
        "budget": {"max_nodes": 4, "max_model_calls": 0, "max_wall_seconds": 30},
        "nodes": [{"kind": "tool", "id": "write", "tool": "write_file",
                   "args": {"path": "event-proof.txt", "content": "one effect"}}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    effect_calls = []
    replace_reviewed = file_tools.replace_reviewed

    def record_completed_write(workspace, parts, content, expected, begin_effect):
        replace_reviewed(workspace, parts, content, expected, begin_effect)
        effect_calls.append((str(workspace), "/".join(parts), content))

    monkeypatch.setattr(file_tools, "replace_reviewed", record_completed_write)
    append = store.append_event
    rejected = False

    def reject_result_once(event):
        nonlocal rejected
        if (not rejected and event.type is EventType.tool_result
                and event.data.get("tool") == "write_file"):
            rejected = True
            raise RuntimeError("injected result-event queue failure")
        return append(event)

    monkeypatch.setattr(store, "append_event", reject_result_once)
    drive(engine, store, submission.attempt_run_id, timeout=30)

    failed_attempt = store.get_run(submission.attempt_run_id)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert rejected
    assert failed_attempt.status is RunStatus.failed
    assert failed_attempt.exit_reason == "event_delivery_failed"
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert view["workflow"]["attempt_run_id"] != submission.attempt_run_id
    assert len(effect_calls) == 1
    assert effect_calls[0][1:] == ("event-proof.txt", "one effect")


def _repair_plan(*, rounds=2):
    return {
        "name": "repair-and-recheck",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 12, "max_model_calls": 4, "max_repairs": rounds,
                    "max_wall_seconds": 60},
        "nodes": [
            {"kind": "transform", "id": "producer", "op": "constant", "args": {"value": 1}},
            {"kind": "verify", "id": "check", "checks": [
                {"kind": "schema", "ref": "producer", "schema": {"type": "integer", "minimum": 3}}],
             "on_fail": {"action": "repair", "rounds": rounds, "adopt": "producer",
                         "instruction": "Return the corrected integer value."}},
            {"kind": "transform", "id": "after", "op": "constant",
             "args": {"value": {"ref": "producer"}}},
        ],
    }


def _use_repair_responses(monkeypatch, responses):
    from hutch import engine as engine_module
    from hutch.models import Event, EventType

    calls = []

    class CannedRepairRuntime:
        kind = "fixture-repair"

        def execute(self, run, ctx, _tools, _stop):
            index = len(calls)
            calls.append(run.id)
            text = responses[min(index, len(responses) - 1)]
            ctx.emit(Event(run_id=run.id, type=EventType.message,
                           data={"role": "assistant", "content": text}))
            return text

    runtime = CannedRepairRuntime()
    monkeypatch.setattr(engine_module, "get_runtime", lambda _bot: runtime)
    return calls


@pytest.fixture()
def repair_model(monkeypatch):
    from tests.fakes import FakeOllama

    server = FakeOllama({"tiny:1b": {"params": "1.0B", "size": 800_000_000, "ctx": 8192}})
    monkeypatch.setenv("OLLAMA_HOST", server.url)
    yield
    server.close()


def test_repair_adopts_output_and_rechecks_each_durable_round(store, config, monkeypatch, repair_model):
    bot = make_bot(store, name="repair-adoption-bot", model="ollama/tiny:1b", tools=[])
    engine = Engine(config, store)
    calls = _use_repair_responses(monkeypatch, ['{"replacement":2}', '{"replacement":3}'])
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=_repair_plan(rounds=2))

    drive(engine, store, submission.attempt_run_id, timeout=60)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert len(calls) == 2
    records = {(node["site_id"], node["instance_key"]): node for node in view["nodes"]}
    assert records[("producer", "once")]["result"] == 1
    assert records[("check", "once")]["result"]["ok"] is False
    assert records[("check", "once|repair:1")]["result"]["output"]["replacement"] == 2
    assert records[("check", "once|r1")]["result"]["ok"] is False
    assert records[("check", "once|repair:2")]["result"]["output"]["replacement"] == 3
    assert records[("check", "once|r2")]["result"]["verified"] is True
    assert records[("after", "once")]["result"] == 3


def test_repair_recovery_reuses_settled_output_and_reconstructs_adopted_scope(
        store, config, monkeypatch, repair_model):
    bot = make_bot(store, name="repair-recovery-bot", model="ollama/tiny:1b", tools=[])
    engine = Engine(config, store)
    calls = _use_repair_responses(monkeypatch, ['{"replacement":2}', '{"replacement":3}'])
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=_repair_plan(rounds=2))
    append = store.append_event
    rejected = {"repair": False, "recheck": False}

    def fail_after_durable_boundary(event):
        data = event.data
        if (event.type is EventType.step and data.get("node") == "check"
                and data.get("phase") == "succeeded" and data.get("instance") == "once|repair:1"
                and not rejected["repair"]):
            rejected["repair"] = True
            raise RuntimeError("crash after the repair result was durably settled")
        if (event.type is EventType.step and data.get("node") == "check"
                and data.get("phase") == "started" and data.get("instance") == "once|r1"
                and not rejected["recheck"]):
            rejected["recheck"] = True
            raise RuntimeError("crash after the recheck round was durably opened")
        return append(event)

    monkeypatch.setattr(store, "append_event", fail_after_durable_boundary)
    drive(engine, store, submission.attempt_run_id, timeout=60)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert rejected == {"repair": True, "recheck": True}
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert len(calls) == 2
    records = {(node["site_id"], node["instance_key"]): node for node in view["nodes"]}
    assert records[("check", "once|repair:1")]["status"] == "succeeded"
    assert records[("check", "once|r1")]["result"]["ok"] is False
    assert records[("check", "once|repair:2")]["result"]["output"]["replacement"] == 3
    assert records[("after", "once")]["result"] == 3


def test_repair_with_no_progress_fails_without_another_round(store, config, monkeypatch, repair_model):
    bot = make_bot(store, name="repair-no-progress-bot", model="ollama/tiny:1b", tools=[])
    engine = Engine(config, store)
    calls = _use_repair_responses(monkeypatch, ['{"replacement":1}'])
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=_repair_plan(rounds=2))

    drive(engine, store, submission.attempt_run_id, timeout=60)

    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "failed"
    assert "made no progress" in view["workflow"]["reason"]
    assert len(calls) == 1
    assert not any(node["instance_key"] == "once|r1" for node in view["nodes"])


def test_advisory_review_reads_the_validated_step_output(store, config, monkeypatch, repair_model):
    bot = make_bot(store, name="advisory-review-bot", model="ollama/tiny:1b", tools=[])
    engine = Engine(config, store)
    _use_repair_responses(monkeypatch, ['{"pass":true,"reason":"the value matches"}'])
    plan = {
        "name": "advisory-review",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 8, "max_model_calls": 2, "max_wall_seconds": 60},
        "nodes": [
            {"kind": "transform", "id": "producer", "op": "constant", "args": {"value": 3}},
            {"kind": "verify", "id": "check", "checks": [
                {"kind": "schema", "ref": "producer", "schema": {"type": "integer", "minimum": 1}},
                {"kind": "agent_review", "ref": "producer", "instruction": "Review the value."}],
            },
        ],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)

    drive(engine, store, submission.attempt_run_id, timeout=60)

    view = wfsubmit.status(store, submission.workflow_run_id)
    check = next(node for node in view["nodes"] if node["site_id"] == "check")
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert check["result"]["verified"] is True
    assert check["result"]["advisory"] == [
        {"kind": "agent_review", "ok": True, "detail": "the value matches", "advisory": True}]
