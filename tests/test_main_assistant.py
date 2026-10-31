"""The first assistant a person creates is their main assistant (the workspace coordinator).

Rule borrowed from OpenClaw's team creation: the first coordinator becomes the system agent only when none
is set, and an existing owner is kept. Creating more assistants never moves the role, and nothing is
decided for a person who already chose a coordinator.
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


def _create(client, name, display):
    response = client.post("/api/bots", json={"name": name, "display_name": display, "model": "ollama/llama3.2:3b", "tools": []})
    assert response.status_code == 201, response.text
    return response.json()


def _coordinator(client):
    return client.get("/api/v1/workspace/coordinator").json()["coordinator"]


def test_the_first_assistant_becomes_the_main_assistant(client):
    assert _coordinator(client) is None
    first = _create(client, "juno", "Juno")
    assert _coordinator(client)["name"] == "juno"
    assert first["is_workspace_coordinator"] is True


def test_later_assistants_do_not_take_the_role(client):
    _create(client, "juno", "Juno")
    second = _create(client, "scribe", "Scribe")
    assert _coordinator(client)["name"] == "juno"
    assert second["is_workspace_coordinator"] is False


def test_a_coordinator_the_person_already_chose_is_kept(client):
    store = client.app.state.store
    from hutch.models import Bot
    store.create_bot(Bot(name="chosen", display_name="Chosen", model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator("chosen")
    _create(client, "newcomer", "Newcomer")
    assert _coordinator(client)["name"] == "chosen"


def test_after_every_assistant_is_gone_the_next_first_one_is_the_main_assistant(client):
    _create(client, "juno", "Juno")
    client.app.state.store.delete_bot("juno")
    assert _coordinator(client) is None
    _create(client, "river", "River")
    assert _coordinator(client)["name"] == "river"
