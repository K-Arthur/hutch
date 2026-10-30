"""Shared helpers moved out of bot_deletion_seed.py to keep it under the file-size cap."""
from __future__ import annotations

import json
import sqlite3
from hutch import bot_deletion


SENTINEL = 'PRIVATEBOTDELETIONSENTINEL'

def all_tables(db: sqlite3.Connection) -> list[str]:
    """Every ordinary table, for content-leak scans."""
    return [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]


def scan_for_sentinel(db: sqlite3.Connection, sentinel: str) -> list[str]:
    """Every table and column that still stores one erased sentinel."""
    leaks = []
    for table in all_tables(db):
        columns = [row[1] for row in db.execute('PRAGMA table_info(' + table + ')')]
        if not columns:
            continue
        for row in db.execute('SELECT * FROM ' + table):
            blob = json.dumps({column: row[column] for column in columns}, default=str)
            if sentinel in blob:
                leaks.append(table)
                break
    return leaks


def scoped_rows(db: sqlite3.Connection, needles: set[str]) -> dict[str, list[str]]:
    """Canonical rows that mention any opaque id of the untouched Bot, per table."""
    found: dict[str, list[str]] = {}
    for table in all_tables(db):
        columns = [row[1] for row in db.execute('PRAGMA table_info(' + table + ')')]
        if not columns:
            continue
        rows = []
        for row in db.execute('SELECT * FROM ' + table):
            record = {column: row[column] for column in columns}
            if any(str(value) in needles for value in record.values() if isinstance(value, str)):
                rows.append(json.dumps(record, sort_keys=True, default=str))
        found[table] = sorted(rows)
    return found


def other_needles(seed: dict) -> set[str]:
    """Opaque ids and the sentinel that belong to the untouched Bot."""
    return {seed['bot'], seed['conversation'], seed['message'], seed['run'], seed['job'],
            seed['document'], seed['workspace_task'], seed['investigation'], seed['action'],
            seed['syn_manifest'], seed['workflow'], seed['handoff'], seed['name'],
            seed['tag'], seed['fact']}


def _assert_erased_shape(store, first, second, preview, result, untouched_before):
    """Assert the erased Bot leaves no content, tombstones receipts and keeps the second Bot."""
    db = store._db
    assert store.get_bot(first['bot']) is None
    assert store.get_bot(second['bot']) is not None
    # Cross-Bot shares are intentionally tombstoned/revoked content-free (the other Bot
    # sees a purged record, never the value), and the outbox records that change.
    after_scoped = scoped_rows(db, other_needles(second))
    shared = {'memory_fact_shares', 'conversation_artifact_shares', 'resource_outbox',
              'bot_deletions', 'idempotency_keys'}
    for table, rows in untouched_before.items():
        if table not in shared:
            assert after_scoped.get(table) == rows, table
    assert all('purged' in row or '"revoked_at": "2' in row or 'redacted' in row
               for row in after_scoped['memory_fact_shares'])
    assert scan_for_sentinel(db, SENTINEL) == []
    assert store.get_bot(second['bot']) is not None
    fts_rows = db.execute('SELECT content FROM conversation_fts').fetchall()
    assert all(SENTINEL not in str(row[0]) for row in fts_rows)
    fts_facts = db.execute('SELECT key, value FROM memory_facts_fts').fetchall()
    assert all(SENTINEL not in str(row[0]) + str(row[1]) for row in fts_facts)
    assert db.execute('SELECT COUNT(*) FROM conversation_questions').fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM conversations WHERE bot_id = ?", (first['bot'],)).fetchone()[0] == 0
    tombstone = db.execute('SELECT key, value, purged_at, purge_id, status FROM memory_facts '
                           'WHERE purge_id != \'\'').fetchone()
    assert tombstone['key'].startswith('purged:') and tombstone['value'] == ''
    assert tombstone['status'] == 'archived' and tombstone['purged_at'] and tombstone['purge_id']
    share = db.execute('SELECT fact_value, purged_at FROM memory_fact_shares '
                       'WHERE source_bot_id = ?', (first['bot'],)).fetchone()
    assert share['fact_value'] == 'purged' and share['purged_at']
    receipt = db.execute("SELECT response_json FROM idempotency_keys WHERE scope = ?",
                         ('api:v1:conversations:' + first['bot'],)).fetchone()
    assert receipt['response_json'] == '{"redacted": "[deleted]"}'
    assert db.execute("SELECT summary, intent_json, result_json FROM tool_actions WHERE id = ?",
                      (first['action'],)).fetchone()['summary'] == ''
    reconciliation = db.execute('SELECT evidence FROM action_reconciliations WHERE action_id = ?',
                                (first['action'],)).fetchone()
    assert reconciliation['evidence'] == '[deleted]'
    assert db.execute('SELECT note FROM memory_fact_decisions WHERE fact_id = ?',
                      (first['fact'],)).fetchone()['note'] == ''
    usage = db.execute('SELECT COUNT(*) FROM usage WHERE bot_id = ?', (first['bot'],)).fetchone()[0]
    assert usage == 1, 'spending history is retained content-free'
    assert db.execute('SELECT COUNT(*) FROM kv').fetchone()[0] == 4
    assert db.execute('SELECT COUNT(*) FROM doc_index_chunks').fetchone()[0] == 2
    assert db.execute('SELECT COUNT(*) FROM doc_index_fts').fetchone()[0] == 2
    evidence = db.execute('SELECT COUNT(*) FROM bot_deletion_items WHERE request_id = ?',
                          (preview['request_id'],)).fetchone()[0]
    assert evidence == preview['counts']['total']
    request = bot_deletion.request_record(store, preview['request_id'])
    assert request['status'] == 'confirmed' and request['cleanup_state'] == 'cleaned'
    assert request['result'] == result and not request['counts'] != preview['counts']
    rendered = json.dumps([request, bot_deletion.requests(store, first['bot'])])
    assert 'token' not in rendered and SENTINEL not in rendered
