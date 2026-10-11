"""Workflow API contracts: typed resources, idempotency, validation-only dry runs.

The dry-run route must compile and check authority without admitting or executing
anything; the run routes must be idempotent; and every question/approval keeps its own
identity.
"""
from __future__ import annotations

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
