"""Whole-Bot permanent deletion: preview, confirmation, evidence and cleanup recovery."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
import pytest
from hutch import bot_deletion
from hutch.models import Bot
from hutch.store import Store
from tests.support.bot_deletion_seed import insert_row, now_iso, seed_bot
from tests.support.bot_deletion_assert import (
    SENTINEL,
    _assert_erased_shape,
    all_tables,
    other_needles,
    scan_for_sentinel,
    scoped_rows,
)


OTHER_SENTINEL = 'SECONDBOTDELETIONSENTINEL'

_REDACTED_TABLES = {'tool_actions', 'idempotency_keys', 'action_reconciliations', 'memory_fact_decisions'}

def seed_cross_links(store, source: dict, target: dict) -> None:
    """One fact share and one artifact share from the first Bot into the second Bot's chat."""
    db = store._db
    share, _ = store.create_fact_share_command(source['bot'], source['fact'], target['bot'],
                                               idem_key='share-' + source['bot'],
                                               request_hash='share-' + source['bot'])
    stamp = now_iso()
    event_id = insert_row(db, 'events', run_id=source['run'], ts=stamp, type='tool_result',
                          data=json.dumps({'artifact': SENTINEL, 'tool': 'shell'}), seq=2,
                          hash='h2', event_key='event-artifact-' + source['bot'])
    insert_row(db, 'conversation_artifact_shares', id='share_' + source['bot'],
               target_conversation_id=target['conversation'], source_run_id=source['run'],
               source_event_id=event_id, artifact_kind='tool_output', created_at=stamp, actor='fixture')
    db.commit()
    source['artifact_event'] = event_id
    source['share_id'] = share.id if hasattr(share, 'id') else share['id']


def table_diffs(store, counts: dict, before: dict[str, int], after: dict[str, int]) -> None:
    """Every erased category's preview count equals the rows that left its table."""
    for key, value in counts.items():
        if key in ('bot', 'files', 'total'):
            continue
        if key in bot_deletion_retained_changed():
            continue
        assert before.get(key, 0) - after.get(key, 0) == value, key


def bot_deletion_retained_changed() -> set[str]:
    """Categories whose rows are retained as content-free evidence, not removed."""
    return {'memory_facts', 'memory_fact_shares', 'workspace_task_fact_shares', 'tool_actions',
            'idempotency_keys', 'action_reconciliations', 'memory_fact_decisions',
            'conversation_artifact_shares'}


def table_counts(db: sqlite3.Connection) -> dict[str, int]:
    """Row count by table, used to prove preview counts equal actual changes."""
    return {table: int(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0])
            for table in all_tables(db) if not table.startswith('sqlite_')}


def erase(store, seed: dict, *, actor='operator', note='', idem_key=None) -> tuple[dict, dict]:
    """Preview then confirm one Bot."""
    preview = bot_deletion.preview(store, seed['bot'], actor=actor, note=note)
    result = bot_deletion.confirm(store, seed['bot'], preview['request_id'], token=preview['token'],
                                  confirmation=seed['name'], actor=actor, idem_key=idem_key)
    return preview, result


def test_preview_is_count_only_hashed_and_non_mutating(store):
    first = seed_bot(store, 'rich-bot', SENTINEL)
    second = seed_bot(store, 'other-bot', OTHER_SENTINEL)
    seed_cross_links(store, first, second)
    db = store._db
    before = table_counts(db)
    before.pop('bot_deletions', None)
    preview = bot_deletion.preview(store, first['bot'], actor='operator', note='reviewed')
    assert sorted(preview) == sorted(['request_id', 'token', 'expires_at', 'created_at', 'bot_id',
                                      'bot_name', 'counts', 'remaining', 'confirmation_hint'])
    assert preview['bot_id'] == first['bot'] and preview['bot_name'] == 'rich-bot'
    assert preview['confirmation_hint'] == 'rich-bot'
    assert preview['remaining'] and any('backups' in item for item in preview['remaining'])
    counts = preview['counts']
    assert counts['bot'] == 1 and counts['files'] == 7   # run dir, workspace, profile, conversation, document, synthesis, identity
    assert counts['messages'] == 3 and counts['runs'] == 1 and counts['approvals'] == 1
    assert counts['events'] == 2 and counts['documents'] == 1 and counts['files'] > 0
    assert counts['conversation_fts'] == 3
    assert counts['budget_policies'] == 3 and counts['budget_pause_releases'] == 2
    assert counts['total'] == sum(value for key, value in counts.items() if key != 'total')
    assert SENTINEL not in json.dumps(preview)
    row = db.execute('SELECT * FROM bot_deletions WHERE id = ?', (preview['request_id'],)).fetchone()
    import hashlib
    assert row['token_hash'] == hashlib.sha256(preview['token'].encode()).hexdigest()
    assert preview['token'] not in json.dumps(dict(row))
    assert row['bot_name_hash'] == hashlib.sha256(b'rich-bot').hexdigest()
    after_preview = table_counts(db)
    after_preview.pop('bot_deletions', None)
    assert after_preview == before, 'preview must only add its own request row'
    requests = bot_deletion.requests(store, first['bot'])
    assert requests and 'token' not in json.dumps(requests)
    assert requests[0]['request_id'] == preview['request_id'] and requests[0]['result'] == {}
    with pytest.raises(ValueError):
        bot_deletion.preview(store, 'bot_missing', actor='operator')
    second_preview = bot_deletion.preview(store, first['bot'], actor='operator')
    with pytest.raises(bot_deletion.BotDeletionConflict, match='no longer pending'):
        bot_deletion.confirm(store, first['bot'], preview['request_id'], token=preview['token'],
                             confirmation='rich-bot', actor='operator')
    assert bot_deletion.request_record(store, preview['request_id'])['status'] == 'superseded'
    assert second_preview['counts'] == counts


def test_preview_refuses_a_live_run(store):
    first = seed_bot(store, 'busy-bot', SENTINEL)
    store._db.execute("INSERT INTO runs (id, bot_id, doc, status, created_at) VALUES "
                      "('run_live', ?, '{}', 'running', ?)", (first['bot'], now_iso()))
    store._db.commit()
    with pytest.raises(bot_deletion.BotDeletionConflict, match='live runs'):
        bot_deletion.preview(store, first['bot'], actor='operator')
    assert store.get_bot(first['bot']) is not None


def test_confirm_erases_rich_bot_content_free_and_second_bot_untouched(store):
    first = seed_bot(store, 'rich-bot', SENTINEL)
    second = seed_bot(store, 'other-bot', OTHER_SENTINEL)
    seed_cross_links(store, first, second)
    db = store._db
    untouched_before = scoped_rows(db, other_needles(second))
    before = table_counts(db)
    preview, result = erase(store, first, idem_key='idem-rich')
    after = table_counts(db)
    assert sorted(result) == sorted(['request_id', 'status', 'deleted_at', 'counts',
                                     'remaining', 'cleanup_state'])
    assert result['status'] == 'confirmed' and result['request_id'] == preview['request_id']
    assert result['counts'] == preview['counts']
    assert result['cleanup_state'] == 'cleaned'
    table_diffs(store, preview['counts'], before, after)
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    _assert_erased_shape(store, first, second, preview, result, untouched_before)


def test_managed_files_removed_and_user_owned_paths_survive(store, tmp_path):
    first = seed_bot(store, 'rich-bot', SENTINEL)
    second = seed_bot(store, 'other-bot', OTHER_SENTINEL)
    seed_cross_links(store, first, second)
    files = {name: path for name, path in first['files'].items()
             if name not in ('code_worktree', 'backup')}
    folder_workdir = tmp_path / 'user-workdir'
    folder_workdir.mkdir()
    (folder_workdir / 'user-file.txt').write_text(SENTINEL, encoding='utf-8')
    exports = Path(store.config.state_dir) / 'exports'
    exports.mkdir()
    (exports / 'export.json').write_text('{}', encoding='utf-8')
    preview, _ = erase(store, first)
    for path in files.values():
        assert not path.exists(), path
    assert (folder_workdir / 'user-file.txt').read_text(encoding='utf-8') == SENTINEL
    assert first['files']['code_worktree'].exists()
    assert first['files']['backup'].exists()
    assert (exports / 'export.json').exists()
    assert (Path(store.config.state_dir) / 'hutch.db.bak-v82').exists()
    request = bot_deletion.request_record(store, preview['request_id'])
    assert request['cleanup_state'] == 'cleaned'


def test_confirm_fails_closed_and_nothing_is_erased(store):
    first = seed_bot(store, 'rich-bot', SENTINEL)
    second = seed_bot(store, 'other-bot', OTHER_SENTINEL)
    seed_cross_links(store, first, second)
    db = store._db
    messages_before = db.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
    with pytest.raises(KeyError):
        bot_deletion.confirm(store, first['bot'], 'del_missing', token='x' * 32,
                             confirmation='rich-bot', actor='operator')
    preview = bot_deletion.preview(store, first['bot'], actor='operator')
    with pytest.raises(bot_deletion.BotDeletionConflict, match='token'):
        bot_deletion.confirm(store, first['bot'], preview['request_id'], token='y' * 32,
                             confirmation='rich-bot', actor='operator')
    with pytest.raises(bot_deletion.BotDeletionConflict, match='typed Bot address'):
        bot_deletion.confirm(store, first['bot'], preview['request_id'], token=preview['token'],
                             confirmation='wrong-bot', actor='operator')
    renamed = 'rich-bot-renamed'
    db.execute('UPDATE bots SET name = ? WHERE id = ?', (renamed, first['bot']))
    db.commit()
    with pytest.raises(bot_deletion.BotDeletionConflict, match='address changed'):
        bot_deletion.confirm(store, first['bot'], preview['request_id'], token=preview['token'],
                             confirmation=renamed, actor='operator')
    db.execute('UPDATE bots SET name = ? WHERE id = ?', (first['name'], first['bot']))
    db.commit()
    changed = bot_deletion.preview(store, first['bot'], actor='operator')
    Store._insert_conversation_message(db, message_id='msg_extra_' + first['bot'],
                                       conversation_id=first['conversation'], seq=4, run_id='',
                                       role='user', content='late message', created_at=now_iso())
    db.commit()
    with pytest.raises(bot_deletion.BotDeletionConflict, match='changed since the preview'):
        bot_deletion.confirm(store, first['bot'], changed['request_id'], token=changed['token'],
                             confirmation='rich-bot', actor='operator')
    assert store.get_bot(first['bot']) is not None
    assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == messages_before + 1


def test_live_run_blocks_then_retry_replays(store):
    """A live run fails closed with a cancellation request, then an exact retry replays."""
    first = seed_bot(store, 'rich-bot', SENTINEL)
    db = store._db
    messages_before = db.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
    assert messages_before == 3
    live_preview = bot_deletion.preview(store, first['bot'], actor='operator')
    from hutch.models import Run
    live_run = store.create_run(Run(bot_id=first['bot'], prompt='live run'))
    db.execute("UPDATE runs SET status = 'running' WHERE id = ?", (live_run.id,))
    db.commit()
    with pytest.raises(bot_deletion.BotDeletionConflict, match='live run'):
        bot_deletion.confirm(store, first['bot'], live_preview['request_id'],
                             token=live_preview['token'], confirmation='rich-bot', actor='operator')
    assert db.execute('SELECT cancel_requested FROM runs WHERE id = ?',
                      (live_run.id,)).fetchone()[0] == 1
    assert store.get_bot(first['bot']) is not None
    assert db.execute('SELECT COUNT(*) FROM messages WHERE conversation_id = ?',
                      (first['conversation'],)).fetchone()[0] == messages_before
    db.execute('DELETE FROM runs WHERE id = ?', (live_run.id,))
    db.commit()
    final = bot_deletion.preview(store, first['bot'], actor='operator')
    result = bot_deletion.confirm(store, first['bot'], final['request_id'], token=final['token'],
                                  confirmation='rich-bot', actor='operator', idem_key='idem-final')
    assert result['status'] == 'confirmed'
    replay = bot_deletion.confirm(store, first['bot'], final['request_id'], token=final['token'],
                                  confirmation='rich-bot', actor='operator', idem_key='idem-final')
    assert replay == result
    restated = bot_deletion.confirm(store, first['bot'], final['request_id'], token=final['token'],
                                    confirmation='rich-bot', actor='operator')
    assert restated == result
    with pytest.raises(bot_deletion.BotDeletionConflict):
        bot_deletion.confirm(store, first['bot'], final['request_id'], token=final['token'],
                             confirmation='rich-bot', actor='operator', idem_key='other-key')


def test_expired_window_fails_closed(store, monkeypatch):
    first = seed_bot(store, 'rich-bot', SENTINEL)
    monkeypatch.setattr(bot_deletion, 'DELETION_TOKEN_TTL_SECONDS', -1)
    preview = bot_deletion.preview(store, first['bot'], actor='operator')
    with pytest.raises(bot_deletion.BotDeletionConflict, match='expired'):
        bot_deletion.confirm(store, first['bot'], preview['request_id'], token=preview['token'],
                             confirmation='rich-bot', actor='operator')
    assert store.get_bot(first['bot']) is not None
    expired = bot_deletion.request_record(store, preview['request_id'])
    assert expired['status'] == 'expired'
    row = store._db.execute('SELECT token_hash FROM bot_deletions WHERE id = ?',
                            (preview['request_id'],)).fetchone()
    assert row['token_hash'] == ''
    monkeypatch.setattr(bot_deletion, 'DELETION_TOKEN_TTL_SECONDS', 600)
    retry = bot_deletion.preview(store, first['bot'], actor='operator')
    bot_deletion.confirm(store, first['bot'], retry['request_id'], token=retry['token'],
                         confirmation='rich-bot', actor='operator')


def test_empty_bot_preview_is_valid_and_erase_is_all_zero_besides_bot(store):
    bot = store.create_bot(Bot(name='empty-bot', display_name='Empty'))
    preview = bot_deletion.preview(store, bot.id, actor='operator')
    assert preview['counts'] == {'bot': 1, 'total': 1}
    result = bot_deletion.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                                  confirmation='empty-bot', actor='operator')
    assert result['counts'] == {'bot': 1, 'total': 1}
    assert store.get_bot(bot.id) is None


def test_symlink_out_of_state_is_needs_attention(store, tmp_path):
    bot = store.create_bot(Bot(name='linked-bot', display_name='Linked'))
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'keep.txt').write_text(SENTINEL, encoding='utf-8')
    managed = Path(store.config.state_dir) / 'workspaces' / bot.id
    managed.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, managed)
    preview = bot_deletion.preview(store, bot.id, actor='operator')
    assert preview['counts']['files'] == 1
    result = bot_deletion.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                                  confirmation='linked-bot', actor='operator')
    assert result['status'] == 'confirmed'
    assert result['cleanup_state'] == 'needs_attention'
    record = bot_deletion.request_record(store, preview['request_id'])
    assert record['cleanup_state'] == 'needs_attention'
    assert record['result']['cleanup_state'] == 'needs_attention'
    assert (outside / 'keep.txt').read_text(encoding='utf-8') == SENTINEL
    row = store._db.execute('SELECT error FROM bot_deletions WHERE id = ?',
                            (preview['request_id'],)).fetchone()
    assert row['error'] and 'symbolic link' in row['error']
    assert str(outside) not in row['error']
    summary = bot_deletion.recover_cleanup(store)
    assert summary['needs_attention'] == [preview['request_id']] and summary['cleaned'] == []


def test_crash_after_commit_is_resumed_by_recover_cleanup(store, monkeypatch):
    first = seed_bot(store, 'rich-bot', SENTINEL)
    preview = bot_deletion.preview(store, first['bot'], actor='operator')
    evidence_before = None

    def explode(*args, **kwargs):
        """Simulate a process crash between commit and file cleanup."""
        raise RuntimeError('simulated crash during file cleanup')

    managed = {name: path for name, path in first['files'].items()
               if name not in ('code_worktree', 'backup')}
    monkeypatch.setattr(bot_deletion, '_remove_managed_path', explode)
    result = bot_deletion.confirm(store, first['bot'], preview['request_id'], token=preview['token'],
                                  confirmation='rich-bot', actor='operator')
    assert result['status'] == 'confirmed'
    assert result['cleanup_state'] == 'needs_attention'
    assert store.get_bot(first['bot']) is None
    assert bot_deletion.request_record(store, preview['request_id'])['cleanup_state'] == 'needs_attention'
    evidence_before = store._db.execute('SELECT COUNT(*) FROM bot_deletion_items WHERE request_id = ?',
                                        (preview['request_id'],)).fetchone()[0]
    monkeypatch.undo()
    summary = bot_deletion.recover_cleanup(store)
    assert summary['checked'] == 1 and summary['cleaned'] == [preview['request_id']]
    assert bot_deletion.request_record(store, preview['request_id'])['cleanup_state'] == 'cleaned'
    evidence_after = store._db.execute('SELECT COUNT(*) FROM bot_deletion_items WHERE request_id = ?',
                                       (preview['request_id'],)).fetchone()[0]
    assert evidence_after == evidence_before
    for path in managed.values():
        assert not path.exists()
    assert first['files']['code_worktree'].exists()
    assert bot_deletion.recover_cleanup(store) == {'checked': 0, 'cleaned': [], 'needs_attention': []}


def test_missing_manifest_is_needs_attention(store, monkeypatch):
    import shutil
    bot = store.create_bot(Bot(name='manifest-bot', display_name='Manifest'))
    preview = bot_deletion.preview(store, bot.id, actor='operator')
    monkeypatch.setattr(bot_deletion, '_cleanup_request', lambda *args, **kwargs: 'skipped')
    bot_deletion.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                         confirmation='manifest-bot', actor='operator')
    monkeypatch.undo()
    manifest_dir = Path(store.config.state_dir) / 'deletions' / preview['request_id']
    assert manifest_dir.exists()
    shutil.rmtree(manifest_dir)
    summary = bot_deletion.recover_cleanup(store)
    assert summary['needs_attention'] == [preview['request_id']]
    record = bot_deletion.request_record(store, preview['request_id'])
    assert record['cleanup_state'] == 'needs_attention'
    assert record['result']['status'] == 'confirmed'


def test_evidence_is_content_free_and_immutable_after_confirm(store):
    first = seed_bot(store, 'rich-bot', SENTINEL)
    preview, _ = erase(store, first)
    db = store._db
    leaks = scan_for_sentinel(db, SENTINEL)
    assert leaks == []
    items = db.execute('SELECT store_name, row_id, original_content_hash FROM bot_deletion_items '
                       'WHERE request_id = ?', (preview['request_id'],)).fetchall()
    assert items and all(len(item['row_id']) <= 128 for item in items)
    assert all(not item['row_id'].startswith('/') for item in items)
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        db.execute('UPDATE bot_deletion_items SET row_id = \'tampered\'')
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        db.execute('DELETE FROM bot_deletion_items')
    with pytest.raises(sqlite3.IntegrityError, match='retained'):
        db.execute('DELETE FROM bot_deletions')
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        db.execute("UPDATE bot_deletions SET result_json = '{}'")
