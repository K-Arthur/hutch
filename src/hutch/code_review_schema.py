"""Schema v89: append-only verification and prune receipts for coding handoffs.

A receipt records what an owner-run check observed, never the code or the output
itself: an argv digest, the exit code, the duration, a content-free worktree
fingerprint and the timestamp. The table is append-only, so re-running a check
adds history instead of rewriting an earlier observation. Both triggers and the
migration are idempotent for a partially applied development database.
"""

from __future__ import annotations

import sqlite3

from .durable_changes import install_resources


def migrate(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS code_handoff_receipts (
        id TEXT PRIMARY KEY,
        handoff_id TEXT NOT NULL REFERENCES code_handoffs(id) ON DELETE RESTRICT,
        kind TEXT NOT NULL CHECK(kind IN ('verify','prune')),
        argv_digest TEXT NOT NULL DEFAULT '',
        exit_code INTEGER,
        duration_ms INTEGER NOT NULL DEFAULT 0 CHECK(duration_ms >= 0),
        changed_files INTEGER NOT NULL DEFAULT 0 CHECK(changed_files >= 0),
        worktree_digest TEXT NOT NULL DEFAULT '',
        timed_out INTEGER NOT NULL DEFAULT 0 CHECK(timed_out IN (0,1)),
        output_truncated INTEGER NOT NULL DEFAULT 0 CHECK(output_truncated IN (0,1)),
        detail TEXT NOT NULL DEFAULT '' CHECK(length(detail) <= 500),
        created_at TEXT NOT NULL,
        CHECK(
            (kind = 'verify' AND length(argv_digest) = 64 AND exit_code IS NOT NULL)
            OR (kind = 'prune' AND argv_digest = '' AND exit_code IS NULL)
        ),
        CHECK(kind = 'prune' OR length(worktree_digest) = 64)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS code_handoff_receipts_latest "
               "ON code_handoff_receipts(handoff_id, kind)")
    db.execute("""CREATE TRIGGER IF NOT EXISTS code_handoff_receipts_append_only
        BEFORE UPDATE ON code_handoff_receipts
        BEGIN SELECT RAISE(ABORT, 'code handoff receipts are append-only'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS code_handoff_receipts_no_delete
        BEFORE DELETE ON code_handoff_receipts
        BEGIN SELECT RAISE(ABORT, 'code handoff receipts are retained history'); END""")
    # Reuse the code_handoffs invalidation stream: a receipt changes the task card,
    # and the resource identifier is the handoff, not the receipt.
    install_resources(db, (("code_handoff_receipts", "code_handoffs", "handoff_id", (), ()),))
