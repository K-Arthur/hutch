"""Identity API: reviewed local text, revision CAS, and no effect on tool authority.

The routes are owner configuration: GET/PUT for the one workspace person profile and for one
assistant's boundaries. A stale revision is refused (409), invalid payloads are refused (422), and the
rendered block returned for review is exactly what the prompt builder will use.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as test_client:
        yield test_client


def test_person_profile_round_trip_and_revision_conflict(client):
    empty = client.get("/api/v1/identity/person").json()
    assert empty["profile"]["revision"] == 0 and len(empty["content_hash"]) == 64
    assert empty["rendered"] == "" and empty["shared_with_every_assistant"] is True

    saved = client.put("/api/v1/identity/person", json={
        "expected_revision": 0, "preferred_name": "Kev",
        "about": "Builds local-first tools.", "treat_person": "Direct, no praise sandwiches."})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["profile"]["revision"] == 1 and "Preferred name: Kev" in body["rendered"]

    stale = client.put("/api/v1/identity/person", json={
        "expected_revision": 0, "preferred_name": "Someone else", "about": "", "treat_person": ""})
    assert stale.status_code == 409 and "reload" in stale.json()["detail"]
    assert client.get("/api/v1/identity/person").json()["profile"]["preferred_name"] == "Kev"


def test_assistant_identity_round_trip_render_and_bounds(client):
    store = client.app.state.store
    store.create_bot(Bot(name="identity-bot", display_name="Identity Bot", tools=[]))
    assert client.get("/api/v1/bots/identity-bot/identity").json()["identity"]["revision"] == 0

    saved = client.put("/api/v1/bots/identity-bot/identity", json={
        "expected_revision": 0, "signature": "Done - reporting back.",
        "boundaries": [" Never publish without review ", "Do not email on my behalf"]})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["identity"]["revision"] == 1
    assert body["identity"]["boundaries"] == ["Never publish without review", "Do not email on my behalf"]
    assert "Never publish without review" in body["rendered"]

    refused = client.put("/api/v1/bots/identity-bot/identity", json={
        "expected_revision": 1, "signature": "", "boundaries": ["x"] * 9})
    assert refused.status_code == 422
    too_long = client.put("/api/v1/bots/identity-bot/identity", json={
        "expected_revision": 1, "signature": "", "boundaries": ["x" * 201]})
    assert too_long.status_code == 422

    assert client.get("/api/v1/bots/missing-bot/identity").status_code == 404
