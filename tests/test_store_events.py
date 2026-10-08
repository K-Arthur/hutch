"""Event sequencing, hash chain, batching, migrations, and wake-ups (UI-3, SR-11, PF-5, PF-7)."""

from __future__ import annotations

import sqlite3
import threading
import time

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
        with pytest.raises(RuntimeError, match="event writer is still running"):
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
