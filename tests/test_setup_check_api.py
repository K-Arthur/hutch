"""`GET /api/v1/setup/check`: the `hutch doctor` findings, read-only, for first run.

First run used to say nothing about whether the install was healthy or whether scheduled
work would run. This exposes the doctor's checks (no network, no deep probes) so the
first-run page can show what needs attention and offer the background service.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as test_client:
        yield test_client


def test_check_returns_the_doctor_findings_with_a_worst_status(client):
    response = client.get("/api/v1/setup/check")
    assert response.status_code == 200
    body = response.json()
    assert body["worst"] in ("ok", "warn", "fail")
    ids = {check["id"] for check in body["checks"]}
    assert {"python", "database", "permissions", "service"} <= ids
    for check in body["checks"]:
        assert set(check) == {"id", "title", "status", "detail", "fix"}
        assert check["status"] in ("ok", "warn", "fail", "info")


def test_check_reports_the_service_state_without_changing_it(client, monkeypatch):
    from hutch import service

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a read-only check must never install, start or stop the service")

    for name in ("install_user_service", "restart_user_service", "stop_user_service"):
        monkeypatch.setattr(service, name, forbidden, raising=False)
    body = client.get("/api/v1/setup/check").json()
    assert any(check["id"] == "service" for check in body["checks"])


def test_check_surfaces_a_failure_with_its_fix(client, monkeypatch):
    from hutch import doctor
    from hutch.doctor import Check

    monkeypatch.setattr(doctor, "run_doctor", lambda *a, **k: [
        Check("database", "Database", "fail", "integrity check failed", "restore from a snapshot with `hutch state`")])
    body = client.get("/api/v1/setup/check").json()
    assert body["worst"] == "fail"
    assert body["checks"][0]["fix"].startswith("restore from a snapshot")


def test_check_failure_is_a_clean_503_not_a_traceback(client, monkeypatch):
    from hutch import doctor

    def broken(*_args, **_kwargs):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(doctor, "run_doctor", broken)
    response = client.get("/api/v1/setup/check")
    assert response.status_code == 503
    assert "setup check" in response.json()["detail"].lower()
    assert "Traceback" not in response.text and "probe exploded" not in response.text


def test_paired_phones_cannot_read_the_check(client):
    """Every API route is registered with no capability, which `authorize_remote_route` answers with 403."""
    from hutch.server.app import REMOTE_ROUTE_CAPABILITIES
    assert ("GET", "/api/v1/setup/check") in REMOTE_ROUTE_CAPABILITIES
    assert REMOTE_ROUTE_CAPABILITIES[("GET", "/api/v1/setup/check")] is None
