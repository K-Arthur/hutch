"""Governed permanent deletion of saved reference facts: erasure, audit, fail-closed paths."""
import json
import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch import fact_purge
from hutch.cli import app as cli_app
from hutch.fact_memory import FactConflict, validate as validate_facts
from hutch.fact_purge_schema import migrate as migrate_purge_schema
from hutch.models import Bot, iso, utcnow
from hutch.server.app import create_app
from hutch.store import Store

SENTINEL = 'PRIVATEPURGESENTINEL'
runner = CliRunner()


def seed(store, name='purge-facts', key='favourite-colour', value=SENTINEL):
    bot = store.create_bot(Bot(name=name, display_name=name.replace('-', ' ').title()))
    conv, _ = store.create_conversation(bot.id, name + '-chat', idem_key=name + '-chat',
                                        request_hash=name + '-chat')
    fact = store.remember(bot.id, key, value, conversation_id=conv['id'])
    store.review_fact(bot.id, fact.id, content_hash=fact.content_hash, action='approve', actor='fixture')
    return bot, conv, fact


def seed_share(store, source, fact, target):
    share, _ = store.create_fact_share_command(source.id, fact.id, target.id,
                                               idem_key='share-' + fact.id, request_hash='share-' + fact.id)
    return share


def erase(store, bot, *, key=None, all_facts=False, confirmation=None):
    preview = fact_purge.preview(store, bot.id, key=key, all=all_facts, actor='fixture')
    expected = confirmation if confirmation is not None else (key if key else bot.name)
    return preview, fact_purge.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                                       confirmation=expected, actor='fixture')


def assert_memory_content_gone(store):
    for table in ('memory_facts', 'memory_fact_shares', 'workspace_task_fact_shares', 'memory'):
        for row in store._db.execute('SELECT * FROM ' + table):
            assert SENTINEL not in json.dumps(dict(row), default=str), table


def test_purge_erases_content_but_keeps_content_free_audit(store):
    bot, conv, fact = seed(store)
    other, _, _ = seed(store, name='purge-other', key='other-key', value='OTHER-SENTINEL')
    preview = fact_purge.preview(store, bot.id, key='favourite-colour', actor='fixture')
    assert preview['counts'] == {'fact_revisions': 1, 'legacy_rows': 0, 'outgoing_shares': 0,
                                 'incoming_shares': 0, 'task_snapshots': 0, 'total': 1}
    assert preview['remaining'] and 'backups' in ' '.join(preview['remaining'])
    result = fact_purge.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                                confirmation='favourite-colour', actor='fixture')
    assert result['counts']['total'] == 1 and result['status'] == 'confirmed'
    assert_memory_content_gone(store)
    assert store.recall_all(bot.id) == []
    assert store.fact_page(bot.id, admin=True, query=SENTINEL) == []
    rows = store._db.execute('SELECT id, key, value, status, purged_at FROM memory_facts').fetchall()
    tombstone = [dict(row) for row in rows if row['id'] == fact.id][0]
    assert tombstone['key'] == 'purged:' + fact.id and tombstone['value'] == ''
    assert tombstone['status'] == 'archived' and tombstone['purged_at']
    assert [fact.key for fact in store.recall_all(other.id)] == ['other-key']
    request = fact_purge.requests(store, bot.id)[0]
    assert request['status'] == 'confirmed' and request['counts']['total'] == 1
    assert 'token' not in json.dumps(request)
    items = store._db.execute('SELECT table_name, row_id, original_content_hash FROM memory_purge_items').fetchall()
    assert [(row['table_name'], row['row_id']) for row in items] == [('memory_facts', fact.id)]
    assert items[0]['original_content_hash'] == fact.content_hash
    validate_facts(store._db)


def test_shared_snapshot_content_erased_in_both_directions(store):
    source, _, fact = seed(store)
    target = store.create_bot(Bot(name='purge-target'))
    seed_share(store, source, fact, target)
    assert store.fact_shares(target.id)['incoming'][0]['state'] == 'active'
    _, result = erase(store, source, key='favourite-colour')
    assert result['counts']['outgoing_shares'] == 1
    assert store.fact_shares(target.id)['incoming'] == []
    share_rows = store._db.execute('SELECT fact_key, fact_value, purged_at FROM memory_fact_shares').fetchall()
    assert len(share_rows) == 1 and share_rows[0]['fact_value'] == 'purged' and share_rows[0]['purged_at']
    assert_memory_content_gone(store)
    validate_facts(store._db)


def test_all_scope_erases_legacy_rows_and_requires_the_bot_address(store):
    bot, _, _ = seed(store)
    seed(store, name='purge-second', key='second-key', value='SECOND-SENTINEL')
    store._db.execute("INSERT INTO memory (bot_id, key, value, updated_at) VALUES (?, 'favourite-colour', ?, ?)",
                      (bot.id, SENTINEL, iso(utcnow())))
    store._db.commit()
    preview = fact_purge.preview(store, bot.id, all=True, actor='fixture')
    assert preview['counts']['legacy_rows'] == 1
    with pytest.raises(FactConflict, match='confirmation'):
        fact_purge.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                           confirmation='wrong-bot', actor='fixture')
    assert store.recall_all(bot.id), 'a failed confirmation must not erase anything'
    result = fact_purge.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                                confirmation=bot.name, actor='fixture')
    assert result['counts']['fact_revisions'] == 1 and result['counts']['legacy_rows'] == 1
    assert store.recall_all(bot.id) == []
    assert store._db.execute('SELECT COUNT(*) FROM memory').fetchone()[0] == 0
    assert_memory_content_gone(store)


def test_purge_confirmation_fails_closed_and_is_idempotent(store):
    bot, _, _ = seed(store)
    preview = fact_purge.preview(store, bot.id, key='favourite-colour', actor='fixture')
    with pytest.raises(FactConflict, match='token'):
        fact_purge.confirm(store, bot.id, preview['request_id'], token='x' * 32,
                           confirmation='favourite-colour', actor='fixture')
    with pytest.raises(FactConflict, match='confirmation'):
        fact_purge.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                           confirmation='wrong-key', actor='fixture')
    assert store.recall_all(bot.id)[0].key == 'favourite-colour'
    second = fact_purge.preview(store, bot.id, key='favourite-colour', actor='fixture')
    result = fact_purge.confirm(store, bot.id, second['request_id'], token=second['token'],
                                confirmation='favourite-colour', actor='fixture')
    replay = fact_purge.confirm(store, bot.id, second['request_id'], token=second['token'],
                                confirmation='favourite-colour', actor='fixture')
    assert replay == result
    with pytest.raises(FactConflict, match='nothing saved'):
        fact_purge.preview(store, bot.id, key='favourite-colour', actor='fixture')


def test_purge_preview_supersedes_older_pending_requests(store):
    bot, _, _ = seed(store)
    first = fact_purge.preview(store, bot.id, key='favourite-colour', actor='fixture')
    second = fact_purge.preview(store, bot.id, key='favourite-colour', actor='fixture')
    with pytest.raises(FactConflict, match='no longer pending'):
        fact_purge.confirm(store, bot.id, first['request_id'], token=first['token'],
                           confirmation='favourite-colour', actor='fixture')
    assert fact_purge.requests(store, bot.id)[0]['id'] == second['request_id']


def test_expired_confirmation_window_fails_closed(store, monkeypatch):
    bot, _, _ = seed(store)
    monkeypatch.setattr(fact_purge, 'PURGE_TOKEN_TTL_SECONDS', -1)
    preview = fact_purge.preview(store, bot.id, key='favourite-colour', actor='fixture')
    with pytest.raises(FactConflict, match='expired'):
        fact_purge.confirm(store, bot.id, preview['request_id'], token=preview['token'],
                           confirmation='favourite-colour', actor='fixture')
    assert store.recall_all(bot.id)[0].key == 'favourite-colour'
    monkeypatch.setattr(fact_purge, 'PURGE_TOKEN_TTL_SECONDS', 600)
    retry = fact_purge.preview(store, bot.id, key='favourite-colour', actor='fixture')
    result = fact_purge.confirm(store, bot.id, retry['request_id'], token=retry['token'],
                                confirmation='favourite-colour', actor='fixture')
    assert result['status'] == 'confirmed'


def test_purge_api_is_typed_two_step_and_content_free(config):
    app = create_app()
    with TestClient(app) as client:
        store = app.state.store
        bot, _, _ = seed(store)
        base = '/api/v1/bots/' + bot.id + '/facts/purge-requests'
        assert client.post(base, json={'key': 'favourite-colour', 'all': True}).status_code == 422
        preview = client.post(base, json={'key': 'favourite-colour', 'note': 'fixture purge'})
        assert preview.status_code == 201, preview.text
        body = preview.json()
        assert body['scope_kind'] == 'key' and body['counts']['total'] == 1 and len(body['token']) >= 16
        confirm_url = base + '/' + body['request_id'] + '/confirm'
        payload = {'token': body['token'], 'confirmation': 'favourite-colour'}
        assert client.post(confirm_url, json=payload).status_code == 428
        wrong = client.post(confirm_url, json={**payload, 'confirmation': 'wrong'},
                            headers={'Idempotency-Key': 'purge-confirm'})
        assert wrong.status_code == 409
        done = client.post(confirm_url, json=payload, headers={'Idempotency-Key': 'purge-confirm'})
        assert done.status_code == 200, done.text
        assert done.json()['counts']['total'] == 1 and SENTINEL not in done.text
        replay = client.post(confirm_url, json=payload, headers={'Idempotency-Key': 'purge-confirm'})
        assert replay.status_code == 200 and replay.json() == done.json()
        listing = client.get(base)
        assert listing.status_code == 200 and 'token' not in listing.text and SENTINEL not in listing.text
        assert listing.json()['requests'][0]['status'] == 'confirmed'
        assert client.get('/api/v1/bots/' + bot.id + '/facts').json()['facts'] == []
        assert client.get('/api/v1/bots/' + bot.id + '/fact-shares').json()['incoming'] == []
        assert client.post('/api/v1/bots/missing/facts/purge-requests', json={'key': 'x'}).status_code == 404
        assert client.post(confirm_url, json=payload, headers={'Idempotency-Key': 'other'}).json() == done.json()


def test_purge_schema_migration_is_idempotent_and_guarded():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    try:
        db.execute('CREATE TABLE memory_facts (id TEXT PRIMARY KEY, bot_id TEXT NOT NULL, scope_kind TEXT NOT NULL,'
                   ' scope_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, revision INTEGER NOT NULL,'
                   ' content_hash TEXT NOT NULL, run_id TEXT NOT NULL, source TEXT NOT NULL, updated_at TEXT NOT NULL,'
                   " status TEXT NOT NULL)")
        db.execute('CREATE TABLE memory_fact_shares (id TEXT PRIMARY KEY, source_fact_id TEXT NOT NULL,'
                   ' source_bot_id TEXT NOT NULL, source_display_name TEXT NOT NULL, source_scope_kind TEXT NOT NULL,'
                   ' source_scope_id TEXT NOT NULL, target_bot_id TEXT NOT NULL, target_display_name TEXT NOT NULL,'
                   ' fact_key TEXT NOT NULL, fact_value TEXT NOT NULL, fact_revision INTEGER NOT NULL,'
                   ' content_hash TEXT NOT NULL, created_at TEXT NOT NULL, revoked_at TEXT, revoked_by TEXT NOT NULL DEFAULT \'\')')
        db.execute('CREATE TABLE workspace_task_fact_shares (id INTEGER PRIMARY KEY AUTOINCREMENT,'
                   ' workspace_task_id TEXT NOT NULL, source_fact_id TEXT NOT NULL, source_bot_id TEXT NOT NULL,'
                   ' source_display_name TEXT NOT NULL, source_scope_kind TEXT NOT NULL, source_scope_id TEXT NOT NULL,'
                   ' fact_key TEXT NOT NULL, fact_value TEXT NOT NULL, fact_revision INTEGER NOT NULL,'
                   ' content_hash TEXT NOT NULL, created_at TEXT NOT NULL)')
        migrate_purge_schema(db)
        migrate_purge_schema(db)
        for table in ('memory_facts', 'memory_fact_shares', 'workspace_task_fact_shares'):
            columns = {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')}
            assert 'purged_at' in columns, table
        assert {'memory_purge_requests', 'memory_purge_items'} <= set(
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        db.execute("INSERT INTO memory_facts VALUES ('fact_a', 'bot_a', 'bot', 'bot_a', 'k', 'PRIVATE', 1,"
                   " 'h', '', 'user', 'now', 'approved', '', '')")
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            db.execute("UPDATE memory_facts SET value = 'changed' WHERE id = 'fact_a'")
        db.execute("INSERT INTO memory_purge_requests (id, bot_id, scope_kind, scope_key, actor, note,"
                   " request_hash, token_hash, created_at, expires_at, status, counts_json)"
                   " VALUES ('req_a', 'bot_a', 'key', 'k', 'fixture', '', '" + 'a' * 64 + "', '" + 'b' * 64 + "',"
                   " 'now', 'later', 'pending', '{}')")
        with pytest.raises(sqlite3.IntegrityError, match='evidence'):
            db.execute("DELETE FROM memory_purge_requests WHERE id = 'req_a'")
        db.execute("UPDATE memory_facts SET status = 'archived' WHERE id = 'fact_a'")
        db.execute("UPDATE memory_facts SET key = 'purged:fact_a', value = '', content_hash = 'h',"
                   " purged_at = 'now', purge_id = 'request_a' WHERE id = 'fact_a'")
        assert db.execute('SELECT key FROM memory_facts').fetchone()[0] == 'purged:fact_a'
    finally:
        db.close()


def test_cli_purge_previews_then_erases_after_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv('HUTCH_STATE_DIR', str(tmp_path / 'state'))
    assert runner.invoke(cli_app, ['init']).exit_code == 0
    created = runner.invoke(cli_app, ['bot', 'create', 'purge-cli', '--model', 'mock/demo'])
    assert created.exit_code == 0, created.output
    from hutch.cli import _store
    store = _store()
    bot = store.get_bot('purge-cli')
    conv, _ = store.create_conversation(bot.id, 'cli-chat', idem_key='cli-chat', request_hash='cli-chat')
    fact = store.remember(bot.id, 'cli-key', SENTINEL, conversation_id=conv['id'])
    store.review_fact(bot.id, fact.id, content_hash=fact.content_hash, action='approve', actor='fixture')
    store.close()
    result = runner.invoke(cli_app, ['bot', 'purge', 'purge-cli', '--key', 'cli-key', '--yes'])
    assert result.exit_code == 0, result.output
    assert 'remains:' in result.output and 'erased' in result.output
    store = _store()
    try:
        assert store.recall_all(bot.id) == []
    finally:
        store.close()
