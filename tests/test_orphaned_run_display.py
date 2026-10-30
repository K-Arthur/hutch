"""A run whose owner process is gone stops showing as "Working" and ends as interrupted.

The audit (S8) feared a "Working" row that nothing would ever finish. The engine recovers
runs whose owner has exited (lease lapsed, or for pre-lease rows a dead pid). This pins that
guarantee against a *real* process that has exited, through the API a person's header and
Activity page read. The orphan is seeded before the app starts so the running supervisor is
the only thing that can recover it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from hutch.config import get_config
from hutch.doctor import run_doctor
from hutch.models import Bot, Run, RunStatus
from hutch.server.app import create_app
from hutch.store import Store


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()


def _exited_pid() -> str:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=30)
    return str(process.pid)


def _seed(owner: str) -> str:
    """Write a `running` run owned by `owner` into the state directory, with no app running."""
    config = get_config()
    store = Store(config)
    try:
        bot = store.create_bot(Bot(name="orphan-check", display_name="Orphan Check", tools=[]))
        run = store.create_run(Run(bot_id=bot.id, prompt="tidy my downloads", status=RunStatus.running, owner=owner))
        assert store.get_run(run.id).status is RunStatus.running
        return run.id
    finally:
        store.close()


def _wait_for(client, run_id, timeout=20.0):
    deadline = time.monotonic() + timeout
    run = client.get(f"/api/runs/{run_id}").json()
    while run["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.2)
        run = client.get(f"/api/runs/{run_id}").json()
    return run


def test_the_supervisor_recovers_a_dead_owner_run_and_it_stops_being_working():
    run_id = _seed(_exited_pid())
    with TestClient(create_app()) as client:
        run = _wait_for(client, run_id)
        assert run["status"] == "failed" and run["terminal"] is True, run["status"]
        assert run["status_label"] != "Working"
        assert run["exit_reason"] == "interrupted"
        assert "exited before it finished" in run["error"]
        assert client.get("/api/stats").json()["working_runs"] == 0, "the header stops saying Working"


def test_a_run_whose_owner_is_alive_is_left_alone():
    run_id = _seed(str(os.getpid()))
    with TestClient(create_app()) as client:
        time.sleep(2.5)  # several supervisor beats
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "running"


def test_the_doctor_reports_the_orphan_while_nothing_is_supervising():
    _seed(_exited_pid())
    config = get_config()
    store = Store(config)
    try:
        checks = {c.id: c for c in run_doctor(config, store)}
    finally:
        store.close()
    assert checks["orphans"].status == "warn"
    assert "exited" in checks["orphans"].detail
    assert "next time" in checks["orphans"].fix
