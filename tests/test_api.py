from __future__ import annotations

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Event, EventType, Run, RunStatus
from hutch.server.app import create_app


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

    bot = make_bot(client, name="scheduled-v1", cron="0 9 * * 1", timezone="America/Vancouver")
    schedules = client.get("/api/v1/schedules").json()
    schedule = next(row for row in schedules if row["bot_id"] == bot["id"])
    assert schedule["cron"] == "0 9 * * 1" and schedule["timezone"] == "America/Vancouver"
    assert schedule["next_fire"] and schedule["last_dispatched"]

    capabilities = {row["id"]: row for row in client.get("/api/v1/capabilities").json()}
    assert capabilities["strict_offline"]["status"] in {"experimental", "unavailable"}
    assert capabilities["strict_offline"]["verification"] == "network_pid_namespace_tcp_unix_socket_probe"
    assert capabilities["remote_pairing"]["status"] == "experimental"
    assert capabilities["browser_handoff"]["status"] in {"experimental", "unavailable"}
    assert capabilities["browser_handoff"]["verification"] in {
        "host_display_and_playwright_check", "host_prerequisite_check"}
    assert capabilities["phone_control"]["status"] == "unavailable"
    assert capabilities["external_runtimes"]["status"] == "unavailable"
