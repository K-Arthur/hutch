"""Notification storage: the outbox rebuild and the trigger repair that reaches live databases.

These are migration-level checks. They build a database in the shape an earlier release left
behind and upgrade it through the real Store, because that is the only way to notice a trigger
whose body `CREATE TRIGGER IF NOT EXISTS` can never replace.
"""

from __future__ import annotations

import pytest


def test_the_outbox_rebuild_preserves_reply_deliveries_and_refuses_orphans(tmp_path):
    """A v85-shaped database upgrades without losing a reply delivery; an orphan blocks it."""
    import sqlite3

    from hutch import notification_schema

    db = sqlite3.connect(tmp_path / "v85.db")
    db.row_factory = sqlite3.Row
    try:
        db.execute("CREATE TABLE channel_connections (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE channel_events (id INTEGER PRIMARY KEY, channel_id TEXT, revision INTEGER)")
        db.execute("CREATE TABLE approvals (id TEXT PRIMARY KEY, bot_id TEXT, status TEXT, doc TEXT)")
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, bot_id TEXT, status TEXT, doc TEXT)")
        db.execute("""CREATE TABLE channel_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL UNIQUE REFERENCES channel_events(id),
            text TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL, provider_message_id TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '', reconciled_at TEXT NOT NULL DEFAULT '',
            reconciliation TEXT NOT NULL DEFAULT '')""")
        db.execute("INSERT INTO channel_connections(id) VALUES ('ch_1')")
        db.execute("INSERT INTO channel_events(id,channel_id,revision) VALUES (7,'ch_1',3)")
        db.execute("INSERT INTO channel_deliveries(event_id,text,state,attempts,next_attempt_at) "
                   "VALUES (7,'a reply','sent',2,'2026-10-31T00:00:00+00:00')")
        notification_schema.migrate(db)
        row = db.execute("SELECT * FROM channel_deliveries").fetchone()
        assert (row["event_id"], row["notification_id"], row["channel_id"]) == (7, None, "ch_1")
        assert (row["text"], row["state"], row["attempts"]) == ("a reply", "sent", 2)
        assert "notifications" in {item[0] for item in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        # A second run is a no-op once the new shape is present.
        notification_schema.migrate(db)
        assert db.execute("SELECT COUNT(*) FROM channel_deliveries").fetchone()[0] == 1
    finally:
        db.close()


def test_the_outbox_rebuild_refuses_a_delivery_with_no_inbound_event(tmp_path):
    import sqlite3

    from hutch import notification_schema

    db = sqlite3.connect(tmp_path / "bad.db")
    try:
        db.execute("CREATE TABLE channel_connections (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE channel_events (id INTEGER PRIMARY KEY, channel_id TEXT, revision INTEGER)")
        db.execute("CREATE TABLE approvals (id TEXT PRIMARY KEY, bot_id TEXT, status TEXT, doc TEXT)")
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, bot_id TEXT, status TEXT, doc TEXT)")
        db.execute("""CREATE TABLE channel_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL UNIQUE, text TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL, provider_message_id TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '', reconciled_at TEXT NOT NULL DEFAULT '',
            reconciliation TEXT NOT NULL DEFAULT '')""")
        db.execute("INSERT INTO channel_deliveries(event_id,text,next_attempt_at) VALUES (99,'orphan','x')")
        with pytest.raises(RuntimeError, match="preserve the database"):
            notification_schema.migrate(db)
        assert db.execute("SELECT name FROM sqlite_master WHERE name='channel_deliveries_v86'").fetchone() is None
    finally:
        db.close()


def test_a_database_that_already_ran_the_migration_gets_the_corrected_triggers(tmp_path):
    """CREATE TRIGGER IF NOT EXISTS can never change a live body; the repair step must."""
    import sqlite3

    from hutch.config import hutchConfig
    from hutch.models import ApprovalMode, ApprovalRequest, Bot, Run, RunStatus, iso, utcnow
    from hutch.store import SCHEMA_VERSION, Store

    root = tmp_path / "state"
    first = Store(hutchConfig(root))
    bot = first.create_bot(Bot(name="upgrade-me", approval_mode=ApprovalMode.ask))
    run = Run(bot_id=bot.id, prompt="p", status=RunStatus.running, started_at=iso(utcnow()))
    first.create_run(run)
    approval = first.create_approval(ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="t", action="a"))
    first.close()
    # Rewind to the shape shipped before the fix: old trigger bodies, version 86.
    db = sqlite3.connect(root / "hutch.db")
    try:
        db.execute("DROP TRIGGER notification_approval_resolved")
        db.execute("DROP TRIGGER notification_run_outcome")
        db.execute("""CREATE TRIGGER notification_approval_resolved AFTER UPDATE OF status ON approvals
            WHEN OLD.status = 'pending' AND NEW.status IN ('expired','denied')
            BEGIN INSERT OR IGNORE INTO notifications(id, kind, bot_id, subject_kind, subject_id, detail, created_at)
            VALUES ('ntf_old', 'approval_denied', NEW.bot_id, 'approval', NEW.id,
            substr(coalesce(json_extract(NEW.doc, '$.decided_by'), ''), 1, 40),
            strftime('%Y-%m-%dT%H:%M:%f+00:00','now')); END""")
        db.execute("""CREATE TRIGGER notification_run_outcome AFTER UPDATE OF status ON runs
            WHEN NEW.status <> OLD.status AND (NEW.status IN ('failed','outcome_unknown'))
            BEGIN INSERT OR IGNORE INTO notifications(id, kind, bot_id, subject_kind, subject_id, detail, created_at)
            VALUES ('ntf_old2', 'run_failed', NEW.bot_id, 'run', NEW.id,
            substr(coalesce(json_extract(NEW.doc, '$.exit_reason'), ''), 1, 40),
            strftime('%Y-%m-%dT%H:%M:%f+00:00','now')); END""")
        db.execute("PRAGMA user_version = 86")
        db.commit()
    finally:
        db.close()
    upgraded = Store(hutchConfig(root))
    try:
        assert upgraded.schema_version == SCHEMA_VERSION > 86
        with upgraded._lock:
            bodies = {row[0]: row[1] or "" for row in upgraded._db.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'notification%'")}
        assert set(bodies) == {"notification_approval_created", "notification_approval_resolved",
                               "notification_run_outcome"}
        assert "json_valid(NEW.doc)" in bodies["notification_approval_resolved"]
        assert "json_valid(NEW.doc)" in bodies["notification_run_outcome"]
        # The corrected body is live: a corrupt document skips the alert, never aborts the write.
        with upgraded._tx() as tx:
            tx.execute("UPDATE runs SET doc='not json' WHERE id=?", (run.id,))
            tx.execute("UPDATE runs SET status='failed' WHERE id=?", (run.id,))
        with upgraded._lock:
            assert upgraded._db.execute("SELECT status FROM runs WHERE id=?", (run.id,)).fetchone()[0] == "failed"
        # A healthy transition still notifies, so the repair does not silently disable alerts.
        healthy = Run(bot_id=bot.id, prompt="q", status=RunStatus.running, started_at=iso(utcnow()))
        upgraded.create_run(healthy)
        upgraded.transition_run(healthy.id, RunStatus.failed, exit_reason="model_unavailable")
        with upgraded._lock:
            kinds = [row[0] for row in upgraded._db.execute(
                "SELECT kind FROM notifications WHERE subject_id=?", (healthy.id,))]
        assert kinds == ["run_failed"]
        assert approval.id
    finally:
        upgraded.close()


