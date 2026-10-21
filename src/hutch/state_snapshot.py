"""Database snapshots and offline restore; no source process or workspace access.

A snapshot is not an archive of credentials, browser profiles or user files.
Restore publishes a held installation in a NEW directory. Process identities in
the copy are evidence, not authority to signal the source installation.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid
import shutil
from urllib.parse import quote

from . import __version__
from .config import hutchConfig
from .models import RunStatus, iso, utcnow

EXCLUDED = ["provider credentials and connection files", "browser profiles and cookies",
            "workspaces, artifacts and other user files", "filesystem transcript mirrors"]


class ExecutionHeld(RuntimeError):
    def __init__(self, restore_id: str):
        self.restore_id = restore_id
        super().__init__("Restored history is held for local review. Inspect the restore report on this machine "
                         "before activating new work; old work will not resume.")


def migrate(db: sqlite3.Connection) -> None:
    db.execute("ALTER TABLE run_procs ADD COLUMN detached_at TEXT")
    db.execute("ALTER TABLE run_procs ADD COLUMN detached_reason TEXT NOT NULL DEFAULT ''")
    db.execute("""CREATE TABLE state_restores (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source_schema INTEGER NOT NULL,
        manifest_hash TEXT NOT NULL, source_code_hash TEXT NOT NULL DEFAULT '',
        verified_code_hash TEXT NOT NULL, report_json TEXT NOT NULL CHECK(json_valid(report_json)),
        activated_at TEXT, activation_evidence TEXT NOT NULL DEFAULT '', superseded_by TEXT NOT NULL DEFAULT '')""")
    db.execute("""CREATE TABLE state_restore_items (
        restore_id TEXT NOT NULL, kind TEXT NOT NULL, resource_id TEXT NOT NULL, prior_status TEXT NOT NULL,
        PRIMARY KEY(restore_id, kind, resource_id))""")
    from .durable_changes import install_resources
    install_resources(db, (("state_restores", "state", "id", ("activated_at", "superseded_by"), ()),))


def code_hash() -> str:
    """Identify installed package code and runtime resources, excluding generated Python caches."""
    root = Path(__file__).parent
    value = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'}:
            continue
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            raise RuntimeError('installed package changed while computing its restore fingerprint') from None
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            continue
        with os.fdopen(fd, 'rb') as stream:
            value.update(path.relative_to(root).as_posix().encode() + b'\0')
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                value.update(chunk)
    return value.hexdigest()


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def _regular(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
        raise ValueError('snapshot input must be an owned regular file with no links')


def _open_source(path: Path) -> sqlite3.Connection:
    _regular(path)
    db = sqlite3.connect(f"file:{quote(str(path.absolute()))}?mode=ro", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def _sync(path: Path, *, directory: bool = False) -> None:
    fd = os.open(path, os.O_RDONLY | (os.O_DIRECTORY if directory else 0) | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _copy_database(source: Path, destination: Path) -> int:
    original = _open_source(source)
    target = sqlite3.connect(destination)
    os.chmod(destination, 0o600)
    try:
        deadline = time.monotonic() + 300
        def progress(*_args):
            if time.monotonic() >= deadline:
                raise RuntimeError('database snapshot exceeded five minutes; preserve the incomplete directory and retry')
        original.backup(target, pages=256, progress=progress)
        # A snapshot must be a standalone file, not a main file whose WAL could
        # later bypass the manifest digest. The unique destination has no peers.
        if target.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
            raise ValueError('could not produce a standalone database snapshot')
        if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('database integrity check failed')
        if target.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('database foreign key check failed')
        schema = target.execute('PRAGMA user_version').fetchone()[0]
        if not target.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bots'").fetchone():
            raise ValueError('input is not a Hutch database')
        return schema
    finally:
        target.close()
        original.close()


def backup(config: hutchConfig, destination: Path, *, source_database: Path | None = None) -> dict:
    """Capture committed WAL pages; never open/migrate the source through Store."""
    destination = destination.absolute()
    destination.mkdir(mode=0o700)  # exclusive: never overwrite a snapshot
    _write(destination / '.hutch-database-snapshot', {'scope': 'database snapshot; never executor state'})
    marker = destination / '.incomplete'
    _write(marker, {'operation': 'database snapshot'})
    schema = _copy_database(source_database or config.db_path, destination / 'hutch.db')
    _sync(destination / 'hutch.db')
    manifest = {'format': 'hutch-database-snapshot', 'format_version': 1,
                'created_at': iso(utcnow()), 'schema': schema, 'hutch_version': __version__,
                'capturing_code_hash': code_hash(), 'database_sha256': file_hash(destination / 'hutch.db'),
                'scope': 'database only', 'excluded': EXCLUDED}
    _write(destination / 'manifest.json', manifest)
    marker.unlink()
    _sync(destination, directory=True)
    _sync(destination.parent, directory=True)
    return manifest


def _manifest(snapshot: Path) -> dict:
    if (snapshot / '.incomplete').exists():
        raise ValueError('snapshot did not finish; preserve it and create a new snapshot')
    path = snapshot / 'manifest.json'
    _regular(path)
    with path.open('rb') as stream:
        raw = stream.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ValueError('snapshot manifest is too large')
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get('format') != 'hutch-database-snapshot'
            or type(value.get('format_version')) is not int or value.get('format_version') != 1
            or type(value.get('schema')) is not int or not isinstance(value.get('database_sha256'), str)
            or not isinstance(value.get('capturing_code_hash', ''), str)):
        raise ValueError('unsupported snapshot manifest')
    _regular(snapshot / 'hutch.db')
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = snapshot / ('hutch.db' + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            raise ValueError('snapshot has SQLite sidecars; close it and create a fresh snapshot')
    if file_hash(snapshot / 'hutch.db') != value['database_sha256']:
        raise ValueError('snapshot database hash does not match its manifest')
    value['_manifest_sha256'] = hashlib.sha256(raw).hexdigest()
    return value


def validate_history(store) -> dict:
    """Bounded event scan, including gaps and hashes; legacy hashes stay qualified."""
    from .store import GENESIS, chain_hash
    from .transcript_mirror import MAX_LINE_BYTES
    if store._db.execute('SELECT 1 FROM events WHERE length(CAST(data AS BLOB)) > ? LIMIT 1', (MAX_LINE_BYTES,)).fetchone():
        raise ValueError('snapshot contains an event beyond the supported transcript size; preserve it for inspection')
    checked = legacy = runs = 0
    cursor = store._db.execute('SELECT run_id, seq, hash, ts, type, data FROM events ORDER BY run_id, seq')
    previous_run, sequence, previous_hash = None, 0, GENESIS
    for row in cursor:
        if row['run_id'] != previous_run:
            previous_run, sequence, previous_hash = row['run_id'], 0, GENESIS
            runs += 1
        sequence += 1
        if row['seq'] != sequence:
            raise ValueError('snapshot transcript sequence has a gap')
        if not row['hash']:
            legacy += 1
            continue
        expected = chain_hash(previous_hash, row['run_id'], sequence, row['ts'], row['type'], row['data'])
        if expected != row['hash']:
            raise ValueError('snapshot transcript hash chain is invalid')
        checked += 1
        previous_hash = row['hash']
    for row in store._db.execute('SELECT intent_json, intent_hash FROM tool_actions'):
        from .action_receipts import digest
        if digest(row['intent_json']) != row['intent_hash']:
            raise ValueError('snapshot action intent hash is invalid')
    from .fact_memory import validate
    validate(store._db)
    return {'transcripts': runs, 'hashed_events': checked, 'unhashed_legacy_events': legacy}


def quarantine(store, manifest: dict, manifest_hash: str) -> dict:
    if not store._maintenance:
        raise RuntimeError('restore quarantine requires an offline maintenance store')
    verification = validate_history(store)
    restore_id, now = 'restore_' + uuid.uuid4().hex[:16], iso(utcnow())
    counts = {}
    with store._tx() as db:
        specifications = (
            ('runs', "SELECT id, status FROM runs WHERE sealed = 0 AND status NOT IN "
                     "('succeeded','failed','stopped','skipped','outcome_unknown')"),
            ('tasks', "SELECT id, state FROM tasks WHERE done = 0"),
            ('processes', "SELECT CAST(id AS TEXT), kind FROM run_procs WHERE ended_at IS NULL AND detached_at IS NULL"),
            ('approvals', "SELECT id, status FROM approvals WHERE status = 'pending'"),
            ('devices', "SELECT id, label FROM paired_credentials WHERE revoked_at IS NULL"),
            ('standing_permissions', "SELECT bot_id || ':' || sticky_key, 'granted' FROM tool_allows"),
            ('bots', "SELECT id, CASE WHEN json_extract(doc, '$.paused') THEN 'paused' ELSE 'enabled' END FROM bots"),
        )
        for kind, query in specifications:
            # Device labels, permission keys and prompts do not enter the public report.
            if kind == 'devices':
                query = "SELECT id, 'active' FROM paired_credentials WHERE revoked_at IS NULL"
            if kind == 'standing_permissions':
                counts[kind] = db.execute('SELECT COUNT(*) FROM tool_allows').fetchone()[0]
                continue
            count = 0
            cursor = db.execute(query)
            while rows := cursor.fetchmany(256):
                db.executemany('INSERT INTO state_restore_items VALUES (?, ?, ?, ?)',
                               [(restore_id, kind, row[0], row[1]) for row in rows])
                count += len(rows)
            counts[kind] = count
        # Never end/signal a process from the source. Its old identity remains
        # recorded with a distinct detached marker, not a false cleanup receipt.
        db.execute("UPDATE run_procs SET detached_at = ?, detached_reason = 'snapshot restore: source ownership relinquished' "
                   "WHERE ended_at IS NULL AND detached_at IS NULL", (now,))
        after = ''
        while rows := db.execute("SELECT id FROM runs WHERE id > ? AND sealed = 0 AND status NOT IN "
                                "('succeeded','failed','stopped','skipped','outcome_unknown') ORDER BY id LIMIT 256", (after,)).fetchall():
            for row in rows:
                after = row['id']
                store._apply_transition(db, after, RunStatus.outcome_unknown, None, 'restored_snapshot',
                    'Restored history cannot prove later effects. This old attempt will not resume. '
                    'Source process ownership was relinquished; source processes were not stopped by this restore.',
                    {'reason': 'restored_snapshot', 'restore_id': restore_id, 'source_processes_stopped': False},
                    True, {'owner': '', 'pgid': 0})
        db.execute("UPDATE tasks SET state = 'quarantined', done = 1 WHERE id IN "
                   "(SELECT resource_id FROM state_restore_items WHERE restore_id = ? AND kind = 'tasks')", (restore_id,))
        db.execute("UPDATE usage_reservations SET status = 'uncertain', reason = 'snapshot restored: reconcile provider usage' "
                   "WHERE status = 'reserved'")
        db.execute("UPDATE approvals SET status = 'expired', doc = json_set(doc, '$.status', 'expired', "
                   "'$.resolved_at', ?, '$.resolution', 'snapshot restored; permission is not transferable') "
                   "WHERE status = 'pending'", (now,))
        db.execute("UPDATE device_sessions SET revoked_at = ? WHERE revoked_at IS NULL", (now,))
        db.execute("UPDATE paired_credentials SET revoked_at = ? WHERE revoked_at IS NULL", (now,))
        db.execute("UPDATE auth_sessions SET revoked_at = ? WHERE revoked_at IS NULL", (now,))
        db.execute("DELETE FROM auth_challenges")
        db.execute("DELETE FROM passkey_attempts")
        db.execute("DELETE FROM pairing_codes")
        db.execute("DELETE FROM pairing_attempts")
        db.execute("DELETE FROM tool_allows")
        db.execute("UPDATE bots SET doc = json_set(doc, '$.paused', json('true'), '$.remote_start_enabled', json('false'))")
        db.execute("UPDATE supervisor_leases SET owner = '', expires_at = NULL, fence = fence + 1")
        db.execute("UPDATE runs SET pgid = 0 WHERE id IN "
                   "(SELECT resource_id FROM state_restore_items WHERE restore_id = ? AND kind = 'runs')", (restore_id,))
        db.execute("UPDATE resource_outbox_meta SET epoch = ? WHERE singleton = 1", (uuid.uuid4().hex,))
        # A new copy may itself contain a previous restore hold. Supersession
        # preserves its audit without pretending a human activated that copy.
        db.execute("UPDATE state_restores SET superseded_by = ? WHERE activated_at IS NULL AND superseded_by = ''", (restore_id,))
        report = {'id': restore_id, 'created_at': now, 'execution_held': True, 'counts': counts,
                  'verification': verification, 'source_schema': manifest['schema'],
                  'schema': store.schema_version, 'excluded': EXCLUDED, 'source_processes_stopped': False,
                  'old_work_will_resume': False}
        db.execute('INSERT INTO state_restores(id, created_at, source_schema, manifest_hash, source_code_hash, '
                   'verified_code_hash, report_json) VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (restore_id, now, manifest['schema'], manifest_hash, manifest.get('capturing_code_hash', ''),
                    code_hash(), json.dumps(report, sort_keys=True)))
    return report


def restore(snapshot: Path, destination: Path) -> dict:
    """Verify, migrate and quarantine before removing the incomplete marker."""
    from .store import Store
    snapshot, destination = snapshot.absolute(), destination.absolute()
    manifest = _manifest(snapshot)
    # Exclusive destination creation preserves existing installations/backups.
    destination.mkdir(mode=0o700)
    marker = destination / '.restore-in-progress'
    _write(marker, {'operation': 'restore', 'source_manifest_hash': manifest['_manifest_sha256']})
    # This is a closed, standalone snapshot produced by the backup API, never
    # a live main/WAL file copy. Hash the actual copied bytes before migration.
    with (snapshot / 'hutch.db').open('rb') as original, (destination / 'hutch.db').open('xb') as target:
        os.chmod(destination / 'hutch.db', 0o600)
        shutil.copyfileobj(original, target, length=1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    if (file_hash(destination / 'hutch.db') != manifest['database_sha256']
            or _manifest(snapshot)['_manifest_sha256'] != manifest['_manifest_sha256']):
        raise ValueError('snapshot changed during restoration')
    copied = _open_source(destination / 'hutch.db')
    try:
        if copied.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            raise ValueError('snapshot is not a closed standalone database; create a fresh backup')
        if copied.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or copied.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('copied database integrity check failed')
        if copied.execute('PRAGMA user_version').fetchone()[0] != manifest['schema']:
            raise ValueError('snapshot schema does not match its manifest')
    finally:
        copied.close()
    store = Store(hutchConfig(destination), maintenance=True)
    try:
        report = quarantine(store, manifest, manifest['_manifest_sha256'])
        store._db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:
        store.close()
    _sync(destination / 'hutch.db')
    _write(destination / 'restore-report.json', report)
    marker.unlink()
    _sync(destination, directory=True)
    _sync(destination.parent, directory=True)
    return report
