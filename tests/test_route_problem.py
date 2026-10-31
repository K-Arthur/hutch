"""An assistant that cannot run says so before anyone tries (no unusable route looks healthy).

Demo-era rows may carry `mock/...` (retired runtime) or a bare value like `demo` that is not a route at
all. Both used to read "Idle" with a chip showing the raw last segment, and only failed when a message was
sent. The server computes one answer, `route_problem`, whose shape rules mirror the send-time validator;
the roster, composer chip, settings and `/api/bots` all use it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, RuntimeKind
from hutch.route_problem import route_problem
from hutch.server.app import create_app


def _bot(model, runtime=RuntimeKind.builtin):
    return Bot(name="needs-route", model=model, runtime=runtime, tools=[])


@pytest.mark.parametrize("model,runtime,expected", [
    ("", RuntimeKind.builtin, "no model route"),
    ("   ", RuntimeKind.builtin, "no model route"),
    ("demo", RuntimeKind.builtin, "provider/model"),
    ("demo/", RuntimeKind.builtin, "provider/model"),
    ("/demo", RuntimeKind.builtin, "provider/model"),
    ("mock/demo", RuntimeKind.builtin, "retired demo route"),
    ("MOCK/anything", RuntimeKind.builtin, "retired demo route"),
    ("anything", RuntimeKind.mock, "retired demo runtime"),
    ("mock/anything", RuntimeKind.mock, "retired demo runtime"),
    ("opencode/opencode/big-pickle", RuntimeKind.builtin, "OpenCode runtime"),
    ("ollama/llama3.2:3b", RuntimeKind.opencode, "not an OpenCode route"),
    ("opencode/opencode", RuntimeKind.opencode, "not an OpenCode route"),
])
def test_an_unusable_route_is_named(model, runtime, expected):
    problem = route_problem(_bot(model, runtime))
    assert problem and expected in problem


@pytest.mark.parametrize("model,runtime", [
    ("ollama/llama3.2:3b", RuntimeKind.builtin),
    ("openai/gpt-4o-mini", RuntimeKind.builtin),
    ("anthropic/claude-sonnet", RuntimeKind.builtin),
    ("opencode/opencode/big-pickle", RuntimeKind.opencode),
    ("", RuntimeKind.pi),                    # the Pi runtime chooses its own model
    ("anything", RuntimeKind.pi),
])
def test_a_runnable_route_has_no_problem(model, runtime):
    assert route_problem(_bot(model, runtime)) is None


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
    store.create_bot(Bot(name="bare-demo", display_name="Bare Demo", model="demo", tools=[]))
    store.create_bot(Bot(name="real-one", display_name="Real One", model="ollama/llama3.2:3b", tools=[]))
    by_name = {item["name"]: item for item in client.get("/api/bots").json()}
    assert "retired demo route" in by_name["old-demo"]["route_problem"]
    assert "provider/model" in by_name["bare-demo"]["route_problem"]
    assert by_name["real-one"]["route_problem"] is None


def test_the_saved_workspace_default_carries_its_problem(client):
    """A legacy saved default is not shown as a usable route: first run reads the same server answer."""
    assert client.get("/api/v1/preferences/model-defaults").json()["route_problem"] is None
    client.app.state.store.kv_set("workspace:model-defaults",
                                  '{"model": "mock/demo", "inference_mode": "hybrid"}')
    legacy = client.get("/api/v1/preferences/model-defaults").json()
    assert legacy["model"] == "mock/demo" and "retired demo route" in legacy["route_problem"]
    client.app.state.store.kv_set("workspace:model-defaults",
                                  '{"model": "opencode/opencode/big-pickle", "inference_mode": "hybrid"}')
    opencode = client.get("/api/v1/preferences/model-defaults").json()
    assert "OpenCode runtime" in opencode["route_problem"]
    client.app.state.store.kv_set("workspace:model-defaults",
                                  '{"model": "ollama/llama3.2:3b", "inference_mode": "hybrid"}')
    assert client.get("/api/v1/preferences/model-defaults").json()["route_problem"] is None
