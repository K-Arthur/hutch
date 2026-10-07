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


def test_templates_endpoint(client):
    templates = client.get("/api/bots/templates").json()
    names = {t["name"] for t in templates}
    assert {"research-briefing", "repo-sweeper", "tidy-downloads"} <= names


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

    assert client.post(f"/api/approvals/{req['id']}/approve", json={"always": True}).status_code == 200
    # duplicate resolution is rejected
    assert client.post(f"/api/approvals/{req['id']}/approve", json={}).status_code == 409

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
