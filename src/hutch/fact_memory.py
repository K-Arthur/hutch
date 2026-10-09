"""Versioned reference facts. Human review is not tool permission or proof of truth.

Model proposals inherit the owning run's conversation; only an explicit human
share creates a bot-wide fact. Historic unscoped rows remain reviewable as legacy.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid

from .lifecycle import LeaseLost, TERMINAL
from .models import RunStatus, iso, utcnow

MAX_KEY = 120
MAX_VALUE = 2000
MAX_RESULTS = 100
MAX_CONTEXT = 6000
CONTENT_FIELDS = ('bot_id', 'scope_kind', 'scope_id', 'key', 'value', 'revision', 'run_id', 'source')


class FactConflict(ValueError):
    pass


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def migrate(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE memory_facts (
        id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, scope_kind TEXT NOT NULL
        CHECK(scope_kind IN ('conversation','run','bot','legacy')), scope_id TEXT NOT NULL,
        key TEXT NOT NULL, value TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0),
        content_hash TEXT NOT NULL, run_id TEXT NOT NULL, source TEXT NOT NULL, updated_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('proposed','approved','archived')),
        UNIQUE(bot_id, scope_kind, scope_id, key, revision))""")
    db.execute('CREATE INDEX memory_facts_scope ON memory_facts(bot_id, scope_kind, scope_id, key, revision)')
    db.execute("""CREATE TABLE memory_fact_decisions (
        fact_id TEXT NOT NULL, action TEXT NOT NULL CHECK(action IN ('approve','archive','share')),
        request_hash TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
        result_json TEXT NOT NULL CHECK(json_valid(result_json)), PRIMARY KEY(fact_id, action))""")
    db.execute("""CREATE TRIGGER memory_facts_immutable BEFORE UPDATE ON memory_facts
        WHEN NEW.id IS NOT OLD.id OR NEW.bot_id IS NOT OLD.bot_id OR NEW.scope_kind IS NOT OLD.scope_kind
        OR NEW.scope_id IS NOT OLD.scope_id OR NEW.key IS NOT OLD.key OR NEW.value IS NOT OLD.value
        OR NEW.revision IS NOT OLD.revision OR NEW.content_hash IS NOT OLD.content_hash
        OR NEW.run_id IS NOT OLD.run_id OR NEW.source IS NOT OLD.source OR NEW.updated_at IS NOT OLD.updated_at
        BEGIN SELECT RAISE(ABORT, 'fact content is immutable; propose a new revision'); END""")
    db.execute("CREATE TRIGGER memory_facts_no_delete BEFORE DELETE ON memory_facts "
               "BEGIN SELECT RAISE(ABORT, 'archive facts; scoped permanent deletion is not implemented'); END")
    for operation in ('UPDATE', 'DELETE'):
        db.execute(f"CREATE TRIGGER memory_decisions_no_{operation.lower()} BEFORE {operation} ON memory_fact_decisions "
                   "BEGIN SELECT RAISE(ABORT, 'fact review is immutable'); END")
    db.execute('CREATE VIRTUAL TABLE memory_facts_fts USING fts5(key, value)')
    db.execute("""CREATE TRIGGER memory_facts_index AFTER INSERT ON memory_facts BEGIN
        INSERT INTO memory_facts_fts(rowid, key, value) VALUES (NEW.rowid, NEW.key, NEW.value); END""")
    # Preserve bytes/provenance; no inference that an old bot fact belongs to a
    # particular private conversation, or that source='user' means reviewed.
    cursor = db.execute('SELECT bot_id, key, value, run_id, source, updated_at FROM memory ORDER BY bot_id, key')
    for row in cursor:
        insert(db, row['bot_id'], 'legacy', row['bot_id'], row['key'], row['value'],
               row['run_id'], row['source'], updated_at=row['updated_at'])
    from .durable_changes import install_resources
    install_resources(db, (("memory_facts", "memory", "id", ("status",), ("bot_id", "scope_kind", "scope_id")),))


def insert(db, bot_id, scope_kind, scope_id, key, value, run_id='', source='user', *, updated_at=None):
    revision = db.execute('SELECT COALESCE(MAX(revision), 0) + 1 FROM memory_facts WHERE bot_id = ? '
                          'AND scope_kind = ? AND scope_id = ? AND key = ?',
                          (bot_id, scope_kind, scope_id, key)).fetchone()[0]
    content = dict(bot_id=bot_id, scope_kind=scope_kind, scope_id=scope_id, key=key, value=value,
                   revision=revision, run_id=run_id, source=source)
    fact_id = 'fact_' + uuid.uuid4().hex[:20]
    db.execute('INSERT INTO memory_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
               (fact_id, bot_id, scope_kind, scope_id, key, value, revision, digest(content),
                run_id, source, updated_at or iso(utcnow()), 'proposed'))
    return dict(db.execute('SELECT * FROM memory_facts WHERE id = ?', (fact_id,)).fetchone())


def propose(store, db, bot_id, key, value, *, run_id='', fence=None, conversation_id=None):
    if not isinstance(key, str) or not isinstance(value, str) or not key.strip() or not value.strip():
        raise ValueError('fact key and value must be nonempty text')
    if len(key) > MAX_KEY or len(value) > MAX_VALUE:
        raise ValueError('fact key/value exceed 120/2000 characters; shorten them explicitly')
    key.encode('utf-8'); value.encode('utf-8')
    bot = db.execute('SELECT doc FROM bots WHERE id = ?', (bot_id,)).fetchone()
    if bot is None:
        raise KeyError(bot_id)
    scope_kind, scope_id, source = 'bot', bot_id, 'user'
    if run_id:
        row = db.execute('SELECT * FROM runs WHERE id = ?', (run_id,)).fetchone()
        if fence is None:
            raise LeaseLost(run_id, 'fact writes require the expected execution fence')
        store._check_lease(row, run_id, fence)
        if (row['bot_id'] != bot_id or row['sealed'] or RunStatus(row['status']) in TERMINAL or row['cancel_requested']
                or (fence > 0 and row['status'] != RunStatus.running.value)):
            raise LeaseLost(run_id, 'this run cannot propose a fact')
        if not json.loads(bot['doc']).get('memory_enabled', True):
            raise ValueError('fact memory is disabled for this bot')
        scope_kind = 'conversation' if row['conversation_id'] else 'run'
        scope_id = row['conversation_id'] or run_id
        source = 'bot'
    elif conversation_id:
        check_conversation(db, bot_id, conversation_id)
        scope_kind, scope_id = 'conversation', conversation_id
    return insert(db, bot_id, scope_kind, scope_id, key, value, run_id, source)


def check_conversation(db, bot_id, conversation_id):
    row = db.execute('SELECT bot_id FROM conversations WHERE id = ?', (conversation_id,)).fetchone()
    if row is None or row['bot_id'] != bot_id:
        raise KeyError(conversation_id)


CURRENT = ('NOT EXISTS (SELECT 1 FROM memory_facts newer WHERE newer.bot_id = f.bot_id '
           'AND newer.scope_kind = f.scope_kind AND newer.scope_id = f.scope_id '
           'AND newer.key = f.key AND newer.revision > f.revision)')


def page(db, bot_id, *, conversation_id=None, run_id=None, approved_only=False, admin=False,
         query='', limit=50, offset=0, include_archived=False):
    if len(query) > 256:
        raise ValueError('fact search is limited to 256 characters')
    clauses, args = ['f.bot_id = ?', CURRENT], [bot_id]
    if not include_archived:
        clauses.append("f.status != 'archived'")
    if not admin:
        scopes = ["(f.scope_kind = 'bot' AND f.scope_id = ?)"]
        args.append(bot_id)
        if conversation_id:
            check_conversation(db, bot_id, conversation_id)
            scopes.append("(f.scope_kind = 'conversation' AND f.scope_id = ?)")
            args.append(conversation_id)
        elif run_id:
            scopes.append("(f.scope_kind = 'run' AND f.scope_id = ?)")
            args.append(run_id)
        clauses.append('(' + ' OR '.join(scopes) + ')')
    if approved_only:
        clauses.append("f.status = 'approved'")
    join, order = '', 'f.updated_at DESC, f.id'
    if query.strip():
        tokens = re.findall(r'\w+', query, flags=re.UNICODE)[:10]
        if not tokens:
            return []
        # User search is literal AND terms, never arbitrary FTS/SQL syntax.
        args.append(' AND '.join('"' + term.replace('"', '""') + '"' for term in tokens))
        join = ' JOIN memory_facts_fts ON memory_facts_fts.rowid = f.rowid '
        clauses.append('memory_facts_fts MATCH ?')
        order = 'memory_facts_fts.rank, ' + order
    rows = db.execute('SELECT f.id, f.bot_id, f.scope_kind, f.scope_id, substr(f.key,1,120) AS key, '
                      'substr(f.value,1,2000) AS value, f.revision, f.content_hash, f.run_id, f.source, f.updated_at, f.status, '
                      '(length(f.key)>120 OR length(f.value)>2000) AS truncated, '
                      "COALESCE((SELECT title FROM conversations WHERE id=f.scope_id AND bot_id=f.bot_id), '') AS conversation_title "
                      'FROM memory_facts f ' + join +
                      ' WHERE ' + ' AND '.join(clauses) + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?',
                      (*args, max(1, min(MAX_RESULTS, limit)), max(0, offset))).fetchall()
    return [dict(row) for row in rows]


def incoming_page(db, target_bot_id, *, query='', limit=20):
    """Return active, provenance-labelled snapshots explicitly shared with this Bot."""
    if len(query) > 256:
        raise ValueError('fact search is limited to 256 characters')
    clauses = [
        's.target_bot_id = ?', 's.revoked_at IS NULL', "f.status = 'approved'", CURRENT,
        'f.id = s.source_fact_id', 'f.bot_id = s.source_bot_id',
        'f.scope_kind = s.source_scope_kind', 'f.scope_id = s.source_scope_id',
        'f.key = s.fact_key', 'f.value = s.fact_value', 'f.revision = s.fact_revision',
        'f.content_hash = s.content_hash', "f.scope_kind IN ('bot','conversation')",
        "COALESCE(json_extract(source_bot.doc, '$.memory_enabled'), 1) = 1",
        "COALESCE(json_extract(target_bot.doc, '$.memory_enabled'), 1) = 1",
    ]
    args = [target_bot_id]
    join = ''
    if query.strip():
        tokens = re.findall(r'\w+', query, flags=re.UNICODE)[:10]
        if not tokens:
            return []
        args.append(' AND '.join('"' + term.replace('"', '""') + '"' for term in tokens))
        join = ' JOIN memory_facts_fts ON memory_facts_fts.rowid = f.rowid '
        clauses.append('memory_facts_fts MATCH ?')
    rows = db.execute(
        'SELECT s.id AS id, s.id AS share_id, s.source_fact_id AS source_fact_id, '
        's.source_bot_id AS bot_id, s.source_display_name AS shared_from, '
        "'shared' AS scope_kind, s.source_scope_id AS scope_id, s.fact_key AS key, "
        's.fact_value AS value, s.fact_revision AS revision, s.content_hash AS content_hash, '
        "f.run_id AS run_id, 'shared' AS source, s.created_at AS updated_at, 'approved' AS status, "
        "0 AS truncated, COALESCE((SELECT title FROM conversations WHERE id=s.source_scope_id "
        'AND bot_id=s.source_bot_id), \'\') AS conversation_title '
        'FROM memory_fact_shares s JOIN memory_facts f ON f.id = s.source_fact_id '
        'JOIN bots source_bot ON source_bot.id = s.source_bot_id '
        'JOIN bots target_bot ON target_bot.id = s.target_bot_id ' + join +
        ' WHERE ' + ' AND '.join(clauses) + ' ORDER BY s.created_at DESC, s.id LIMIT ?',
        (*args, max(1, min(MAX_RESULTS, limit)))).fetchall()
    return [dict(row) for row in rows]


def history(db, bot_id, fact_id, *, limit=50, offset=0):
    fact = db.execute('SELECT scope_kind, scope_id, key FROM memory_facts WHERE id = ? AND bot_id = ?', (fact_id, bot_id)).fetchone()
    if fact is None:
        raise KeyError(fact_id)
    rows = db.execute('SELECT id, bot_id, scope_kind, scope_id, substr(key,1,120) AS key, substr(value,1,2000) AS value, '
                      'revision, content_hash, run_id, source, updated_at, status, '
                      '(length(key)>120 OR length(value)>2000) AS truncated FROM memory_facts '
                      'WHERE bot_id = ? AND scope_kind = ? AND scope_id = ? AND key = ? ORDER BY revision DESC LIMIT ? OFFSET ?',
                      (bot_id, fact['scope_kind'], fact['scope_id'], fact['key'], min(100, max(1, limit)), max(0, offset))).fetchall()
    versions = [dict(row) for row in rows]
    decisions = []
    for row in rows:
        reviews = db.execute('SELECT fact_id, action, actor, note, created_at, result_json FROM memory_fact_decisions '
                             "WHERE fact_id = ? OR json_extract(result_json,'$.result_id') = ? ORDER BY created_at, action",
                             (row['id'], row['id'])).fetchall()
        for review in reviews:
            decisions.append({key: review[key] for key in ('fact_id','action','actor','note','created_at')} |
                             {'result_id': json.loads(review['result_json'])['result_id']})
    return {'facts': versions, 'reviews': decisions, 'limit': limit, 'offset': offset,
            'next_offset': offset + limit if len(rows) == limit else None}


def review(db, bot_id, fact_id, *, content_hash, action, actor, note=''):
    if action not in {'approve', 'archive', 'share'} or len(note) > 1000 or not actor or len(actor) > 120:
        raise ValueError('invalid fact review')
    note.encode('utf-8')
    request_hash = digest(dict(content_hash=content_hash, action=action, actor=actor, note=note))
    existing = db.execute('SELECT d.request_hash, d.result_json FROM memory_fact_decisions d '
                          'JOIN memory_facts f ON f.id = d.fact_id WHERE d.fact_id = ? AND d.action = ? AND f.bot_id = ?',
                          (fact_id, action, bot_id)).fetchone()
    if existing:
        if existing['request_hash'] != request_hash:
            raise FactConflict('this fact already has a different review for that action')
        return json.loads(existing['result_json'])
    fact = db.execute('SELECT * FROM memory_facts f WHERE f.id = ? AND f.bot_id = ? AND ' + CURRENT,
                      (fact_id, bot_id)).fetchone()
    if fact is None:
        raise FactConflict('this fact was replaced or is unavailable; refresh before reviewing')
    if fact['content_hash'] != content_hash:
        raise FactConflict('fact arguments changed; review the current revision')
    if digest({key: fact[key] for key in CONTENT_FIELDS}) != content_hash:
        raise FactConflict('fact content failed its integrity check; preserve it for inspection')
    if fact['status'] == 'archived':
        raise FactConflict('this fact is archived')
    if action != 'archive' and (len(fact['key']) > MAX_KEY or len(fact['value']) > MAX_VALUE):
        raise FactConflict('legacy fact is too large to review; propose an explicit shorter revision')
    result_id = fact_id
    if action == 'approve':
        if fact['scope_kind'] == 'legacy':
            raise FactConflict('legacy facts have no private chat scope; explicitly share or archive them')
        db.execute("UPDATE memory_facts SET status = 'approved' WHERE id = ?", (fact_id,))
    elif action == 'archive':
        db.execute("UPDATE memory_facts SET status = 'archived' WHERE id = ?", (fact_id,))
    else:
        if fact['scope_kind'] == 'bot':
            raise FactConflict('this fact already has bot-wide scope; review it directly')
        other = db.execute('SELECT * FROM memory_facts f WHERE f.bot_id = ? AND f.scope_kind = ? '
                           'AND f.scope_id = ? AND f.key = ? AND ' + CURRENT,
                           (bot_id, 'bot', bot_id, fact['key'])).fetchone()
        if other and other['status'] != 'archived':
            raise FactConflict('a shared fact with this key already exists; review or archive it first')
        shared = insert(db, bot_id, 'bot', bot_id, fact['key'], fact['value'], fact['run_id'], 'user-shared')
        result_id = shared['id']
        db.execute("UPDATE memory_facts SET status = 'approved' WHERE id = ?", (result_id,))
        db.execute("UPDATE memory_facts SET status = 'archived' WHERE id = ?", (fact_id,))
    result = dict(fact_id=fact_id, result_id=result_id, action=action, content_hash=content_hash)
    db.execute('INSERT INTO memory_fact_decisions VALUES (?, ?, ?, ?, ?, ?, ?)',
               (fact_id, action, request_hash, actor, note, iso(utcnow()), json.dumps(result, sort_keys=True)))
    return result


def validate(db):
    for row in db.execute('SELECT * FROM memory_facts'):
        if digest({key: row[key] for key in CONTENT_FIELDS}) != row['content_hash']:
            raise ValueError('snapshot fact content hash is invalid')
    for row in db.execute('SELECT s.*, f.bot_id AS fact_bot_id, f.scope_kind AS fact_scope_kind, '
                          'f.scope_id AS fact_scope_id, f.key AS source_key, f.value AS source_value, '
                          'f.revision AS source_revision, f.content_hash AS source_hash, f.run_id AS source_run_id, '
                          'f.source AS fact_source FROM memory_fact_shares s '
                          'JOIN memory_facts f ON f.id = s.source_fact_id'):
        content = dict(bot_id=row['source_bot_id'], scope_kind=row['source_scope_kind'],
                       scope_id=row['source_scope_id'], key=row['fact_key'], value=row['fact_value'],
                       revision=row['fact_revision'], run_id=row['source_run_id'], source=row['fact_source'])
        if (row['fact_bot_id'] != row['source_bot_id'] or row['fact_scope_kind'] != row['source_scope_kind']
                or row['fact_scope_id'] != row['source_scope_id'] or row['source_key'] != row['fact_key']
                or row['source_value'] != row['fact_value'] or row['source_revision'] != row['fact_revision']
                or row['source_hash'] != row['content_hash'] or digest(content) != row['content_hash']):
            raise ValueError('snapshot shared-fact content or provenance is invalid')
