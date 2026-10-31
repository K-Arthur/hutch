"""An assistant that cannot run says so before anyone tries (no demo route looks healthy).

The mock runtime was removed, but an assistant whose saved route is still `mock/...` showed as
"Idle" with a model chip reading "demo", and only failed when someone sent a message. The server
now computes one answer, `route_problem`, from the assistant's saved route; the roster, the composer
chip and `/api/bots` all use it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.route_problem import route_problem
from hutch.server.app import create_app


@pytest.mark.parametrize("model,runtime_mock", [("", False), ("   ", False), ("mock/demo", False), ("MOCK/anything", False)])
def test_an_unusable_route_is_named(model, runtime_mock):
    problem = route_problem(Bot(name="needs-route", model=model, tools=[]))
    assert problem and ("no model route" in problem or "retired demo route" in problem)


@pytest.mark.parametrize("model", ["ollama/llama3.2:3b", "openai/gpt-4o-mini", "opencode/opencode/big-pickle", "anthropic/claude-sonnet"])
def test_a_real_route_has_no_problem(model):
    assert route_problem(Bot(name="ready", model=model, tools=[])) is None


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as test_client:
        yield test_client


def test_the_roster_api_carries_the_problem_for_the_ui(client):
    store = client.app.state.store
    store.create_bot(Bot(name="old-demo", display_name="Old Demo", model="mock/demo", tools=[]))
    store.create_bot(Bot(name="real-one", display_name="Real One", model="ollama/llama3.2:3b", tools=[]))
    by_name = {item["name"]: item for item in client.get("/api/bots").json()}
    assert "retired demo route" in by_name["old-demo"]["route_problem"]
    assert by_name["real-one"]["route_problem"] is None


def test_the_saved_workspace_default_carries_its_problem(client):
    """A legacy saved default is not shown as a usable route: first run reads the same server answer."""
    assert client.get("/api/v1/preferences/model-defaults").json()["route_problem"] is None
    client.app.state.store.kv_set("workspace:model-defaults",
                                  '{"model": "mock/demo", "inference_mode": "hybrid"}')
    legacy = client.get("/api/v1/preferences/model-defaults").json()
    assert legacy["model"] == "mock/demo" and "retired demo route" in legacy["route_problem"]
    client.app.state.store.kv_set("workspace:model-defaults",
                                  '{"model": "ollama/llama3.2:3b", "inference_mode": "hybrid"}')
    assert client.get("/api/v1/preferences/model-defaults").json()["route_problem"] is None
