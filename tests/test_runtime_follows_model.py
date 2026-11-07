"""A person chooses a model, never a runtime (owner report: "model setup also doesn't work").

Against a real OpenCode install, saving an OpenCode model as the workspace default failed with "belongs to the OpenCode
runtime", and the API happily created an assistant that pairs an OpenCode route with Hutch's own runtime, which can never
run. The runtime now follows the model everywhere a model is chosen, and an explicit mismatch is refused with a plain reason.
These tests run without OpenCode installed (its catalogue is not consulted for a route's shape).
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from hutch.route_problem import runtime_for_route
from hutch.server.app import create_app

OPENCODE = "opencode/opencode/glm-flash-free"


def _ack_sharing(client, bot: str, model: str) -> None:
    """A hosted route change needs the EC-28 data-sharing confirmation first."""
    token = re.search(r'name="csrf" content="([^"]+)"', client.get("/models").text).group(1)
    response = client.post(f"/api/bots/{bot}/model-sharing", json={"model": model, "scope": "default"},
                           headers={"x-csrf-token": token})
    assert response.status_code == 200, response.text


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    monkeypatch.setenv("PATH", "/nonexistent")          # no OpenCode CLI: only the route's shape matters here
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.mark.parametrize("model,runtime", [(OPENCODE, "opencode"), ("OpenCode/x/y", "opencode"), ("ollama/llama3.2:3b", "builtin"),
                                           ("openai/gpt-4o", "builtin"), ("", "builtin"), ("mock/demo", "builtin")])
def test_the_runtime_a_route_needs(model, runtime):
    assert runtime_for_route(model).value == runtime


def test_the_workspace_default_can_be_an_opencode_model(client):
    saved = client.put("/api/v1/preferences/model-defaults", json={"model": OPENCODE, "inference_mode": "hybrid"})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/v1/preferences/model-defaults").json()["model"] == OPENCODE


def test_an_assistant_created_without_a_runtime_gets_the_one_its_model_needs(client):
    created = client.post("/api/bots", json={"name": "juno", "display_name": "Juno", "model": OPENCODE, "tools": []})
    assert created.status_code == 201, created.text
    assert created.json()["runtime"] == "opencode"
    local = client.post("/api/bots", json={"name": "scribe", "display_name": "Scribe", "model": "ollama/llama3.2:3b", "tools": []})
    assert local.status_code == 201 and local.json()["runtime"] == "builtin"


def test_an_assistant_created_from_an_opencode_default_follows_it(client):
    client.put("/api/v1/preferences/model-defaults", json={"model": OPENCODE, "inference_mode": "hybrid"})
    created = client.post("/api/bots", json={"name": "inherits", "display_name": "Inherits", "tools": []})
    assert created.status_code == 201, created.text
    assert created.json()["runtime"] == "opencode" and created.json()["model"] == OPENCODE


def test_an_explicit_mismatch_is_refused_with_a_plain_reason_not_saved_broken(client):
    refused = client.post("/api/bots", json={"name": "broken", "display_name": "Broken", "model": OPENCODE, "runtime": "builtin", "tools": []})
    assert refused.status_code == 422 and "runs on the opencode runtime" in refused.text
    assert client.get("/api/bots/broken").status_code == 404, "nothing was saved"


def test_choosing_a_model_on_an_existing_assistant_brings_its_runtime(client):
    client.post("/api/bots", json={"name": "mover", "display_name": "Mover", "model": "ollama/llama3.2:3b", "tools": []})
    _ack_sharing(client, "mover", OPENCODE)
    moved = client.patch("/api/bots/mover", json={"model": OPENCODE})
    assert moved.status_code == 200, moved.text
    assert moved.json()["runtime"] == "opencode" and moved.json()["model"] == OPENCODE
    back = client.patch("/api/bots/mover", json={"model": "ollama/llama3.2:3b"})
    assert back.status_code == 200 and back.json()["runtime"] == "builtin"


def test_the_dashboards_creation_route_makes_the_first_assistant_the_main_one(client):
    """The dashboard creates through /api/v1/bots, not /api/bots: the rule has to hold on that route (it did not)."""
    body = {"name": "juno", "display_name": "Juno", "model": "ollama/llama3.2:3b", "tools": []}
    created = client.post("/api/v1/bots", json=body, headers={"Idempotency-Key": "first-assistant"})
    assert created.status_code == 201, created.text
    assert created.json()["is_workspace_coordinator"] is True
    second = client.post("/api/v1/bots", json={**body, "name": "scribe", "display_name": "Scribe"}, headers={"Idempotency-Key": "second"})
    assert second.status_code == 201 and second.json()["is_workspace_coordinator"] is False
