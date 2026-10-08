"""Recoverable JSONL delivery from canonical SQLite events.

Intent is enqueued by the canonical event writer in the same transaction. A private file lock serializes delivery
across Stores; acknowledgement follows fsync. A restart verifies the file prefix
against the canonical hash chain before appending, including an unacknowledged
successful write. Corrupt/partial mirrors are preserved before reconstruction.
"""
from __future__ import annotations

import fcntl
from collections import OrderedDict
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
import uuid

BATCH = 128
MAX_LINE_BYTES = 32 * 1024 * 1024
MAX_BATCH_BYTES = 4 * 1024 * 1024
MAX_PREFIX_CACHE = 128
_COMPONENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def migrate(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE transcript_delivery (
        run_id TEXT PRIMARY KEY, bot_name TEXT NOT NULL, target_seq INTEGER NOT NULL,
        delivered_seq INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
        file_size INTEGER NOT NULL DEFAULT -1, file_mtime_ns INTEGER NOT NULL DEFAULT 0)""")
    db.execute("""INSERT INTO transcript_delivery(run_id, bot_name, target_seq)
        SELECT e.run_id, COALESCE(b.name, 'unassigned'), MAX(e.seq)
        FROM events e LEFT JOIN runs r ON r.id = e.run_id LEFT JOIN bots b ON b.id = r.bot_id
        GROUP BY e.run_id""")


class MirrorMismatch(ValueError):
    pass


class DeliveryPaused(Exception):
    pass


def _signature(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _private_regular(fd: int) -> None:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise ValueError("transcript/lock must be an owned regular file with no hard links")


def _body(row) -> dict:
    return {"seq": row["seq"], "ts": row["ts"], "type": row["type"],
            "data": json.loads(row["data"]), "hash": row["hash"]}


def _normalized(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class TranscriptMirror:
    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.cache = OrderedDict()  # path -> (stat signature, verified seq, canonical hash)
        self.scan_cursor = ""
        self.scan_done = False
        self.delivery_cursor = ""
        self.last_error = ""
        self.thread = threading.Thread(target=self._loop, name="hutch-transcript-mirror", daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread.ident is not None:
            self.thread.join(5)
            if self.thread.is_alive():
                raise RuntimeError("cannot close Hutch state while transcript delivery is still running")

    def status(self, run_id: str) -> dict:
        with self.store._lock:
            row = self.store._db.execute("SELECT * FROM transcript_delivery WHERE run_id = ?",
                                         (run_id,)).fetchone()
        if row and row["target_seq"] <= row["delivered_seq"] and not row["error"]:
            self._check_file(row)
            with self.store._lock:
                row = self.store._db.execute("SELECT * FROM transcript_delivery WHERE run_id = ?", (run_id,)).fetchone()
        with self.store._lock:
            tail = self.store._db.execute("SELECT COALESCE(MAX(seq), 0) FROM events WHERE run_id = ?", (run_id,)).fetchone()[0]
        target = max(row["target_seq"], tail) if row else tail
        return {"target_seq": target, "delivered_seq": row["delivered_seq"] if row else 0,
                "pending": bool(row and target > row["delivered_seq"]),
                "error": row["error"] if row else "", "worker_error": self.last_error}

    def flush(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        self.wake.set()
        while True:
            with self.store._lock:
                row = self.store._db.execute("SELECT run_id, error FROM transcript_delivery "
                    "WHERE target_seq > delivered_seq OR error != '' LIMIT 1").fetchone()
            if row is None and self.scan_done:
                return
            if time.monotonic() >= deadline:
                reason = f"for {row[0]}: {row[1] or 'delivery in progress'}" if row else "during startup verification"
                raise RuntimeError(f"transcript mirror remains pending {reason}")
            time.sleep(0.02)

    def _loop(self):
        while True:
            self.wake.clear()
            try:
                scanning = self._scan_files()
                progressed = self.drain_once() or scanning
                self.last_error = ""
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"[:400]
                progressed = False
            if self.stop.is_set():
                return
            if not progressed:
                self.wake.wait(1.0)  # discover silent commits from another process

    def _check_file(self, row):
        reason = "mirror metadata differs; checking canonical prefix"
        try:
            path = self._directory(row["bot_name"], row["run_id"]) / "transcript.jsonl"
            info = path.lstat()
            if (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                    and info.st_size == row["file_size"] and info.st_mtime_ns == row["file_mtime_ns"]):
                return
        except (OSError, ValueError) as exc:
            reason = f"{type(exc).__name__}: {exc}"[:400]
        with self.store._tx() as db:
            db.execute("UPDATE transcript_delivery SET delivered_seq = 0, error = ? "
                "WHERE run_id = ? AND delivered_seq = ? AND file_size = ? AND file_mtime_ns = ? AND error = ''",
                (reason, row["run_id"], row["delivered_seq"], row["file_size"], row["file_mtime_ns"]))
        self.wake.set()

    def _scan_files(self):
        if self.scan_done:
            return False
        with self.store._lock:
            rows = self.store._db.execute("SELECT * FROM transcript_delivery WHERE run_id > ? "
                                         "ORDER BY run_id LIMIT 20", (self.scan_cursor,)).fetchall()
        for row in rows:
            self.scan_cursor = row["run_id"]
            if row["target_seq"] <= row["delivered_seq"] and not row["error"]:
                self._check_file(row)
        self.scan_done = len(rows) < 20
        return not self.scan_done

    def drain_once(self) -> bool:
        with self.store._lock:
            rows = self.store._db.execute("SELECT run_id, bot_name, target_seq FROM transcript_delivery "
                "WHERE (target_seq > delivered_seq OR error != '') AND run_id > ? ORDER BY run_id LIMIT 20",
                (self.delivery_cursor,)).fetchall()
        if not rows:
            self.delivery_cursor = ""
            return False
        progressed = False
        for row in rows:
            self.delivery_cursor = row["run_id"]
            try:
                progressed = self._deliver(row) or progressed
            except DeliveryPaused:
                break  # shutdown interrupts prefix checking without inventing an IO failure
            except Exception as exc:
                # Persist the failure without claiming delivery. A later process
                # retries it; the API exposes the pending/error state.
                with self.store._tx() as db:
                    db.execute("UPDATE transcript_delivery SET error = ? WHERE run_id = ?",
                               (f"{type(exc).__name__}: {exc}"[:400], row["run_id"]))
        if len(rows) < 20:
            self.delivery_cursor = ""
        return progressed

    def _directory(self, bot_name: str, run_id: str) -> Path:
        if not _COMPONENT.fullmatch(bot_name) or not _COMPONENT.fullmatch(run_id):
            raise ValueError("unsafe transcript path component; delivery requires operator repair")
        root = self.store.config.state_dir.resolve()
        current = root
        for component in ("bots", bot_name, "runs", run_id):
            current = current / component
            current.mkdir(mode=0o700, exist_ok=True)
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("transcript directory must be owned and cannot be a symlink")
        return current

    def _events(self, run_id, after):
        with self.store._lock:
            sizes = self.store._db.execute("SELECT seq, length(CAST(data AS BLOB)) FROM events WHERE run_id = ? "
                "AND seq > ? ORDER BY seq LIMIT ?", (run_id, after, BATCH)).fetchall()
            total, last = 0, after
            for row in sizes:
                if row[1] > MAX_LINE_BYTES:
                    raise ValueError("canonical event exceeds mirror line limit; delivery remains pending")
                if total and total + row[1] > MAX_BATCH_BYTES:
                    break
                total += row[1]
                last = row[0]
                if total >= MAX_BATCH_BYTES:
                    break
            return self.store._db.execute("SELECT seq, hash, ts, type, data FROM events WHERE run_id = ? "
                                         "AND seq > ? AND seq <= ? ORDER BY seq", (run_id, after, last)).fetchall()

    def _verify_row(self, row, run_id, seq, previous):
        from .store import chain_hash, GENESIS
        if row["seq"] != seq + 1:
            raise ValueError("canonical transcript sequence has a gap; refusing reconstruction")
        if row["hash"] and chain_hash(previous, run_id, row["seq"], row["ts"], row["type"], row["data"]) != row["hash"]:
            raise ValueError("canonical transcript hash is invalid; refusing reconstruction")
        return row["seq"], row["hash"] or GENESIS

    def _cache_prefix(self, path, signature, seq, previous):
        self.cache[path] = signature, seq, previous
        self.cache.move_to_end(path)
        while len(self.cache) > MAX_PREFIX_CACHE:
            self.cache.popitem(last=False)

    def _prefix(self, path, run_id):
        from .store import GENESIS
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            return 0, GENESIS
        with os.fdopen(fd, "rb") as source:
            _private_regular(source.fileno())
            signature = _signature(os.fstat(source.fileno()))
            cached = self.cache.get(path)
            if cached and cached[0] == signature:
                self.cache.move_to_end(path)
                return cached[1:]
            seq, previous, rows = 0, GENESIS, []
            while True:
                if self.stop.is_set():
                    raise DeliveryPaused()
                line = source.readline(MAX_LINE_BYTES + 1)
                if not line:
                    self._cache_prefix(path, signature, seq, previous)
                    return seq, previous
                if not line.endswith(b"\n") or len(line) > MAX_LINE_BYTES:
                    raise MirrorMismatch("partial or oversized mirror line")
                if not rows:
                    rows = list(reversed(self._events(run_id, seq)))
                if not rows:
                    raise MirrorMismatch("mirror is ahead of restored canonical history")
                row = rows.pop()
                seq, previous = self._verify_row(row, run_id, seq, previous)
                try:
                    matches = _normalized(json.loads(line)) == _normalized(_body(row))
                except (ValueError, UnicodeDecodeError):
                    matches = False
                if not matches:
                    raise MirrorMismatch("mirror differs from canonical history")

    def _ack(self, run_id, seq, signature):
        with self.store._tx() as db:
            # While a job is already pending, event inserts need not rewrite it.
            # Re-read the canonical tail in the ACK transaction before clearing
            # pending: an event committed during file IO cannot be lost. A later
            # event insert sees the acknowledged job and makes it pending again.
            tail = db.execute("SELECT COALESCE(MAX(seq), 0) FROM events WHERE run_id = ?", (run_id,)).fetchone()[0]
            if tail < seq:
                raise ValueError("canonical transcript tail is missing; refusing acknowledgement")
            db.execute("UPDATE transcript_delivery SET target_seq = MAX(target_seq, ?), delivered_seq = MAX(delivered_seq, ?), error = '', "
                       "file_size = ?, file_mtime_ns = ? WHERE run_id = ?",
                       (tail, seq, signature[2], signature[3], run_id))

    def _deliver(self, pending) -> bool:
        if self.stop.is_set():
            raise DeliveryPaused()
        directory = self._directory(pending["bot_name"], pending["run_id"])
        path = directory / "transcript.jsonl"
        lock_fd = os.open(directory / ".transcript.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            _private_regular(lock_fd)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            try:
                seq, previous = self._prefix(path, pending["run_id"])
            except MirrorMismatch:
                # Keep forensic material, including a newer file beside a
                # restored database. Never overwrite a good prefix in place.
                path.replace(directory / f"transcript.preserved-{uuid.uuid4().hex}.jsonl")
                self.cache.pop(path, None)
                from .store import GENESIS
                seq, previous = 0, GENESIS
            rows = self._events(pending["run_id"], seq)
            if not rows and seq < pending["target_seq"]:
                raise ValueError("canonical transcript tail is missing; delivery remains pending")
            lines = []
            for row in rows:
                if self.stop.is_set():
                    raise DeliveryPaused()
                seq, previous = self._verify_row(row, pending["run_id"], seq, previous)
                line = (_normalized(_body(row)) + "\n").encode()
                if len(line) > MAX_LINE_BYTES:
                    raise ValueError("canonical event exceeds mirror line limit; delivery remains pending")
                lines.append(line)
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            with os.fdopen(fd, "ab") as destination:
                _private_regular(destination.fileno())
                destination.writelines(lines)
                destination.flush()
                os.fsync(destination.fileno())
                signature = _signature(os.fstat(destination.fileno()))
                self._cache_prefix(path, signature, seq, previous)
            dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            self._ack(pending["run_id"], seq, signature)
            return seq >= pending["target_seq"] or bool(rows)
        finally:
            os.close(lock_fd)
