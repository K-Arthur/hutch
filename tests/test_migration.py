"""A database written by the baseline (schema v4) upgrades to the current schema without losing anything.

tests/fixtures/state_v4.db.fixture was produced by the baseline code (commit b3e4b15, SCHEMA_VERSION 4) with two bots, a
schedule, memory, a sticky allow, finished runs with hash-chained events, a usage row, a pending approval, a queued run, and a
run that was 'running' when its process died (a legacy orphan).
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from hutch.config import get_config, hutchConfig
from hutch.engine import Engine
from hutch.lifecycle import IllegalTransition
from hutch.models import RunStatus
from hutch.store import SCHEMA_VERSION, Store

FIXTURE = Path(__file__).parent / "fixtures" / "state_v4.db.fixture"
BRIEFING, SWEEPER = "bot_7eef563ee683", "bot_611a4b96d543"
FINISHED_1, FINISHED_2, ORPHAN, QUEUED = "run_582f4cc75ea4", "run_fa7f70664c38", "run_3cefb894fd73", "run_e169d5380ff5"


@pytest.fixture()
def v4(config):
    config.ensure()
    shutil.copy(FIXTURE, config.db_path)
    return config


def test_the_fixture_really_is_schema_v4(v4):
    c = sqlite3.connect(v4.db_path)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 4
    assert "fence" not in [r[1] for r in c.execute("PRAGMA table_info(runs)")]


def test_upgrade_preserves_bot_ids_schedules_memory_and_allows(v4):
    store = Store(v4)
    try:
        assert store.schema_version == SCHEMA_VERSION
        bots = {b.id: b for b in store.list_bots()}
        assert set(bots) == {BRIEFING, SWEEPER}                                  # ids unchanged
        briefing = bots[BRIEFING]
        assert briefing.name == "briefing" and briefing.schedule.cron == "0 9 * * 1"
        assert briefing.schedule.timezone == "Europe/London"
        assert {m.key: (m.value, m.source) for m in store.recall_all(BRIEFING)} == {
            "style": ("concise", "user"), "last-run": ("research briefing for: summarise this week", "bot")}
        assert store.list_sticky_allows(BRIEFING) == ["files:write"]
        assert store.kv_get(f"schedule:{BRIEFING}:last_fire") == "2026-10-05T09:00:00+00:00"   # the schedule position survives
        assert store.usage_tokens_since("mock", 10**9) == 3450      # the ledger written by the baseline, unchanged
        legacy = store._db.execute("SELECT provider, account_id FROM usage ORDER BY id LIMIT 1").fetchone()
        assert legacy["account_id"] == legacy["provider"] == "mock"  # pre-account usage retains its original grouping
        assert store._db.execute("SELECT COUNT(*) FROM usage_reservations").fetchone()[0] == 0
    finally:
        store.close()


def test_upgrade_preserves_transcripts_and_their_hash_chain(v4):
    store = Store(v4)
    try:
        for rid in (FINISHED_1, FINISHED_2):
            run = store.get_run(rid)
            assert run.status is RunStatus.succeeded and run.steps >= 3
            assert len(store.list_events(rid)) >= 5
            chain = store.verify_chain(rid)
            assert chain["ok"] and chain["checked"] >= 5 and chain["legacy"] == 0
    finally:
        store.close()


def test_upgrade_keeps_legacy_run_contexts_separate(v4):
    store = Store(v4)
    try:
        first = store.get_conversation(f"conv_legacy_{FINISHED_1}")
        second = store.get_conversation(f"conv_legacy_{FINISHED_2}")
        assert first and second and first["is_legacy"] and second["is_legacy"]
        assert first["id"] != second["id"] and first["bot_id"] != second["bot_id"]
        assert store.get_run(FINISHED_1).conversation_id == first["id"]
        first_messages = store.list_conversation_messages(first["id"])
        second_messages = store.list_conversation_messages(second["id"])
        assert first_messages[0]["role"] == second_messages[0]["role"] == "user"
        assert first_messages[0]["content"] != second_messages[0]["content"]
        assert all(message["run_id"] == FINISHED_1 for message in first_messages)
        assert all(message["run_id"] == FINISHED_2 for message in second_messages)
    finally:
        store.close()


def test_a_backup_is_written_before_the_upgrade(v4):
    Store(v4).close()
    assert (v4.state_dir / "hutch.db.bak-v4").exists()
    c = sqlite3.connect(v4.state_dir / "hutch.db.bak-v4")
    assert c.execute("PRAGMA user_version").fetchone()[0] == 4                  # the backup is the untouched original


def test_sqlite_backup_can_be_restored_and_upgraded(v4):
    Store(v4).close()
    restore = hutchConfig(state_dir=v4.state_dir / "restored")
    restore.ensure()
    source = sqlite3.connect(v4.state_dir / "hutch.db.bak-v4")
    destination = sqlite3.connect(restore.db_path)
    try:
        source.backup(destination)
    finally:
        destination.close(); source.close()
    recovered = Store(restore)
    try:
        assert recovered.schema_version == SCHEMA_VERSION
        assert recovered.get_bot(BRIEFING) is not None
        assert recovered.get_run(FINISHED_1).status is RunStatus.succeeded
    finally:
        recovered.close()


def test_old_task_rows_keep_their_meaning(v4):
    store = Store(v4)
    try:
        rows = store._db.execute("SELECT done, state FROM tasks ORDER BY done").fetchall()
        assert [(r["done"], r["state"]) for r in rows] == [(0, "queued"), (1, "done"), (1, "done")]
        assert [t.prompt for t in store.pending_tasks(BRIEFING)] == ["queued before the upgrade"]
    finally:
        store.close()


def test_a_legacy_orphan_is_recovered_by_the_pid_check_and_its_approval_expired(v4):
    store = Store(v4)
    try:
        orphan = store.get_run(ORPHAN)
        assert orphan.status is RunStatus.running and orphan.fence == 0 and orphan.lease_owner == ""
        recovered = Engine(v4, store).recover_orphans()
        assert [r.id for r in recovered] == [ORPHAN]
        fixed = store.get_run(ORPHAN)
        assert fixed.status is RunStatus.failed and fixed.exit_reason == "interrupted" and fixed.fence == 1
        assert store.pending_approvals() == []
        assert store.verify_chain(ORPHAN)["ok"]
    finally:
        store.close()


def test_a_run_queued_before_the_upgrade_runs_after_it(v4):
    store = Store(v4)
    try:
        engine = Engine(v4, store)
        engine.recover_orphans()                       # frees the briefing bot's rival, as a restart would
        engine.dispatch_pending()
        import time
        deadline = time.time() + 15
        while time.time() < deadline and store.get_run(QUEUED).status in (RunStatus.pending, RunStatus.running):
            time.sleep(0.1)
        assert store.get_run(QUEUED).status in (RunStatus.succeeded, RunStatus.waiting_approval, RunStatus.failed)
        assert store.get_run(QUEUED).fence >= 1        # it was claimed like any new run
    finally:
        store.close()


def test_running_the_upgrade_twice_changes_nothing(v4):
    Store(v4).close()
    first = sqlite3.connect(v4.db_path).execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    s = Store(v4)
    try:
        assert s.schema_version == SCHEMA_VERSION
    finally:
        s.close()
    assert sqlite3.connect(v4.db_path).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == first


def test_a_database_from_a_newer_hutch_is_refused_not_downgraded(config):
    config.ensure()
    shutil.copy(FIXTURE, config.db_path)
    c = sqlite3.connect(config.db_path)
    c.execute("PRAGMA user_version = 99"); c.commit(); c.close()
    with pytest.raises(RuntimeError, match="newer than this hutch"):
        Store(config)
