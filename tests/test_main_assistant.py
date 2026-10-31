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


def test_the_main_assistant_is_always_a_local_owned_assistant(client):
    """A9: the role can only name an assistant that exists in this workspace's store.

    Hutch has no remote or shared assistants, and a catalog entry is reviewed and created as the
    person's own local copy (see catalog.py and the setup review), so a catalog copy is eligible
    exactly like a hand-made assistant — never by reference to someone else's bot.
    """
    missing = client.put("/api/v1/workspace/coordinator", json={"bot_id": "not-a-bot"})
    assert missing.status_code == 404
    from hutch.templates import instantiate
    store = client.app.state.store
    copy = instantiate("day-planner", "planner-copy")
    store.create_bot(copy)
    assert client.put("/api/v1/workspace/coordinator", json={"bot_id": copy.id}).status_code == 200
    assert _coordinator(client)["name"] == "planner-copy"


def test_after_every_assistant_is_gone_the_next_first_one_is_the_main_assistant(client):
    _create(client, "juno", "Juno")
    client.app.state.store.delete_bot("juno")
    assert _coordinator(client) is None
    _create(client, "river", "River")
    assert _coordinator(client)["name"] == "river"


def test_a_workspace_that_has_assistants_but_no_main_gets_one_from_the_next_assistant_created(client):
    """Owner report: a workspace that predates the main assistant had no way to get one, and there is no setting for it."""
    from hutch.models import Bot
    store = client.app.state.store
    store.create_bot(Bot(name="older", display_name="Older", model="ollama/llama3.2:3b", tools=[]))
    assert _coordinator(client) is None
    created = _create(client, "fresh", "Fresh")
    assert _coordinator(client)["name"] == "fresh" and created["is_workspace_coordinator"] is True


def test_a_leftover_on_the_retired_demo_route_is_never_made_the_main_assistant(client):
    created = client.post("/api/bots", json={"name": "old-demo", "display_name": "Old Demo", "model": "mock/demo", "tools": []})
    if created.status_code == 201:
        assert _coordinator(client) is None, "a dead route is not a main assistant"
