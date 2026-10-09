from __future__ import annotations

import hashlib
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Event, EventType, Run, RunStatus, Task
from hutch.server.app import create_app
from hutch.store import Store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def make_bot(client, name="api-bot", **overrides):
    body = {
        "name": name, "model": "mock/demo",
        "tools": ["files", "memory", "shell"],
        "approval_mode": "auto",
        "description": "api test bot",
        "instructions": "test",
    }
    body.update(overrides)
    res = client.post("/api/bots", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def create_owned_human_wait(store, bot_id, prompt="finish a login"):
    run = store.create_run(Run(bot_id=bot_id, prompt=prompt))
    claimed = store.claim_run(run.id, "fixture-human-wait-owner", lease_seconds=30)
    assert claimed is not None
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    store.transition_run(run.id, RunStatus.waiting_human, fence=claimed.fence)
    store.append_event(Event(run_id=run.id, type=EventType.human_needed,
                             data={"reason": "Sign in to continue"}))
    return store.get_run(run.id), store.list_events(run.id)[-1].seq


def test_health_and_stats(client):
    assert client.get("/api/health").json()["status"] == "ok"
    stats = client.get("/api/stats").json()
    assert stats["bots"] == 0 and stats["pending_approvals"] == 0


def test_run_output_artifacts_are_paged_scoped_and_hash_checked(client, tmp_path):
    bot = make_bot(client, name="artifact-bot")
    store, config = client.app.state.store, client.app.state.config
    run = Run(bot_id=bot["id"], prompt="inspect a large result")
    store.create_run(run)
    artifact_dir = config.run_dir(bot["name"], run.id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    filename = "001-read_file.txt"
    payload = b"full output that was too large for model context\n"
    (artifact_dir / filename).write_bytes(payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "ok": True, "output": "[clipped]", "chars": 5000,
        "artifact": f"artifacts/{filename}", "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_bytes": len(payload),
    }))
    second_filename = "002-read_file.txt"
    second_payload = b"a later output from the same tool\n"
    (artifact_dir / second_filename).write_bytes(second_payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "ok": True, "output": "[later clipped result]", "chars": 7000,
        "artifact": f"artifacts/{second_filename}",
        "artifact_sha256": hashlib.sha256(second_payload).hexdigest(),
        "artifact_bytes": len(second_payload),
    }))
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "ok": True, "output": "[legacy clipped result]", "chars": 6000,
        "artifact": "artifacts/003-read_file.txt",
    }))
    generated_filename = "004-workspace_file.txt"
    generated_payload = b"invoice,total\nA-100,42\n"
    (artifact_dir / generated_filename).write_bytes(generated_payload)
    combined_output_filename = "005-write_file.txt"
    combined_output_payload = b"wrote report.csv (23 chars) plus clipped metadata"
    (artifact_dir / combined_output_filename).write_bytes(combined_output_payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "write_file", "ok": True, "output": "[clipped write result]",
        "artifact": f"artifacts/{combined_output_filename}",
        "artifact_sha256": hashlib.sha256(combined_output_payload).hexdigest(),
        "artifact_bytes": len(combined_output_payload), "chars": 5000,
        "workspace_file": {
            "artifact": f"artifacts/{generated_filename}",
            "sha256": hashlib.sha256(generated_payload).hexdigest(),
            "bytes": len(generated_payload), "name": "report.csv", "path": "report.csv",
        },
    }))

    url = f"/api/v1/tasks/runs/{run.id}/artifacts"
    first = client.get(url, params={"limit": 1})
    assert first.status_code == 200, first.text
    page = first.json()
    assert page["next_offset"] == 1 and len(page["artifacts"]) == 1
    artifact = page["artifacts"][0]
    assert artifact["version"] > 0 and artifact["conversation_id"] == ""
    assert artifact["filename"] == filename and artifact["state"] == "available"
    assert artifact["sha256"] == hashlib.sha256(payload).hexdigest()

    later = client.get(url, params={"limit": 1, "offset": 1}).json()["artifacts"][0]
    assert later["state"] == "available" and later["filename"] == second_filename
    assert later["version"] > artifact["version"] and later["id"] != artifact["id"]
    assert client.get(later["download_url"]).content == second_payload

    old = client.get(url, params={"limit": 1, "offset": 2}).json()["artifacts"][0]
    assert old["state"] == "unverified" and old["download_url"] is None
    combined_output = client.get(url, params={"limit": 1, "offset": 3}).json()["artifacts"][0]
    assert combined_output["kind"] == "tool_output" and combined_output["id"].endswith(":tool_output")
    assert client.get(combined_output["download_url"]).content == combined_output_payload
    generated = client.get(url, params={"limit": 1, "offset": 4}).json()["artifacts"][0]
    assert generated["kind"] == "workspace_file" and generated["filename"] == "report.csv"
    assert generated["id"].endswith(":workspace_file")
    assert generated["state"] == "available" and generated["sha256"] == hashlib.sha256(generated_payload).hexdigest()
    generated_download = client.get(generated["download_url"])
    assert generated_download.content == generated_payload
    assert generated_download.headers["content-disposition"] == 'attachment; filename="report.csv"'
    assert generated_download.headers["x-hutch-artifact-verified"] == "sha256"
    (artifact_dir / generated_filename).write_bytes(generated_payload.replace(b"A-100", b"A-101"))
    tampered_generated = client.get(generated["download_url"])
    assert tampered_generated.status_code == 409 and "SHA-256" in tampered_generated.text
    assert client.get(url + "/not-a-generated-name").status_code == 404

    download = client.get(artifact["download_url"])
    assert download.status_code == 200 and download.content == payload
    assert download.headers["x-hutch-artifact-verified"] == "sha256"
    assert download.headers["etag"] == f'"{hashlib.sha256(payload).hexdigest()}"'

    path = artifact_dir / filename
    path.write_bytes(payload.replace(b"full", b"evil", 1))
    changed = client.get(artifact["download_url"])
    assert changed.status_code == 409 and "SHA-256" in changed.text
    path.unlink()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(payload)
    path.symlink_to(outside)
    assert client.get(artifact["download_url"]).status_code == 404
    path.unlink()
    safe_dir = artifact_dir.with_name("artifacts-safe")
    artifact_dir.rename(safe_dir)
    artifact_dir.symlink_to(tmp_path, target_is_directory=True)
    assert client.get(artifact["download_url"]).status_code == 404
    artifact_dir.unlink()
    safe_dir.rename(artifact_dir)


def test_conversation_artifacts_are_scoped_and_paged(client):
    bot = make_bot(client, name="artifact-owner", paused=True)
    other_bot = make_bot(client, name="other-artifact-owner", paused=True)
    store, config = client.app.state.store, client.app.state.config

    def add_conversation(bot_record, title, key, contents):
        conversation, _ = store.create_conversation(
            bot_record["id"], title, idem_key=f"conversation-{key}", request_hash=f"request-{key}")
        prompt = f"run {key}"
        run = Run(bot_id=bot_record["id"], prompt=prompt, conversation_id=conversation["id"],
                  status=RunStatus.succeeded)
        store.create_run(run)
        with store._tx() as db:
            db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                       (conversation["id"], run.id, run.created_at))
        run_id = run.id
        artifact_dir = config.run_dir(bot_record["name"], run_id) / "artifacts"
        artifact_dir.mkdir(parents=True)
        for index, (kind, name, payload) in enumerate(contents, 1):
            stored = f"{index:03d}-{key}.txt"
            (artifact_dir / stored).write_bytes(payload)
            data = {"tool": "write_file" if kind == "workspace_file" else "read_file",
                    "output": "saved", "artifact": f"artifacts/{stored}",
                    "artifact_sha256": hashlib.sha256(payload).hexdigest(),
                    "artifact_bytes": len(payload), "chars": len(payload)}
            if kind == "workspace_file":
                data["workspace_file"] = {"artifact": f"artifacts/{stored}",
                                           "sha256": hashlib.sha256(payload).hexdigest(),
                                           "bytes": len(payload), "name": name, "path": name}
            store.append_event(Event(run_id=run_id, type=EventType.tool_result, data=data))
        return conversation, run_id

    conversation, own_run = add_conversation(bot, "Project notes", "own", [
        ("tool_output", "output", b"saved tool result"),
        ("workspace_file", "summary.txt", b"created file"),
    ])
    _, sibling_run = add_conversation(bot, "Private chat", "sibling", [
        ("workspace_file", "private.txt", b"another conversation"),
    ])
    add_conversation(other_bot, "Other bot", "other", [
        ("workspace_file", "other.txt", b"another bot's file"),
    ])

    url = f"/api/v1/conversations/{conversation['id']}/artifacts"
    page = client.get(url, params={"limit": 1})
    assert page.status_code == 200, page.text
    first_page = page.json()
    assert first_page["next_cursor"] and len(first_page["artifacts"]) == 1
    assert first_page["artifacts"][0]["kind"] == "tool_output"

    # A new artifact inserted while browsing sorts before the current keyset boundary;
    # it must not shift older pages or cause a duplicate/skip in this traversal.
    late_filename = "999-late.txt"
    late_payload = b"added after the first page"
    late_dir = config.run_dir(bot["name"], own_run) / "artifacts"
    (late_dir / late_filename).write_bytes(late_payload)
    store.append_event(Event(run_id=own_run, type=EventType.tool_result, data={
        "tool": "write_file", "output": "saved", "artifact": f"artifacts/{late_filename}",
        "artifact_sha256": hashlib.sha256(late_payload).hexdigest(),
        "artifact_bytes": len(late_payload), "chars": len(late_payload),
    }))

    items = first_page["artifacts"]
    second_page = client.get(url, params={"limit": 1, "cursor": first_page["next_cursor"]}).json()
    assert second_page["artifacts"][0]["kind"] == "workspace_file"
    assert second_page["artifacts"][0]["version"] == items[0]["version"]
    assert second_page["next_cursor"]
    items += second_page["artifacts"]
    third_page = client.get(url, params={"limit": 1, "cursor": second_page["next_cursor"]}).json()
    assert third_page["next_cursor"] is None
    items += third_page["artifacts"]
    assert len(items) == 3, [(item["id"], item["kind"], item["filename"]) for item in items]
    assert late_filename not in {item["filename"] for item in items}
    assert {item["run_id"] for item in items} == {own_run}
    assert {item["kind"] for item in items} == {"tool_output", "workspace_file"}
    generated = next(item for item in items if item["kind"] == "workspace_file")
    assert generated["filename"] == "summary.txt" and generated["state"] == "available"
    assert client.get(generated["download_url"]).content == b"created file"
    assert client.get(url, params={"limit": 101}).status_code == 422
    assert client.get(url, params={"cursor": "not-a-valid-cursor"}).status_code == 422
    assert client.get("/api/v1/conversations/conv_missing/artifacts").status_code == 404
    assert client.get(f"/api/v1/conversations/{conversation['id']}/artifacts",
                      params={"limit": 100}).json()["artifacts"]
    assert all(item["run_id"] != sibling_run for item in items)


def test_conversation_artifact_share_is_explicit_cross_bot_idempotent_and_revocable(client, tmp_path):
    source_bot = make_bot(client, name="share-source", paused=True)
    target_bot = make_bot(client, name="share-target", paused=True)
    store, config = client.app.state.store, client.app.state.config
    source, _ = store.create_conversation(source_bot["id"], "Private source", idem_key="share-source-conv",
                                          request_hash="share-source-request")
    target, _ = store.create_conversation(target_bot["id"], "Selected recipient", idem_key="share-target-conv",
                                          request_hash="share-target-request")
    run = Run(bot_id=source_bot["id"], prompt="build report", conversation_id=source["id"],
              status=RunStatus.succeeded)
    store.create_run(run)
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (source["id"], run.id, run.created_at))
    payload = b"approved report contents\n"
    filename = "001-report.txt"
    artifact_dir = config.run_dir(source_bot["name"], run.id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    path = artifact_dir / filename
    path.write_bytes(payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "write_file", "output": "report saved", "chars": len(payload),
        "artifact": f"artifacts/{filename}", "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_bytes": len(payload),
        "workspace_file": {"artifact": f"artifacts/{filename}", "sha256": hashlib.sha256(payload).hexdigest(),
                           "bytes": len(payload), "name": "report.txt", "path": "report.txt"},
    }))

    source_url = f"/api/v1/conversations/{source['id']}/artifacts"
    target_url = f"/api/v1/conversations/{target['id']}/artifacts"
    assert len(client.get(source_url).json()["artifacts"]) == 2
    assert client.get(target_url).json()["artifacts"] == []
    share_url = f"/api/v1/conversations/{target['id']}/artifact-shares"
    body = {"source_run_id": run.id, "source_version": 1, "kind": "workspace_file"}
    changes_before_share = store.list_resource_changes()["cursor"]
    assert client.post(share_url, json=body).status_code == 428

    headers = {"Idempotency-Key": "explicit-report-share"}
    created = client.post(share_url, json=body, headers=headers)
    assert created.status_code == 201, created.text
    share = created.json()
    assert share["target_conversation_id"] == target["id"]
    assert share["source_run_id"] == run.id and share["source_version"] == 1
    assert share["kind"] == "workspace_file" and share["actor"] == "operator"
    assert share["revoked_at"] is None
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with store._tx() as db:
            db.execute("UPDATE conversation_artifact_shares SET source_run_id = 'forged' WHERE id = ?",
                       (share["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with store._tx() as db:
            db.execute("DELETE FROM conversation_artifact_shares WHERE id = ?", (share["id"],))

    replay = client.post(share_url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == share["id"]
    assert client.post(share_url, json={**body, "kind": "tool_output"}, headers=headers).status_code == 409
    duplicate = client.post(share_url, json=body, headers={"Idempotency-Key": "another-share-key"})
    assert duplicate.status_code == 200 and duplicate.json()["id"] == share["id"]
    share_changes = [item for item in store.list_resource_changes(changes_before_share)["changes"]
                     if item["resource"] == "conversations"]
    target_share_changes = [item for item in share_changes if item["resource_id"] == target["id"]]
    source_share_changes = [item for item in share_changes if item["resource_id"] == source["id"]]
    assert sum(item["operation"] == "created" for item in target_share_changes) == 1
    assert sum(item["operation"] == "updated" for item in source_share_changes) == 1

    source_items = client.get(source_url).json()["artifacts"]
    source_workspace_file = next(item for item in source_items if item["kind"] == "workspace_file")
    assert source_workspace_file["shared_with"] == [{
        "id": share["id"], "target_conversation_id": target["id"],
        "target_conversation_title": "Selected recipient", "created_at": share["created_at"],
    }]

    shared = client.get(target_url).json()["artifacts"]
    assert len(shared) == 1
    assert shared[0]["share_id"] == share["id"] and shared[0]["shared_from"] == "Private source"
    assert shared[0]["run_id"] == run.id and shared[0]["filename"] == "report.txt"
    shared_url = shared[0]["download_url"]
    assert f"/conversations/{target['id']}/artifact-shares/{share['id']}/content" in shared_url
    assert client.get(shared_url).content == payload
    assert client.get(f"/api/v1/conversations/{source['id']}/artifact-shares/{share['id']}/content").status_code == 404
    assert client.get(f"/api/v1/conversations/{target['id']}").json()["messages"] == []
    assert client.post(f"/api/v1/conversations/{source['id']}/artifact-shares", json=body,
                       headers={"Idempotency-Key": "share-to-source"}).status_code == 409

    revoke_url = f"/api/v1/conversations/{target['id']}/artifact-shares/{share['id']}"
    revoke_headers = {"Idempotency-Key": "revoke-report-share"}
    revoked = client.delete(revoke_url, headers=revoke_headers)
    assert revoked.status_code == 200 and revoked.json()["revoked_at"]
    revoke_changes = [item for item in store.list_resource_changes(changes_before_share)["changes"]
                      if item["resource"] == "conversations"]
    target_revoke_changes = [item for item in revoke_changes if item["resource_id"] == target["id"]]
    source_revoke_changes = [item for item in revoke_changes if item["resource_id"] == source["id"]]
    assert sum(item["operation"] == "updated" for item in target_revoke_changes) == 1
    assert sum(item["operation"] == "updated" for item in source_revoke_changes) == 2
    assert client.get(target_url).json()["artifacts"] == []
    revoke_replay = client.delete(revoke_url, headers=revoke_headers)
    assert revoke_replay.status_code == 200 and revoke_replay.json()["id"] == share["id"]
    assert client.get(shared_url).status_code == 404, "revocation must stop later downloads through the grant"
    assert client.get(f"/api/v1/tasks/runs/{run.id}/artifacts/{filename}").content == payload
    source_items = client.get(source_url).json()["artifacts"]
    assert next(item for item in source_items if item["kind"] == "workspace_file")["shared_with"] == []

    renewed = client.post(share_url, json=body, headers={"Idempotency-Key": "share-again"})
    assert renewed.status_code == 201 and renewed.json()["id"] != share["id"]
    assert len(client.get(target_url).json()["artifacts"]) == 1
    source_items = client.get(source_url).json()["artifacts"]
    assert next(item for item in source_items if item["kind"] == "workspace_file")["shared_with"][0]["id"] == renewed.json()["id"]
    rows = store._db.execute("SELECT id, revoked_at FROM conversation_artifact_shares ORDER BY created_at, id").fetchall()
    assert len(rows) == 2 and rows[0]["id"] == share["id"] and rows[0]["revoked_at"]


def test_only_verified_artifacts_can_be_shared_and_share_history_is_immutable(client):
    bot = make_bot(client, name="share-verification", paused=True)
    store = client.app.state.store
    source, _ = store.create_conversation(bot["id"], "Source", idem_key="unverified-source",
                                          request_hash="unverified-source-request")
    target, _ = store.create_conversation(bot["id"], "Target", idem_key="unverified-target",
                                          request_hash="unverified-target-request")
    run = Run(bot_id=bot["id"], prompt="old output", conversation_id=source["id"], status=RunStatus.succeeded)
    store.create_run(run)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "output": "old", "artifact": "artifacts/001-old.txt", "chars": 100,
    }))
    url = f"/api/v1/conversations/{target['id']}/artifact-shares"
    response = client.post(url, json={"source_run_id": run.id, "source_version": 1, "kind": "tool_output"},
                           headers={"Idempotency-Key": "reject-unverified"})
    assert response.status_code == 409 and "verified" in response.text
    assert store._db.execute("SELECT COUNT(*) FROM conversation_artifact_shares").fetchone()[0] == 0


def test_artifact_bytes_are_checked_again_when_sharing_and_downloading(client, tmp_path):
    bot = make_bot(client, name="share-integrity", paused=True)
    store, config = client.app.state.store, client.app.state.config
    source, _ = store.create_conversation(bot["id"], "Integrity source", idem_key="integrity-source",
                                          request_hash="integrity-source-request")
    target, _ = store.create_conversation(bot["id"], "Integrity target", idem_key="integrity-target",
                                          request_hash="integrity-target-request")
    run = Run(bot_id=bot["id"], prompt="save verified output", conversation_id=source["id"],
              status=RunStatus.succeeded)
    store.create_run(run)
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (source["id"], run.id, run.created_at))
    payload = b"verified bytes"
    filename = "001-report.txt"
    artifact_dir = config.run_dir(bot["name"], run.id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    path = artifact_dir / filename
    path.write_bytes(payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "read_file", "output": "saved", "chars": len(payload),
        "artifact": f"artifacts/{filename}", "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_bytes": len(payload),
    }))
    body = {"source_run_id": run.id, "source_version": 1, "kind": "tool_output"}
    url = f"/api/v1/conversations/{target['id']}/artifact-shares"
    headers = {"Idempotency-Key": "integrity-share"}
    path.write_bytes(b"changed bytes")
    failed = client.post(url, json=body, headers=headers)
    assert failed.status_code == 409 and "do not match" in failed.text
    assert store._db.execute("SELECT COUNT(*) FROM conversation_artifact_shares").fetchone()[0] == 0

    path.write_bytes(payload)
    created = client.post(url, json=body, headers=headers)
    assert created.status_code == 201, created.text
    shared = client.get(f"/api/v1/conversations/{target['id']}/artifacts").json()["artifacts"][0]
    assert client.get(shared["download_url"]).content == payload
    path.write_bytes(b"tampered bytes")
    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == created.json()["id"]
    checked = client.get(shared["download_url"])
    assert checked.status_code == 409 and "SHA-256" in checked.text


def test_bot_crud_and_validation(client):
    bot = make_bot(client, local_browser_handoff=True)
    assert bot["name"] == "api-bot"
    assert bot["local_browser_handoff"] is True
    assert bot["tools"] == ["read_file", "list_files", "write_file", "remember", "recall", "shell"]

    # duplicate
    assert client.post("/api/bots", json={"name": "api-bot"}).status_code == 409
    # bad slug
    assert client.post("/api/bots", json={"name": "Bad!"}).status_code == 422
    # unknown tool
    assert client.post("/api/bots", json={"name": "x-bot", "tools": ["laser"]}).status_code == 422

    detail = client.get("/api/bots/api-bot").json()
    assert detail["recent_runs"] == []

    patched = client.patch("/api/bots/api-bot", json={"paused": True, "cron": "0 9 * * 1"}).json()
    assert patched["paused"] is True and patched["schedule"]["cron"] == "0 9 * * 1"
    local = client.patch("/api/bots/api-bot", json={"local_browser_handoff": True}).json()
    assert local["local_browser_handoff"] is True
    disabled = client.patch("/api/bots/api-bot", json={"local_browser_handoff": False}).json()
    assert disabled["local_browser_handoff"] is False

    assert client.delete("/api/bots/api-bot").status_code == 200
    assert client.get("/api/bots/api-bot").status_code == 404


def test_bot_create_requires_a_real_route_outside_the_test_harness(client, monkeypatch):
    monkeypatch.delenv("HUTCH_TESTING", raising=False)
    missing = client.post("/api/bots", json={"name": "unconfigured"})
    assert missing.status_code == 422 and "No model route is configured" in missing.json()["detail"]
    retired = client.post("/api/bots", json={"name": "legacy-mock", "model": "mock/demo"})
    assert retired.status_code == 422 and "test-only" in retired.json()["detail"]
    assert client.get("/api/bots").json() == []


def test_bot_limits_are_editable_and_validated(client):
    make_bot(client)
    saved = client.patch("/api/bots/api-bot", json={"limits": {
        "max_steps": 12, "timeout_seconds": 300, "daily_token_cap": 5000,
        "max_turn_tokens": 1500, "max_cost_usd": 0.75, "daily_cost_cap_usd": 4.25,
    }})
    assert saved.status_code == 200, saved.text
    assert saved.json()["limits"] == {
        "max_steps": 12, "timeout_seconds": 300, "daily_token_cap": 5000,
        "max_turn_tokens": 1500, "max_cost_usd": 0.75, "daily_cost_cap_usd": 4.25,
    }
    assert client.patch("/api/bots/api-bot", json={"limits": {"max_steps": 0}}).status_code == 422
    assert client.patch("/api/bots/api-bot", json={"limits": {"max_cost_usd": -0.01}}).status_code == 422


def test_templates_endpoint(client):
    templates = client.get("/api/bots/templates").json()
    names = {t["name"] for t in templates}
    assert {"research-briefing", "repo-sweeper", "tidy-downloads"} <= names


def test_spa_connections_api_never_echoes_key_and_validates_allowance(client):
    created = client.post("/api/connections", json={
        "template": "custom-openai", "name": "fixture-endpoint", "base_url": "https://example.invalid/v1",
    })
    assert created.status_code == 201, created.text
    assert created.json() == {"added": "fixture-endpoint"}

    listing = client.get("/api/connections").json()
    connection = next(row for row in listing["connections"] if row["name"] == "fixture-endpoint")
    assert connection["has_key"] is False
    assert "key" not in connection

    secret = "fixture-secret-do-not-use"
    saved = client.post("/api/connections/fixture-endpoint/set-key", json={"key": secret})
    assert saved.status_code == 200 and secret not in saved.text
    assert "key" not in saved.json()
    listing = client.get("/api/connections").json()
    connection = next(row for row in listing["connections"] if row["name"] == "fixture-endpoint")
    assert connection["has_key"] is True
    assert secret not in client.get("/api/connections").text

    assert client.post("/api/connections/fixture-endpoint/allowance",
                       json={"window": "week", "tokens": 12345}).status_code == 200
    assert client.post("/api/connections/fixture-endpoint/allowance",
                       json={"window": "week", "tokens": -1}).status_code == 422
    assert client.post("/api/connections/fixture-endpoint/clear-key", json={}).status_code == 200
    assert client.post("/api/connections/fixture-endpoint/remove", json={}).status_code == 200
    assert all(row["name"] != "fixture-endpoint" for row in client.get("/api/connections").json()["connections"])


def test_full_mock_run_via_api(client):
    bot = make_bot(client)
    res = client.post("/api/bots/api-bot/run", json={"prompt": "research the news and summarize"})
    assert res.status_code == 201
    run_id = res.json()["id"]

    deadline = time.time() + 20
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("pending", "running", "waiting_approval"):
            break
        time.sleep(0.2)
    assert run["status"] == "succeeded"
    assert run["steps"] >= 3
    assert len(run["events"]) >= 5
    assert any(e["type"] == "tool_call" for e in run["events"])

    listing = client.get("/api/runs").json()
    assert listing[0]["bot_name"] == "api-bot"

    after = client.get(f"/api/runs/{run_id}/events?after={run['events'][0]['id']}").json()
    assert len(after["events"]) == len(run["events"]) - 1


def test_v1_manual_run_is_idempotent_and_legacy_alias_remains(client):
    bot = make_bot(client, name="retryable-run", paused=True)
    url = "/api/v1/tasks/runs"
    body = {"bot": bot["id"], "prompt": "prepare a short report", "rehearse": True}

    assert client.post(url, json=body).status_code == 428

    headers = {"Idempotency-Key": "manual-run-create-once"}
    created = client.post(url, json=body, headers=headers)
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    assert created.json()["replayed"] is False

    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == run_id and replay.json()["replayed"] is True

    changed = client.post(url, json={**body, "prompt": "different request"}, headers=headers)
    assert changed.status_code == 409
    changed_bot = client.post(url, json={**body, "bot": "missing-bot"}, headers=headers)
    assert changed_bot.status_code == 409
    cross_command = client.post("/api/v1/conversations", json={"bot": bot["id"], "title": "Other command"},
                                headers=headers)
    assert cross_command.status_code == 409

    store = client.app.state.store
    assert store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 1
    assert store._db.execute("SELECT COUNT(*) FROM tasks WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 1

    legacy = client.post("/api/bots/retryable-run/run", json={"prompt": "legacy request"})
    assert legacy.status_code == 201, legacy.text
    assert legacy.json()["id"] != run_id
    assert store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 2

    # A lost-response retry can still retrieve its committed result during restore
    # review; a genuinely new command remains held and creates no work.
    with store._tx() as db:
        db.execute("INSERT INTO state_restores(id, created_at, source_schema, manifest_hash, verified_code_hash, report_json) "
                   "VALUES (?, ?, ?, ?, ?, ?)",
                   ("restore_retry_test", "2026-10-09T00:00:00Z", store.schema_version, "fixture", "fixture", "{}"))
    replay_while_held = client.post(url, json=body, headers=headers)
    assert replay_while_held.status_code == 200 and replay_while_held.json()["id"] == run_id
    assert replay_while_held.json()["replayed"] is True
    held = client.post(url, json=body, headers={"Idempotency-Key": "manual-run-new-during-hold"})
    assert held.status_code == 409 and held.json()["code"] == "restore_review_required"
    assert store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 2
    assert store._db.execute("SELECT COUNT(*) FROM tasks WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 2


def test_v1_run_idempotency_is_atomic_across_store_connections(client):
    bot = make_bot(client, name="concurrent-run", paused=True)
    config = client.app.state.config
    first_store = client.app.state.store
    second_store = Store(config)
    barrier = Barrier(2)
    key = "same-run-from-two-connections"
    digest = "request-hash-for-concurrent-run"

    def submit(store):
        run = Run(bot_id=bot["id"], prompt="the same run", origin="manual:api:v1", rehearsal=True)
        task = Task(bot_id=bot["id"], kind="on_demand", prompt="the same run")
        barrier.wait()
        return store.submit_run_idempotent(run, task, idem_key=key, request_hash=digest)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (first_store, second_store)))
        assert len({run.id for run, _created in results}) == 1
        assert sorted(created for _run, created in results) == [False, True]
        assert first_store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 1
        assert first_store._db.execute("SELECT COUNT(*) FROM tasks WHERE bot_id = ?", (bot["id"],)).fetchone()[0] == 1
    finally:
        second_store.close()


def test_v1_resume_is_idempotent_and_bound_to_one_human_wait(client):
    bot = make_bot(client, name="human-wait", paused=True)
    store = client.app.state.store
    run, first_wait_seq = create_owned_human_wait(store, bot["id"])
    url = f"/api/v1/tasks/runs/{run.id}/resume"
    body = {"human_event_seq": first_wait_seq}

    assert client.post(url, json=body).status_code == 428
    headers = {"Idempotency-Key": "resume-login-wait-once"}
    resumed = client.post(url, json=body, headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json() == {"resumed": run.id, "human_event_seq": first_wait_seq, "replayed": False}
    assert store.kv_get(f"resume:{run.id}") == "1"

    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert store.kv_get(f"resume:{run.id}") == "1"

    duplicate_wait = client.post(url, json=body, headers={"Idempotency-Key": "resume-same-wait-again"})
    assert duplicate_wait.status_code == 409
    assert store.consume_resume(run.id)
    assert not store.consume_resume(run.id)

    store.append_event(Event(run_id=run.id, type=EventType.human_needed,
                             data={"reason": "Confirm the second sign-in step"}))
    second_wait_seq = store.list_events(run.id)[-1].seq
    assert second_wait_seq > first_wait_seq
    assert client.post(url, json=body, headers=headers).json()["replayed"] is True
    assert store.kv_get(f"resume:{run.id}") == "0", "replaying an old wait must not resume a later challenge"
    stale = client.post(url, json=body, headers={"Idempotency-Key": "resume-stale-wait"})
    assert stale.status_code == 409

    current = client.post(url, json={"human_event_seq": second_wait_seq},
                          headers={"Idempotency-Key": "resume-second-wait"})
    assert current.status_code == 200 and current.json()["human_event_seq"] == second_wait_seq
    assert store.kv_get(f"resume:{run.id}") == "1"
    assert store.consume_resume(run.id)
    store.transition_run(run.id, RunStatus.running, event={"reason": "fixture completed the human wait"})
    assert client.post(url, json={"human_event_seq": second_wait_seq},
                       headers={"Idempotency-Key": "resume-second-wait"}).json()["replayed"] is True
    rejected = client.post(url, json={"human_event_seq": second_wait_seq},
                           headers={"Idempotency-Key": "resume-after-wait-ended"})
    assert rejected.status_code == 409 and "not waiting" in rejected.text


def test_v1_resume_accepts_only_one_concurrent_command_per_human_wait(client):
    bot = make_bot(client, name="concurrent-human-wait", paused=True)
    first_store = client.app.state.store
    second_store = Store(client.app.state.config)
    run, event_seq = create_owned_human_wait(first_store, bot["id"])
    barrier = Barrier(2)

    keys = ("human-wait-race-a", "human-wait-race-b")

    def resume(store, key):
        barrier.wait()
        try:
            return store.resume_run_idempotent(
                run.id, event_seq, idem_key=key, request_hash=f"request-{key}")
        except ValueError as exc:
            return str(exc)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda args: resume(*args), zip((first_store, second_store), keys)))
        assert sum(isinstance(result, tuple) and result[1] for result in results) == 1
        assert sum(isinstance(result, str) and "already has a resume command" in result
                   for result in results) == 1
        assert first_store.kv_get(f"resume:{run.id}") == "1"
        assert first_store._db.execute("SELECT COUNT(*) FROM human_wait_resumes WHERE run_id = ?",
                                       (run.id,)).fetchone()[0] == 1
        winner_key = keys[next(index for index, result in enumerate(results)
                               if isinstance(result, tuple) and result[1])]
        replay_store = Store(client.app.state.config)
        try:
            replay, created = replay_store.resume_run_idempotent(
                run.id, event_seq, idem_key=winner_key, request_hash=f"request-{winner_key}")
            assert not created and replay["human_event_seq"] == event_seq
            assert replay_store.kv_get(f"resume:{run.id}") == "1"
        finally:
            replay_store.close()
    finally:
        second_store.close()


def test_v1_resume_rejects_a_wait_without_a_live_owner(client):
    bot = make_bot(client, name="expired-human-wait", paused=True)
    store = client.app.state.store
    run, event_seq = create_owned_human_wait(store, bot["id"])
    with store._tx() as db:
        db.execute("UPDATE runs SET lease_expires_at = ? WHERE id = ?",
                   ("2000-01-01T00:00:00+00:00", run.id))
    response = client.post(f"/api/v1/tasks/runs/{run.id}/resume", json={"human_event_seq": event_seq},
                           headers={"Idempotency-Key": "resume-expired-worker"})
    assert response.status_code == 409 and "active owner" in response.text
    assert store.kv_get(f"resume:{run.id}") is None
    assert store._db.execute("SELECT COUNT(*) FROM human_wait_resumes WHERE run_id = ?",
                             (run.id,)).fetchone()[0] == 0


def test_approval_flow_via_api(client):
    make_bot(client, name="asker", approval_mode="ask")
    res = client.post("/api/bots/asker/run", json={"prompt": "sort my downloads"})
    run_id = res.json()["id"]

    deadline = time.time() + 15
    approvals = []
    while time.time() < deadline:
        approvals = client.get("/api/approvals").json()
        if approvals:
            break
        time.sleep(0.2)
    assert approvals, "expected a write_file approval to appear"
    req = approvals[0]
    assert req["bot_name"] == "asker" and req["tool"] in ("files", "shell")
    approval_id = req["id"]
    assert client.get(f"/api/approvals/{approval_id}").json()["status"] == "pending"

    assert client.post(f"/api/approvals/{approval_id}/approve", json={"always": True}).status_code == 200
    # duplicate resolution is rejected
    assert client.post(f"/api/approvals/{approval_id}/approve", json={}).status_code == 409
    decided = client.get(f"/api/approvals/{approval_id}").json()
    assert decided["status"] == "approved" and decided["decided_by"]
    assert any(a["id"] == approval_id for a in client.get("/api/approvals?status=resolved&limit=8").json())
    assert client.get("/api/approvals/does-not-exist").status_code == 404

    deadline = time.time() + 20
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("pending", "running", "waiting_approval"):
            break
        time.sleep(0.2)
    assert run["status"] == "succeeded"

    # sticky allow recorded on the bot
    detail = client.get("/api/bots/asker").json()
    assert req["sticky_key"] in detail["sticky_allows"]


def test_dashboard_page_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "hutch" in res.text.lower()
    assert res.headers["content-type"].startswith("text/html")
    css = client.get("/static/style.css")
    assert css.status_code == 200
    js = client.get("/static/app.js")
    assert js.status_code == 200


def test_sticky_and_memory_deletion(client):
    make_bot(client, name="mem-bot")
    # inject memory and sticky via internal store or approval
    # we can call the store via client app state or run a quick task
    # or test deletion on non-existent (idempotent 200)
    res_mem = client.delete("/api/bots/mem-bot/memory/test-key")
    assert res_mem.status_code == 200
    assert res_mem.json() == {"forgot": "test-key", "operation": "archived",
                              "scope": "all facts with this key for this bot", "history_retained": True}

    res_sticky = client.delete("/api/bots/mem-bot/sticky-allows/shell:echo")
    assert res_sticky.status_code == 200
    assert res_sticky.json() == {"revoked": "shell:echo"}


def test_versioned_stop_is_idempotent_and_rejects_key_reuse(client):
    from hutch.models import Bot, Run

    bot = client.app.state.store.create_bot(Bot(name="idem-stop", model="mock/demo"))
    first = client.app.state.store.create_run(Run(bot_id=bot.id, prompt="first"))
    second = client.app.state.store.create_run(Run(bot_id=bot.id, prompt="second"))
    url = f"/api/v1/tasks/runs/{first.id}/stop"
    assert client.post(url).status_code == 428
    headers = {"Idempotency-Key": "stop-one"}
    assert client.post(url, headers=headers).status_code == 200
    assert client.post(url, headers=headers).status_code == 200
    conflict = client.post(f"/api/v1/tasks/runs/{second.id}/stop", headers=headers)
    assert conflict.status_code == 409


def test_versioned_approval_resolution_is_idempotent_and_hash_bound(client):
    from hutch.models import ApprovalRequest, Bot, Run

    store = client.app.state.store
    bot = store.create_bot(Bot(name="idem-approval", model="mock/demo"))
    run = store.create_run(Run(bot_id=bot.id, prompt="approve this"))
    request = store.create_approval(ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="files",
                                                    action="write report", detail={"path": "report.txt"},
                                                    sticky_key="files:write:report.txt", action_hash="fingerprint"))
    url = f"/api/v1/actions/approvals/{request.id}/approve"
    body = {"always": True, "action_hash": request.action_hash}
    assert client.post(url, json=body).status_code == 428
    headers = {"Idempotency-Key": "approve-one"}
    approved = client.post(url, json=body, headers=headers)
    assert approved.status_code == 200, approved.text
    assert client.post(url, json=body, headers=headers).status_code == 200
    assert store.is_sticky_allowed(bot.id, request.sticky_key)
    changed = client.post(url, json={**body, "always": False}, headers=headers)
    assert changed.status_code == 409


def test_versioned_connections_schedules_and_capabilities_are_typed_and_secret_free(client):
    from hutch.connections import ConnectionBook

    book = ConnectionBook(client.app.state.config.state_dir)
    book.add("custom-openai", name="private-route", base_url="https://models.example.test/v1",
             account_id="api-account", account_daily_cost_cap_usd=5.0,
             quota={"window": "day", "tokens": 5000})
    book.set_key("private-route", "never-return-this-key")
    connections = client.get("/api/v1/connections")
    assert connections.status_code == 200
    route = next(row for row in connections.json() if row["name"] == "private-route")
    assert route["key_present"] is True and route["protocol"] == "openai-chat"
    assert route["account_id"] == "api-account" and route["account_daily_cost_cap_usd"] == 5.0
    assert route["configured_account_daily_cost_cap_usd"] == 5.0
    bot = client.app.state.store.create_bot(Bot(name="reservation-api"))
    # Keep the fixture out of the live supervisor's pending queue; its fence
    # owns production reservations, while this API resource check is synthetic.
    run = client.app.state.store.create_run(Run(bot_id=bot.id, prompt="api status", status=RunStatus.running))
    client.app.state.store.reserve_usage(run_id=run.id, bot_id=bot.id, provider="private-route",
                                         account_id="api-account", model="m", reserved_tokens=123,
                                         reserved_cost_usd=0.45)
    reservations = client.get("/api/v1/usage/reservations").json()
    assert reservations[0]["account_id"] == "api-account" and reservations[0]["reserved_tokens"] == 123
    route = next(row for row in client.get("/api/v1/connections").json() if row["name"] == "private-route")
    assert route["quota_reserved_tokens"] == 123 and route["account_daily_cost_reserved_usd"] == 0.45
    assert "never-return-this-key" not in connections.text

    bot = make_bot(client, name="scheduled-v1", cron="0 9 * * 1", timezone="America/Vancouver",
                   schedule_prompt="Review new release notes and write a concise report.")
    schedules = client.get("/api/v1/schedules").json()
    schedule = next(row for row in schedules if row["bot_id"] == bot["id"])
    assert schedule["cron"] == "0 9 * * 1" and schedule["timezone"] == "America/Vancouver"
    assert schedule["prompt"] == "Review new release notes and write a concise report."
    assert schedule["name"] == "Scheduled task"
    assert schedule["next_fire"] and schedule["last_dispatched"]
    assert client.get("/api/bots/scheduled-v1").json()["schedule"]["prompt"] == schedule["prompt"]
    updated = client.patch("/api/bots/scheduled-v1", json={"schedule_prompt": "Check the weekly security feed."})
    assert updated.status_code == 200 and updated.json()["schedule"]["prompt"] == "Check the weekly security feed."
    reset = client.patch("/api/bots/scheduled-v1", json={"schedule_prompt": ""})
    assert reset.status_code == 200 and reset.json()["schedule"]["prompt"] == ""
    multi = client.app.state.store.get_bot("scheduled-v1")
    from hutch.models import Schedule
    multi.set_schedules([multi.schedule, Schedule(id="quarterly", name="Quarterly review",
                                                   cron="0 9 1 1,4,7,10 *", prompt="Review the quarter")])
    client.app.state.store.upsert_bot(multi)
    listed = [row for row in client.get("/api/v1/schedules").json() if row["bot_id"] == multi.id]
    assert {row["id"] for row in listed} == {multi.schedule.id, "quarterly"}
    assert next(row for row in listed if row["id"] == "quarterly")["name"] == "Quarterly review"
    legacy_edit = client.patch("/api/bots/scheduled-v1", json={"schedule_prompt": "First task changed"})
    assert legacy_edit.status_code == 200 and legacy_edit.json()["schedule"]["prompt"] == "First task changed"
    assert {item["id"] for item in legacy_edit.json()["schedules"]} == {multi.schedule.id, "quarterly"}
    non_schedule_edit = client.patch("/api/bots/scheduled-v1", json={"description": "keep the sibling"})
    assert non_schedule_edit.status_code == 200
    assert {item["id"] for item in non_schedule_edit.json()["schedules"]} == {multi.schedule.id, "quarterly"}
    body = {"name": "Morning brief", "cron": "0 8 * * 1-5", "timezone": "UTC",
            "catch_up": "coalesce", "prompt": "Summarize priority messages."}
    created = client.put(f"/api/v1/bots/{multi.id}/schedules/morning", json=body)
    assert created.status_code == 200 and created.json()["next_fire"]
    assert client.put(f"/api/v1/bots/{multi.id}/schedules/morning", json=body).json() == created.json()
    listed = [row for row in client.get("/api/v1/schedules").json() if row["bot_id"] == multi.id]
    assert {row["id"] for row in listed} == {multi.schedule.id, "quarterly", "morning"}
    first_page = client.get("/api/v1/schedules", params={"bot": multi.id, "limit": 1, "offset": 0}).json()
    second_page = client.get("/api/v1/schedules", params={"bot": multi.id, "limit": 1, "offset": 1}).json()
    assert len(first_page) == len(second_page) == 1 and first_page[0]["id"] != second_page[0]["id"]
    other = client.app.state.store.create_bot(Bot(name="other-scheduled-bot"))
    assert client.put(f"/api/v1/bots/{other.id}/schedules/morning", json=body).status_code == 409
    invalid = client.put(f"/api/v1/bots/{multi.id}/schedules/invalid", json={**body, "timezone": "Mars/Olympus"})
    assert invalid.status_code == 422
    removed_id = multi.schedule.id
    assert client.delete(f"/api/v1/bots/{multi.id}/schedules/{removed_id}").status_code == 204
    after_delete = client.app.state.store.get_bot("scheduled-v1")
    assert after_delete.schedule.id == "quarterly" and len(after_delete.schedules) == 2
    assert client.put(f"/api/v1/bots/{multi.id}/schedules/{removed_id}", json=body).status_code == 409
    assert client.delete(f"/api/v1/bots/{multi.id}/schedules/missing").status_code == 404
    assert client.patch("/api/bots/scheduled-v1", json={"clear_cron": True,
                      "schedule_prompt": "Prompt without a schedule"}).status_code == 422
    no_cron_prompt = client.post("/api/bots", json={"name": "prompt-needs-cron", "model": "mock/demo",
                                                     "schedule_prompt": "Prompt without a schedule"})
    assert no_cron_prompt.status_code == 422
    overlong_prompt = client.post("/api/bots", json={"name": "prompt-too-long", "model": "mock/demo",
                                                      "cron": "0 9 * * 1", "schedule_prompt": "x" * 4001})
    assert overlong_prompt.status_code == 422

    capabilities = {row["id"]: row for row in client.get("/api/v1/capabilities").json()}
    assert capabilities["strict_offline"]["status"] in {"experimental", "unavailable"}
    assert capabilities["strict_offline"]["verification"] == "network_pid_namespace_tcp_unix_socket_probe"
    assert capabilities["remote_pairing"]["status"] == "experimental"
    assert capabilities["browser_handoff"]["status"] in {"experimental", "unavailable"}
    assert capabilities["browser_handoff"]["verification"] in {
        "host_display_and_playwright_check", "host_prerequisite_check"}
    assert capabilities["phone_control"]["status"] == "unavailable"
    assert capabilities["external_runtimes"]["status"] == "unavailable"
