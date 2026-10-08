from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Run, RunStatus
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


def test_bot_crud_and_validation(client):
    bot = make_bot(client)
    assert bot["name"] == "api-bot"
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

    assert client.delete("/api/bots/api-bot").status_code == 200
    assert client.get("/api/bots/api-bot").status_code == 404


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
    assert capabilities["phone_control"]["status"] == "unavailable"
    assert capabilities["external_runtimes"]["status"] == "unavailable"
