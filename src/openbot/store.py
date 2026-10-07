"""SQLite persistence layer.

One file, WAL mode, thread-safe via a lock (FastAPI workers + daemon threads
share one process). Every run's events are appended here AND mirrored to an
append-only JSONL transcript on disk, so transcripts survive even a corrupt DB.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from .config import OpenBotConfig, get_config
from .models import (
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


class Store:
    def __init__(self, config: OpenBotConfig | None = None):
        self.config = config or get_config()
        self.config.ensure()
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.config.db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.executescript(_SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------- bots

    def create_bot(self, bot: Bot) -> Bot:
        with self._lock:
            self._db.execute(
                "INSERT INTO bots (id, name, doc) VALUES (?, ?, ?)",
                (bot.id, bot.name, bot.model_dump_json()),
            )
            self._db.commit()
        return bot

    def upsert_bot(self, bot: Bot) -> Bot:
        with self._lock:
            self._db.execute(
                "INSERT INTO bots (id, name, doc) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET id=excluded.id, doc=excluded.doc",
                (bot.id, bot.name, bot.model_dump_json()),
            )
            self._db.commit()
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
        return True

    # ------------------------------------------------------------ tasks

    def enqueue_task(self, task: Task) -> Task:
        with self._lock:
            self._db.execute(
                "INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done) VALUES (?, ?, ?, ?, ?, 0)",
                (task.id, task.bot_id, task.kind, task.prompt, task.created_at),
            )
            self._db.commit()
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
        return run

    def update_run(self, run: Run) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE runs SET doc = ?, status = ? WHERE id = ?",
                (run.model_dump_json(), run.status.value, run.id),
            )
            self._db.commit()

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

    def active_runs(self) -> list[Run]:
        live = (RunStatus.pending.value, RunStatus.running.value, RunStatus.waiting_approval.value)
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
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events (run_id, ts, type, data) VALUES (?, ?, ?, ?)",
                (event.run_id, event.ts, event.type.value, event.json()),
            )
            self._db.commit()
            event.id = cur.lastrowid
        return event

    def list_events(self, run_id: str, after_id: int = 0) -> list[Event]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, run_id, ts, type, data FROM events WHERE run_id = ? AND id > ? ORDER BY id",
                (run_id, after_id),
            ).fetchall()
        return [
            Event(
                id=r["id"], run_id=r["run_id"], ts=r["ts"],
                type=EventType(r["type"]), data=json.loads(r["data"]),
            )
            for r in rows
        ]

    # -------------------------------------------------------- approvals

    def create_approval(self, req: ApprovalRequest) -> ApprovalRequest:
        with self._lock:
            self._db.execute(
                "INSERT INTO approvals (id, run_id, bot_id, status, created_at, doc) VALUES (?, ?, ?, ?, ?, ?)",
                (req.id, req.run_id, req.bot_id, req.status.value, req.created_at, req.model_dump_json()),
            )
            self._db.commit()
        return req

    def update_approval(self, req: ApprovalRequest) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE approvals SET status = ?, doc = ? WHERE id = ?",
                (req.status.value, req.model_dump_json(), req.id),
            )
            self._db.commit()

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            row = self._db.execute("SELECT doc FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return ApprovalRequest.model_validate_json(row["doc"]) if row else None

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

    def remember(self, bot_id: str, key: str, value: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO memory (bot_id, key, value, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(bot_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (bot_id, key, value, iso(utcnow())),
            )
            self._db.commit()

    def recall_all(self, bot_id: str) -> list[MemoryItem]:
        with self._lock:
            rows = self._db.execute(
                "SELECT key, value, updated_at FROM memory WHERE bot_id = ? ORDER BY key", (bot_id,)
            ).fetchall()
        return [MemoryItem(**dict(r)) for r in rows]

    def forget(self, bot_id: str, key: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM memory WHERE bot_id = ? AND key = ?", (bot_id, key))
            self._db.commit()
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
