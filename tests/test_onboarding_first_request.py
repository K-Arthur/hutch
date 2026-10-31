"""Tests for onboarding first request execution and approval intro (slice 08).

Validates review rendering, human-in-the-loop protection explanations, CSRF checks,
task submission, and setup completion timestamp recording.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, iso, utcnow
from hutch.onboarding import apply_request_edit, default_setup, encode_setup
from hutch.onboarding_store import SETUP_KEY
from hutch.server.app import create_app

FIRST_REQUEST_URL = "/onboarding/first-request"
RUN_URL = "/onboarding/first-request/run"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        yield c


def seed(c, *, text="Summarise today's release notes"):
    now = utcnow()
    bot = c.app.state.store.create_bot(Bot(name="pilot-bot", display_name="Pilot Bot", model="test/model"))
    result = apply_request_edit(default_setup(now), expected_revision=0, request_text=text, now=now)
    assert result.kind == "accepted" and result.setup is not None
    setup = result.setup.model_copy(update={
        "resume_expires_at": iso(now + timedelta(days=30)),
        "route_kind": "opencode",
        "connection_name": "opencode",
        "assistant_id": bot.id,
        "step": "first_request",
    })
    c.app.state.store.kv_set(SETUP_KEY, encode_setup(setup))
    return setup, bot


def stored(c) -> dict:
    return json.loads(c.app.state.store.kv_get(SETUP_KEY))


def csrf(c) -> str:
    body = c.get(FIRST_REQUEST_URL).text
    match = re.search(r'<meta name="csrf" content="([^"]+)">', body)
    if not match:
        match = re.search(r'name="csrf" value="([^"]+)"', body)
    return match.group(1) if match else "test-csrf"


def test_get_without_request_redirects_to_onboarding(client):
    r = client.get(FIRST_REQUEST_URL, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/onboarding"


def test_get_with_request_renders_step_and_protections(client):
    seed(client, text="Compile system health report")
    r = client.get(FIRST_REQUEST_URL)
    assert r.status_code == 200
    assert "Step 5 of 5: First Request" in r.text
    assert "Review and run your first request" in r.text
    assert "Compile system health report" in r.text
    assert "Pilot Bot" in r.text
    assert "Human-in-the-loop protection" in r.text


def test_post_without_csrf_is_forbidden(client):
    seed(client)
    r = client.post(RUN_URL, data={"request": "Hello", "revision": "1"})
    assert r.status_code == 403


def test_post_with_blank_request_returns_422(client):
    seed(client)
    token = csrf(client)
    r = client.post(RUN_URL, data={"csrf": token, "revision": "1", "request": "   "})
    assert r.status_code == 422
    assert "Please enter a task" in r.text


def test_post_valid_submits_and_marks_completed(client):
    setup, bot = seed(client, text="Compile system health report")
    token = csrf(client)
    r = client.post(RUN_URL, data={
        "csrf": token,
        "revision": str(setup.revision),
        "request": "Compile system health report",
    }, follow_redirects=False)

    assert r.status_code == 303
    assert "/onboarding/first-request?" in r.headers["location"]
    assert "submitted=1" in r.headers["location"]

    rec = stored(client)
    assert rec["first_request_completed_at"]

    follow = client.get(r.headers["location"])
    assert follow.status_code == 200
    assert "Your task is on its way" in follow.text
    assert "Execution Status" in follow.text
