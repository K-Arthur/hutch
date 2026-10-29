"""Whole-Bot deletion surfaces: typed JSON API contract and the CLI destroy command.

The command layer (hutch.bot_deletion) owns erasure, evidence and cleanup; these
tests pin the HTTP and CLI shells that must share it: typed bodies, fail-closed
conflicts, local-owner permission, idempotent replay after the Bot is gone, and
the typed-address refusal.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch import bot_deletion
from hutch.cli import app as cli_app
from hutch.models import Bot, Run, RunStatus
from hutch.server.app import create_app
from hutch.server.bot_deletion_api import install_bot_deletion_routes, require_local_owner

PREVIEW_KEYS = {'request_id', 'token', 'expires_at', 'created_at', 'bot_id', 'bot_name',
                'counts', 'remaining', 'confirmation_hint'}
RESULT_KEYS = {'request_id', 'status', 'deleted_at', 'counts', 'remaining', 'cleanup_state'}
REQUEST_KEYS = {'request_id', 'bot_id', 'status', 'actor', 'note', 'created_at', 'expires_at',
                'confirmed_at', 'deleted_at', 'cleanup_state', 'counts', 'result'}
CLEANUP_STATES = {'none', 'pending', 'cleaning', 'cleaned', 'needs_attention'}
LOCAL_OWNER_REFUSAL = 'whole-Bot deletion is a local owner action'

runner = CliRunner()


@pytest.fixture()
def api(config):
    """One app instance with a live SQLite store behind the JSON API."""
    app = create_app()
    with TestClient(app) as client:
        yield client, app.state.store


def seed_bot(store, name='delete-me'):
    """Create one plain Bot with nothing to run, so only Bot-scoped rows count."""
    bot = store.create_bot(Bot(name=name, display_name=name.replace('-', ' ').title(),
                               model='mock/demo'))
    return bot


def preview_request(client, bot):
    """Issue a preview through the API and return its typed body."""
    response = client.post(f'/api/v1/bots/{bot.id}/deletion-requests',
                           json={'note': 'fixture deletion'})
    assert response.status_code == 201, response.text
    return response.json()


def confirm_request(client, bot, preview, *, key='confirm-key-1', confirmation=None):
    """Send one confirmation through the API with a caller-chosen idempotency key."""
    return client.post(
        f"/api/v1/bots/{bot.name}/deletion-requests/{preview['request_id']}/confirm",
        json={'token': preview['token'], 'confirmation': confirmation or bot.name},
        headers={'Idempotency-Key': key})


def test_preview_is_typed_and_history_is_content_free(api):
    client, store = api
    bot = seed_bot(store)
    preview = preview_request(client, bot)
    assert set(preview) == PREVIEW_KEYS
    assert preview['bot_id'] == bot.id and preview['bot_name'] == bot.name
    assert preview['confirmation_hint'] and preview['remaining']
    assert preview['counts'] and all(isinstance(value, int) for value in preview['counts'].values())
    assert preview['counts']['total'] >= 1 and len(preview['token']) >= 16

    base = f'/api/v1/bots/{bot.name}/deletion-requests'
    history = client.get(base)
    assert history.status_code == 200, history.text
    assert set(history.json()) == {'requests'}
    item = history.json()['requests'][0]
    assert set(item) == REQUEST_KEYS
    assert item['request_id'] == preview['request_id'] and item['bot_id'] == bot.id
    assert item['status'] == 'pending' and item['result'] == {} and item['counts']['total'] >= 1
    assert 'token' not in history.text and preview['token'] not in history.text

    assert client.get(base, params={'limit': 1}).status_code == 200
    assert client.get(base, params={'limit': 0}).status_code == 422
    assert client.get(base, params={'limit': 101}).status_code == 422
    assert client.post(base, json={'note': 'x' * 1001}).status_code == 422
    assert client.post(base, json={'note': '', 'unexpected': True}).status_code == 422
    assert client.post('/api/v1/bots/no-such-bot/deletion-requests', json={}).status_code == 404
    assert client.get('/api/v1/bots/no-such-bot/deletion-requests').status_code == 404


def test_confirm_is_fail_closed_and_typed(api):
    client, store = api
    bot = seed_bot(store, name='fail-closed-bot')
    preview = preview_request(client, bot)
    url = f"/api/v1/bots/{bot.name}/deletion-requests/{preview['request_id']}/confirm"
    payload = {'token': preview['token'], 'confirmation': bot.name}

    assert client.post(url, json=payload).status_code == 428
    assert client.post(url, json=payload,
                       headers={'Idempotency-Key': 'spaces here'}).status_code == 422
    assert client.post(url, json=payload,
                       headers={'Idempotency-Key': 'k' * 129}).status_code == 422
    assert client.post(url, json={'token': 'short', 'confirmation': bot.name},
                       headers={'Idempotency-Key': 'key-a'}).status_code == 422
    assert client.post(url, json={**payload, 'unexpected': 1},
                       headers={'Idempotency-Key': 'key-a'}).status_code == 422
    wrong_token = client.post(url, json={'token': 'x' * 32, 'confirmation': bot.name},
                              headers={'Idempotency-Key': 'key-a'})
    assert wrong_token.status_code == 409
    wrong_name = client.post(url, json={'token': preview['token'], 'confirmation': 'not-the-bot'},
                             headers={'Idempotency-Key': 'key-a'})
    assert wrong_name.status_code == 409
    assert store.get_bot(bot.id) is not None, 'a refused confirmation must not erase anything'
    missing = client.post(f'/api/v1/bots/{bot.id}/deletion-requests/req_missing/confirm',
                          json=payload, headers={'Idempotency-Key': 'key-b'})
    assert missing.status_code == 404
    no_bot = client.post('/api/v1/bots/no-such-bot/deletion-requests/req_missing/confirm',
                         json=payload, headers={'Idempotency-Key': 'key-b'})
    assert no_bot.status_code == 404


def test_confirm_refuses_a_request_belonging_to_another_bot(api):
    client, store = api
    first = seed_bot(store, name='delete-first')
    second = seed_bot(store, name='delete-second')
    preview = preview_request(client, first)
    response = client.post(
        f"/api/v1/bots/{second.name}/deletion-requests/{preview['request_id']}/confirm",
        json={'token': preview['token'], 'confirmation': second.name},
        headers={'Idempotency-Key': 'cross-bot'})
    assert response.status_code == 404
    assert store.get_bot(first.id) is not None and store.get_bot(second.id) is not None


def test_expired_confirmation_window_and_live_run_fail_closed(api, monkeypatch):
    client, store = api
    expired_bot = seed_bot(store, name='expired-bot')
    monkeypatch.setattr(bot_deletion, 'DELETION_TOKEN_TTL_SECONDS', -1)
    preview = preview_request(client, expired_bot)
    expired = confirm_request(client, expired_bot, preview)
    assert expired.status_code == 409
    assert store.get_bot(expired_bot.id) is not None
    monkeypatch.setattr(bot_deletion, 'DELETION_TOKEN_TTL_SECONDS', 600)
    busy_bot = seed_bot(store, name='busy-bot')
    store.create_run(Run(bot_id=busy_bot.id, prompt='live work', status=RunStatus.running))
    blocked = client.post(f'/api/v1/bots/{busy_bot.id}/deletion-requests', json={})
    assert blocked.status_code == 409
    assert store.get_bot(busy_bot.id) is not None


def test_confirm_deletes_replays_after_deletion_and_keeps_evidence(api):
    client, store = api
    bot = seed_bot(store, name='confirmed-bot')
    preview = preview_request(client, bot)
    base = f'/api/v1/bots/{bot.id}/deletion-requests'
    assert client.get(base).json()['requests'][0]['status'] == 'pending'

    done = confirm_request(client, bot, preview)
    assert done.status_code == 200, done.text
    result = done.json()
    assert set(result) == RESULT_KEYS and result['status'] == 'confirmed'
    assert result['request_id'] == preview['request_id'] and result['counts']['total'] >= 1
    assert result['cleanup_state'] in CLEANUP_STATES and result['deleted_at']
    assert preview['token'] not in done.text
    assert store.get_bot(bot.id) is None, 'the whole Bot row must be gone'

    replay = confirm_request(client, bot, preview)
    assert replay.status_code == 200 and replay.json() == result
    changed = confirm_request(client, bot, preview, key='another-key')
    assert changed.status_code == 409
    assert client.get(base).status_code == 404, 'history resolves a live Bot only'

    evidence = store._db.execute('SELECT status, cleanup_state, result_json, token_hash '
                                 'FROM bot_deletions').fetchall()
    assert len(evidence) == 1
    assert evidence[0]['status'] == 'confirmed' and evidence[0]['token_hash'] == ''
    assert evidence[0]['cleanup_state'] in CLEANUP_STATES - {'none'}
    assert preview['token'] not in json.dumps([dict(row) for row in evidence])
    assert store._db.execute('SELECT COUNT(*) FROM bot_deletion_items').fetchone()[0] >= 1


def test_post_deletion_replay_requires_the_typed_bot_address(api):
    client, store = api
    bot = seed_bot(store, name='address-bot')
    preview = preview_request(client, bot)
    done = confirm_request(client, bot, preview)
    assert done.status_code == 200, done.text
    wrong_name = client.post(
        f"/api/v1/bots/some-other-name/deletion-requests/{preview['request_id']}/confirm",
        json={'token': preview['token'], 'confirmation': bot.name},
        headers={'Idempotency-Key': 'confirm-key-1'})
    assert wrong_name.status_code == 404
    replay = confirm_request(client, bot, preview)
    assert replay.status_code == 200 and replay.json() == done.json()


def test_routes_refuse_a_paired_phone_principal(store):
    app = FastAPI()

    @app.middleware('http')
    async def _paired_principal(request, call_next):
        request.state.hutch_principal = {'kind': 'paired', 'credential_id': 'cred-1',
                                         'capabilities': ['monitor']}
        return await call_next(request)

    install_bot_deletion_routes(app, store)
    bot = seed_bot(store, name='paired-bot')
    with TestClient(app) as client:
        base = f'/api/v1/bots/{bot.name}/deletion-requests'
        calls = (
            lambda: client.post(base, json={}),
            lambda: client.get(base),
            lambda: client.post(base + '/req_missing/confirm',
                                json={'token': 't' * 32, 'confirmation': bot.name},
                                headers={'Idempotency-Key': 'paired-key'}),
        )
        for call in calls:
            response = call()
            assert response.status_code == 403, response.text
            assert response.json()['detail'] == LOCAL_OWNER_REFUSAL
    assert store.get_bot(bot.id) is not None


def test_require_local_owner_allows_the_local_operator_and_refuses_paired_phone():
    paired = SimpleNamespace(state=SimpleNamespace(
        hutch_principal={'kind': 'paired', 'credential_id': 'cred-1', 'capabilities': ['monitor']}))
    with pytest.raises(HTTPException) as caught:
        require_local_owner(paired)
    assert caught.value.status_code == 403
    assert caught.value.detail == LOCAL_OWNER_REFUSAL
    for principal in (None, {'kind': 'owner', 'capabilities': ['owner']}):
        request = SimpleNamespace(state=SimpleNamespace(hutch_principal=principal))
        require_local_owner(request)


def test_install_recovers_once_and_survives_a_recovery_failure(store, monkeypatch):
    calls = []

    def failing_recovery(store_arg):
        calls.append(store_arg)
        raise RuntimeError('cleanup recovery failed')

    monkeypatch.setattr(bot_deletion, 'recover_cleanup', failing_recovery)
    app = FastAPI()
    install_bot_deletion_routes(app, store)
    assert calls == [store]
    paths = {route.path for route in app.routes}
    assert {'/api/v1/bots/{ref}/deletion-requests',
            '/api/v1/bots/{ref}/deletion-requests/{request_id}/confirm'} <= paths


def test_cli_destroy_previews_then_erases_with_yes(tmp_path, monkeypatch):
    monkeypatch.setenv('HUTCH_STATE_DIR', str(tmp_path / 'state'))
    assert runner.invoke(cli_app, ['init']).exit_code == 0
    created = runner.invoke(cli_app, ['bot', 'create', 'destroy-cli', '--model', 'mock/demo'])
    assert created.exit_code == 0, created.output
    result = runner.invoke(cli_app, ['bot', 'destroy', 'destroy-cli', '--yes'])
    assert result.exit_code == 0, result.output
    output = result.output
    assert 'scope:' in output and 'erase:' in output and 'remains:' in output
    assert 'deleted' in output and 'evidence kept as' in output
    from hutch.cli import _store
    store = _store()
    try:
        assert store.get_bot('destroy-cli') is None
        row = store._db.execute('SELECT status, token_hash FROM bot_deletions').fetchone()
        assert row['status'] == 'confirmed' and row['token_hash'] == ''
    finally:
        store.close()


def test_cli_destroy_requires_the_typed_bot_address(tmp_path, monkeypatch):
    monkeypatch.setenv('HUTCH_STATE_DIR', str(tmp_path / 'state'))
    assert runner.invoke(cli_app, ['init']).exit_code == 0
    created = runner.invoke(cli_app, ['bot', 'create', 'careful-bot', '--model', 'mock/demo'])
    assert created.exit_code == 0, created.output
    refused = runner.invoke(cli_app, ['bot', 'destroy', 'careful-bot'], input='not-the-name\n')
    assert refused.exit_code == 1, refused.output
    assert 'did not match' in refused.output and 'nothing was erased' in refused.output
    from hutch.cli import _store
    store = _store()
    try:
        assert store.get_bot('careful-bot') is not None
        assert store._db.execute('SELECT COUNT(*) FROM bot_deletions').fetchone()[0] == 1
    finally:
        store.close()
    confirmed = runner.invoke(cli_app, ['bot', 'destroy', 'careful-bot'], input='careful-bot\n')
    assert confirmed.exit_code == 0, confirmed.output
    assert 'deleted' in confirmed.output
