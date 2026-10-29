"""Governed whole-Bot permanent deletion: preview, confirm and cleanup recovery.

One Bot is erased by one BEGIN IMMEDIATE transaction that revalidates a
short-lived preview: exact per-store counts, a hashed one-time token, the typed
Bot address, the absence of live runs and the unchanged Bot name. Rows are
erased in foreign-key-safe order, retained receipts are redacted in place, the
bots row is deleted last and one content-free bot_deletion_items row records
every erased row or managed file. Managed files are deleted after commit from a
private fsynced manifest so a crash is resumable; a missing or unsafe manifest
is reported as needs_attention and never claimed complete.

Honest limits: database backups, exports, provider-side copies, channel-platform
history, OS caches or journals and user-owned folders (folder-mode workdir,
code-worktrees) are not erased. Retained content-free: completed usage rows,
prior memory-purge evidence, action receipts, schedule markers in kv, and the
global documentation index (doc_index_chunks/doc_index_fts is the local user
document corpus, not Bot-generated documents). No disk-shredding guarantee is
claimed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from .models import ACTIVE_STATUSES, iso, utcnow

#: Long enough to read the consequences, short enough to stale.
DELETION_TOKEN_TTL_SECONDS = 600
#: Upper bound on evidence rows one request may write; a scope this large needs review.
MAX_DELETION_ITEMS = 250_000
#: Honest, content-free statements of what a whole-Bot deletion cannot reach.
DELETION_REMAINING = (
    'database backups taken before this deletion, state snapshots and exports',
    'provider-side prompts, responses, uploaded media and OAuth grants held by the provider',
    'channel-platform message history on the remote service',
    'filesystem journals, copy-on-write snapshots, SSD wear-leveling copies and OS caches',
    'user-owned folder-mode --workdir content and code-worktrees/ directories',
)
#: Content-free marker for a retained receipt whose payload was erased.
REDACTED_MARKER = '[deleted]'
#: The one place managed paths are recorded; removed after a successful cleanup.
_MANIFEST_NAME = 'cleanup.json'
_MANIFEST_ROOT = 'deletions'
_MANAGED_FIRST_COMPONENTS = frozenset({'bots', 'workspaces', 'browser-profiles', 'documents', 'synthesis'})
_ACTIVE = tuple(status.value for status in ACTIVE_STATUSES)
_ACTIVE_MARKS = ', '.join('?' for _ in _ACTIVE)


class BotDeletionConflict(ValueError):
    """A previewed whole-Bot deletion can no longer be confirmed; nothing was erased."""


class _LiveRuns(Exception):
    """Internal: live runs were found inside the transaction; cancel after rollback."""

    def __init__(self, run_ids: list[str]):
        self.run_ids = run_ids
        super().__init__('live runs')


class _Expired(Exception):
    """Internal: the confirmation window elapsed; mark it after the rollback."""


class _ManifestError(Exception):
    """A cleanup manifest is missing, corrupt or outside the managed shapes."""


# ---------------------------------------------------------------- SQL scopes
# Named parameter :bot is the Bot id on every derived predicate. Every scope
# bottoms out in a direct bot_id table, so nested subqueries stay content-free.

_BOT_CONVERSATIONS = '(SELECT id FROM conversations WHERE bot_id = :bot)'
_BOT_RUNS = '(SELECT id FROM runs WHERE bot_id = :bot)'
_BOT_MESSAGES = '(SELECT id FROM messages WHERE conversation_id IN ' + _BOT_CONVERSATIONS + ')'
_BOT_JOBS = '(SELECT id FROM jobs WHERE bot_id = :bot)'
_BOT_INVESTIGATIONS = '(SELECT id FROM investigations WHERE bot_id = :bot)'
_BOT_MANIFESTS = '(SELECT id FROM syn_manifests WHERE bot_id = :bot)'
_BOT_PLANS = '(SELECT id FROM syn_plans WHERE bot_id = :bot)'
_BOT_WORKFLOWS = '(SELECT id FROM workflow_runs WHERE bot_id = :bot)'
_BOT_DOCUMENTS = '(SELECT id FROM documents WHERE bot_id = :bot)'
_BOT_TASKS = (
    '(SELECT id FROM workspace_tasks WHERE parent_conversation_id IN ' + _BOT_CONVERSATIONS
    + ' OR source_run_id IN ' + _BOT_RUNS
    + ' OR child_run_id IN ' + _BOT_RUNS
    + ' OR child_conversation_id IN ' + _BOT_CONVERSATIONS
    + ' OR source_user_message_id IN ' + _BOT_MESSAGES
    + ' OR source_assistant_message_id IN ' + _BOT_MESSAGES + ')'
)


@dataclass(frozen=True)
class _Step:
    """One ordered erase or retention action, also the unit of preview counts."""

    store: str
    kind: str = 'delete'      # delete | redact | cascade | handler
    predicate: str = ''
    set_sql: str = ''
    hash_sql: str = ''
    hash_kind: str = ''       # digest (stored as-is) | content (sha256 in Python)
    handler: str = ''


_ERASE_STEPS: tuple[_Step, ...] = (
    _Step('conversation_artifact_shares', 'handler', handler='revoke_shares'),
    _Step('memory_facts', 'handler', handler='tombstone_facts'),
    _Step('memory_fact_shares', 'handler', handler='tombstone_shares'),
    _Step('memory_facts_fts', 'delete',
          'rowid IN (SELECT rowid FROM memory_facts WHERE bot_id = :bot)'),
    _Step('workspace_task_fact_shares', 'handler', handler='tombstone_task_shares'),
    _Step('tool_actions', 'redact', 'run_id IN ' + _BOT_RUNS,
          "summary = '', intent_json = '{}', result_json = '{}'",
          hash_sql='result_digest', hash_kind='digest'),
    _Step('idempotency_keys', 'handler', handler='redact_idempotency'),
    _Step('action_reconciliations', 'redact', 'run_id IN ' + _BOT_RUNS,
          "evidence = '" + REDACTED_MARKER + "'", hash_sql='evidence', hash_kind='content'),
    _Step('memory_fact_decisions', 'redact', 'fact_id IN (SELECT id FROM memory_facts WHERE bot_id = :bot)',
          "note = ''", hash_sql='note', hash_kind='content'),
    _Step('budget_policies', 'delete',
          "(scope_kind = 'bot' AND scope_id = :bot)"
          + " OR (scope_kind = 'run' AND scope_id IN " + _BOT_RUNS + ')'
          + " OR (scope_kind = 'conversation' AND scope_id IN " + _BOT_CONVERSATIONS + ')'),
    _Step('budget_pause_releases', 'delete',
          "(scope_kind = 'bot' AND scope_id = :bot)"
          + " OR (scope_kind = 'run' AND scope_id IN " + _BOT_RUNS + ')'
          + " OR (scope_kind = 'conversation' AND scope_id IN " + _BOT_CONVERSATIONS + ')'
          + ' OR approval_id IN (SELECT id FROM approvals WHERE bot_id = :bot)'
          + ' OR reservation_id IN (SELECT id FROM usage_reservations WHERE bot_id = :bot)'),
    _Step('inv_media_frames', 'delete',
          'media_id IN (SELECT id FROM inv_media WHERE investigation_id IN ' + _BOT_INVESTIGATIONS + ')'),
    _Step('inv_evidence', 'delete', 'investigation_id IN ' + _BOT_INVESTIGATIONS),
    _Step('inv_observations', 'delete', 'investigation_id IN ' + _BOT_INVESTIGATIONS),
    _Step('inv_answers', 'delete', 'investigation_id IN ' + _BOT_INVESTIGATIONS),
    _Step('inv_query_attempts', 'delete', 'investigation_id IN ' + _BOT_INVESTIGATIONS),
    _Step('inv_media', 'delete', 'investigation_id IN ' + _BOT_INVESTIGATIONS),
    _Step('inv_claims', 'delete', 'investigation_id IN ' + _BOT_INVESTIGATIONS),
    _Step('inv_sources', 'delete', 'investigation_id IN ' + _BOT_INVESTIGATIONS),
    _Step('inv_stream_cursors', 'delete', 'investigation_id IN ' + _BOT_INVESTIGATIONS),
    _Step('investigations', 'delete', 'bot_id = :bot'),
    _Step('workspace_task_checkpoints', 'cascade',
          'workspace_task_id IN ' + _BOT_TASKS + ' OR child_run_id IN ' + _BOT_RUNS),
    _Step('workspace_task_continuations', 'cascade', 'task_id IN ' + _BOT_TASKS),
    _Step('workspace_task_fact_shares', 'cascade',
          'workspace_task_id IN ' + _BOT_TASKS + ' AND source_bot_id != :bot'),
    _Step('workspace_tasks', 'delete', 'id IN ' + _BOT_TASKS),
    _Step('delegated_wait_continuations', 'delete',
          'run_id IN ' + _BOT_RUNS + ' OR child_run_id IN ' + _BOT_RUNS),
    _Step('opencode_submissions', 'delete', 'run_id IN ' + _BOT_RUNS),
    _Step('human_wait_resumes', 'delete', 'run_id IN ' + _BOT_RUNS),
    _Step('code_handoffs', 'delete', 'bot_id = :bot'),
    _Step('channel_deliveries', 'delete',
          'event_id IN (SELECT id FROM channel_events WHERE channel_id IN '
          '(SELECT id FROM channel_connections WHERE bot_id = :bot))'),
    _Step('channel_events', 'delete',
          'channel_id IN (SELECT id FROM channel_connections WHERE bot_id = :bot)'),
    _Step('channel_threads', 'delete', 'bot_id = :bot'),
    _Step('channel_connections', 'delete', 'bot_id = :bot'),
    _Step('syn_manifest_revisions', 'delete', 'manifest_id IN ' + _BOT_MANIFESTS),
    _Step('syn_artifacts', 'delete', 'manifest_id IN ' + _BOT_MANIFESTS),
    _Step('syn_manifests', 'delete', 'bot_id = :bot'),
    _Step('syn_effects', 'delete', 'plan_id IN ' + _BOT_PLANS),
    _Step('syn_plans', 'delete', 'bot_id = :bot'),
    _Step('syn_sources', 'delete', 'bot_id = :bot'),
    _Step('workflow_amendment_history', 'delete', 'workflow_run_id IN ' + _BOT_WORKFLOWS),
    _Step('workflow_nodes', 'delete', 'workflow_run_id IN ' + _BOT_WORKFLOWS),
    _Step('workflow_questions', 'delete', 'workflow_run_id IN ' + _BOT_WORKFLOWS),
    _Step('workflow_runs', 'delete', 'bot_id = :bot'),
    _Step('conversation_artifact_shares', 'cascade', 'target_conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('conversation_task_state', 'delete', 'conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('conversation_task_state_revisions', 'cascade', 'conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('conversation_workflow_policies', 'delete', 'conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('assistant_home_conversations', 'delete', 'bot_id = :bot'),
    _Step('document_versions', 'delete', 'document_id IN ' + _BOT_DOCUMENTS),
    _Step('documents', 'delete', 'bot_id = :bot'),
    _Step('event_outbox', 'delete', 'run_id IN ' + _BOT_RUNS),
    _Step('events', 'delete', 'run_id IN ' + _BOT_RUNS),
    _Step('run_procs', 'delete', 'run_id IN ' + _BOT_RUNS),
    _Step('run_compactions', 'delete', 'run_id IN ' + _BOT_RUNS),
    _Step('transcript_delivery', 'delete', 'run_id IN ' + _BOT_RUNS),
    _Step('model_capability_observations', 'delete', 'run_id IN ' + _BOT_RUNS),
    _Step('media_jobs', 'delete', 'run_id IN ' + _BOT_RUNS + ' OR conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('source_events', 'delete',
          'run_id IN ' + _BOT_RUNS + ' OR job_id IN ' + _BOT_JOBS
          + ' OR source_id IN (SELECT id FROM event_sources WHERE bot_id = :bot)'),
    _Step('job_steps', 'delete', 'job_id IN ' + _BOT_JOBS + ' OR run_id IN ' + _BOT_RUNS),
    _Step('uploads', 'delete', 'conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('conversation_runs', 'delete',
          'conversation_id IN ' + _BOT_CONVERSATIONS + ' OR run_id IN ' + _BOT_RUNS),
    _Step('conversation_fts', 'delete', 'conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('workspace_sessions', 'delete', 'conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('persona_feedback', 'delete',
          'conversation_id IN ' + _BOT_CONVERSATIONS + ' OR message_id IN ' + _BOT_MESSAGES),
    _Step('messages', 'handler', handler='null_choice_questions'),
    _Step('conversation_questions', 'delete', 'bot_id = :bot'),
    _Step('messages', 'delete', 'conversation_id IN ' + _BOT_CONVERSATIONS),
    _Step('runs', 'delete', 'bot_id = :bot'),
    _Step('memory', 'delete', 'bot_id = :bot'),
    _Step('approvals', 'delete', 'bot_id = :bot'),
    _Step('tasks', 'delete', 'bot_id = :bot'),
    _Step('jobs', 'delete', 'bot_id = :bot'),
    _Step('event_sources', 'delete', 'bot_id = :bot'),
    _Step('tool_allows', 'delete', 'bot_id = :bot'),
    _Step('schedule_identities', 'delete', 'bot_id = :bot'),
    _Step('schedule_occurrences', 'delete', 'bot_id = :bot'),
    _Step('schedule_occurrences_v20', 'delete', 'bot_id = :bot'),
    _Step('opencode_session_bindings', 'delete', 'bot_id = :bot'),
    _Step('google_calendar_grants', 'delete', 'bot_id = :bot'),
    _Step('google_mail_grants', 'delete', 'bot_id = :bot'),
    _Step('google_mail_send_grants', 'delete', 'bot_id = :bot'),
    _Step('outlook_calendar_grants', 'delete', 'bot_id = :bot'),
    _Step('outlook_calendar_write_grants', 'delete', 'bot_id = :bot'),
    _Step('outlook_mail_grants', 'delete', 'bot_id = :bot'),
    _Step('outlook_mail_send_grants', 'delete', 'bot_id = :bot'),
    _Step('integration_tool_grants', 'delete', 'bot_id = :bot'),
    _Step('workspace_specialists', 'delete', 'bot_id = :bot'),
    _Step('usage_reservations', 'delete', 'bot_id = :bot'),
    _Step('conversations', 'delete', 'bot_id = :bot'),
    _Step('bots', 'delete', 'id = :bot'),
    _Step('resource_outbox', 'handler', handler='clean_outbox'),
)


# ------------------------------------------------------------- small helpers

def _canonical(value: Any) -> str:
    """Stable JSON for one digest; never persisted as erased content."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _sha256_text(value: str) -> str:
    """SHA-256 hex of one string."""
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _safe_digest(value: Any) -> str:
    """A stored digest when it looks like one, else the empty evidence hash."""
    text = '' if value is None else str(value)
    return text if len(text) == 64 and all(char in '0123456789abcdef' for char in text) else ''


def _valid_actor(actor: Any) -> str:
    """Bound the actor identity, exactly like the fact purge."""
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 120:
        raise ValueError('deletion requires a bounded actor identity')
    return actor.strip()


def _valid_note(note: Any) -> str:
    """Bound the operator note."""
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError('deletion note is limited to 1,000 characters')
    return note


def _now_iso() -> str:
    """Current UTC timestamp in the repository's canonical format."""
    return iso(utcnow())


def _request_hash(bot_id: str, request_id: str, token: str, confirmation: str, actor: str) -> str:
    """The idempotency request digest for one confirmation payload."""
    return _sha256_text(_canonical({'bot_id': bot_id, 'request_id': request_id, 'token': token,
                                    'confirmation': confirmation, 'actor': actor}))


def _scope_ids(db: sqlite3.Connection, bot_id: str) -> dict[str, list[str]]:
    """Recorded opaque ids used by redaction, cleanup paths and outbox cleanup."""
    def ids(sql: str) -> list[str]:
        """Run one id-only scoped query."""
        return [str(row[0]) for row in db.execute(sql, {'bot': bot_id})]

    return {
        'runs': ids('SELECT id FROM runs WHERE bot_id = :bot'),
        'conversations': ids('SELECT id FROM conversations WHERE bot_id = :bot'),
        'jobs': ids('SELECT id FROM jobs WHERE bot_id = :bot'),
        'workflows': ids('SELECT id FROM workflow_runs WHERE bot_id = :bot'),
        'documents': ids('SELECT id FROM documents WHERE bot_id = :bot'),
        'tasks': ids('SELECT id FROM workspace_tasks WHERE id IN ' + _BOT_TASKS),
        'synthesis': ids('SELECT DISTINCT storage_path FROM syn_artifacts WHERE storage_path != \'\' '
                         'AND manifest_id IN ' + _BOT_MANIFESTS),
    }


def _managed_paths(db: sqlite3.Connection, bot_row: sqlite3.Row, scope_ids: dict[str, list[str]]) -> list[str]:
    """Managed state-directory paths derived only from recorded opaque ids."""
    bot_id = str(bot_row['id'])
    bot_name = str(bot_row['name'])
    if not _safe_component(bot_name):
        raise BotDeletionConflict('the Bot address cannot name a managed directory')
    paths = ['workspaces/' + bot_id, 'browser-profiles/' + bot_id]
    paths += ['bots/' + bot_name + '/runs/' + run_id for run_id in scope_ids['runs']]
    paths += ['workspaces/' + conversation_id for conversation_id in scope_ids['conversations']]
    paths += ['documents/' + document_id for document_id in scope_ids['documents']]
    paths += ['synthesis/' + storage_path for storage_path in scope_ids['synthesis']]
    unique: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen and _managed_path_ok(path):
            seen.add(path)
            unique.append(path)
    return unique


def _safe_component(value: str) -> bool:
    """Whether a Bot name is one safe path component."""
    return bool(value) and value not in ('.', '..') and '/' not in value and '\\' not in value


def _managed_path_ok(relative: str) -> bool:
    """Whether one recorded path is a managed shape under the state directory."""
    parts = Path(relative).parts
    if not parts or not relative or os.path.isabs(relative):
        return False
    if any(part in ('..', '.', '') for part in parts):
        return False
    if parts[0] not in _MANAGED_FIRST_COMPONENTS:
        return False
    if parts[0] == 'bots':
        return len(parts) == 4 and parts[2] == 'runs'
    return len(parts) >= 2

# ------------------------------------------------------------- step engine

def _key_column(db: sqlite3.Connection, table: str) -> str:
    """The opaque row identity recorded in evidence: id when it is the only key, else rowid."""
    columns = [row for row in db.execute(f'PRAGMA table_info({table})')]
    keys = [row[1] for row in columns if row[5]]
    return 'id' if keys == ['id'] else 'rowid'


def _row_id_text(value: Any) -> str:
    """A bounded opaque row id; never erased content."""
    text = '' if value is None else str(value)
    if not text or len(text) > 128:
        return _sha256_text('row:' + text)[:32]
    return text


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

def _sha256_bytes(data: bytes) -> str:
    """SHA-256 hex of one byte string."""
    return hashlib.sha256(data).hexdigest()


def _chmod_private(path: Path) -> None:
    """Best-effort private permissions on a directory we own."""
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _fsync_dir(path: Path) -> None:
    """Best-effort directory fsync so a recorded path list survives a crash."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _manifest_dir(state_dir: Path, request_id: str) -> Path:
    """The private per-request directory holding the only managed-path record."""
    return Path(state_dir) / _MANIFEST_ROOT / request_id


def _write_manifest(state_dir: Path, request_id: str, bot_id: str, paths: list[str]) -> tuple[str, Path]:
    """Write a 0700, fsynced manifest of managed paths and return its SHA-256."""
    if not _safe_component(request_id):
        raise _ManifestError('the deletion request cannot name a manifest directory')
    for relative in paths:
        if not _managed_path_ok(relative):
            raise _ManifestError('a cleanup path is outside the managed state shapes')
    root = Path(state_dir) / _MANIFEST_ROOT
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _chmod_private(root)
    target = root / request_id
    target.mkdir(mode=0o700, exist_ok=True)
    _chmod_private(target)
    body = _canonical({'request_id': request_id, 'bot_id': bot_id, 'created_at': _now_iso(),
                       'paths': paths}).encode('utf-8')
    temporary = target / (_MANIFEST_NAME + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, target / _MANIFEST_NAME)
    _fsync_dir(target)
    _fsync_dir(root)
    return _sha256_bytes(body), target


def _remove_manifest_dir(state_dir: Path, request_id: str) -> None:
    """Remove the manifest record after its managed paths are gone; tolerate a missing one."""
    target = _manifest_dir(state_dir, request_id)
    try:
        (target / _MANIFEST_NAME).unlink(missing_ok=True)
        (target / (_MANIFEST_NAME + '.tmp')).unlink(missing_ok=True)
        os.rmdir(target)
    except FileNotFoundError:
        pass


def _read_manifest(state_dir: Path, request_id: str, expected_hash: str) -> dict[str, Any]:
    """Read and verify one cleanup manifest; any doubt is an honest cleanup error."""
    path = _manifest_dir(state_dir, request_id) / _MANIFEST_NAME
    try:
        data = path.read_bytes()
    except OSError:
        raise _ManifestError('the cleanup manifest is missing; the erased rows are gone and '
                             'the managed files may remain') from None
    if _sha256_bytes(data) != expected_hash:
        raise _ManifestError('the cleanup manifest does not match its recorded hash; managed files may remain')
    try:
        body = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise _ManifestError('the cleanup manifest is unreadable; managed files may remain') from None
    if not isinstance(body, dict) or body.get('request_id') != request_id:
        raise _ManifestError('the cleanup manifest does not describe this request; managed files may remain')
    paths = body.get('paths')
    if not isinstance(paths, list) or any(not isinstance(item, str) or not _managed_path_ok(item)
                                          for item in paths):
        raise _ManifestError('the cleanup manifest lists paths outside the managed shapes; nothing was deleted')
    return body


def _delete_tree(path: Path) -> None:
    """Depth-first deletion without following symlinks; missing entries are tolerated."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise _ManifestError('a recorded cleanup path is a symbolic link; nothing was deleted')
    if not stat.S_ISDIR(info.st_mode):
        os.unlink(path)
        return
    with os.scandir(path) as entries:
        names = [entry.name for entry in entries]
    for name in names:
        child = path / name
        try:
            child_info = os.lstat(child)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(child_info.st_mode):
            _delete_tree(child)
        else:
            os.unlink(child)
    os.rmdir(path)


def _remove_managed_path(state_dir: Path, relative: str) -> None:
    """Delete one recorded managed path, refusing symlinks or escapes; missing entries are fine."""
    if not _managed_path_ok(relative):
        raise _ManifestError('a recorded cleanup path is outside the managed shapes; nothing was deleted')
    current = Path(state_dir)
    for part in Path(relative).parts:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode):
            raise _ManifestError('a recorded cleanup path crosses a symbolic link; nothing was deleted')
    _delete_tree(current)


# ----------------------------------------------------------- cleanup state

def _fetch_request(store, request_id: str) -> Optional[sqlite3.Row]:
    """One request row under the store lock, or None."""
    with store._lock:
        return store._db.execute('SELECT * FROM bot_deletions WHERE id = ?', (request_id,)).fetchone()


def _set_cleanup_state(store, request_id: str, state: str, error: str = '', *, bump: bool = False) -> None:
    """Move one confirmed request's cleanup state forward; the schema guard enforces monotonic steps."""
    with store._tx() as db:
        row = db.execute('SELECT status, cleanup_state, cleanup_attempts FROM bot_deletions WHERE id = ?',
                         (request_id,)).fetchone()
        if row is None or row['status'] != 'confirmed':
            return
        attempts = int(row['cleanup_attempts']) + (1 if bump else 0)
        db.execute('UPDATE bot_deletions SET cleanup_state = ?, cleanup_attempts = ?, error = ? WHERE id = ?',
                   (state, attempts, '' if state == 'cleaned' else error[:2000], request_id))


def _cleanup_request(store, request_id: str) -> str:
    """Resume one committed deletion's filesystem cleanup from its manifest; safe to repeat."""
    row = _fetch_request(store, request_id)
    if row is None or row['status'] != 'confirmed':
        return 'skipped'
    if row['cleanup_state'] not in ('pending', 'cleaning', 'needs_attention'):
        return 'skipped'
    state_dir = Path(store.config.state_dir)
    _set_cleanup_state(store, request_id, 'cleaning', bump=True)
    try:
        manifest = _read_manifest(state_dir, request_id, row['manifest_hash'])
        for relative in manifest['paths']:
            _remove_managed_path(state_dir, relative)
        _remove_manifest_dir(state_dir, request_id)
    except _ManifestError as exc:
        _set_cleanup_state(store, request_id, 'needs_attention', str(exc))
        return 'needs_attention'
    except OSError:
        _set_cleanup_state(store, request_id, 'needs_attention',
                           'managed file cleanup failed; the erased rows are gone and files may remain')
        return 'needs_attention'
    _set_cleanup_state(store, request_id, 'cleaned')
    return 'cleaned'


# ------------------------------------------------------------- public API

def _record(row: sqlite3.Row) -> dict[str, Any]:
    """The exact content-free history record shape; never a token or path."""
    result = json.loads(row['result_json'] or '{}')
    if isinstance(result, dict) and result:
        result = dict(result)
        result['cleanup_state'] = row['cleanup_state']
    return {
        'request_id': row['id'],
        'bot_id': row['bot_id'],
        'status': row['status'],
        'actor': row['actor'],
        'note': row['note'],
        'created_at': row['created_at'],
        'expires_at': row['expires_at'],
        'confirmed_at': row['confirmed_at'],
        'deleted_at': row['deleted_at'],
        'cleanup_state': row['cleanup_state'],
        'counts': json.loads(row['counts_json'] or '{}'),
        'result': result,
    }


def request_record(store, request_id: str) -> Optional[dict[str, Any]]:
    """One content-free request record by id, resolved without the bots row."""
    row = _fetch_request(store, request_id)
    return _record(row) if row is not None else None


def requests(store, bot_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Recent whole-Bot deletion previews and outcomes; no tokens, paths or erased text."""
    bounded = max(1, min(100, int(limit)))
    with store._lock:
        rows = store._db.execute('SELECT * FROM bot_deletions WHERE bot_id = ? '
                                 'ORDER BY created_at DESC, id DESC LIMIT ?',
                                 (bot_id, bounded)).fetchall()
    return [_record(row) for row in rows]


def _supersede_pending(db: sqlite3.Connection, bot_id: str, now: str) -> None:
    """Mark stale pending previews expired, then supersede the rest before a new preview."""
    db.execute("UPDATE bot_deletions SET status = 'expired', token_hash = '' "
               "WHERE bot_id = ? AND status = 'pending' AND expires_at <= ?", (bot_id, now))
    db.execute("UPDATE bot_deletions SET status = 'superseded', token_hash = '' "
               "WHERE bot_id = ? AND status = 'pending'", (bot_id,))


def preview(store, bot_id: str, *, actor: str, note: str = '') -> dict[str, Any]:
    """Issue a single-use, count-snapshotted confirmation token for one whole Bot."""
    actor = _valid_actor(actor)
    note = _valid_note(note)
    if not isinstance(bot_id, str) or not bot_id:
        raise ValueError('deletion requires one Bot id')
    now = _now_iso()
    request_id = 'del_' + uuid.uuid4().hex[:20]
    token = secrets.token_urlsafe(32)
    expires = iso(utcnow() + timedelta(seconds=DELETION_TOKEN_TTL_SECONDS))
    with store._tx() as db:
        try:
            counts, _paths, _scope_ids, bot_row = _snapshot(db, bot_id, Path(store.config.state_dir))
        except KeyError:
            raise ValueError('unknown Bot: nothing can be previewed') from None
        live = db.execute(f'SELECT COUNT(*) FROM runs WHERE bot_id = ? AND status IN ({_ACTIVE_MARKS})',
                          (bot_id, *_ACTIVE)).fetchone()[0]
        if live:
            raise BotDeletionConflict('this Bot has live runs; stop them before previewing whole-Bot deletion')
        if counts['total'] > MAX_DELETION_ITEMS:
            raise BotDeletionConflict(f'this deletion would record {counts["total"]:,} evidence items; '
                                      'review the Bot before confirming')
        _supersede_pending(db, bot_id, now)
        request_hash = _sha256_text(_canonical({'bot_id': bot_id, 'counts': counts,
                                                'actor': actor, 'note': note}))
        db.execute('INSERT INTO bot_deletions (id, bot_id, bot_name_hash, actor, note, request_hash, '
                   'token_hash, status, counts_json, result_json, manifest_hash, cleanup_state, '
                   'cleanup_attempts, created_at, expires_at, confirmed_at, deleted_at, error) '
                   "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, '{}', '', 'none', 0, ?, ?, '', '', '')",
                   (request_id, bot_id, _sha256_text(str(bot_row['name'])), actor, note, request_hash,
                    _sha256_text(token), json.dumps(counts, sort_keys=True), now, expires))
    store.bus.notify('bots')
    return {
        'request_id': request_id,
        'token': token,
        'expires_at': expires,
        'created_at': now,
        'bot_id': bot_id,
        'bot_name': str(bot_row['name']),
        'counts': counts,
        'remaining': list(DELETION_REMAINING),
        'confirmation_hint': str(bot_row['name']),
    }


def _replay(db: sqlite3.Connection, scope: str, idem_key: Optional[str],
            request_hash: str) -> Optional[dict[str, Any]]:
    """The stored idempotent result, if this key and payload already ran."""
    if idem_key is None:
        return None
    from .store import IdempotencyConflict, Store
    try:
        return Store._idempotency_replay(db, scope, idem_key, request_hash)
    except IdempotencyConflict as exc:
        raise BotDeletionConflict(str(exc)) from None

def _valid_token(row: sqlite3.Row, token: str) -> bool:
    """Constant-time check of the one-time token against its stored SHA-256."""
    stored = str(row['token_hash'] or '')
    if len(stored) != 64:
        return False
    return hmac.compare_digest(_sha256_text(token), stored)


def _erase_and_confirm(db: sqlite3.Connection, bot_row: sqlite3.Row, counts: dict[str, int],
                       paths: list[str], request_id: str, now: str,
                       scope_ids: dict[str, list[str]], manifest_hash: str) -> dict[str, Any]:
    """Erase, redact and write evidence; secure_delete is enabled only for this transaction."""
    bot_id = str(bot_row['id'])
    previous_secure_delete = db.execute('PRAGMA secure_delete').fetchone()[0]
    db.execute('PRAGMA secure_delete = ON')
    db.execute('INSERT INTO bot_deletion_scope (singleton, request_id, created_at) VALUES (1, ?, ?)',
               (request_id, now))
    try:
        for step in _ERASE_STEPS:
            if step.kind == 'handler':
                items = _handler_step(db, step, bot_id, now, request_id, scope_ids)
            else:
                items = _execute_sql_step(db, step, bot_id, now)
            _insert_items(db, request_id, items, now)
        _insert_items(db, request_id,
                      [('files', _sha256_text(relative)[:32], '') for relative in paths], now)
        result = {
            'request_id': request_id,
            'status': 'confirmed',
            'deleted_at': now,
            'counts': counts,
            'remaining': list(DELETION_REMAINING),
            'cleanup_state': 'pending',
        }
        db.execute("UPDATE bot_deletions SET status = 'confirmed', confirmed_at = ?, deleted_at = ?, "
                   "token_hash = '', result_json = ?, manifest_hash = ?, cleanup_state = 'pending', "
                   "cleanup_attempts = 0, error = '' WHERE id = ?",
                   (now, now, json.dumps(result, sort_keys=True), manifest_hash, request_id))
        db.execute('DELETE FROM bot_deletion_scope WHERE singleton = 1')
        return result
    finally:
        db.execute(f'PRAGMA secure_delete = {int(previous_secure_delete)}')


def _confirm_locked(db: sqlite3.Connection, bot_id: str, request_id: str, *, token: str,
                    confirmation: str, actor: str, idem_key: Optional[str], request_hash: str,
                    scope: str, state_dir: Path) -> dict[str, Any]:
    """Revalidate and erase inside the caller's BEGIN IMMEDIATE transaction."""
    row = db.execute('SELECT * FROM bot_deletions WHERE id = ?', (request_id,)).fetchone()
    if row is None or row['bot_id'] != bot_id:
        raise KeyError(request_id)
    stored_result = json.loads(row['result_json'] or '{}')
    if row['status'] == 'confirmed':
        if idem_key is None:
            return stored_result
        raise BotDeletionConflict('this deletion request was already confirmed; a different idempotency '
                                  'key cannot repeat it')
    if row['status'] != 'pending':
        raise BotDeletionConflict('this deletion request is no longer pending; preview the deletion again')
    if not _valid_token(row, token):
        raise BotDeletionConflict('deletion token is invalid; preview the deletion again')
    bot_row = db.execute('SELECT id, name FROM bots WHERE id = ?', (bot_id,)).fetchone()
    if bot_row is None:
        raise KeyError(bot_id)
    if _sha256_text(str(bot_row['name'])) != row['bot_name_hash']:
        raise BotDeletionConflict('the Bot address changed since the preview; preview the deletion again')
    if not hmac.compare_digest(confirmation.strip(), str(bot_row['name'])):
        raise BotDeletionConflict('the typed Bot address does not match; nothing was erased')
    now = _now_iso()
    if row['expires_at'] <= now:
        raise _Expired()
    live = db.execute(f'SELECT id FROM runs WHERE bot_id = ? AND status IN ({_ACTIVE_MARKS})',
                      (bot_id, *_ACTIVE)).fetchall()
    if live:
        raise _LiveRuns([str(item['id']) for item in live])
    counts, paths, scope_ids, current_bot = _snapshot(db, bot_id, state_dir)
    if counts != json.loads(row['counts_json'] or '{}'):
        raise BotDeletionConflict('the Bot changed since the preview; preview the deletion again')
    try:
        manifest_hash, _target = _write_manifest(state_dir, request_id, bot_id, paths)
    except _ManifestError:
        raise
    except OSError:
        raise BotDeletionConflict('the cleanup manifest could not be written; nothing was erased') from None
    try:
        result = _erase_and_confirm(db, current_bot, counts, paths, request_id, now, scope_ids,
                                    manifest_hash)
        if idem_key is not None:
            db.execute('INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) '
                       'VALUES (?, ?, ?, ?, ?)',
                       (scope, idem_key, request_hash, json.dumps(result, sort_keys=True), now))
    except BaseException:
        _remove_manifest_dir(state_dir, request_id)
        raise
    return result


def confirm(store, bot_id: str, request_id: str, *, token: str, confirmation: str, actor: str,
            idem_key: Optional[str] = None, request_hash: Optional[str] = None) -> dict[str, Any]:
    """Apply one previewed whole-Bot deletion; a retry with the same key returns the same result."""
    actor = _valid_actor(actor)
    if not isinstance(token, str) or not 16 <= len(token) <= 200:
        raise ValueError('deletion token is invalid')
    if not isinstance(confirmation, str):
        raise ValueError('the typed Bot address is required')
    if idem_key is not None and (not isinstance(idem_key, str) or not 1 <= len(idem_key) <= 200):
        raise ValueError('idempotency key is invalid')
    if not isinstance(bot_id, str) or not bot_id or not isinstance(request_id, str) or not request_id:
        raise ValueError('deletion requires a Bot id and a request id')
    scope = 'api:v1:bot-deletion:' + bot_id + ':' + request_id
    digest = request_hash or _request_hash(bot_id, request_id, token, confirmation, actor)
    state_dir = Path(store.config.state_dir)
    live_ids: list[str] = []
    expired = False
    result: dict[str, Any] = {}
    try:
        with store._tx() as db:
            replay = _replay(db, scope, idem_key, digest)
            if replay is not None:
                result = replay
            else:
                result = _confirm_locked(db, bot_id, request_id, token=token, confirmation=confirmation,
                                         actor=actor, idem_key=idem_key, request_hash=digest,
                                         scope=scope, state_dir=state_dir)
    except _Expired:
        expired = True
    except _LiveRuns as live:
        live_ids = live.run_ids
    if expired:
        _mark_expired(store, request_id)
        raise BotDeletionConflict('the deletion confirmation window expired; preview the deletion again')
    if live_ids:
        for run_id in live_ids:
            store.request_cancel(run_id)
        raise BotDeletionConflict(f'{len(live_ids)} live run(s) block this deletion; cancellation was '
                                  'requested, retry after they stop')
    try:
        with store._lock:
            store._db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    except sqlite3.OperationalError:
        pass
    if result.get('status') == 'confirmed':
        try:
            _cleanup_request(store, request_id)
        except Exception:
            _mark_cleanup_failure(store, request_id)
        result = _fresh_result(store, request_id, result)
    store.bus.notify('bots', 'runs', 'conversations')
    return result


def _mark_expired(store, request_id: str) -> None:
    """Commit the expired outcome in its own transaction after a rolled-back confirmation."""
    with store._tx() as db:
        db.execute("UPDATE bot_deletions SET status = 'expired', token_hash = '' "
                   "WHERE id = ? AND status = 'pending'", (request_id,))


def _mark_cleanup_failure(store, request_id: str) -> None:
    """Expose an unexpected cleanup failure honestly; the row stays resumable."""
    try:
        _set_cleanup_state(store, request_id, 'needs_attention',
                           'file cleanup failed unexpectedly; rerun cleanup recovery to retry')
    except Exception:
        pass


def _fresh_result(store, request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Return the stored result with the live cleanup state, which is immutable in result_json."""
    row = _fetch_request(store, request_id)
    state = str(row['cleanup_state']) if row is not None else str(result.get('cleanup_state', 'pending'))
    if state not in ('cleaned', 'needs_attention'):
        state = 'pending'
    fresh = dict(result)
    fresh['cleanup_state'] = state
    return fresh


def recover_cleanup(store) -> dict[str, Any]:
    """Resume committed-but-uncleaned deletions from their manifests; never claims false completion."""
    with store._lock:
        rows = store._db.execute("SELECT id FROM bot_deletions WHERE status = 'confirmed' "
                                 "AND cleanup_state IN ('pending', 'cleaning', 'needs_attention') "
                                 'ORDER BY created_at, id').fetchall()
    cleaned: list[str] = []
    needs_attention: list[str] = []
    for row in rows:
        try:
            outcome = _cleanup_request(store, str(row['id']))
        except Exception:
            outcome = 'cleaning'
        if outcome == 'cleaned':
            cleaned.append(str(row['id']))
        elif outcome == 'needs_attention':
            needs_attention.append(str(row['id']))
    return {'checked': len(rows), 'cleaned': cleaned, 'needs_attention': needs_attention}
