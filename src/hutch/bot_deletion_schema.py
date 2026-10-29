"""Whole-Bot deletion evidence schema: request rows, item evidence, immutability guards.

Kept outside store.py so the frozen migration list delegates without growing
the module; the migration keeps the pre-upgrade SQLite backup that
Store._upgrade already takes. The rows intentionally have no foreign key to
bots so evidence survives the Bot row it proves was erased.
"""
from __future__ import annotations

import sqlite3

#: Guards this module installs, dropped first so the migration is re-runnable.
_TRIGGER_NAMES = (
    'bot_deletion_request_insert_guard',
    'bot_deletion_request_update_guard',
    'bot_deletion_request_no_delete',
    'bot_deletion_item_no_update',
    'bot_deletion_item_no_delete',
)

#: Immutable identity and snapshot columns of bot_deletions.
_IMMUTABLE = ('id', 'bot_id', 'bot_name_hash', 'actor', 'note', 'request_hash',
              'created_at', 'expires_at', 'counts_json')

#: The only cleanup states a confirmed row may hold after the Bot rows are gone.
_CLEANUP_STATES = ('pending', 'cleaning', 'cleaned', 'needs_attention')


def _drop_previous_guards(db: sqlite3.Connection) -> None:
    """Drop the guards this migration replaces so it is safely re-runnable."""
    for trigger in _TRIGGER_NAMES:
        db.execute(f'DROP TRIGGER IF EXISTS {trigger}')


def _install_request_table(db: sqlite3.Connection) -> None:
    """Create the content-free per-request audit row and its lifecycle guards."""
    db.execute("""CREATE TABLE IF NOT EXISTS bot_deletions (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL CHECK(length(bot_id) BETWEEN 1 AND 120),
        bot_name_hash TEXT NOT NULL CHECK(length(bot_name_hash) = 64),
        actor TEXT NOT NULL CHECK(length(actor) BETWEEN 1 AND 120),
        note TEXT NOT NULL DEFAULT '' CHECK(length(note) <= 1000),
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        token_hash TEXT NOT NULL CHECK(length(token_hash) IN (0, 64)),
        status TEXT NOT NULL CHECK(status IN ('pending','confirmed','expired','superseded','failed')),
        counts_json TEXT NOT NULL CHECK(json_valid(counts_json)),
        result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json)),
        manifest_hash TEXT NOT NULL DEFAULT '' CHECK(length(manifest_hash) IN (0, 64)),
        cleanup_state TEXT NOT NULL DEFAULT 'none'
            CHECK(cleanup_state IN ('none','pending','cleaning','cleaned','needs_attention')),
        cleanup_attempts INTEGER NOT NULL DEFAULT 0 CHECK(cleanup_attempts >= 0),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        confirmed_at TEXT NOT NULL DEFAULT '',
        deleted_at TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '' CHECK(length(error) <= 2000))""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_bot_deletions_bot "
               "ON bot_deletions(bot_id, created_at DESC)")
    db.execute("""CREATE TRIGGER bot_deletion_request_insert_guard
        BEFORE INSERT ON bot_deletions
        WHEN NEW.status != 'pending' OR NEW.confirmed_at != '' OR NEW.deleted_at != ''
          OR NEW.result_json != '{}' OR NEW.manifest_hash != '' OR NEW.cleanup_state != 'none'
          OR NEW.cleanup_attempts != 0 OR NEW.error != '' OR length(NEW.token_hash) != 64
          OR NEW.expires_at = '' OR NEW.created_at = ''
        BEGIN SELECT RAISE(ABORT, 'new deletion requests are pending, token-bound and unconfirmed'); END""")
    immutable_sql = ' OR '.join(f'NEW.{column} IS NOT OLD.{column}' for column in _IMMUTABLE)
    cleanup_states = ', '.join("'" + state + "'" for state in _CLEANUP_STATES)
    db.execute(f"""CREATE TRIGGER bot_deletion_request_update_guard
        BEFORE UPDATE ON bot_deletions
        WHEN {immutable_sql}
          OR NOT (
            (OLD.status = 'pending' AND (
                (NEW.status = 'confirmed' AND NEW.confirmed_at != '' AND NEW.deleted_at != ''
                 AND NEW.token_hash = '' AND NEW.result_json != '{{}}'
                 AND length(NEW.manifest_hash) = 64 AND NEW.cleanup_state = 'pending'
                 AND NEW.cleanup_attempts = 0 AND NEW.error = '')
             OR (NEW.status IN ('expired','superseded','failed')
                 AND NEW.confirmed_at = '' AND NEW.deleted_at = ''
                 AND NEW.result_json = '{{}}' AND NEW.manifest_hash = ''
                 AND NEW.cleanup_state = 'none' AND NEW.cleanup_attempts = 0
                 AND NEW.token_hash = ''
                 AND (NEW.error = '' OR NEW.status = 'failed'))
            ))
            OR (OLD.status = 'confirmed' AND NEW.status = 'confirmed'
                AND NEW.confirmed_at = OLD.confirmed_at AND NEW.deleted_at = OLD.deleted_at
                AND NEW.token_hash = OLD.token_hash AND NEW.result_json = OLD.result_json
                AND NEW.manifest_hash = OLD.manifest_hash
                AND NEW.cleanup_state IN ({cleanup_states})
                AND NEW.cleanup_attempts >= OLD.cleanup_attempts)
          )
        BEGIN SELECT RAISE(ABORT, 'deletion requests are immutable after their outcome'); END""")
    db.execute("""CREATE TRIGGER bot_deletion_request_no_delete
        BEFORE DELETE ON bot_deletions
        BEGIN SELECT RAISE(ABORT, 'deletion requests are retained as deletion evidence'); END""")


def _install_item_table(db: sqlite3.Connection) -> None:
    """Create the per-row, content-free item evidence and its immutability guards."""
    db.execute("""CREATE TABLE IF NOT EXISTS bot_deletion_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL REFERENCES bot_deletions(id) ON DELETE RESTRICT,
        store_name TEXT NOT NULL CHECK(length(store_name) BETWEEN 1 AND 80),
        row_id TEXT NOT NULL CHECK(length(row_id) BETWEEN 1 AND 128),
        original_content_hash TEXT NOT NULL DEFAULT '' CHECK(length(original_content_hash) IN (0, 64)),
        erased_at TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_bot_deletion_items_request "
               "ON bot_deletion_items(request_id, id)")
    db.execute("""CREATE TRIGGER bot_deletion_item_no_update
        BEFORE UPDATE ON bot_deletion_items
        BEGIN SELECT RAISE(ABORT, 'deletion item evidence is immutable'); END""")
    db.execute("""CREATE TRIGGER bot_deletion_item_no_delete
        BEFORE DELETE ON bot_deletion_items
        BEGIN SELECT RAISE(ABORT, 'deletion item evidence is immutable'); END""")


def migrate(db: sqlite3.Connection) -> None:
    """Whole-Bot deletion evidence tables for schema v83.

    One bot_deletions row is the request, the audit record and the cleanup job
    row. bot_deletion_items records one content-free item per erased row or
    managed file: an opaque id or hash, an optional content hash and a
    timestamp, never erased text or paths.
    """
    _drop_previous_guards(db)
    _install_request_table(db)
    _install_item_table(db)
