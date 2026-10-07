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
from pathlib import Path
from typing import Any, Optional

from .config import hutchConfig, get_config
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


#: schema upgrades applied in order; index + 2 == resulting user_version
_MIGRATIONS = [_migrate_2]
SCHEMA_VERSION = 1 + len(_MIGRATIONS)

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
        self._seq: dict[str, int] = {}
        self._tail: dict[str, str] = {}
        self._run_status: dict[str, str] = {}
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

    # ------------------------------------------------------------ tasks

    def enqueue_task(self, task: Task) -> Task:
        with self._lock:
            self._db.execute(
                "INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done) VALUES (?, ?, ?, ?, ?, 0)",
                (task.id, task.bot_id, task.kind, task.prompt, task.created_at),
            )
            self._db.commit()
        self.bus.notify("work")
        return task

    def next_task(self, bot_id: str) -> Optional[Task]:
        with self._lock:
            row = self._db.execute(
                "SELECT id, bot_id, kind, prompt, created_at FROM tasks "
                "WHERE bot_id = ? AND done = 0 ORDER BY created_at LIMIT 1",
                (bot_id,),
            ).fetchone()
        return Task(**dict(row)) if row else None

    def finish_task(self, task_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
            self._db.commit()

    def pending_tasks(self, bot_id: Optional[str] = None) -> list[Task]:
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
                (run.id, run.bot_id, run.task_id, run.model_dump_json(), run.status.value, run.created_at),
            )
            self._db.commit()
        self.bus.notify("work", "runs", f"run:{run.id}")
        return run

    def update_run(self, run: Run) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE runs SET doc = ?, status = ? WHERE id = ?",
                (run.model_dump_json(), run.status.value, run.id),
            )
            self._db.commit()
        # `work` wakes the scheduler loop; only a status transition changes what it should do,
        # so per-step accounting updates must not make an idle loop spin.
        if self._run_status.get(run.id) != run.status.value:
            self._run_status[run.id] = run.status.value
            self.bus.notify("work", "runs", f"run:{run.id}")
        else:
            self.bus.notify(f"run:{run.id}")

    def get_run(self, run_id: str) -> Optional[Run]:
        with self._lock:
            row = self._db.execute("SELECT doc FROM runs WHERE id = ?", (run_id,)).fetchone()
        return Run.model_validate_json(row["doc"]) if row else None

    def list_runs(self, bot_id: Optional[str] = None, limit: int = 50) -> list[Run]:
        q = "SELECT doc FROM runs"
        args: tuple = ()
        if bot_id:
            q += " WHERE bot_id = ?"
            args = (bot_id,)
        q += " ORDER BY created_at DESC LIMIT ?"
        args = args + (limit,)
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [Run.model_validate_json(r["doc"]) for r in rows]

    def list_runs_page(self, bot_id: Optional[str] = None, status: Optional[str] = None,
                       limit: int = 50, offset: int = 0) -> list[Run]:
        """Filtered, paginated run listing for the Runs page."""
        q, args = "SELECT doc FROM runs WHERE 1=1", []
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
        return [Run.model_validate_json(r["doc"]) for r in rows]

    def latest_finished_run(self, bot_id: str) -> Optional[Run]:
        done = (RunStatus.succeeded.value, RunStatus.failed.value, RunStatus.stopped.value)
        with self._lock:
            row = self._db.execute(
                f"SELECT doc FROM runs WHERE bot_id = ? AND status IN ({','.join('?' for _ in done)}) "
                "ORDER BY created_at DESC LIMIT 1", (bot_id, *done)).fetchone()
        return Run.model_validate_json(row["doc"]) if row else None

    def active_runs(self) -> list[Run]:
        live = tuple(st.value for st in ACTIVE_STATUSES)
        marks = ",".join("?" for _ in live)
        with self._lock:
            rows = self._db.execute(
                f"SELECT doc FROM runs WHERE status IN ({marks})", live
            ).fetchall()
        return [Run.model_validate_json(r["doc"]) for r in rows]

    def active_run_for_bot(self, bot_id: str) -> Optional[Run]:
        runs = [r for r in self.active_runs() if r.bot_id == bot_id]
        return runs[0] if runs else None

    def last_successful_run(self, bot_id: str) -> Optional[Run]:
        with self._lock:
            row = self._db.execute(
                "SELECT doc FROM runs WHERE bot_id = ? AND status = ? ORDER BY created_at DESC LIMIT 1",
                (bot_id, RunStatus.succeeded.value),
            ).fetchone()
        return Run.model_validate_json(row["doc"]) if row else None

    # ----------------------------------------------------------- events

    def append_event(self, event: Event) -> Event:
        """Assign ``seq`` and the chain hash now; the single writer commits in batches.

        Returns immediately, so the agent loop never waits on a disk commit. Reads
        call ``flush_events`` first, so every reader still sees its own writes.
        """
        data_json = _canonical(event.data)
        with self._buf_cv:
            seq = self._seq.get(event.run_id)
            if seq is None:
                seq, tail = self._load_tail(event.run_id)
                self._tail[event.run_id] = tail
            seq += 1
            self._seq[event.run_id] = seq
            event.seq = seq
            event.hash = chain_hash(self._tail[event.run_id], event.run_id, seq,
                                    event.ts, event.type.value, data_json)
            self._tail[event.run_id] = event.hash
            self._pending.append(event)
            self._enqueued += 1
            self._buf_cv.notify_all()
        return event

    def _load_tail(self, run_id: str) -> tuple[int, str]:
        with self._lock:
            row = self._db.execute(
                "SELECT seq, hash FROM events WHERE run_id = ? ORDER BY seq DESC LIMIT 1", (run_id,)
            ).fetchone()
        if row is None:
            return 0, GENESIS
        return row["seq"], row["hash"] or GENESIS

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
            try:
                self._commit_batch(batch)
            finally:
                with self._buf_cv:
                    self._committed += len(batch)
                    self._buf_cv.notify_all()
            self.bus.notify(*{f"run:{e.run_id}" for e in batch}, "events")

    def _commit_batch(self, batch: list[Event]) -> None:
        rows = [(e.run_id, e.seq, e.hash, e.ts, e.type.value, _canonical(e.data)) for e in batch]
        last: Optional[Exception] = None
        for attempt in range(5):
            try:
                with self._lock:
                    self._db.executemany(
                        "INSERT INTO events (run_id, seq, hash, ts, type, data) VALUES (?, ?, ?, ?, ?, ?)", rows)
                    self._db.commit()
                return
            except sqlite3.OperationalError as exc:  # another process held the write lock past busy_timeout
                last = exc
                time.sleep(0.05 * (attempt + 1))
        import sys
        print(f"hutch: dropped {len(rows)} events after repeated DB errors: {last}", file=sys.stderr)

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

    def tokens_today(self, bot_id: str) -> int:
        day_prefix = utcnow().astimezone().date().isoformat()
        with self._lock:
            rows = self._db.execute(
                "SELECT doc FROM runs WHERE bot_id = ? AND created_at LIKE ?", (bot_id, f"{day_prefix}%")
            ).fetchall()
        return sum(Run.model_validate_json(r["doc"]).tokens for r in rows)

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
