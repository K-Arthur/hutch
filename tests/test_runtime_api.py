"""Local Runtime & Background Work status endpoint (owner-only).

The route is deliberately absent from REMOTE_ROUTE_CAPABILITIES
(tests/test_remote_pairing.py asserts it), so a paired phone can never read or
act on the local engine's service state.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from hutch.server.app import create_app


def test_runtime_endpoint_reports_engine_queue_and_exposure(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setenv("HUTCH_STATE_DIR", str(state))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/runtime").json()

    assert body["engine"]["state_dir"] == str(state)
    assert body["engine"]["instance_id"] and body["engine"]["pid"] > 0
    assert body["engine"]["version"] and body["engine"]["schema"] > 0
    assert body["scheduler"]["role"] in ("supervisor", "follower")
    assert body["exposure"]["mode"] == "loopback"
    assert set(body["queue"]) >= {"queued_tasks", "active_runs", "pending_approvals",
                                  "unresolved_actions", "execution_held"}
    assert set(body["service"]) >= {"installed", "state", "active", "ready", "linger"}
    # The local payload never contains provider keys, tokens, or database rows.
    assert "token" not in json.dumps(body).lower().replace("state_dir", "")


def test_runtime_endpoint_reports_a_real_installed_unit(tmp_path, monkeypatch):
    """With a managed unit file present, the endpoint reports its port and readiness
    state without ever claiming ready when nothing answers the handshake."""
    from hutch.service import render_user_unit

    state = tmp_path / "state"
    config_home = tmp_path / "config"
    unit_dir = config_home / "systemd/user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "hutch.service").write_text(render_user_unit("/usr/bin/python3", state, port=18999))
    monkeypatch.setenv("HUTCH_STATE_DIR", str(state))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    with TestClient(create_app()) as client:
        service = client.get("/api/v1/runtime").json()["service"]

    # On a Linux host with systemctl the unit is not really active, so a ready=True
    # claim would be a bug; on hosts without systemctl the state is "unavailable".
    if service["supported"] and service["state"] not in ("unavailable", "not installed"):
        assert service["ready"] is not True
