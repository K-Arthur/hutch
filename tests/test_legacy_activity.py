"""Demo-era failures are history, not "Needs you".

A failed run whose assistant has a retired/unusable route, or whose recorded error names the removed mock
runtime, is classified on read: it moves to a Legacy list with a repair action, stops counting toward
"Needs you", stays in History with a Legacy badge, and the doubled error prefix is displayed once.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, Run, RunStatus, iso, utcnow
from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as test_client:
        yield test_client


def _failed(store, bot, *, error, exit_reason="error", days=5):
    return store.create_run(Run(
        bot_id=bot.id, prompt=f"weekly update for {bot.name}", status=RunStatus.failed,
        exit_reason=exit_reason, error=error,
        created_at=iso(utcnow() - timedelta(days=days)), finished_at=iso(utcnow() - timedelta(days=days))))


def test_legacy_failures_leave_needs_you_and_keep_a_repair_action(client):
    store = client.app.state.store
    retired = store.create_bot(Bot(name="research-briefing", display_name="Research Briefing",
                                   model="mock/demo", tools=[]))
    malformed = store.create_bot(Bot(name="design-partner", display_name="Design Partner",
                                     model="demo", tools=[]))
    runnable = store.create_bot(Bot(name="repo-sweeper", display_name="Repo Sweeper",
                                    model="ollama/llama3.2:3b", tools=[]))
    retired_run = _failed(store, retired, error="The mock runtime was removed. Select a configured route.")
    broken_run = _failed(store, malformed, error="'demo' is not a model spec")
    current_run = _failed(store, runnable, error="the model server refused the request", exit_reason="timeout")

    overview = client.get("/api/overview").json()
    assert [r["id"] for r in overview["failures"]] == [current_run.id]
    assert {r["id"] for r in overview["legacy_failures"]} == {retired_run.id, broken_run.id}
    assert overview["needs_count"] == 1                      # the legacy pair no longer counts
    legacy = next(r for r in overview["legacy_failures"] if r["id"] == retired_run.id)
    assert legacy["legacy"] is True
    assert "retired demo runtime" in legacy["wait"]["cause"]
    assert "model route" in legacy["wait"]["fix"]
    assert legacy["wait"]["link_text"] == "Open the assistant"


def test_the_doubled_error_prefix_is_shown_once(client):
    store = client.app.state.store
    bot = store.create_bot(Bot(name="prefix-bot", model="ollama/llama3.2:3b", tools=[]))
    _failed(store, bot, error="The run ended with an error: The run ended with an error: the provider refused")
    cause = client.get("/api/overview").json()["failures"][0]["wait"]["cause"]
    assert cause.count("The run ended with an error:") == 1


def test_the_runs_api_marks_legacy_for_history(client):
    store = client.app.state.store
    retired = store.create_bot(Bot(name="old-one", model="mock/demo", tools=[]))
    runnable = store.create_bot(Bot(name="new-one", model="ollama/llama3.2:3b", tools=[]))
    legacy_run = _failed(store, retired, error="The mock runtime was removed")
    current_run = _failed(store, runnable, error="boom")
    runs = {item["id"]: item for item in client.get("/api/runs").json() if isinstance(item, dict)}
    assert runs[legacy_run.id]["legacy"] is True
    assert runs[current_run.id]["legacy"] is False
