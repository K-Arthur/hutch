"""Schema v94: Inbound webhook sources and delivery tracking (G04).

Defines ``webhook_sources`` and ``webhook_deliveries`` tables.
Supports constant-time SHA-256 token verification, one-time secret generation,
dual-window secret rotation, idempotency deduplication, and atomic admission.
"""

from __future__ import annotations

import sqlite3


def migrate(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS webhook_sources (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        token_prefix TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        prev_token_prefix TEXT NOT NULL DEFAULT '',
        prev_token_hash TEXT NOT NULL DEFAULT '',
        prev_token_expires_at TEXT NOT NULL DEFAULT '',
        prompt_template TEXT NOT NULL DEFAULT '',
        workflow_id TEXT NOT NULL DEFAULT '',
        cooldown_seconds REAL NOT NULL DEFAULT 0.0 CHECK(cooldown_seconds >= 0.0),
        max_per_hour INTEGER NOT NULL DEFAULT 60 CHECK(max_per_hour >= 0),
        enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
        last_delivery_at TEXT,
        last_success_at TEXT,
        last_error TEXT NOT NULL DEFAULT '',
        error_count INTEGER NOT NULL DEFAULT 0 CHECK(error_count >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_webhook_sources_bot "
               "ON webhook_sources(bot_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_webhook_sources_token_hash "
               "ON webhook_sources(token_hash)")

    db.execute("""CREATE TABLE IF NOT EXISTS webhook_deliveries (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES webhook_sources(id) ON DELETE CASCADE,
        idempotency_key TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL CHECK(status IN ('received', 'processed', 'duplicate', 'rejected')),
        status_code INTEGER NOT NULL,
        error_message TEXT NOT NULL DEFAULT '',
        payload_bytes INTEGER NOT NULL DEFAULT 0,
        payload_sha256 TEXT NOT NULL DEFAULT '',
        content_type TEXT NOT NULL DEFAULT '',
        run_id TEXT,
        received_at TEXT NOT NULL,
        processed_at TEXT,
        client_ip TEXT NOT NULL DEFAULT ''
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_source "
               "ON webhook_deliveries(source_id, received_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_idempotency "
               "ON webhook_deliveries(source_id, idempotency_key, status)")
    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_deliveries_processed_idem
               ON webhook_deliveries(source_id, idempotency_key)
               WHERE idempotency_key != '' AND status = 'processed'""")
