"""Schedule policy sidecar: CAS, validation, cleanup and the workflow limit."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Schedule
from hutch.schedule_conditions import ConditionError
from hutch.schedule_policy import PolicyUnsupported, all_policies, get_policy, put_policy
from hutch.server.app import create_app
from hutch.store import RevisionConflict


def _bot(store, name: str = "policy-bot", **schedule_fields) -> Bot:
    fields = {"name": "Nightly", "cron": "0 3 * * *", "timezone": "UTC", "prompt": "Check releases."}
    fields.update(schedule_fields)
    return store.create_bot(Bot(name=name, display_name=name.title(), tools=[],
                                schedule=Schedule(**fields)))


def test_policy_round_trip_and_compare_and_swap(store):
    bot = _bot(store)
    first = put_policy(store, bot.id, bot.schedule.id, approval_required=True, conditions=[])
    assert first.revision == 1 and first.approval_required is True
    assert get_policy(store, bot.id, bot.schedule.id).approval_required is True

    second = put_policy(store, bot.id, bot.schedule.id, approval_required=False,
                        conditions=[{"field": "schedule_timezone", "op": "eq", "value": "UTC"}],
                        expected_revision=1)
    assert second.revision == 2 and second.approval_required is False
    assert second.conditions == [{"field": "schedule_timezone", "op": "eq", "value": "UTC"}]

    with pytest.raises(RevisionConflict, match="current 2"):
        put_policy(store, bot.id, bot.schedule.id, approval_required=True, conditions=[],
                   expected_revision=1)


def test_policy_rejects_invalid_conditions(store):
    bot = _bot(store)
    with pytest.raises(ConditionError, match="unknown condition field"):
        put_policy(store, bot.id, bot.schedule.id, approval_required=False,
                   conditions=[{"field": "prompt", "op": "eq", "value": "secret"}])


def test_policy_rejects_approval_for_a_linked_saved_workflow(store):
    bot = _bot(store, workflow_definition_id="wf-1", workflow_revision_id="rev-1")
    with pytest.raises(PolicyUnsupported, match="step approvals"):
        put_policy(store, bot.id, bot.schedule.id, approval_required=True, conditions=[])
    # Conditions remain available for workflow-linked routines.
    saved = put_policy(store, bot.id, bot.schedule.id, approval_required=False,
                       conditions=[{"field": "schedule_enabled", "op": "eq", "value": True}])
    assert saved.conditions


def test_removing_a_schedule_removes_only_its_policy(store):
    bot = _bot(store)
    second = store.put_schedule(bot.id, Schedule(name="Second", cron="0 4 * * *", timezone="UTC"))
    assert second is not None
    second_id = next(item.id for item in second.schedules if item.name == "Second")
    put_policy(store, bot.id, bot.schedule.id, approval_required=True, conditions=[])
    put_policy(store, bot.id, second_id, approval_required=True, conditions=[])
    store.delete_schedule(bot.id, second_id)
    remaining = store._db.execute(
        "SELECT schedule_id FROM schedule_policies WHERE bot_id = ?", (bot.id,)).fetchall()
    assert [row["schedule_id"] for row in remaining] == [bot.schedule.id]


def test_policy_api_round_trip_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        store = client.app.state.store
        bot = _bot(store, name="policy-api")
        url = f"/api/v1/bots/{bot.name}/schedules/{bot.schedule.id}/policy"

        created = client.put(url, json={"approval_required": True, "conditions": [],
                                        "expected_revision": 0})
        assert created.status_code == 200, created.text
        assert created.json()["revision"] == 1
        assert created.json()["approval_required"] is True

        fetched = client.get(url)
        assert fetched.status_code == 200
        assert fetched.json()["conditions"] == []
        assert str(tmp_path) not in fetched.text

        stale = client.put(url, json={"approval_required": False, "conditions": [],
                                      "expected_revision": 0})
        assert stale.status_code == 409

        invalid = client.put(url, json={"approval_required": False,
                                        "conditions": [{"field": "prompt", "op": "eq", "value": "x"}],
                                        "expected_revision": 1})
        assert invalid.status_code == 422

        bulk = client.get("/api/v1/schedule-policies")
        assert bulk.status_code == 200
        assert bulk.json()[0]["bot_name"] == "policy-api"


def test_policy_api_reports_the_workflow_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        store = client.app.state.store
        bot = _bot(store, name="workflow-policy", workflow_definition_id="wf-1",
                   workflow_revision_id="rev-1")
        response = client.put(
            f"/api/v1/bots/{bot.name}/schedules/{bot.schedule.id}/policy",
            json={"approval_required": True, "conditions": [], "expected_revision": 0},
        )
        assert response.status_code == 422
        assert "step approvals" in response.text


def test_all_policies_include_the_assistant_name(store):
    bot = _bot(store)
    put_policy(store, bot.id, bot.schedule.id, approval_required=True, conditions=[])
    rows = all_policies(store)
    assert rows[0]["bot_name"] == "policy-bot"
