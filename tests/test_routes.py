"""One read authority for AI services, routes and assistant routing (owner addendum R7/R8).

The workspace default is parsed in exactly one place, every assistant's saved routes are summarized with the
same shape truth the run validator uses, and the API is read-only. Saving a default that cannot seed a
built-in assistant is refused.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from hutch import routes
from hutch.models import Bot, InferenceMode, RuntimeKind
from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as test_client:
        yield test_client


def _bots(client):
    store = client.app.state.store
    broken = store.create_bot(Bot(name="design-partner", display_name="Design Partner",
                                  model="demo", tools=[]))
    good = store.create_bot(Bot(name="repo-sweeper", display_name="Repo Sweeper",
                                model="ollama/llama3.2:3b", tools=[]))
    store.create_bot(Bot(name="opencode-bot", display_name="OpenCode Bot", model="opencode/opencode/big-pickle",
                         runtime=RuntimeKind.opencode, tools=[]))
    store.set_workspace_coordinator(good.id)
    return broken, good


def test_the_workspace_default_has_one_parser_and_one_shape(client):
    store = client.app.state.store
    assert routes.workspace_default(store) == {"model": "", "inference_mode": "hybrid",
                                               "configured": False, "route_problem": None}
    store.kv_set("workspace:model-defaults", json.dumps({"model": "demo", "inference_mode": "local"}))
    default = routes.workspace_default(store)
    assert default["model"] == "demo" and default["inference_mode"] == "local"
    assert "provider/model" in default["route_problem"]
    store.kv_set("workspace:model-defaults", "{not json")
    damaged = routes._defaults_record(store)
    assert damaged["damaged"] is True and damaged["model"] == ""
    assert routes.workspace_default(store) == {"model": "", "inference_mode": "hybrid",
                                               "configured": False, "route_problem": None}


def test_the_authority_summarizes_services_assistants_and_warnings(client):
    _bots(client)
    store = client.app.state.store
    authority = routes.authority(store)
    assert authority["counts"] == {"assistants": 3, "usable": 2, "needs_model": 1}
    design = next(a for a in authority["assistants"] if a["name"] == "design-partner")
    assert design["usable"] is False and "provider/model" in design["route_problem"]
    assert design["fix_href"] == "/#/bot/design-partner"
    repo = next(a for a in authority["assistants"] if a["name"] == "repo-sweeper")
    assert repo["routes"] == [{"spec": "ollama/llama3.2:3b", "role": "primary"}]
    services = {service["id"]: service for service in authority["services"]}
    assert services["ollama"]["working"] == 1 and services["demo"]["needs_model"] == 1
    assert services["opencode"]["assistants"] == 1
    assert any("cannot run" in warning for warning in authority["warnings"])
    assert authority["one_destination"]["add_or_repair"] == "#/connections"


def test_the_routes_api_exposes_the_authority_read_only(client):
    _bots(client)
    before = (len(client.app.state.store.list_bots()), len(client.app.state.store.list_runs()))
    response = client.get("/api/v1/routes")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["assistants"] == 3
    assert {a["name"] for a in body["assistants"]} == {"design-partner", "repo-sweeper", "opencode-bot"}
    assert (len(client.app.state.store.list_bots()), len(client.app.state.store.list_runs())) == before


def test_a_default_that_cannot_run_is_refused(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    for spec in ("demo", "mock/demo"):
        response = client.put("/api/v1/preferences/model-defaults",
                              json={"model": spec, "inference_mode": "hybrid"})
        assert response.status_code == 422, (spec, response.text)
    assert client.get("/api/v1/preferences/model-defaults").json()["model"] == ""
    saved = client.put("/api/v1/preferences/model-defaults",
                       json={"model": "openai/gpt-4o-mini", "inference_mode": "hybrid"})
    assert saved.status_code == 200, saved.text


def test_an_opencode_model_is_a_valid_default_because_the_runtime_follows_the_model(client):
    """It used to be refused ("belongs to the OpenCode runtime"), which made the Models page's "Review in Settings, then save" fail."""
    saved = client.put("/api/v1/preferences/model-defaults", json={"model": "opencode/opencode/big-pickle", "inference_mode": "hybrid"})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/v1/preferences/model-defaults").json()["model"] == "opencode/opencode/big-pickle"
