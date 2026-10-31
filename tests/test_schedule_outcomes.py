"""What the owner is told about the last time a recurring task actually ran.

Scheduled work has to answer "why didn't it run?" from persisted rows: the claimed
window, the run behind it, and the run's own exit reason. A routine that cannot run
at all is distinguished from one whose last run failed, and neither is reported as a
success. Nothing here calls a model.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from hutch.engine import Engine
from hutch.models import Bot, CatchUpPolicy, Run, RunStatus, Schedule, Task, iso
from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The real routes without the lifespan supervisor.

    These tests need a scheduled occurrence they control. The app's supervisor would
    claim and execute the same queue, so it is deliberately not started here.
    """
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    yield TestClient(app)
    app.state.store.close()


def _scheduled_bot(store) -> Bot:
    return store.create_bot(Bot(
        name="outcomes", instructions="work",
        schedule=Schedule(cron="0 * * * *", timezone="UTC", catch_up=CatchUpPolicy.coalesce),
        created_at="2026-10-07T10:00:00+00:00",
    ))


def _claim_occurrence(config, store, bot):
    """Claim the 11:00 and 12:00 windows as one coalesced occurrence (two missed)."""
    engine = Engine(config, store)
    store.kv_set(f"{bot.schedule.id}:last_fire", "2026-10-07T10:00:00+00:00")
    due = engine.scheduler.due_claims(datetime(2026, 10, 7, 12, 30, tzinfo=timezone.utc))[0]
    marker = iso(due.occurrence)
    run = Run(bot_id=bot.id, prompt="check the release feed", origin="schedule",
              schedule_id=due.schedule.id, missed_windows=due.missed)
    task = Task(bot_id=bot.id, kind="scheduled", prompt=run.prompt)
    claimed = store.submit_scheduled(run, task, occurrence=marker, expected_marker=due.marker,
                                     new_marker=marker, claimed_by="test", schedule_id=due.schedule.id)
    assert claimed is not None
    return run


def _finish(config, store, run, status: RunStatus, *, exit_reason: str = "") -> None:
    owner = store.claim_run(run.id, "outcome-test", lease_seconds=30)
    store.transition_run(run.id, RunStatus.running, fence=owner.fence)
    store.transition_run(run.id, status, fence=owner.fence, exit_reason=exit_reason or None)


def _row(client, bot) -> dict:
    return next(row for row in client.get("/api/v1/schedules").json() if row["bot_id"] == bot.id)


def test_a_failed_last_run_names_its_reason_and_asks_for_attention(client, config):
    store = client.app.state.store
    bot = _scheduled_bot(store)
    run = _claim_occurrence(config, store, bot)
    _finish(config, store, run, RunStatus.failed, exit_reason="model_unavailable")

    row = _row(client, bot)
    assert row["last_occurrence"]["run_id"] == run.id
    assert row["last_occurrence"]["run_status"] == "failed"
    assert row["last_occurrence"]["exit_reason"] == "model_unavailable"
    assert row["last_occurrence"]["missed_windows"] == run.missed_windows
    assert row["last_occurrence"]["missed_windows"] >= 1
    assert row["last_occurrence"]["needs_attention"] is True
    assert row["needs_attention"] is True


def test_a_successful_last_run_is_not_attention(client, config):
    store = client.app.state.store
    bot = _scheduled_bot(store)
    run = _claim_occurrence(config, store, bot)
    _finish(config, store, run, RunStatus.succeeded)

    row = _row(client, bot)
    assert row["last_occurrence"]["run_status"] == "succeeded"
    assert row["last_occurrence"]["exit_reason"] == ""
    assert row["last_occurrence"]["needs_attention"] is False
    assert row["needs_attention"] is False


def test_a_cancelled_run_is_reported_without_asking_for_attention(client, config):
    store = client.app.state.store
    bot = _scheduled_bot(store)
    run = _claim_occurrence(config, store, bot)
    _finish(config, store, run, RunStatus.stopped)

    row = _row(client, bot)
    assert row["last_occurrence"]["run_status"] == "stopped"
    assert row["last_occurrence"]["needs_attention"] is False


def test_an_unknown_outcome_asks_for_attention(client, config):
    store = client.app.state.store
    bot = _scheduled_bot(store)
    run = _claim_occurrence(config, store, bot)
    _finish(config, store, run, RunStatus.outcome_unknown, exit_reason="outcome_unknown")

    row = _row(client, bot)
    assert row["last_occurrence"]["run_status"] == "outcome_unknown"
    assert row["last_occurrence"]["needs_attention"] is True


def test_a_claim_whose_run_cannot_be_read_asks_for_attention(client, config):
    store = client.app.state.store
    bot = _scheduled_bot(store)
    with store._tx() as db:
        db.execute(
            "INSERT INTO schedule_occurrences_v20 "
            "(schedule_id, occurrence, bot_id, run_id, claimed_at, claimed_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (bot.schedule.id, "2026-10-07T12:00:00+00:00", bot.id, "run_missing",
             "2026-10-07T12:00:01+00:00", "test"))

    row = _row(client, bot)
    assert row["last_occurrence"]["run_status"] == ""
    assert row["last_occurrence"]["needs_attention"] is True
    assert row["needs_attention"] is True


def test_a_routine_that_never_ran_has_no_last_run(client):
    store = client.app.state.store
    bot = _scheduled_bot(store)

    row = _row(client, bot)
    assert row["last_occurrence"] is None
    assert row["needs_attention"] is False


def test_a_routine_that_cannot_run_asks_for_attention_without_a_run(client):
    store = client.app.state.store
    bot = _scheduled_bot(store)
    store.kv_set(f"{bot.schedule.id}:blocked", json.dumps(
        {"reason": "invalid_timezone", "detail": "Mars/Olympus", "at": "2026-10-07T12:00:00+00:00"}))

    row = _row(client, bot)
    assert row["blocked"]["reason"] == "invalid_timezone"
    assert row["last_occurrence"] is None
    assert row["needs_attention"] is True


def test_the_history_endpoint_carries_the_same_outcome(client, config):
    store = client.app.state.store
    bot = _scheduled_bot(store)
    run = _claim_occurrence(config, store, bot)
    _finish(config, store, run, RunStatus.failed, exit_reason="timeout")

    history = client.get(f"/api/v1/bots/{bot.name}/schedules/{bot.schedule.id}/occurrences").json()
    assert len(history) == 1
    assert history[0]["run_status"] == "failed"
    assert history[0]["exit_reason"] == "timeout"
    assert history[0]["missed_windows"] == run.missed_windows
    assert history[0]["missed_windows"] >= 1


def test_the_outcome_projection_never_carries_the_prompt_or_an_error_body(client, config):
    store = client.app.state.store
    bot = _scheduled_bot(store)
    run = _claim_occurrence(config, store, bot)
    _finish(config, store, run, RunStatus.failed, exit_reason="model_unavailable")

    row = _row(client, bot)
    serialized = json.dumps(row["last_occurrence"])
    assert "check the release feed" not in serialized
    assert set(row["last_occurrence"]) == {
        "occurrence", "run_id", "claimed_at", "run_status", "exit_reason", "missed_windows", "needs_attention"}
