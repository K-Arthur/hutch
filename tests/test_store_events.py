"""Event sequencing, hash chain, batching, migrations, and wake-ups (UI-3, SR-11, PF-5, PF-7)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from hutch.config import get_config
from hutch.models import Bot, Event, EventType, Run
from hutch.store import GENESIS, SCHEMA_VERSION, Store, chain_hash
from hutch.wake import Bus


def _run(store) -> Run:
    bot = store.create_bot(Bot(name="evbot"))
    return store.create_run(Run(bot_id=bot.id, prompt="x"))


def test_close_keeps_persistence_open_until_a_blocked_event_writer_exits(store, monkeypatch):
    run = _run(store)
    entered, release = threading.Event(), threading.Event()
    commit = store._commit_batch
    join, flush = store._writer.join, store.flush_events

    def held_commit(batch):
        entered.set()
        assert release.wait(5), "test must release the writer"
        return commit(batch)

    monkeypatch.setattr(store, "_commit_batch", held_commit)
    monkeypatch.setattr(store, "flush_events", lambda **kw: flush(timeout=0.01))
    monkeypatch.setattr(store._writer, "join", lambda **kw: join(timeout=0.01))
    store.append_event(Event(run_id=run.id, type=EventType.log, data={"held": True}))
    try:
        assert entered.wait(2)
        with pytest.raises(RuntimeError, match="event writer is still running|event flush timed out"):
            store.close()
        assert store._db.execute("SELECT 1").fetchone()[0] == 1
        with pytest.raises(RuntimeError, match="closing"):
            store.append_event(Event(run_id=run.id, type=EventType.log, data={"late": True}))
    finally:
        release.set()
        join(timeout=3)
    assert not store._writer.is_alive()
    assert store._db.execute("SELECT COUNT(*) FROM events WHERE run_id = ?", (run.id,)).fetchone()[0] == 1
    store.close()  # retry completes rather than returning merely because closing began
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        store._db.execute("SELECT 1")
    store.close()  # completed closure remains idempotent


def test_flush_reports_uncommitted_events_and_preserves_them_for_retry(store, monkeypatch):
    run = _run(store)
    entered, release = threading.Event(), threading.Event()
    original = store._commit_batch
    def hold(batch):
        entered.set()
        assert release.wait(5)
        return original(batch)
    monkeypatch.setattr(store, "_commit_batch", hold)
    store.append_event(Event(run_id=run.id, type=EventType.log, data={"not_yet_committed": True}))
    try:
        assert entered.wait(2)
        with pytest.raises(RuntimeError, match="canonical events remain uncommitted"):
            store.flush_events(timeout=0.01)
        assert store._db.execute("SELECT COUNT(*) FROM events WHERE run_id = ?", (run.id,)).fetchone()[0] == 0
    finally:
        release.set()
    store.flush_events()
    assert store.list_events(run.id)[0].data == {"not_yet_committed": True}


def test_queued_event_survives_process_restart_before_canonical_commit(store, config):
    """An acknowledged queue append must survive loss of the writer process."""
    run = _run(store)
    store.close()
    project = str(Path(__file__).resolve().parents[1])
    env = os.environ.copy()
    env["HUTCH_STATE_DIR"] = str(config.state_dir)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (project, env.get("PYTHONPATH", "")) if part)
    script = r"""
import os
import sys
import threading
from hutch.config import get_config
from hutch.models import Event, EventType
from hutch.store import Store

Store._writer_loop = lambda self: threading.Event().wait()
store = Store(get_config())
store.append_event(Event(run_id=sys.argv[1], type=EventType.log,
                         data={"recovered": "after-process-restart"}))
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", script, run.id], env=env, check=True, timeout=10)

    recovered = Store(config)
    try:
        events = recovered.list_events(run.id)
        assert [event.data for event in events] == [{"recovered": "after-process-restart"}]
        assert events[0].seq == 1
        assert recovered.verify_chain(run.id)["ok"]
    finally:
        recovered.close()


def test_two_stores_recovering_the_same_outbox_entry_commit_it_once(store, config, monkeypatch):
    run = _run(store)
    entered, release = threading.Event(), threading.Event()
    original_batch = store._commit_batch
    event = Event(run_id=run.id, type=EventType.log, data={"same": "outbox entry"})

    def hold_batch(batch):
        entered.set()
        assert release.wait(5)
        return original_batch(batch)

    monkeypatch.setattr(store, "_commit_batch", hold_batch)
    store.append_event(event)
    assert entered.wait(2)

    recovered = Store(config)
    try:
        recovered.flush_events(timeout=2)
        release.set()
        store.flush_events(timeout=2)
        assert recovered.count_events(run.id) == 1
        assert recovered.verify_chain(run.id)["ok"]
        assert recovered._db.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0] == 0
        conflicting = Event(outbox_id=event.outbox_id, run_id=run.id, ts=event.ts,
                            type=EventType.log, data={"different": "payload"})
        with pytest.raises(ValueError, match="event outbox identity conflicts"):
            with recovered._tx() as db:
                Store._insert_events(db, run.id, [conflicting])
    finally:
        release.set()
        recovered.close()


def test_non_lock_database_failure_requeues_event_batch_without_acknowledging_it(store, monkeypatch):
    run = _run(store)
    entered, release = threading.Event(), threading.Event()
    original_batch = store._commit_batch

    def hold_batch(batch):
        entered.set()
        assert release.wait(5)
        return original_batch(batch)

    monkeypatch.setattr(store, "_commit_batch", hold_batch)
    store.append_event(Event(run_id=run.id, type=EventType.log, data={"retry": True}))
    assert entered.wait(2)
    transaction = store._tx
    failed = False

    def fail_once():
        nonlocal failed
        if not failed:
            failed = True
            raise sqlite3.IntegrityError("injected event transaction failure")
        return transaction()

    monkeypatch.setattr(store, "_tx", fail_once)
    release.set()
    store.flush_events(timeout=2)

    assert failed
    assert store.count_events(run.id) == 1
    assert store.verify_chain(run.id)["ok"]
    assert store.dropped_events == 0


def test_repeated_storage_failures_back_off_without_acknowledging_events(store, monkeypatch):
    run = _run(store)
    entered, release = threading.Event(), threading.Event()
    original_batch = store._commit_batch

    def hold_batch(batch):
        entered.set()
        assert release.wait(5)
        return original_batch(batch)

    monkeypatch.setattr(store, "_commit_batch", hold_batch)
    store.append_event(Event(run_id=run.id, type=EventType.log, data={"durable": "after-retry"}))
    assert entered.wait(2)
    transaction = store._tx
    attempts: list[float] = []

    def fail_four_commits():
        attempts.append(time.monotonic())
        if len(attempts) <= 4:
            raise sqlite3.IntegrityError("injected persistent storage failure")
        return transaction()

    monkeypatch.setattr(store, "_tx", fail_four_commits)
    release.set()
    store.flush_events(timeout=5)

    assert len(attempts) == 5
    intervals = [later - earlier for earlier, later in zip(attempts, attempts[1:])]
    assert intervals[0] >= 0.04
    assert intervals[1] >= 0.08
    assert intervals[2] >= 0.16
    assert intervals[3] >= 0.32
    events = store.list_events(run.id)
    assert [event.data for event in events] == [{"durable": "after-retry"}]
    assert store.verify_chain(run.id)["ok"]
    assert store.dropped_events == 0


def test_sqlite_full_event_write_is_retained_until_capacity_returns(store, capsys):
    run = _run(store)
    entered, release = threading.Event(), threading.Event()
    original_batch = store._commit_batch

    def hold_batch(batch):
        entered.set()
        assert release.wait(5)
        return original_batch(batch)

    store._commit_batch = hold_batch
    store.append_event(Event(run_id=run.id, type=EventType.log, data={"payload": "x" * 2_000_000}))
    assert entered.wait(2)
    with store._tx() as db:
        db.execute("CREATE TABLE storage_pressure (payload BLOB NOT NULL)")
        db.execute("INSERT INTO storage_pressure(payload) VALUES (zeroblob(?))", (4 * 1024 * 1024,))
        page_count = db.execute("PRAGMA page_count").fetchone()[0]
        free_pages = db.execute("PRAGMA freelist_count").fetchone()[0]
        db.execute(f"PRAGMA max_page_count = {page_count}")

    assert free_pages == 0
    release.set()
    with pytest.raises(RuntimeError, match="canonical events remain uncommitted"):
        store.flush_events(timeout=1.2)

    deadline = time.monotonic() + 5
    with store._buf_cv:
        while not store._pending or store._inflight:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "SQLite full failure did not return the event batch to the queue"
            store._buf_cv.wait(timeout=min(remaining, 0.05))
    assert "database or disk is full" in capsys.readouterr().err
    with store._lock:
        assert store._db.execute("SELECT COUNT(*) FROM events WHERE run_id = ?", (run.id,)).fetchone()[0] == 0

    with store._tx() as db:
        db.execute("DELETE FROM storage_pressure")
        db.execute("DROP TABLE storage_pressure")
    store.flush_events(timeout=5)

    events = store.list_events(run.id)
    assert len(events) == 1
    assert events[0].data == {"payload": "x" * 2_000_000}
    assert store.verify_chain(run.id)["ok"]
    assert store.dropped_events == 0


def test_seq_is_contiguous_per_run_and_independent_between_runs(store):
    a, b = _run(store), None
    bot2 = store.create_bot(Bot(name="other"))
    b = store.create_run(Run(bot_id=bot2.id, prompt="y"))
    for i in range(5):
        store.append_event(Event(run_id=a.id, type=EventType.log, data={"i": i}))
        store.append_event(Event(run_id=b.id, type=EventType.log, data={"i": i}))
    assert [e.seq for e in store.list_events(a.id)] == [1, 2, 3, 4, 5]
    assert [e.seq for e in store.list_events(b.id)] == [1, 2, 3, 4, 5]
    assert store.last_seq(a.id) == 5


def test_resume_cursor_returns_exactly_the_missing_tail(store):
    run = _run(store)
    for i in range(20):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    got = store.list_events(run.id, after_seq=12)
    assert [e.seq for e in got] == list(range(13, 21))
    assert store.list_events(run.id, after_seq=20) == []


def test_pagination_tail_and_earlier(store):
    run = _run(store)
    for i in range(50):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    tail = store.tail_events(run.id, limit=10)
    assert [e.seq for e in tail] == list(range(41, 51))
    earlier = store.events_before(run.id, before_seq=tail[0].seq, limit=10)
    assert [e.seq for e in earlier] == list(range(31, 41))


def test_hash_chain_verifies_and_detects_tampering(store):
    run = _run(store)
    for i in range(6):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    ok = store.verify_chain(run.id)
    assert ok["ok"] and ok["checked"] == 6

    # an attacker (or a bug) edits history directly in the database
    store.flush_events()
    with store._lock:
        store._db.execute("UPDATE events SET data = ? WHERE run_id = ? AND seq = 3",
                          ('{"i":999}', run.id))
        store._db.commit()
    bad = store.verify_chain(run.id)
    assert not bad["ok"] and bad["bad_seq"] == 3


def test_hash_chain_detects_deleted_event(store):
    run = _run(store)
    for i in range(5):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    store.flush_events()
    with store._lock:
        store._db.execute("DELETE FROM events WHERE run_id = ? AND seq = 2", (run.id,))
        store._db.commit()
    assert not store.verify_chain(run.id)["ok"]


def test_chain_continues_across_store_reopen(config):
    s1 = Store(config)
    bot = s1.create_bot(Bot(name="reopen"))
    run = s1.create_run(Run(bot_id=bot.id, prompt="x"))
    for i in range(3):
        s1.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    s1.close()
    s2 = Store(config)
    s2.append_event(Event(run_id=run.id, type=EventType.log, data={"i": 3}))
    assert [e.seq for e in s2.list_events(run.id)] == [1, 2, 3, 4]
    assert s2.verify_chain(run.id)["ok"]
    s2.close()


def test_batched_writer_sustains_over_1000_events_per_second(store):
    run = _run(store)
    n = 5000
    t0 = time.perf_counter()
    for i in range(n):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))
    store.flush_events()
    rate = n / (time.perf_counter() - t0)
    assert store.count_events(run.id) == n
    assert rate > 1000, f"only {rate:.0f} events/s"


def test_concurrent_appenders_keep_seq_gap_free(store):
    run = _run(store)

    def worker(k):
        for i in range(200):
            store.append_event(Event(run_id=run.id, type=EventType.log, data={"k": k, "i": i}))

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    seqs = [e.seq for e in store.list_events(run.id)]
    assert seqs == list(range(1, 1601))
    assert store.verify_chain(run.id)["ok"]


def test_migrates_a_v1_database_and_backs_it_up(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    config = get_config()
    config.ensure()
    # build a v0.1-shaped database: no seq/hash columns, no user_version
    db = sqlite3.connect(config.db_path)
    db.executescript("""
        CREATE TABLE bots (id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, doc TEXT NOT NULL);
        CREATE TABLE tasks (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, kind TEXT NOT NULL,
            prompt TEXT NOT NULL, created_at TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE runs (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, task_id TEXT, doc TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, ts TEXT NOT NULL,
            type TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE approvals (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, bot_id TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, doc TEXT NOT NULL);
        CREATE TABLE tool_allows (bot_id TEXT NOT NULL, sticky_key TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY (bot_id, sticky_key));
        CREATE TABLE memory (bot_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
            updated_at TEXT NOT NULL, PRIMARY KEY (bot_id, key));
        CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    for i in range(4):
        db.execute("INSERT INTO events (run_id, ts, type, data) VALUES ('run_old', '2026-01-01T00:00:00+00:00', 'log', ?)",
                   (f'{{"i": {i}}}',))
    db.execute("INSERT INTO memory VALUES ('b', 'k', 'v', '2026-01-01T00:00:00+00:00')")
    db.commit()
    db.close()

    store = Store(config)
    assert store.schema_version == SCHEMA_VERSION
    assert (config.state_dir / "hutch.db.bak-v1").exists()  # safety copy before upgrading
    events = store.list_events("run_old")
    assert [e.seq for e in events] == [1, 2, 3, 4]          # backfilled in insertion order
    assert store.verify_chain("run_old")["legacy"] == 4     # reported as unchained, not as tampering
    # new events chain from genesis and old data stays readable
    store.append_event(Event(run_id="run_old", type=EventType.log, data={"i": 4}))
    assert store.last_seq("run_old") == 5
    assert store.recall_all("b")[0].value == "v"
    store.close()


def test_refuses_a_newer_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    config = get_config()
    s = Store(config)
    s.close()
    db = sqlite3.connect(config.db_path)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    db.commit()
    db.close()
    import pytest
    with pytest.raises(RuntimeError, match="newer than this hutch"):
        Store(config)


def test_chain_hash_is_order_sensitive():
    a = chain_hash(GENESIS, "r", 1, "t", "log", "{}")
    b = chain_hash(a, "r", 2, "t", "log", "{}")
    assert b != chain_hash(GENESIS, "r", 2, "t", "log", "{}")


# ---------------------------------------------------------------- wake bus (PF-5)

def test_bus_wait_returns_immediately_if_version_already_moved():
    bus = Bus()
    seen = bus.version("t")
    bus.notify("t")
    t0 = time.perf_counter()
    assert bus.wait("t", seen, timeout=5) != seen
    assert time.perf_counter() - t0 < 0.1


def test_bus_wakes_a_sleeper_and_times_out_otherwise():
    bus = Bus()
    seen = bus.version("t")
    threading.Timer(0.1, bus.notify, args=("t",)).start()
    t0 = time.perf_counter()
    assert bus.wait("t", seen, timeout=5) != seen
    assert 0.05 < time.perf_counter() - t0 < 1.0
    t0 = time.perf_counter()
    assert bus.wait("t", bus.version("t"), timeout=0.2) == bus.version("t")
    assert time.perf_counter() - t0 >= 0.18


def test_cross_process_hub_delivers_between_two_stores(tmp_path, monkeypatch):
    """Two Store objects on one state dir stand in for `hutch serve` and a CLI process."""
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    config = get_config()
    server, cli = Store(config), Store(config)
    server.ensure_listening()
    seen = server.bus.version("approvals")
    cli.bus.notify("approvals")           # what `hutch approvals approve` does via the store
    deadline = time.time() + 5
    while server.bus.version("approvals") == seen and time.time() < deadline:
        time.sleep(0.02)
    assert server.bus.version("approvals") != seen
    server.close()
    cli.close()


def test_review_wakeup_discovers_a_recently_started_listener(tmp_path, monkeypatch):
    """An approval decision must bypass the no-peer discovery throttle."""
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    config = get_config()
    sender, worker = Store(config), Store(config)
    sender.bus.notify("background")  # caches that no worker is listening
    worker.ensure_listening()
    seen = worker.bus.version("approval:review-1")
    sender.bus.notify("approval:review-1")
    deadline = time.monotonic() + 2
    while worker.bus.version("approval:review-1") == seen and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        assert worker.bus.version("approval:review-1") != seen
    finally:
        sender.close()
        worker.close()
