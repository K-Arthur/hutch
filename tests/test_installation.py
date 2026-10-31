"""Installation review: what an earlier version left behind, and the person's acknowledgement.

Read-only computation over the existing store; recording a review writes one marker and changes nothing
else. A new issue after a review appears once; fresh state stays with first-run onboarding.
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


def _state(client):
    response = client.get("/api/v1/installation")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_fresh_install_stays_with_first_run_onboarding(client):
    state = _state(client)
    assert state["state"] == "fresh" and state["review_required"] is False
    assert state["issues"] == [] and state["assistant_count"] == 0


def test_a_legacy_installation_needs_a_review_and_records_one(client):
    store = client.app.state.store
    bot = store.create_bot(Bot(name="research-briefing", display_name="Research Briefing",
                               model="mock/demo", tools=[]))
    created = iso(utcnow() - timedelta(days=5))
    store.create_run(Run(bot_id=bot.id, prompt="weekly research briefing", status=RunStatus.failed,
                         exit_reason="error", error="The mock runtime was removed.",
                         created_at=created, finished_at=created))
    bots_before, runs_before = len(store.list_bots()), len(store.list_runs())

    state = _state(client)
    assert state["state"] == "needs_review" and state["review_required"] is True
    kinds = {issue["kind"] for issue in state["issues"]}
    assert kinds == {"assistant", "legacy_runs", "no_main_assistant"}
    assistant = next(issue for issue in state["issues"] if issue["kind"] == "assistant")
    assert assistant["display_name"] == "Research Briefing"
    assert assistant["href"] == "#/bot/research-briefing"
    assert assistant["remove_href"] == "/bots/research-briefing/delete"
    assert "model route" in assistant["fix"]

    reviewed = client.post("/api/v1/installation/review")
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["state"] == "ready" and reviewed.json()["review_required"] is False
    assert reviewed.json()["reviewed_at"]
    assert len(store.list_bots()) == bots_before and len(store.list_runs()) == runs_before   # nothing rewritten

    assert _state(client)["review_required"] is False          # the reminder stays dismissed


def test_a_new_problem_after_a_review_appears_once(client):
    store = client.app.state.store
    first = store.create_bot(Bot(name="design-partner", model="mock/demo", tools=[]))
    store.set_workspace_coordinator(first.id)
    client.post("/api/v1/installation/review")
    assert _state(client)["review_required"] is False
    second = store.create_bot(Bot(name="repo-sweeper", model="demo", tools=[]))
    state = _state(client)
    assert state["state"] == "needs_review"
    assert [issue["key"] for issue in state["open_issues"]] == [f"assistant:{second.id}"]


def test_a_ghost_live_row_is_listed_but_never_deleted(client):
    store = client.app.state.store
    bot = store.create_bot(Bot(name="tidy-downloads", model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator(bot.id)
    run = store.create_run(Run(bot_id=bot.id, prompt="sort the downloads", status=RunStatus.cancelling,
                               owner="", created_at=iso(utcnow() - timedelta(days=23))))
    state = _state(client)
    ghost = next(issue for issue in state["issues"] if issue["kind"] == "ghost_runs")
    assert ghost["count"] >= 1 and "Stop all does not clear" in ghost["fix"]
    assert store.get_run(run.id) is not None


def test_a_clean_installation_is_ready_without_a_review(client):
    store = client.app.state.store
    bot = store.create_bot(Bot(name="repo-sweeper", model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator(bot.id)
    state = _state(client)
    assert state["state"] == "ready" and state["issues"] == [] and state["review_required"] is False
