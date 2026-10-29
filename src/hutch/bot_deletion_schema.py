"""Whole-Bot deletion evidence schema: request rows, item evidence, guarded allowances.

Kept outside store.py so the frozen migration list delegates without growing
the module; the migration keeps the pre-upgrade SQLite backup that
Store._upgrade already takes. The rows intentionally have no foreign key to
bots so evidence survives the Bot row it proves was erased.

Schema v83 also carries the guarded trigger allowances whole-Bot erasure needs:
it rebuilds conversation_artifact_shares so retained share history can survive
its source rows, and it lets a governed deletion redact the content-bearing
columns of otherwise-immutable action, reconciliation and fact-review receipts.
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

#: Pre-existing guards this migration replaces with deletion-aware versions.
_ALLOWANCE_TRIGGERS = (
    'action_intent_immutable',
    'action_receipt_sealed',
    'reconciliation_immutable',
    'memory_decisions_no_update',
    'conversation_task_state_revisions_no_delete',
)

#: Immutable identity and snapshot columns of bot_deletions.
_IMMUTABLE = ('id', 'bot_id', 'bot_name_hash', 'actor', 'note', 'request_hash',
              'created_at', 'expires_at', 'counts_json')

#: Cleanup states a confirmed row may step forward through, never backwards.
_CLEANUP_STATES = ('pending', 'cleaning', 'cleaned', 'needs_attention')
_CLEANUP_MONOTONIC = """
                AND (NEW.cleanup_state = OLD.cleanup_state
                     OR (OLD.cleanup_state = 'pending' AND NEW.cleanup_state IN
                         ('cleaning','cleaned','needs_attention'))
                     OR (OLD.cleanup_state = 'cleaning' AND NEW.cleanup_state IN
                         ('cleaning','cleaned','needs_attention'))
                     OR (OLD.cleanup_state = 'needs_attention' AND NEW.cleanup_state IN
                         ('needs_attention','cleaning','cleaned')))"""

#: One transient row marks a governed erasure transaction; the redaction
#: allowances below fire only while it exists, so ordinary immutability holds.
_SCOPE_TABLE = """CREATE TABLE IF NOT EXISTS bot_deletion_scope (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    request_id TEXT NOT NULL,
    created_at TEXT NOT NULL)"""

#: The rebuilt share table keeps revoked evidence while its sources are erased.
#: It is created under a temporary name, copied, swapped, then renamed in place.
_SHARE_TABLE = """CREATE TABLE conversation_artifact_shares_v83 (
    id TEXT PRIMARY KEY,
    target_conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    source_run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
    source_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    artifact_kind TEXT NOT NULL CHECK(artifact_kind IN ('tool_output','workspace_file')),
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    revoked_at TEXT,
    revoked_by TEXT NOT NULL DEFAULT '')"""

_SHARE_INDEXES = (
    "CREATE UNIQUE INDEX conversation_artifact_shares_active "
    "ON conversation_artifact_shares(target_conversation_id, source_event_id, artifact_kind) "
    "WHERE revoked_at IS NULL",
    "CREATE INDEX conversation_artifact_shares_target "
    "ON conversation_artifact_shares(target_conversation_id, revoked_at, source_event_id DESC)",
)

_SHARE_GUARD = """CREATE TRIGGER conversation_artifact_shares_source_guard
    BEFORE INSERT ON conversation_artifact_shares
    WHEN NOT EXISTS (
        SELECT 1 FROM events e JOIN runs r ON r.id = e.run_id
        WHERE e.id = NEW.source_event_id AND e.run_id = NEW.source_run_id AND e.type = 'tool_result'
          AND r.conversation_id IS NOT NULL AND r.conversation_id != NEW.target_conversation_id
          AND EXISTS (SELECT 1 FROM conversation_runs cr
                      WHERE cr.conversation_id = r.conversation_id AND cr.run_id = r.id)
          AND json_type(e.data, CASE NEW.artifact_kind
                WHEN 'tool_output' THEN '$.artifact' ELSE '$.workspace_file.artifact' END) = 'text'
    )
    BEGIN SELECT RAISE(ABORT, 'share source is not an artifact from a different conversation'); END"""

#: History stays immutable, while the two source ids may be cleared by their own
#: ON DELETE SET NULL actions and revoked_at/revoked_by may be set exactly once.
_SHARE_IMMUTABLE = """CREATE TRIGGER conversation_artifact_shares_immutable
    BEFORE UPDATE ON conversation_artifact_shares
    WHEN NEW.id IS NOT OLD.id OR NEW.target_conversation_id IS NOT OLD.target_conversation_id
      OR NEW.artifact_kind IS NOT OLD.artifact_kind OR NEW.created_at IS NOT OLD.created_at
      OR NEW.actor IS NOT OLD.actor
      OR ((NEW.source_run_id IS NOT OLD.source_run_id)
          AND NOT (NEW.source_run_id IS NULL AND OLD.source_run_id IS NOT NULL))
      OR ((NEW.source_event_id IS NOT OLD.source_event_id)
          AND NOT (NEW.source_event_id IS NULL AND OLD.source_event_id IS NOT NULL))
      OR (OLD.revoked_at IS NOT NULL
          AND (NEW.revoked_at IS NOT OLD.revoked_at OR NEW.revoked_by IS NOT OLD.revoked_by))
      OR (OLD.revoked_at IS NULL
          AND (NEW.revoked_at IS NOT OLD.revoked_at OR NEW.revoked_by IS NOT OLD.revoked_by)
          AND NOT (NEW.revoked_at IS NOT NULL AND NEW.revoked_by != ''))
    BEGIN SELECT RAISE(ABORT, 'artifact share history is immutable; revoke it once'); END"""

#: Explicit deletes stay refused; deleting the target conversation still cascades
#: (the parent row is already gone when this runs, exactly like the task guards).
_SHARE_NO_DELETE = """CREATE TRIGGER conversation_artifact_shares_no_delete
    BEFORE DELETE ON conversation_artifact_shares
    WHEN EXISTS (SELECT 1 FROM conversations WHERE id = OLD.target_conversation_id)
    BEGIN SELECT RAISE(ABORT, 'artifact share history is immutable; revoke it instead'); END"""

_SHARE_OUTBOX = (
    """CREATE TRIGGER conversation_artifact_shares_source_insert_outbox
    AFTER INSERT ON conversation_artifact_shares
    BEGIN
        INSERT INTO resource_outbox(previous_id, resource, resource_id, operation, ts, context)
        SELECT meta.tail_id, 'conversations', c.id, 'updated',
               strftime('%Y-%m-%dT%H:%M:%fZ','now'), json_object('bot_id', c.bot_id)
        FROM resource_outbox_meta meta
        JOIN runs r ON r.id = NEW.source_run_id
        JOIN conversations c ON c.id = r.conversation_id
        WHERE meta.singleton = 1;
        UPDATE resource_outbox_meta SET tail_id = last_insert_rowid() WHERE singleton = 1;
    END""",
    """CREATE TRIGGER conversation_artifact_shares_source_update_outbox
    AFTER UPDATE OF revoked_at, revoked_by ON conversation_artifact_shares
    WHEN OLD.revoked_at IS NOT NEW.revoked_at OR OLD.revoked_by IS NOT NEW.revoked_by
    BEGIN
        INSERT INTO resource_outbox(previous_id, resource, resource_id, operation, ts, context)
        SELECT meta.tail_id, 'conversations', c.id, 'updated',
               strftime('%Y-%m-%dT%H:%M:%fZ','now'), json_object('bot_id', c.bot_id)
        FROM resource_outbox_meta meta
        JOIN runs r ON r.id = NEW.source_run_id
        JOIN conversations c ON c.id = r.conversation_id
        WHERE meta.singleton = 1;
        UPDATE resource_outbox_meta SET tail_id = last_insert_rowid() WHERE singleton = 1;
    END""",
)


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    """Whether one ordinary table is present in this database."""
    return db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                      (table,)).fetchone() is not None


def _drop_previous_guards(db: sqlite3.Connection) -> None:
    """Drop the guards this migration replaces so it is safely re-runnable."""
    for trigger in _TRIGGER_NAMES + _ALLOWANCE_TRIGGERS:
        db.execute(f'DROP TRIGGER IF EXISTS {trigger}')


def _share_table_rebuilt(db: sqlite3.Connection) -> bool:
    """Whether the artifact-share table already has deletion-aware foreign keys."""
    for row in db.execute('PRAGMA foreign_key_list(conversation_artifact_shares)'):
        if row[2] == 'runs' and row[6] == 'SET NULL':
            return True
    return False


def _rebuild_artifact_shares(db: sqlite3.Connection) -> None:
    """Let revoked share history outlive its source rows and vanish with its target chat."""
    if not _table_exists(db, 'conversation_artifact_shares') or _share_table_rebuilt(db):
        return
    columns = ('id, target_conversation_id, source_run_id, source_event_id, artifact_kind, '
               'created_at, actor, revoked_at, revoked_by')
    db.execute('DROP TABLE IF EXISTS conversation_artifact_shares_v83')
    db.execute(_SHARE_TABLE)
    db.execute(f'INSERT INTO conversation_artifact_shares_v83 ({columns}) '
               f'SELECT {columns} FROM conversation_artifact_shares')
    db.execute('DROP TABLE conversation_artifact_shares')
    db.execute('ALTER TABLE conversation_artifact_shares_v83 RENAME TO conversation_artifact_shares')
    for statement in _SHARE_INDEXES:
        db.execute(statement)
    for statement in (_SHARE_GUARD, _SHARE_IMMUTABLE, _SHARE_NO_DELETE, *_SHARE_OUTBOX):
        db.execute(statement)
    from .durable_changes import install_resources
    install_resources(db, (("conversation_artifact_shares", "conversations", "target_conversation_id",
                            ("revoked_at", "revoked_by"), ("source_run_id",)),))


def _install_redaction_allowances(db: sqlite3.Connection) -> None:
    """Allow only a governed redaction of retained receipts, never a content edit.

    Every allowance requires the bot_deletion_scope marker row that only the
    command layer writes inside its one erase transaction, so the same tables
    stay immutable for every other writer.
    """
    governed = 'EXISTS (SELECT 1 FROM bot_deletion_scope WHERE singleton = 1)'
    if _table_exists(db, 'tool_actions'):
        db.execute(f"""CREATE TRIGGER action_intent_immutable
            BEFORE UPDATE OF id, run_id, tool, idem_key, effect, summary, started_at, intent_json,
                intent_hash, effect_key, legacy, workflow_identity, workflow_fingerprint
                ON tool_actions
            WHEN NEW.id IS NOT OLD.id OR NEW.run_id IS NOT OLD.run_id OR NEW.tool IS NOT OLD.tool
              OR NEW.idem_key IS NOT OLD.idem_key OR NEW.effect IS NOT OLD.effect
              OR NEW.started_at IS NOT OLD.started_at OR NEW.intent_hash IS NOT OLD.intent_hash
              OR NEW.effect_key IS NOT OLD.effect_key OR NEW.legacy IS NOT OLD.legacy
              OR NEW.workflow_identity IS NOT OLD.workflow_identity
              OR NEW.workflow_fingerprint IS NOT OLD.workflow_fingerprint
              OR ((NEW.summary IS NOT OLD.summary OR NEW.intent_json IS NOT OLD.intent_json)
                  AND NOT ({governed} AND NEW.summary = '' AND NEW.intent_json = '{{}}'))
            BEGIN SELECT RAISE(ABORT, 'action intent is immutable'); END""")
        db.execute(f"""CREATE TRIGGER action_receipt_sealed
            BEFORE UPDATE OF status, result_digest, result_json, finished_at ON tool_actions
            WHEN (OLD.status != 'started' OR NEW.status NOT IN ('done', 'failed', 'unknown')
                  OR (NEW.status IN ('done', 'failed')
                      AND EXISTS(SELECT 1 FROM runs WHERE id = OLD.run_id AND sealed = 1)))
              AND NOT ({governed} AND NEW.status = OLD.status
                       AND NEW.result_digest IS OLD.result_digest
                       AND NEW.finished_at IS OLD.finished_at AND NEW.result_json = '{{}}')
            BEGIN SELECT RAISE(ABORT, 'action receipt is sealed'); END""")
    if _table_exists(db, 'action_reconciliations'):
        db.execute(f"""CREATE TRIGGER reconciliation_immutable
            BEFORE UPDATE ON action_reconciliations
            WHEN NOT ({governed} AND NEW.evidence = '[deleted]' AND NEW.action_id IS OLD.action_id
                      AND NEW.run_id IS OLD.run_id AND NEW.intent_hash IS OLD.intent_hash
                      AND NEW.outcome IS OLD.outcome AND NEW.recorded_by IS OLD.recorded_by
                      AND NEW.recorded_at IS OLD.recorded_at)
            BEGIN SELECT RAISE(ABORT, 'action reconciliation is immutable'); END""")
    if _table_exists(db, 'memory_fact_decisions'):
        db.execute(f"""CREATE TRIGGER memory_decisions_no_update
            BEFORE UPDATE ON memory_fact_decisions
            WHEN NOT ({governed} AND NEW.note = '' AND NEW.fact_id IS OLD.fact_id AND NEW.action IS OLD.action
                      AND NEW.request_hash IS OLD.request_hash AND NEW.actor IS OLD.actor
                      AND NEW.created_at IS OLD.created_at AND NEW.result_json IS OLD.result_json)
            BEGIN SELECT RAISE(ABORT, 'fact review is immutable'); END""")
    if _table_exists(db, 'conversation_task_state_revisions'):
        db.execute("""CREATE TRIGGER conversation_task_state_revisions_no_delete
            BEFORE DELETE ON conversation_task_state_revisions
            WHEN EXISTS (SELECT 1 FROM conversations WHERE id = OLD.conversation_id)
            BEGIN SELECT RAISE(ABORT, 'task-state revisions are retained'); END""")


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
    _install_request_guards(db)


def _install_request_guards(db: sqlite3.Connection) -> None:
    """Install the insert, lifecycle-update and no-delete guards on requests."""
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
                AND NEW.cleanup_attempts >= OLD.cleanup_attempts{_CLEANUP_MONOTONIC})
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
    """Whole-Bot deletion evidence tables and guarded allowances for schema v83.

    One bot_deletions row is the request, the audit record and the cleanup job
    row. bot_deletion_items records one content-free item per erased row or
    managed file: an opaque id or hash, an optional content hash and a
    timestamp, never erased text or paths. The allowances are exact redaction
    shapes; they never permit a content edit.
    """
    _drop_previous_guards(db)
    db.execute(_SCOPE_TABLE)
    _rebuild_artifact_shares(db)
    _install_request_table(db)
    _install_item_table(db)
    _install_redaction_allowances(db)
