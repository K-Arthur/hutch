"""Grounding API: bundles, frame serving with hash verification, capability config."""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from hutch.config import get_config
from hutch.models import Bot, Run
from hutch.server.app import create_app
from hutch.store import Store


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def _seed(tmp_path):
    store = Store(get_config())
    inv = store.create_investigation(question="did the bridge reopen?",
                                     reference_instant="2026-10-11T12:00:00+00:00",
                                     horizon_hours=24, user_timezone="UTC")
    store.record_query_attempts(inv["id"], [{"adapter": "feeds", "state": "ok", "retained": 1,
                                             "disabled_engines": ["bing news"], "latency_ms": 12.5}])
    store.record_sources(inv["id"], [{
        "adapter": "feeds", "url": "https://news.example/bridge", "title": "Bridge reopened",
        "origin_id": "https://news.example/bridge", "retrieved_at": "2026-10-11T12:00:01+00:00",
        "published": {"raw": "2026-10-11T08:00:00Z", "role": "publication", "method": "rfc822",
                      "precision": "second", "instant": "2026-10-11T08:00:00+00:00"},
        "excerpt": "Officials said the bridge reopened at noon."}])
    frame_bytes = b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-serving"
    frame_dir = get_config().state_dir / "grounding" / "media" / "run_api"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_path = frame_dir / "frame-0.jpg"
    frame_path.write_bytes(frame_bytes)
    media = store.add_media(inv["id"], origin="https://news.example/bridge.jpg", local_path=str(frame_path),
                            kind="image", mime="image/jpeg", byte_size=len(frame_bytes),
                            sha256=hashlib.sha256(frame_bytes).hexdigest(),
                            frames=[{"at_ms": 0, "path": str(frame_path),
                                     "sha256": hashlib.sha256(frame_bytes).hexdigest()}])
    store.add_observation(inv["id"], kind="model_input", text="1 frame transmitted",
                          media_id=media, transmitted_json={"transmitted": 1})
    return store, inv, media


def test_investigation_bundle_is_parsed_and_served(app_client, tmp_path):
    store, inv, media = _seed(tmp_path)
    response = app_client.get(f"/api/v1/investigations/{inv['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["investigation"]["question"].startswith("did the bridge")
    assert body["attempts"][0]["disabled_engines_json"] == ["bing news"]
    published = body["sources"][0]["published_json"]
    assert published["role"] == "publication" and published["instant"] == "2026-10-11T08:00:00+00:00"
    assert body["answers"] == []
    frame = body["media"][0]["frames"][0]
    assert frame["available"] and frame["url"].startswith(f"/api/v1/investigations/{inv['id']}/media/")
    served = app_client.get(frame["url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert served.content == b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-serving"
    # tampering with the stored derivative is detected, not served
    from pathlib import Path
    Path(body["media"][0]["local_path"]).write_bytes(b"tampered")
    mismatch = app_client.get(frame["url"])
    assert mismatch.status_code == 409
    store.close()


def test_run_investigation_endpoint_is_empty_for_a_plain_run(app_client):
    store = Store(get_config())
    bot = store.create_bot(Bot(name="gap-bot", model="mock/demo", tools=[]))
    run = store.create_run(Run(bot_id=bot.id, prompt="hello"))
    body = app_client.get(f"/api/v1/tasks/runs/{run.id}/investigation").json()
    assert body["investigation"] is None and body["sources"] == []
    store.close()


def test_frame_route_rejects_paths_outside_the_state_dir(app_client, tmp_path):
    store, inv, media = _seed(tmp_path)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"\xff\xd8\xffoutside")
    rogue = store.add_media(inv["id"], origin="https://news.example/rogue.jpg", local_path=str(outside),
                            kind="image", mime="image/jpeg", byte_size=outside.stat().st_size,
                            sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
                            frames=[{"at_ms": 0, "path": str(outside),
                                     "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()}])
    frame = store.investigation_bundle(inv["id"])["media"][-1]["frames"][0]
    response = app_client.get(f"/api/v1/investigations/{inv['id']}/media/{rogue}/frames/{frame['id']}")
    assert response.status_code == 404
    store.close()


def test_grounding_config_lists_lanes_without_claiming_connections(app_client):
    body = app_client.get("/api/v1/grounding/config").json()
    assert "news" in body["lanes"] and "social" in body["lanes"]
    assert "feeds" in body["lanes"]
    assert body["searxng"]["configured"] is False
    assert body["media"]["reverse_image"]["state"] == "unsupported"
    assert body["streams"]["wikimedia"]["verified_on"]
