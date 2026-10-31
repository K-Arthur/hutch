"""Durable owner notifications and the single channel outbox that delivers them.

A notification is created by the same transaction that creates an approval or ends a
run: a trigger writes one content-free row per subject and event kind, so a crash
cannot lose it and a retried transition cannot duplicate it. Delivery reuses the
channel outbox's rows, states and reconciliation. There is no second sender.

The outbox rebuild is additive in effect: existing reply deliveries are copied with
their channel resolved from the inbound event they answer, and a notification
delivery carries a nullable ``notification_id`` instead of an ``event_id``. Exactly
one of the two is present.
"""

from __future__ import annotations

import sqlite3

from .durable_changes import install_resources

NOTIFICATION_KINDS = (
    "approval_needs_you", "approval_expired", "approval_denied",
    "run_failed", "run_outcome_unknown", "run_succeeded",
)
UNATTENDED_ORIGINS = ("schedule", "source", "job", "workflow", "workflow:continuation", "workflow_auto")
TRIGGER_NAMES = ("notification_approval_created", "notification_approval_resolved",
                 "notification_run_outcome")
STAMP = "strftime('%Y-%m-%dT%H:%M:%f+00:00','now')"
NEW_ID = "'ntf_' || lower(hex(randomblob(12)))"


def migrate(db: sqlite3.Connection) -> None:
    db.execute(f"""CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK(kind IN ({','.join(repr(kind) for kind in NOTIFICATION_KINDS)})),
        bot_id TEXT NOT NULL,
        subject_kind TEXT NOT NULL CHECK(subject_kind IN ('approval','run')),
        subject_id TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        UNIQUE(kind, subject_kind, subject_id))""")
    db.execute("CREATE INDEX IF NOT EXISTS notifications_recent ON notifications(bot_id, created_at)")
    _rebuild_deliveries(db)
    _install_triggers(db)


def repair(db: sqlite3.Connection) -> None:
    """Re-install the observation triggers, replacing any earlier definition.

    ``CREATE TRIGGER IF NOT EXISTS`` inside a migration that has already run can never
    change a live body, so a corrected trigger reaches existing databases only through a
    step of its own. Dropping and recreating is safe: a trigger holds no rows, and no
    notification is lost or repeated because the rows are already stored.
    """
    for name in TRIGGER_NAMES:
        db.execute(f"DROP TRIGGER IF EXISTS {name}")
    _install_triggers(db)


def _rebuild_deliveries(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(channel_deliveries)")}
    if "notification_id" in columns:
        return
    orphans = db.execute("SELECT COUNT(*) FROM channel_deliveries d WHERE NOT EXISTS "
                         "(SELECT 1 FROM channel_events e WHERE e.id = d.event_id)").fetchone()[0]
    if orphans:
        raise RuntimeError(f"{orphans} channel deliveries reference a missing inbound event; "
                           "preserve the database and repair it before upgrading")
    db.execute("""CREATE TABLE channel_deliveries_v86 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT NOT NULL REFERENCES channel_connections(id),
        event_id INTEGER UNIQUE REFERENCES channel_events(id),
        notification_id TEXT UNIQUE REFERENCES notifications(id),
        text TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending'
            CHECK(state IN ('pending','sending','sent','uncertain','failed','cancelled')),
        attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL,
        provider_message_id TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
        reconciled_at TEXT NOT NULL DEFAULT '', reconciliation TEXT NOT NULL DEFAULT '',
        CHECK((event_id IS NULL) <> (notification_id IS NULL)))""")
    db.execute("""INSERT INTO channel_deliveries_v86
        (id, channel_id, event_id, notification_id, text, state, attempts, next_attempt_at,
         provider_message_id, error, reconciled_at, reconciliation)
        SELECT d.id, e.channel_id, d.event_id, NULL, d.text, d.state, d.attempts, d.next_attempt_at,
               d.provider_message_id, d.error, d.reconciled_at, d.reconciliation
        FROM channel_deliveries d JOIN channel_events e ON e.id = d.event_id""")
    db.execute("DROP TABLE channel_deliveries")
    db.execute("ALTER TABLE channel_deliveries_v86 RENAME TO channel_deliveries")
    db.execute("CREATE INDEX IF NOT EXISTS channel_deliveries_pending ON channel_deliveries(state, next_attempt_at)")
    install_resources(db, (("channel_deliveries", "channel_deliveries", "id", ("state",), ("channel_id",)),))


def _install_triggers(db: sqlite3.Connection) -> None:
    # A pending approval needs the owner. It is one row per approval, whatever path created it.
    db.execute(f"""CREATE TRIGGER IF NOT EXISTS notification_approval_created AFTER INSERT ON approvals
        WHEN NEW.status = 'pending'
        BEGIN
            INSERT OR IGNORE INTO notifications(id, kind, bot_id, subject_kind, subject_id, detail, created_at)
            VALUES ({NEW_ID}, 'approval_needs_you', NEW.bot_id, 'approval', NEW.id, '', {STAMP});
        END""")
    # Silence is not consent: an expired or denied approval is a distinct, visible fact.
    db.execute(f"""CREATE TRIGGER IF NOT EXISTS notification_approval_resolved
        AFTER UPDATE OF status ON approvals
        WHEN OLD.status = 'pending' AND NEW.status IN ('expired','denied') AND json_valid(NEW.doc)
        BEGIN
            INSERT OR IGNORE INTO notifications(id, kind, bot_id, subject_kind, subject_id, detail, created_at)
            VALUES ({NEW_ID},
                    CASE NEW.status WHEN 'denied' THEN 'approval_denied' ELSE 'approval_expired' END,
                    NEW.bot_id, 'approval', NEW.id,
                    substr(coalesce(json_extract(NEW.doc, '$.decided_by'), ''), 1, 40), {STAMP});
        END""")
    origins = ",".join(repr(origin) for origin in UNATTENDED_ORIGINS)
    # Failures always matter. A success only notifies for work nobody was watching.
    db.execute(f"""CREATE TRIGGER IF NOT EXISTS notification_run_outcome AFTER UPDATE OF status ON runs
        WHEN NEW.status <> OLD.status AND json_valid(NEW.doc) AND (
            NEW.status IN ('failed','outcome_unknown')
            OR (NEW.status = 'succeeded' AND json_extract(NEW.doc, '$.origin') IN ({origins})))
        BEGIN
            INSERT OR IGNORE INTO notifications(id, kind, bot_id, subject_kind, subject_id, detail, created_at)
            VALUES ({NEW_ID},
                    CASE NEW.status WHEN 'failed' THEN 'run_failed'
                                    WHEN 'outcome_unknown' THEN 'run_outcome_unknown'
                                    ELSE 'run_succeeded' END,
                    NEW.bot_id, 'run', NEW.id,
                    substr(coalesce(json_extract(NEW.doc, '$.exit_reason'), ''), 1, 40), {STAMP});
        END""")
