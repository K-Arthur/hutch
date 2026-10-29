"""Whole-Bot permanent deletion: preview, confirmation, evidence and cleanup recovery."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from hutch import bot_deletion, fact_purge
from hutch.models import Bot, iso, utcnow
from hutch.store import Store

SENTINEL = 'PRIVATEBOTDELETIONSENTINEL'
OTHER_SENTINEL = 'SECONDBOTDELETIONSENTINEL'
digest = 'a' * 64
_REDACTED_TABLES = {'tool_actions', 'idempotency_keys', 'action_reconciliations', 'memory_fact_decisions'}


def now_iso() -> str:
    """One canonical timestamp for fixture rows."""
    return iso(utcnow())


def insert_row(db: sqlite3.Connection, table: str, **values) -> int:
    """Insert one explicit fixture row; callers pass every required column."""
    columns = ', '.join(values)
    marks = ', '.join('?' for _ in values)
    cursor = db.execute(f'INSERT INTO {table} ({columns}) VALUES ({marks})', tuple(values.values()))
    return int(cursor.lastrowid or 0)


def make_files(store, seed: dict) -> dict:
    """Create the managed files this Bot owns plus the user-owned paths that must survive."""
    state = Path(store.config.state_dir)
    created = {}

    def write(relative: str, text: str) -> Path:
        """Create one fixture file under the state directory."""
        path = state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    created['run_dir'] = write('bots/' + seed['name'] + '/runs/' + seed['run'] + '/workspace/artifact.txt', SENTINEL)
    created['workspace'] = write('workspaces/' + seed['bot'] + '/notes.txt', SENTINEL)
    created['profile'] = write('browser-profiles/' + seed['bot'] + '/profile.txt', SENTINEL)
    created['conversation'] = write('workspaces/' + seed['conversation'] + '/upload.txt', SENTINEL)
    created['document'] = write('documents/' + seed['document'] + '/v001-abcdef12/file.md', SENTINEL)
    created['synthesis'] = write('synthesis/' + seed['syn_storage_path'], SENTINEL)
    created['code_worktree'] = write('code-worktrees/' + seed['handoff'] + '/user-code.txt', SENTINEL)
    created['backup'] = write('hutch.db.bak-v82', 'backup')
    return created


def seed_bot(store, name: str, tag: str) -> dict:
    """Seed one rich Bot across the store families the erase inventory names."""
    db = store._db
    stamp = now_iso()
    digest = 'a' * 64 if tag == SENTINEL else 'b' * 64
    bot = store.create_bot(Bot(name=name, display_name=name.replace('-', ' ').title()))
    seed = {'bot': bot.id, 'name': name, 'tag': tag}
    conversation, message, run = _seed_core(store, db, bot, seed, stamp, tag, digest, name)
    _seed_store_records(db, bot, seed, stamp, tag, digest, conversation, run)
    _seed_workspace_and_investigations(db, bot, seed, stamp, tag, digest, name,
                                       conversation, message, run)
    _seed_synthesis(db, bot, seed, stamp, tag, digest, conversation, run)
    _seed_workflows(db, bot, seed, stamp, tag, digest, conversation, run)
    _seed_handoffs_and_sessions(store, db, bot, seed, stamp, tag, digest, conversation, message, run)
    question = 'q_' + bot.id
    insert_row(db, 'conversation_questions', id=question, conversation_id=conversation, run_id=run,
               bot_id=bot.id, assistant_message_id=message, question=tag, selection_mode='single',
               options_json=json.dumps([tag]), status='pending', created_at=stamp)
    db.execute('UPDATE messages SET choice_question_id = ? WHERE id = ?', (question, message))
    db.commit()
    fact = store.remember(bot.id, 'favourite-' + tag[-4:], tag, conversation_id=conversation)
    store.review_fact(bot.id, fact.id, content_hash=fact.content_hash, action='approve', actor='fixture')
    seed['fact'] = fact.id
    db.commit()
    seed['files'] = make_files(store, seed)
    return seed


def _seed_core(store, db, bot, seed, stamp, tag, digest, name):
    """Create the Bot's conversation, reply chain, run, receipts, budget and markers."""
    conversation = 'conv_' + bot.id
    seed['conversation'] = conversation
    insert_row(db, 'conversations', id=conversation, bot_id=bot.id, title=tag + ' chat',
               created_at=stamp, updated_at=stamp)
    message = 'msg_' + bot.id
    seed['message'] = message
    Store._insert_conversation_message(db, message_id=message, conversation_id=conversation, seq=1,
                                       run_id='', role='user', content=tag, created_at=stamp)
    assistant = 'amsg_' + bot.id
    seed['assistant_message'] = assistant
    Store._insert_conversation_message(db, message_id=assistant, conversation_id=conversation, seq=2,
                                       run_id='', role='assistant', content=tag + ' reply',
                                       created_at=stamp)
    reply = 'rmsg_' + bot.id
    Store._insert_conversation_message(db, message_id=reply, conversation_id=conversation, seq=3,
                                       run_id='', role='user', content=tag + ' follow-up',
                                       created_at=stamp, reply_to_message_id=assistant)
    run = 'run_' + bot.id
    seed['run'] = run
    insert_row(db, 'runs', id=run, bot_id=bot.id, doc=json.dumps({'prompt': tag, 'workspace': 'managed'}),
               status='succeeded', created_at=stamp, conversation_id=conversation)
    insert_row(db, 'events', run_id=run, ts=stamp, type='message', data=json.dumps({'text': tag}),
               seq=1, hash='h1', event_key='event-1-' + bot.id)
    insert_row(db, 'run_procs', run_id=run, pid=1, pgid=1, started_at=stamp)
    insert_row(db, 'run_compactions', id='compact_' + bot.id, run_id=run, seq=1, created_at=stamp,
               reason='budget', before_tokens=1, after_tokens=1, status='done', summary_text=tag)
    insert_row(db, 'transcript_delivery', run_id=run, bot_name=name, target_seq=1, delivered_seq=1,
               error='', file_size=1, file_mtime_ns=1)
    action = 'act_' + bot.id
    seed['action'] = action
    insert_row(db, 'tool_actions', id=action, run_id=run, tool='shell',
               idem_key='idem-action-' + bot.id,
               effect='process', summary=tag, status='done', started_at=stamp, finished_at=stamp,
               result_digest=digest, intent_json=json.dumps({'arguments': tag}), intent_hash=digest,
               result_json=json.dumps({'stdout': tag}))
    insert_row(db, 'action_reconciliations', action_id=action, run_id=run, intent_hash=digest,
               outcome='confirmed_done', evidence=tag, recorded_by='operator', recorded_at=stamp)
    insert_row(db, 'approvals', id='appr_' + bot.id, run_id=run, bot_id=bot.id, status='pending',
               created_at=stamp, doc=json.dumps({'action': tag, 'arguments': {'command': tag}}),
               action_hash=digest, expires_at=stamp)
    resets = {'bot': 'lifetime', 'run': 'run_lifetime', 'conversation': 'conversation_lifetime'}
    for scope_kind, scope_id in (('bot', bot.id), ('run', run), ('conversation', conversation)):
        insert_row(db, 'budget_policies', scope_kind=scope_kind, scope_id=scope_id, currency='USD',
                   reset=resets[scope_kind], revision=1, updated_at=stamp)
    insert_row(db, 'budget_pause_releases', scope_kind='bot', scope_id=bot.id, route_hash='route',
               cycle_key='cycle', policy_revision=1, quote_usd=0.0, approval_id='appr_' + bot.id,
               created_at=stamp, request_hash=digest)
    insert_row(db, 'budget_pause_releases', scope_kind='run', scope_id=run, route_hash='route',
               cycle_key='cycle', policy_revision=1, quote_usd=0.0, created_at=stamp,
               request_hash=digest)
    insert_row(db, 'kv', key='selfcheck:' + bot.id, value='1')
    insert_row(db, 'kv', key='schedule:' + bot.id + ':last_fire', value=stamp)
    generation = insert_row(db, 'doc_index_generations', status='active', source_hashes='{}',
                            created_at=stamp)
    chunk = insert_row(db, 'doc_index_chunks', generation=1, doc_name='global-doc.md',
                       doc_sha256=digest, page=1, chunk_index=0, extraction='text',
                       content='global user documentation')
    insert_row(db, 'doc_index_fts', rowid=chunk, content='global user documentation',
               doc_name='global-doc.md', doc_sha256=digest)
    return conversation, message, run


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

# ------------------------------------------------------------------- helpers

def all_tables(db: sqlite3.Connection) -> list[str]:
    """Every ordinary table, for content-leak scans."""
    return [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]


def scan_for_sentinel(db: sqlite3.Connection, sentinel: str) -> list[str]:
    """Every table and column that still stores one erased sentinel."""
    leaks = []
    for table in all_tables(db):
        columns = [row[1] for row in db.execute('PRAGMA table_info(' + table + ')')]
        if not columns:
            continue
        for row in db.execute('SELECT * FROM ' + table):
            blob = json.dumps({column: row[column] for column in columns}, default=str)
            if sentinel in blob:
                leaks.append(table)
                break
    return leaks


def scoped_rows(db: sqlite3.Connection, needles: set[str]) -> dict[str, list[str]]:
    """Canonical rows that mention any opaque id of the untouched Bot, per table."""
    found: dict[str, list[str]] = {}
    for table in all_tables(db):
        columns = [row[1] for row in db.execute('PRAGMA table_info(' + table + ')')]
        if not columns:
            continue
        rows = []
        for row in db.execute('SELECT * FROM ' + table):
            record = {column: row[column] for column in columns}
            if any(str(value) in needles for value in record.values() if isinstance(value, str)):
                rows.append(json.dumps(record, sort_keys=True, default=str))
        found[table] = sorted(rows)
    return found


def other_needles(seed: dict) -> set[str]:
    """Opaque ids and the sentinel that belong to the untouched Bot."""
    return {seed['bot'], seed['conversation'], seed['message'], seed['run'], seed['job'],
            seed['document'], seed['workspace_task'], seed['investigation'], seed['action'],
            seed['syn_manifest'], seed['workflow'], seed['handoff'], seed['name'],
            seed['tag'], seed['fact']}


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


# --------------------------------------------------------------------- tests

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
    assert counts['bot'] == 1 and counts['files'] == 6
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


def _assert_erased_shape(store, first, second, preview, result, untouched_before):
    """Assert the erased Bot leaves no content, tombstones receipts and keeps the second Bot."""
    db = store._db
    assert store.get_bot(first['bot']) is None
    assert store.get_bot(second['bot']) is not None
    # Cross-Bot shares are intentionally tombstoned/revoked content-free (the other Bot
    # sees a purged record, never the value), and the outbox records that change.
    after_scoped = scoped_rows(db, other_needles(second))
    shared = {'memory_fact_shares', 'conversation_artifact_shares', 'resource_outbox',
              'bot_deletions', 'idempotency_keys'}
    for table, rows in untouched_before.items():
        if table not in shared:
            assert after_scoped.get(table) == rows, table
    assert all('purged' in row or '"revoked_at": "2' in row or 'redacted' in row
               for row in after_scoped['memory_fact_shares'])
    assert scan_for_sentinel(db, SENTINEL) == []
    assert store.get_bot(second['bot']) is not None
    fts_rows = db.execute('SELECT content FROM conversation_fts').fetchall()
    assert all(SENTINEL not in str(row[0]) for row in fts_rows)
    fts_facts = db.execute('SELECT key, value FROM memory_facts_fts').fetchall()
    assert all(SENTINEL not in str(row[0]) + str(row[1]) for row in fts_facts)
    assert db.execute('SELECT COUNT(*) FROM conversation_questions').fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM conversations WHERE bot_id = ?", (first['bot'],)).fetchone()[0] == 0
    tombstone = db.execute('SELECT key, value, purged_at, purge_id, status FROM memory_facts '
                           'WHERE purge_id != \'\'').fetchone()
    assert tombstone['key'].startswith('purged:') and tombstone['value'] == ''
    assert tombstone['status'] == 'archived' and tombstone['purged_at'] and tombstone['purge_id']
    share = db.execute('SELECT fact_value, purged_at FROM memory_fact_shares '
                       'WHERE source_bot_id = ?', (first['bot'],)).fetchone()
    assert share['fact_value'] == 'purged' and share['purged_at']
    receipt = db.execute("SELECT response_json FROM idempotency_keys WHERE scope = ?",
                         ('api:v1:conversations:' + first['bot'],)).fetchone()
    assert receipt['response_json'] == '{"redacted": "[deleted]"}'
    assert db.execute("SELECT summary, intent_json, result_json FROM tool_actions WHERE id = ?",
                      (first['action'],)).fetchone()['summary'] == ''
    reconciliation = db.execute('SELECT evidence FROM action_reconciliations WHERE action_id = ?',
                                (first['action'],)).fetchone()
    assert reconciliation['evidence'] == '[deleted]'
    assert db.execute('SELECT note FROM memory_fact_decisions WHERE fact_id = ?',
                      (first['fact'],)).fetchone()['note'] == ''
    usage = db.execute('SELECT COUNT(*) FROM usage WHERE bot_id = ?', (first['bot'],)).fetchone()[0]
    assert usage == 1, 'spending history is retained content-free'
    assert db.execute('SELECT COUNT(*) FROM kv').fetchone()[0] == 4
    assert db.execute('SELECT COUNT(*) FROM doc_index_chunks').fetchone()[0] == 2
    assert db.execute('SELECT COUNT(*) FROM doc_index_fts').fetchone()[0] == 2
    evidence = db.execute('SELECT COUNT(*) FROM bot_deletion_items WHERE request_id = ?',
                          (preview['request_id'],)).fetchone()[0]
    assert evidence == preview['counts']['total']
    request = bot_deletion.request_record(store, preview['request_id'])
    assert request['status'] == 'confirmed' and request['cleanup_state'] == 'cleaned'
    assert request['result'] == result and not request['counts'] != preview['counts']
    rendered = json.dumps([request, bot_deletion.requests(store, first['bot'])])
    assert 'token' not in rendered and SENTINEL not in rendered


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


def _seed_store_records(db, bot, seed, stamp, tag, digest, conversation, run) -> None:
    """Fixture rows for job, event_sources, usage, documents, uploads and channels."""
    job = 'job_' + bot.id
    seed['job'] = job
    insert_row(db, 'jobs', id=job, bot_id=bot.id, kind='schedule',
               occurrence_key='2026-10-29T00:00:00Z-' + bot.id,
               created_at=stamp, updated_at=stamp, status='succeeded',
               input=json.dumps({'prompt': tag}))
    insert_row(db, 'job_steps', job_id=job, step_key='step-1', attempt=1, status='succeeded',
               output=json.dumps({'output': tag}), updated_at=stamp)
    source = 'src_' + bot.id
    insert_row(db, 'event_sources', id=source, bot_id=bot.id, kind='feed', name=tag,
               config=json.dumps({'url': tag}), next_check_at=stamp, created_at=stamp)
    insert_row(db, 'source_events', source_id=source, source_revision=1,
               event_key='source-event-1', kind='entry', occurrence='occ-1', summary=tag,
               received_at=stamp, run_id=run, job_id=job)
    insert_row(db, 'tasks', id='task_' + bot.id, bot_id=bot.id, kind='chat', prompt=tag, created_at=stamp)
    insert_row(db, 'schedule_identities', schedule_id='schedule:' + bot.id, bot_id=bot.id, created_at=stamp)
    insert_row(db, 'schedule_occurrences_v20', schedule_id='schedule:' + bot.id,
               occurrence='2026-10-29T00:00:00+00:00', bot_id=bot.id, run_id=run, claimed_at=stamp)
    insert_row(db, 'usage', ts=stamp, run_id=run, bot_id=bot.id, provider='mock', model='demo',
               prompt_tokens=1, completion_tokens=1, cached_tokens=0, cost_usd=0.0)
    insert_row(db, 'usage_reservations', id='res_' + bot.id, run_id=run, bot_id=bot.id, provider='mock',
               account_id='acct', model='demo', status='active', created_at=stamp)
    document = 'doc_' + bot.id
    seed['document'] = document
    insert_row(db, 'documents', id=document, bot_id=bot.id, conversation_id=conversation, title=tag,
               format='md', current_version=1, created_at=stamp)
    insert_row(db, 'document_versions', document_id=document, version=1, filename='file.md',
               storage_name='file.md', mime='text/markdown', bytes=1, sha256=digest,
               storage_path=document + '/v001-abcdef12/file.md', source='generated', run_id=run,
               validation_state='passed', preview_mode='download_only', created_at=stamp)
    insert_row(db, 'uploads', id='upl_' + bot.id, conversation_id=conversation, filename=tag,
               mime='text/plain', byte_size=1, sha256=digest, state='ready', created_at=stamp)
    channel = 'chan_' + bot.id
    insert_row(db, 'channel_connections', id=channel, kind='telegram', name=tag, bot_id=bot.id,
               credential_digest=digest, credential_ref='ref', remote_bot_id='remote-' + bot.id,
               allowed_senders='[]', accept_after=stamp, next_poll_at=stamp, created_at=stamp)
    event_id = insert_row(db, 'channel_events', channel_id=channel, revision=1, external_id='ext-1',
                          sender=tag, text=tag, content_hash=digest, received_at=stamp, run_id=run)
    insert_row(db, 'channel_deliveries', event_id=event_id, text=tag, next_attempt_at=stamp)
    insert_row(db, 'idempotency_keys', scope='api:v1:conversations:' + bot.id, key='receipt-key',
               request_hash=digest, response_json=json.dumps({'conversation_id': conversation, 'title': tag}),
               created_at=stamp)


def _seed_workspace_and_investigations(db, bot, seed, stamp, tag, digest, name, conversation,
                                      message, run) -> None:
    """Fixture rows for workspace tasks, checkpoints and investigations."""
    task = 'wtask_' + bot.id
    seed['workspace_task'] = task
    insert_row(db, 'workspace_tasks', id=task, parent_conversation_id=conversation, source_run_id=run,
               source_user_message_id=message, source_assistant_message_id=message,
               target_bot_id=bot.id, target_display_name=name, original_request=tag,
               proposed_brief=tag, task_brief=tag, child_conversation_id=conversation,
               child_run_id=run, created_at=stamp)
    event_row = db.execute('SELECT id FROM events WHERE run_id = ? ORDER BY id DESC LIMIT 1', (run,)).fetchone()
    insert_row(db, 'workspace_task_checkpoints', workspace_task_id=task, child_run_id=run,
               event_id=event_row[0], event_seq=1, event_type='message', run_status='succeeded',
               kind='terminal', recovery_state='none', created_at=stamp)
    investigation = 'inv_' + bot.id
    seed['investigation'] = investigation
    insert_row(db, 'investigations', id=investigation, run_id=run, conversation_id=conversation,
               bot_id=bot.id, question=tag, question_kind='general', status='done',
               reference_instant=stamp, as_of_instant=stamp, created_at=stamp, updated_at=stamp,
               revision=1, budget_json='{}', coverage_json='{}')
    insert_row(db, 'inv_sources', id='invsrc_' + bot.id, investigation_id=investigation, item_key='i1',
               adapter='web', lane='web', platform='web', kind='page', url=tag, canonical_url=tag,
               origin='web', origin_id='o1', title=tag, excerpt=tag, retrieved_at=stamp)
    insert_row(db, 'inv_claims', id='invclaim_' + bot.id, investigation_id=investigation, text=tag,
               created_at=stamp)
    insert_row(db, 'inv_evidence', id='invev_' + bot.id, investigation_id=investigation,
               claim_id='invclaim_' + bot.id, source_id='invsrc_' + bot.id, relation='supports',
               created_at=stamp)
    insert_row(db, 'inv_answers', id='invans_' + bot.id, investigation_id=investigation,
               body_json=json.dumps({'answer': tag}), effective_as_of=stamp, created_at=stamp)
    insert_row(db, 'inv_media', id='invmedia_' + bot.id, investigation_id=investigation, origin='web',
               local_path='/tmp/media', kind='image', sha256=digest, acquired_at=stamp)
    insert_row(db, 'inv_media_frames', media_id='invmedia_' + bot.id, at_ms=0, path='/tmp/frame.png',
               sha256=digest)
    insert_row(db, 'inv_observations', id='invobs_' + bot.id, investigation_id=investigation, kind='fact',
               text=tag, created_at=stamp)
    insert_row(db, 'inv_query_attempts', id='invqa_' + bot.id, investigation_id=investigation,
               adapter='web', state='done', started_at=stamp)
    insert_row(db, 'inv_stream_cursors', stream_key='stream-' + bot.id, investigation_id=investigation,
               adapter='web', instance='i1', cursor_kind='page', cursor_json='{}', updated_at=stamp)


def _seed_synthesis(db, bot, seed, stamp, tag, digest, conversation, run) -> None:
    """Fixture rows for synthesis manifests, artifacts, plans, sources and effects."""
    manifest = 'syn_' + bot.id
    seed['syn_manifest'] = manifest
    seed['syn_storage_path'] = manifest + '/audio/v001-abcdef12/out.wav'
    insert_row(db, 'syn_manifests', id=manifest, conversation_id=conversation, bot_id=bot.id, run_id=run,
               revision=1, status='committed', language='en', policy='default',
               doc=json.dumps({'summary': tag}), created_at=stamp, updated_at=stamp)
    insert_row(db, 'syn_manifest_revisions', manifest_id=manifest, revision=1, reason='initial',
               doc=json.dumps({'summary': tag}), created_at=stamp)
    insert_row(db, 'syn_artifacts', id='synart_' + bot.id, manifest_id=manifest, kind='audio', version=1,
               status='committed', storage_path=seed['syn_storage_path'], storage_name='out.wav',
               mime='audio/wav', bytes=1, sha256=digest, meta='{}', created_at=stamp)
    plan = 'synplan_' + bot.id
    insert_row(db, 'syn_plans', id=plan, conversation_id=conversation, bot_id=bot.id, run_id=run,
               status='done', approval_scope_hash=digest, doc=json.dumps({'plan': tag}),
               created_at=stamp, updated_at=stamp)
    insert_row(db, 'syn_sources', id='synsrc_' + bot.id, conversation_id=conversation, bot_id=bot.id,
               run_id=run, kind='web', identity='identity-' + bot.id, revision=1, title=tag,
               doc=json.dumps({'source': tag}), created_at=stamp, updated_at=stamp)
    insert_row(db, 'syn_effects', id='syneff_' + bot.id, plan_id=plan, step_id='step-1', kind='tool',
               idempotency_key='effect-key-' + bot.id, status='done', created_at=stamp,
               updated_at=stamp)


def _seed_workflows(db, bot, seed, stamp, tag, digest, conversation, run) -> None:
    """Fixture rows for workflow definitions, runs, nodes, questions and amendments."""
    insert_row(db, 'workflow_definitions', id='def_' + bot.id, name='workflow-' + bot.id,
               description='', active=1, source='fixture', created_at=stamp, updated_at=stamp)
    insert_row(db, 'workflow_revisions', id='rev1_' + bot.id, definition_id='def_' + bot.id, revision=1,
               plan_hash=digest, plan_json='{}', note='', created_by='fixture', created_at=stamp)
    insert_row(db, 'workflow_revisions', id='rev2_' + bot.id, definition_id='def_' + bot.id, revision=2,
               plan_hash=digest, plan_json='{}', note='', created_by='fixture', created_at=stamp)
    workflow = 'wf_' + bot.id
    seed['workflow'] = workflow
    insert_row(db, 'workflow_runs', id=workflow, definition_id='def_' + bot.id, revision_id='rev1_' + bot.id,
               plan_hash=digest, bot_id=bot.id, conversation_id=conversation, origin='user',
               status='succeeded', created_at=stamp, updated_at=stamp)
    insert_row(db, 'workflow_nodes', workflow_run_id=workflow, site_id='site-1',
               instance_key='node-1', kind='tool', status='succeeded', attempt=1)
    insert_row(db, 'workflow_questions', id='wfq_' + bot.id, workflow_run_id=workflow, site_id='site-1',
               instance_key='node-1', question=tag, status='answered', asked_at=stamp, expires_at=stamp)
    insert_row(db, 'workflow_amendment_history', id='wfam_' + bot.id, workflow_run_id=workflow,
               previous_revision_id='rev1_' + bot.id, adopted_revision_id='rev2_' + bot.id,
               previous_attempt_run_id=run, previous_status='succeeded', previous_plan_hash=digest,
               adopted_plan_hash=digest, preview_json=json.dumps({'preview': tag}), nodes_json='[]',
               questions_json='[]', result_json='{}', created_at=stamp)


def _seed_handoffs_and_sessions(store, db, bot, seed, stamp, tag, digest, conversation, message, run) -> None:
    """Fixture rows for code handoffs, media, persona feedback and conversation state."""
    handoff = 'handoff_' + bot.id
    seed['handoff'] = handoff
    insert_row(db, 'code_handoffs', id=handoff, conversation_id=conversation, bot_id=bot.id,
               source_run_id=run, source_user_message_id=message,
               source_assistant_message_id=message, original_request=tag, proposed_brief=tag,
               task_brief=tag, project_root='/home/user/project', project_name='project',
               project_device='1', project_inode=1, git_common_dir='/home/user/project/.git',
               base_commit='a' * 40, status='prepared', created_at=stamp, updated_at=stamp)
    insert_row(db, 'media_jobs', id='media_' + bot.id, run_id=run, conversation_id=conversation,
               kind='image', backend='local', status='succeeded',
               idempotency_key='media-key-' + bot.id,
               requested=tag, created_at=stamp, updated_at=stamp)
    insert_row(db, 'persona_feedback', conversation_id=conversation, message_id=message,
               feedback_version=1, revision=1, rating='helpful', reason=None, updated_at=stamp)
    insert_row(db, 'workspace_sessions', conversation_id=conversation, generation=1, status='active',
               env_fingerprint='env', workspace_dir=str(Path(store.config.state_dir) / 'workspaces' / conversation),
               created_at=stamp, updated_at=stamp)
    insert_row(db, 'conversation_task_state', conversation_id=conversation, revision=1,
               source_high_watermark=0, state_json=json.dumps({'state': tag}), updated_at=stamp)
    insert_row(db, 'conversation_task_state_revisions', conversation_id=conversation, revision=1,
               supersedes_revision=0, source_high_watermark=0, state_json=json.dumps({'state': tag}),
               created_at=stamp)
    insert_row(db, 'conversation_workflow_policies', conversation_id=conversation, mode='off',
               revision=1, updated_at=stamp)
    insert_row(db, 'conversation_runs', conversation_id=conversation, run_id=run, attached_at=stamp)
    insert_row(db, 'assistant_home_conversations', bot_id=bot.id, conversation_id=conversation,
               created_at=stamp)
    insert_row(db, 'tool_allows', bot_id=bot.id, sticky_key='allow-key', created_at=stamp)
    insert_row(db, 'google_mail_grants', bot_id=bot.id, account_id='google-account', granted_at=stamp)
    insert_row(db, 'outlook_mail_grants', bot_id=bot.id, account_id='outlook-account', granted_at=stamp)
    insert_row(db, 'integrations', integration_id='notebooklm-' + bot.id, revision='rev-1',
               title='NotebookLM', transport='in_process', credential_id='', state='operation_authorized',
               enabled=1, created_at=stamp)
    insert_row(db, 'integration_tool_grants', integration_id='notebooklm-' + bot.id, bot_id=bot.id,
               server_tool_name='search', canonical_name='mcp__notebooklm__search',
               schema_revision=digest, granted_at=stamp)
    insert_row(db, 'opencode_session_bindings', binding_key='binding-' + bot.id, bot_id=bot.id,
               route_hash='route', workspace='/tmp/workspace', policy_hash='policy', agent_id='agent',
               session_id='session', updated_at=stamp)
    insert_row(db, 'workspace_specialists', bot_id=bot.id, added_at=stamp)
