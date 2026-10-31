"""Tests for contextual Getting Started checklist module (slice 09).

Validates facts-based progress calculation, experienced user suppression,
CSRF-protected dismissal, and dynamic percentage computation.
"""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, iso, utcnow
from hutch.onboarding import apply_request_edit, default_setup, encode_setup
from hutch.onboarding_store import SETUP_KEY
from hutch.server.app import create_app

GETTING_STARTED_API = "/api/v1/getting-started"
DISMISS_API = "/api/v1/getting-started/dismiss"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        yield c


def csrf(c) -> str:
    body = c.get("/onboarding").text
    match = re.search(r'<meta name="csrf" content="([^"]+)">', body)
    if not match:
        match = re.search(r'name="csrf" value="([^"]+)"', body)
    return match.group(1) if match else "test-csrf"


def test_fresh_installation_shows_checklist_with_zero_progress(client):
    r = client.get(GETTING_STARTED_API)
    assert r.status_code == 200
    data = r.json()
    assert data["visible"] is True
    assert data["completed_count"] == 0
    assert data["total_count"] == 5
    assert data["percentage"] == 0
    assert len(data["items"]) == 5


def test_checklist_progresses_with_actual_store_facts(client):
    now = utcnow()
    bot = client.app.state.store.create_bot(Bot(name="helper", display_name="Helper"))
    result = apply_request_edit(default_setup(now), expected_revision=0, request_text="A real task", now=now)
    setup = result.setup.model_copy(update={
        "connection_name": "opencode",
        "assistant_id": bot.id,
        "first_request_completed_at": iso(now),
    })
    client.app.state.store.kv_set(SETUP_KEY, encode_setup(setup))

    r = client.get(GETTING_STARTED_API)
    assert r.status_code == 200
    data = r.json()
    assert data["visible"] is True
    assert data["completed_count"] >= 4
    assert data["percentage"] >= 80

    items_by_id = {item["id"]: item for item in data["items"]}
    assert items_by_id["request"]["completed"] is True
    assert items_by_id["connection"]["completed"] is True
    assert items_by_id["assistant"]["completed"] is True
    assert items_by_id["first_run"]["completed"] is True


def test_experienced_user_with_multiple_bots_never_sees_checklist(client):
    client.app.state.store.create_bot(Bot(name="bot-1", display_name="Bot 1"))
    client.app.state.store.create_bot(Bot(name="bot-2", display_name="Bot 2"))

    r = client.get(GETTING_STARTED_API)
    assert r.status_code == 200
    data = r.json()
    assert data["visible"] is False


def test_dismiss_checklist_hides_it_permanently(client):
    token = csrf(client)
    # Dismissing without CSRF is rejected
    r_bad = client.post(DISMISS_API)
    assert r_bad.status_code == 403

    # Dismissing with valid CSRF succeeds
    r_ok = client.post(DISMISS_API, headers={"x-csrf-token": token})
    assert r_ok.status_code == 200
    assert r_ok.json()["status"] == "dismissed"

    # Subsequent GET returns visible = False
    r_after = client.get(GETTING_STARTED_API)
    assert r_after.status_code == 200
    assert r_after.json()["visible"] is False
    assert r_after.json()["dismissed"] is True
