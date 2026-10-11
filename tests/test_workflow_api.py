"""Workflow API contracts: typed resources, idempotency, validation-only dry runs.

The dry-run route must compile and check authority without admitting or executing
anything; the run routes must be idempotent; and every question/approval keeps its own
identity.
"""
from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from hutch import providers
from hutch.hardware import Hardware
from hutch.server.app import create_app
from hutch.workflow import probes as probe_module
from tests.fakes import FakeOllama

KEY = {"Idempotency-Key": "wf-test-key-1"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def make_bot(client, name="wf-api-bot", **overrides) -> dict:
    body = {"name": name, "model": "mock/demo", "tools": ["files"],
            "approval_mode": "auto", "instructions": "workflow test bot"}
    body.update(overrides)
    res = client.post("/api/bots", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def plan(**overrides) -> dict:
    body = {
        "name": "api-collect",
        "inputs": {"root": {"type": "string", "default": "."}},
        "envelope": {"tools": ["list_files"]},
        "budget": {"max_nodes": 20, "max_model_calls": 0},
        "nodes": [
            {"kind": "tool", "id": "scan", "tool": "list_files", "args": {"path": {"ref": "input.root"}}},
            {"kind": "transform", "id": "count", "op": "pluck",
             "args": {"value": {"ref": "scan.data"}, "path": "count"}},
            {"kind": "publish", "id": "report", "artifacts": [
                {"name": "summary", "ref": "count", "primary": True}]},
            {"kind": "verify", "id": "check", "checks": [
                {"kind": "schema", "ref": "count", "schema": {"type": "integer", "minimum": 0}}]},
        ],
    }
    body.update(overrides)
    return body


def test_validate_compiles_and_checks_without_admitting_anything(client):
    bot = make_bot(client)
    res = client.post("/api/v1/workflows/validate", json={"plan": plan(), "bot": bot["name"]}, headers=KEY)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True and body["node_count"] == 4
    assert body["required_tools"] == ["list_files"]
    assert body["plan_hash"] and len(body["plan_hash"]) == 64
    # Nothing was admitted.
    runs = client.get("/api/v1/workflows/runs").json()
    assert runs["items"] == []
    assert client.get("/api/v1/workflows").json()["items"] == []


def test_validate_reports_diagnostics_for_an_invalid_plan(client):
    bot = make_bot(client)
    broken = plan()
    broken["nodes"][1]["args"]["value"] = {"ref": "missing_node"}
    res = client.post("/api/v1/workflows/validate", json={"plan": broken, "bot": bot["name"]}, headers=KEY)
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert any("missing_node" in item["message"] for item in body["diagnostics"])


def test_validate_reports_authority_refusals(client):
    bot = make_bot(client)
    plan_ = plan()
    plan_["envelope"]["tools"] = ["list_files", "shell"]
    res = client.post("/api/v1/workflows/validate", json={"plan": plan_, "bot": bot["name"]}, headers=KEY)
    body = res.json()
    assert body["ok"] is False and body["diagnostics"][0]["code"] == "authority"


def test_save_run_and_read_back_with_idempotency(client):
    bot = make_bot(client)
    saved = client.post("/api/v1/workflows", headers=KEY,
                        json={"name": "api-collect", "plan": plan(), "description": "test"})
    assert saved.status_code == 201, saved.text
    assert saved.json()["revisions"] == 1
    assert client.get("/api/v1/workflows").json()["items"][0]["name"] == "api-collect"
    fetched = client.get("/api/v1/workflows/api-collect").json()
    assert fetched["plan"]["name"] == "api-collect"

    conversation = client.post("/api/v1/conversations", headers={"Idempotency-Key": "workflow-run-chat"},
                               json={"bot": bot["name"], "title": "Workflow run"})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]

    res = client.post("/api/v1/workflows/api-collect/runs", headers=KEY,
                      json={"bot": bot["name"], "conversation_id": conversation_id, "inputs": {}})
    assert res.status_code == 201, res.text
    submission = res.json()
    assert submission["workflow_run_id"].startswith("wrun_")

    replay = client.post("/api/v1/workflows/api-collect/runs", headers=KEY,
                         json={"bot": bot["name"], "conversation_id": conversation_id, "inputs": {}})
    assert replay.status_code == 201
    assert replay.json()["workflow_run_id"] == submission["workflow_run_id"]
    assert len(client.get("/api/v1/workflows/runs").json()["items"]) == 1

    # Drive the engine until the instance settles, then read the authoritative view.
    from hutch.store import Store
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/workflows/runs/{submission['workflow_run_id']}").json()
        if detail["workflow"]["status"] in ("succeeded", "failed", "stopped"):
            break
        time.sleep(0.1)
    assert detail["workflow"]["status"] == "succeeded", detail
    assert detail["workflow"]["conversation_id"] == conversation_id
    assert {node["site_id"] for node in detail["nodes"]} == {"scan", "count", "report", "check"}
    assert detail["plan"]["name"] == "api-collect"
    assert [item["site_id"] for item in detail["structure"]] == ["scan", "count", "report", "check"]
    assert detail["workflow"]["result"]["artifacts"][0]["name"] == "summary"


def test_dynamic_plan_submission_is_bound_to_its_conversation(client):
    bot = make_bot(client, name="wf-plan-chat-owner")
    other = make_bot(client, name="wf-plan-chat-other")
    created = client.post("/api/v1/conversations", headers={"Idempotency-Key": "wf-plan-chat-create"},
                          json={"bot": bot["name"], "title": "Dynamic workflow chat"})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    simple_plan = {
        "name": "conversation-bound-plan",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 3, "max_model_calls": 0},
        "nodes": [{"kind": "transform", "id": "value", "op": "constant",
                   "args": {"value": "chat-bound"}}],
    }
    submitted = client.post("/api/v1/workflows/plans", headers={"Idempotency-Key": "wf-plan-chat-submit"},
                            json={"plan": simple_plan, "bot": bot["name"],
                                  "conversation_id": conversation_id})
    assert submitted.status_code == 201, submitted.text
    detail = client.get(f"/api/v1/workflows/runs/{submitted.json()['workflow_run_id']}").json()
    assert detail["workflow"]["conversation_id"] == conversation_id

    mismatched = client.post("/api/v1/workflows/plans", headers={"Idempotency-Key": "wf-plan-chat-mismatch"},
                             json={"plan": {**simple_plan, "name": "other-chat-plan"},
                                   "bot": other["name"], "conversation_id": conversation_id})
    assert mismatched.status_code == 422
    missing = client.post("/api/v1/workflows/plans", headers={"Idempotency-Key": "wf-plan-chat-missing"},
                          json={"plan": {**simple_plan, "name": "missing-chat-plan"},
                                "bot": bot["name"], "conversation_id": "missing-conversation"})
    assert missing.status_code == 404


@pytest.mark.parametrize(
    ("value", "encoded", "site_id"),
    [(False, "false", "value-false"), (0, "0", "value-zero"),
     ([], "[]", "value-array"), (None, "null", "value-null"), ("", '""', "value-empty")],
)
def test_run_detail_preserves_scalar_array_null_and_falsy_node_values(client, value, encoded, site_id):
    bot = make_bot(client, name="wf-lossless-api-bot")
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": plan(), "bot": bot["name"],
                                  "definition_name": "lossless-values"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    store = client.app.state.store
    with store._tx() as db:
        db.execute("""INSERT INTO workflow_nodes
                      (workflow_run_id, site_id, instance_key, kind, status, result_json, error_json)
                      VALUES (?, ?, 'once', 'transform', 'succeeded', ?, ?)""",
                   (workflow_id, site_id, encoded, encoded))

    detail = client.get(f"/api/v1/workflows/runs/{workflow_id}")
    assert detail.status_code == 200, detail.text
    node = next(row for row in detail.json()["nodes"] if row["site_id"] == site_id)
    assert node["result"] == value
    assert node["error"] == value


def test_commands_require_an_idempotency_key(client):
    bot = make_bot(client)
    res = client.post("/api/v1/workflows/validate", json={"plan": plan(), "bot": bot["name"]})
    assert res.status_code == 428


def test_unknown_bot_and_unknown_workflow_are_404(client):
    res = client.post("/api/v1/workflows/validate", json={"plan": plan(), "bot": "nope"}, headers=KEY)
    assert res.status_code == 404
    assert client.get("/api/v1/workflows/nope").status_code == 404
    assert client.get("/api/v1/workflows/runs/wrun_missing").status_code == 404


def test_question_answering_is_bound_to_its_own_id(client):
    bot = make_bot(client)
    ask_plan = {
        "name": "api-ask",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [{"kind": "ask", "id": "confirm", "question": "Ship it?", "options": ["yes", "no"],
                   "timeout_seconds": 300}],
    }
    res = client.post("/api/v1/workflows/plans", headers=KEY,
                      json={"plan": ask_plan, "bot": bot["name"], "definition_name": "api-ask"})
    assert res.status_code == 201, res.text
    wf_id = res.json()["workflow_run_id"]
    deadline = time.monotonic() + 15
    question = None
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/workflows/runs/{wf_id}").json()
        if detail["questions"]:
            question = detail["questions"][0]
            break
        time.sleep(0.1)
    assert question is not None and question["status"] == "pending"
    answered = client.post(f"/api/v1/workflows/questions/{question['id']}/answer", headers=KEY,
                           json={"answer": "yes"})
    assert answered.status_code == 200 and answered.json()["status"] == "answered"
    # A second, different answer is refused; the record stays the first answer.
    again = client.post(f"/api/v1/workflows/questions/{question['id']}/answer", headers=KEY,
                        json={"answer": "no"})
    assert again.status_code == 200 and again.json()["answer"] == "yes"
    assert client.post("/api/v1/workflows/questions/wq_missing/answer", headers=KEY,
                       json={"answer": "yes"}).status_code == 404


def test_pause_holds_an_answered_wait_and_resume_continues_the_same_workflow(client):
    bot = make_bot(client, name="wf-pause-resume-bot")
    ask_plan = {
        "name": "pause-resume-contract",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 8, "max_model_calls": 0},
        "nodes": [
            {"kind": "ask", "id": "confirm", "question": "Which result should continue?",
             "options": ["verified", "all"], "timeout_seconds": 300},
            {"kind": "transform", "id": "carry_answer", "op": "constant",
             "args": {"value": {"ref": "confirm.answer"}}},
        ],
    }
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": ask_plan, "bot": bot["name"],
                                  "definition_name": "pause-resume-contract"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    deadline = time.monotonic() + 15
    detail = None
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if (detail["questions"] and detail["questions"][0]["status"] == "pending"
                and detail["workflow"]["status"] == "waiting"
                and detail["attempt"]["status"] == "waiting_workflow"):
            break
        time.sleep(0.05)
    assert detail is not None and detail["pause_available"] is True, detail
    workflow = detail["workflow"]
    attempt_id = workflow["attempt_run_id"]
    pause_body = {"expected_revision_id": workflow["revision_id"],
                  "expected_generation": attempt_id}
    pause_url = f"/api/v1/workflows/runs/{workflow_id}/pause"
    pause_headers = {"Idempotency-Key": "wf-pause-once"}
    assert client.post(pause_url, headers={"Idempotency-Key": "wf-pause-stale-revision"},
                       json={**pause_body, "expected_revision_id": "stale-revision"}).status_code == 409
    assert client.post(pause_url, headers={"Idempotency-Key": "wf-pause-stale-generation"},
                       json={**pause_body, "expected_generation": "stale-generation"}).status_code == 409
    store = client.app.state.store
    child_id = "run_pause_active_child"
    with store._tx() as db:
        db.execute("INSERT INTO runs (id, bot_id, doc, status, created_at, parent_run_id, kind) "
                   "VALUES (?, ?, '{}', 'queued', ?, ?, 'step')",
                   (child_id, bot["id"], "2026-10-11T00:00:00+00:00", attempt_id))
    deferred = client.post(pause_url, headers=pause_headers, json=pause_body)
    assert deferred.status_code == 200, deferred.text
    assert deferred.json()["paused"] is True and deferred.json()["parked"] is False
    with store._lock:
        child = store._db.execute("SELECT status, cancel_requested FROM runs WHERE id = ?", (child_id,)).fetchone()
    assert child["status"] == "queued" and child["cancel_requested"] == 0
    with store._tx() as db:
        db.execute("UPDATE runs SET status='failed' WHERE id=?", (child_id,))
    paused = deferred
    assert paused.json() == {"workflow_run_id": workflow_id, "revision_id": workflow["revision_id"],
                             "attempt_run_id": attempt_id, "status": "waiting", "paused": True,
                             "parked": False}
    assert client.post(pause_url, headers=pause_headers, json=pause_body).json() == paused.json()

    paused_detail = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
    assert paused_detail["workflow"]["pause_requested"] is True
    assert paused_detail["pause_available"] is False and paused_detail["resume_available"] is True
    question = paused_detail["questions"][0]
    answer = client.post(f"/api/v1/workflows/questions/{question['id']}/answer", headers=KEY,
                         json={"answer": "verified"})
    assert answer.status_code == 200 and answer.json()["status"] == "answered"

    # Keep the engine awake past its recovery interval: the durable pause still blocks admission.
    time.sleep(2.25)
    held = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
    assert held["workflow"]["pause_requested"] is True
    assert held["workflow"]["attempt_run_id"] == attempt_id
    assert held["attempt"]["status"] == "waiting_workflow"
    assert {node["site_id"] for node in held["nodes"]} == set()

    resume_url = f"/api/v1/workflows/runs/{workflow_id}/resume"
    resumed = client.post(resume_url, headers={"Idempotency-Key": "wf-resume-once"}, json=pause_body)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["paused"] is False
    assert client.post(resume_url, headers={"Idempotency-Key": "wf-resume-once"}, json=pause_body).json() == resumed.json()
    reused_key = client.post(pause_url, headers={"Idempotency-Key": "wf-resume-once"}, json=pause_body)
    assert reused_key.status_code == 409

    deadline = time.monotonic() + 20
    finished = None
    while time.monotonic() < deadline:
        finished = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if finished["workflow"]["status"] in ("succeeded", "failed", "stopped", "outcome_unknown"):
            break
        time.sleep(0.05)
    assert finished is not None and finished["workflow"]["status"] == "succeeded", finished
    assert finished["workflow"]["pause_requested"] is False
    assert finished["workflow"]["attempt_run_id"] != attempt_id
    assert {node["site_id"] for node in finished["nodes"]} == {"carry_answer"}
    assert next(item for item in finished["questions"] if item["id"] == question["id"])["status"] == "answered"
    assert next(node for node in finished["nodes"] if node["site_id"] == "carry_answer")["result"] == "verified"

    stop_plan = {**ask_plan, "name": "stop-clears-pause", "nodes": ask_plan["nodes"][:1]}
    stop_submission = client.post("/api/v1/workflows/plans", headers={"Idempotency-Key": "wf-pause-stop-submit"},
                                  json={"plan": stop_plan, "bot": bot["name"],
                                        "definition_name": "stop-clears-pause"})
    assert stop_submission.status_code == 201, stop_submission.text
    stop_workflow_id = stop_submission.json()["workflow_run_id"]
    deadline = time.monotonic() + 15
    parked = None
    while time.monotonic() < deadline:
        parked = client.get(f"/api/v1/workflows/runs/{stop_workflow_id}").json()
        if parked["pause_available"]:
            break
        time.sleep(0.05)
    assert parked and parked["pause_available"] is True
    stop_body = {"expected_revision_id": parked["workflow"]["revision_id"],
                 "expected_generation": parked["workflow"]["attempt_run_id"]}
    pause_for_stop = client.post(f"/api/v1/workflows/runs/{stop_workflow_id}/pause",
                                 headers={"Idempotency-Key": "wf-pause-before-stop"}, json=stop_body)
    assert pause_for_stop.status_code == 200 and pause_for_stop.json()["paused"] is True
    stopped = client.post(f"/api/v1/workflows/runs/{stop_workflow_id}/stop",
                          headers={"Idempotency-Key": "wf-stop-after-pause"},
                          json={"expected_revision_id": stop_body["expected_revision_id"]})
    assert stopped.status_code == 200 and stopped.json()["stop_requested"] is True
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        stopped_detail = client.get(f"/api/v1/workflows/runs/{stop_workflow_id}").json()
        if stopped_detail["workflow"]["status"] == "stopped":
            break
        time.sleep(0.05)
    assert stopped_detail["workflow"]["status"] == "stopped"
    assert stopped_detail["workflow"]["pause_requested"] is False


def test_active_work_pause_waits_for_current_node_before_holding_the_next(client, monkeypatch):
    from hutch.workflow.engine import Interpreter

    entered = threading.Event()
    release = threading.Event()
    original_transform = Interpreter._transform

    def slow_transform(self, node, scope):
        if node.id == "slow":
            entered.set()
            assert release.wait(10), "test did not release the in-flight node"
        return original_transform(self, node, scope)

    monkeypatch.setattr(Interpreter, "_transform", slow_transform)
    bot = make_bot(client, name="wf-active-pause-bot")
    active_plan = {
        "name": "active-pause-boundary",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [
            {"kind": "transform", "id": "slow", "op": "constant", "args": {"value": "settled"}},
            {"kind": "transform", "id": "after", "op": "constant", "args": {"value": {"ref": "slow"}}},
        ],
    }
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": active_plan, "bot": bot["name"],
                                  "definition_name": "active-pause-boundary"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    try:
        assert entered.wait(10), "the first node did not enter its in-flight operation"
        active = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        assert active["workflow"]["status"] == "running", active
        assert active["attempt"]["status"] == "running", active
        assert active["pause_available"] is True
        body = {"expected_revision_id": active["workflow"]["revision_id"],
                "expected_generation": active["workflow"]["attempt_run_id"]}
        pause = client.post(f"/api/v1/workflows/runs/{workflow_id}/pause",
                            headers={"Idempotency-Key": "wf-active-pause"}, json=body)
        assert pause.status_code == 200, pause.text
        assert pause.json()["paused"] is True and pause.json()["parked"] is False
        assert client.get(f"/api/v1/workflows/runs/{workflow_id}").json()["workflow"]["pause_requested"] is True

        release.set()
        deadline = time.monotonic() + 15
        held = None
        while time.monotonic() < deadline:
            held = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
            if held["resume_available"]:
                break
            time.sleep(0.05)
        assert held is not None and held["resume_available"] is True, held
        assert held["workflow"]["status"] == "waiting", held
        assert held["attempt"]["status"] == "waiting_workflow", held
        assert {node["site_id"] for node in held["nodes"]} == {"slow"}
        assert next(node for node in held["nodes"] if node["site_id"] == "slow")["result"] == "settled"

        resumed = client.post(f"/api/v1/workflows/runs/{workflow_id}/resume",
                              headers={"Idempotency-Key": "wf-active-pause-resume"}, json=body)
        assert resumed.status_code == 200 and resumed.json()["paused"] is False
        deadline = time.monotonic() + 15
        finished = None
        while time.monotonic() < deadline:
            finished = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
            if finished["workflow"]["status"] in ("succeeded", "failed", "stopped", "outcome_unknown"):
                break
            time.sleep(0.05)
        assert finished is not None and finished["workflow"]["status"] == "succeeded", finished
        assert {node["site_id"] for node in finished["nodes"]} == {"slow", "after"}
    finally:
        release.set()


def test_recovery_parks_a_lost_active_attempt_when_pause_is_requested(client):
    bot = make_bot(client, name="wf-pause-recovery-bot")
    recovery_plan = {
        "name": "pause-recovery-boundary",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [
            {"kind": "ask", "id": "confirm", "question": "Continue after recovery?",
             "options": ["yes", "no"], "timeout_seconds": 300},
            {"kind": "transform", "id": "after", "op": "constant",
             "args": {"value": {"ref": "confirm.answer"}}},
        ],
    }
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": recovery_plan, "bot": bot["name"],
                                  "definition_name": "pause-recovery-boundary"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    deadline = time.monotonic() + 15
    waiting = None
    while time.monotonic() < deadline:
        waiting = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if waiting["pause_available"]:
            break
        time.sleep(0.05)
    assert waiting and waiting["pause_available"] is True
    old_generation = waiting["workflow"]["attempt_run_id"]
    body = {"expected_revision_id": waiting["workflow"]["revision_id"],
            "expected_generation": old_generation}
    paused = client.post(f"/api/v1/workflows/runs/{workflow_id}/pause",
                         headers={"Idempotency-Key": "wf-pause-recovery"}, json=body)
    assert paused.status_code == 200 and paused.json()["parked"] is True
    question_id = waiting["questions"][0]["id"]
    assert client.post(f"/api/v1/workflows/questions/{question_id}/answer", headers=KEY,
                       json={"answer": "yes"}).status_code == 200

    # Simulate process replacement after a crash: the parked attempt disappeared, while
    # the answered wait and durable pause survive in SQLite. Recovery may establish a new
    # parked attempt, but must not run the downstream node until Resume.
    with client.app.state.store._tx() as db:
        db.execute("UPDATE runs SET status='failed' WHERE id=?", (old_generation,))
        db.execute("UPDATE workflow_runs SET status='running', updated_at=datetime('now','-10 seconds') WHERE id=?",
                   (workflow_id,))

    deadline = time.monotonic() + 20
    held = None
    while time.monotonic() < deadline:
        held = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if held["workflow"]["attempt_run_id"] != old_generation and held["resume_available"]:
            break
        time.sleep(0.05)
    assert held and held["workflow"]["attempt_run_id"] != old_generation, held
    assert held["workflow"]["status"] == "waiting", held
    assert held["attempt"]["status"] == "waiting_workflow", held
    assert {node["site_id"] for node in held["nodes"]} == set()

    resume_body = {"expected_revision_id": held["workflow"]["revision_id"],
                   "expected_generation": held["workflow"]["attempt_run_id"]}
    resumed = client.post(f"/api/v1/workflows/runs/{workflow_id}/resume",
                          headers={"Idempotency-Key": "wf-pause-recovery-resume"}, json=resume_body)
    assert resumed.status_code == 200, resumed.text
    deadline = time.monotonic() + 15
    finished = None
    while time.monotonic() < deadline:
        finished = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if finished["workflow"]["status"] in ("succeeded", "failed", "stopped", "outcome_unknown"):
            break
        time.sleep(0.05)
    assert finished is not None and finished["workflow"]["status"] == "succeeded", finished
    assert {node["site_id"] for node in finished["nodes"]} == {"after"}


def test_stop_is_durable_and_idempotent(client):
    bot = make_bot(client)
    res = client.post("/api/v1/workflows/plans", headers=KEY,
                      json={"plan": plan(), "bot": bot["name"], "definition_name": "api-stop"})
    wf_id = res.json()["workflow_run_id"]
    revision_id = client.get(f"/api/v1/workflows/runs/{wf_id}").json()["workflow"]["revision_id"]
    url = f"/api/v1/workflows/runs/{wf_id}/stop"
    stale = client.post(url, headers={"Idempotency-Key": "wf-stale-stop"},
                        json={"expected_revision_id": "stale-revision"})
    assert stale.status_code == 409
    body = {"expected_revision_id": revision_id}
    stopped = client.post(url, headers=KEY, json=body)
    assert stopped.status_code == 200 and stopped.json()["stop_requested"] is True
    again = client.post(url, headers=KEY, json=body)
    assert again.status_code == 200
    assert client.post("/api/v1/workflows/runs/wrun_missing/stop", headers=KEY,
                       json=body).status_code == 404


def _amendment_plan() -> dict:
    return {
        "name": "amendment-preview",
        "inputs": {"seed": {"type": "string", "default": "original"}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 20, "max_model_calls": 0},
        "nodes": [
            {"kind": "transform", "id": "source", "op": "constant",
             "args": {"value": {"ref": "input.seed"}}},
            {"kind": "transform", "id": "derived", "op": "to_json",
             "args": {"value": {"ref": "source"}}},
            {"kind": "transform", "id": "independent", "op": "constant",
             "args": {"value": 42}},
        ],
    }


def _wait_for_workflow(client, workflow_id: str) -> dict:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if detail["workflow"]["status"] in ("succeeded", "failed", "stopped"):
            return detail
        time.sleep(0.05)
    raise AssertionError(f"workflow {workflow_id} did not settle")


def test_amendment_preview_shows_dependency_invalidation_and_safe_reuse_without_mutation(client):
    bot = make_bot(client, name="amendment-preview-bot")
    base_plan = _amendment_plan()
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": base_plan, "bot": bot["name"],
                                  "definition_name": "amendment-preview"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    detail = _wait_for_workflow(client, workflow_id)
    assert detail["workflow"]["status"] == "succeeded", detail
    before_runs = client.get("/api/v1/workflows/runs").json()["items"]
    before_revisions = client.get("/api/v1/workflows/amendment-preview").json()["revision"]

    candidate = _amendment_plan()
    candidate["nodes"][0]["args"]["value"] = "revised source"
    preview = client.post(f"/api/v1/workflows/runs/{workflow_id}/amendments/preview", json={
        "expected_revision_id": detail["workflow"]["revision_id"],
        "expected_generation": detail["workflow"]["attempt_run_id"],
        "plan": candidate,
    })
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["eligible"] is True
    assert body["plan_changed"] is True
    assert body["changed_sites"] == ["source"]
    assert body["added_sites"] == body["removed_sites"] == []
    assert {row["site_id"] for row in body["reuse"]} == {"independent"}
    assert {row["site_id"] for row in body["invalidate"]} == {"source", "derived"}
    assert body["quiescence"]["required"] is False
    source_diff = next(row for row in body["nodes"] if row["site_id"] == "source")
    assert source_diff["change"] == "changed"
    assert source_diff["fields"] == [{"field": "args", "old": {"value": {"ref": "input.seed"}},
                                       "new": {"value": "revised source"}}]

    after_runs = client.get("/api/v1/workflows/runs").json()["items"]
    assert [item["revision_id"] for item in after_runs] == [item["revision_id"] for item in before_runs]
    assert client.get("/api/v1/workflows/amendment-preview").json()["revision"] == before_revisions
    assert client.get(f"/api/v1/workflows/runs/{workflow_id}").json()["workflow"]["revision_id"] == detail["workflow"]["revision_id"]


def test_terminal_workflow_amendment_refusal_is_explicit_and_preserves_result(client):
    bot = make_bot(client, name="terminal-amendment-bot")
    original = _amendment_plan()
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": original, "bot": bot["name"],
                                  "definition_name": "terminal-amendment"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    finished = _wait_for_workflow(client, workflow_id)
    assert finished["workflow"]["status"] == "succeeded", finished
    before = finished["workflow"]

    candidate = _amendment_plan()
    candidate["nodes"][0]["args"]["value"] = "a revised source"
    preview = client.post(f"/api/v1/workflows/runs/{workflow_id}/amendments/preview", json={
        "expected_revision_id": before["revision_id"],
        "expected_generation": before["attempt_run_id"],
        "plan": candidate,
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["eligible"] is True  # Plan authority/budget is distinct from adoption support.
    assert preview.json()["quiescence"]["workflow_status"] == "succeeded"

    response = client.post(
        f"/api/v1/workflows/runs/{workflow_id}/amendments/adopt",
        headers={"Idempotency-Key": "terminal-amendment-refused"},
        json={"expected_revision_id": before["revision_id"],
              "expected_generation": before["attempt_run_id"], "plan": candidate},
    )
    assert response.status_code == 409, response.text
    assert "terminal workflow amendments are unsupported" in response.json()["detail"]["message"]

    after = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
    assert after["workflow"]["status"] == "succeeded"
    assert after["workflow"]["revision_id"] == before["revision_id"]
    assert after["workflow"]["attempt_run_id"] == before["attempt_run_id"]
    assert after["workflow"]["result"] == before["result"]
    assert client.get(f"/api/v1/workflows/runs/{workflow_id}/amendments").json()["items"] == []


def test_amendment_preview_fences_stale_revision_and_generation_and_invalidates_changed_inputs(client):
    bot = make_bot(client, name="amendment-fence-bot")
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": _amendment_plan(), "bot": bot["name"],
                                  "definition_name": "amendment-fence", "inputs": {"seed": "original"}})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    detail = _wait_for_workflow(client, workflow_id)
    current = detail["workflow"]
    url = f"/api/v1/workflows/runs/{workflow_id}/amendments/preview"

    stale_revision = client.post(url, json={
        "expected_revision_id": "stale-revision", "expected_generation": current["attempt_run_id"],
        "plan": _amendment_plan(),
    })
    assert stale_revision.status_code == 409
    stale_generation = client.post(url, json={
        "expected_revision_id": current["revision_id"], "expected_generation": "stale-generation",
        "plan": _amendment_plan(),
    })
    assert stale_generation.status_code == 409

    changed_inputs = client.post(url, json={
        "expected_revision_id": current["revision_id"], "expected_generation": current["attempt_run_id"],
        "plan": _amendment_plan(), "inputs": {"seed": "changed input"},
    })
    assert changed_inputs.status_code == 200, changed_inputs.text
    result = changed_inputs.json()
    assert result["plan_changed"] is False
    assert result["candidate_inputs"] == {"seed": "changed input"}
    assert {row["reason"] for row in result["invalidate"]} == {"inputs_changed"}
    assert result["reuse"] == []


def test_amendment_preview_refreshes_authority_and_refuses_budget_widening(client):
    bot = make_bot(client, name="amendment-authority-bot")
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": _amendment_plan(), "bot": bot["name"],
                                  "definition_name": "amendment-authority"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    detail = _wait_for_workflow(client, workflow_id)
    current = detail["workflow"]
    url = f"/api/v1/workflows/runs/{workflow_id}/amendments/preview"

    broader = _amendment_plan()
    broader["envelope"]["tools"] = ["shell"]
    authority = client.post(url, json={
        "expected_revision_id": current["revision_id"], "expected_generation": current["attempt_run_id"],
        "plan": broader,
    })
    assert authority.status_code == 200, authority.text
    assert authority.json()["eligible"] is False
    assert "tools the Bot does not allow" in authority.json()["blocked_reasons"][0]

    wider_budget = _amendment_plan()
    wider_budget["budget"]["max_nodes"] = 30
    budget = client.post(url, json={
        "expected_revision_id": current["revision_id"], "expected_generation": current["attempt_run_id"],
        "plan": wider_budget,
    })
    assert budget.status_code == 200, budget.text
    assert budget.json()["eligible"] is False
    assert budget.json()["budgets"]["max_nodes"]["effective_if_adopted"] == 20
    assert any("cannot increase the root max_nodes allowance" in reason
               for reason in budget.json()["blocked_reasons"])


def test_amendment_preview_includes_pending_question_id_and_requires_quiescence(client):
    bot = make_bot(client, name="amendment-pending-question-bot")
    ask_plan = {
        "name": "amendment-pending-question",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [
            {"kind": "ask", "id": "confirm_first", "question": "Ready to publish?",
             "options": ["yes", "no"], "timeout_seconds": 300},
        ],
    }
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": ask_plan, "bot": bot["name"],
                                  "definition_name": "amendment-pending-question"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]

    deadline = time.monotonic() + 15
    detail = None
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if any(question["status"] == "pending" for question in detail["questions"]):
            break
        time.sleep(0.1)
    assert detail is not None
    pending = [question for question in detail["questions"] if question["status"] == "pending"]
    assert len(pending) == 1, detail

    preview = client.post(f"/api/v1/workflows/runs/{workflow_id}/amendments/preview", json={
        "expected_revision_id": detail["workflow"]["revision_id"],
        "expected_generation": detail["workflow"]["attempt_run_id"],
        "plan": ask_plan,
    })
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["eligible"] is True  # Authority/budget eligibility is separate from adoption readiness.
    assert body["quiescence"]["required"] is True
    assert body["quiescence"]["attempt_status"] == "waiting_workflow"
    assert body["quiescence"]["attempt_parked"] is True
    assert body["quiescence"]["owned_work_quiet"] is True
    assert set(body["quiescence"]["pending_question_ids"]) == {question["id"] for question in pending}
    assert all(row["reason"] == "not_settled" for row in body["invalidate"])


def test_amendment_preview_does_not_reuse_results_derived_from_effects_or_evidence(client):
    bot = make_bot(client, name="amendment-effect-dependency-bot")
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": plan(), "bot": bot["name"],
                                  "definition_name": "amendment-effect-dependency"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    detail = _wait_for_workflow(client, workflow_id)
    assert detail["workflow"]["status"] == "succeeded", detail

    preview = client.post(f"/api/v1/workflows/runs/{workflow_id}/amendments/preview", json={
        "expected_revision_id": detail["workflow"]["revision_id"],
        "expected_generation": detail["workflow"]["attempt_run_id"],
        "plan": plan(),
    })
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["reuse"] == []
    assert {row["site_id"] for row in body["invalidate"]} == {"scan", "count", "report", "check"}
    assert next(row for row in body["invalidate"] if row["site_id"] == "count")["reason"] == \
        "dependency_result_not_reusable"


def test_amendment_adoption_archives_and_cancels_old_question_then_continues(client, monkeypatch):
    from hutch.workflow import persistence as workflow_store

    bot = make_bot(client, name="amendment-adoption-bot")
    old_plan = {
        "name": "amendment-adoption",
        "inputs": {"seed": {"type": "string", "default": "stable"}},
        "envelope": {"tools": []},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [
            {"kind": "transform", "id": "stable", "op": "constant",
             "args": {"value": {"ref": "input.seed"}}},
            {"kind": "ask", "id": "confirm", "question": "Use the original method?",
             "options": ["yes", "no"], "timeout_seconds": 300},
        ],
    }
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": old_plan, "bot": bot["name"],
                                  "definition_name": "amendment-adoption"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]

    deadline = time.monotonic() + 15
    detail = None
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if any(question["status"] == "pending" for question in detail["questions"]):
            break
        time.sleep(0.1)
    assert detail is not None
    old_question = next(question for question in detail["questions"] if question["status"] == "pending")
    old_workflow = detail["workflow"]
    pause_body = {"expected_revision_id": old_workflow["revision_id"],
                  "expected_generation": old_workflow["attempt_run_id"]}
    paused = client.post(f"/api/v1/workflows/runs/{workflow_id}/pause",
                         headers={"Idempotency-Key": "adoption-pause-before-review"}, json=pause_body)
    assert paused.status_code == 200 and paused.json()["parked"] is True
    candidate = json.loads(json.dumps(old_plan))
    candidate["nodes"][1]["question"] = "Use the revised method?"
    body = {"expected_revision_id": old_workflow["revision_id"],
            "expected_generation": old_workflow["attempt_run_id"], "plan": candidate}
    url = f"/api/v1/workflows/runs/{workflow_id}/amendments/adopt"

    refused = client.post(url, headers={"Idempotency-Key": "adoption-requires-question-choice"}, json=body)
    assert refused.status_code == 409, refused.text
    assert "cancel_pending_questions=true" in refused.json()["detail"]["message"]

    confirmed_body = {**body, "cancel_pending_questions": True}
    with monkeypatch.context() as patch:
        patch.setattr(workflow_store, "MAX_AMENDMENT_SNAPSHOT_BYTES", 1)
        oversized = client.post(url, headers={"Idempotency-Key": "adoption-snapshot-limit"},
                                json=confirmed_body)
        assert oversized.status_code == 413, oversized.text
        unchanged = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        assert unchanged["workflow"]["revision_id"] == old_workflow["revision_id"]
        assert any(question["id"] == old_question["id"] and question["status"] == "pending"
                   for question in unchanged["questions"])

    adopted = client.post(url, headers={"Idempotency-Key": "adoption-cancel-old-question"},
                          json=confirmed_body)
    assert adopted.status_code == 200, adopted.text
    result = adopted.json()
    assert result["previous_revision_id"] == old_workflow["revision_id"]
    assert result["revision_id"] != old_workflow["revision_id"]
    assert result["attempt_run_id"] == old_workflow["attempt_run_id"]
    assert result["cancelled_question_ids"] == [old_question["id"]]
    assert [row["site_id"] for row in result["preview"]["reuse"]] == ["stable"]
    adopted_detail = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
    assert adopted_detail["workflow"]["pause_requested"] is False

    from hutch.lifecycle import LeaseLost
    stale_run = client.app.state.store.get_run(old_workflow["attempt_run_id"])
    with pytest.raises(LeaseLost):
        workflow_store.settle_node(
            client.app.state.store, workflow_id, "stable", "once",
            owner_run_id=stale_run.id, owner_fence=stale_run.fence,
            revision_id=old_workflow["revision_id"], status="succeeded", result="stable")

    replay = client.post(url, headers={"Idempotency-Key": "adoption-cancel-old-question"}, json=confirmed_body)
    assert replay.status_code == 200 and replay.json() == result
    stale = client.post(url, headers={"Idempotency-Key": "adoption-old-generation"}, json=body)
    assert stale.status_code == 409
    assert client.get(f"/api/v1/workflows/runs/{workflow_id}/amendments").json()["items"][0]["id"] == result["history_id"]

    history = client.get(f"/api/v1/workflows/runs/{workflow_id}/amendments/{result['history_id']}")
    assert history.status_code == 200, history.text
    archived_question = next(question for question in history.json()["questions"]
                             if question["id"] == old_question["id"])
    assert archived_question["status"] == "cancelled"
    archived_node = next(node for node in history.json()["nodes"] if node["site_id"] == "stable")
    assert archived_node["result"] == "stable"
    assert client.post(f"/api/v1/workflows/questions/{old_question['id']}/answer", headers=KEY,
                       json={"answer": "yes"}).status_code == 404

    deadline = time.monotonic() + 15
    continued = None
    while time.monotonic() < deadline:
        continued = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if any(question["question"] == "Use the revised method?"
               and question["status"] == "pending" for question in continued["questions"]):
            break
        time.sleep(0.1)
    assert continued is not None
    new_question = next(question for question in continued["questions"]
                        if question["question"] == "Use the revised method?"
                        and question["status"] == "pending")
    assert new_question["id"] != old_question["id"]
    assert continued["workflow"]["attempt_run_id"] != old_workflow["attempt_run_id"]
    assert continued["plan"]["nodes"][1]["question"] == "Use the revised method?"


def test_amendment_adoption_refuses_active_child_without_cancelling_question(client):
    bot = make_bot(client, name="amendment-active-child-bot")
    ask_plan = {
        "name": "amendment-active-child",
        "envelope": {"tools": []},
        "budget": {"max_nodes": 5, "max_model_calls": 0},
        "nodes": [{"kind": "ask", "id": "confirm", "question": "Continue?",
                   "options": ["yes", "no"], "timeout_seconds": 300}],
    }
    submitted = client.post("/api/v1/workflows/plans", headers=KEY,
                            json={"plan": ask_plan, "bot": bot["name"],
                                  "definition_name": "amendment-active-child"})
    assert submitted.status_code == 201, submitted.text
    workflow_id = submitted.json()["workflow_run_id"]
    deadline = time.monotonic() + 15
    detail = None
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
        if any(question["status"] == "pending" for question in detail["questions"]):
            break
        time.sleep(0.1)
    assert detail is not None
    old_question = next(question for question in detail["questions"] if question["status"] == "pending")
    current = detail["workflow"]
    candidate = json.loads(json.dumps(ask_plan))
    candidate["nodes"][0]["question"] = "Continue with the revised method?"

    store = client.app.state.store
    fake_child_id = "run_amendment_active_child_fixture"
    fake_task_id = "task_amendment_active_child_fixture"
    with store._tx() as db:
        db.execute("""INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done)
                      VALUES (?, ?, 'step', 'active child fixture', ?, 0)""",
                   (fake_task_id, bot["id"], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        db.execute("""INSERT INTO runs (id, bot_id, task_id, doc, status, created_at,
                                          parent_run_id, kind)
                      VALUES (?, ?, ?, '{}', 'running', ?, ?, 'step')""",
                   (fake_child_id, bot["id"], fake_task_id,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), current["attempt_run_id"]))

    preview = client.post(
        f"/api/v1/workflows/runs/{workflow_id}/amendments/preview",
        json={"expected_revision_id": current["revision_id"],
              "expected_generation": current["attempt_run_id"], "plan": candidate},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["quiescence"]["attempt_parked"] is True
    assert preview.json()["quiescence"]["owned_work_quiet"] is False

    response = client.post(
        f"/api/v1/workflows/runs/{workflow_id}/amendments/adopt",
        headers={"Idempotency-Key": "adoption-refuses-live-child"},
        json={"expected_revision_id": current["revision_id"],
              "expected_generation": current["attempt_run_id"], "plan": candidate,
              "cancel_pending_questions": True},
    )
    assert response.status_code == 409, response.text
    assert "child work or an owned process is active" in response.json()["detail"]["message"]
    after = client.get(f"/api/v1/workflows/runs/{workflow_id}").json()
    assert after["workflow"]["revision_id"] == current["revision_id"]
    assert any(question["id"] == old_question["id"] and question["status"] == "pending"
               for question in after["questions"])
    assert client.get(f"/api/v1/workflows/runs/{workflow_id}/amendments").json()["items"] == []

    with store._tx() as db:
        db.execute("DELETE FROM runs WHERE id = ?", (fake_child_id,))
        db.execute("DELETE FROM tasks WHERE id = ?", (fake_task_id,))
    client.post(f"/api/v1/workflows/runs/{workflow_id}/stop",
                headers={"Idempotency-Key": "cleanup-amendment-active-child-fixture"},
                json={"expected_revision_id": current["revision_id"]})


def test_qualification_routes_are_scoped_and_revocable(client):
    bot = make_bot(client, name="wf-real-route", model="ollama/qwen3:4b")
    assessed = client.get("/api/v1/workflows/qualifications/assess",
                          params={"bot": bot["name"], "role": "author"})
    assert assessed.status_code == 200 and assessed.json()["allowed"] is False
    ack = client.post("/api/v1/workflows/qualifications", headers=KEY,
                      json={"bot": bot["name"], "role": "worker",
                            "reason": "local extraction only", "scope": {"tools": False}})
    assert ack.status_code == 201 and ack.json()["state"] == "limited"
    listed = client.get("/api/v1/workflows/qualifications").json()["items"]
    assert listed and listed[0]["role"] == "worker" and listed[0]["source"] == "operator"
    removed = client.delete("/api/v1/workflows/qualifications",
                            params={"bot": bot["name"], "role": "worker"}, headers=KEY)
    assert removed.json()["removed"] == 1
    assert client.get("/api/v1/workflows/qualifications").json()["items"] == []
    # Authoring can never be unlocked by an acknowledgement.
    bad = client.post("/api/v1/workflows/qualifications", headers=KEY,
                      json={"bot": bot["name"], "role": "author", "reason": "trust me"})
    assert bad.status_code == 422


def test_workflow_policy_route_saves_mode_and_scope(client):
    bot = make_bot(client, name="policy-bot")
    before = client.get("/api/v1/workflows/policy", params={"bot": "policy-bot"}).json()
    assert before["mode"] == "suggest" and before["limits"] == {}

    definition = client.post("/api/v1/workflows", headers={"Idempotency-Key": "save-auto-definition"},
                             json={"name": "expense-audit", "plan": plan(), "activate": True})
    assert definition.status_code == 201, definition.text

    saved = client.post("/api/v1/workflows/policy", headers=KEY,
                        json={"bot": "policy-bot", "mode": "auto", "definitions": ["expense-audit"],
                              "max_nodes": 40, "max_model_calls": 12, "max_tokens": 32000,
                              "max_wall_seconds": 900, "max_fanout": 8})
    assert saved.status_code == 200, saved.text
    assert saved.json()["mode"] == "auto"
    assert saved.json()["limits"]["definitions"] == ["expense-audit"]
    after = client.get("/api/v1/workflows/policy", params={"bot": "policy-bot"}).json()
    assert after["mode"] == "auto" and after["limits"]["max_nodes"] == 40
    assert after["limits"]["max_tokens"] == 32000

    conversation = client.post("/api/v1/conversations", headers={"Idempotency-Key": "create-auto-chat"},
                               json={"bot": bot["name"], "title": "Auto scope"})
    assert conversation.status_code == 201
    url = f"/api/v1/workflows/conversations/{conversation.json()['id']}/policy"
    view = client.get(url).json()
    assert view["mode"] == "auto" and view["auto_available"] is True
    scoped = client.post(url, headers={"Idempotency-Key": "enable-chat-auto"},
                         json={"mode": "auto", "expected_revision": 0})
    assert scoped.status_code == 200 and scoped.json()["mode"] == "auto"

    # Switching back to off clears the auto scope rather than leaving it armed.
    client.post("/api/v1/workflows/policy", headers=KEY,
                json={"bot": "policy-bot", "mode": "off", "definitions": ["expense-audit"]})
    assert client.get("/api/v1/workflows/policy", params={"bot": "policy-bot"}).json()["limits"] == {}
    assert client.post("/api/v1/workflows/policy", headers=KEY,
                       json={"bot": "policy-bot", "mode": "sometimes"}).status_code == 422


def test_conversation_workflow_policy_is_revisioned_and_defaults_to_suggest(client):
    bot = make_bot(client, name="conversation-policy-bot")
    created = client.post("/api/v1/conversations", headers={"Idempotency-Key": "create-policy-chat"},
                          json={"bot": bot["name"], "title": "A policy chat"})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    url = f"/api/v1/workflows/conversations/{conversation_id}/policy"

    initial = client.get(url)
    assert initial.status_code == 200, initial.text
    assert initial.json()["mode"] == "suggest"
    assert initial.json()["override"] == "inherit"
    assert initial.json()["revision"] == 0
    assert initial.json()["auto_available"] is False

    saved = client.post(url, headers={"Idempotency-Key": "policy-off"},
                        json={"mode": "off", "expected_revision": 0})
    assert saved.status_code == 200, saved.text
    assert saved.json()["mode"] == "off" and saved.json()["revision"] == 1
    replay = client.post(url, headers={"Idempotency-Key": "policy-off"},
                         json={"mode": "off", "expected_revision": 0})
    assert replay.status_code == 200 and replay.json()["revision"] == 1
    stale = client.post(url, headers={"Idempotency-Key": "policy-stale"},
                        json={"mode": "suggest", "expected_revision": 0})
    assert stale.status_code == 409
    inherited = client.post(url, headers={"Idempotency-Key": "policy-inherit"},
                            json={"mode": "inherit", "expected_revision": 1})
    assert inherited.status_code == 200
    assert inherited.json()["mode"] == "suggest" and inherited.json()["revision"] == 2
    replay_after_change = client.post(url, headers={"Idempotency-Key": "policy-off"},
                                      json={"mode": "off", "expected_revision": 0})
    assert replay_after_change.status_code == 200
    assert replay_after_change.json()["mode"] == "off" and replay_after_change.json()["revision"] == 1
    blocked_auto = client.post(url, headers={"Idempotency-Key": "policy-auto-unscoped"},
                              json={"mode": "auto", "expected_revision": 2})
    assert blocked_auto.status_code == 409


def test_oversized_plans_are_refused(client):
    bot = make_bot(client)
    big = plan()
    big["description"] = "x" * 600_000
    res = client.post("/api/v1/workflows/validate", json={"plan": big, "bot": bot["name"]}, headers=KEY)
    assert res.status_code == 413


def test_qualification_probe_api_is_idempotent_and_uses_the_bounded_local_runner(client, monkeypatch):
    monkeypatch.setattr(probe_module, "probe_hardware",
                        lambda with_runtimes=False: Hardware(ram_total_gb=24, ram_available_gb=12))
    model = "qwen3:1.7b-q4_K_M"
    server = FakeOllama(models={model: {"params": "1.7B", "quant": "Q4_K_M",
                                        "caps": ["completion", "tools"]}})
    server.version = "0.40.3"
    from tests.test_workflow_probes import _case_id, _reply

    server.script = lambda body: {"content": _reply(_case_id(body))}
    monkeypatch.setattr(providers, "make_provider", lambda _provider, _endpoint=None:
                        __import__("hutch.providers.ollama", fromlist=["OllamaProvider"]).OllamaProvider(server.url))
    try:
        bot = make_bot(client, "wf-probe-bot", model=f"ollama/{model}", base_url=server.url)
        payload = {"bot": bot["name"], "role": "selector", "campaign_id": "api-probe-test"}
        response = client.post("/api/v1/workflows/qualifications/probe", json=payload, headers=KEY)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "passed" and len(body["requests"]) == 4
        assert len(server.of("/api/chat")) == 4
        replay = client.post("/api/v1/workflows/qualifications/probe", json=payload, headers=KEY)
        assert replay.status_code == 200 and replay.json()["id"] == body["id"]
        assert replay.json()["status"] == "passed" and len(server.of("/api/chat")) == 4
        detail = client.get(f"/api/v1/workflows/qualifications/probes/{body['id']}")
        assert detail.status_code == 200 and detail.json()["status"] == "passed"
    finally:
        server.close()
