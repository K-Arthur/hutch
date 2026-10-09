"""Restore must never dispatch or signal source ownership, even on the same boot."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch.cli import app
from hutch.config import hutchConfig
from hutch.durable_changes import SnapshotRequired
from hutch.engine import Engine
from hutch.models import ApprovalRequest, Bot, Event, EventType, Run, RunStatus, Schedule, Task
from hutch import procguard
from hutch.server.app import create_app
from hutch.state_snapshot import ExecutionHeld, backup, file_hash, restore
from hutch.store import SCHEMA_VERSION, Store


def source_work(store):
    bot = store.create_bot(Bot(name='restore-fixture', tools=[], schedule=Schedule(cron='* * * * *')))
    run = store.submit_run(Run(bot_id=bot.id, prompt='private unfinished work'), Task(bot_id=bot.id, prompt='private task'))
    run = store.claim_run(run.id, 'source-owner', 600)
    store.transition_run(run.id, RunStatus.running, fence=run.fence)
    store.append_event(Event(run_id=run.id, type=EventType.message, data={'role': 'assistant', 'content': 'private history'}))
    store.flush_events()
    action = store.begin_action(run.id, 'files_write', 'file-fixture', 'fs', arguments={'path': 'fixture.md'}, fence=run.fence)
    approval = store.create_approval(ApprovalRequest(run_id=run.id, bot_id=bot.id, tool='shell', action='private effect'))
    store.reserve_usage(run_id=run.id, bot_id=bot.id, provider='mock', account_id='fixture-account', model='demo',
                        reserved_tokens=100, reserved_cost_usd=0, expected_fence=run.fence)
    with store._tx() as db:
        db.execute('INSERT INTO tool_allows VALUES (?, ?, ?)', (bot.id, 'files:write', run.created_at))
    code = store.create_pairing_code()
    device, reason = store.exchange_pairing_code(code, 'private device label', 'fixture')
    assert reason == 'ok'
    return bot, run, action, approval, device


def test_live_wal_backup_then_restore_cannot_signal_or_replay_source(store, config, tmp_path, monkeypatch):
    bot, original, action, approval, device = source_work(store)
    queued = store.submit_run(Run(bot_id=bot.id, prompt='queued source'), Task(bot_id=bot.id, prompt='queued source'))
    task = store.enqueue_task(Task(bot_id=bot.id, prompt='unattached queue'))
    source = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
    snapshot, destination = tmp_path / 'snapshot', tmp_path / 'restored'
    try:
        identity = procguard.identity(source.pid)
        assert identity is not None
        source_boot = procguard.boot_id()
        store.add_proc(original.id, source.pid, identity.pgrp, identity.starttime, boot_id=source_boot)
        # A live reader/writer remains connected. Backup must capture committed WAL.
        manifest = backup(config, snapshot)
        assert manifest['schema'] == SCHEMA_VERSION and manifest['scope'] == 'database only'
        assert file_hash(snapshot / 'hutch.db') == manifest['database_sha256']
        report = restore(snapshot, destination)
        restored = Store(hutchConfig(destination))
        try:
            assert report['execution_held'] and report['source_processes_stopped'] is False
            assert report['counts']['runs'] == 2 and report['counts']['tasks'] == 3
            assert report['counts']['processes'] == 1
            assert restored.get_run(original.id).status is RunStatus.outcome_unknown
            assert restored.get_run(queued.id).status is RunStatus.outcome_unknown
            assert restored.get_run(original.id).fence > original.fence
            assert restored.get_run(original.id).pgid == 0
            assert restored.get_action(action)['status'] == 'unknown'
            assert restored.pending_tasks() == [] and restored.pending_approvals() == []
            assert restored.get_approval(approval.id).status.value == 'expired'
            assert restored.list_sticky_allows(bot.id) == []
            assert not restored.validate_device_token(device['token'])
            assert restored.get_bot(bot.id).paused
            assert restored.unresolved_usage_reservations()[0]['status'] == 'uncertain'
            assert restored.live_procs(original.id) == []
            detached = restored._db.execute('SELECT ended_at, detached_at, pid, boot_id FROM run_procs').fetchone()
            assert detached['ended_at'] is None and detached['detached_at']
            assert detached['pid'] == source.pid and detached['boot_id'] == source_boot
            assert restored.verify_chain(original.id)['ok']
            assert restored.list_events(original.id)[-1].data['source_processes_stopped'] is False
            with pytest.raises(SnapshotRequired):
                restored.list_resource_changes(store.list_resource_changes()['cursor'])
            with pytest.raises(ExecutionHeld):
                Engine(restored.config, restored, light=True).submit(restored.get_bot(bot.id), 'new work')
            assert not restored.claim_supervisor('copy-owner', 30)
            assert restored.claim_run(queued.id, 'copy-owner', 30, max_live=1) is None
            # Any attempt to terminate a process is a test failure, including recovery.
            monkeypatch.setattr(Engine, '_end_recorded_processes', lambda *args: pytest.fail('restore signalled source'))
            engine = Engine(restored.config, restored, light=True)
            assert engine.recover_orphans() == [] and engine.dispatch_pending() == 0
            assert source.poll() is None
            assert restored.activate_restoration(report['id'], 'Fixture source remains separate; no production activation')
            assert not restored.activate_restoration(report['id'], 'Fixture source remains separate; no production activation')
            with pytest.raises(ValueError, match='different review'):
                restored.activate_restoration(report['id'], 'changed')
            assert engine.dispatch_pending() == 0 and source.poll() is None
            assert restored.pending_tasks() == []  # explicit review never requeues the old tasks
            assert restored._db.execute('SELECT state FROM tasks WHERE id = ?', (task.id,)).fetchone()[0] == 'quarantined'
            fresh = engine.submit(restored.get_bot(bot.id), 'new explicit attempt')
            assert restored.claim_run(fresh.id, 'new-owner', 30, max_live=1)
            engine.shutdown()
        finally:
            restored.close()
        # Original source records and authorization were not changed by restoring a copy.
        assert store.get_run(original.id).status is RunStatus.running
        assert store.get_run(queued.id).status is RunStatus.pending
        assert store.get_action(action)['status'] == 'started'
        assert store.validate_device_token(device['token'])
        assert not store.get_bot(bot.id).paused and store.list_sticky_allows(bot.id) == ['files:write']
        assert source.poll() is None
    finally:
        source.terminate()
        source.wait(timeout=5)


def test_restore_preserves_explicit_cross_bot_fact_grants(store, config, tmp_path):
    source = store.create_bot(Bot(name='restore-share-source', display_name='Research Partner'))
    target = store.create_bot(Bot(name='restore-share-target', display_name='Brief Writer'))
    source_chat, _ = store.create_conversation(source.id, 'Reviewed sources', idem_key='restore-share-source-chat',
                                                request_hash='source')
    target_chat, _ = store.create_conversation(target.id, 'Draft', idem_key='restore-share-target-chat',
                                                request_hash='target')
    fact = store.remember(source.id, 'preferred-reference', 'Use the reviewed vendor guide.',
                          conversation_id=source_chat['id'])
    store.review_fact(source.id, fact.id, content_hash=fact.content_hash, action='approve', actor='fixture')
    grant, created = store.create_fact_share_command(source.id, fact.id, target.id,
                                                      idem_key='restore-share-create', request_hash='same')
    assert created

    snapshot, destination = tmp_path / 'fact-share-snapshot', tmp_path / 'fact-share-restored'
    backup(config, snapshot)
    report = restore(snapshot, destination)
    restored = Store(hutchConfig(destination))
    try:
        assert report['execution_held']
        shares = restored.fact_shares(target.id)
        assert shares['incoming'][0]['id'] == grant['id'] and shares['incoming'][0]['state'] == 'active'
        recalled = restored.recall_fact_page(target.id, conversation_id=target_chat['id'],
                                             query='vendor', limit=20)
        assert recalled[0]['share_id'] == grant['id'] and recalled[0]['shared_from'] == 'Research Partner'
        assert restored.restoration_status()['execution_held']
    finally:
        restored.close()


def test_legacy_restore_preserves_history_and_separately_quarantines_unfinished(tmp_path):
    original = hutchConfig(tmp_path / 'legacy')
    original.ensure()
    shutil.copy(Path(__file__).parent / 'fixtures/state_v4.db.fixture', original.db_path)
    snapshot = tmp_path / 'legacy-snapshot'
    backup(original, snapshot)
    report = restore(snapshot, tmp_path / 'legacy-restored')
    restored = Store(hutchConfig(tmp_path / 'legacy-restored'))
    try:
        assert report['source_schema'] == 4 and report['schema'] == SCHEMA_VERSION
        assert report['execution_held'] and report['counts']['runs'] == 2
        assert restored.get_run('run_582f4cc75ea4').status is RunStatus.succeeded
        assert restored.verify_chain('run_582f4cc75ea4')['ok']
        assert restored.get_run('run_3cefb894fd73').status is RunStatus.outcome_unknown
        assert len(restored.list_bots()) == 2
        assert (restored.config.state_dir / 'hutch.db.bak-v4').exists()
    finally:
        restored.close()


def test_damaged_manifest_or_database_refused_before_destination_creation(store, config, tmp_path):
    source_work(store)
    snapshot = tmp_path / 'snapshot'
    backup(config, snapshot)
    with (snapshot / 'hutch.db').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='hash'):
        restore(snapshot, tmp_path / 'copy')
    assert not (tmp_path / 'copy').exists()
    with pytest.raises(FileExistsError):
        backup(config, snapshot)


def test_bad_hash_chain_leaves_incomplete_copy_that_cannot_open(store, config, tmp_path):
    _, run, *_ = source_work(store)
    snapshot = tmp_path / 'snapshot'
    backup(config, snapshot)
    db = sqlite3.connect(snapshot / 'hutch.db')
    db.execute("UPDATE events SET data = '{}' WHERE run_id = ?", (run.id,))
    db.commit()
    db.close()
    path = snapshot / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['database_sha256'] = file_hash(snapshot / 'hutch.db')
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='hash chain'):
        restore(snapshot, tmp_path / 'copy')
    assert (tmp_path / 'copy/.restore-in-progress').exists()
    with pytest.raises(RuntimeError, match='incomplete'):
        Store(hutchConfig(tmp_path / 'copy'))


def test_restore_refuses_existing_state_and_links(store, config, tmp_path):
    snapshot = tmp_path / 'snapshot'
    backup(config, snapshot)
    with pytest.raises(RuntimeError, match='cannot be used as executor'):
        Store(hutchConfig(snapshot))
    with pytest.raises(FileExistsError):
        restore(snapshot, config.state_dir)
    before = file_hash(snapshot / 'hutch.db')
    shutil.move(snapshot / 'hutch.db', snapshot / 'real.db')
    (snapshot / 'hutch.db').symlink_to(snapshot / 'real.db')
    with pytest.raises(ValueError, match='no links'):
        restore(snapshot, tmp_path / 'copy')
    assert file_hash(snapshot / 'real.db') == before


def test_wal_sidecars_cannot_bypass_snapshot_digest(store, config, tmp_path):
    snapshot = tmp_path / 'snapshot'
    backup(config, snapshot)
    assert not (snapshot / 'hutch.db-wal').exists()
    db = sqlite3.connect(snapshot / 'hutch.db')
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("INSERT INTO kv VALUES ('changed', 'outside standalone snapshot')")
        db.commit()
        with pytest.raises(ValueError, match='sidecars'):
            restore(snapshot, tmp_path / 'copy')
        assert not (tmp_path / 'copy').exists()
    finally:
        db.close()


def test_two_local_reviews_resolve_once_and_hold_survives_restart(store, config, tmp_path):
    import threading
    source_work(store)
    snapshot, destination = tmp_path / 'snapshot', tmp_path / 'copy'
    backup(config, snapshot)
    report = restore(snapshot, destination)
    one, two = Store(hutchConfig(destination)), Store(hutchConfig(destination))
    barrier, results = threading.Barrier(2), []
    def activate(s, evidence):
        barrier.wait()
        try:
            results.append(s.activate_restoration(report['id'], evidence))
        except ValueError as exc:
            results.append(str(exc))
    try:
        assert one.restoration_status()['execution_held'] and two.restoration_status()['execution_held']
        threads = [threading.Thread(target=activate, args=(one, 'First local fixture review')),
                   threading.Thread(target=activate, args=(two, 'Second local fixture review'))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            assert not thread.is_alive()
        assert results.count(True) == 1
        assert sum(isinstance(r, str) and 'different review record' in r for r in results) == 1
        assert not one.restoration_status()['execution_held']
    finally:
        one.close()
        two.close()
    reopened = Store(hutchConfig(destination))
    try:
        assert not reopened.restoration_status()['execution_held']
        assert reopened.active_runs() == [] and reopened.pending_tasks() == []
    finally:
        reopened.close()


def test_held_api_rejects_new_work_but_keeps_readable_report(store, config, tmp_path, monkeypatch):
    bot, *_ = source_work(store)
    snapshot = tmp_path / 'snapshot'
    backup(config, snapshot)
    report = restore(snapshot, tmp_path / 'copy')
    monkeypatch.setenv('HUTCH_STATE_DIR', str(tmp_path / 'copy'))
    application = create_app()
    with TestClient(application) as client:
        assert client.get('/api/v1/health').json()['execution_held']
        assert client.get('/api/stats').json()['execution_held']
        page = client.get('/api/v1/state/restore?limit=2').json()
        assert page['report']['id'] == report['id'] and len(page['items']) == 2
        assert 'private' not in json.dumps(page)
        assert client.get('/api/v1/state/restore?limit=201').status_code == 422
        response = client.post(f'/api/bots/{bot.name}/run', json={'prompt': 'must not dispatch'})
        assert response.status_code == 409 and response.json()['code'] == 'restore_review_required'
        assert client.get('/api/v1/tasks/runs').status_code == 200
        changes = client.get('/api/v1/changes')
        assert changes.status_code == 200, changes.text
        assert any(change['resource'] == 'state' for change in changes.json()['changes'])


def test_cli_restore_report_activation_and_changed_release(store, config, tmp_path, monkeypatch):
    source_work(store)
    runner = CliRunner()
    snapshot, destination = tmp_path / 'snapshot', tmp_path / 'copy'
    assert runner.invoke(app, ['state', 'backup', str(snapshot)]).exit_code == 0
    result = runner.invoke(app, ['state', 'restore', str(snapshot), '--to', str(destination)])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    monkeypatch.setenv('HUTCH_STATE_DIR', str(destination))
    assert runner.invoke(app, ['state', 'report', report['id'], '--limit', '1']).exit_code == 0
    assert 'execution held' in runner.invoke(app, ['status']).output
    monkeypatch.setattr('hutch.state_snapshot.code_hash', lambda: 'changed-release')
    result = runner.invoke(app, ['state', 'activate', report['id'], '--evidence', 'Reviewed fixture'])
    assert result.exit_code == 1 and 'changed since restore' in result.output
