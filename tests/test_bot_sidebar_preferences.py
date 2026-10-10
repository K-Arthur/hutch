from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as test_client:
        yield test_client


def test_bot_sidebar_hide_and_sections_are_durable_preferences(client):
    store = client.app.state.store
    bot = store.create_bot(Bot(name="project-reviewer", model="mock/demo", tools=[]))
    coordinator = store.create_bot(Bot(name="workspace-coordinator", model="mock/demo", tools=[]))
    store.set_workspace_coordinator(coordinator.id)

    changed = client.patch(f"/api/bots/{bot.id}", json={
        "sidebar_hidden": True,
        "roster_section": "  Client   work  ",
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["sidebar_hidden"] is True
    assert changed.json()["roster_section"] == "Client work"

    reopened = client.get(f"/api/bots/{bot.id}")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["sidebar_hidden"] is True
    assert reopened.json()["roster_section"] == "Client work"

    cleared = client.patch(f"/api/bots/{bot.id}", json={"roster_section": "   ", "sidebar_hidden": False})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["sidebar_hidden"] is False
    assert cleared.json()["roster_section"] is None


def test_workspace_coordinator_cannot_be_hidden_or_grouped(client):
    coordinator = client.app.state.store.create_bot(
        Bot(name="workspace-coordinator", model="mock/demo", tools=[]))
    client.app.state.store.set_workspace_coordinator(coordinator.id)

    hidden = client.patch(f"/api/bots/{coordinator.id}", json={"sidebar_hidden": True})
    assert hidden.status_code == 409
    grouped = client.patch(f"/api/bots/{coordinator.id}", json={"roster_section": "Operations"})
    assert grouped.status_code == 409


def test_roster_section_names_are_bounded(client):
    bot = client.app.state.store.create_bot(Bot(name="bounded-section", model="mock/demo", tools=[]))

    result = client.patch(f"/api/bots/{bot.id}", json={"roster_section": "x" * 41})

    assert result.status_code == 422
    assert client.app.state.store.get_bot(bot.id).roster_section is None
