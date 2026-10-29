"""Revoked artifact-share history survives a whole-Bot deletion without crashing readers.

The v83 rebuild makes the share's source ids nullable so a revoked cross-chat
grant can outlive the Bot that produced it. These are the defensive read paths:
the active reader must exclude the revoked row, and a revoke (fresh or replayed)
must return the revoked history instead of raising on a deleted source run/event.
"""
from __future__ import annotations

import hashlib

from hutch import bot_deletion
from hutch.models import Bot, Event, EventType, Run, RunStatus


def seed_shared_artifact(store, config):
    """Create a source Bot with a verified artifact shared into a second Bot's chat."""
    source = store.create_bot(Bot(name='share-source', model='mock/demo', tools=[]))
    target = store.create_bot(Bot(name='share-target', model='mock/demo', tools=[]))
    source_conversation, _ = store.create_conversation(
        source.id, 'Private source', idem_key='share-source-chat', request_hash='share-source-chat')
    target_conversation, _ = store.create_conversation(
        target.id, 'Selected recipient', idem_key='share-target-chat', request_hash='share-target-chat')
    run = Run(bot_id=source.id, prompt='build report', conversation_id=source_conversation['id'],
              status=RunStatus.succeeded)
    store.create_run(run)
    with store._tx() as db:
        db.execute('INSERT INTO conversation_runs (conversation_id, run_id, attached_at) '
                   'VALUES (?, ?, ?)', (source_conversation['id'], run.id, run.created_at))
    payload = b'approved report contents\n'
    filename = '001-report.txt'
    artifact_dir = config.run_dir(source.name, run.id) / 'artifacts'
    artifact_dir.mkdir(parents=True)
    (artifact_dir / filename).write_bytes(payload)
    store.append_event(Event(run_id=run.id, type=EventType.tool_result, data={
        'tool': 'write_file', 'output': 'report saved', 'chars': len(payload),
        'artifact': f'artifacts/{filename}', 'artifact_sha256': hashlib.sha256(payload).hexdigest(),
        'artifact_bytes': len(payload),
        'workspace_file': {'artifact': f'artifacts/{filename}',
                           'sha256': hashlib.sha256(payload).hexdigest(),
                           'bytes': len(payload), 'name': 'report.txt', 'path': 'report.txt'},
    }))
    store.flush_events()
    share, created = store.share_conversation_artifact(
        target_conversation['id'], run.id, 1, 'workspace_file', actor='operator',
        idem_key='share-report', request_hash='share-report-request')
    assert created is True
    return source, target, source_conversation, target_conversation, run, share


def test_whole_bot_deletion_keeps_revoked_share_history_readable(store, config):
    source, target, _source_chat, target_chat, run, share = seed_shared_artifact(store, config)
    run_dir = config.run_dir(source.name, run.id)
    assert run_dir.exists()

    preview = bot_deletion.preview(store, source.id, actor='test')
    result = bot_deletion.confirm(
        store, source.id, preview['request_id'], token=preview['token'],
        confirmation=source.name, actor='test', idem_key='delete-source',
        request_hash='delete-source-request')
    assert result['status'] == 'confirmed'
    assert store.get_bot(source.id) is None and store.get_bot(target.id) is not None
    assert not run_dir.exists(), 'managed run files are part of the deletion'

    evidence = store._db.execute('SELECT * FROM conversation_artifact_shares WHERE id = ?',
                                 (share['id'],)).fetchone()
    assert evidence is not None, 'revoked cross-chat history survives the deletion'
    assert evidence['revoked_at'] and evidence['source_run_id'] is None
    assert evidence['source_event_id'] is None
    assert evidence['target_conversation_id'] == target_chat['id']
    assert store.active_conversation_artifact_share(target_chat['id'], share['id']) is None

    revoked, changed = store.revoke_conversation_artifact_share(
        target_chat['id'], share['id'], actor='operator',
        idem_key='revoke-after-delete', request_hash='revoke-after-delete-request')
    assert changed is False
    assert revoked['id'] == share['id'] and revoked['revoked_at']
    assert revoked['source_version'] is None, 'a deleted source reports no resurrected version'

    replay, changed_again = store.revoke_conversation_artifact_share(
        target_chat['id'], share['id'], actor='operator',
        idem_key='revoke-after-delete', request_hash='revoke-after-delete-request')
    assert changed_again is False
    assert replay['id'] == share['id'] and replay['source_version'] is None
