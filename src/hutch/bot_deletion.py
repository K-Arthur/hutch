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

import hmac
import json
import secrets
import sqlite3
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from .models import iso, utcnow
from .bot_deletion_files import _read_manifest, _remove_managed_path, _remove_manifest_dir, _write_manifest
from .bot_deletion_plan import BotDeletionConflict, DELETION_REMAINING, MAX_DELETION_ITEMS, _ACTIVE, _ACTIVE_MARKS, _ERASE_STEPS, _Expired, _LiveRuns, _ManifestError, _canonical, _now_iso, _request_hash, _scope_ids, _sha256_text, _valid_actor, _valid_note
from .bot_deletion_steps import _execute_sql_step, _handler_step, _insert_items, _snapshot

#: Long enough to read the consequences, short enough to stale.
DELETION_TOKEN_TTL_SECONDS = 600

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
