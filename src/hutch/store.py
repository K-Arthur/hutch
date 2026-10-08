"""SQLite persistence layer.

One file, WAL mode, ONE writer connection (PF-7): FastAPI workers and daemon
threads share it behind a lock, and event inserts are queued and committed in
batches by a single writer thread, using FULL WAL synchronization. Canonical
events and transcript delivery intents commit together. An owned drainer
verifies/appends/fsyncs JSONL files and acknowledges delivery separately;
resource invalidations provide reconnectable state and visible mirror errors.

Events carry a gap-free per-run ``seq`` (the resume cursor for SSE, UI-3) and a
hash-chain link (SR-11). The schema is versioned with ``PRAGMA user_version``;
upgrades back the database up first.
"""

from __future__ import annotations

import atexit
import fcntl
import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
import weakref
import contextlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from .config import hutchConfig, get_config
from . import action_receipts, durable_changes
from .lifecycle import TERMINAL, IllegalTransition, LeaseLost, allowed
from .models import (
    ACTIVE_STATUSES,
    ApprovalRequest,
    ApprovalStatus,
    Bot,
    Event,
    EventType,
    MemoryItem,
    Run,
    RunStatus,
    Schedule,
    Task,
    iso,
    local_day_bounds,
    utcnow,
)
from .wake import Bus, WakeHub

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bots (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    prompt TEXT NOT NULL,
    created_at TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    task_id TEXT,
    doc TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_bot ON runs(bot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE TABLE IF NOT EXISTS tool_allows (
    bot_id TEXT NOT NULL,
    sticky_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (bot_id, sticky_key)
);
CREATE TABLE IF NOT EXISTS memory (
    bot_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (bot_id, key)
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


GENESIS = "0" * 64


def chain_hash(prev: str, run_id: str, seq: int, ts: str, type_: str, data_json: str) -> str:
    """Hash-chain link (SR-11): editing, dropping or reordering any past event breaks every later hash."""
    return hashlib.sha256(f"{prev}|{run_id}|{seq}|{ts}|{type_}|{data_json}".encode()).hexdigest()


def _migrate_2(db: sqlite3.Connection) -> None:
    """Per-run event sequence + hash chain; memory provenance."""
    db.execute("ALTER TABLE events ADD COLUMN seq INTEGER NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE events ADD COLUMN hash TEXT NOT NULL DEFAULT ''")
    db.execute(
        "UPDATE events SET seq = (SELECT COUNT(*) FROM events e2 "
        "WHERE e2.run_id = events.run_id AND e2.id <= events.id)"
    )
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq)")
    db.execute("ALTER TABLE memory ADD COLUMN run_id TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE memory ADD COLUMN source TEXT NOT NULL DEFAULT 'bot'")


def _migrate_3(db: sqlite3.Connection) -> None:
    """Usage ledger: one row per model call. Powers allowance enforcement for subscription connections
    (CN-5) and the Usage page (UI-11): spend by bot, provider and day."""
    db.execute("""CREATE TABLE IF NOT EXISTS usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, run_id TEXT NOT NULL, bot_id TEXT NOT NULL,
        provider TEXT NOT NULL, model TEXT NOT NULL, prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0, cached_tokens INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'step')""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_usage_provider_ts ON usage(provider, ts)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_usage_bot_ts ON usage(bot_id, ts)")


def _migrate_4(db: sqlite3.Connection) -> None:
    """Model reliability profiles (LM-11): keyed by model + quant + runtime + template + digest + window, so a changed
    file, runtime or window is a *different* profile instead of a stale number."""
    db.execute("""CREATE TABLE IF NOT EXISTS model_profiles (
        key TEXT PRIMARY KEY, model TEXT NOT NULL, runtime TEXT NOT NULL, digest TEXT NOT NULL DEFAULT '',
        template_hash TEXT NOT NULL DEFAULT '', measured_at TEXT NOT NULL, doc TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_profiles_model ON model_profiles(model, measured_at)")


def _migrate_5(db: sqlite3.Connection) -> None:
    """Ownership, leases and fencing (ADR-0001/0003): who holds a run, until when, and which writes are stale; durable task
    state; one row per claimed schedule occurrence; one row per tool action so a crash can be told from a clean stop.

    Additive only. Existing rows get fence 0 / no lease and keep working: they are 'legacy' and recovered by the old pid check.
    """
    db.execute("ALTER TABLE runs ADD COLUMN fence INTEGER NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE runs ADD COLUMN lease_owner TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE runs ADD COLUMN lease_expires_at TEXT")
    db.execute("ALTER TABLE runs ADD COLUMN heartbeat_at TEXT")
    db.execute("ALTER TABLE runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE runs ADD COLUMN pgid INTEGER NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE runs ADD COLUMN sealed INTEGER NOT NULL DEFAULT 0")   # 1 once a transition ended it: no more events
    db.execute("CREATE INDEX IF NOT EXISTS idx_runs_lease ON runs(status, lease_expires_at)")
    db.execute("ALTER TABLE tasks ADD COLUMN state TEXT NOT NULL DEFAULT 'queued'")
    db.execute("ALTER TABLE tasks ADD COLUMN run_id TEXT")
    db.execute("UPDATE tasks SET state = CASE WHEN done = 1 THEN 'done' ELSE 'queued' END")
    db.execute("UPDATE tasks SET run_id = (SELECT r.id FROM runs r WHERE r.task_id = tasks.id)")
    db.execute("""CREATE TABLE IF NOT EXISTS schedule_occurrences (
        bot_id TEXT NOT NULL, occurrence TEXT NOT NULL, run_id TEXT NOT NULL, claimed_at TEXT NOT NULL,
        claimed_by TEXT NOT NULL DEFAULT '', PRIMARY KEY (bot_id, occurrence))""")
    db.execute("""CREATE TABLE IF NOT EXISTS tool_actions (
        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, tool TEXT NOT NULL, idem_key TEXT NOT NULL, effect TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
        result_digest TEXT NOT NULL DEFAULT '')""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_actions_run ON tool_actions(run_id, status)")
    db.execute("""CREATE TABLE IF NOT EXISTS run_procs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, pid INTEGER NOT NULL, pgid INTEGER NOT NULL,
        starttime INTEGER NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'tool', started_at TEXT NOT NULL, ended_at TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_run_procs_run ON run_procs(run_id, ended_at)")
    db.execute("ALTER TABLE approvals ADD COLUMN action_hash TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE approvals ADD COLUMN expires_at TEXT")
    db.execute("UPDATE approvals SET expires_at = json_extract(doc, '$.expires_at')")
    # bots from before the OS sandbox existed keep running as they did; only bots created from now on default to it
    db.execute("UPDATE bots SET doc = json_set(doc, '$.sandbox', 'off') WHERE json_extract(doc, '$.sandbox') IS NULL")


def _migrate_6(db: sqlite3.Connection) -> None:
    """Record the kernel boot identity alongside process start ticks so recovery cannot signal a reused PID after reboot."""
    db.execute("ALTER TABLE run_procs ADD COLUMN boot_id TEXT NOT NULL DEFAULT ''")


def _migrate_7(db: sqlite3.Connection) -> None:
    """Elect one durable scheduler/recovery supervisor across dashboard workers and daemon processes."""
    db.execute("""CREATE TABLE IF NOT EXISTS supervisor_leases (
        name TEXT PRIMARY KEY, owner TEXT NOT NULL DEFAULT '', expires_at TEXT, fence INTEGER NOT NULL DEFAULT 0)""")


def _migrate_8(db: sqlite3.Connection) -> None:
    """Canonical conversations and restart-safe command idempotency (ADR-0010/0011)."""
    db.execute("""CREATE TABLE conversations (
        id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
        is_legacy INTEGER NOT NULL DEFAULT 0)""")
    db.execute("CREATE INDEX idx_conversations_bot_updated ON conversations(bot_id, archived, updated_at DESC)")
    db.execute("""CREATE TABLE messages (
        id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, seq INTEGER NOT NULL,
        run_id TEXT NOT NULL DEFAULT '', role TEXT NOT NULL CHECK(role IN ('user','assistant')),
        content TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(conversation_id, seq))""")
    db.execute("CREATE INDEX idx_messages_conversation_seq ON messages(conversation_id, seq)")
    db.execute("""CREATE TABLE conversation_runs (
        conversation_id TEXT NOT NULL, run_id TEXT NOT NULL UNIQUE, attached_at TEXT NOT NULL,
        PRIMARY KEY(conversation_id, run_id))""")
    db.execute("""CREATE TABLE idempotency_keys (
        scope TEXT NOT NULL, key TEXT NOT NULL, request_hash TEXT NOT NULL,
        response_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(scope, key))""")
    db.execute("ALTER TABLE runs ADD COLUMN conversation_id TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE runs ADD COLUMN conversation_context TEXT NOT NULL DEFAULT '[]'")
    # FTS5 indexes only approved conversation text, never tool output, workspaces or secrets.
    db.execute("CREATE VIRTUAL TABLE conversation_fts USING fts5(message_id UNINDEXED, conversation_id UNINDEXED, content)")

    # Keep every historic run and its transcript in its own imported conversation. Combining runs here would
    # silently join contexts whose ownership or intended continuity was never recorded by older releases.
    runs = db.execute("SELECT id, bot_id, created_at, doc FROM runs ORDER BY created_at, id").fetchall()
    for row in runs:
        doc = json.loads(row["doc"])
        conversation_id = f"conv_legacy_{row['id']}"
        created_at = row["created_at"]
        prompt = str(doc.get("prompt") or "")
        title = (prompt.strip().replace("\n", " ")[:72] or f"Imported run {row['id']}")
        db.execute("INSERT INTO conversations (id, bot_id, title, created_at, updated_at, is_legacy) "
                   "VALUES (?, ?, ?, ?, ?, 1)",
                   (conversation_id, row["bot_id"], title, created_at, created_at))
        seq = 0
        if prompt:
            seq += 1
            message_id = f"msg_legacy_{row['id']}_user"
            db.execute("INSERT INTO messages (id, conversation_id, seq, run_id, role, content, created_at) "
                       "VALUES (?, ?, ?, ?, 'user', ?, ?)",
                       (message_id, conversation_id, seq, row["id"], prompt, created_at))
            db.execute("INSERT INTO conversation_fts (message_id, conversation_id, content) VALUES (?, ?, ?)",
                       (message_id, conversation_id, prompt))
        events = db.execute("SELECT id, ts, data FROM events WHERE run_id = ? AND type = 'message' ORDER BY id",
                            (row["id"],)).fetchall()
        for event in events:
            data = json.loads(event["data"])
            content = data.get("content")
            if data.get("role") != "assistant" or not isinstance(content, str) or not content:
                continue
            seq += 1
            message_id = f"msg_legacy_{row['id']}_{event['id']}"
            db.execute("INSERT INTO messages (id, conversation_id, seq, run_id, role, content, created_at) "
                       "VALUES (?, ?, ?, ?, 'assistant', ?, ?)",
                       (message_id, conversation_id, seq, row["id"], content, event["ts"]))
            db.execute("INSERT INTO conversation_fts (message_id, conversation_id, content) VALUES (?, ?, ?)",
                       (message_id, conversation_id, content))
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (conversation_id, row["id"], created_at))
        db.execute("UPDATE runs SET conversation_id = ? WHERE id = ?", (conversation_id, row["id"]))


def _migrate_9(db: sqlite3.Connection) -> None:
    """Single-use remote pairing and revocable device sessions (ADR-0010)."""
    db.execute("""CREATE TABLE pairing_codes (
        code_hash TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT)""")
    db.execute("""CREATE TABLE device_sessions (
        id TEXT PRIMARY KEY, label TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_used_at TEXT,
        revoked_at TEXT)""")
    db.execute("CREATE INDEX idx_device_sessions_active ON device_sessions(revoked_at, expires_at)")
    db.execute("""CREATE TABLE pairing_attempts (
        remote_ip TEXT PRIMARY KEY, window_started_at TEXT NOT NULL, failures INTEGER NOT NULL DEFAULT 0)""")


def _migrate_10(db: sqlite3.Connection) -> None:
    """Shared, crash-safe provider/account usage reservations (ADR-0011)."""
    db.execute("ALTER TABLE usage ADD COLUMN account_id TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE usage ADD COLUMN reservation_id TEXT")
    db.execute("UPDATE usage SET account_id = provider WHERE account_id = ''")
    db.execute("CREATE INDEX idx_usage_account_ts ON usage(account_id, ts)")
    db.execute("CREATE UNIQUE INDEX idx_usage_reservation ON usage(reservation_id) WHERE reservation_id IS NOT NULL")
    db.execute("""CREATE TABLE usage_reservations (
        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, bot_id TEXT NOT NULL, provider TEXT NOT NULL,
        account_id TEXT NOT NULL, model TEXT NOT NULL, reserved_tokens INTEGER NOT NULL DEFAULT 0,
        reserved_cost_usd REAL NOT NULL DEFAULT 0, status TEXT NOT NULL,
        created_at TEXT NOT NULL, resolved_at TEXT, actual_prompt_tokens INTEGER,
        actual_completion_tokens INTEGER, actual_cached_tokens INTEGER NOT NULL DEFAULT 0,
        actual_cost_usd REAL, reason TEXT NOT NULL DEFAULT '')""")
    db.execute("CREATE INDEX idx_usage_reservations_run ON usage_reservations(run_id, status, created_at)")
    db.execute("CREATE INDEX idx_usage_reservations_bot ON usage_reservations(bot_id, status, created_at)")
    db.execute("CREATE INDEX idx_usage_reservations_account ON usage_reservations(account_id, status, created_at)")


def _migrate_11(db: sqlite3.Connection) -> None:
    """Resource invalidations commit with their state; existing resources require a snapshot."""
    durable_changes.migrate(db)


def _migrate_12(db: sqlite3.Connection) -> None:
    from .transcript_mirror import migrate
    migrate(db)
    durable_changes.install_resources(db, (
        ("transcript_delivery", "transcript_mirrors", "run_id", ("delivered_seq", "error"), ("run_id",)),
    ))


def _migrate_13(db: sqlite3.Connection) -> None:
    action_receipts.migrate(db)
    durable_changes.install_resources(db, (
        ("action_reconciliations", "actions", "action_id", (), ("run_id",)),
    ))


def _migrate_14(db: sqlite3.Connection) -> None:
    from .state_snapshot import migrate
    migrate(db)


#: schema upgrades applied in order; index + 2 == resulting user_version
_MIGRATIONS = [_migrate_2, _migrate_3, _migrate_4, _migrate_5, _migrate_6, _migrate_7, _migrate_8, _migrate_9, _migrate_10,
               _migrate_11, _migrate_12, _migrate_13, _migrate_14]
SCHEMA_VERSION = 1 + len(_MIGRATIONS)

#: computed fields of ``Run`` are for API output only and are never persisted
_RUN_COMPUTED = {"status_label", "terminal", "needs_person"}
#: the run columns that are authoritative over whatever the JSON document says
_RUN_COLS = "doc, status, fence, lease_owner, lease_expires_at, cancel_requested, pgid, conversation_id, conversation_context"
_TERMINAL_VALUES = tuple(sorted(st.value for st in TERMINAL))
_LIVE_VALUES = tuple(sorted(st.value for st in ACTIVE_STATUSES if st is not RunStatus.pending))
#: fields only the owner writes while a run is claimed: merged into the document in one statement (no read-modify-write)
_PROGRESS_FIELDS = {"steps", "tokens", "workspace", "started_at", "prompt_tokens", "completion_tokens", "cached_tokens",
                    "cost_usd", "model_ms", "queue_ms", "tool_ms", "overhead_ms", "context_used", "context_limit", "model_used",
                    "owner", "missed_windows", "reason", "verified", "task_id"}

EVENT_BATCH_MAX = 256


class IdempotencyConflict(ValueError):
    """A command key was previously used for a different canonical request."""


class UsageBudgetRefusal(ValueError):
    """The requested model call cannot be reserved under a configured token or currency cap."""


EVENT_FLUSH_SECONDS = 0.02


class Store:
    def __init__(self, config: hutchConfig | None = None, bus: Bus | None = None, *, maintenance: bool = False):
        self.config = config or get_config()
        self._maintenance = maintenance
        if (self.config.state_dir / '.hutch-database-snapshot').exists():
            raise RuntimeError('a database snapshot cannot be used as executor state; use hutch state restore --to a new directory')
        if not maintenance and (self.config.state_dir / '.restore-in-progress').exists():
            raise RuntimeError('this restore is incomplete; preserve the directory and restore into a new destination')
        self.config.ensure()
        self.bus = bus or Bus()
        self.hub = WakeHub(self.config.state_dir, self.bus)  # cross-process nudges (PF-5)
        self.bus.attach_hub(self.hub)
        self._listening = False
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.config.db_path, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            # Intent, permissions and budget reservations precede external
            # effects. Do not acknowledge their WAL commit before its sync.
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA busy_timeout=30000")
            self._db.execute("PRAGMA foreign_keys=ON")
            try:
                self._upgrade()
            except BaseException:
                self._db.close()
                self.hub.close()
                raise
        # ---- batched event writer (one writer thread, group commit)
        self._buf_cv = threading.Condition()
        self._pending: list[Event] = []
        self._enqueued = 0
        self._committed = 0
        self._run_status: dict[str, str] = {}
        #: optional per-run observers; recoverable file delivery has its own queue
        #: runs this process has seen reach a terminal state: a late worker's events for them are dropped (never appended)
        self._sealed: set[str] = set()
        self._inflight = 0                    # events the writer thread has taken and not yet committed
        self._sinks: dict[str, Callable[[Event], None]] = {}
        self._sink_errors: dict[str, list[str]] = {}
        self.dropped_events = 0
        self._closing = False
        self._closed = False
        self._shutdown_hooks: list[weakref.WeakMethod] = []
        self._writer = threading.Thread(target=self._writer_loop, name="hutch-event-writer", daemon=True)
        if not maintenance:
            self._writer.start()
        from .transcript_mirror import TranscriptMirror
        self._mirror = TranscriptMirror(self)
        if not maintenance:
            self._mirror.start()
        ref = weakref.ref(self)
        atexit.register(lambda: (s := ref()) and s.close())

    # ------------------------------------------------------------ migrations

    def _upgrade(self) -> None:
        db = self._db
        lock_path = self.config.db_path.with_suffix(self.config.db_path.suffix + ".migrate.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bots'").fetchone()
                if version == 0 and existing:
                    version = 1  # a v0.1 database predating versioning
                target = SCHEMA_VERSION
                if version > target:
                    raise RuntimeError(
                        f"{self.config.db_path} is schema v{version}, newer than this hutch (v{target}); "
                        "upgrade hutch instead of opening it with an older build")
                if existing and version < target:
                    backup = self.config.db_path.with_suffix(f".db.bak-v{version}")
                    if not backup.exists():
                        # SQLite's backup API captures committed WAL pages too; copying the main file can omit them.
                        temporary = backup.with_suffix(backup.suffix + ".tmp")
                        destination = sqlite3.connect(temporary)
                        try:
                            db.backup(destination)
                        finally:
                            destination.close()
                        temporary.replace(backup)
                db.execute("BEGIN EXCLUSIVE")
                try:
                    for statement in _SCHEMA.split(";"):
                        if statement.strip():
                            db.execute(statement)
                    if version == 0:
                        version = 1
                    for v in range(version, target):
                        _MIGRATIONS[v - 1](db)
                        db.execute(f"PRAGMA user_version = {v + 1}")
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def ensure_listening(self) -> None:
        """Start receiving wake-ups from other hutch processes (idempotent)."""
        if not self._listening:
            self._listening = True
            self.hub.listen()

    @property
    def schema_version(self) -> int:
        with self._lock:
            return self._db.execute("PRAGMA user_version").fetchone()[0]

    # -------------------------------------------------------- restore hold

    @staticmethod
    def _execution_hold(db: sqlite3.Connection) -> Optional[str]:
        row = db.execute("SELECT id FROM state_restores WHERE activated_at IS NULL AND superseded_by = '' LIMIT 1").fetchone()
        return row[0] if row else None

    @classmethod
    def _assert_execution_ready(cls, db: sqlite3.Connection) -> None:
        from .state_snapshot import ExecutionHeld
        if restore_id := cls._execution_hold(db):
            raise ExecutionHeld(restore_id)

    def restoration_status(self) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._db.execute("SELECT * FROM state_restores WHERE superseded_by = '' ORDER BY created_at DESC LIMIT 1").fetchone()
        if row is None:
            return None
        report = json.loads(row['report_json'])
        report.update(execution_held=row['activated_at'] is None, activated_at=row['activated_at'],
                      activation_evidence=row['activation_evidence'], verified_code_hash=row['verified_code_hash'])
        return report

    def restoration_items(self, restore_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute('SELECT kind, resource_id, prior_status FROM state_restore_items '
                                    'WHERE restore_id = ? ORDER BY kind, resource_id LIMIT ? OFFSET ?',
                                    (restore_id, max(1, min(200, limit)), max(0, offset))).fetchall()
        return [dict(row) for row in rows]

    def activate_restoration(self, restore_id: str, evidence: str) -> bool:
        """Local operator review permits NEW work; never requeue old work/grants."""
        from .state_snapshot import code_hash, validate_history
        evidence = evidence.strip()
        if not evidence or len(evidence) > 4000:
            raise ValueError('review evidence must contain 1–4000 characters')
        evidence.encode('utf-8')
        with self._tx() as db:
            row = db.execute('SELECT * FROM state_restores WHERE id = ?', (restore_id,)).fetchone()
            if row is None:
                raise KeyError(restore_id)
            if row['superseded_by']:
                raise ValueError('this restore was superseded; inspect the current restore report')
            if row['activated_at']:
                if row['activation_evidence'] != evidence:
                    raise ValueError('this restore already has a different review record')
                return False
            if row['verified_code_hash'] != code_hash():
                raise ValueError('installed executor/UI changed since restore validation; restore with this release into a new directory')
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('restored database integrity failed; preserve and inspect the copy')
            validate_history(self)
            if db.execute("SELECT 1 FROM runs WHERE status IN ('pending','running','loading_model','waiting_approval',"
                          "'waiting_human','waiting_resources','recovering','cancelling') LIMIT 1").fetchone():
                raise ValueError('unexpected runnable work appeared during restore review; preserve and inspect the copy')
            db.execute('UPDATE state_restores SET activated_at = ?, activation_evidence = ? WHERE id = ? AND activated_at IS NULL',
                       (iso(utcnow()), evidence, restore_id))
        self.bus.notify('work', 'state')
        return True

    # ---------------------------------------------------------- remote pairing

    @staticmethod
    def _secret_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def create_pairing_code(self, ttl_seconds: int = 60) -> str:
        """Create a one-use, short-lived pairing code. Only the hash reaches SQLite."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        raw = "".join(secrets.choice(alphabet) for _ in range(14))
        code = "-".join((raw[:4], raw[4:8], raw[8:12], raw[12:]))
        now = utcnow()
        with self._tx() as db:
            db.execute("DELETE FROM pairing_codes WHERE expires_at <= ? OR consumed_at IS NOT NULL", (iso(now),))
            db.execute("INSERT INTO pairing_codes(code_hash, created_at, expires_at) VALUES (?, ?, ?)",
                       (self._secret_hash(raw), iso(now), iso(now + timedelta(seconds=ttl_seconds))))
        return code

    def exchange_pairing_code(self, code: str, label: str, remote_ip: str) -> tuple[dict[str, Any] | None, str]:
        """Consume a pairing code once and mint one sliding 30-day revocable device session."""
        normalized = "".join(ch for ch in code.upper() if ch.isalnum())
        code_hash = self._secret_hash(normalized)
        now = utcnow()
        now_text = iso(now)
        token = secrets.token_urlsafe(32)
        device_id = f"dev_{uuid.uuid4().hex[:16]}"
        with self._tx() as db:
            attempt = db.execute("SELECT window_started_at, failures FROM pairing_attempts WHERE remote_ip = ?",
                                 (remote_ip,)).fetchone()
            if attempt:
                started = datetime.fromisoformat(attempt["window_started_at"])
                if (now - started).total_seconds() < 600 and attempt["failures"] >= 5:
                    return None, "rate_limited"
                if (now - started).total_seconds() >= 600:
                    db.execute("DELETE FROM pairing_attempts WHERE remote_ip = ?", (remote_ip,))
            row = db.execute("SELECT expires_at, consumed_at FROM pairing_codes WHERE code_hash = ?",
                             (code_hash,)).fetchone()
            if row is None or row["consumed_at"] is not None or row["expires_at"] <= now_text:
                db.execute("INSERT INTO pairing_attempts(remote_ip, window_started_at, failures) VALUES (?, ?, 1) "
                           "ON CONFLICT(remote_ip) DO UPDATE SET failures = failures + 1",
                           (remote_ip, now_text))
                return None, "invalid"
            db.execute("UPDATE pairing_codes SET consumed_at = ? WHERE code_hash = ? AND consumed_at IS NULL",
                       (now_text, code_hash))
            db.execute("INSERT INTO device_sessions(id, label, token_hash, created_at, expires_at, last_used_at) "
                       "VALUES (?, ?, ?, ?, ?, ?)",
                       (device_id, label.strip()[:80] or "Phone", self._secret_hash(token), now_text,
                        iso(now + timedelta(days=30)), now_text))
            db.execute("DELETE FROM pairing_attempts WHERE remote_ip = ?", (remote_ip,))
        return {"id": device_id, "label": label.strip()[:80] or "Phone", "token": token}, "ok"

    def validate_device_token(self, token: str) -> bool:
        if not token or len(token) > 256:
            return False
        now = utcnow()
        with self._tx() as db:
            row = db.execute("SELECT id, expires_at, revoked_at FROM device_sessions WHERE token_hash = ?",
                             (self._secret_hash(token),)).fetchone()
            if row is None or row["revoked_at"] is not None or row["expires_at"] <= iso(now):
                return False
            # Sliding expiry is limited to the session's existing 30-day lifetime per active use.
            db.execute("UPDATE device_sessions SET last_used_at = ?, expires_at = ? WHERE id = ?",
                       (iso(now), iso(now + timedelta(days=30)), row["id"]))
            return True

    def device_identity(self, token: str) -> Optional[str]:
        if not token or len(token) > 256:
            return None
        with self._lock:
            row = self._db.execute("SELECT id FROM device_sessions WHERE token_hash = ? AND revoked_at IS NULL "
                                   "AND expires_at > ?", (self._secret_hash(token), iso(utcnow()))).fetchone()
        return row[0] if row else None

    def list_device_sessions(self) -> list[dict[str, Any]]:
        now = iso(utcnow())
        with self._lock:
            rows = self._db.execute("SELECT id, label, created_at, expires_at, last_used_at, revoked_at "
                                    "FROM device_sessions WHERE revoked_at IS NULL AND expires_at > ? "
                                    "ORDER BY created_at DESC", (now,)).fetchall()
        return [dict(row) for row in rows]

    def revoke_device_session(self, device_id: str) -> bool:
        with self._tx() as db:
            cur = db.execute("UPDATE device_sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                             (iso(utcnow()), device_id))
        return cur.rowcount == 1

    # ----------------------------------------------------------- lifecycle

    def register_shutdown(self, callback: Callable[[], None]) -> None:
        """Register an owner that must join its workers before this Store closes the database."""
        try:
            hook = weakref.WeakMethod(callback)
        except TypeError:
            return
        self._shutdown_hooks = [h for h in self._shutdown_hooks if h() is not None]
        owner = getattr(callback, "__self__", None)
        func = getattr(callback, "__func__", None)
        if owner is not None and not any(getattr(h(), "__self__", None) is owner
                                         and getattr(h(), "__func__", None) is func for h in self._shutdown_hooks):
            self._shutdown_hooks.append(hook)

    def close(self) -> None:
        if self._closed:
            return
        if not self._closing:
            for hook in list(self._shutdown_hooks):
                owner_shutdown = hook()
                if owner_shutdown is not None:
                    owner_shutdown()
            try:
                self.flush_events()
            finally:
                with self._buf_cv:
                    self._closing = True
                    self._buf_cv.notify_all()
        if self._writer.ident is not None:
            self._writer.join(timeout=5)
        if self._writer.is_alive():
            # Do not close a connection still owned by the writer. Retain the
            # closing state (new events are refused); callers may retry closure
            # after the blocked commit exits, without rerunning owner shutdown.
            raise RuntimeError("cannot close Hutch state while the event writer is still running")
        self._mirror.close()
        self.hub.close()
        with self._lock:
            self._db.close()
            self._closed = True

    # ------------------------------------------------------------- bots

    def create_bot(self, bot: Bot) -> Bot:
        with self._lock:
            self._db.execute(
                "INSERT INTO bots (id, name, doc) VALUES (?, ?, ?)",
                (bot.id, bot.name, bot.model_dump_json()),
            )
            self._db.commit()
        self.bus.notify("work", "bots")
        return bot

    def upsert_bot(self, bot: Bot) -> Bot:
        with self._lock:
            self._db.execute(
                "INSERT INTO bots (id, name, doc) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET id=excluded.id, doc=excluded.doc",
                (bot.id, bot.name, bot.model_dump_json()),
            )
            self._db.commit()
        self.bus.notify("work", "bots")
        return bot

    def list_bots(self) -> list[Bot]:
        with self._lock:
            rows = self._db.execute("SELECT doc FROM bots ORDER BY name").fetchall()
        return [Bot.model_validate_json(r["doc"]) for r in rows]

    def get_bot(self, ref: str) -> Optional[Bot]:
        """Look up a bot by id or name."""
        with self._lock:
            row = self._db.execute(
                "SELECT doc FROM bots WHERE id = ? OR name = ?", (ref, ref)
            ).fetchone()
        return Bot.model_validate_json(row["doc"]) if row else None

    def delete_bot(self, ref: str) -> bool:
        bot = self.get_bot(ref)
        if not bot:
            return False
        with self._lock:
            self._db.execute("DELETE FROM bots WHERE id = ?", (bot.id,))
            self._db.execute("DELETE FROM tool_allows WHERE bot_id = ?", (bot.id,))
            self._db.execute("DELETE FROM memory WHERE bot_id = ?", (bot.id,))
            self._db.commit()
        self.bus.notify("work", "bots")
        return True

    # --------------------------------------------------------- transactions

    @contextlib.contextmanager
    def _tx(self):
        """One atomic write transaction. ``BEGIN IMMEDIATE`` takes the write lock up front, so a read-compare-write inside it
        cannot interleave with another process doing the same (that is what makes claims and fences real)."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.rollback()
                raise
            else:
                self._db.commit()

    @staticmethod
    def _run_json(run: Run) -> str:
        return run.model_dump_json(exclude=_RUN_COMPUTED)

    @staticmethod
    def _insert_conversation_message(db: sqlite3.Connection, *, message_id: str, conversation_id: str, seq: int,
                                    run_id: str, role: str, content: str, created_at: str) -> None:
        db.execute("INSERT INTO messages (id, conversation_id, seq, run_id, role, content, created_at) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (message_id, conversation_id, seq, run_id, role, content, created_at))
        db.execute("INSERT INTO conversation_fts (message_id, conversation_id, content) VALUES (?, ?, ?)",
                   (message_id, conversation_id, content))
        db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (created_at, conversation_id))

    @staticmethod
    def _run(row: sqlite3.Row) -> Run:
        """A Run from its row: the columns, not the JSON, are authoritative for status, fence, lease and cancel."""
        run = Run.model_validate_json(row["doc"])
        run.status = RunStatus(row["status"])
        run.fence = row["fence"]
        run.lease_owner = row["lease_owner"]
        run.lease_expires_at = row["lease_expires_at"]
        run.cancel_requested = bool(row["cancel_requested"])
        run.pgid = row["pgid"]
        run.conversation_id = row["conversation_id"]
        run.conversation_context = json.loads(row["conversation_context"] or "[]")
        return run

    # ------------------------------------------------------------ tasks

    def enqueue_task(self, task: Task) -> Task:
        with self._lock:
            self._assert_execution_ready(self._db)
            self._db.execute(
                "INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state) VALUES (?, ?, ?, ?, ?, 0, 'queued')",
                (task.id, task.bot_id, task.kind, task.prompt, task.created_at),
            )
            self._db.commit()
        self.bus.notify("work")
        return task

    def next_task(self, bot_id: str) -> Optional[Task]:
        with self._lock:
            row = self._db.execute(
                "SELECT id, bot_id, kind, prompt, created_at FROM tasks "
                "WHERE bot_id = ? AND done = 0 AND state = 'queued' ORDER BY created_at LIMIT 1",
                (bot_id,),
            ).fetchone()
        return Task(**dict(row)) if row else None

    def finish_task(self, task_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE tasks SET done = 1, state = 'done' WHERE id = ?", (task_id,))
            self._db.commit()

    def pending_tasks(self, bot_id: Optional[str] = None) -> list[Task]:
        """Tasks that have not finished (queued, or claimed by a run that is still going)."""
        q = "SELECT id, bot_id, kind, prompt, created_at FROM tasks WHERE done = 0 AND state IN ('queued', 'claimed')"
        args: tuple = ()
        if bot_id:
            q += " AND bot_id = ?"
            args = (bot_id,)
        with self._lock:
            rows = self._db.execute(q + " ORDER BY created_at", args).fetchall()
        return [Task(**dict(r)) for r in rows]

    # ------------------------------------------------------------- runs

    def create_run(self, run: Run) -> Run:
        with self._lock:
            self._assert_execution_ready(self._db)
            self._db.execute(
                "INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, conversation_context) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run.id, run.bot_id, run.task_id, self._run_json(run), run.status.value, run.created_at,
                 run.conversation_id, json.dumps(run.conversation_context, ensure_ascii=False)),
            )
            self._db.commit()
        self.bus.notify("work", "runs", f"run:{run.id}")
        return run

    def submit_run(self, run: Run, task: Task) -> Run:
        """Admit work: the task and its run are created together, linked, in ONE transaction (or not at all).

        The old path made three separate commits and marked the task done before anything had run."""
        run.task_id = task.id
        with self._tx() as db:
            self._assert_execution_ready(db)
            db.execute("INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id) "
                       "VALUES (?, ?, ?, ?, ?, 0, 'queued', ?)",
                       (task.id, task.bot_id, task.kind, task.prompt, task.created_at, run.id))
            db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, conversation_context) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (run.id, run.bot_id, task.id, self._run_json(run), run.status.value, run.created_at,
                        run.conversation_id, json.dumps(run.conversation_context, ensure_ascii=False)))
        self.bus.notify("work", "runs", f"run:{run.id}")
        return run

    @staticmethod
    def _idempotency_replay(db: sqlite3.Connection, scope: str, key: str, request_hash: str) -> Optional[dict[str, Any]]:
        row = db.execute("SELECT request_hash, response_json FROM idempotency_keys WHERE scope = ? AND key = ?",
                         (scope, key)).fetchone()
        if row is None:
            used = db.execute("SELECT scope FROM idempotency_keys WHERE key = ? LIMIT 1", (key,)).fetchone()
            if used is not None:
                raise IdempotencyConflict("Idempotency-Key was already used by a different command")
            return None
        if row["request_hash"] != request_hash:
            raise IdempotencyConflict("Idempotency-Key was already used for a different request")
        return json.loads(row["response_json"])

    def create_conversation(self, bot_id: str, title: str, *, idem_key: str, request_hash: str) -> tuple[dict[str, Any], bool]:
        """Create a conversation and record its idempotency response in the same transaction."""
        scope = f"api:v1:conversations:{bot_id}"
        now = iso(utcnow())
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        with self._tx() as db:
            replay = self._idempotency_replay(db, scope, idem_key, request_hash)
            if replay is not None:
                row = db.execute("SELECT * FROM conversations WHERE id = ?", (replay["conversation_id"],)).fetchone()
                if row is None:
                    raise RuntimeError("idempotent conversation response points to missing state")
                return dict(row), False
            if db.execute("SELECT 1 FROM bots WHERE id = ?", (bot_id,)).fetchone() is None:
                raise KeyError(bot_id)
            db.execute("INSERT INTO conversations (id, bot_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                       (conversation_id, bot_id, title.strip(), now, now))
            db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
                       (scope, idem_key, request_hash, _canonical({"conversation_id": conversation_id}), now))
            row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        self.bus.notify("conversations", f"conversation:{conversation_id}")
        return dict(row), True

    def get_conversation(self, conversation_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._db.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count, "
                "(SELECT COALESCE(MAX(m.seq), 0) FROM messages m WHERE m.conversation_id = c.id) AS last_seq, "
                "(SELECT r.run_id FROM conversation_runs r WHERE r.conversation_id = c.id "
                "ORDER BY r.attached_at DESC LIMIT 1) AS latest_run_id "
                "FROM conversations c WHERE c.id = ?", (conversation_id,)).fetchone()
            return self._with_conversation_authority(row) if row else None

    def _with_conversation_authority(self, row: sqlite3.Row) -> dict[str, Any]:
        """Choose control ownership from every attached run, independently of message pagination.

        Call with the Store lock held. Executing/waiting work precedes queued turns;
        the conversation boundary prevents another bot conversation becoming the Stop target.
        """
        from .lifecycle import LABELS
        states = tuple(sorted(status.value for status in ACTIVE_STATUSES))
        marks = ",".join("?" for _ in states)
        active = self._db.execute(
            "SELECT r.id, r.status FROM runs r JOIN conversation_runs cr ON cr.run_id = r.id "
            f"WHERE cr.conversation_id = ? AND r.status IN ({marks}) "
            "ORDER BY (r.status = 'pending'), r.created_at, r.id LIMIT 1", (row["id"], *states)).fetchone()
        return {**dict(row), "active_run_id": active["id"] if active else None,
                "active_run_status": active["status"] if active else None,
                "active_run_status_label": LABELS[RunStatus(active["status"])] if active else None}

    def conversation_last_seq(self, conversation_id: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM messages WHERE conversation_id = ?",
                                   (conversation_id,)).fetchone()
        return int(row["seq"])

    def archive_conversation(self, conversation_id: str, archived: bool, *, idem_key: str,
                             request_hash: str) -> tuple[dict[str, Any], bool]:
        scope = f"api:v1:conversation:{conversation_id}:archive"
        now = iso(utcnow())
        with self._tx() as db:
            replay = self._idempotency_replay(db, scope, idem_key, request_hash)
            if replay is not None:
                row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
                if row is None:
                    raise RuntimeError("idempotent archive response points to missing state")
                return dict(row), False
            row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                raise KeyError(conversation_id)
            db.execute("UPDATE conversations SET archived = ?, updated_at = ? WHERE id = ?",
                       (int(archived), now, conversation_id))
            db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
                       (scope, idem_key, request_hash,
                        _canonical({"conversation_id": conversation_id, "archived": archived}), now))
            result = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        self.bus.notify("conversations", f"conversation:{conversation_id}")
        return dict(result), True

    def list_conversations(self, bot_id: Optional[str] = None, *, include_legacy: bool = False,
                           limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        query = ("SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count, "
                 "(SELECT COALESCE(MAX(m.seq), 0) FROM messages m WHERE m.conversation_id = c.id) AS last_seq, "
                 "(SELECT r.run_id FROM conversation_runs r WHERE r.conversation_id = c.id "
                 "ORDER BY r.attached_at DESC LIMIT 1) AS latest_run_id "
                 "FROM conversations c WHERE c.archived = 0")
        args: list[Any] = []
        if bot_id:
            query += " AND c.bot_id = ?"
            args.append(bot_id)
        if not include_legacy:
            query += " AND c.is_legacy = 0"
        query += " ORDER BY c.updated_at DESC, c.id LIMIT ? OFFSET ?"
        args.extend((limit, offset))
        with self._lock:
            rows = self._db.execute(query, args).fetchall()
            return [self._with_conversation_authority(row) for row in rows]

    def list_conversation_messages(self, conversation_id: str, *, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM messages WHERE conversation_id = ? AND seq > ? "
                                    "ORDER BY seq LIMIT ?", (conversation_id, after, limit)).fetchall()
        return [dict(row) for row in rows]

    def search_conversation_messages(self, query: str, *, bot_id: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
        terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        if not terms:
            return []
        # Treat input as plain text, not FTS operators. Quoting terms avoids malformed MATCH syntax
        # from punctuation and keeps the query language stable for API clients.
        fts_query = " AND ".join(f'"{term}"' for term in terms)
        sql = ("SELECT m.*, c.bot_id, c.title FROM conversation_fts "
               "JOIN messages m ON m.id = conversation_fts.message_id "
               "JOIN conversations c ON c.id = m.conversation_id "
               "WHERE conversation_fts MATCH ? AND c.archived = 0 AND c.is_legacy = 0")
        args: list[Any] = [fts_query]
        if bot_id:
            sql += " AND c.bot_id = ?"
            args.append(bot_id)
        sql += " ORDER BY rank LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [dict(row) for row in rows]

    def submit_conversation_message(self, conversation_id: str, prompt: str, run: Run, task: Task, *,
                                    idem_key: str, request_hash: str, context_messages: int = 12,
                                    context_chars: int = 16_000) -> tuple[str, bool]:
        """Append a user message and admit its run atomically, with a bounded context snapshot and durable idempotency."""
        scope = f"api:v1:conversation:{conversation_id}:messages"
        now = iso(utcnow())
        with self._tx() as db:
            replay = self._idempotency_replay(db, scope, idem_key, request_hash)
            if replay is not None:
                return str(replay["run_id"]), False
            self._assert_execution_ready(db)
            conversation = db.execute("SELECT bot_id, title, archived FROM conversations WHERE id = ?",
                                      (conversation_id,)).fetchone()
            if conversation is None:
                raise KeyError(conversation_id)
            if conversation["bot_id"] != run.bot_id:
                raise PermissionError("conversation belongs to another bot")
            if conversation["archived"]:
                raise ValueError("conversation is archived")

            recent = db.execute("SELECT role, content FROM messages WHERE conversation_id = ? "
                                "ORDER BY seq DESC LIMIT ?", (conversation_id, context_messages)).fetchall()
            context: list[dict[str, str]] = []
            remaining = context_chars
            for row in reversed(recent):
                if remaining <= 0:
                    break
                content = str(row["content"])
                if len(content) > remaining:
                    marker = "[earlier text omitted]\n"
                    content = (marker + content[-(remaining - len(marker)):]) if remaining > len(marker) else content[-remaining:]
                if content:
                    context.append({"role": row["role"], "content": content})
                    remaining -= len(content)
            run.conversation_id = conversation_id
            run.conversation_context = context
            run.task_id = task.id
            seq = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?",
                             (conversation_id,)).fetchone()[0]
            message_id = f"msg_{uuid.uuid4().hex[:12]}"
            self._insert_conversation_message(db, message_id=message_id, conversation_id=conversation_id, seq=seq,
                                             run_id=run.id, role="user", content=prompt, created_at=now)
            if not conversation["title"].strip():
                title = prompt.strip().replace("\n", " ")[:72] or "Conversation"
                db.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))
            db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                       (conversation_id, run.id, now))
            db.execute("INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id) "
                       "VALUES (?, ?, ?, ?, ?, 0, 'queued', ?)",
                       (task.id, task.bot_id, task.kind, task.prompt, task.created_at, run.id))
            db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, conversation_context) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (run.id, run.bot_id, task.id, self._run_json(run), run.status.value, run.created_at,
                        conversation_id, json.dumps(context, ensure_ascii=False)))
            user_event = Event(run_id=run.id, type=EventType.message,
                               data={"role": "user", "content": prompt})
            self._insert_events(db, run.id, [user_event])
            db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
                       (scope, idem_key, request_hash, _canonical({"run_id": run.id}), now))
        self._mirror.wake.set()
        self.bus.notify("work", "runs", f"run:{run.id}", "conversations", f"conversation:{conversation_id}")
        return run.id, True

    def submit_scheduled(self, run: Run, task: Task, *, occurrence: str, expected_marker: Optional[str], new_marker: str,
                         claimed_by: str, note: Optional[dict] = None) -> Optional[Run]:
        """Claim one schedule occurrence and create its run, atomically. None means somebody else already did.

        Two schedulers (``serve`` plus ``daemon``), or a crash between "dispatch" and "mark dispatched", used to produce two runs
        for one window. Now the last-fire marker is compared and advanced, the occurrence row is inserted (unique per bot and
        window) and the run is created in a single write transaction: exactly one caller can win.
        """
        marker_key = f"schedule:{run.bot_id}:last_fire"
        run.task_id = task.id
        with self._tx() as db:
            self._assert_execution_ready(db)
            row = db.execute("SELECT value FROM kv WHERE key = ?", (marker_key,)).fetchone()
            if (row["value"] if row else None) != expected_marker:
                return None
            try:
                db.execute("INSERT INTO schedule_occurrences (bot_id, occurrence, run_id, claimed_at, claimed_by) "
                           "VALUES (?, ?, ?, ?, ?)", (run.bot_id, occurrence, run.id, iso(utcnow()), claimed_by))
            except sqlite3.IntegrityError:
                return None
            db.execute("INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id) "
                       "VALUES (?, ?, ?, ?, ?, 0, 'queued', ?)",
                       (task.id, task.bot_id, task.kind, task.prompt, task.created_at, run.id))
            db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, conversation_context) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (run.id, run.bot_id, task.id, self._run_json(run), run.status.value, run.created_at,
                        run.conversation_id, json.dumps(run.conversation_context, ensure_ascii=False)))
            db.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                       (marker_key, new_marker))
            if note is not None:
                db.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                           (f"schedule:{run.bot_id}:last_dispatch", json.dumps(note)))
        self.bus.notify("work", "runs", f"run:{run.id}")
        return run

    def claim_run(self, run_id: str, owner: str, lease_seconds: float, now: Optional[datetime] = None,
                  max_live: Optional[int] = None) -> Optional[Run]:
        """Take ownership of a queued run, atomically. Returns the claimed run (new ``fence``) or None.

        One statement decides: the run is still pending and unclaimed (or its claimant's lease lapsed), no stop was requested,
        no other run of the SAME bot is live or freshly claimed (the per-bot single-instance rule, now enforced across
        processes), and - if ``max_live`` is given - fewer than that many runs are live overall.
        """
        now = now or utcnow()
        stamp, expires = iso(now), iso(now + timedelta(seconds=lease_seconds))
        marks = ",".join("?" for _ in _LIVE_VALUES)
        # A successful claim leaves a run in `pending` while its supervisor starts the
        # worker. That reservation already consumes a global slot, even though it is not
        # yet one of the active execution statuses.
        cap = (" AND (SELECT COUNT(*) FROM runs c WHERE c.status IN (" + marks + ") OR "
               "(c.status = 'pending' AND c.lease_owner != '' AND c.lease_expires_at >= ?)) < ?") if max_live else ""
        sql = (
            "UPDATE runs SET lease_owner = ?, lease_expires_at = ?, heartbeat_at = ?, fence = fence + 1 "
            "WHERE id = ? AND status = 'pending' AND cancel_requested = 0 "
            "AND (lease_owner = '' OR lease_expires_at IS NULL OR lease_expires_at < ?) "
            "AND NOT EXISTS (SELECT 1 FROM runs o WHERE o.bot_id = runs.bot_id AND o.id != runs.id AND "
            "(o.status IN (" + marks + ") OR (o.status = 'pending' AND o.lease_owner != '' AND o.lease_expires_at >= ?)))"
            + cap)
        args: list[Any] = [owner, expires, stamp, run_id, stamp, *_LIVE_VALUES, stamp]
        if max_live:
            args += [*_LIVE_VALUES, stamp, max_live]
        with self._tx() as db:
            if self._execution_hold(db):
                return None
            if db.execute(sql, args).rowcount != 1:
                return None
            db.execute("UPDATE tasks SET state = 'claimed' WHERE run_id = ? AND done = 0", (run_id,))
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run(row)

    def renew_leases(self, owner: str, lease_seconds: float, now: Optional[datetime] = None) -> list[str]:
        """Heartbeat: extend every unfinished run this owner holds and return their ids. A run the owner lost (recovered by
        someone else while it was stalled) is simply absent from the result, which is how the owner finds out."""
        now = now or utcnow()
        marks = ",".join("?" for _ in _TERMINAL_VALUES)
        with self._lock:
            rows = self._db.execute(
                f"UPDATE runs SET lease_expires_at = ?, heartbeat_at = ? WHERE lease_owner = ? AND status NOT IN ({marks}) "
                "AND lease_expires_at >= ? RETURNING id",
                (iso(now + timedelta(seconds=lease_seconds)), iso(now), owner, *_TERMINAL_VALUES, iso(now))).fetchall()
            self._db.commit()
        return [r["id"] for r in rows]

    def release_expired_claims(self, now: Optional[datetime] = None) -> int:
        """A claim whose owner vanished before it started anything is just a queued run again: nothing happened, nothing to undo."""
        stamp = iso(now or utcnow())
        with self._tx() as db:
            ids = [r["id"] for r in db.execute(
                "SELECT id FROM runs WHERE status = 'pending' AND lease_owner != '' AND lease_expires_at < ?", (stamp,))]
            for rid in ids:
                db.execute("UPDATE runs SET lease_owner = '', lease_expires_at = NULL WHERE id = ?", (rid,))
                db.execute("UPDATE tasks SET state = 'queued' WHERE run_id = ? AND done = 0", (rid,))
        if ids:
            self.bus.notify("work")
        return len(ids)

    def expired_runs(self, now: Optional[datetime] = None) -> list[Run]:
        """Live runs whose owner stopped renewing the lease: the owner is gone."""
        marks = ",".join("?" for _ in _LIVE_VALUES)
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_RUN_COLS} FROM runs WHERE status IN ({marks}) AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                (*_LIVE_VALUES, iso(now or utcnow()))).fetchall()
        return [self._run(r) for r in rows]

    def next_lease_expiry(self, exclude_owner: str = "") -> Optional[str]:
        """The earliest lease expiry among live runs held by somebody else: when a supervisor should next look for orphans."""
        marks = ",".join("?" for _ in _LIVE_VALUES)
        with self._lock:
            row = self._db.execute(
                f"SELECT MIN(lease_expires_at) AS m FROM runs WHERE status IN ({marks}) AND lease_expires_at IS NOT NULL "
                "AND lease_owner != ?", (*_LIVE_VALUES, exclude_owner)).fetchone()
        return row["m"] if row else None

    def claim_supervisor(self, owner: str, lease_seconds: float, now: Optional[datetime] = None) -> bool:
        """Renew the current supervisor lease or atomically take it after expiry."""
        now = now or utcnow()
        stamp, expires = iso(now), iso(now + timedelta(seconds=lease_seconds))
        with self._tx() as db:
            if self._execution_hold(db):
                return False
            row = db.execute("SELECT owner, expires_at FROM supervisor_leases WHERE name = 'scheduler'").fetchone()
            if row is None:
                db.execute("INSERT INTO supervisor_leases (name, owner, expires_at, fence) VALUES ('scheduler', ?, ?, 1)",
                           (owner, expires))
                return True
            if row["owner"] == owner:
                db.execute("UPDATE supervisor_leases SET expires_at = ? WHERE name = 'scheduler' AND owner = ?",
                           (expires, owner))
                return True
            if row["expires_at"] is None or row["expires_at"] >= stamp:
                return False
            return db.execute(
                "UPDATE supervisor_leases SET owner = ?, expires_at = ?, fence = fence + 1 "
                "WHERE name = 'scheduler' AND owner = ? AND expires_at = ?",
                (owner, expires, row["owner"], row["expires_at"])).rowcount == 1

    def release_supervisor(self, owner: str) -> bool:
        with self._tx() as db:
            return db.execute("UPDATE supervisor_leases SET owner = '', expires_at = NULL "
                              "WHERE name = 'scheduler' AND owner = ?", (owner,)).rowcount == 1

    def legacy_live_runs(self) -> list[Run]:
        """Live runs from before leases existed (no lease at all): only the old process-liveness check can judge them."""
        marks = ",".join("?" for _ in _LIVE_VALUES)
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_RUN_COLS} FROM runs WHERE status IN ({marks}) AND lease_expires_at IS NULL AND fence = 0",
                _LIVE_VALUES).fetchall()
        return [self._run(r) for r in rows]

    def set_pgid(self, run_id: str, fence: int, pgid: int) -> None:
        with self._tx() as db:
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            self._check_lease(row, run_id, fence)
            if RunStatus(row["status"]) in TERMINAL:
                raise LeaseLost(run_id, "cannot change process ownership after completion")
            db.execute("UPDATE runs SET pgid = ? WHERE id = ? AND fence = ?", (pgid, run_id, fence))

    @staticmethod
    def _check_lease(row, run_id: str, fence: int) -> None:
        """Validate at the mutation transaction, including the gap before takeover.

        Fence-zero imports/fixtures have no lease. Claimed owners cannot revive an
        expired lease; recovery must acquire a new fence. Terminal no-op reads are
        checked by their callers because successful completion clears the lease.
        """
        if row is None or row["fence"] != fence:
            raise LeaseLost(run_id, "this worker no longer owns the run")
        if row["fence"] and (not row["lease_owner"] or not row["lease_expires_at"]
                             or row["lease_expires_at"] < iso(utcnow())):
            raise LeaseLost(run_id, "ownership lease expired; recovery must acquire a new fence")

    def update_run(self, run: Run) -> None:
        """Persist a run's progress.

        A run that was never claimed (fence 0: a fixture, an import, a demo) has no owner to race with and is written whole, as
        before. A claimed run is written ONLY by its owner and ONLY while it still owns it: the write carries the fence, merges
        just the progress fields (never status, which changes through ``transition_run``), and is refused once the run is
        finished. A stale writer gets ``LeaseLost`` instead of silently overwriting the outcome.
        """
        with self._tx() as db:
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run.id,)).fetchone()
            if row is None:
                return
            if row["fence"] == 0 and run.fence == 0:
                db.execute("UPDATE runs SET doc = ?, status = ? WHERE id = ? AND fence = 0",
                           (self._run_json(run), run.status.value, run.id))
            else:
                if row["fence"] != run.fence:
                    raise LeaseLost(run.id, f"fence {run.fence} is stale (current {row['fence']})")
                if RunStatus(row["status"]) in TERMINAL:
                    raise LeaseLost(run.id, f"already {row['status']}")
                self._check_lease(row, run.id, run.fence)
                patch = json.dumps(run.model_dump(include=_PROGRESS_FIELDS), default=str)
                marks = ",".join("?" for _ in _TERMINAL_VALUES)
                cur = db.execute(
                    f"UPDATE runs SET doc = json_patch(doc, ?) WHERE id = ? AND fence = ? AND status NOT IN ({marks})",
                    (patch, run.id, run.fence, *_TERMINAL_VALUES))
                if cur.rowcount != 1:
                    raise LeaseLost(run.id, "ownership changed while saving progress")
        self._notify_run(run)

    def _notify_run(self, run: Run) -> None:
        # `work` wakes the scheduler loop; only a status transition changes what it should do,
        # so per-step accounting updates must not make an idle loop spin.
        if self._run_status.get(run.id) != run.status.value:
            self._run_status[run.id] = run.status.value
            self.bus.notify("work", "runs", f"run:{run.id}")
        else:
            self.bus.notify(f"run:{run.id}")

    def transition_run(self, run_id: str, to: RunStatus, *, fence: Optional[int] = None, exit_reason: Optional[str] = None,
                       error: Optional[str] = None, event: Optional[dict[str, Any]] = None, bump_fence: bool = False,
                       fields: Optional[dict[str, Any]] = None, cancel_wins: bool = False) -> Run:
        """Move a run to ``to`` - the ONLY way status changes for a claimed run (ADR-0003).

        In one transaction: the fence is checked (``LeaseLost``), the move is checked against the lifecycle table
        (``IllegalTransition``), the status column and the document are updated, a terminal move clears the lease and settles the
        task, and the ``status`` event is written. If any part fails nothing changed. ``bump_fence`` is used by recovery so the
        previous owner can no longer write. A move to the state the run is already in is a no-op.
        """
        with self._buf_cv:                                       # lock order: event buffer, then database (as append_event)
            # A reader that sees the new status must also see every event that came before it. Wait out the writer's in-flight
            # batch, then commit this run's still-buffered events in the SAME transaction as the status change.
            while self._inflight:
                self._buf_cv.wait(timeout=0.05)
            mine = [e for e in self._pending if e.run_id == run_id]
            with self._tx() as db:
                kept = self._worker_events(db, run_id, mine)
                row, emitted = self._apply_transition(db, run_id, to, fence, exit_reason, error, event, bump_fence, fields,
                                                      earlier=kept, cancel_wins=cancel_wins)
            self.dropped_events += len(mine) - len(kept)
            if mine:
                done = {id(e) for e in mine}
                self._pending = [e for e in self._pending if id(e) not in done]
                self._committed += len(mine)                      # they are committed now; flush_events must not wait for them
                self._buf_cv.notify_all()
            for e in kept + ([emitted] if emitted is not None else []):
                self._fan_out(e)                                 # committed: now observers see them, in sequence order
        run = self._run(row)
        self._run_status[run_id] = run.status.value
        if run.status in TERMINAL:
            with self._buf_cv:
                self._sealed.add(run_id)
        if emitted is not None or run.status is to:
            self.bus.notify("work", "runs", f"run:{run_id}", "events", "usage")
        return run

    def _apply_transition(self, db: sqlite3.Connection, run_id: str, to: RunStatus, fence: Optional[int],
                          exit_reason: Optional[str], error: Optional[str], event: Optional[dict[str, Any]],
                          bump_fence: bool, fields: Optional[dict[str, Any]],
                          earlier: Optional[list[Event]] = None, cancel_wins: bool = False) -> tuple[sqlite3.Row, Optional[Event]]:
        from .models import EventType
        row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        cur = RunStatus(row["status"])
        if fence is not None and row["fence"] != fence:
            raise LeaseLost(run_id, f"fence {fence} is stale (current {row['fence']})")
        if fence is not None and cur not in TERMINAL:
            self._check_lease(row, run_id, fence)
        if cancel_wins and to in (RunStatus.failed, RunStatus.succeeded) and row["cancel_requested"]:
            to, exit_reason, error = RunStatus.stopped, "stopped", "stopped after owned processes were verified gone"
            event = {**(event or {}), "reason": "stopped", "error": error}
        if cur not in TERMINAL and to in TERMINAL:
            uncertain = db.execute("SELECT tool, summary FROM tool_actions a WHERE a.run_id = ? "
                "AND a.status IN ('started', 'unknown') AND NOT EXISTS "
                "(SELECT 1 FROM action_reconciliations x WHERE x.action_id = a.id) ORDER BY started_at LIMIT 3",
                (run_id,)).fetchall()
            if uncertain:
                # Receipt loss is authoritative even if the runtime reported
                # success. Seal receipts and status/events in this transaction.
                if to is not RunStatus.outcome_unknown:
                    exit_reason = "action_receipt_missing"
                to = RunStatus.outcome_unknown
                note = "Action outcome needs review; do not replay: " + "; ".join(r["summary"] or r["tool"] for r in uncertain)
                error = ((error + "\n") if error else "") + note
                event = {**(event or {}), "reason": exit_reason, "error": error}
                db.execute("UPDATE tool_actions SET status = 'unknown' WHERE run_id = ? AND status = 'started'", (run_id,))
        if not allowed(cur, to) and cur is not to:
            raise IllegalTransition(run_id, cur, to)
        if cur is to:
            if cur in TERMINAL and earlier:
                raise LeaseLost(run_id, "terminal runs refuse buffered late events")
            if earlier:              # nothing to change, but the buffered events still commit
                self._insert_events(db, run_id, list(earlier))
            return row, None
        doc = json.loads(row["doc"])
        patch: dict[str, Any] = {"status": to.value, **(fields or {})}
        terminal = to in TERMINAL
        if terminal:
            patch["finished_at"] = iso(utcnow())
            patch["exit_reason"] = exit_reason if exit_reason is not None else ""
            patch["error"] = (error or "")[:2_000]
        elif exit_reason is not None:
            patch["exit_reason"] = exit_reason
        sets, args = "status = ?, doc = json_patch(doc, ?), fence = ?", [to.value, json.dumps(patch, default=str),
                                                                        row["fence"] + (1 if bump_fence else 0)]
        if terminal:
            sets += ", lease_owner = '', lease_expires_at = NULL, sealed = 1"
        db.execute(f"UPDATE runs SET {sets} WHERE id = ?", (*args, run_id))
        if terminal:
            # A crash can leave a reservation between admission and usage settlement. With no live caller to
            # verify the outcome, keep it held until an operator reconciles the provider record.
            db.execute("UPDATE usage_reservations SET status = 'uncertain', reason = "
                       "CASE WHEN reason = '' THEN 'run ended before provider usage was settled' ELSE reason END "
                       "WHERE run_id = ? AND status = 'reserved'", (run_id,))
            task_state = {RunStatus.succeeded: "done", RunStatus.skipped: "cancelled",
                          RunStatus.stopped: "cancelled"}.get(to, "failed")
            db.execute("UPDATE tasks SET state = ?, done = 1 WHERE run_id = ? OR id = ?",
                       (task_state, run_id, doc.get("task_id")))
        emitted: Optional[Event] = None
        if event is not None:
            data = {"status": to.value, **event}
            emitted = Event(run_id=run_id, ts=iso(utcnow()), type=EventType.status, data=data)
        if earlier or emitted is not None:        # buffered events first (they precede it), then the status event, one commit
            self._insert_events(db, run_id, list(earlier or []) + ([emitted] if emitted is not None else []))
        return db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone(), emitted

    def set_status(self, run: Run, to: RunStatus, *, event: Optional[dict[str, Any]] = None,
                   fields: Optional[dict[str, Any]] = None) -> bool:
        """Move the run object you hold to ``to`` through the lifecycle, updating it in place.

        Returns False if the move is not allowed from where the run now is (typically: a stop was requested and the run is
        'cancelling'); the object is refreshed to the stored status so the caller sees the truth. ``LeaseLost`` (the run was
        taken from this owner) propagates: the caller must stop."""
        try:
            fresh = self.transition_run(run.id, to, fence=run.fence, event=event, fields=fields)
        except IllegalTransition:
            cur = self.get_run(run.id)
            if cur is not None:
                run.status = cur.status
            return False
        run.status = fresh.status
        return True

    def request_cancel(self, run_id: str, *, idem_key: Optional[str] = None,
                       request_hash: Optional[str] = None) -> Optional[Run]:
        """Record that a person wants this run stopped. ANY process may call this; the owner (or recovery) acts on it.

        A queued run nobody owns is ended here. A claimed or live run moves to ``cancelling`` and stays there until the
        owner has verified everything it started is gone. (The old Stop flipped an in-memory flag and only worked in the
        process that owned the run.)
        """
        with self._tx() as db:
            scope = f"api:v1:run:{run_id}:stop"
            replay = None
            if idem_key is not None:
                if request_hash is None:
                    raise ValueError("request_hash is required with an idempotency key")
                replay = self._idempotency_replay(db, scope, idem_key, request_hash)
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            if replay is None:
                if RunStatus(row["status"]) not in TERMINAL:
                    db.execute("UPDATE runs SET cancel_requested = 1 WHERE id = ?", (run_id,))
                    patch = _canonical({"status": "expired", "resolved_at": iso(utcnow()), "decided_by": "stopped"})
                    db.execute("UPDATE approvals SET status = 'expired', doc = json_patch(doc, ?) "
                               "WHERE run_id = ? AND status = 'pending'", (patch, run_id))
                if idem_key is not None:
                    db.execute("INSERT INTO idempotency_keys(scope, key, request_hash, response_json, created_at) "
                               "VALUES (?, ?, ?, ?, ?)",
                               (scope, idem_key, request_hash, _canonical({"run_id": run_id}), iso(utcnow())))
            elif RunStatus(row["status"]) in TERMINAL:
                return self._run(row)
        run = self.get_run(run_id)
        assert run is not None
        try:
            if run.status is RunStatus.pending and not run.lease_owner:
                run = self.transition_run(run_id, RunStatus.stopped, exit_reason="stopped before start",
                                          error="stopped before it started", event={"reason": "stopped before start"})
            elif run.status is not RunStatus.cancelling:
                run = self.transition_run(run_id, RunStatus.cancelling, event={"reason": "stop requested"})
        except (IllegalTransition, LeaseLost):
            run = self.get_run(run_id) or run                     # finished in the meantime: nothing to stop
        self.bus.notify(f"approval:wake:{run_id}", f"human:{run_id}", f"run:{run_id}", "approvals", "work")
        return run

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            row = self._db.execute("SELECT cancel_requested FROM runs WHERE id = ?", (run_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    def get_run(self, run_id: str) -> Optional[Run]:
        with self._lock:
            row = self._db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run(row) if row else None

    def list_runs(self, bot_id: Optional[str] = None, limit: int = 50) -> list[Run]:
        q = f"SELECT {_RUN_COLS} FROM runs"
        args: tuple = ()
        if bot_id:
            q += " WHERE bot_id = ?"
            args = (bot_id,)
        q += " ORDER BY created_at DESC LIMIT ?"
        args = args + (limit,)
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [self._run(r) for r in rows]

    def list_runs_page(self, bot_id: Optional[str] = None, status: Optional[str] = None,
                       limit: int = 50, offset: int = 0) -> list[Run]:
        """Filtered, paginated run listing for the Runs page."""
        q, args = f"SELECT {_RUN_COLS} FROM runs WHERE 1=1", []
        if bot_id:
            q += " AND bot_id = ?"
            args.append(bot_id)
        if status == "active":
            q += f" AND status IN ({','.join('?' for _ in ACTIVE_STATUSES)})"
            args += [st.value for st in ACTIVE_STATUSES]
        elif status:
            q += " AND status = ?"
            args.append(status)
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [self._run(r) for r in rows]

    def latest_finished_run(self, bot_id: str) -> Optional[Run]:
        marks = ",".join("?" for _ in _TERMINAL_VALUES)
        with self._lock:
            row = self._db.execute(
                f"SELECT {_RUN_COLS} FROM runs WHERE bot_id = ? AND status IN ({marks}) AND status != 'skipped' "
                "ORDER BY created_at DESC LIMIT 1", (bot_id, *_TERMINAL_VALUES)).fetchone()
        return self._run(row) if row else None

    def active_runs(self) -> list[Run]:
        live = tuple(st.value for st in ACTIVE_STATUSES)
        marks = ",".join("?" for _ in live)
        with self._lock:
            rows = self._db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE status IN ({marks})", live).fetchall()
        return [self._run(r) for r in rows]

    def active_run_for_bot(self, bot_id: str) -> Optional[Run]:
        runs = [r for r in self.active_runs() if r.bot_id == bot_id]
        # A queued turn must not hide work already executing or waiting for a human.
        return min(runs, key=lambda r: (r.status is RunStatus.pending, r.created_at, r.id)) if runs else None

    def last_successful_run(self, bot_id: str) -> Optional[Run]:
        with self._lock:
            row = self._db.execute(
                f"SELECT {_RUN_COLS} FROM runs WHERE bot_id = ? AND status = ? ORDER BY created_at DESC LIMIT 1",
                (bot_id, RunStatus.succeeded.value),
            ).fetchone()
        return self._run(row) if row else None

    # --------------------------------------------------- processes a run started

    def add_proc(self, run_id: str, pid: int, pgid: int, starttime: int, kind: str = "tool", boot_id: str = "") -> None:
        """Remember a process a run started, with its identity, so ending the run (or recovering a crashed owner) can end it."""
        with self._lock:
            self._db.execute("INSERT INTO run_procs (run_id, pid, pgid, starttime, kind, started_at, boot_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (run_id, pid, pgid, starttime, kind, iso(utcnow()), boot_id))
            self._db.commit()

    def end_proc(self, run_id: str, pid: int) -> None:
        with self._lock:
            self._db.execute("UPDATE run_procs SET ended_at = ? WHERE run_id = ? AND pid = ? AND ended_at IS NULL AND detached_at IS NULL",
                             (iso(utcnow()), run_id, pid))
            self._db.commit()

    def live_procs(self, run_id: str) -> list[dict[str, Any]]:
        """Processes recorded for the run that were never recorded as finished."""
        with self._lock:
            rows = self._db.execute("SELECT pid, pgid, starttime, kind, boot_id FROM run_procs WHERE run_id = ? "
                                    "AND ended_at IS NULL AND detached_at IS NULL",
                                    (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def claim_recovery(self, run: Run, owner: str, lease_seconds: float, *, owner_exited: bool = False,
                       now: Optional[datetime] = None) -> Optional[Run]:
        """Atomically take and fence an expired run before recovery touches any process it started.

        The snapshot fields prevent two recoverers from acting on one lease. ``owner_exited`` is reserved for the supervisor
        that has just reaped its own worker process; all other callers must observe an expired lease.
        """
        from .models import EventType
        now = now or utcnow()
        stamp, expires = iso(now), iso(now + timedelta(seconds=lease_seconds))
        with self._tx() as db:
            if self._execution_hold(db):
                return None
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run.id,)).fetchone()
            if row is None or row["fence"] != run.fence or row["status"] != run.status.value:
                return None
            if row["lease_owner"] != run.lease_owner or row["lease_expires_at"] != run.lease_expires_at:
                return None
            is_legacy = row["lease_expires_at"] is None and row["fence"] == 0
            expired = row["lease_expires_at"] is not None and row["lease_expires_at"] < stamp
            exited_owner = owner_exited and (row["lease_owner"] == owner
                                              or row["lease_owner"] == f"cleanup-pending:{run.id}")
            if not (expired or exited_owner or (is_legacy and owner_exited)):
                return None
            cur = RunStatus(row["status"])
            target = RunStatus.cancelling if cur is RunStatus.cancelling else RunStatus.recovering
            if target is not cur and not allowed(cur, target):
                return None
            reason = "cleanup in progress" if target is RunStatus.cancelling else "recovering interrupted execution"
            patch = json.dumps({"status": target.value, "reason": reason}, ensure_ascii=False)
            updated = db.execute(
                "UPDATE runs SET status = ?, doc = json_patch(doc, ?), fence = fence + 1, lease_owner = ?, "
                "lease_expires_at = ?, heartbeat_at = ? WHERE id = ? AND fence = ? AND status = ? "
                "AND lease_owner = ? AND lease_expires_at IS ?",
                (target.value, patch, owner, expires, stamp, run.id, run.fence, run.status.value,
                 run.lease_owner, run.lease_expires_at))
            if updated.rowcount != 1:
                return None
            event = Event(run_id=run.id, type=EventType.status,
                          data={"status": target.value, "reason": reason, "recovered_by": owner})
            self._insert_events(db, run.id, [event])
            fresh = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run.id,)).fetchone()
        self._fan_out(event)
        self.bus.notify("work", "runs", f"run:{run.id}", "events")
        return self._run(fresh)

    def defer_recovery(self, run: Run, reason: str, retry_after: float = 1.0) -> bool:
        """Keep cleanup visible and relinquish its lease briefly so another supervisor can retry it."""
        now = utcnow()
        with self._tx() as db:
            row = db.execute("SELECT fence, status FROM runs WHERE id = ?", (run.id,)).fetchone()
            if row is None or row["fence"] != run.fence or row["status"] not in ("recovering", "cancelling"):
                return False
            patch = json.dumps({"reason": reason[:500]}, ensure_ascii=False)
            cur = db.execute(
                "UPDATE runs SET doc = json_patch(doc, ?), lease_owner = ?, lease_expires_at = ?, heartbeat_at = ? "
                "WHERE id = ? AND fence = ? AND status IN ('recovering','cancelling')",
                (patch, f"cleanup-pending:{run.id}", iso(now + timedelta(seconds=retry_after)), iso(now), run.id, run.fence))
            return cur.rowcount == 1

    def close_procs(self, run_id: str, keep_pid: Optional[int] = None) -> None:
        with self._lock:
            if keep_pid is None:
                self._db.execute("UPDATE run_procs SET ended_at = ? WHERE run_id = ? AND ended_at IS NULL AND detached_at IS NULL",
                                 (iso(utcnow()), run_id))
            else:
                self._db.execute("UPDATE run_procs SET ended_at = ? WHERE run_id = ? AND ended_at IS NULL AND detached_at IS NULL AND pid != ?",
                                 (iso(utcnow()), run_id, keep_pid))
            self._db.commit()

    # ----------------------------------------------------- tool actions (receipts)

    def begin_action(self, run_id: str, tool: str, idem_key: str, effect: str, summary: str = "",
                     fence: Optional[int] = None, *, arguments: Optional[dict] = None,
                     authority: Optional[dict] = None, scope: Optional[dict] = None) -> str:
        """Commit immutable effect intent before authorization to act; claimed runs require their fence."""
        from .models import new_id
        if any(value is not None and not isinstance(value, dict) for value in (arguments, authority, scope)):
            raise ValueError("action arguments, authority and scope must be JSON objects")
        arguments, authority, scope = (action_receipts.freeze(value) if value is not None else None
                                       for value in (arguments, authority, scope))
        action_id = new_id("act")
        with self._tx() as db:
            row = db.execute(f"SELECT bot_id, {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            self._action_owner(row, run_id, fence)
            if row["fence"] > 0 and arguments is None:
                raise ValueError("owned actions require immutable arguments")
            st = RunStatus(row["status"])
            if st in TERMINAL | {RunStatus.cancelling, RunStatus.recovering} or row["cancel_requested"]:
                raise LeaseLost(run_id, f"the run is {st.value}; no new action may start")
            if authority and authority.get("approval_id"):
                approval = db.execute("SELECT doc, status, action_hash, expires_at FROM approvals WHERE id = ?",
                                      (authority["approval_id"],)).fetchone()
                if (approval is None or approval["status"] != "approved"
                        or approval["action_hash"] != authority.get("action_hash")
                        or not approval["expires_at"] or approval["expires_at"] <= iso(utcnow())):
                    raise action_receipts.ActionConflict("reviewed permission is missing, changed or expired; request a new review")
                req = json.loads(approval["doc"])
                if req["run_id"] != run_id or req["bot_id"] != row["bot_id"]:
                    raise action_receipts.ActionConflict("reviewed permission belongs to another run")
                if action_receipts.canonical(req["detail"]) != action_receipts.canonical(authority.get("detail")):
                    raise action_receipts.ActionConflict("reviewed arguments changed; request a new review")
            # Conservative across attempts: a process command may affect a remote
            # service even if its workspace changed. File destinations are scoped.
            repeat_scope = {"bot_id": row["bot_id"]}
            if effect == "fs":
                repeat_scope["workspace"] = (scope or {}).get("workspace", "")
            effect_key = action_receipts.digest(action_receipts.canonical(
                {"tool": tool, "effect": effect, "arguments": arguments, "scope": repeat_scope})) if arguments is not None else ""
            if row["conversation_id"]:
                previous = db.execute("SELECT a.id FROM tool_actions a JOIN runs r ON r.id = a.run_id "
                    "WHERE r.conversation_id = ? AND r.sealed = 1 AND a.status IN ('started', 'unknown') "
                    "AND (a.effect_key = ? OR a.effect_key = '') AND NOT EXISTS "
                    "(SELECT 1 FROM action_reconciliations x WHERE x.action_id = a.id) LIMIT 1",
                    (row["conversation_id"], effect_key)).fetchone()
                if previous:
                    raise action_receipts.ActionConflict(
                        f"unreconciled action {previous[0]} may already have happened; record its outcome before repeating")
            intent = {"schema": 1, "run_id": run_id, "bot_id": row["bot_id"], "fence": row["fence"],
                      "tool": tool, "effect": effect, "arguments": arguments, "authority": authority,
                      "scope": scope, "effect_key": effect_key}
            raw = action_receipts.canonical(intent)
            if len(raw.encode()) > action_receipts.MAX_INTENT_BYTES:
                raise ValueError("action intent exceeds 4 MiB; reduce the requested arguments")
            db.execute("INSERT INTO tool_actions "
                "(id, run_id, tool, idem_key, effect, summary, status, started_at, intent_json, intent_hash, effect_key, legacy) "
                "VALUES (?, ?, ?, ?, ?, ?, 'started', ?, ?, ?, ?, ?)",
                (action_id, run_id, tool, idem_key, effect, summary[:500], iso(utcnow()), raw,
                 action_receipts.digest(raw), effect_key, int(arguments is None)))
        return action_id

    @staticmethod
    def _action_owner(row, run_id, fence):
        if row is None:
            raise KeyError(run_id)
        if row["fence"] > 0 and fence is None:
            raise LeaseLost(run_id, "the current worker fence is required for an action write")
        if fence is not None:
            Store._check_lease(row, run_id, fence)

    def finish_action(self, action_id: str, status: str, result_digest: str = "", *,
                      expected_fence: Optional[int] = None) -> None:
        if status not in ("done", "failed"):
            raise ValueError("a worker receipt must report done or failed")
        with self._tx() as db:
            action = db.execute("SELECT run_id, status FROM tool_actions WHERE id = ?", (action_id,)).fetchone()
            if action is None:
                raise KeyError(action_id)
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (action["run_id"],)).fetchone()
            self._action_owner(row, action["run_id"], expected_fence)
            if RunStatus(row["status"]) in TERMINAL or action["status"] != "started":
                raise LeaseLost(action["run_id"], "receipt is sealed or uncertain; reconcile instead of overwriting it")
            db.execute("UPDATE tool_actions SET status = ?, finished_at = ?, result_digest = ? WHERE id = ? AND status = 'started'",
                       (status, iso(utcnow()), result_digest[:128], action_id))

    def actions_in_doubt(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT a.id, a.tool, a.effect, a.summary, a.started_at, a.idem_key FROM tool_actions a "
                "WHERE a.run_id = ? AND a.status IN ('started', 'unknown') AND NOT EXISTS "
                "(SELECT 1 FROM action_reconciliations x WHERE x.action_id = a.id) ORDER BY a.started_at", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def mark_actions_unknown(self, run_id: str, *, expected_fence: Optional[int] = None) -> int:
        with self._tx() as db:
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            self._action_owner(row, run_id, expected_fence)
            if RunStatus(row["status"]) in TERMINAL:
                raise LeaseLost(run_id, "terminal action receipts are sealed; reconcile instead")
            cur = db.execute("UPDATE tool_actions SET status = 'unknown' WHERE run_id = ? AND status = 'started'", (run_id,))
        return cur.rowcount

    @staticmethod
    def _action_view(db, row):
        result = action_receipts.view(row)
        bot = db.execute("SELECT COALESCE(b.name, d.bot_name, r.bot_id) FROM runs r LEFT JOIN bots b ON b.id=r.bot_id "
                         "LEFT JOIN transcript_delivery d ON d.run_id=r.id WHERE r.id=?", (row['run_id'],)).fetchone()
        result['bot_name'] = bot[0] if bot else ''
        reconciliation = db.execute("SELECT * FROM action_reconciliations WHERE action_id = ?", (row["id"],)).fetchone()
        result["reconciliation"] = dict(reconciliation) if reconciliation else None
        return result

    def get_action(self, action_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._db.execute("SELECT * FROM tool_actions WHERE id = ?", (action_id,)).fetchone()
            return self._action_view(self._db, row) if row else None

    def list_actions(self, run_id: Optional[str] = None, *, unresolved: bool = False, reviewed: bool = False,
                     limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        # Lists carry summaries; immutable arguments are fetched one action at
        # a time, avoiding hundreds of MiB for a page of large file intents.
        query = ("SELECT a.id, a.run_id, a.tool, a.idem_key, a.effect, a.summary, a.status, a.started_at, "
                 "a.finished_at, a.result_digest, a.intent_hash, a.legacy, "
                 "(SELECT COALESCE(b.name,d.bot_name,r.bot_id) FROM runs r LEFT JOIN bots b ON b.id=r.bot_id "
                 "LEFT JOIN transcript_delivery d ON d.run_id=r.id WHERE r.id=a.run_id) AS bot_name "
                 "FROM tool_actions a WHERE 1 = 1")
        args = []
        if run_id is not None:
            query += " AND a.run_id = ?"; args.append(run_id)
        if unresolved:
            query += (" AND a.status IN ('started', 'unknown') AND EXISTS (SELECT 1 FROM runs r "
                      "WHERE r.id = a.run_id AND r.sealed = 1) AND NOT EXISTS "
                      "(SELECT 1 FROM action_reconciliations x WHERE x.action_id = a.id)")
        if reviewed:
            query += " AND EXISTS (SELECT 1 FROM action_reconciliations x WHERE x.action_id = a.id)"
        query += " ORDER BY a.started_at, a.id LIMIT ? OFFSET ?"
        args.extend((max(1, min(limit, 200)), max(0, offset)))
        with self._lock:
            rows = self._db.execute(query, args).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["legacy"] = bool(item["legacy"])
                reconciliation = self._db.execute("SELECT * FROM action_reconciliations WHERE action_id = ?", (row["id"],)).fetchone()
                item["reconciliation"] = dict(reconciliation) if reconciliation else None
                results.append(item)
            return results

    def count_unresolved_actions(self, run_id: Optional[str] = None) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM tool_actions a JOIN runs r ON r.id = a.run_id "
                "WHERE (? IS NULL OR a.run_id = ?) AND r.sealed = 1 AND a.status IN ('started', 'unknown') AND NOT EXISTS "
                "(SELECT 1 FROM action_reconciliations x WHERE x.action_id = a.id)", (run_id, run_id)).fetchone()[0]

    def action_context(self, run_id: str) -> str:
        """Read current, bounded receipt authority at execution, even for previously queued turns.

        Only identifiers/tools and recorded outcomes enter model context. Raw
        arguments, destinations and operator evidence remain in the review UI.
        This guidance supplements the actual repeat guard; it grants nothing.
        """
        with self._lock:
            rows = self._db.execute("SELECT a.id, a.tool, x.outcome FROM tool_actions a JOIN runs r ON r.id = a.run_id "
                "LEFT JOIN action_reconciliations x ON x.action_id = a.id "
                "WHERE r.conversation_id = (SELECT conversation_id FROM runs WHERE id = ?) "
                "AND r.sealed = 1 AND a.status IN ('started', 'unknown') ORDER BY a.started_at DESC LIMIT 20",
                (run_id,)).fetchall()
        if not rows:
            return ""
        entries = [{"id": row["id"], "tool": row["tool"][:80], "operator_outcome": row["outcome"] or "unresolved"}
                   for row in rows]
        # At most ten records fit the guidance window. Query newest first;
        # history may contain more and must be inspected before repeating.
        while len(action_receipts.canonical(entries)) > 2000:
            entries.pop()
        return ("\nAction receipt review in this conversation (bounded newest records; consult history for more): "
                + action_receipts.canonical(entries) + "\nUnresolved effects may already have happened. Do not replay them. "
                "Operator outcomes are human reports, not independent verification or permission to repeat an action.")

    def reconcile_action(self, action_id: str, *, intent_hash: str, outcome: str, evidence: str,
                         by: str, idem_key: str, request_hash: str) -> tuple[dict, bool]:
        evidence = evidence.strip()
        evidence.encode('utf-8')
        if outcome not in ("confirmed_done", "confirmed_failed", "not_applied") or not 1 <= len(evidence) <= 4000:
            raise ValueError("select an observed outcome and provide 1–4000 characters of verification evidence")
        scope = f"api:v1:action:{action_id}:reconcile"
        with self._tx() as db:
            replay = self._idempotency_replay(db, scope, idem_key, request_hash)
            row = db.execute("SELECT * FROM tool_actions WHERE id = ?", (action_id,)).fetchone()
            if row is None:
                raise KeyError(action_id)
            action = self._action_view(db, row)
            if replay is not None:
                return action, False
            if not action["intent_valid"] or intent_hash != row["intent_hash"]:
                raise action_receipts.ActionConflict("action details changed or failed integrity verification; review again")
            if action["reconciliation"]:
                raise action_receipts.ActionConflict("another client already recorded this action's outcome")
            run = db.execute("SELECT sealed FROM runs WHERE id = ?", (row["run_id"],)).fetchone()
            if not run or not run["sealed"] or row["status"] not in ("started", "unknown"):
                raise action_receipts.ActionConflict("only an uncertain action from ended execution can be reconciled")
            now = iso(utcnow())
            db.execute("INSERT INTO action_reconciliations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (action_id, row["run_id"], intent_hash, outcome, evidence, by[:128], now))
            db.execute("INSERT INTO idempotency_keys(scope, key, request_hash, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (scope, idem_key, request_hash, _canonical({"action_id": action_id}), now))
            action = self._action_view(db, row)
        self.bus.notify("actions", f"run:{row['run_id']}")
        return action, True

    # ----------------------------------------------------------- events

    def append_event(self, event: Event) -> Event:
        """Queue an event; the single writer commits in batches. Returns immediately, so the agent loop never waits on a disk commit.

        ``seq`` and the chain ``hash`` are NOT assigned here: they are assigned at commit time, inside the write transaction, from
        the tail the DATABASE holds. Several processes append to one run's transcript (the worker, the dashboard recording a stop,
        a supervisor recovering it); a per-process counter would give them colliding numbers and a broken chain. Reads call
        ``flush_events`` first, so every reader still sees its own writes."""
        with self._buf_cv:
            if self._maintenance:
                raise RuntimeError('maintenance stores do not queue background events')
            if self._closing:
                raise RuntimeError("Hutch state is closing; new events are refused")
            if event.run_id in self._sealed:
                return event                  # the run is over: a worker that outlived it cannot extend the transcript
            self._pending.append(event)
            self._enqueued += 1
            self._buf_cv.notify_all()
        return event

    def attach_sink(self, run_id: str, sink: Callable[[Event], None]) -> None:
        """Receive every event of ``run_id`` in sequence order, once committed (with its ``seq`` and ``hash``)."""
        self._sinks[run_id] = sink

    def sink_errors(self, run_id: str) -> list[str]:
        return list(self._sink_errors.get(run_id, []))

    def detach_sink(self, run_id: str) -> list[str]:
        """Stop observing; returns the errors the sink raised (an unwritable transcript is reported, not swallowed)."""
        self._sinks.pop(run_id, None)
        return self._sink_errors.pop(run_id, [])

    def _fan_out(self, event: Event) -> None:
        sink = self._sinks.get(event.run_id)
        if sink is not None:
            try:
                sink(event)
            except Exception as exc:
                self._sink_errors.setdefault(event.run_id, []).append(f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _insert_events(db: sqlite3.Connection, run_id: str, events: list[Event]) -> None:
        """Give ``events`` the next sequence numbers and chain hashes of this run's transcript and insert them. Must run inside
        the write transaction: the tail it reads cannot change before the commit."""
        row = db.execute("SELECT seq, hash FROM events WHERE run_id = ? ORDER BY seq DESC LIMIT 1", (run_id,)).fetchone()
        seq, prev = (row["seq"], row["hash"] or GENESIS) if row else (0, GENESIS)
        rows = []
        for e in events:
            seq += 1
            data_json = _canonical(e.data)
            e.seq, e.hash = seq, chain_hash(prev, run_id, seq, e.ts, e.type.value, data_json)
            prev = e.hash
            rows.append((run_id, seq, e.hash, e.ts, e.type.value, data_json))
        db.executemany("INSERT INTO events (run_id, seq, hash, ts, type, data) VALUES (?, ?, ?, ?, ?, ?)", rows)
        # Every event insertion path projects canonical replies in the same transaction.
        # Terminal transitions drain the buffer here rather than through _commit_batch;
        # projecting only in that writer lost replies when completion won the race.
        replies = [e for e in events if e.type is EventType.message and e.data.get("role") == "assistant"
                   and isinstance(e.data.get("content"), str) and e.data["content"]]
        if replies:
            run = db.execute("SELECT conversation_id FROM runs WHERE id = ?", (run_id,)).fetchone()
            conversation_id = run["conversation_id"] if run is not None else ""
            if conversation_id:
                next_seq = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?",
                                      (conversation_id,)).fetchone()[0]
                for offset, e in enumerate(replies):
                    Store._insert_conversation_message(
                        db, message_id=f"msg_{uuid.uuid4().hex[:12]}", conversation_id=conversation_id,
                        seq=next_seq + offset, run_id=run_id, role="assistant", content=e.data["content"], created_at=e.ts)

    def _writer_loop(self) -> None:
        while True:
            with self._buf_cv:
                while not self._pending and not self._closing:
                    self._buf_cv.wait()
                if not self._pending and self._closing:
                    return
                # Notifications announce more rows; they must not prematurely
                # end accumulation and turn FULL synchronization into one fsync
                # per event. Commit at the size threshold or bounded deadline.
                until = time.monotonic() + EVENT_FLUSH_SECONDS
                while len(self._pending) < EVENT_BATCH_MAX and not self._closing:
                    remaining = until - time.monotonic()
                    if remaining <= 0:
                        break
                    self._buf_cv.wait(timeout=remaining)
                if not self._pending:
                    continue  # a status transition drained the buffer while we waited
                batch, self._pending = self._pending, []
                self._inflight = len(batch)
            kept: list[Event] = []
            try:
                kept = self._commit_batch(batch)
            finally:
                with self._buf_cv:
                    self._committed += len(batch)
                    self._inflight = 0
                    self._buf_cv.notify_all()
            self.bus.notify(*{f"run:{e.run_id}" for e in kept}, "events")

    def _commit_batch(self, batch: list[Event]) -> list[Event]:
        """Commit a batch: per run, assign sequence and hash from the database tail, in one transaction. Events for a run that a
        transition already ended (a zombie worker's late writes, possibly from another process) are dropped here, at the
        database, and counted. Returns the events that were stored."""
        by_run: dict[str, list[Event]] = {}
        for e in batch:
            by_run.setdefault(e.run_id, []).append(e)
        last: Optional[Exception] = None
        for attempt in range(5):
            try:
                stored: list[Event] = []
                dropped = 0
                with self._tx() as db:
                    for run_id, evs in by_run.items():
                        row = db.execute("SELECT sealed FROM runs WHERE id = ?", (run_id,)).fetchone()
                        if row is not None and row["sealed"]:
                            dropped += len(evs)
                            continue
                        kept = self._worker_events(db, run_id, evs)
                        dropped += len(evs) - len(kept)
                        self._insert_events(db, run_id, kept)
                        stored += kept
                self.dropped_events += dropped
                for e in stored:                      # committed: observers see them in sequence order
                    self._fan_out(e)
                return stored
            except sqlite3.OperationalError as exc:  # another process held the write lock past busy_timeout
                last = exc
                time.sleep(0.05 * (attempt + 1))
        # Not silent and not lost if it can be avoided: put them back for the next cycle, up to a bound.
        import sys
        with self._buf_cv:
            if len(self._pending) + len(batch) <= 10_000:
                self._pending = batch + self._pending
                self._enqueued += 0
                self._committed -= len(batch)         # they are not committed after all
                print(f"hutch: {len(batch)} events could not be written ({last}); retrying", file=sys.stderr)
                return []
        self.dropped_events += len(batch)
        print(f"hutch: DROPPED {len(batch)} events after repeated DB errors: {last}", file=sys.stderr)
        return []

    @staticmethod
    def _worker_events(db: sqlite3.Connection, run_id: str, events: list[Event]) -> list[Event]:
        """Check worker authority when committing, including buffered messages.

        Client/supervisor events have no owner fence. Worker events retain their
        claimed fence in memory; a stale batch cannot extend transcript or history.
        """
        if not any(e.owner_fence is not None for e in events):
            return events
        row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
        kept = []
        for event in events:
            if event.owner_fence is not None:
                try:
                    Store._check_lease(row, run_id, event.owner_fence)
                    if RunStatus(row["status"]) in TERMINAL:
                        continue
                except LeaseLost:
                    continue
            kept.append(event)
        return kept

    def flush_events(self, timeout: float = 10.0) -> None:
        """Block until every event appended so far is committed."""
        deadline = time.monotonic() + timeout
        with self._buf_cv:
            target = self._enqueued
            while self._committed < target and self._writer.is_alive():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise RuntimeError("canonical events remain uncommitted; event flush timed out")
                self._buf_cv.wait(timeout=min(left, 0.1))
            if self._committed < target:
                raise RuntimeError("canonical events remain uncommitted; event writer is not running")

    def flush_transcripts(self, timeout: float = 10.0) -> None:
        """Await file delivery explicitly; canonical state does not wait for filesystem IO."""
        self.flush_events()
        self._mirror.flush(timeout)

    def list_events(self, run_id: str, after_seq: int = 0, limit: Optional[int] = None, after_id: Optional[int] = None) -> list[Event]:
        """Events with ``seq > after_seq`` (or ``id > after_id``) in order (the SSE resume query)."""
        self.flush_events()
        if after_id is not None:
            q = ("SELECT id, run_id, seq, hash, ts, type, data FROM events "
                 "WHERE run_id = ? AND id > ? ORDER BY seq, id")
            args: tuple = (run_id, after_id)
        else:
            q = ("SELECT id, run_id, seq, hash, ts, type, data FROM events "
                 "WHERE run_id = ? AND seq > ? ORDER BY seq")
            args = (run_id, after_seq)
        if limit:
            q += " LIMIT ?"
            args += (limit,)
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [self._event(r) for r in rows]

    def events_before(self, run_id: str, before_seq: int, limit: int = 200) -> list[Event]:
        """The page of events immediately older than ``before_seq`` (for 'load earlier')."""
        self.flush_events()
        with self._lock:
            rows = self._db.execute(
                "SELECT id, run_id, seq, hash, ts, type, data FROM events "
                "WHERE run_id = ? AND seq < ? ORDER BY seq DESC LIMIT ?",
                (run_id, before_seq, limit),
            ).fetchall()
        return [self._event(r) for r in reversed(rows)]

    def tail_events(self, run_id: str, limit: int = 200) -> list[Event]:
        """The newest ``limit`` events, oldest first — the default run-page window (PF-9)."""
        return self.events_before(run_id, before_seq=2**62, limit=limit)

    def last_seq(self, run_id: str) -> int:
        self.flush_events()
        with self._lock:
            row = self._db.execute("SELECT MAX(seq) AS m FROM events WHERE run_id = ?", (run_id,)).fetchone()
        return row["m"] or 0

    def count_events(self, run_id: str) -> int:
        return self.last_seq(run_id)

    def global_event_bounds(self) -> tuple[int, int]:
        """Return the oldest and newest globally ordered event IDs retained in SQLite."""
        self.flush_events()
        with self._lock:
            row = self._db.execute("SELECT MIN(id) AS first, MAX(id) AS last FROM events").fetchone()
        return int(row["first"] or 0), int(row["last"] or 0)

    def list_global_events(self, after_id: int = 0, limit: int = 200) -> list[Event]:
        """Read a bounded global event page in committed insertion order."""
        self.flush_events()
        limit = max(1, min(int(limit), 500))
        with self._lock:
            rows = self._db.execute(
                "SELECT id, run_id, seq, hash, ts, type, data FROM events WHERE id > ? ORDER BY id LIMIT ?",
                (max(0, int(after_id)), limit)).fetchall()
        return [self._event(r) for r in rows]

    def reconciliation_snapshot(self, limit: int = 200) -> dict[str, Any]:
        """Read a bounded, consistent resource snapshot and its event high-water mark.

        The caller resumes event replay *after* the returned cursor. The read transaction pins a SQLite snapshot; events
        committed after its high-water mark are replayed, so changes during reconciliation are not lost.
        """
        limit = max(1, min(int(limit), 500))
        self.flush_events()
        with self._lock:
            self._db.execute("BEGIN")
            try:
                cursor = int(self._db.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0])
                change_epoch, change_tail = durable_changes.bounds(self._db)
                bot_rows = self._db.execute("SELECT doc FROM bots ORDER BY name LIMIT ?", (limit + 1,)).fetchall()
                bot_total = int(self._db.execute("SELECT COUNT(*) FROM bots").fetchone()[0])
                run_rows = self._db.execute(
                    f"SELECT {_RUN_COLS} FROM runs ORDER BY created_at DESC, id LIMIT ?", (limit + 1,)).fetchall()
                run_total = int(self._db.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
                approval_rows = self._db.execute(
                    "SELECT doc FROM approvals WHERE status = ? ORDER BY created_at, id LIMIT ?",
                    (ApprovalStatus.pending.value, limit + 1)).fetchall()
                approval_total = int(self._db.execute(
                    "SELECT COUNT(*) FROM approvals WHERE status = ?", (ApprovalStatus.pending.value,)).fetchone()[0])
                conv_rows = self._db.execute(
                    "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count, "
                    "(SELECT COALESCE(MAX(m.seq), 0) FROM messages m WHERE m.conversation_id = c.id) AS last_seq, "
                    "(SELECT r.run_id FROM conversation_runs r WHERE r.conversation_id = c.id "
                    "ORDER BY r.attached_at DESC LIMIT 1) AS latest_run_id "
                    "FROM conversations c WHERE c.archived = 0 ORDER BY c.updated_at DESC, c.id LIMIT ?",
                    (limit + 1,)).fetchall()
                conv_total = int(self._db.execute(
                    "SELECT COUNT(*) FROM conversations WHERE archived = 0").fetchone()[0])
                conversations = [self._with_conversation_authority(row) for row in conv_rows[:limit]]
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise

        bots = [Bot.model_validate_json(row["doc"]) for row in bot_rows[:limit]]
        runs = [self._run(row) for row in run_rows[:limit]]
        approvals = [ApprovalRequest.model_validate_json(row["doc"]) for row in approval_rows[:limit]]
        totals = {"bots": bot_total, "runs": run_total, "approvals": approval_total, "conversations": conv_total}
        items = {"bots": bots, "runs": runs, "approvals": approvals, "conversations": conversations}
        return {"event_cursor": cursor, "change_cursor": f"{change_epoch}:{change_tail}",
                "limit": limit, "items": items, "totals": totals,
                "truncated": {name: total > limit for name, total in totals.items()}}

    def list_resource_changes(self, cursor: str | None = None, limit: int = 200) -> dict[str, Any]:
        """Replay content-free invalidations in one read snapshot, across process restarts.

        Polling this durable outbox does not depend on a post-commit bus notification.
        Transcript delivery and external notifications are separate consumers.
        """
        self.flush_events()
        with self._lock:
            self._db.execute("BEGIN")
            try:
                page = durable_changes.read(self._db, cursor, limit)
                self._db.commit()
                return page
            except BaseException:
                self._db.rollback()
                raise

    @staticmethod
    def _event(r: sqlite3.Row) -> Event:
        return Event(id=r["id"], run_id=r["run_id"], seq=r["seq"], hash=r["hash"], ts=r["ts"],
                     type=EventType(r["type"]), data=json.loads(r["data"]))

    def verify_chain(self, run_id: str) -> dict[str, Any]:
        """Recompute a run's hash chain. Events from before chaining existed are reported, not failed."""
        self.flush_events()
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, hash, ts, type, data FROM events WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        prev, checked, legacy = GENESIS, 0, 0
        for r in rows:
            if not r["hash"]:
                legacy += 1
                continue
            expect = chain_hash(prev, run_id, r["seq"], r["ts"], r["type"], r["data"])
            if expect != r["hash"]:
                return {"ok": False, "bad_seq": r["seq"], "checked": checked, "legacy": legacy,
                        "total": len(rows)}
            prev, checked = r["hash"], checked + 1
        gaps = [i for i, r in enumerate(rows, start=1) if r["seq"] != i]
        return {"ok": not gaps, "bad_seq": rows[gaps[0]]["seq"] if gaps else None,
                "checked": checked, "legacy": legacy, "total": len(rows)}

    # -------------------------------------------------------- approvals

    def create_approval(self, req: ApprovalRequest, *, expected_fence: Optional[int] = None,
                        begin_wait: bool = False) -> ApprovalRequest:
        """Admit a request and, for worker gates, its authoritative wait in one transaction.

        Plain imports/fixtures can retain their supplied state. Worker gates set begin_wait;
        an observer of the new request cannot see the run still computing.
        """
        with self._buf_cv:
            while self._inflight:
                self._buf_cv.wait(timeout=0.05)
            mine = [event for event in self._pending if event.run_id == req.run_id] if begin_wait else []
            kept, emitted, request_event = [], None, None
            waiting = False
            with self._tx() as db:
                row = db.execute(f"SELECT bot_id, {_RUN_COLS} FROM runs WHERE id = ?", (req.run_id,)).fetchone()
                if row is None:
                    raise KeyError(req.run_id)
                if row["bot_id"] != req.bot_id:
                    raise ValueError("approval must belong to the run's bot")
                if expected_fence is not None and row["fence"] != expected_fence:
                    raise LeaseLost(req.run_id, "cannot request approval with stale ownership")
                if expected_fence is not None and RunStatus(row["status"]) not in TERMINAL:
                    self._check_lease(row, req.run_id, expected_fence)
                elif begin_wait and int(row["fence"]) > 0 and expected_fence is None:
                    raise LeaseLost(req.run_id, "a worker fence is required to admit an approval wait")
                if req.status is ApprovalStatus.pending and (
                        row["cancel_requested"] or RunStatus(row["status"]) in TERMINAL | {RunStatus.cancelling, RunStatus.recovering}):
                    req.status, req.resolved_at, req.decided_by = ApprovalStatus.expired, iso(utcnow()), "stopped"
                db.execute(
                    "INSERT INTO approvals (id, run_id, bot_id, status, created_at, doc, action_hash, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (req.id, req.run_id, req.bot_id, req.status.value, req.created_at, req.model_dump_json(),
                     req.action_hash, req.expires_at))
                if begin_wait and req.status is ApprovalStatus.pending:
                    kept = self._worker_events(db, req.run_id, mine)
                    row, emitted = self._apply_transition(db, req.run_id, RunStatus.waiting_approval,
                        expected_fence, None, None, {"approval_id": req.id}, False, None, earlier=kept)
                    request_event = Event(run_id=req.run_id, type=EventType.approval_request,
                        data={"approval_id": req.id, "tool": req.tool, "action": req.action,
                              "rule": req.rule, "risk": req.risk, "outward": req.outward,
                              "expires_at": req.expires_at, "detail": req.detail,
                              "segments": req.segments, "sticky_key": req.sticky_key,
                              "plan_id": req.plan_id, "action_hash": req.action_hash,
                              "conversation_id": row["conversation_id"]})
                    self._insert_events(db, req.run_id, [request_event])
                    waiting = True
            if waiting:
                self._run_status[req.run_id] = RunStatus.waiting_approval.value
                self.dropped_events += len(mine) - len(kept)
                done = {id(event) for event in mine}
                self._pending = [event for event in self._pending if id(event) not in done]
                self._committed += len(mine)
                self._buf_cv.notify_all()
                for event in kept + ([emitted] if emitted is not None else []) + [request_event]:
                    self._fan_out(event)
        self.bus.notify("approvals", "work", f"run:{req.run_id}")
        return req

    def update_approval(self, req: ApprovalRequest) -> None:
        raise ValueError("approval arguments are immutable; create a new request or use decide_approval to resolve once")

    def decide_approval(self, approval_id: str, status: ApprovalStatus, by: str, *, expected_hash: Optional[str] = None,
                        now: Optional[datetime] = None, sticky: bool = False, idem_key: Optional[str] = None,
                        request_hash: Optional[str] = None) -> tuple[Optional[ApprovalRequest], str]:
        """Atomically move a PENDING approval to a decision. Returns ``(request, outcome)``.

        outcome is ``won`` (this call decided it), ``already`` (somebody else did: the request shows who and what),
        ``expired`` (its deadline passed, so it is recorded as expired and cannot be approved), ``mismatch`` (the caller was
        shown a different action than the one stored) or ``missing``. One conditional UPDATE decides, so two clients, a client
        and the timeout, or two processes can never both win; the old read-then-write let both succeed.
        """
        now = now or utcnow()
        with self._tx() as db:
            scope = f"api:v1:approval:{approval_id}:resolve"
            if idem_key is not None:
                if request_hash is None:
                    raise ValueError("request_hash is required with an idempotency key")
                replay = self._idempotency_replay(db, scope, idem_key, request_hash)
                if replay is not None:
                    row = db.execute("SELECT doc, status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
                    if row is None:
                        return None, "missing"
                    req = ApprovalRequest.model_validate_json(row["doc"])
                    req.status = ApprovalStatus(row["status"])
                    return req, "replayed" if replay.get("outcome") == "won" else f"replayed_{replay.get('outcome')}"
            row = db.execute("SELECT doc, status, action_hash, expires_at FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if row is None:
                return None, "missing"
            req = ApprovalRequest.model_validate_json(row["doc"])
            req.status = ApprovalStatus(row["status"])
            if req.status is not ApprovalStatus.pending:
                return req, "already"
            if expected_hash and row["action_hash"] and expected_hash != row["action_hash"]:
                return req, "mismatch"
            outcome = "won"
            run = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (req.run_id,)).fetchone()
            if run is not None and (run["cancel_requested"] or RunStatus(run["status"]) in
                    TERMINAL | {RunStatus.cancelling, RunStatus.recovering}):
                status, by, outcome = ApprovalStatus.expired, "stopped", "expired"
            elif run is not None and int(run["fence"]) > 0 and (
                    not run["lease_owner"] or not run["lease_expires_at"] or run["lease_expires_at"] < iso(now)):
                status, by, outcome = ApprovalStatus.expired, "owner_expired", "expired"
            elif status is ApprovalStatus.approved and row["expires_at"] and row["expires_at"] <= iso(now):
                status, by, outcome = ApprovalStatus.expired, "timeout", "expired"      # silence is never consent: too late
            patch = {"status": status.value, "resolved_at": iso(now), "decided_by": by}
            cur = db.execute("UPDATE approvals SET status = ?, doc = json_patch(doc, ?) WHERE id = ? AND status = 'pending'",
                             (status.value, json.dumps(patch), approval_id))
            if cur.rowcount != 1:
                return self.get_approval(approval_id), "already"
            req.status, req.resolved_at, req.decided_by = status, patch["resolved_at"], by
            if status is ApprovalStatus.approved and sticky and req.sticky_key and not req.outward:
                db.execute("INSERT OR REPLACE INTO tool_allows(bot_id, sticky_key, created_at) VALUES (?, ?, ?)",
                           (req.bot_id, req.sticky_key, iso(now)))
            if idem_key is not None:
                db.execute("INSERT INTO idempotency_keys(scope, key, request_hash, response_json, created_at) "
                           "VALUES (?, ?, ?, ?, ?)",
                           (scope, idem_key, request_hash,
                            _canonical({"approval_id": approval_id, "outcome": outcome}), iso(now)))
        self.bus.notify("approvals", "work", f"approval:{approval_id}", f"run:{req.run_id}")
        return req, outcome

    def approval_states_for_events(self, run_id: str, events: list[Event]) -> dict[str, Any]:
        """Canonical decisions for review events, even if the worker never emitted its response.

        Scope lookup to this run; bounded chunks also support explicit full-history reads.
        Arguments remain in the immutable request/event, not duplicated in this summary.
        """
        ids = list({str(e.data["approval_id"]) for e in events if e.type is EventType.approval_request
                    and e.data.get("approval_id")})
        states = {}
        with self._lock:
            for offset in range(0, len(ids), 200):
                part = ids[offset:offset + 200]
                marks = ",".join("?" for _ in part)
                rows = self._db.execute(f"SELECT id, status, json_extract(doc, '$.decided_by') AS decided_by, "
                    f"json_extract(doc, '$.resolved_at') AS resolved_at FROM approvals "
                    f"WHERE run_id = ? AND id IN ({marks})", (run_id, *part)).fetchall()
                states.update({row["id"]: {"result": row["status"], "by": row["decided_by"],
                                           "resolved_at": row["resolved_at"]} for row in rows})
        return states

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            row = self._db.execute("SELECT doc FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return ApprovalRequest.model_validate_json(row["doc"]) if row else None

    def recent_approvals(self, limit: int = 10, offset: int = 0) -> list[ApprovalRequest]:
        """Most recently decided approvals, newest first (the inbox's 'recently decided' list)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT doc FROM approvals WHERE status != ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (ApprovalStatus.pending.value, max(1, limit), max(0, offset))).fetchall()
        return [ApprovalRequest.model_validate_json(r["doc"]) for r in rows]

    def pending_approvals(self, bot_id: Optional[str] = None, limit: Optional[int] = None,
                          offset: int = 0) -> list[ApprovalRequest]:
        q = "SELECT doc FROM approvals WHERE status = ?"
        args: tuple = (ApprovalStatus.pending.value,)
        if bot_id:
            q += " AND bot_id = ?"
            args = args + (bot_id,)
        with self._lock:
            query = q + " ORDER BY created_at, id"
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                args += (max(1, limit), max(0, offset))
            rows = self._db.execute(query, args).fetchall()
        return [ApprovalRequest.model_validate_json(r["doc"]) for r in rows]

    # ----------------------------------------------------- sticky allows

    def allow_sticky(self, bot_id: str, sticky_key: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO tool_allows (bot_id, sticky_key, created_at) VALUES (?, ?, ?)",
                (bot_id, sticky_key, iso(utcnow())),
            )
            self._db.commit()

    def is_sticky_allowed(self, bot_id: str, sticky_key: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM tool_allows WHERE bot_id = ? AND sticky_key = ?",
                (bot_id, sticky_key),
            ).fetchone()
        return row is not None

    def list_sticky_allows(self, bot_id: str) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT sticky_key FROM tool_allows WHERE bot_id = ? ORDER BY created_at", (bot_id,)
            ).fetchall()
        return [r["sticky_key"] for r in rows]

    def revoke_sticky(self, bot_id: str, sticky_key: str) -> None:
        with self._lock:
            self._db.execute(
                "DELETE FROM tool_allows WHERE bot_id = ? AND sticky_key = ?", (bot_id, sticky_key)
            )
            self._db.commit()

    # ------------------------------------------------------------ memory

    def remember(self, bot_id: str, key: str, value: str, run_id: str = "", source: str = "bot") -> None:
        """Upsert a memory fact; ``run_id`` records which run wrote it (UI-10 provenance)."""
        with self._lock:
            self._db.execute(
                "INSERT INTO memory (bot_id, key, value, updated_at, run_id, source) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(bot_id, key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at, run_id = excluded.run_id, source = excluded.source",
                (bot_id, key, value, iso(utcnow()), run_id, source),
            )
            self._db.commit()
        self.bus.notify("memory")

    def recall_all(self, bot_id: str) -> list[MemoryItem]:
        with self._lock:
            rows = self._db.execute(
                "SELECT key, value, updated_at, run_id, source FROM memory WHERE bot_id = ? ORDER BY key",
                (bot_id,),
            ).fetchall()
        return [MemoryItem(**dict(r)) for r in rows]

    def forget(self, bot_id: str, key: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM memory WHERE bot_id = ? AND key = ?", (bot_id, key))
            self._db.commit()
        self.bus.notify("memory")
        return cur.rowcount > 0

    # ------------------------------------------------------------ usage

    def _runs_today(self, bot_id: Optional[str] = None, now: Optional[datetime] = None) -> list[Run]:
        start, end = local_day_bounds(now)
        sql, args = f"SELECT {_RUN_COLS} FROM runs WHERE created_at >= ? AND created_at < ?", [start, end]
        if bot_id is not None:
            sql, args = sql + " AND bot_id = ?", args + [bot_id]
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [self._run(r) for r in rows]

    def tokens_today(self, bot_id: str, now: Optional[datetime] = None) -> int:
        """Tokens used by this bot's runs started during the current local day (the daily token cap)."""
        return sum(r.tokens for r in self._runs_today(bot_id, now))

    def cost_today(self, bot_id: Optional[str] = None, now: Optional[datetime] = None) -> float:
        """Hosted spend for the current local day, for one bot or for all (the daily cost cap)."""
        return sum(r.cost_usd for r in self._runs_today(bot_id, now))

    def bot_budget_today(self, bot_id: str, now: Optional[datetime] = None) -> tuple[int, int, float, float]:
        """Measured tokens/cost and held token/cost estimates for a bot's local day."""
        start, end = local_day_bounds(now)
        with self._lock:
            measured = self._db.execute(
                "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS tokens, "
                "COALESCE(SUM(cost_usd), 0) AS cost FROM usage WHERE bot_id = ? AND ts >= ? AND ts < ?",
                (bot_id, start, end)).fetchone()
            held = self._db.execute(
                "SELECT COALESCE(SUM(reserved_tokens), 0) AS tokens, COALESCE(SUM(reserved_cost_usd), 0) AS cost "
                "FROM usage_reservations WHERE bot_id = ? "
                "AND status IN ('reserved', 'uncertain')", (bot_id,)).fetchone()
        # Older releases also wrote per-run totals. Taking the larger value preserves those totals without counting
        # the same calls twice when both representations exist.
        measured_tokens = max(int(measured["tokens"]), self.tokens_today(bot_id, now))
        measured_cost = max(float(measured["cost"]), self.cost_today(bot_id, now))
        return measured_tokens, int(held["tokens"]), measured_cost, float(held["cost"])

    def run_reserved_usage(self, run_id: str) -> tuple[int, float]:
        with self._lock:
            row = self._db.execute(
                "SELECT COALESCE(SUM(reserved_tokens), 0) AS tokens, COALESCE(SUM(reserved_cost_usd), 0) AS cost "
                "FROM usage_reservations WHERE run_id = ? AND status IN ('reserved', 'uncertain')", (run_id,)).fetchone()
        return int(row["tokens"]), float(row["cost"])

    def bot_stats(self) -> dict[str, dict[str, Any]]:
        """Per-bot aggregates for the dashboard: run counts + staleness."""
        bots = self.list_bots()
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            for bot in bots:
                counts: dict[str, int] = {}
                for row in self._db.execute(
                    "SELECT status, COUNT(*) AS n FROM runs WHERE bot_id = ? GROUP BY status", (bot.id,)
                ):
                    counts[row["status"]] = row["n"]
                out[bot.id] = {"counts": counts}
        return out

    # -------------------------------------------------------------- usage

    def reserve_usage(self, *, run_id: str, bot_id: str, provider: str, account_id: str, model: str,
                      reserved_tokens: int, reserved_cost_usd: float, daily_token_cap: int = 0,
                      max_run_cost_usd: float = 0.0, daily_bot_cost_cap_usd: float = 0.0,
                      daily_account_cost_cap_usd: float = 0.0,
                      account_quotas: list[tuple[int, float]] | None = None,
                      expected_fence: Optional[int] = None) -> str:
        """Atomically reserve estimated tokens and worst-case cost before a provider call.

        Reservations in `reserved` or `uncertain` state continue to consume caps. Only exact usage settlement or an
        operator's explicit reconciliation releases the reservation.
        """
        from math import isfinite
        from .models import new_id
        reserved_tokens = int(reserved_tokens)
        if reserved_tokens < 0:
            raise ValueError("reserved tokens must be non-negative")
        reserved_cost_usd = float(reserved_cost_usd)
        if not isfinite(reserved_cost_usd) or reserved_cost_usd < 0:
            raise ValueError("reserved cost must be finite and non-negative")
        caps = (max_run_cost_usd, daily_bot_cost_cap_usd, daily_account_cost_cap_usd)
        if any(not isfinite(float(cap)) or float(cap) < 0 for cap in caps):
            raise ValueError("currency caps must be finite and non-negative")
        daily_token_cap = int(daily_token_cap)
        if daily_token_cap < 0:
            raise ValueError("daily token cap must be non-negative")
        for quota_tokens, seconds in account_quotas or []:
            if int(quota_tokens) < 0 or not isfinite(float(seconds)) or float(seconds) <= 0:
                raise ValueError("account quota windows require non-negative tokens and positive finite seconds")
        now = utcnow()
        now_text = iso(now)
        day_start, day_end = local_day_bounds(now)
        active = ("reserved", "uncertain")
        reservation_id = new_id("rsv")

        with self._tx() as db:
            def totals(query: str, args: tuple) -> tuple[float, int]:
                row = db.execute(query, args).fetchone()
                return float(row["cost"] or 0.0), int(row["tokens"] or 0)

            run_doc_row = db.execute(f"SELECT bot_id, {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run_doc_row is None or run_doc_row["bot_id"] != bot_id:
                raise ValueError("usage reservation must refer to an existing run owned by this bot")
            if RunStatus(run_doc_row["status"]) in TERMINAL:
                raise LeaseLost(run_id, f"cannot reserve usage for a terminal {run_doc_row['status']} run")
            if expected_fence is not None and int(run_doc_row["fence"]) != expected_fence:
                raise LeaseLost(run_id, f"fence {expected_fence} is stale (current {run_doc_row['fence']})")
            if expected_fence is not None:
                self._check_lease(run_doc_row, run_id, expected_fence)
            elif int(run_doc_row["fence"]) > 0:
                raise LeaseLost(run_id, "a worker fence is required for usage reservations")
            if run_doc_row["cancel_requested"] or RunStatus(run_doc_row["status"]) in (RunStatus.cancelling, RunStatus.recovering):
                raise LeaseLost(run_id, "the run is stopping or recovering; no new provider call may start")
            legacy_run = json.loads(run_doc_row["doc"])
            ledger_run_cost, _ = totals(
                "SELECT SUM(cost_usd) AS cost, SUM(prompt_tokens + completion_tokens) AS tokens "
                "FROM usage WHERE run_id = ?", (run_id,))
            # Pre-v10 usage is represented only by the persisted Run document. Use the larger representation so
            # migrated totals still protect run limits without double-counting calls already in the usage ledger.
            spent = max(ledger_run_cost, float(legacy_run.get("cost_usd", 0) or 0))
            held, _ = totals("SELECT SUM(reserved_cost_usd) AS cost, SUM(reserved_tokens) AS tokens "
                             "FROM usage_reservations WHERE run_id = ? AND status IN (?, ?)",
                             (run_id, *active))
            if max_run_cost_usd and spent + held + reserved_cost_usd > max_run_cost_usd + 1e-9:
                raise UsageBudgetRefusal(
                    f"the next call could pass this run's ${max_run_cost_usd:.2f} cap; "
                    f"${spent + held:.4f} is spent or reserved")

            bot_ledger_spent, bot_ledger_tokens = totals(
                "SELECT SUM(cost_usd) AS cost, SUM(prompt_tokens + completion_tokens) AS tokens FROM usage "
                "WHERE bot_id = ? AND ts >= ? AND ts < ?", (bot_id, day_start, day_end))
            legacy_bot_rows = db.execute("SELECT doc FROM runs WHERE bot_id = ? AND created_at >= ? AND created_at < ?",
                                         (bot_id, day_start, day_end)).fetchall()
            legacy_bot_spent = 0.0
            legacy_bot_tokens = 0
            for legacy_row in legacy_bot_rows:
                doc = json.loads(legacy_row["doc"])
                legacy_bot_spent += float(doc.get("cost_usd", 0) or 0)
                legacy_bot_tokens += int(doc.get("tokens", 0) or 0)
            bot_spent = max(bot_ledger_spent, legacy_bot_spent)
            bot_tokens = max(bot_ledger_tokens, legacy_bot_tokens)
            bot_held, bot_held_tokens = totals(
                "SELECT SUM(reserved_cost_usd) AS cost, SUM(reserved_tokens) AS tokens FROM usage_reservations "
                "WHERE bot_id = ? AND status IN (?, ?)", (bot_id, *active))
            if daily_token_cap and bot_tokens + bot_held_tokens + reserved_tokens > daily_token_cap:
                raise UsageBudgetRefusal(
                    f"the next call could pass this bot's estimated {daily_token_cap:,}-token daily cap; "
                    f"{bot_tokens + bot_held_tokens:,} tokens are used or reserved")
            if daily_bot_cost_cap_usd and bot_spent + bot_held + reserved_cost_usd > daily_bot_cost_cap_usd + 1e-9:
                raise UsageBudgetRefusal(
                    f"the next call could pass this bot's ${daily_bot_cost_cap_usd:.2f} daily cap; "
                    f"${bot_spent + bot_held:.4f} is spent or reserved")

            account_spent, account_tokens = totals(
                "SELECT SUM(cost_usd) AS cost, SUM(prompt_tokens + completion_tokens) AS tokens FROM usage "
                "WHERE account_id = ? AND ts >= ? AND ts < ?", (account_id, day_start, day_end))
            account_held, account_held_tokens = totals(
                "SELECT SUM(reserved_cost_usd) AS cost, SUM(reserved_tokens) AS tokens FROM usage_reservations "
                "WHERE account_id = ? AND status IN (?, ?)", (account_id, *active))
            if daily_account_cost_cap_usd and account_spent + account_held + reserved_cost_usd > daily_account_cost_cap_usd + 1e-9:
                raise UsageBudgetRefusal(
                    f"the next call could pass billing account '{account_id}'s "
                    f"${daily_account_cost_cap_usd:.2f} daily cap; ${account_spent + account_held:.4f} is spent or reserved")

            for quota_tokens, seconds in account_quotas or []:
                since = iso(now - timedelta(seconds=max(0.0, float(seconds))))
                used = int(db.execute(
                    "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) FROM usage "
                    "WHERE account_id = ? AND ts >= ?", (account_id, since)).fetchone()[0])
                reserved = int(db.execute(
                    "SELECT COALESCE(SUM(reserved_tokens), 0) FROM usage_reservations "
                    "WHERE account_id = ? AND status IN (?, ?)", (account_id, *active)).fetchone()[0])
                if used + reserved + reserved_tokens > quota_tokens:
                    raise UsageBudgetRefusal(
                        f"the next call could pass billing account '{account_id}'s {quota_tokens:,}-token allowance; "
                        f"{used + reserved:,} tokens are used or reserved in its rolling window")

            db.execute("INSERT INTO usage_reservations (id, run_id, bot_id, provider, account_id, model, "
                       "reserved_tokens, reserved_cost_usd, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?)",
                       (reservation_id, run_id, bot_id, provider, account_id, model, reserved_tokens,
                        reserved_cost_usd, now_text))
        self.bus.notify("usage")
        return reservation_id

    def _usage_authority(self, db: sqlite3.Connection, run_id: str, bot_id: Optional[str],
                         expected_fence: Optional[int], *, required: bool = True) -> None:
        row = db.execute(f"SELECT bot_id, {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            if not required and expected_fence is None:
                return  # compatibility import/diagnostic accounting, not worker settlement
            raise ValueError("usage must refer to an existing run")
        if bot_id is not None and row["bot_id"] != bot_id:
            raise ValueError("usage must belong to the run's bot")
        if RunStatus(row["status"]) in TERMINAL:
            raise LeaseLost(run_id, "terminal runs refuse worker usage mutations; reconcile the billing record")
        if int(row["fence"]) > 0 and expected_fence is None:
            raise LeaseLost(run_id, "a worker fence is required for usage mutations")
        if expected_fence is not None:
            self._check_lease(row, run_id, expected_fence)

    def mark_usage_uncertain(self, reservation_id: str, reason: str, *, expected_fence: Optional[int] = None) -> bool:
        with self._tx() as db:
            row = db.execute("SELECT run_id, bot_id FROM usage_reservations WHERE id = ?", (reservation_id,)).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            self._usage_authority(db, row["run_id"], row["bot_id"], expected_fence)
            cur = db.execute("UPDATE usage_reservations SET status = 'uncertain', reason = ? "
                             "WHERE id = ? AND status = 'reserved'", (reason[:500], reservation_id))
        self.bus.notify("usage")
        return cur.rowcount == 1

    def release_usage_reservation(self, reservation_id: str, reason: str, *, expected_fence: Optional[int] = None) -> bool:
        """Release only when the caller knows the provider call never started."""
        if not reason.strip():
            raise ValueError("a reason is required")
        with self._tx() as db:
            row = db.execute("SELECT run_id, bot_id FROM usage_reservations WHERE id = ?", (reservation_id,)).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            self._usage_authority(db, row["run_id"], row["bot_id"], expected_fence)
            cur = db.execute("UPDATE usage_reservations SET status = 'released', resolved_at = ?, reason = ? "
                             "WHERE id = ? AND status = 'reserved'",
                             (iso(utcnow()), reason[:500], reservation_id))
        self.bus.notify("usage")
        return cur.rowcount == 1

    def unresolved_usage_reservations(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, run_id, bot_id, provider, account_id, model, reserved_tokens, reserved_cost_usd, "
                "status, created_at, reason FROM usage_reservations WHERE status IN ('reserved', 'uncertain') "
                "ORDER BY created_at LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        return [dict(row) for row in rows]

    def resolve_usage_reservation(self, reservation_id: str, *, not_charged: bool = False,
                                  prompt_tokens: Optional[int] = None, completion_tokens: Optional[int] = None,
                                  cached_tokens: int = 0, actual_cost_usd: Optional[float] = None,
                                  reason: str = "") -> str:
        """Reconcile a stranded reservation after its run is terminal and the billing record was checked."""
        from math import isfinite
        now_text = iso(utcnow())
        with self._tx() as db:
            row = db.execute("SELECT * FROM usage_reservations WHERE id = ?", (reservation_id,)).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            if row["status"] not in ("reserved", "uncertain"):
                if row["status"] == "released" and not_charged:
                    return "released"
                if row["status"] == "settled" and not not_charged:
                    same = (prompt_tokens == row["actual_prompt_tokens"]
                            and completion_tokens == row["actual_completion_tokens"]
                            and cached_tokens == row["actual_cached_tokens"]
                            and actual_cost_usd is not None
                            and abs(float(actual_cost_usd) - float(row["actual_cost_usd"] or 0.0)) < 1e-12)
                    if same:
                        return "settled"
                raise ValueError("this reservation was already reconciled with a different outcome")
            run = db.execute("SELECT status FROM runs WHERE id = ?", (row["run_id"],)).fetchone()
            if run is None:
                raise ValueError("the reservation's run no longer exists; preserve its receipt for manual review")
            if RunStatus(run["status"]) in ACTIVE_STATUSES:
                raise ValueError("the run is still active; reconcile this reservation after it finishes")
            if not reason.strip():
                raise ValueError("a reconciliation reason is required")
            if not_charged:
                db.execute("UPDATE usage_reservations SET status = 'released', resolved_at = ?, reason = ? WHERE id = ?",
                           (now_text, reason[:500], reservation_id))
                result = "released"
            else:
                if prompt_tokens is None or completion_tokens is None or actual_cost_usd is None:
                    raise ValueError("charged usage requires prompt tokens, completion tokens and actual cost")
                prompt_tokens, completion_tokens, cached_tokens = map(int, (prompt_tokens, completion_tokens, cached_tokens))
                actual_cost_usd = float(actual_cost_usd)
                if min(prompt_tokens, completion_tokens, cached_tokens) < 0 or not isfinite(actual_cost_usd) or actual_cost_usd < 0:
                    raise ValueError("actual usage must be finite and non-negative")
                db.execute("INSERT INTO usage (ts, run_id, bot_id, provider, model, prompt_tokens, completion_tokens, "
                           "cached_tokens, cost_usd, kind, account_id, reservation_id) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'reconciled', ?, ?)",
                           (now_text, row["run_id"], row["bot_id"], row["provider"], row["model"], prompt_tokens,
                            completion_tokens, cached_tokens, actual_cost_usd, row["account_id"], reservation_id))
                db.execute("UPDATE usage_reservations SET status = 'settled', resolved_at = ?, actual_prompt_tokens = ?, "
                           "actual_completion_tokens = ?, actual_cached_tokens = ?, actual_cost_usd = ?, reason = ? WHERE id = ?",
                           (now_text, prompt_tokens, completion_tokens, cached_tokens, actual_cost_usd,
                            reason[:500], reservation_id))
                result = "settled"
        self.bus.notify("usage")
        return result

    def add_usage(self, run_id: str, bot_id: str, provider: str, model: str, prompt_tokens: int,
                  completion_tokens: int, cached_tokens: int = 0, cost_usd: float = 0.0, kind: str = "step",
                  account_id: str = "", reservation_id: Optional[str] = None,
                  expected_fence: Optional[int] = None) -> None:
        from math import isfinite
        prompt_tokens, completion_tokens, cached_tokens = map(int, (prompt_tokens, completion_tokens, cached_tokens))
        cost_usd = float(cost_usd)
        if min(prompt_tokens, completion_tokens, cached_tokens) < 0 or not isfinite(cost_usd) or cost_usd < 0:
            raise ValueError("usage must contain non-negative token counts and a finite non-negative cost")
        now_text = iso(utcnow())
        with self._tx() as db:
            account = account_id or provider
            if reservation_id:
                reservation = db.execute("SELECT * FROM usage_reservations WHERE id = ?",
                                         (reservation_id,)).fetchone()
                if reservation is None:
                    raise KeyError(reservation_id)
                identity = (run_id, bot_id, provider, model)
                recorded = tuple(reservation[field] for field in ("run_id", "bot_id", "provider", "model"))
                if identity != recorded or (account_id and account_id != reservation["account_id"]):
                    raise ValueError("usage reservation identity cannot change during settlement")
                if reservation["status"] == "settled":
                    actual = tuple(reservation[field] for field in
                                   ("actual_prompt_tokens", "actual_completion_tokens", "actual_cached_tokens"))
                    if actual == (prompt_tokens, completion_tokens, cached_tokens) and abs(
                            float(reservation["actual_cost_usd"] or 0) - cost_usd) < 1e-12:
                        return
                    raise ValueError("this reservation was already settled with a different outcome")
                self._usage_authority(db, run_id, bot_id, expected_fence)
                if reservation["status"] == "released":
                    raise ValueError("the usage reservation was released and cannot be settled")
                if reservation["status"] == "uncertain":
                    raise ValueError("uncertain usage requires explicit terminal-run reconciliation")
                account = reservation["account_id"]
            else:
                self._usage_authority(db, run_id, bot_id, expected_fence, required=False)
            db.execute(
                "INSERT INTO usage (ts, run_id, bot_id, provider, model, prompt_tokens, completion_tokens, "
                "cached_tokens, cost_usd, kind, account_id, reservation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now_text, run_id, bot_id, provider, model, prompt_tokens, completion_tokens, cached_tokens,
                 cost_usd, kind, account, reservation_id))
            if reservation_id:
                db.execute("UPDATE usage_reservations SET status = 'settled', resolved_at = ?, actual_prompt_tokens = ?, "
                           "actual_completion_tokens = ?, actual_cached_tokens = ?, actual_cost_usd = ?, reason = '' WHERE id = ?",
                           (now_text, prompt_tokens, completion_tokens, cached_tokens, cost_usd, reservation_id))
        self.bus.notify("usage")

    def reserved_account_usage_since(self, account_id: str, seconds: float) -> tuple[int, float]:
        """Every unresolved hold consumes the current allowance until settled/reconciled.

        ``seconds`` remains for compatibility with the measured window API. Wall-clock
        rollover cannot prove a provider charge or make an outstanding hold disappear.
        """
        with self._lock:
            row = self._db.execute(
                "SELECT COALESCE(SUM(reserved_tokens), 0) AS tokens, COALESCE(SUM(reserved_cost_usd), 0) AS cost "
                "FROM usage_reservations WHERE account_id = ? AND status IN ('reserved','uncertain')",
                (account_id,)).fetchone()
        return int(row["tokens"]), float(row["cost"])

    def account_cost_since(self, account_id: str, seconds: float) -> float:
        since = iso(utcnow() - timedelta(seconds=max(0.0, seconds)))
        with self._lock:
            row = self._db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM usage WHERE account_id = ? AND ts >= ?",
                                   (account_id, since)).fetchone()
        return float(row[0])

    def account_daily_costs(self, account_id: str) -> tuple[float, float]:
        start, end = local_day_bounds()
        with self._lock:
            used = float(self._db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM usage "
                                          "WHERE account_id = ? AND ts >= ? AND ts < ?",
                                          (account_id, start, end)).fetchone()[0])
            reserved = float(self._db.execute("SELECT COALESCE(SUM(reserved_cost_usd), 0) FROM usage_reservations "
                                              "WHERE account_id = ? AND created_at >= ? AND created_at < ? "
                                              "AND status IN ('reserved','uncertain')",
                                              (account_id, start, end)).fetchone()[0])
        return used, reserved

    def usage_tokens_since(self, provider: str, seconds: float) -> int:
        """Tokens (prompt + completion) sent to ``provider`` in the trailing window."""
        from datetime import timedelta
        since = iso(utcnow() - timedelta(seconds=seconds))
        with self._lock:
            row = self._db.execute(
                "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS n FROM usage "
                "WHERE provider = ? AND ts >= ?", (provider, since)).fetchone()
        return int(row["n"])

    def account_usage_tokens_since(self, account_id: str, seconds: float) -> int:
        since = iso(utcnow() - timedelta(seconds=max(0.0, seconds)))
        with self._lock:
            row = self._db.execute(
                "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS n FROM usage "
                "WHERE account_id = ? AND ts >= ?", (account_id, since)).fetchone()
        return int(row["n"])

    def save_profile(self, profile: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO model_profiles (key, model, runtime, digest, template_hash, measured_at, doc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (profile.key, profile.model, profile.runtime, profile.digest, profile.template_hash,
                 profile.measured_at, profile.to_json()))
            self._db.commit()

    def latest_profile(self, model: str) -> Optional[Any]:
        """The most recent profile of ``model`` ("ollama/qwen3:4b"), whatever window it was measured at."""
        from .reliability import Profile
        with self._lock:
            row = self._db.execute("SELECT doc FROM model_profiles WHERE model = ? ORDER BY measured_at DESC LIMIT 1",
                                   (model,)).fetchone()
        return Profile.from_json(row["doc"]) if row else None

    def list_profiles(self) -> list[Any]:
        from .reliability import Profile
        with self._lock:
            rows = self._db.execute("SELECT doc FROM model_profiles ORDER BY model, measured_at DESC").fetchall()
        return [Profile.from_json(r["doc"]) for r in rows]

    def usage_models(self, limit: int = 100) -> list[tuple[str, str]]:
        """(provider, model) pairs that have actually been called, most recent first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT provider, model, MAX(ts) AS last FROM usage GROUP BY provider, model "
                "ORDER BY last DESC LIMIT ?", (limit,)).fetchall()
        return [(r["provider"], r["model"]) for r in rows]

    def usage_summary(self, group: str = "day", days: int = 30) -> list[dict[str, Any]]:
        """Aggregate the ledger: group is day | bot | provider | model."""
        from datetime import timedelta
        cols = {"day": "substr(ts, 1, 10)", "bot": "bot_id", "provider": "provider", "model": "provider || '/' || model"}
        if group not in cols:
            raise ValueError(f"group must be one of {', '.join(cols)}")
        since = iso(utcnow() - timedelta(days=days))
        with self._lock:
            rows = self._db.execute(
                f"SELECT {cols[group]} AS k, COUNT(*) AS calls, SUM(prompt_tokens) AS prompt, "
                "SUM(completion_tokens) AS completion, SUM(cached_tokens) AS cached, SUM(cost_usd) AS cost "
                f"FROM usage WHERE ts >= ? GROUP BY k ORDER BY {'k DESC' if group == 'day' else 'cost DESC, calls DESC'}",
                (since,)).fetchall()
        return [{"key": r["k"], "calls": r["calls"], "prompt": r["prompt"] or 0, "completion": r["completion"] or 0,
                 "cached": r["cached"] or 0, "cost": r["cost"] or 0.0} for r in rows]

    def usage_by_local_day(self, days: int = 30, now: Optional[datetime] = None) -> list[dict[str, Any]]:
        """The ledger grouped by LOCAL calendar day (same day definition as the daily caps), newest first.

        Aggregated in SQL by UTC hour and each hour is assigned to the local day of its midpoint, so a timezone with a
        30/45-minute offset can misplace at most half an hour of usage across midnight."""
        from datetime import timedelta
        end_day = (now or utcnow()).astimezone().date()
        since = iso(datetime.combine(end_day - timedelta(days=days - 1), datetime.min.time()).astimezone())
        with self._lock:
            rows = self._db.execute(
                "SELECT substr(ts, 1, 13) AS h, COUNT(*) AS calls, SUM(prompt_tokens) AS p, SUM(completion_tokens) AS c, "
                "SUM(cached_tokens) AS k, SUM(cost_usd) AS cost FROM usage WHERE ts >= ? GROUP BY h", (since,)).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            mid = datetime.fromisoformat(r["h"] + ":30:00+00:00").astimezone().date().isoformat()
            d = out.setdefault(mid, {"day": mid, "calls": 0, "prompt": 0, "completion": 0, "cached": 0, "cost": 0.0})
            d["calls"] += r["calls"]
            d["prompt"] += r["p"] or 0
            d["completion"] += r["c"] or 0
            d["cached"] += r["k"] or 0
            d["cost"] += r["cost"] or 0.0
        return sorted(out.values(), key=lambda d: d["day"], reverse=True)

    def usage_by(self, group: str, days: int = 30, now: Optional[datetime] = None) -> list[dict[str, Any]]:
        """Ledger totals per bot, provider or provider/model over the last ``days`` LOCAL days."""
        from datetime import timedelta
        cols = {"bot": "bot_id", "provider": "provider", "model": "provider || '/' || model"}
        if group not in cols:
            raise ValueError(f"group must be one of {', '.join(cols)}")
        end_day = (now or utcnow()).astimezone().date()
        since = iso(datetime.combine(end_day - timedelta(days=days - 1), datetime.min.time()).astimezone())
        with self._lock:
            rows = self._db.execute(
                f"SELECT {cols[group]} AS k, COUNT(*) AS calls, SUM(prompt_tokens) AS p, SUM(completion_tokens) AS c, "
                "SUM(cached_tokens) AS cached, SUM(cost_usd) AS cost FROM usage WHERE ts >= ? GROUP BY k "
                "ORDER BY cost DESC, (p + c) DESC", (since,)).fetchall()
        return [{"key": r["k"], "calls": r["calls"], "prompt": r["p"] or 0, "completion": r["c"] or 0,
                 "cached": r["cached"] or 0, "cost": r["cost"] or 0.0} for r in rows]

    def recent_rung_changes(self, limit: int = 25) -> list[dict[str, Any]]:
        """Fallbacks, escalations and allowance stops across all runs, newest first (the escalation log)."""
        self.flush_events()
        with self._lock:
            rows = self._db.execute(
                "SELECT run_id, ts, data FROM events WHERE type = 'log' AND "
                "json_extract(data, '$.kind') IN ('fallback', 'escalation', 'quota') ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        out = []
        for r in rows:
            try:
                d = json.loads(r["data"])
            except ValueError:
                continue
            out.append({"run_id": r["run_id"], "ts": r["ts"], "kind": d.get("kind"), "note": d.get("note", ""),
                        "from": d.get("from_model", ""), "to": d.get("to_model", "")})
        return out

    # ------------------------------------------------------- human pauses

    def resume_run(self, run_id: str) -> None:
        """A person finished the login/CAPTCHA wall: wake the run that is waiting on it."""
        self.kv_set(f"resume:{run_id}", "1")
        self.bus.notify(f"human:{run_id}", f"run:{run_id}", "work")

    def consume_resume(self, run_id: str) -> bool:
        if self.kv_get(f"resume:{run_id}") == "1":
            self.kv_set(f"resume:{run_id}", "0")
            return True
        return False

    # --------------------------------------------------------------- kv

    def kv_set(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._db.commit()

    def kv_get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
