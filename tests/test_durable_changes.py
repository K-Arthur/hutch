"""Transactional resource invalidations: crashes, retention, restart and bounded replay."""
import json
import multiprocessing
import os
import sqlite3

import pytest

from hutch import durable_changes
from hutch.models import Bot
from hutch.config import hutchConfig
from hutch.store import Store


@pytest.fixture
def installed(store):
    assert store.schema_version >= 11
    return store


def test_resource_and_change_commit_or_rollback_together(installed, config):
    store = installed
    with pytest.raises(RuntimeError):
        with store._tx() as db:
            db.execute("INSERT INTO bots(id,name,doc) VALUES ('rollback','rollback','{}')")
            raise RuntimeError("crash before commit")
    assert durable_changes.read(store._db)["changes"] == []
    bot = store.create_bot(Bot(name="outbox-secret", instructions="PRIVATE INSTRUCTIONS"))
    with sqlite3.connect(config.db_path) as observer:
        changes = durable_changes.read(observer)["changes"]
        assert observer.execute("SELECT id FROM bots").fetchone()[0] == bot.id
    assert [(c["resource"], c["resource_id"], c["operation"]) for c in changes] == [("bots", bot.id, "created")]
    assert "PRIVATE INSTRUCTIONS" not in json.dumps(changes)


def test_replay_survives_reopen_and_id_gaps(installed, config):
    store = installed
    store.create_bot(Bot(name="first"))
    first = durable_changes.read(store._db)["cursor"]
    # AUTOINCREMENT need not be contiguous. A cursor links committed rows.
    with store._tx() as db:
        db.execute("UPDATE sqlite_sequence SET seq = seq + 9 WHERE name = 'resource_outbox'")
    store.create_bot(Bot(name="second"))
    with sqlite3.connect(config.db_path) as observer:
        page = durable_changes.read(observer, first, 1)
        assert len(page["changes"]) == 1 and page["changes"][0]["id"] == 11
        assert durable_changes.read(observer, page["cursor"])["changes"] == []


@pytest.mark.parametrize("removal", ["leading", "middle", "all"])
def test_retention_gaps_force_snapshot_including_empty_history(installed, removal):
    store = installed
    for i in range(3):
        store.create_bot(Bot(name=f"outbox-{i}"))
    with store._tx() as db:
        db.execute({"leading": "DELETE FROM resource_outbox WHERE id = 1",
                    "middle": "DELETE FROM resource_outbox WHERE id = 2",
                    "all": "DELETE FROM resource_outbox"}[removal])
    with pytest.raises(durable_changes.SnapshotRequired, match="removed"):
        durable_changes.read(store._db)


def test_future_or_foreign_cursor_requires_snapshot(installed):
    epoch, _ = durable_changes.bounds(installed._db)
    for cursor in ("different:0", f"{epoch}:1", "malformed"):
        with pytest.raises(durable_changes.SnapshotRequired):
            durable_changes.read(installed._db, cursor)


def test_no_change_write_and_session_touch_do_not_emit(installed):
    store = installed
    bot = store.create_bot(Bot(name="stable-outbox"))
    first = durable_changes.read(store._db)["cursor"]
    with store._tx() as db:
        db.execute("UPDATE bots SET doc = doc WHERE id = ?", (bot.id,))
        db.execute("INSERT INTO device_sessions(id,label,token_hash,created_at,expires_at) "
                   "VALUES ('device','Phone','SECRET_TOKEN_HASH','start','later')")
    cursor = durable_changes.read(store._db, first)["cursor"]
    with store._tx() as db:
        db.execute("UPDATE device_sessions SET last_used_at = 'now', expires_at = 'later-again'")
    assert durable_changes.read(store._db, cursor)["changes"] == []
    assert "SECRET_TOKEN_HASH" not in json.dumps(durable_changes.read(store._db))


def _crash_writer(state_dir, committed):
    child = Store(hutchConfig(state_dir=state_dir))
    if committed:
        child.create_bot(Bot(name="committed-crash"))
    else:
        with child._tx() as db:
            db.execute("INSERT INTO bots(id,name,doc) VALUES ('uncommitted','uncommitted','{}')")
            os._exit(0)
    os._exit(0)


@pytest.mark.parametrize("committed", [False, True])
def test_process_death_cannot_separate_resource_and_outbox(store, config, committed):
    process = multiprocessing.get_context("spawn").Process(target=_crash_writer,
                                                           args=(config.state_dir, committed))
    process.start(); process.join(10)
    try:
        assert not process.is_alive() and process.exitcode == 0
        page = store.list_resource_changes()
        assert len(page["changes"]) == int(committed)
        assert len(store.list_bots()) == int(committed)
        if committed:
            assert page["changes"][0]["resource_id"] == store.list_bots()[0].id
    finally:
        if process.is_alive():
            process.kill(); process.join(5)


def _competing_writer(state_dir, index, ready):
    child = Store(hutchConfig(state_dir=state_dir))
    try:
        assert ready.wait(10)
        for i in range(4):
            child.create_bot(Bot(name=f"competing-{index}-{i}"))
    finally:
        child.close()


def test_competing_processes_preserve_one_committed_replay_chain(store, config):
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    processes = [context.Process(target=_competing_writer, args=(config.state_dir, i, ready)) for i in range(3)]
    for process in processes:
        process.start()
    ready.set()
    try:
        for process in processes:
            process.join(15)
            assert not process.is_alive() and process.exitcode == 0
        seen, cursor = [], None
        while True:
            page = store.list_resource_changes(cursor, 2)
            seen.extend(page["changes"])
            cursor = page["cursor"]
            if not page["has_more"]:
                break
        assert len(seen) == 12
        assert len({change["resource_id"] for change in seen}) == 12
        assert [change["id"] for change in seen] == sorted({change["id"] for change in seen})
    finally:
        for process in processes:
            if process.is_alive():
                process.kill(); process.join(5)


def test_snapshot_state_and_change_cursor_share_one_read_snapshot(store, config, monkeypatch):
    store.create_bot(Bot(name="before-snapshot"))
    observer = Store(config)
    original = durable_changes.bounds
    def concurrent_commit(db):
        position = original(db)
        observer.create_bot(Bot(name="during-snapshot"))
        return position
    monkeypatch.setattr(durable_changes, "bounds", concurrent_commit)
    try:
        snapshot = store.reconciliation_snapshot()
        assert [bot.name for bot in snapshot["items"]["bots"]] == ["before-snapshot"]
        monkeypatch.setattr(durable_changes, "bounds", original)
        page = store.list_resource_changes(snapshot["change_cursor"])
        assert len(page["changes"]) == 1
        assert page["changes"][0]["resource_id"] == observer.get_bot("during-snapshot").id
    finally:
        observer.close()


def test_upgrade_v10_preserves_state_and_initializes_fresh_change_history(config, monkeypatch):
    from hutch import store as store_module
    from hutch.transcript_mirror import TranscriptMirror
    migrations = store_module._MIGRATIONS
    version = store_module.SCHEMA_VERSION
    start = TranscriptMirror.start
    monkeypatch.setattr(TranscriptMirror, "start", lambda self: None)
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", 10)
    monkeypatch.setattr(store_module, "_MIGRATIONS", migrations[:9])
    legacy = Store(config)
    bot = legacy.create_bot(Bot(name="v10-preserved"))
    legacy.close()
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", version)
    monkeypatch.setattr(store_module, "_MIGRATIONS", migrations)
    monkeypatch.setattr(TranscriptMirror, "start", start)
    upgraded = Store(config)
    try:
        assert upgraded.get_bot(bot.id).name == "v10-preserved"
        assert upgraded.list_resource_changes()["changes"] == []
        assert upgraded.reconciliation_snapshot()["items"]["bots"][0].id == bot.id
        with sqlite3.connect(config.db_path.with_suffix(".db.bak-v10")) as backup:
            assert backup.execute("PRAGMA user_version").fetchone()[0] == 10
            assert backup.execute("SELECT id FROM bots").fetchone()[0] == bot.id
            assert backup.execute("SELECT 1 FROM sqlite_master WHERE name='resource_outbox'").fetchone() is None
        restored_config = hutchConfig(state_dir=config.state_dir / "restore-v10")
        restored_config.ensure()
        with sqlite3.connect(config.db_path.with_suffix(".db.bak-v10")) as backup:
            with sqlite3.connect(restored_config.db_path) as destination:
                backup.backup(destination)
        restored = Store(restored_config)
        try:
            assert restored.get_bot(bot.id).name == "v10-preserved"
            assert restored.schema_version == version
            with pytest.raises(durable_changes.SnapshotRequired):
                restored.list_resource_changes(upgraded.list_resource_changes()["cursor"])
        finally:
            restored.close()
    finally:
        upgraded.close()


def test_canonical_approval_summary_is_run_scoped_without_worker_resolution_event(store):
    from hutch.models import ApprovalRequest, ApprovalStatus, Event, EventType, Run, RunStatus
    bot = store.create_bot(Bot(name="summary-scope"))
    run = store.create_run(Run(bot_id=bot.id, prompt="review", status=RunStatus.running))
    other = store.create_run(Run(bot_id=bot.id, prompt="private peer", status=RunStatus.running))
    request = store.create_approval(ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="files", action="fixture"), begin_wait=True)
    peer = store.create_approval(ApprovalRequest(run_id=other.id, bot_id=bot.id, tool="files", action="private peer"), begin_wait=True)
    store.decide_approval(request.id, ApprovalStatus.denied, "second-client")
    events = store.list_events(run.id)
    assert not any(event.type is EventType.approval_resolved for event in events)
    states = store.approval_states_for_events(run.id, events + [Event(run_id=run.id,
        type=EventType.approval_request, data={"approval_id": peer.id})])
    assert set(states) == {request.id}
    assert states[request.id]["result"] == "denied" and states[request.id]["by"] == "second-client"
    assert states[request.id]["resolved_at"]
