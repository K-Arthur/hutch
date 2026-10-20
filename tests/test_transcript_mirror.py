"""Recoverable audit files: committed intent, append/ack crashes and hostile paths."""
import json
import multiprocessing
import os
import sqlite3
import time
from pathlib import Path

import pytest

from hutch.config import hutchConfig
from hutch.models import Bot, Event, EventType, Run
from hutch.store import Store
from hutch.transcript_mirror import TranscriptMirror


@pytest.fixture
def paused(config, monkeypatch):
    monkeypatch.setattr(TranscriptMirror, "start", lambda self: None)
    store = Store(config)
    yield store
    store.close()


def history(store, *, name="mirror", run_id=None, count=3):
    bot = store.create_bot(Bot(name=name))
    run = store.create_run(Run(bot_id=bot.id, prompt="fixture", **({"id": run_id} if run_id else {})))
    for index in range(count):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"note": f"row {index}"}))
    store.flush_events()
    return bot, run, store.config.run_dir(bot.name, run.id) / "transcript.jsonl"


def drain(store, limit=30):
    for _ in range(limit):
        store._mirror.drain_once()
        with store._lock:
            remaining = store._db.execute("SELECT COUNT(*) FROM transcript_delivery WHERE target_seq > delivered_seq OR error != ''").fetchone()[0]
        if not remaining:
            return
    raise AssertionError("delivery did not complete")


def assert_file(store, run, path):
    actual = [json.loads(line) for line in path.read_text().splitlines()]
    events = store.list_events(run.id)
    expected = [{"seq": e.seq, "ts": e.ts, "type": e.type.value, "data": e.data, "hash": e.hash} for e in events]
    assert actual == expected
    assert [row["seq"] for row in actual] == list(range(1, len(actual) + 1))


def test_intent_rolls_back_with_event_and_retains_bot_directory_after_deletion(paused):
    store = paused
    assert store._db.execute("PRAGMA synchronous").fetchone()[0] == 2
    bot, run, path = history(store)
    assert not store._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                                 ("transcript_delivery_insert",)).fetchone()
    assert not path.exists() and store._mirror.status(run.id)["pending"]
    with pytest.raises(RuntimeError):
        with store._tx() as db:
            Store._insert_events(db, run.id, [Event(run_id=run.id, type=EventType.log, data={"note": "rollback"})])
            raise RuntimeError("before commit")
    assert store._mirror.status(run.id)["target_seq"] == 3
    store.delete_bot(bot.id)
    drain(store)
    assert_file(store, run, path)
    assert path.stat().st_mode & 0o777 == 0o600


def test_v16_replaces_legacy_event_trigger_and_preserves_delivery_intents(paused, config, monkeypatch):
    bot, run, _ = history(paused, name="migrated-mirror", count=2)
    pending = paused._db.execute("SELECT target_seq, delivered_seq FROM transcript_delivery WHERE run_id = ?",
                                 (run.id,)).fetchone()
    assert tuple(pending) == (2, 0)
    paused.close()

    # Model an installed v15 database with its original insert trigger. The
    # SQLite backup made during upgrade must preserve that source for rollback.
    with sqlite3.connect(config.db_path) as db:
        db.executescript("""CREATE TRIGGER transcript_delivery_insert AFTER INSERT ON events
            WHEN NOT EXISTS(SELECT 1 FROM transcript_delivery WHERE run_id = NEW.run_id AND target_seq > delivered_seq)
            BEGIN
            INSERT INTO transcript_delivery(run_id, bot_name, target_seq)
            VALUES (NEW.run_id, COALESCE((SELECT b.name FROM runs r JOIN bots b ON b.id = r.bot_id
                    WHERE r.id = NEW.run_id), 'unassigned'), NEW.seq)
            ON CONFLICT(run_id) DO UPDATE SET target_seq = MAX(target_seq, NEW.seq);
            END;""")
        db.execute("PRAGMA user_version = 15")

    # Keep this migration test scoped to v15 -> v16 as later migrations are
    # covered independently. The fixture database already has newer tables.
    from hutch import store as store_module
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", 16)
    monkeypatch.setattr(store_module, "_MIGRATIONS", store_module._MIGRATIONS[:15])
    upgraded = Store(config)
    try:
        assert upgraded.schema_version == 16
        assert not upgraded._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                                        ("transcript_delivery_insert",)).fetchone()
        assert tuple(upgraded._db.execute("SELECT target_seq, delivered_seq FROM transcript_delivery WHERE run_id = ?",
                                         (run.id,)).fetchone()) == (2, 0)
        backup = sqlite3.connect(config.db_path.with_suffix(".db.bak-v15"))
        try:
            assert backup.execute("PRAGMA user_version").fetchone()[0] == 15
            assert backup.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                                  ("transcript_delivery_insert",)).fetchone()
        finally:
            backup.close()

        upgraded.append_event(Event(run_id=run.id, type=EventType.log, data={"next": True}))
        upgraded.flush_events()
        assert tuple(upgraded._db.execute("SELECT target_seq, delivered_seq FROM transcript_delivery WHERE run_id = ?",
                                         (run.id,)).fetchone()) == (2, 0)
        assert upgraded._mirror.status(run.id)["target_seq"] == 3
        drain(upgraded)
        assert_file(upgraded, run, config.run_dir(bot.name, run.id) / "transcript.jsonl")
    finally:
        upgraded.close()


def test_lost_ack_retries_file_without_duplicate_rows(paused, monkeypatch):
    _, run, path = history(paused)
    original = paused._mirror._ack
    monkeypatch.setattr(paused._mirror, "_ack", lambda *args: (_ for _ in ()).throw(RuntimeError("crash before ack")))
    paused._mirror.drain_once()
    assert_file(paused, run, path)
    assert paused._mirror.status(run.id)["delivered_seq"] == 0
    monkeypatch.setattr(paused._mirror, "_ack", original)
    paused._mirror.cache.clear()
    drain(paused)
    assert_file(paused, run, path)
    assert not paused._mirror.status(run.id)["pending"]


@pytest.mark.parametrize("damage", ["partial", "changed", "ahead"])
def test_changed_mirror_is_preserved_before_reconstruction(paused, damage):
    _, run, path = history(paused)
    drain(paused)
    original = path.read_bytes()
    broken = {"partial": original + b'{"seq":4', "changed": original.replace(b"row 1", b"WRONG"),
              "ahead": original + original.splitlines(keepends=True)[-1]}[damage]
    path.write_bytes(broken)
    paused._mirror.status(run.id)  # metadata change marks reconciliation due
    drain(paused)
    assert_file(paused, run, path)
    copies = list(path.parent.glob("transcript.preserved-*.jsonl"))
    assert len(copies) == 1 and copies[0].read_bytes() == broken


@pytest.mark.parametrize("kind", ["file_symlink", "file_hardlink", "lock_symlink", "directory_symlink"])
def test_delivery_refuses_links_without_touching_their_target(paused, tmp_path, kind):
    _, run, path = history(paused)
    victim = tmp_path / "private-target"
    victim.write_text("DO NOT TOUCH")
    path.parent.mkdir(parents=True)
    if kind == "file_symlink":
        path.symlink_to(victim)
    elif kind == "file_hardlink":
        os.link(victim, path)
    elif kind == "lock_symlink":
        (path.parent / ".transcript.lock").symlink_to(victim)
    else:
        path.parent.rmdir()
        private_directory = tmp_path / "private-directory"
        private_directory.mkdir()
        path.parent.symlink_to(private_directory, target_is_directory=True)
    paused._mirror.drain_once()
    state = paused._mirror.status(run.id)
    assert state["pending"] and state["error"]
    assert victim.read_text() == "DO NOT TOUCH"
    if kind == "directory_symlink":
        assert list(private_directory.iterdir()) == []


def _crash_after_file_flush(state_dir):
    TranscriptMirror.start = lambda self: None
    store = Store(hutchConfig(state_dir=Path(state_dir)))
    history(store, name="crash-mirror", run_id="run_mirror_crash")
    store._mirror._ack = lambda *args: os._exit(0)
    store._mirror.drain_once()
    os._exit(2)


def test_real_process_death_after_file_flush_replays_and_acknowledges(config):
    process = multiprocessing.get_context("spawn").Process(target=_crash_after_file_flush, args=(str(config.state_dir),))
    process.start(); process.join(10)
    try:
        assert not process.is_alive() and process.exitcode == 0
        store = Store(config)
        try:
            store.flush_transcripts()
            run = store.get_run("run_mirror_crash")
            path = config.run_dir("crash-mirror", run.id) / "transcript.jsonl"
            assert_file(store, run, path)
            assert not store._mirror.status(run.id)["pending"]
        finally:
            store.close()
    finally:
        if process.is_alive():
            process.kill(); process.join(5)


def test_missing_file_recovers_after_restart_even_after_ack(paused, config, monkeypatch):
    _, run, path = history(paused)
    drain(paused)
    path.unlink()
    paused.close()
    # Restore the real start method saved on the class by the fixture patch.
    monkeypatch.undo()
    recovered = Store(config)
    try:
        # Startup file scan notices an acknowledged file missing from this state.
        recovered.flush_transcripts()
        assert_file(recovered, run, path)
    finally:
        recovered.close()


def test_permanent_bad_paths_do_not_starve_another_run(paused):
    for i in range(21):
        history(paused, name=f"bad-{i}", run_id=f"a{i:02d}/unsafe")
    _, run, path = history(paused, name="healthy-tail", run_id="z_healthy")
    paused._mirror.drain_once(); paused._mirror.drain_once()
    assert_file(paused, run, path)
    assert not paused._mirror.status(run.id)["pending"]


def test_delivery_checks_canonical_hash_before_replacing_a_good_file(paused):
    _, run, path = history(paused)
    drain(paused)
    original = path.read_bytes()
    with paused._tx() as db:
        db.execute("UPDATE events SET data = '{\"note\":\"CORRUPT DB\"}' WHERE run_id = ? AND seq = 2", (run.id,))
        db.execute("UPDATE transcript_delivery SET delivered_seq = 0, error = 'recheck' WHERE run_id = ?", (run.id,))
    paused._mirror.cache.clear()
    paused._mirror.drain_once()
    assert "canonical transcript hash" in paused._mirror.status(run.id)["error"]
    assert path.read_bytes() == original
    assert not list(path.parent.glob("transcript.preserved-*.jsonl"))


def test_successive_batches_append_without_rereading_the_whole_history(paused, monkeypatch):
    _, run, path = history(paused, count=650)
    afters = []
    original = paused._mirror._events
    def observe(run_id, after):
        afters.append(after)
        return original(run_id, after)
    monkeypatch.setattr(paused._mirror, "_events", observe)
    drain(paused)
    for i in range(20):
        paused.append_event(Event(run_id=run.id, type=EventType.log, data={"more": i}))
    paused.flush_events()
    drain(paused)
    assert_file(paused, run, path)
    assert afters == sorted(set(afters)) and afters[0] == 0
    assert len(afters) <= 7, "verified prefix should be reused until its file metadata changes"


def _competing_delivery(state_dir, run_id, ready):
    TranscriptMirror.start = lambda self: None
    store = Store(hutchConfig(state_dir=Path(state_dir)))
    try:
        assert ready.wait(10)
        deadline = time.monotonic() + 10
        while store._mirror.status(run_id)["pending"] and time.monotonic() < deadline:
            if not store._mirror.drain_once():
                # A peer may own the nonblocking file lock; give it time to
                # finish and acknowledge before retrying instead of burning a
                # fixed number of lock-contention attempts.
                time.sleep(0.005)
        assert not store._mirror.status(run_id)["pending"], "competing delivery did not reach the canonical tail"
    finally:
        store.close()


def test_two_processes_deliver_one_file_without_duplicates(paused, config):
    _, run, path = history(paused, count=400)
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    processes = [context.Process(target=_competing_delivery, args=(str(config.state_dir), run.id, ready))
                 for _ in range(2)]
    for process in processes:
        process.start()
    ready.set()
    try:
        for process in processes:
            process.join(10)
            assert not process.is_alive() and process.exitcode == 0
        assert_file(paused, run, path)
        assert not paused._mirror.status(run.id)["pending"]
    finally:
        for process in processes:
            if process.is_alive():
                process.kill(); process.join(5)


def test_shutdown_joins_delivery_before_closing_database(config, monkeypatch):
    import threading
    store = Store(config)
    entered, release = threading.Event(), threading.Event()
    original = store._mirror._deliver
    join = store._mirror.thread.join
    def blocked(row):
        entered.set()
        assert release.wait(10)
        return original(row)
    monkeypatch.setattr(store._mirror, "_deliver", blocked)
    try:
        history(store)
        store._mirror.wake.set()
        assert entered.wait(5)
        monkeypatch.setattr(store._mirror.thread, "join", lambda timeout=None: join(0.02))
        with pytest.raises(RuntimeError, match="transcript delivery is still running"):
            store.close()
        assert store._mirror.thread.is_alive() and not store._closed
        assert store._db.execute("SELECT 1").fetchone()[0] == 1
    finally:
        release.set()
        join(5)
        store.close()
    assert not store._mirror.thread.is_alive() and store._closed


def test_batches_bound_bytes_before_loading_large_payloads(paused, monkeypatch):
    from hutch import transcript_mirror
    monkeypatch.setattr(transcript_mirror, "MAX_BATCH_BYTES", 100)
    monkeypatch.setattr(transcript_mirror, "MAX_LINE_BYTES", 1000)
    _, run, path = history(paused, count=0)
    for i in range(3):
        paused.append_event(Event(run_id=run.id, type=EventType.log, data={"value": "x" * 60, "i": i}))
    paused.flush_events()
    assert len(paused._mirror._events(run.id, 0)) == 1
    drain(paused)
    assert_file(paused, run, path)


def test_prefix_cache_is_bounded_and_evicted_history_is_reverified(paused, monkeypatch):
    from hutch import transcript_mirror
    monkeypatch.setattr(transcript_mirror, "MAX_PREFIX_CACHE", 2)
    first = history(paused, name="first")
    drain(paused)
    for name in ("second", "third"):
        history(paused, name=name)
        drain(paused)
    assert len(paused._mirror.cache) == 2 and first[2] not in paused._mirror.cache
    paused.append_event(Event(run_id=first[1].id, type=EventType.log, data={"later": True}))
    paused.flush_events()
    drain(paused)
    assert_file(paused, first[1], first[2])
    assert len(paused._mirror.cache) == 2


def test_pending_job_coalesces_writes_but_ack_cannot_lose_a_racing_event(paused, monkeypatch):
    _, run, path = history(paused)
    assert not paused._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                                  ("transcript_delivery_insert",)).fetchone()
    # One committed batch creates one intent at its tail; subsequent events do
    # not rewrite that pending row, and status derives the newer tail from DB.
    assert paused._db.execute("SELECT target_seq FROM transcript_delivery WHERE run_id = ?", (run.id,)).fetchone()[0] == 3
    assert paused._mirror.status(run.id)["target_seq"] == 3
    original = paused._mirror._ack
    raced = []
    def during_io(run_id, seq, signature):
        if not raced:
            raced.append(1)
            paused.append_event(Event(run_id=run_id, type=EventType.log, data={"committed_before_ack": True}))
            paused.flush_events()
        original(run_id, seq, signature)
    monkeypatch.setattr(paused._mirror, "_ack", during_io)
    paused._mirror.drain_once()
    assert paused._mirror.status(run.id)["pending"]
    assert paused._mirror.status(run.id)["target_seq"] == 4
    assert paused._mirror.status(run.id)["delivered_seq"] == 3
    drain(paused)
    assert_file(paused, run, path)
    paused.append_event(Event(run_id=run.id, type=EventType.log, data={"committed_after_ack": True}))
    paused.flush_events()
    assert paused._mirror.status(run.id)["pending"]
    drain(paused)
    assert_file(paused, run, path)


def test_deleted_canonical_tail_cannot_clear_a_delivery_intent(paused):
    _, run, path = history(paused)
    drain(paused)
    path.unlink()
    with paused._tx() as db:
        db.execute("DELETE FROM events WHERE run_id = ? AND seq = 3", (run.id,))
    paused._mirror.status(run.id)
    paused._mirror.drain_once()
    paused._mirror.drain_once()
    state = paused._mirror.status(run.id)
    assert state["target_seq"] == 3 and state["delivered_seq"] == 2 and state["pending"]
    assert "canonical transcript tail is missing" in state["error"]
