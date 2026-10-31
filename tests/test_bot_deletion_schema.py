"""Schema v83 evidence tables for whole-Bot deletion: upgrade, guards, re-runs."""
from __future__ import annotations

import sqlite3

import pytest

from hutch.bot_deletion_schema import migrate as migrate_deletion_schema
from hutch.models import Bot
from hutch.store import SCHEMA_VERSION, Store

EVIDENCE_TABLES = {'bot_deletions', 'bot_deletion_items'}
GUARD_TRIGGERS = {
    'bot_deletion_request_insert_guard',
    'bot_deletion_request_update_guard',
    'bot_deletion_request_no_delete',
    'bot_deletion_item_no_update',
    'bot_deletion_item_no_delete',
}
PENDING = dict(
    bot_id='bot_a', bot_name_hash='a' * 64, actor='operator', note='',
    request_hash='b' * 64, token_hash='c' * 64, status='pending',
    counts_json='{"total": 1}', result_json='{}', manifest_hash='',
    cleanup_state='none', cleanup_attempts=0,
    created_at='2026-10-29T00:00:00+00:00', expires_at='2026-10-29T00:10:00+00:00',
    confirmed_at='', deleted_at='', error='')


def insert_pending(db, request_id='del_a', **overrides):
    """Insert one valid pending request shape the guards must accept."""
    record = {**PENDING, 'id': request_id, **overrides}
    columns = ', '.join(record)
    marks = ', '.join('?' for _ in record)
    db.execute(f'INSERT INTO bot_deletions ({columns}) VALUES ({marks})', tuple(record.values()))
    return record


def refuse(db, sql, args=(), match=None):
    """Assert SQLite refuses a statement, optionally matching the guard message."""
    with pytest.raises(sqlite3.IntegrityError) as caught:
        db.execute(sql, args)
    if match is not None:
        assert match in str(caught.value), str(caught.value)


def schema_names(db, kind):
    """Every sqlite_master name of one kind in the database."""
    return {row[0] for row in db.execute('SELECT name FROM sqlite_master WHERE type = ?', (kind,))}


def memory_db():
    """A fresh in-memory database with foreign keys on and the v83 schema."""
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    migrate_deletion_schema(db)
    return db


def make_v82(db_path):
    """Turn a current store file into its v82 shape by dropping the v83 evidence."""
    db = sqlite3.connect(db_path)
    try:
        db.execute('DROP TABLE IF EXISTS bot_deletion_items')
        db.execute('DROP TABLE IF EXISTS bot_deletions')
        db.execute('PRAGMA user_version = 82')
        db.commit()
    finally:
        db.close()


def test_fresh_store_carries_v83_evidence_tables_and_guards(store):
    # This pins the bot-deletion feature floor, not the whole store's latest version:
    # later additive migrations (for example v84 personal operations) may advance it.
    assert SCHEMA_VERSION >= 83
    assert store.schema_version == SCHEMA_VERSION
    db = store._db
    assert EVIDENCE_TABLES <= schema_names(db, 'table')
    assert GUARD_TRIGGERS <= schema_names(db, 'trigger')
    assert 'idx_bot_deletions_bot' in schema_names(db, 'index')
    assert 'idx_bot_deletion_items_request' in schema_names(db, 'index')
    assert db.execute('SELECT COUNT(*) FROM bot_deletions').fetchone()[0] == 0
    assert db.execute('PRAGMA foreign_key_list(bot_deletions)').fetchall() == []
    edges = db.execute('PRAGMA foreign_key_list(bot_deletion_items)').fetchall()
    assert [(row['table'], row['on_delete']) for row in edges] == [('bot_deletions', 'RESTRICT')]


def test_v82_store_with_data_upgrades_to_v83_and_keeps_a_backup(config):
    db_path = config.db_path
    first = Store(config)
    try:
        bot = first.create_bot(Bot(name='upgrade-bot', display_name='Upgrade Bot'))
        conversation, _ = first.create_conversation(bot.id, 'upgrade-chat', idem_key='upgrade-chat',
                                                    request_hash='upgrade-chat')
        first.remember(bot.id, 'upgrade-key', 'upgrade-value', conversation_id=conversation['id'])
        before = dict(first._db.execute('SELECT id, name, doc FROM bots').fetchone())
        memory_before = first._db.execute('SELECT COUNT(*) FROM memory_facts').fetchone()[0]
    finally:
        first.close()
    make_v82(db_path)
    backup = db_path.with_suffix('.db.bak-v82')
    assert not backup.exists()
    upgraded = Store(config)
    try:
        assert upgraded.schema_version == SCHEMA_VERSION
        assert dict(upgraded._db.execute('SELECT id, name, doc FROM bots').fetchone()) == before
        assert upgraded._db.execute('SELECT COUNT(*) FROM memory_facts').fetchone()[0] == memory_before
        assert EVIDENCE_TABLES <= schema_names(upgraded._db, 'table')
        assert GUARD_TRIGGERS <= schema_names(upgraded._db, 'trigger')
        assert upgraded._db.execute('SELECT COUNT(*) FROM bot_deletions').fetchone()[0] == 0
    finally:
        upgraded.close()
    assert backup.exists()
    with sqlite3.connect(backup) as backup_db:
        assert backup_db.execute('PRAGMA user_version').fetchone()[0] == 82
        assert backup_db.execute('SELECT COUNT(*) FROM bots').fetchone()[0] == 1
        assert backup_db.execute('SELECT name FROM bots').fetchone()[0] == 'upgrade-bot'


def test_insert_guard_accepts_only_pending_token_bound_shapes():
    db = memory_db()
    try:
        insert_pending(db)
        illegal = (
            {'status': 'confirmed'}, {'status': 'expired'}, {'status': 'failed'},
            {'token_hash': ''}, {'token_hash': 'short'},
            {'confirmed_at': 'now'}, {'deleted_at': 'now'}, {'result_json': '{"status": "confirmed"}'},
            {'manifest_hash': 'd' * 64}, {'cleanup_state': 'pending'}, {'cleanup_attempts': 1},
            {'error': 'boom'}, {'bot_name_hash': 'short'}, {'request_hash': 'short'},
            {'counts_json': 'not-json'}, {'cleanup_state': 'unknown'}, {'status': 'unknown'},
            {'expires_at': ''},
        )
        for index, overrides in enumerate(illegal):
            with pytest.raises(sqlite3.IntegrityError):
                insert_pending(db, f'bad_{index}', **overrides)
        assert db.execute('SELECT COUNT(*) FROM bot_deletions').fetchone()[0] == 1
    finally:
        db.close()


def test_update_guard_rejects_identity_count_and_unfinished_outcomes():
    db = memory_db()
    try:
        insert_pending(db)
        for column, value in (('bot_id', 'bot_b'), ('bot_name_hash', 'd' * 64), ('actor', 'intruder'),
                              ('note', 'changed'), ('request_hash', 'd' * 64),
                              ('counts_json', '{"total": 2}'), ('created_at', 'later'),
                              ('expires_at', 'later'), ('id', 'del_b')):
            refuse(db, f'UPDATE bot_deletions SET {column} = ? WHERE id = ?', (value, 'del_a'),
                   match='immutable')
        refuse(db, "UPDATE bot_deletions SET status = 'confirmed' WHERE id = 'del_a'", match='immutable')
        refuse(db, "UPDATE bot_deletions SET status = 'expired' WHERE id = 'del_a'", match='immutable')
        refuse(db, "UPDATE bot_deletions SET status = 'superseded', token_hash = ? WHERE id = 'del_a'",
               ('c' * 64,), match='immutable')
        assert db.execute('SELECT status FROM bot_deletions').fetchone()[0] == 'pending'
    finally:
        db.close()


def test_update_guard_allows_terminal_walk_and_cleanup_transitions():
    db = memory_db()
    try:
        insert_pending(db, 'del_expire')
        db.execute("UPDATE bot_deletions SET status = 'expired', token_hash = '' WHERE id = 'del_expire'")
        insert_pending(db, 'del_fail')
        db.execute("UPDATE bot_deletions SET status = 'failed', token_hash = '', error = 'preview raced' "
                   "WHERE id = 'del_fail'")
        insert_pending(db, 'del_confirm')
        db.execute("UPDATE bot_deletions SET status = 'confirmed', confirmed_at = 'now', deleted_at = 'now', "
                   "token_hash = '', result_json = '{\"status\": \"confirmed\"}', manifest_hash = ?, "
                   "cleanup_state = 'pending' WHERE id = 'del_confirm'", ('d' * 64,))
        db.execute("UPDATE bot_deletions SET cleanup_state = 'cleaning', cleanup_attempts = 1 "
                   "WHERE id = 'del_confirm'")
        db.execute("UPDATE bot_deletions SET cleanup_state = 'needs_attention', cleanup_attempts = 2, "
                   "error = 'paths remain' WHERE id = 'del_confirm'")
        db.execute("UPDATE bot_deletions SET cleanup_state = 'cleaned', cleanup_attempts = 3, error = '' "
                   "WHERE id = 'del_confirm'")
        statuses = dict(db.execute('SELECT id, status FROM bot_deletions').fetchall())
        assert statuses == {'del_expire': 'expired', 'del_fail': 'failed', 'del_confirm': 'confirmed'}
        refuse(db, "UPDATE bot_deletions SET status = 'failed' WHERE id = 'del_confirm'", match='immutable')
        refuse(db, "UPDATE bot_deletions SET result_json = '{}' WHERE id = 'del_confirm'", match='immutable')
        refuse(db, "UPDATE bot_deletions SET cleanup_attempts = 1 WHERE id = 'del_confirm'",
               match='immutable')
        refuse(db, "UPDATE bot_deletions SET cleanup_state = 'pending', cleanup_attempts = 4 "
                   "WHERE id = 'del_confirm'", match='immutable')
        refuse(db, "UPDATE bot_deletions SET cleanup_state = 'cleaning', cleanup_attempts = 4 "
                   "WHERE id = 'del_confirm'", match='immutable')
    finally:
        db.close()


def test_evidence_rows_cannot_be_deleted_or_rewritten():
    db = memory_db()
    try:
        insert_pending(db)
        db.execute("INSERT INTO bot_deletion_items (request_id, store_name, row_id, original_content_hash, "
                   "erased_at) VALUES ('del_a', 'runs', 'run_a', ?, 'now')", ('e' * 64,))
        refuse(db, "UPDATE bot_deletion_items SET row_id = 'run_b'", match='immutable')
        refuse(db, "UPDATE bot_deletion_items SET original_content_hash = ''", match='immutable')
        refuse(db, 'DELETE FROM bot_deletion_items', match='immutable')
        refuse(db, 'DELETE FROM bot_deletions', match='retained')
        refuse(db, "INSERT INTO bot_deletion_items (request_id, store_name, row_id, erased_at) "
                   "VALUES ('missing', 'runs', 'run_a', 'now')", match='FOREIGN KEY')
        assert db.execute('SELECT COUNT(*) FROM bot_deletion_items').fetchone()[0] == 1
    finally:
        db.close()


def test_migration_is_re_runnable_and_preserves_existing_evidence(store):
    db = store._db
    insert_pending(db, 'del_rerun')
    db.execute("INSERT INTO bot_deletion_items (request_id, store_name, row_id, erased_at) "
               "VALUES ('del_rerun', 'messages', 'message_a', 'now')")
    db.commit()
    migrate_deletion_schema(db)
    migrate_deletion_schema(db)
    assert db.execute('SELECT COUNT(*) FROM bot_deletions').fetchone()[0] == 1
    assert db.execute('SELECT COUNT(*) FROM bot_deletion_items').fetchone()[0] == 1
    assert GUARD_TRIGGERS <= schema_names(db, 'trigger')
    refuse(db, "UPDATE bot_deletions SET status = 'superseded' WHERE id = 'del_rerun'", match='immutable')
    refuse(db, 'DELETE FROM bot_deletions', match='retained')

def _install_share_world(db):
    """A v82-shaped share world: old-shape share table plus the rows it references."""
    db.execute('CREATE TABLE conversations (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL)')
    db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, conversation_id TEXT)')
    db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, run_id TEXT NOT NULL)')
    db.execute('CREATE TABLE conversation_runs (conversation_id TEXT NOT NULL, run_id TEXT NOT NULL, '
               'attached_at TEXT NOT NULL)')
    db.execute('CREATE TABLE resource_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, previous_id INTEGER NOT NULL, '
               'resource TEXT NOT NULL, resource_id TEXT NOT NULL, operation TEXT NOT NULL, ts TEXT NOT NULL, '
               'context TEXT NOT NULL)')
    db.execute('CREATE TABLE resource_outbox_meta (singleton INTEGER PRIMARY KEY, epoch TEXT NOT NULL, '
               'tail_id INTEGER NOT NULL)')
    db.execute("INSERT INTO resource_outbox_meta VALUES (1, '0', 0)")
    db.execute("""CREATE TABLE conversation_artifact_shares (
        id TEXT PRIMARY KEY,
        target_conversation_id TEXT NOT NULL REFERENCES conversations(id),
        source_run_id TEXT NOT NULL REFERENCES runs(id),
        source_event_id INTEGER NOT NULL REFERENCES events(id),
        artifact_kind TEXT NOT NULL CHECK(artifact_kind IN ('tool_output','workspace_file')),
        created_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        revoked_at TEXT,
        revoked_by TEXT NOT NULL DEFAULT '')""")
    for name, target in (('conv_a', 'bot_a'), ('conv_b', 'bot_b'), ('conv_src', 'bot_a')):
        db.execute('INSERT INTO conversations VALUES (?, ?)', (name, target))
    db.execute("INSERT INTO conversation_runs VALUES ('conv_src', 'run_a', 'now')")
    db.execute("INSERT INTO runs VALUES ('run_a', 'conv_src')")
    db.execute("INSERT INTO events VALUES (1, 'run_a')")
    db.commit()


def test_artifact_share_rebuild_preserves_history_and_relinks_foreign_keys():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        _install_share_world(db)
        db.execute("INSERT INTO conversation_artifact_shares VALUES "
                   "('share_a', 'conv_a', 'run_a', 1, 'tool_output', 'now', 'operator', NULL, '')")
        db.execute("INSERT INTO conversation_artifact_shares VALUES "
                   "('share_b', 'conv_b', 'run_a', 1, 'tool_output', 'now', 'operator', NULL, '')")
        migrate_deletion_schema(db)
        actions = {row['table']: row['on_delete']
                   for row in db.execute('PRAGMA foreign_key_list(conversation_artifact_shares)')}
        assert actions == {'conversations': 'CASCADE', 'runs': 'SET NULL', 'events': 'SET NULL'}
        assert {'conversation_artifact_shares_active', 'conversation_artifact_shares_target'} <= schema_names(
            db, 'index')
        assert {'conversation_artifact_shares_immutable', 'conversation_artifact_shares_no_delete',
                'conversation_artifact_shares_source_guard'} <= schema_names(db, 'trigger')
        assert [row['id'] for row in db.execute('SELECT id FROM conversation_artifact_shares ORDER BY id')] == [
            'share_a', 'share_b']
        refuse(db, "DELETE FROM conversation_artifact_shares WHERE id = 'share_a'", match='revoke')
        db.execute("DELETE FROM conversations WHERE id = 'conv_a'")
        assert [row['id'] for row in db.execute('SELECT id FROM conversation_artifact_shares')] == ['share_b']
        db.execute("UPDATE conversation_artifact_shares SET revoked_at = 'now', revoked_by = 'operator' "
                   "WHERE id = 'share_b'")
        db.execute("DELETE FROM runs WHERE id = 'run_a'")
        db.execute('DELETE FROM events WHERE id = 1')
        share = dict(db.execute('SELECT * FROM conversation_artifact_shares').fetchone())
        assert share['source_run_id'] is None and share['source_event_id'] is None
        assert share['revoked_at'] == 'now' and share['target_conversation_id'] == 'conv_b'
        refuse(db, "UPDATE conversation_artifact_shares SET revoked_by = 'again' WHERE id = 'share_b'",
               match='immutable')
        refuse(db, "DELETE FROM conversation_artifact_shares WHERE id = 'share_b'", match='revoke')
        migrate_deletion_schema(db)
        assert db.execute('SELECT COUNT(*) FROM conversation_artifact_shares').fetchone()[0] == 1
    finally:
        db.close()


def _install_receipt_world(db):
    """Minimal live-shape tables for the receipt redaction allowances."""
    db.execute("""CREATE TABLE tool_actions (
        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, tool TEXT NOT NULL, idem_key TEXT NOT NULL,
        effect TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
        started_at TEXT NOT NULL, finished_at TEXT, result_digest TEXT NOT NULL DEFAULT '',
        intent_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(intent_json)),
        intent_hash TEXT NOT NULL DEFAULT '', effect_key TEXT NOT NULL DEFAULT '',
        legacy INTEGER NOT NULL DEFAULT 1 CHECK(legacy IN (0, 1)),
        workflow_identity TEXT NOT NULL DEFAULT '', workflow_fingerprint TEXT NOT NULL DEFAULT '',
        result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json)))""")
    db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, sealed INTEGER NOT NULL DEFAULT 0)')
    db.execute("""CREATE TABLE action_reconciliations (
        action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, intent_hash TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK(outcome IN ('confirmed_done', 'confirmed_failed', 'not_applied')),
        evidence TEXT NOT NULL CHECK(length(evidence) BETWEEN 1 AND 4000),
        recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE memory_fact_decisions (
        fact_id TEXT NOT NULL, action TEXT NOT NULL CHECK(action IN ('approve','archive','share')),
        request_hash TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
        result_json TEXT NOT NULL CHECK(json_valid(result_json)), PRIMARY KEY(fact_id, action))""")
    for table in ('tool_actions', 'action_reconciliations'):
        db.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
                   "BEGIN SELECT RAISE(ABORT, 'action history requires an explicit scoped deletion command'); END")
    db.execute("CREATE TRIGGER memory_decisions_no_delete BEFORE DELETE ON memory_fact_decisions "
               "BEGIN SELECT RAISE(ABORT, 'fact review is immutable'); END")
    db.commit()


def test_redaction_allowances_accept_only_deletion_shapes():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    try:
        _install_receipt_world(db)
        migrate_deletion_schema(db)
        assert 'bot_deletion_scope' in schema_names(db, 'table')
        db.execute("INSERT INTO runs VALUES ('run_a', 1)")
        db.execute("INSERT INTO tool_actions (id, run_id, tool, idem_key, effect, summary, status, started_at, "
                   "finished_at, result_digest, intent_json, intent_hash, result_json) VALUES "
                   "('act_a', 'run_a', 'shell', 'idem', 'write', 'ran a private command', 'done', 'now', 'now', "
                   "'digest', '{\"schema\": 1, \"arguments\": {\"cmd\": \"secret\"}}', 'hash', "
                   "'{\"stdout\": \"secret\"}')")
        refuse(db, "UPDATE tool_actions SET summary = '', intent_json = '{}' WHERE id = 'act_a'",
               match='immutable')
        db.execute("INSERT INTO bot_deletion_scope VALUES (1, 'req_a', 'now')")
        db.execute("UPDATE tool_actions SET summary = '', intent_json = '{}', result_json = '{}' "
                   "WHERE id = 'act_a'")
        row = dict(db.execute('SELECT * FROM tool_actions').fetchone())
        assert (row['summary'], row['intent_json'], row['result_json']) == ('', '{}', '{}')
        refuse(db, "UPDATE tool_actions SET summary = 'exfiltrated' WHERE id = 'act_a'", match='immutable')
        refuse(db, "UPDATE tool_actions SET intent_json = '{\"arguments\": {\"cmd\": \"new\"}}' "
                   "WHERE id = 'act_a'", match='immutable')
        refuse(db, "UPDATE tool_actions SET result_json = '{\"stdout\": \"new\"}' WHERE id = 'act_a'",
               match='sealed')
        refuse(db, "UPDATE tool_actions SET run_id = 'run_b' WHERE id = 'act_a'", match='immutable')
        refuse(db, 'DELETE FROM tool_actions', match='explicit scoped deletion')
        db.execute("INSERT INTO action_reconciliations VALUES "
                   "('act_a', 'run_a', 'hash', 'confirmed_done', 'opaque evidence', 'operator', 'now')")
        db.execute("UPDATE action_reconciliations SET evidence = '[deleted]' WHERE action_id = 'act_a'")
        refuse(db, "UPDATE action_reconciliations SET evidence = 'changed' WHERE action_id = 'act_a'",
               match='immutable')
        refuse(db, "UPDATE action_reconciliations SET run_id = 'run_b' WHERE action_id = 'act_a'",
               match='immutable')
        refuse(db, 'DELETE FROM action_reconciliations', match='explicit scoped deletion')
        db.execute("INSERT INTO memory_fact_decisions VALUES "
                   "('fact_a', 'approve', 'hash', 'operator', 'a private note', 'now', '{}')")
        db.execute("UPDATE memory_fact_decisions SET note = '' WHERE fact_id = 'fact_a'")
        assert db.execute('SELECT note FROM memory_fact_decisions').fetchone()[0] == ''
        refuse(db, "UPDATE memory_fact_decisions SET note = 'changed' WHERE fact_id = 'fact_a'", match='immutable')
        refuse(db, "UPDATE memory_fact_decisions SET actor = 'intruder' WHERE fact_id = 'fact_a'",
               match='immutable')
        refuse(db, 'DELETE FROM memory_fact_decisions', match='immutable')
    finally:
        db.close()

def test_task_state_revision_guard_allows_only_parent_cascade():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        db.execute('CREATE TABLE conversations (id TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE conversation_task_state_revisions (conversation_id TEXT NOT NULL '
                   'REFERENCES conversations(id) ON DELETE CASCADE, revision INTEGER NOT NULL, '
                   'PRIMARY KEY(conversation_id, revision))')
        db.execute("CREATE TRIGGER conversation_task_state_revisions_no_delete BEFORE DELETE ON "
                   "conversation_task_state_revisions BEGIN SELECT RAISE(ABORT, 'task-state revisions are retained'); END")
        db.execute("INSERT INTO conversations VALUES ('conv_a')")
        db.execute("INSERT INTO conversation_task_state_revisions VALUES ('conv_a', 1)")
        migrate_deletion_schema(db)
        refuse(db, "DELETE FROM conversation_task_state_revisions WHERE conversation_id = 'conv_a'",
               match='retained')
        db.execute("DELETE FROM conversations WHERE id = 'conv_a'")
        assert db.execute('SELECT COUNT(*) FROM conversation_task_state_revisions').fetchone()[0] == 0
    finally:
        db.close()
