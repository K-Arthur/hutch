"""Governed permanent deletion for saved reference facts.

Content is erased while identity, scope, revision and review hashes remain so a
reviewer can prove the deletion. Transcripts, files and backups are explicitly
out of scope; the confirmation preview names them instead of implying more.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from datetime import timedelta

from .fact_memory import FactConflict, MAX_KEY, digest
from .models import iso, utcnow


#: A confirmation window long enough to read the consequences, short enough to stale.
PURGE_TOKEN_TTL_SECONDS = 600
MAX_PURGE_ITEMS = 20_000
PURGE_REMAINING = (
    'conversation messages, assistant replies and run transcripts that already contain the text',
    'run context snapshots and event histories',
    'files, documents and workspace artefacts',
    'database backups taken before this purge, filesystem or journal copies outside SQLite,'
    'and provider-side copies of earlier prompts',
    'credential-free review and purge audit rows (hashes, actors, timestamps) that prove the erasure',
)


def _purge_scope(alias: str, key, all_facts: bool) -> tuple[str, tuple]:
    """One exact Bot-wide or key-wide predicate; never caller-provided SQL."""
    if all_facts:
        return f"{alias}.bot_id = ?", ()
    if not isinstance(key, str) or not key.strip() or len(key) > MAX_KEY:
        raise ValueError('purge requires one exact non-empty fact key of at most 120 characters')
    key.encode('utf-8')
    return f"{alias}.bot_id = ? AND {alias}.key = ?", (key,)


def purge_counts(db, bot_id, *, key=None, all=False) -> dict:
    """Count every saved copy a purge would erase, without returning fact text."""
    facts_sql, facts_args = _purge_scope('f', key, all)
    shares_sql = '' if all else ' AND {alias}.fact_key = ?'
    share_args = () if all else (key,)

    def one(sql: str, args: tuple = ()) -> int:
        """Count one bounded predicate without loading rows."""
        return int(db.execute(sql, (bot_id, *args)).fetchone()[0])

    counts = {
        'fact_revisions': one("SELECT COUNT(*) FROM memory_facts f WHERE " + facts_sql
                              + " AND f.purged_at = ''", facts_args),
        'legacy_rows': one("SELECT COUNT(*) FROM memory WHERE bot_id = ?"
                           + ('' if all else ' AND key = ?'), facts_args),
        'outgoing_shares': one("SELECT COUNT(*) FROM memory_fact_shares s WHERE s.purged_at = ''"
                               " AND s.source_bot_id = ?" + shares_sql.format(alias='s'), share_args),
        'incoming_shares': one("SELECT COUNT(*) FROM memory_fact_shares s WHERE s.purged_at = ''"
                               " AND s.target_bot_id = ?" + shares_sql.format(alias='s'), share_args),
        'task_snapshots': one("SELECT COUNT(*) FROM workspace_task_fact_shares t WHERE t.purged_at = ''"
                              " AND t.source_bot_id = ?"
                              + ('' if all else ' AND t.fact_key = ?'), share_args),
        'receipts_redacted': len(_receipt_rows(db, bot_id, key, all)),
    }
    counts['total'] = sum(counts.values())
    return counts


def _receipt_targets(bot_id: str) -> tuple:
    """API idempotency scopes whose stored replay result embeds fact text."""
    return (
        (f'api:v1:facts:propose:{bot_id}', '$.key', ('key', 'value')),
        (f'api:v1:fact-shares:create:{bot_id}', '$.fact_key', ('fact_key', 'fact_value')),
    )


def _receipt_rows(db, bot_id, key, all_facts) -> list:
    """Short-lived API receipts that may embed the purged text, with their content fields."""
    rows = []
    for scope, match, fields in _receipt_targets(bot_id):
        sql = 'SELECT scope, key, response_json FROM idempotency_keys WHERE scope = ?'
        args = (scope,)
        if not all_facts:
            sql += f" AND json_extract(response_json, '{match}') = ?"
            args = (scope, key)
        rows.extend((row, fields) for row in db.execute(sql, args).fetchall())
    return rows


def _redact_receipts(db, bot_id, key, all_facts) -> list:
    """Replace embedded fact text in API replay receipts; keep the receipt and its hash."""
    items = []
    for row, fields in _receipt_rows(db, bot_id, key, all_facts):
        original = hashlib.sha256(row['response_json'].encode('utf-8')).hexdigest()
        try:
            record = json.loads(row['response_json'])
        except ValueError:
            record = {}
        if not isinstance(record, dict):
            record = {}
        for field in fields:
            if field in record:
                record[field] = '[purged]'
        db.execute('UPDATE idempotency_keys SET response_json = ? WHERE scope = ? AND key = ?',
                   (json.dumps(record, sort_keys=True), row['scope'], row['key']))
        row_id = hashlib.sha256((row['scope'] + chr(0) + row['key']).encode()).hexdigest()[:32]
        items.append(('idempotency_keys', row_id, original))
    return items


def issue_purge_request(db, bot_id, *, key=None, all=False, actor='operator', note='') -> dict:
    """Return a single-use confirmation token for a bounded, explicit purge preview."""
    all = bool(all)
    if all == (key is not None):
        raise ValueError('choose exactly one purge scope: one key or all saved facts')
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 120:
        raise ValueError('purge requires a bounded actor identity')
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError('purge note is limited to 1,000 characters')
    counts = purge_counts(db, bot_id, key=key, all=all)
    if counts['total'] == 0:
        raise FactConflict('nothing saved matches this purge scope')
    if counts['total'] > MAX_PURGE_ITEMS:
        raise FactConflict(f'this scope would erase {counts["total"]:,} saved rows; purge one key at a time')
    scope_kind = 'all' if all else 'key'
    scope_key = '' if all else key
    now = iso(utcnow())
    expires = iso(utcnow() + timedelta(seconds=PURGE_TOKEN_TTL_SECONDS))
    db.execute("UPDATE memory_purge_requests SET status = 'expired' WHERE bot_id = ? "
               "AND status = 'pending' AND expires_at <= ?", (bot_id, now))
    db.execute("UPDATE memory_purge_requests SET status = 'superseded' WHERE bot_id = ? "
               "AND scope_kind = ? AND scope_key = ? AND status = 'pending'",
               (bot_id, scope_kind, scope_key))
    token = secrets.token_urlsafe(32)
    request_id = 'purge_' + uuid.uuid4().hex[:20]
    db.execute("INSERT INTO memory_purge_requests (id, bot_id, scope_kind, scope_key, actor, note, "
               "request_hash, token_hash, created_at, expires_at, status, counts_json) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
               (request_id, bot_id, scope_kind, scope_key, actor.strip(), note,
                digest({'bot_id': bot_id, 'scope_kind': scope_kind, 'scope_key': scope_key,
                        'actor': actor.strip(), 'counts': counts}),
                hashlib.sha256(token.encode()).hexdigest(), now, expires,
                json.dumps(counts, sort_keys=True)))
    return {'request_id': request_id, 'token': token, 'expires_at': expires,
            'scope_kind': scope_kind, 'scope_key': scope_key, 'counts': counts,
            'confirmation_hint': key if not all else 'the Bot address'}


def _erase_fact_rows(db, bot_id, key, all_facts, request_id, now):
    """Archive, then erase, each matching revision; keep a content-free tombstone row."""
    clause, args = _purge_scope('f', key, all_facts)
    rows = db.execute("SELECT f.id, f.bot_id, f.scope_kind, f.scope_id, f.key, f.revision, f.run_id, "
                      "f.source, f.content_hash FROM memory_facts f WHERE " + clause
                      + " AND f.purged_at = ''", (bot_id, *args)).fetchall()
    db.execute("UPDATE memory_facts AS f SET status = 'archived' WHERE " + clause
               + " AND f.status != 'archived'", (bot_id, *args))
    items = []
    for fact in rows:
        tombstone = 'purged:' + fact['id']
        content = dict(bot_id=fact['bot_id'], scope_kind=fact['scope_kind'],
                       scope_id=fact['scope_id'], key=tombstone, value='',
                       revision=fact['revision'], run_id=fact['run_id'], source=fact['source'])
        db.execute("UPDATE memory_facts SET key = ?, value = '', content_hash = ?, status = 'archived', "
                   "purged_at = ?, purge_id = ? WHERE id = ?",
                   (tombstone, digest(content), now, request_id, fact['id']))
        items.append(('memory_facts', fact['id'], fact['content_hash']))
    for start in range(0, len(rows), 500):
        chunk = [fact['id'] for fact in rows[start:start + 500]]
        marks = ','.join('?' for _ in chunk)
        db.execute("DELETE FROM memory_facts_fts WHERE rowid IN "
                   "(SELECT rowid FROM memory_facts WHERE id IN (" + marks + "))", chunk)
    return items


def _erase_share_rows(db, bot_id, key, all_facts, request_id, now):
    """Erase snapshot content in both directions; identities and audit rows remain."""
    key_sql = '' if all_facts else ' AND fact_key = ?'
    key_args = () if all_facts else (key,)
    outgoing, incoming = [], []
    for direction, sink in (('source_bot_id', outgoing), ('target_bot_id', incoming)):
        rows = db.execute("SELECT id, content_hash FROM memory_fact_shares "
                          "WHERE purged_at = '' AND " + direction + " = ?" + key_sql,
                          (bot_id, *key_args)).fetchall()
        for share in rows:
            db.execute("UPDATE memory_fact_shares SET fact_key = ?, fact_value = 'purged', content_hash = ?, "
                       "purged_at = ? WHERE id = ?",
                       ('purged:' + share['id'], digest({'purged': share['id']}), now, share['id']))
            sink.append(('memory_fact_shares', share['id'], share['content_hash']))
    return outgoing, incoming


def _erase_task_snapshots(db, bot_id, key, all_facts, request_id, now):
    """Erase copies this Bot contributed to reviewed specialist-task briefs."""
    key_sql = '' if all_facts else ' AND fact_key = ?'
    key_args = () if all_facts else (key,)
    rows = db.execute("SELECT id, content_hash FROM workspace_task_fact_shares "
                      "WHERE purged_at = '' AND source_bot_id = ?" + key_sql,
                      (bot_id, *key_args)).fetchall()
    for row in rows:
        db.execute("UPDATE workspace_task_fact_shares SET fact_key = '', fact_value = 'purged', "
                   "content_hash = ?, purged_at = ? WHERE id = ?",
                   (digest({'purged-task-share': int(row['id'])}), now, row['id']))
    return [('workspace_task_fact_shares', str(row['id']), row['content_hash']) for row in rows]


def _erase_legacy_rows(db, bot_id, key, all_facts, now):
    """Remove the pre-versioned ``memory`` copies the facts were migrated from."""
    clause = 'bot_id = ?' if all_facts else 'bot_id = ? AND key = ?'
    args = (bot_id,) if all_facts else (bot_id, key)
    rows = db.execute("SELECT rowid FROM memory WHERE " + clause, args).fetchall()
    db.execute("DELETE FROM memory WHERE " + clause, args)
    return [('memory', str(row['rowid']), '') for row in rows]


def confirm_purge(db, bot_id, request_id, *, token, confirmation, actor, bot_address) -> dict:
    """Erase a previewed scope in one transaction; the request row is the audit record."""
    if not isinstance(token, str) or not 16 <= len(token) <= 200:
        raise ValueError('purge token is invalid')
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 120:
        raise ValueError('purge requires a bounded actor identity')
    row = db.execute('SELECT * FROM memory_purge_requests WHERE id = ? AND bot_id = ?',
                     (request_id, bot_id)).fetchone()
    if row is None:
        raise KeyError(request_id)
    stored_result = json.loads(row['result_json'] or '{}')
    if row['status'] == 'confirmed':
        return stored_result
    if row['status'] != 'pending':
        raise FactConflict('this purge request is no longer pending; preview the purge again')
    now = iso(utcnow())
    if row['expires_at'] <= now:
        db.execute("UPDATE memory_purge_requests SET status = 'expired' WHERE id = ?", (request_id,))
        raise FactConflict('this purge confirmation window expired; preview the purge again')
    expected = row['scope_key'] if row['scope_kind'] == 'key' else bot_address
    if not isinstance(confirmation, str) or not hmac.compare_digest(confirmation.strip(), expected):
        raise FactConflict('confirmation text does not match; nothing was erased')
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if not hmac.compare_digest(token_hash, row['token_hash']):
        raise FactConflict('purge token is invalid; preview the purge again')
    all_facts = row['scope_kind'] == 'all'
    key = None if all_facts else row['scope_key']
    return _apply_purge(db, bot_id, request_id, key, all_facts, now)


def _apply_purge(db, bot_id, request_id, key, all_facts, now) -> dict:
    """Erase every saved copy and write content-free evidence; secure-delete is enabled around it."""
    previous_secure_delete = db.execute('PRAGMA secure_delete').fetchone()[0]
    db.execute('PRAGMA secure_delete = ON')
    try:
        outgoing, incoming = _erase_share_rows(db, bot_id, key, all_facts, request_id, now)
        items = _erase_fact_rows(db, bot_id, key, all_facts, request_id, now)
        items += outgoing + incoming
        items += _erase_task_snapshots(db, bot_id, key, all_facts, request_id, now)
        items += _erase_legacy_rows(db, bot_id, key, all_facts, now)
        items += _redact_receipts(db, bot_id, key, all_facts)
        db.executemany("INSERT INTO memory_purge_items (request_id, table_name, row_id, "
                       "original_content_hash, purged_at) VALUES (?, ?, ?, ?, ?)",
                       [(request_id, table, row_id, original, now)
                        for table, row_id, original in items])
        counts = {
            'fact_revisions': len([item for item in items if item[0] == 'memory_facts']),
            'legacy_rows': len([item for item in items if item[0] == 'memory']),
            'outgoing_shares': len(outgoing),
            'incoming_shares': len(incoming),
            'task_snapshots': len([item for item in items if item[0] == 'workspace_task_fact_shares']),
            'receipts_redacted': len([item for item in items if item[0] == 'idempotency_keys']),
        }
        counts['total'] = sum(counts.values())
        result = {'request_id': request_id, 'status': 'confirmed', 'purged_at': now,
                  'counts': counts, 'remaining': list(PURGE_REMAINING)}
        db.execute("UPDATE memory_purge_requests SET status = 'confirmed', confirmed_at = ?, "
                   "counts_json = ?, result_json = ?, token_hash = '' WHERE id = ?",
                   (now, json.dumps(counts, sort_keys=True), json.dumps(result, sort_keys=True), request_id))
        return result
    finally:
        db.execute(f'PRAGMA secure_delete = {int(previous_secure_delete)}')


def purge_request_page(db, bot_id, *, limit=20):
    """Recent purge previews and outcomes for one Bot, without tokens or fact text."""
    rows = db.execute("SELECT id, bot_id, scope_kind, scope_key, actor, note, created_at, expires_at, "
                      "confirmed_at, status, counts_json, result_json FROM memory_purge_requests "
                      "WHERE bot_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                      (bot_id, max(1, min(100, int(limit))))).fetchall()
    page = []
    for row in rows:
        record = dict(row)
        record['counts'] = json.loads(record.pop('counts_json') or '{}')
        record['result'] = json.loads(record.pop('result_json') or '{}')
        page.append(record)
    return page




# ------------------------------------------------ store-facing commands

def preview(store, bot_id, *, key=None, all=False, actor='operator', note='') -> dict:
    """Issue a one-time purge confirmation; the preview names what cannot be erased."""
    with store._tx() as db:
        result = issue_purge_request(db, bot_id, key=key, all=all, actor=actor, note=note)
    store.bus.notify('memory')
    result['remaining'] = list(PURGE_REMAINING)
    return result


def confirm(store, bot_id, request_id, *, token, confirmation, actor='operator',
            idem_key=None, request_hash=None) -> dict:
    """Apply one previewed purge; a retry with the same key returns the same result."""
    scope = f'api:v1:fact-purge:{bot_id}:{request_id}'
    with store._tx() as db:
        if idem_key:
            replay = store._idempotency_replay(db, scope, idem_key, request_hash)
            if replay is not None:
                return replay
        bot = db.execute('SELECT name FROM bots WHERE id = ?', (bot_id,)).fetchone()
        if bot is None:
            raise KeyError(bot_id)
        result = confirm_purge(db, bot_id, request_id, token=token, confirmation=confirmation,
                               actor=actor, bot_address=bot['name'])
        if idem_key:
            db.execute('INSERT INTO idempotency_keys VALUES (?, ?, ?, ?, ?)',
                       (scope, idem_key, request_hash, json.dumps(result, sort_keys=True), iso(utcnow())))
    store.bus.notify('memory')
    try:
        with store._lock:
            store._db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    except sqlite3.OperationalError:
        pass
    return result


def requests(store, bot_id, *, limit=20) -> list:
    """Recent purge previews and outcomes for one Bot; no tokens or fact text."""
    with store._lock:
        return purge_request_page(store._db, bot_id, limit=limit)
