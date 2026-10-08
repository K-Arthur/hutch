"""SQLite persistence layer.

One file, WAL mode, ONE writer connection (PF-7): FastAPI workers and daemon
threads share it behind a lock, and event inserts are queued and committed in
batches by a single writer thread. Every run's events are appended here AND
mirrored to an append-only JSONL transcript on disk, so transcripts survive
even a corrupt DB.

Events carry a gap-free per-run ``seq`` (the resume cursor for SSE, UI-3) and a
hash-chain link (SR-11). The schema is versioned with ``PRAGMA user_version``;
upgrades back the database up first.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import shutil
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


#: schema upgrades applied in order; index + 2 == resulting user_version
_MIGRATIONS = [_migrate_2, _migrate_3, _migrate_4, _migrate_5]
SCHEMA_VERSION = 1 + len(_MIGRATIONS)

#: computed fields of ``Run`` are for API output only and are never persisted
_RUN_COMPUTED = {"status_label", "terminal", "needs_person"}
#: the run columns that are authoritative over whatever the JSON document says
_RUN_COLS = "doc, status, fence, lease_owner, lease_expires_at, cancel_requested, pgid"
_TERMINAL_VALUES = tuple(sorted(st.value for st in TERMINAL))
_LIVE_VALUES = tuple(sorted(st.value for st in ACTIVE_STATUSES if st is not RunStatus.pending))
#: fields only the owner writes while a run is claimed: merged into the document in one statement (no read-modify-write)
_PROGRESS_FIELDS = {"steps", "tokens", "workspace", "started_at", "prompt_tokens", "completion_tokens", "cached_tokens",
                    "cost_usd", "model_ms", "tool_ms", "overhead_ms", "context_used", "context_limit", "model_used",
                    "owner", "missed_windows", "reason", "verified", "task_id"}

EVENT_BATCH_MAX = 256
EVENT_FLUSH_SECONDS = 0.02


class Store:
    def __init__(self, config: hutchConfig | None = None, bus: Bus | None = None):
        self.config = config or get_config()
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
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("PRAGMA busy_timeout=30000")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._upgrade()
        # ---- batched event writer (one writer thread, group commit)
        self._buf_cv = threading.Condition()
        self._pending: list[Event] = []
        self._enqueued = 0
        self._committed = 0
        self._run_status: dict[str, str] = {}
        #: per-run observers of events in sequence order (the JSONL transcript mirror); errors are collected, never swallowed
        #: runs this process has seen reach a terminal state: a late worker's events for them are dropped (never appended)
        self._sealed: set[str] = set()
        self._inflight = 0                    # events the writer thread has taken and not yet committed
        self._sinks: dict[str, Callable[[Event], None]] = {}
        self._sink_errors: dict[str, list[str]] = {}
        self.dropped_events = 0
        self._closing = False
        self._writer = threading.Thread(target=self._writer_loop, name="hutch-event-writer", daemon=True)
        self._writer.start()
        ref = weakref.ref(self)
        atexit.register(lambda: (s := ref()) and s.close())

    # ------------------------------------------------------------ migrations

    def _upgrade(self) -> None:
        db = self._db
        version = db.execute("PRAGMA user_version").fetchone()[0]
        existing = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bots'").fetchone()
        if version == 0 and existing:
            version = 1  # a v0.1 database predating versioning
        db.executescript(_SCHEMA)
        if version == 0:
            version = 1
        target = SCHEMA_VERSION
        if version >= target:
            if version > target:
                raise RuntimeError(
                    f"{self.config.db_path} is schema v{version}, newer than this hutch (v{target}); "
                    "upgrade hutch instead of opening it with an older build")
            return
        if existing and version < target:
            backup = self.config.db_path.with_suffix(f".db.bak-v{version}")
            if not backup.exists():
                db.commit()
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                shutil.copy2(self.config.db_path, backup)
        for v in range(version, target):
            _MIGRATIONS[v - 1](db)
            db.execute(f"PRAGMA user_version = {v + 1}")
            db.commit()

    def ensure_listening(self) -> None:
        """Start receiving wake-ups from other hutch processes (idempotent)."""
        if not self._listening:
            self._listening = True
            self.hub.listen()

    @property
    def schema_version(self) -> int:
        with self._lock:
            return self._db.execute("PRAGMA user_version").fetchone()[0]

    # ----------------------------------------------------------- lifecycle

    def close(self) -> None:
        if self._closing:
            return
        self.flush_events()
        with self._buf_cv:
            self._closing = True
            self._buf_cv.notify_all()
        self._writer.join(timeout=5)
        self.hub.close()
        with self._lock:
            try:
                self._db.close()
            except sqlite3.Error:
                pass

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
    def _run(row: sqlite3.Row) -> Run:
        """A Run from its row: the columns, not the JSON, are authoritative for status, fence, lease and cancel."""
        run = Run.model_validate_json(row["doc"])
        run.status = RunStatus(row["status"])
        run.fence = row["fence"]
        run.lease_owner = row["lease_owner"]
        run.lease_expires_at = row["lease_expires_at"]
        run.cancel_requested = bool(row["cancel_requested"])
        run.pgid = row["pgid"]
        return run

    # ------------------------------------------------------------ tasks

    def enqueue_task(self, task: Task) -> Task:
        with self._lock:
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
        q = "SELECT id, bot_id, kind, prompt, created_at FROM tasks WHERE done = 0"
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
            self._db.execute(
                "INSERT INTO runs (id, bot_id, task_id, doc, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run.id, run.bot_id, run.task_id, self._run_json(run), run.status.value, run.created_at),
            )
            self._db.commit()
        self.bus.notify("work", "runs", f"run:{run.id}")
        return run

    def submit_run(self, run: Run, task: Task) -> Run:
        """Admit work: the task and its run are created together, linked, in ONE transaction (or not at all).

        The old path made three separate commits and marked the task done before anything had run."""
        run.task_id = task.id
        with self._tx() as db:
            db.execute("INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id) "
                       "VALUES (?, ?, ?, ?, ?, 0, 'queued', ?)",
                       (task.id, task.bot_id, task.kind, task.prompt, task.created_at, run.id))
            db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (run.id, run.bot_id, task.id, self._run_json(run), run.status.value, run.created_at))
        self.bus.notify("work", "runs", f"run:{run.id}")
        return run

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
            db.execute("INSERT INTO runs (id, bot_id, task_id, doc, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (run.id, run.bot_id, task.id, self._run_json(run), run.status.value, run.created_at))
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
        cap = " AND (SELECT COUNT(*) FROM runs c WHERE c.status IN (" + marks + ")) < ?" if max_live else ""
        sql = (
            "UPDATE runs SET lease_owner = ?, lease_expires_at = ?, heartbeat_at = ?, fence = fence + 1 "
            "WHERE id = ? AND status = 'pending' AND cancel_requested = 0 "
            "AND (lease_owner = '' OR lease_expires_at IS NULL OR lease_expires_at < ?) "
            "AND NOT EXISTS (SELECT 1 FROM runs o WHERE o.bot_id = runs.bot_id AND o.id != runs.id AND "
            "(o.status IN (" + marks + ") OR (o.status = 'pending' AND o.lease_owner != '' AND o.lease_expires_at >= ?)))"
            + cap)
        args: list[Any] = [owner, expires, stamp, run_id, stamp, *_LIVE_VALUES, stamp]
        if max_live:
            args += [*_LIVE_VALUES, max_live]
        with self._tx() as db:
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
                "RETURNING id", (iso(now + timedelta(seconds=lease_seconds)), iso(now), owner, *_TERMINAL_VALUES)).fetchall()
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

    def legacy_live_runs(self) -> list[Run]:
        """Live runs from before leases existed (no lease at all): only the old process-liveness check can judge them."""
        marks = ",".join("?" for _ in _LIVE_VALUES)
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_RUN_COLS} FROM runs WHERE status IN ({marks}) AND lease_expires_at IS NULL AND fence = 0",
                _LIVE_VALUES).fetchall()
        return [self._run(r) for r in rows]

    def set_pgid(self, run_id: str, fence: int, pgid: int) -> None:
        with self._lock:
            self._db.execute("UPDATE runs SET pgid = ? WHERE id = ? AND fence = ?", (pgid, run_id, fence))
            self._db.commit()

    def update_run(self, run: Run) -> None:
        """Persist a run's progress.

        A run that was never claimed (fence 0: a fixture, an import, a demo) has no owner to race with and is written whole, as
        before. A claimed run is written ONLY by its owner and ONLY while it still owns it: the write carries the fence, merges
        just the progress fields (never status, which changes through ``transition_run``), and is refused once the run is
        finished. A stale writer gets ``LeaseLost`` instead of silently overwriting the outcome.
        """
        with self._lock:
            row = self._db.execute("SELECT fence, status FROM runs WHERE id = ?", (run.id,)).fetchone()
            if row is None:
                return
            if row["fence"] == 0 and run.fence == 0:
                cur = self._db.execute("UPDATE runs SET doc = ?, status = ? WHERE id = ? AND fence = 0",
                                       (self._run_json(run), run.status.value, run.id))
                self._db.commit()
                if cur.rowcount == 1:
                    self._notify_run(run)
                    return
                row = self._db.execute("SELECT fence, status FROM runs WHERE id = ?", (run.id,)).fetchone()
            if row["fence"] != run.fence:
                raise LeaseLost(run.id, f"fence {run.fence} is stale (current {row['fence']})")
            if RunStatus(row["status"]) in TERMINAL:
                raise LeaseLost(run.id, f"already {row['status']}")
            patch = json.dumps(run.model_dump(include=_PROGRESS_FIELDS), default=str)
            marks = ",".join("?" for _ in _TERMINAL_VALUES)
            cur = self._db.execute(
                f"UPDATE runs SET doc = json_patch(doc, ?) WHERE id = ? AND fence = ? AND status NOT IN ({marks})",
                (patch, run.id, run.fence, *_TERMINAL_VALUES))
            self._db.commit()
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
                       fields: Optional[dict[str, Any]] = None) -> Run:
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
                row, emitted = self._apply_transition(db, run_id, to, fence, exit_reason, error, event, bump_fence, fields,
                                                      earlier=mine)
            if mine:
                done = {id(e) for e in mine}
                self._pending = [e for e in self._pending if id(e) not in done]
                self._committed += len(mine)                      # they are committed now; flush_events must not wait for them
                self._buf_cv.notify_all()
            for e in mine + ([emitted] if emitted is not None else []):
                self._fan_out(e)                                 # committed: now observers see them, in sequence order
        run = self._run(row)
        self._run_status[run_id] = run.status.value
        if run.status in TERMINAL:
            with self._buf_cv:
                self._sealed.add(run_id)
        if emitted is not None or run.status is to:
            self.bus.notify("work", "runs", f"run:{run_id}", "events")
        return run

    def _apply_transition(self, db: sqlite3.Connection, run_id: str, to: RunStatus, fence: Optional[int],
                          exit_reason: Optional[str], error: Optional[str], event: Optional[dict[str, Any]],
                          bump_fence: bool, fields: Optional[dict[str, Any]],
                          earlier: Optional[list[Event]] = None) -> tuple[sqlite3.Row, Optional[Event]]:
        from .models import EventType
        row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        cur = RunStatus(row["status"])
        if fence is not None and row["fence"] != fence:
            raise LeaseLost(run_id, f"fence {fence} is stale (current {row['fence']})")
        if not allowed(cur, to) and cur is not to:
            raise IllegalTransition(run_id, cur, to)
        if cur is to:
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

    def request_cancel(self, run_id: str) -> Optional[Run]:
        """Record that a person wants this run stopped. ANY process may call this; the owner (or recovery) acts on it.

        A queued run nobody owns is ended here. A claimed or live run moves to ``cancelling`` and stays there until the
        owner has verified everything it started is gone. (The old Stop flipped an in-memory flag and only worked in the
        process that owned the run.)
        """
        with self._tx() as db:
            row = db.execute(f"SELECT {_RUN_COLS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            if RunStatus(row["status"]) in TERMINAL:
                return self._run(row)
            db.execute("UPDATE runs SET cancel_requested = 1 WHERE id = ?", (run_id,))
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
        self.bus.notify(f"approval:wake:{run_id}", f"human:{run_id}", f"run:{run_id}", "work")
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
        return runs[0] if runs else None

    def last_successful_run(self, bot_id: str) -> Optional[Run]:
        with self._lock:
            row = self._db.execute(
                f"SELECT {_RUN_COLS} FROM runs WHERE bot_id = ? AND status = ? ORDER BY created_at DESC LIMIT 1",
                (bot_id, RunStatus.succeeded.value),
            ).fetchone()
        return self._run(row) if row else None

    # --------------------------------------------------- processes a run started

    def add_proc(self, run_id: str, pid: int, pgid: int, starttime: int, kind: str = "tool") -> None:
        """Remember a process a run started, with its identity, so ending the run (or recovering a crashed owner) can end it."""
        with self._lock:
            self._db.execute("INSERT INTO run_procs (run_id, pid, pgid, starttime, kind, started_at) VALUES (?, ?, ?, ?, ?, ?)",
                             (run_id, pid, pgid, starttime, kind, iso(utcnow())))
            self._db.commit()

    def end_proc(self, run_id: str, pid: int) -> None:
        with self._lock:
            self._db.execute("UPDATE run_procs SET ended_at = ? WHERE run_id = ? AND pid = ? AND ended_at IS NULL",
                             (iso(utcnow()), run_id, pid))
            self._db.commit()

    def live_procs(self, run_id: str) -> list[dict[str, Any]]:
        """Processes recorded for the run that were never recorded as finished."""
        with self._lock:
            rows = self._db.execute("SELECT pid, pgid, starttime, kind FROM run_procs WHERE run_id = ? AND ended_at IS NULL",
                                    (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def close_procs(self, run_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE run_procs SET ended_at = ? WHERE run_id = ? AND ended_at IS NULL", (iso(utcnow()), run_id))
            self._db.commit()

    # ----------------------------------------------------- tool actions (receipts)

    def begin_action(self, run_id: str, tool: str, idem_key: str, effect: str, summary: str = "",
                     fence: Optional[int] = None) -> str:
        """Write the INTENT to run an action that has an effect, before it runs (ADR-0003).

        If the process dies after the effect but before ``finish_action``, the row stays ``started``: recovery then knows the
        outcome is unknown and never replays it. With ``fence`` the intent is admitted only if the caller still owns a run that
        is live and not being stopped - checked in the same transaction as the insert - so a worker that lost its lease (or was
        told to stop) cannot START a new effect, even if it never noticed."""
        from .models import new_id
        action_id = new_id("act")
        with self._tx() as db:
            if fence is not None:
                row = db.execute("SELECT fence, status, cancel_requested FROM runs WHERE id = ?", (run_id,)).fetchone()
                if row is None or row["fence"] != fence:
                    raise LeaseLost(run_id, "this worker no longer owns the run")
                st = RunStatus(row["status"])
                if st in TERMINAL or st in (RunStatus.cancelling, RunStatus.recovering) or row["cancel_requested"]:
                    raise LeaseLost(run_id, f"the run is {st.value}; no new action may start")
            db.execute(
                "INSERT INTO tool_actions (id, run_id, tool, idem_key, effect, summary, status, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'started', ?)",
                (action_id, run_id, tool, idem_key, effect, summary[:500], iso(utcnow())))
        return action_id

    def finish_action(self, action_id: str, status: str, result_digest: str = "") -> None:
        assert status in ("done", "failed")
        with self._lock:
            self._db.execute("UPDATE tool_actions SET status = ?, finished_at = ?, result_digest = ? WHERE id = ?",
                             (status, iso(utcnow()), result_digest, action_id))
            self._db.commit()

    def actions_in_doubt(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, tool, effect, summary, started_at, idem_key FROM tool_actions "
                "WHERE run_id = ? AND status IN ('started', 'unknown') ORDER BY started_at", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    def mark_actions_unknown(self, run_id: str) -> int:
        with self._lock:
            cur = self._db.execute("UPDATE tool_actions SET status = 'unknown' WHERE run_id = ? AND status = 'started'", (run_id,))
            self._db.commit()
        return cur.rowcount

    def list_actions(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM tool_actions WHERE run_id = ? ORDER BY started_at", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    # ----------------------------------------------------------- events

    def append_event(self, event: Event) -> Event:
        """Queue an event; the single writer commits in batches. Returns immediately, so the agent loop never waits on a disk commit.

        ``seq`` and the chain ``hash`` are NOT assigned here: they are assigned at commit time, inside the write transaction, from
        the tail the DATABASE holds. Several processes append to one run's transcript (the worker, the dashboard recording a stop,
        a supervisor recovering it); a per-process counter would give them colliding numbers and a broken chain. Reads call
        ``flush_events`` first, so every reader still sees its own writes."""
        with self._buf_cv:
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

    def _writer_loop(self) -> None:
        while True:
            with self._buf_cv:
                while not self._pending and not self._closing:
                    self._buf_cv.wait()
                if not self._pending and self._closing:
                    return
                # let a burst accumulate: group commit amortises the fsync-free WAL append
                if len(self._pending) < EVENT_BATCH_MAX:
                    self._buf_cv.wait(timeout=EVENT_FLUSH_SECONDS)
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
                with self._tx() as db:
                    for run_id, evs in by_run.items():
                        row = db.execute("SELECT sealed FROM runs WHERE id = ?", (run_id,)).fetchone()
                        if row is not None and row["sealed"]:
                            self.dropped_events += len(evs)
                            continue
                        self._insert_events(db, run_id, evs)
                        stored += evs
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

    def flush_events(self, timeout: float = 10.0) -> None:
        """Block until every event appended so far is committed."""
        deadline = time.monotonic() + timeout
        with self._buf_cv:
            target = self._enqueued
            while self._committed < target and self._writer.is_alive():
                left = deadline - time.monotonic()
                if left <= 0:
                    return
                self._buf_cv.wait(timeout=min(left, 0.1))

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

    def create_approval(self, req: ApprovalRequest) -> ApprovalRequest:
        with self._lock:
            self._db.execute(
                "INSERT INTO approvals (id, run_id, bot_id, status, created_at, doc) VALUES (?, ?, ?, ?, ?, ?)",
                (req.id, req.run_id, req.bot_id, req.status.value, req.created_at, req.model_dump_json()),
            )
            self._db.commit()
        self.bus.notify("approvals", "work", f"run:{req.run_id}")
        return req

    def update_approval(self, req: ApprovalRequest) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE approvals SET status = ?, doc = ? WHERE id = ?",
                (req.status.value, req.model_dump_json(), req.id),
            )
            self._db.commit()
        self.bus.notify("approvals", "work", f"approval:{req.id}", f"run:{req.run_id}")

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            row = self._db.execute("SELECT doc FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return ApprovalRequest.model_validate_json(row["doc"]) if row else None

    def recent_approvals(self, limit: int = 10) -> list[ApprovalRequest]:
        """Most recently decided approvals, newest first (the inbox's 'recently decided' list)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT doc FROM approvals WHERE status != ? ORDER BY created_at DESC LIMIT ?",
                (ApprovalStatus.pending.value, limit)).fetchall()
        return [ApprovalRequest.model_validate_json(r["doc"]) for r in rows]

    def pending_approvals(self, bot_id: Optional[str] = None) -> list[ApprovalRequest]:
        q = "SELECT doc FROM approvals WHERE status = ?"
        args: tuple = (ApprovalStatus.pending.value,)
        if bot_id:
            q += " AND bot_id = ?"
            args = args + (bot_id,)
        with self._lock:
            rows = self._db.execute(q + " ORDER BY created_at", args).fetchall()
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

    def add_usage(self, run_id: str, bot_id: str, provider: str, model: str, prompt_tokens: int,
                  completion_tokens: int, cached_tokens: int = 0, cost_usd: float = 0.0, kind: str = "step") -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO usage (ts, run_id, bot_id, provider, model, prompt_tokens, completion_tokens, "
                "cached_tokens, cost_usd, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (iso(utcnow()), run_id, bot_id, provider, model, prompt_tokens, completion_tokens, cached_tokens,
                 cost_usd, kind))
            self._db.commit()
        self.bus.notify("usage")

    def usage_tokens_since(self, provider: str, seconds: float) -> int:
        """Tokens (prompt + completion) sent to ``provider`` in the trailing window."""
        from datetime import timedelta
        since = iso(utcnow() - timedelta(seconds=seconds))
        with self._lock:
            row = self._db.execute(
                "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS n FROM usage "
                "WHERE provider = ? AND ts >= ?", (provider, since)).fetchone()
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
