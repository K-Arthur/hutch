"""The computer-session state API and the verified frame route."""

from __future__ import annotations

import os
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from hutch.computer.frames import FrameStore
from hutch.config import get_config
from hutch.models import Bot, Event, EventType, Run, RunStatus
from hutch.server.app import create_app


def _png(width: int, height: int, fill: int) -> bytes:
    raw = b"".join(b"\x00" + bytes([fill]) * width for _ in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture()
def seeded(config):
    app = create_app()
    store = app.state.store
    bot = Bot(name="desk-bot", model="ollama/qwen3:4b", tools=["computer"], computer_apps=["kwrite"])
    store.upsert_bot(bot)
    run = store.create_run(Run(bot_id=bot.id, prompt="edit a note", status=RunStatus.running))
    frames = FrameStore(get_config().run_dir(bot.name, run.id))
    ref = frames.save(_png(64, 40, 0x55), "image/png")
    store.append_event(Event(run_id=run.id, type=EventType.log, data={
        "kind": "computer_control", "surface": "desktop", "owner": "agent", "generation": 1, "reason": "session started",
        "fresh_observation_required": True}))
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        "tool": "computer", "ok": True, "output": "observed", "frames": [ref.public()],
        "observation": {"schema": 1, "surface": {"kind": "desktop_screen", "id": "screen-0"},
                        "captured_at": "2026-10-10T17:00:00.000+00:00",
                        "environment": {"mode": "isolated", "applications": ["kwrite"]}}}))
    store.flush_events()
    return TestClient(app), store, run, bot, frames, ref


def test_state_describes_control_environment_and_the_latest_frame(seeded):
    client, _, run, _, _, ref = seeded
    body = client.get(f"/api/v1/tasks/runs/{run.id}/computer").json()
    assert body["active"] is True and body["surface"] == "desktop"
    assert body["control"]["owner"] == "agent" and body["control"]["generation"] == 1
    assert body["environment"]["applications"] == ["kwrite"]
    assert body["frame"]["frame_id"] == ref.frame_id and body["frame"]["url"].endswith(f"/frames/{ref.frame_id}")
    assert "path" not in body["frame"] and "path" not in str(body)
    assert body["remote_control"] is False and "not available" in body["remote_control_note"]
    assert body["human_needed_seq"] == 0


def test_a_run_that_never_used_a_surface_reports_inactive(config):
    app = create_app()
    store = app.state.store
    bot = Bot(name="plain-bot", model="ollama/qwen3:4b", tools=["files"])
    store.upsert_bot(bot)
    run = store.create_run(Run(bot_id=bot.id, prompt="hello", status=RunStatus.running))
    body = TestClient(app).get(f"/api/v1/tasks/runs/{run.id}/computer").json()
    assert body["active"] is False and body["frame"] is None


def test_the_frame_route_serves_verified_bytes_with_safe_headers(seeded):
    client, _, run, _, frames, ref = seeded
    response = client.get(f"/api/v1/tasks/runs/{run.id}/frames/{ref.frame_id}")
    assert response.status_code == 200
    assert response.content == frames.load(ref)
    headers = response.headers
    assert headers["content-type"] == "image/png" and headers["x-content-type-options"] == "nosniff"
    assert headers["cache-control"] == "no-store" and headers["x-hutch-frame-verified"] == "sha256"
    assert "default-src 'none'" in headers["content-security-policy"]


def test_unknown_malformed_foreign_and_tampered_frames_are_not_served(seeded):
    client, store, run, bot, frames, ref = seeded
    assert client.get(f"/api/v1/tasks/runs/{run.id}/frames/f999999").status_code == 404
    assert client.get(f"/api/v1/tasks/runs/{run.id}/frames/..%2F..%2Fetc").status_code in (404, 422)
    assert client.get(f"/api/v1/tasks/runs/{run.id}/frames/F000001").status_code == 404
    # a different run cannot read this run's frame even if it knows the id
    other = store.create_run(Run(bot_id=bot.id, prompt="other", status=RunStatus.running))
    assert client.get(f"/api/v1/tasks/runs/{other.id}/frames/{ref.frame_id}").status_code == 404
    # tampered content fails verification instead of being served
    path = get_config().run_dir(bot.name, run.id) / ref.path
    os.chmod(path, 0o600)
    path.write_bytes(_png(64, 40, 0x99))
    assert client.get(f"/api/v1/tasks/runs/{run.id}/frames/{ref.frame_id}").status_code == 410


def test_waiting_for_a_person_exposes_the_event_to_resume(seeded):
    client, store, run, _, _, _ = seeded
    store.append_event(Event(run_id=run.id, type=EventType.human_needed, data={"reason": "log in", "url": "https://x.example"}))
    store.flush_events()
    store.set_status(run, RunStatus.waiting_human)
    body = client.get(f"/api/v1/tasks/runs/{run.id}/computer").json()
    assert body["run_status"] == "waiting_human" and body["human_needed_seq"] > 0


def test_a_bot_cannot_be_approved_to_open_hutchs_own_dashboard(config, monkeypatch):
    monkeypatch.setenv("HUTCH_DASHBOARD_PORT", "9911")
    client = TestClient(create_app())
    headers = {"Idempotency-Key": "computer-origin-test-1"}
    body = {"name": "dash-bot", "model": "ollama/qwen3:4b", "local_dev_origins": ["http://localhost:9911"]}
    refused = client.post("/api/v1/bots", json=body, headers=headers)
    assert refused.status_code == 422 and "own dashboard" in refused.text, refused.text
    ok = {**body, "name": "dev-bot", "local_dev_origins": ["http://localhost:3000"]}
    created = client.post("/api/v1/bots", json=ok, headers={"Idempotency-Key": "computer-origin-test-2"})
    assert created.status_code in (200, 201), created.text
    stored = client.get("/api/bots/dev-bot").json()
    assert stored.get("local_dev_origins") == ["http://localhost:3000"], stored
    bad = client.post("/api/v1/bots", json={**ok, "name": "bad-apps", "computer_apps": ["/usr/bin/kwrite"]},
                      headers={"Idempotency-Key": "computer-origin-test-3"})
    assert bad.status_code == 422 and "computer_apps" in bad.text
