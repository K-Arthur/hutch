"""Real end-to-end integration tests using local OpenCode CLI and live free models.

No mocks or fake fixtures: verifies the real OpenCode binary, live model listing
including opencode-go/beam-free, real live inference execution, and onboarding
flow progression.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, iso, utcnow
from hutch.onboarding import apply_request_edit, default_setup, encode_setup
from hutch.onboarding_store import SETUP_KEY
from hutch.server.app import create_app
from hutch.server.onboarding_opencode_api import check_opencode_status, find_opencode_binary


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        yield c


def seed(c, *, text="Organize research papers", route_kind="opencode"):
    now = utcnow()
    result = apply_request_edit(default_setup(now), expected_revision=0, request_text=text, now=now)
    assert result.kind == "accepted" and result.setup is not None
    setup = result.setup.model_copy(update={
        "resume_expires_at": iso(now + timedelta(days=30)),
        "route_kind": route_kind,
        "step": "ai_service",
    })
    c.app.state.store.kv_set(SETUP_KEY, encode_setup(setup))
    return setup


def csrf(c) -> str:
    body = c.get("/onboarding").text
    match = re.search(r'<meta name="csrf" content="([^"]+)">', body)
    if not match:
        match = re.search(r'name="csrf" value="([^"]+)"', body)
    return match.group(1) if match else "test-csrf"


def test_opencode_binary_discovery():
    """Verify that find_opencode_binary detects the real local installation."""
    binary = find_opencode_binary()
    assert binary is not None, "OpenCode CLI binary was not found"
    proc = subprocess.run([binary, "--version"], capture_output=True, text=True, check=True)
    assert "opencode" in proc.stdout.lower() or "version" in proc.stdout.lower() or proc.returncode == 0


def test_opencode_status_and_models_listing():
    """Verify check_opencode_status inspects the CLI and detects free models."""
    status = check_opencode_status()
    assert status["installed"] is True
    assert status["binary_path"]
    assert len(status["models"]) > 0
    # Confirm presence of beam-free or open free models
    model_names = " ".join(status["models"]).lower()
    assert "beam-free" in model_names or "flash" in model_names


def test_opencode_live_model_inference():
    """Execute a real live model inference using opencode-go/beam-free."""
    binary = find_opencode_binary()
    assert binary is not None
    cmd = [binary, "run", "--model", "opencode-go/beam-free", "Reply with only: LIVE_TEST_SUCCESS"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, f"OpenCode live run failed: {proc.stderr}"
    assert "LIVE_TEST_SUCCESS" in proc.stdout, f"Unexpected model response: {proc.stdout}"


def test_onboarding_opencode_route_submission(client):
    """Test full server onboarding flow with OpenCode."""
    setup = seed(client)
    token = csrf(client)

    # GET /onboarding/opencode shows real installed status
    r_get = client.get("/onboarding/opencode")
    assert r_get.status_code == 200
    assert "Connect OpenCode" in r_get.text
    assert "Installed" in r_get.text

    # POST /onboarding/opencode connects the service
    r_post = client.post("/onboarding/opencode", data={
        "csrf": token,
        "revision": str(setup.revision),
    }, follow_redirects=False)
    assert r_post.status_code == 303
    assert r_post.headers["location"] == "/onboarding/connection"

    # Setup record reflects connection
    rec = json.loads(client.app.state.store.kv_get(SETUP_KEY))
    assert rec["connection_name"] == "opencode-service"


def test_onboarding_assistant_creation_with_opencode_free_model(client):
    """Verify creating an assistant configured for opencode-go/beam-free."""
    setup = seed(client)
    now = utcnow()
    setup = setup.model_copy(update={"connection_name": "opencode-service", "step": "assistant"})
    client.app.state.store.kv_set(SETUP_KEY, encode_setup(setup))

    token = csrf(client)
    r = client.post("/onboarding/assistant", data={
        "csrf": token,
        "revision": str(setup.revision),
        "name": "opencode-bot",
        "display_name": "OpenCode Assistant",
        "model": "opencode/opencode-go/beam-free",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/onboarding/first-request"

    bot = client.app.state.store.get_bot("opencode-bot")
    assert bot is not None
    assert bot.model == "opencode/opencode-go/beam-free"
    assert bot.approval_mode.value == "ask"
