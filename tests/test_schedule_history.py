"""Append-only schedule revisions: migration, triggers, diffs and the read-only API."""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot, CatchUpPolicy, Schedule
from hutch.schedule_history_schema import migrate
from hutch.server.app import create_app


def _doc(schedule_id: str, *, cron: str = "0 3 * * *", prompt: str = "Check releases.") -> str:
    schedule = {"id": schedule_id, "name": "Nightly release check", "trigger": "cron",
                "cron": cron, "timezone": "UTC", "catch_up": "coalesce", "overlap": "queue",
                "enabled": False, "prompt": prompt, "workflow_inputs": {}, "created_at": "2026-11-06T00:00:00+00:00"}
    return json.dumps({"name": "release-watch", "schedule": schedule, "schedules": [schedule]})


def _bot(store, *, name: str = "release-watch", prompt: str = "Check releases.") -> Bot:
    return store.create_bot(Bot(
        name=name, display_name=name.title(), tools=[],
        schedule=Schedule(name="Nightly release check", cron="0 3 * * *", timezone="UTC",
                          catch_up=CatchUpPolicy.coalesce, enabled=False, prompt=prompt),
    ))


def _replacement(bot: Bot, **overrides) -> Schedule:
    fields = {"id": bot.schedule.id, "name": "Nightly release check", "cron": "0 3 * * *",
              "timezone": "UTC", "catch_up": CatchUpPolicy.coalesce, "enabled": False,
              "prompt": "Check releases."}
    fields.update(overrides)
    return Schedule(**fields)


def test_migration_backfills_existing_bots_and_refuses_rewrite():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    try:
        db.execute("CREATE TABLE bots (id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, doc TEXT NOT NULL)")
        db.execute("INSERT INTO bots VALUES (?, ?, ?)", ("bot-a", "release-watch", _doc("schedule-a")))
        migrate(db)
        rows = db.execute("SELECT bot_id, revision, change_type FROM schedule_revisions").fetchall()
        assert [tuple(row) for row in rows] == [("bot-a", 1, "created")]
        migrate(db)
        assert db.execute("SELECT COUNT(*) FROM schedule_revisions").fetchone()[0] == 1

        db.execute("UPDATE bots SET doc = ? WHERE id = 'bot-a'", (_doc("schedule-a", cron="0 4 * * *"),))
        rows = db.execute("SELECT revision, change_type FROM schedule_revisions ORDER BY revision").fetchall()
        assert [tuple(row) for row in rows] == [(1, "created"), (2, "updated")]

        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("UPDATE schedule_revisions SET bot_name = 'other'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM schedule_revisions")
    finally:
        db.close()


def test_bot_updates_write_only_real_schedule_changes(store):
    bot = _bot(store)
    assert store._db.execute("SELECT COUNT(*) FROM schedule_revisions").fetchone()[0] == 1

    store.upsert_bot(store.get_bot(bot.id))
    assert store._db.execute("SELECT COUNT(*) FROM schedule_revisions").fetchone()[0] == 1

    changed = store.get_bot(bot.id)
    changed.description = "unrelated edit"
    store.upsert_bot(changed)
    assert store._db.execute("SELECT COUNT(*) FROM schedule_revisions").fetchone()[0] == 1

    store.put_schedule(bot.id, _replacement(bot, cron="0 4 * * *"))
    rows = store._db.execute(
        "SELECT revision, change_type FROM schedule_revisions ORDER BY revision").fetchall()
    assert [tuple(row) for row in rows] == [(1, "created"), (2, "updated")]


def test_the_journal_stores_schedules_not_the_whole_bot_document(store):
    bot = store.create_bot(Bot(
        name="private-notes", display_name="Private Notes", tools=[],
        instructions="OWNER PRIVATE INSTRUCTION",
        schedule=Schedule(name="Nightly", cron="0 3 * * *", timezone="UTC", enabled=False,
                          prompt="Check releases."),
    ))
    store.put_schedule(bot.id, _replacement(bot, cron="0 4 * * *"))
    snapshots = " ".join(row[0] for row in store._db.execute(
        "SELECT schedules_json FROM schedule_revisions").fetchall())
    assert "OWNER PRIVATE INSTRUCTION" not in snapshots
    assert "Check releases." in snapshots


def test_revisions_api_returns_bounded_field_diff_and_redacts_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        store = client.app.state.store
        bot = _bot(store, prompt="secret prompt v1")
        store.put_schedule(bot.id, _replacement(bot, cron="0 4 * * *", prompt="secret prompt v2"))

        response = client.get(f"/api/v1/bots/{bot.name}/schedules/{bot.schedule.id}/revisions")
        assert response.status_code == 200
        rows = response.json()
        assert rows[0]["change_type"] == "updated"
        assert rows[0]["schedule_id"] == bot.schedule.id
        changes = {item["field"]: item for item in rows[0]["changes"]}
        assert changes["cron"]["before"] == "0 3 * * *"
        assert changes["cron"]["after"] == "0 4 * * *"
        assert changes["cron"]["redacted"] is False
        assert changes["prompt"]["redacted"] is True
        assert changes["prompt"]["before"] is None and changes["prompt"]["after"] is None
        assert changes["prompt"]["before_hash"] != changes["prompt"]["after_hash"]
        assert "secret prompt" not in response.text
        assert str(tmp_path) not in response.text
        assert rows[0]["before_hash"] and rows[0]["after_hash"]


def test_revisions_api_keeps_a_removed_schedule_history(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        store = client.app.state.store
        bot = _bot(store)
        schedule_id = bot.schedule.id
        store.delete_schedule(bot.id, schedule_id)

        response = client.get(f"/api/v1/bots/{bot.name}/schedules/{schedule_id}/revisions")
        assert response.status_code == 200
        rows = response.json()
        assert rows[0]["change_type"] == "removed"
        assert rows[0]["changes"] == []


def test_revisions_api_404_for_an_unknown_schedule(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        store = client.app.state.store
        bot = _bot(store)
        assert client.get(
            f"/api/v1/bots/{bot.name}/schedules/schedule-missing/revisions").status_code == 404


def test_revisions_api_paginates(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        store = client.app.state.store
        bot = _bot(store)
        for hour in (4, 5, 6):
            store.put_schedule(bot.id, _replacement(bot, cron=f"0 {hour} * * *"))
        response = client.get(
            f"/api/v1/bots/{bot.name}/schedules/{bot.schedule.id}/revisions?limit=1&offset=1")
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["revision"] == 3
