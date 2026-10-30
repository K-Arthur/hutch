"""Whole-Bot deletion steps: selecting, counting, erasing and snapshotting rows."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from .bot_deletion_plan import REDACTED_MARKER, _BOT_CONVERSATIONS, _BOT_RUNS, _ERASE_STEPS, _Step, _canonical, _key_column, _managed_paths, _row_id_text, _safe_digest, _scope_ids, _sha256_text


def _step_items(db: sqlite3.Connection, step: _Step, bot_id: str) -> list[tuple[str, str, str]]:
    """Select the bounded, content-free evidence for one SQL step before it runs."""
    key = _key_column(db, step.store)
    select = key + (', ' + step.hash_sql if step.hash_sql else '')
    rows = db.execute(f'SELECT {select} FROM {step.store} WHERE {step.predicate}', {'bot': bot_id}).fetchall()
    items: list[tuple[str, str, str]] = []
    for row in rows:
        content_hash = ''
        if step.hash_sql:
            if step.hash_kind == 'content':
                content_hash = _sha256_text('' if row[1] is None else str(row[1]))
            else:
                content_hash = _safe_digest(row[1])
        items.append((step.store, _row_id_text(row[0]), content_hash))
    return items


def _insert_items(db: sqlite3.Connection, request_id: str, items: list[tuple[str, str, str]], now: str) -> None:
    """Write one content-free item row per erased or redacted row."""
    rows = [(request_id, store, row_id, content_hash if len(content_hash) == 64 else '', now)
            for store, row_id, content_hash in items]
    for start in range(0, len(rows), 500):
        db.executemany('INSERT INTO bot_deletion_items (request_id, store_name, row_id, '
                       'original_content_hash, erased_at) VALUES (?, ?, ?, ?, ?)', rows[start:start + 500])


def _execute_sql_step(db: sqlite3.Connection, step: _Step, bot_id: str, now: str) -> list[tuple[str, str, str]]:
    """Collect evidence, then delete or redact the matching rows."""
    items = _step_items(db, step, bot_id)
    if step.kind == 'delete':
        db.execute(f'DELETE FROM {step.store} WHERE {step.predicate}', {'bot': bot_id})
    elif step.kind == 'redact':
        db.execute(f'UPDATE {step.store} SET {step.set_sql} WHERE {step.predicate}', {'bot': bot_id})
    return items


def _revoke_shares(db: sqlite3.Connection, bot_id: str, now: str) -> list[tuple[str, str, str]]:
    """Revoke shares from this Bot into other chats; revoking the deleted chat's own shares is unnecessary."""
    predicate = ('revoked_at IS NULL AND source_run_id IN ' + _BOT_RUNS
                 + ' AND target_conversation_id NOT IN ' + _BOT_CONVERSATIONS)
    rows = db.execute('SELECT id FROM conversation_artifact_shares WHERE ' + predicate, {'bot': bot_id}).fetchall()
    db.execute("UPDATE conversation_artifact_shares SET revoked_at = :now, "
               "revoked_by = 'whole-bot deletion' WHERE " + predicate, {'bot': bot_id, 'now': now})
    return [('conversation_artifact_shares', _row_id_text(row[0]), '') for row in rows]


def _tombstone_facts(db: sqlite3.Connection, bot_id: str, now: str, request_id: str) -> list[tuple[str, str, str]]:
    """Keep content-free fact tombstones so review and purge evidence still resolves."""
    rows = db.execute("SELECT id, bot_id, scope_kind, scope_id, revision, run_id, source, content_hash "
                      "FROM memory_facts WHERE bot_id = ? AND purged_at = ''", (bot_id,)).fetchall()
    items = []
    for row in rows:
        content = dict(bot_id=row['bot_id'], scope_kind=row['scope_kind'], scope_id=row['scope_id'],
                       key='purged:' + row['id'], value='', revision=row['revision'],
                       run_id=row['run_id'], source=row['source'])
        db.execute("UPDATE memory_facts SET key = 'purged:' || id, value = '', content_hash = ?, "
                   "status = 'archived', purged_at = ?, purge_id = ? WHERE id = ?",
                   (_sha256_text(_canonical(content)), now, request_id, row['id']))
        items.append(('memory_facts', _row_id_text(row['id']), _safe_digest(row['content_hash'])))
    return items


def _tombstone_shares(db: sqlite3.Connection, bot_id: str, now: str) -> list[tuple[str, str, str]]:
    """Erase snapshot content in both directions while keeping revocation history."""
    rows = db.execute("SELECT id, content_hash FROM memory_fact_shares "
                      "WHERE purged_at = '' AND (source_bot_id = :bot OR target_bot_id = :bot)",
                      {'bot': bot_id}).fetchall()
    items = []
    for row in rows:
        db.execute("UPDATE memory_fact_shares SET fact_key = ?, fact_value = 'purged', content_hash = ?, "
                   'purged_at = ? WHERE id = ?',
                   ('purged:' + str(row['id']), _sha256_text(_canonical({'purged': row['id']})),
                    now, row['id']))
        items.append(('memory_fact_shares', _row_id_text(row['id']), _safe_digest(row['content_hash'])))
    return items


def _tombstone_task_shares(db: sqlite3.Connection, bot_id: str, now: str) -> list[tuple[str, str, str]]:
    """Erase copies this Bot contributed to reviewed specialist-task briefs."""
    rows = db.execute("SELECT id, content_hash FROM workspace_task_fact_shares "
                      "WHERE purged_at = '' AND source_bot_id = :bot", {'bot': bot_id}).fetchall()
    items = []
    for row in rows:
        db.execute("UPDATE workspace_task_fact_shares SET fact_key = '', fact_value = 'purged', "
                   'content_hash = ?, purged_at = ? WHERE id = ?',
                   (_sha256_text(_canonical({'purged-task-share': str(row['id'])})), now, row['id']))
        items.append(('workspace_task_fact_shares', _row_id_text(row['id']), _safe_digest(row['content_hash'])))
    return items


def _idempotency_needles(bot_id: str, scope_ids: dict[str, list[str]]) -> set[str]:
    """Opaque ids whose appearance in a receipt ties it to this Bot."""
    needles = {bot_id}
    for key in ('runs', 'conversations', 'jobs', 'workflows', 'documents', 'tasks'):
        needles.update(scope_ids.get(key, []))
    return {needle for needle in needles if needle}


def _idempotency_matches(db: sqlite3.Connection, bot_id: str,
                         scope_ids: dict[str, list[str]]) -> list[sqlite3.Row]:
    """Receipts whose scope or payload embeds a Bot-scoped opaque id."""
    needles = _idempotency_needles(bot_id, scope_ids)
    matches = []
    for row in db.execute('SELECT scope, key, response_json FROM idempotency_keys'):
        if str(row['scope']).startswith('api:v1:bot-deletion:'):
            continue
        haystack = str(row['scope']) + ' ' + str(row['response_json'] or '')
        if any(needle in haystack for needle in needles):
            matches.append(row)
    return matches


def _redact_idempotency(db: sqlite3.Connection, bot_id: str,
                        scope_ids: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """Keep receipts and hashes, replace content-bearing replay payloads in place."""
    items = []
    for row in _idempotency_matches(db, bot_id, scope_ids):
        original = _sha256_text(str(row['response_json'] or ''))
        db.execute('UPDATE idempotency_keys SET response_json = ? WHERE scope = ? AND key = ?',
                   ('{"redacted": "' + REDACTED_MARKER + '"}', row['scope'], row['key']))
        items.append(('idempotency_keys',
                      _sha256_text(str(row['scope']) + chr(0) + str(row['key']))[:32], original))
    return items


def _null_choice_questions(db: sqlite3.Connection, bot_id: str) -> list[tuple[str, str, str]]:
    """Break the messages/conversation_questions foreign-key cycle before either side is erased."""
    db.execute('UPDATE messages SET choice_question_id = NULL WHERE choice_question_id IN '
               '(SELECT id FROM conversation_questions WHERE bot_id = :bot)', {'bot': bot_id})
    return []


def _clean_resource_outbox(db: sqlite3.Connection, bot_id: str,
                           scope_ids: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """Drop durable-change notifications that name this Bot or one of its erased resources."""
    needles = _idempotency_needles(bot_id, scope_ids)
    deleted: list[int] = []
    for row in db.execute('SELECT id, resource_id, context FROM resource_outbox'):
        resource_id = '' if row['resource_id'] is None else str(row['resource_id'])
        context = '' if row['context'] is None else str(row['context'])
        if resource_id in needles or any(needle in context for needle in needles):
            deleted.append(int(row['id']))
    for outbox_id in deleted:
        db.execute('DELETE FROM resource_outbox WHERE id = ?', (outbox_id,))
    return []


def _handler_step(db: sqlite3.Connection, step: _Step, bot_id: str, now: str, request_id: str,
                  scope_ids: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """Dispatch one retention handler that needs row-by-row content erasure."""
    if step.handler == 'revoke_shares':
        return _revoke_shares(db, bot_id, now)
    if step.handler == 'tombstone_facts':
        return _tombstone_facts(db, bot_id, now, request_id)
    if step.handler == 'tombstone_shares':
        return _tombstone_shares(db, bot_id, now)
    if step.handler == 'tombstone_task_shares':
        return _tombstone_task_shares(db, bot_id, now)
    if step.handler == 'redact_idempotency':
        return _redact_idempotency(db, bot_id, scope_ids)
    if step.handler == 'null_choice_questions':
        return _null_choice_questions(db, bot_id)
    if step.handler == 'clean_outbox':
        return _clean_resource_outbox(db, bot_id, scope_ids)
    raise RuntimeError('unknown deletion step handler: ' + step.handler)


def _count_handler(db: sqlite3.Connection, step: _Step, bot_id: str,
                   scope_ids: dict[str, list[str]]) -> int:
    """Count the rows one retention handler will change, without loading content."""
    def one(sql: str, args: dict[str, Any]) -> int:
        """One scalar count query."""
        return int(db.execute(sql, args).fetchone()[0])

    if step.handler == 'revoke_shares':
        predicate = ('revoked_at IS NULL AND source_run_id IN ' + _BOT_RUNS
                     + ' AND target_conversation_id NOT IN ' + _BOT_CONVERSATIONS)
        return one('SELECT COUNT(*) FROM conversation_artifact_shares WHERE ' + predicate, {'bot': bot_id})
    if step.handler == 'tombstone_facts':
        return one("SELECT COUNT(*) FROM memory_facts WHERE bot_id = :bot AND purged_at = ''", {'bot': bot_id})
    if step.handler == 'tombstone_shares':
        return one("SELECT COUNT(*) FROM memory_fact_shares WHERE purged_at = '' "
                   'AND (source_bot_id = :bot OR target_bot_id = :bot)', {'bot': bot_id})
    if step.handler == 'tombstone_task_shares':
        return one("SELECT COUNT(*) FROM workspace_task_fact_shares "
                   "WHERE purged_at = '' AND source_bot_id = :bot", {'bot': bot_id})
    if step.handler == 'redact_idempotency':
        return len(_idempotency_matches(db, bot_id, scope_ids))
    return 0


def _count_step(db: sqlite3.Connection, step: _Step, bot_id: str,
                scope_ids: dict[str, list[str]]) -> int:
    """How many rows one step changes; the preview and confirm count share this function."""
    if step.kind == 'handler':
        return _count_handler(db, step, bot_id, scope_ids)
    return int(db.execute(f'SELECT COUNT(*) FROM {step.store} WHERE {step.predicate}',
                          {'bot': bot_id}).fetchone()[0])


def _add_count(counts: dict[str, int], key: str, value: int) -> None:
    """Accumulate one non-zero category; duplicate stores merge instead of overwriting."""
    if value:
        counts[key] = counts.get(key, 0) + value


def _path_exists(path: Path) -> bool:
    """Whether a managed entry currently exists, without following a symlink."""
    try:
        os.lstat(path)
    except OSError:
        return False
    return True


def _snapshot(db: sqlite3.Connection, bot_id: str, state_dir: Path) -> tuple[dict[str, int], list[str],
                                                                         dict[str, list[str]], sqlite3.Row]:
    """Counts, existing managed paths and opaque ids for the current state of one Bot."""
    bot_row = db.execute('SELECT id, name FROM bots WHERE id = ?', (bot_id,)).fetchone()
    if bot_row is None:
        raise KeyError(bot_id)
    scope_ids = _scope_ids(db, bot_id)
    candidates = _managed_paths(db, bot_row, scope_ids)
    paths = [relative for relative in candidates if _path_exists(state_dir / relative)]
    counts: dict[str, int] = {}
    _add_count(counts, 'bot', 1)
    _add_count(counts, 'files', len(paths))
    for step in _ERASE_STEPS:
        if step.store == 'bots':
            continue
        _add_count(counts, step.store, _count_step(db, step, bot_id, scope_ids))
    counts['total'] = sum(counts.values())
    return counts, paths, scope_ids, bot_row

# ------------------------------------------------------- filesystem manifest
