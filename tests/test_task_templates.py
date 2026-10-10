from __future__ import annotations

from fastapi.testclient import TestClient

from hutch.server.app import create_app


def test_saved_task_templates_are_local_revisioned_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/task-templates").json() == []
        assert client.post("/api/v1/task-templates", json={
            "name": "Weekly research", "prompt": "Compare these reports and list open questions."}).status_code == 428

        body = {"name": "Weekly research", "prompt": "Compare these reports and list open questions."}
        headers = {"Idempotency-Key": "template-create-1"}
        created = client.post("/api/v1/task-templates", json=body, headers=headers)
        assert created.status_code == 201, created.text
        template = created.json()
        assert template["name"] == body["name"] and template["prompt"] == body["prompt"]
        assert template["revision"] == 1

        replay = client.post("/api/v1/task-templates", json=body, headers=headers)
        assert replay.status_code == 200 and replay.json()["id"] == template["id"]
        conflict = client.post("/api/v1/task-templates", json={**body, "name": "Different"}, headers=headers)
        assert conflict.status_code == 409

        listed = client.get("/api/v1/task-templates?limit=10")
        assert listed.status_code == 200 and [row["id"] for row in listed.json()] == [template["id"]]
        updated = client.put(f"/api/v1/task-templates/{template['id']}",
                             json={"name": "Weekly report", "prompt": "Review the latest reports.",
                                   "expected_revision": 1},
                             headers={"Idempotency-Key": "template-update-1"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2 and updated.json()["name"] == "Weekly report"

        second_update = client.put(f"/api/v1/task-templates/{template['id']}",
                                   json={"name": "Quarterly report", "prompt": "Review this quarter.",
                                         "expected_revision": 2},
                                   headers={"Idempotency-Key": "template-update-2"})
        assert second_update.status_code == 200 and second_update.json()["revision"] == 3
        replay_update = client.put(f"/api/v1/task-templates/{template['id']}",
                                   json={"name": "Weekly report", "prompt": "Review the latest reports.",
                                         "expected_revision": 1},
                                   headers={"Idempotency-Key": "template-update-1"})
        assert replay_update.status_code == 200 and replay_update.json() == updated.json()

        stale = client.put(f"/api/v1/task-templates/{template['id']}",
                           json={"name": "Stale edit", "prompt": "Do not overwrite.", "expected_revision": 1},
                           headers={"Idempotency-Key": "template-update-stale"})
        assert stale.status_code == 409
        assert client.get("/api/v1/task-templates").json()[0]["name"] == "Quarterly report"

        removed = client.delete(f"/api/v1/task-templates/{template['id']}?expected_revision=3",
                                headers={"Idempotency-Key": "template-delete-1"})
        assert removed.status_code == 204
        replay_create = client.post("/api/v1/task-templates", json=body, headers=headers)
        assert replay_create.status_code == 200 and replay_create.json() == template
        replay_delete = client.delete(f"/api/v1/task-templates/{template['id']}?expected_revision=3",
                                      headers={"Idempotency-Key": "template-delete-1"})
        assert replay_delete.status_code == 204
        assert client.get("/api/v1/task-templates").json() == []

    with TestClient(create_app()) as reopened:
        assert reopened.get("/api/v1/task-templates").json() == []


def test_task_template_library_bounds_and_conflicts(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        too_long = client.post("/api/v1/task-templates", json={"name": "x" * 81, "prompt": "Do work"},
                               headers={"Idempotency-Key": "too-long-name"})
        assert too_long.status_code == 422
        empty = client.post("/api/v1/task-templates", json={"name": "Empty", "prompt": "  "},
                            headers={"Idempotency-Key": "empty-prompt"})
        assert empty.status_code == 422
        assert client.get("/api/v1/task-templates?limit=0").status_code == 200
        assert client.delete("/api/v1/task-templates/missing?expected_revision=1",
                             headers={"Idempotency-Key": "delete-missing"}).status_code == 404
