"""Tests for onboarding assistant step (slice 07).

Validates GET rendering, suggestion logic, CSRF protection, slug collision detection,
bot creation in store, and setup revision progression.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hutch.models import iso, utcnow
from hutch.onboarding import apply_request_edit, default_setup, encode_setup
from hutch.onboarding_store import SETUP_KEY
from hutch.server.app import create_app

ASSISTANT_URL = "/onboarding/assistant"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        yield c


def seed(c, *, text="Summarise today's release notes", conn_name="opencode"):
    now = utcnow()
    result = apply_request_edit(default_setup(now), expected_revision=0, request_text=text, now=now)
    assert result.kind == "accepted" and result.setup is not None
    setup = result.setup.model_copy(update={
        "resume_expires_at": iso(now + timedelta(days=30)),
        "route_kind": "opencode",
        "connection_name": conn_name,
        "step": "assistant",
    })
    c.app.state.store.kv_set(SETUP_KEY, encode_setup(setup))
    return setup


def stored(c) -> dict:
    return json.loads(c.app.state.store.kv_get(SETUP_KEY))


def csrf(c) -> str:
    body = c.get(ASSISTANT_URL).text
    match = re.search(r'<meta name="csrf" content="([^"]+)">', body)
    if not match:
        match = re.search(r'name="csrf" value="([^"]+)"', body)
    return match.group(1) if match else "test-csrf"


def test_get_without_request_redirects_to_onboarding(client):
    r = client.get(ASSISTANT_URL, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/onboarding"


def test_get_with_request_renders_assistant_creation(client):
    seed(client, text="Analyze genomic variant data", conn_name="opencode")
    r = client.get(ASSISTANT_URL)
    assert r.status_code == 200
    assert "Step 4 of 5: Create Assistant" in r.text
    assert "Set up your first assistant" in r.text
    assert "Permissions &amp; Execution Boundaries" in r.text
    assert "Human-in-the-loop approvals" in r.text
    assert "Isolated workspace" in r.text
    assert "Analyze genomic variant data" in r.text


def test_post_without_csrf_is_forbidden(client):
    seed(client)
    r = client.post(ASSISTANT_URL, data={"name": "my-bot", "revision": "1"})
    assert r.status_code == 403


def test_post_with_blank_name_returns_422(client):
    seed(client)
    token = csrf(client)
    r = client.post(ASSISTANT_URL, data={"csrf": token, "revision": "1", "name": "   "})
    assert r.status_code == 422
    assert "Choose a short identifier" in r.text


def test_post_with_duplicate_bot_name_returns_409(client):
    seed(client)
    token = csrf(client)
    from hutch.models import Bot
    client.app.state.store.create_bot(Bot(name="existing-bot", display_name="Existing"))

    r = client.post(ASSISTANT_URL, data={
        "csrf": token,
        "revision": "1",
        "name": "existing-bot",
        "display_name": "New Display",
    })
    assert r.status_code == 409
    assert "already exists" in r.text


def test_post_valid_creates_bot_and_advances_setup(client):
    seed(client, text="Organize project milestones", conn_name="opencode")
    token = csrf(client)
    r = client.post(ASSISTANT_URL, data={
        "csrf": token,
        "revision": "1",
        "name": "project-lead",
        "display_name": "Project Lead",
        "model": "opencode/opencode-go/beam-free",
        "instructions": "Be precise and organized.",
    }, follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] == "/onboarding/first-request"

    bot = client.app.state.store.get_bot("project-lead")
    assert bot is not None
    assert bot.display_name == "Project Lead"
    assert bot.model == "opencode/opencode-go/beam-free"
    assert bot.approval_mode.value == "ask"
    assert bot.workspace_mode == "fresh"

    rec = stored(client)
    assert rec["step"] == "first_request"
    assert rec["assistant_id"] == bot.id
