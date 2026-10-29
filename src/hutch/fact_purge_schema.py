"""Purge schema: tombstones, guarded content updates and deletion evidence.

Kept outside ``store.py`` so the frozen migration list can delegate without
growing the module. The migration keeps the pre-upgrade SQLite backup that
``Store._upgrade`` already takes.
"""
from __future__ import annotations

import sqlite3

#: Guards this module installs, in every case after dropping any prior copy.
_TRIGGER_NAMES = (
    'memory_facts_provenance_immutable',
    'memory_facts_content_guard',
    'memory_facts_no_tombstone_insert',
    'memory_fact_share_update_guard',
    'workspace_task_fact_share_update_guard',
    'memory_purge_request_insert_guard',
    'memory_purge_request_update_guard',
    'memory_purge_request_no_delete',
    'memory_purge_item_no_update',
    'memory_purge_item_no_delete',
)


def _drop_previous_guards(db: sqlite3.Connection) -> None:
    """Drop the guards this migration replaces so it is safely re-runnable."""
    for trigger in _TRIGGER_NAMES:
        db.execute(f'DROP TRIGGER IF EXISTS {trigger}')
    for legacy in ('memory_facts_immutable', 'memory_fact_share_snapshot_immutable',
                   'workspace_task_fact_share_immutable'):
        db.execute(f'DROP TRIGGER IF EXISTS {legacy}')


def _ensure_columns(db: sqlite3.Connection) -> None:
    """Add the tombstone columns once, on a database that predates this feature."""
    for table in ('memory_facts', 'memory_fact_shares', 'workspace_task_fact_shares'):
        columns = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
        if 'purged_at' not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN purged_at TEXT NOT NULL DEFAULT ''")
    columns = {row[1] for row in db.execute('PRAGMA table_info(memory_facts)')}
    if 'purge_id' not in columns:
        db.execute("ALTER TABLE memory_facts ADD COLUMN purge_id TEXT NOT NULL DEFAULT ''")


def _install_fact_guards(db: sqlite3.Connection) -> None:
    """Allow exactly one purge-shaped content update; keep review and provenance immutable."""
    db.execute("""CREATE TRIGGER memory_facts_provenance_immutable
        BEFORE UPDATE ON memory_facts
        WHEN NEW.id IS NOT OLD.id OR NEW.bot_id IS NOT OLD.bot_id
          OR NEW.scope_kind IS NOT OLD.scope_kind OR NEW.scope_id IS NOT OLD.scope_id
          OR NEW.revision IS NOT OLD.revision OR NEW.run_id IS NOT OLD.run_id
          OR NEW.source IS NOT OLD.source OR NEW.updated_at IS NOT OLD.updated_at
        BEGIN SELECT RAISE(ABORT, 'fact provenance and revision are immutable'); END""")
    db.execute("""CREATE TRIGGER memory_facts_content_guard
        BEFORE UPDATE OF key, value, content_hash, status, purged_at, purge_id ON memory_facts
        WHEN (NEW.key IS NOT OLD.key OR NEW.value IS NOT OLD.value
              OR NEW.content_hash IS NOT OLD.content_hash
              OR NEW.purged_at IS NOT OLD.purged_at OR NEW.purge_id IS NOT OLD.purge_id)
         AND NOT (OLD.purged_at = '' AND NEW.purged_at != '' AND NEW.purge_id != ''
                  AND NEW.status = 'archived' AND NEW.value = ''
                  AND NEW.key = 'purged:' || OLD.id)
        BEGIN SELECT RAISE(ABORT, 'fact content is immutable; revise it or purge the archived fact'); END""")
    db.execute("""CREATE TRIGGER memory_facts_no_tombstone_insert
        BEFORE INSERT ON memory_facts
        WHEN NEW.purged_at != '' OR NEW.purge_id != '' OR NEW.key = 'purged:' || NEW.id
        BEGIN SELECT RAISE(ABORT, 'purged fact tombstones are created only by a governed purge'); END""")


def _install_share_guards(db: sqlite3.Connection) -> None:
    """Allow one revocation and one purge-shaped update per snapshot; block anything else."""
    db.execute("""CREATE TRIGGER memory_fact_share_update_guard
        BEFORE UPDATE ON memory_fact_shares
        WHEN NEW.id IS NOT OLD.id OR NEW.source_fact_id IS NOT OLD.source_fact_id
          OR NEW.source_bot_id IS NOT OLD.source_bot_id
          OR NEW.source_display_name IS NOT OLD.source_display_name
          OR NEW.source_scope_kind IS NOT OLD.source_scope_kind
          OR NEW.source_scope_id IS NOT OLD.source_scope_id
          OR NEW.target_bot_id IS NOT OLD.target_bot_id
          OR NEW.target_display_name IS NOT OLD.target_display_name
          OR NEW.fact_revision IS NOT OLD.fact_revision OR NEW.created_at IS NOT OLD.created_at
          OR ((NEW.fact_key IS NOT OLD.fact_key OR NEW.fact_value IS NOT OLD.fact_value
               OR NEW.content_hash IS NOT OLD.content_hash
               OR NEW.purged_at IS NOT OLD.purged_at)
              AND NOT (OLD.purged_at = '' AND NEW.purged_at != ''
                       AND NEW.fact_key = 'purged:' || OLD.id AND NEW.fact_value = 'purged'))
          OR ((NEW.revoked_at IS NOT OLD.revoked_at OR NEW.revoked_by IS NOT OLD.revoked_by)
              AND NOT (OLD.revoked_at IS NULL AND OLD.purged_at = ''
                       AND NEW.revoked_at IS NOT NULL AND NEW.revoked_by != ''))
        BEGIN SELECT RAISE(ABORT, 'fact share snapshots are immutable; revoke once or purge once'); END""")
    db.execute("""CREATE TRIGGER workspace_task_fact_share_update_guard
        BEFORE UPDATE ON workspace_task_fact_shares
        WHEN NOT (OLD.purged_at = '' AND NEW.purged_at != ''
                  AND NEW.fact_key = '' AND NEW.fact_value = 'purged'
                  AND NEW.id IS OLD.id AND NEW.workspace_task_id IS OLD.workspace_task_id
                  AND NEW.source_fact_id IS OLD.source_fact_id
                  AND NEW.source_bot_id IS OLD.source_bot_id
                  AND NEW.source_display_name IS OLD.source_display_name
                  AND NEW.source_scope_kind IS OLD.source_scope_kind
                  AND NEW.source_scope_id IS OLD.source_scope_id
                  AND NEW.fact_revision IS OLD.fact_revision
                  AND NEW.created_at IS OLD.created_at)
        BEGIN SELECT RAISE(ABORT, 'task fact share snapshots are immutable; purge erases their content once'); END""")


def _install_request_table(db: sqlite3.Connection) -> None:
    """Create the immutable purge-request row and its token/outcome guards."""
    db.execute("""CREATE TABLE IF NOT EXISTS memory_purge_requests (
        id TEXT PRIMARY KEY,
        bot_id TEXT NOT NULL,
        scope_kind TEXT NOT NULL CHECK(scope_kind IN ('key','all')),
        scope_key TEXT NOT NULL DEFAULT '',
        actor TEXT NOT NULL CHECK(length(actor) BETWEEN 1 AND 120),
        note TEXT NOT NULL DEFAULT '',
        request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
        token_hash TEXT NOT NULL CHECK(length(token_hash) IN (0,64)),
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        confirmed_at TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL CHECK(status IN ('pending','confirmed','expired','superseded')),
        counts_json TEXT NOT NULL CHECK(json_valid(counts_json)),
        result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json)))""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memory_purge_requests_bot "
               "ON memory_purge_requests(bot_id, created_at DESC)")
    db.execute("""CREATE TRIGGER memory_purge_request_insert_guard
        BEFORE INSERT ON memory_purge_requests
        WHEN NEW.status != 'pending' OR NEW.confirmed_at != ''
          OR length(NEW.token_hash) != 64 OR NEW.scope_kind = 'key' AND NEW.scope_key = ''
        BEGIN SELECT RAISE(ABORT, 'new purge requests are pending, token-bound and scoped'); END""")
    db.execute("""CREATE TRIGGER memory_purge_request_update_guard
        BEFORE UPDATE ON memory_purge_requests
        WHEN NEW.id IS NOT OLD.id OR NEW.bot_id IS NOT OLD.bot_id
          OR NEW.scope_kind IS NOT OLD.scope_kind OR NEW.scope_key IS NOT OLD.scope_key
          OR NEW.actor IS NOT OLD.actor OR NEW.note IS NOT OLD.note
          OR NEW.request_hash IS NOT OLD.request_hash OR NEW.created_at IS NOT OLD.created_at
          OR NEW.expires_at IS NOT OLD.expires_at
          OR (OLD.status != 'pending'
              AND NOT (NEW.status = OLD.status AND NEW.confirmed_at = OLD.confirmed_at
                       AND NEW.counts_json = OLD.counts_json
                       AND NEW.result_json = OLD.result_json))
        BEGIN SELECT RAISE(ABORT, 'purge requests are immutable after their outcome'); END""")
    db.execute("""CREATE TRIGGER memory_purge_request_no_delete
        BEFORE DELETE ON memory_purge_requests
        BEGIN SELECT RAISE(ABORT, 'purge requests are retained as deletion evidence'); END""")


def _install_item_table(db: sqlite3.Connection) -> None:
    """Create the per-row, content-free purge evidence and its immutability guards."""
    db.execute("""CREATE TABLE IF NOT EXISTS memory_purge_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL REFERENCES memory_purge_requests(id) ON DELETE RESTRICT,
        table_name TEXT NOT NULL CHECK(table_name IN
            ('memory_facts','memory_fact_shares','workspace_task_fact_shares','memory','idempotency_keys')),
        row_id TEXT NOT NULL,
        original_content_hash TEXT NOT NULL DEFAULT '',
        purged_at TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_memory_purge_items_request "
               "ON memory_purge_items(request_id, id)")
    for operation in ('update', 'delete'):
        db.execute(f"CREATE TRIGGER memory_purge_item_no_{operation} BEFORE {operation.upper()} "
                   "ON memory_purge_items "
                   "BEGIN SELECT RAISE(ABORT, 'purge evidence is immutable'); END")


def _install_evidence_tables(db: sqlite3.Connection) -> None:
    """Create both evidence tables, in foreign-key order."""
    _install_request_table(db)
    _install_item_table(db)


def migrate(db: sqlite3.Connection) -> None:
    """Governed permanent deletion for saved reference facts (schema v83).

    A purged row keeps its identity, scope, revision and review hashes so a
    reviewer can prove the erasure; its content, its search-index row and the
    shared snapshot copies are erased. Transcripts, files and backups are out
    of scope and are named in the confirmation preview instead of being
    silently claimed.
    """
    _drop_previous_guards(db)
    _ensure_columns(db)
    _install_fact_guards(db)
    _install_share_guards(db)
    _install_evidence_tables(db)
