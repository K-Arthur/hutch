"""Whole-Bot deletion plan: limits, errors, the ordered erase steps and small primitives.

Pure data and helpers with no database or filesystem side effects of their own."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .identity import assistant_relative_path
from .models import ACTIVE_STATUSES, iso, utcnow


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
_MANAGED_FIRST_COMPONENTS = frozenset({'bots', 'workspaces', 'browser-profiles', 'documents', 'synthesis', 'identity'})
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
          'channel_id IN (SELECT id FROM channel_connections WHERE bot_id = :bot)'),
    _Step('notifications', 'delete', 'bot_id = :bot'),
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
    paths = ['workspaces/' + bot_id, 'browser-profiles/' + bot_id, assistant_relative_path(bot_id)]   # identity: sign-off and boundaries
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
