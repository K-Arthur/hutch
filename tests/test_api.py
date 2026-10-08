from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

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


def test_tool_limits_patch_and_artifact_serving(client):
    """PF-2: per-tool caps are configurable, truncation keeps the full output,
    and the artifact endpoint serves only files inside this run's directory."""
    bot = make_bot(client)

    res = client.patch(f"/api/bots/{bot['name']}", json={"tool_limits": {"list_files": 1}})
    assert res.status_code == 200 and res.json()["tool_limits"] == {"list_files": 1}
    assert client.patch(f"/api/bots/{bot['name']}", json={"tool_limits": {"nope": 5}}).status_code == 422
    assert client.patch(f"/api/bots/{bot['name']}", json={"tool_limits": {"list_files": -3}}).status_code == 422

    res = client.post("/api/bots/api-bot/run", json={"prompt": "research the news"})
    assert res.status_code == 201
    run_id = res.json()["id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("pending", "running", "waiting_approval"):
            break
        time.sleep(0.2)
    assert run["status"] == "succeeded"

    art_ev = next(e for e in run["events"] if e["type"] == "tool_result" and e["data"].get("artifact"))
    rel = art_ev["data"]["artifact"]
    assert rel.startswith("artifacts/")
    assert "omitted" in art_ev["data"]["output"]       # the display carries the truncation note

    got = client.get(f"/api/runs/{run_id}/{rel}")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("text/plain")
    assert len(got.text) == art_ev["data"]["chars"]    # served file is the FULL output
    assert "omitted" not in got.text                   # ... and not the cut view

    # traversal, absolute, unknown-file and unknown-run are all refused
    assert client.get(f"/api/runs/{run_id}/artifacts/..%2F..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get(f"/api/runs/{run_id}/artifacts/%2Fetc%2Fpasswd").status_code == 404
    assert client.get(f"/api/runs/{run_id}/artifacts/nope.txt").status_code == 404
    assert client.get("/api/runs/run_nope/artifacts/x.txt").status_code == 404


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
    assert res_mem.json() == {"forgot": "test-key"}

    res_sticky = client.delete("/api/bots/mem-bot/sticky-allows/shell:echo")
    assert res_sticky.status_code == 200
    assert res_sticky.json() == {"revoked": "shell:echo"}
