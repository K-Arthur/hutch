"""No unreserved maintenance generations in a Hutch-owned OpenCode runtime."""

import json
import shutil
from contextlib import ExitStack

import pytest

from hutch.runtime.opencode_server import OpenCodeServer, OpenCodeServerError, _write_runtime_config


def test_runtime_config_cannot_reenable_maintenance_from_supplied_agents(tmp_path):
    primary = {'mode': 'primary', 'system': 'Reviewed task', 'model': 'test/model'}
    agents = {'hutch-test': primary, 'title': {'disabled': False, 'model': 'paid/title'}}
    payload = json.loads(_write_runtime_config(tmp_path, agents).read_text())
    assert payload['update'] == 'disable'
    assert payload['compaction']['auto'] is False
    assert payload['warming'] is False
    assert payload['agents']['hutch-test'] == primary
    for name in ('title', 'summary', 'compaction'):
        assert payload['agents'][name] == {'disabled': True}
    assert agents['title']['disabled'] is False  # caller data was not mutated


def test_two_owned_runtime_configs_do_not_overwrite_each_others_agent_or_bridge(tmp_path):
    first = _write_runtime_config(tmp_path, {'hutch-first': {'system': 'First scope'}}, ['first-owned-bridge'])
    second = _write_runtime_config(tmp_path, {'hutch-second': {'system': 'Second scope'}}, ['second-owned-bridge'])
    assert first != second
    a, b = json.loads(first.read_text()), json.loads(second.read_text())
    assert 'hutch-first' in a['agents'] and 'hutch-second' not in a['agents']
    assert 'hutch-second' in b['agents'] and 'hutch-first' not in b['agents']
    assert a['plugins'] == ['first-owned-bridge'] and b['plugins'] == ['second-owned-bridge']


@pytest.mark.parametrize('failure', ['version', 'spawn', 'ready', 'controls'])
def test_startup_failure_removes_only_its_owned_config(tmp_path, monkeypatch, failure):
    from hutch.code_handoff import write_profile_config
    persistent = write_profile_config(tmp_path)
    sibling = _write_runtime_config(tmp_path, {'hutch-other': {'system': 'Other task'}})
    original = persistent.read_bytes(), sibling.read_bytes()
    server = OpenCodeServer(tmp_path, agents={'hutch-test': {'mode': 'primary'}})
    monkeypatch.setattr(server, '_version_major', lambda *a, **k: 1 if failure == 'version' else 2)
    if failure == 'spawn':
        def spawn(*a, **k):
            raise OSError('synthetic spawn failure')
        monkeypatch.setattr('hutch.runtime.opencode_server.subprocess.Popen', spawn)
    elif failure != 'version':
        class Process:
            stderr = None
            def poll(self): return 0
        monkeypatch.setattr('hutch.runtime.opencode_server.subprocess.Popen', lambda *a, **k: Process())
        def fail(*a, **k):
            raise OpenCodeServerError('synthetic preflight failure')
        monkeypatch.setattr(server, '_wait_ready', fail if failure == 'ready' else lambda: None)
        monkeypatch.setattr(server, '_verify_runtime_controls', fail)
    with pytest.raises(OpenCodeServerError):
        server.start()
    server.close()  # idempotent; never removes a different server's profile
    assert list(sibling.parent.glob('runtime-config-*.json')) == [sibling]
    assert (persistent.read_bytes(), sibling.read_bytes()) == original
    assert server.process is None


@pytest.mark.parametrize('fault', ['', 'activation-timeout', 'missing-config', 'auto-compaction', 'warming', 'later-title', 'active-agent', 'wrong-404'])
def test_runtime_controls_read_back_and_refuse_unverified_maintenance_before_inference(tmp_path, monkeypatch, fault):
    server = OpenCodeServer(tmp_path, agents={'hutch-test': {'mode': 'primary'}})
    config = _write_runtime_config(tmp_path, server.agents)
    payload = {'update': 'disable', 'compaction': {'auto': False}, 'warming': False,
               'agents': {name: {'disabled': True} for name in ('title', 'summary', 'compaction')}}
    entries = [{'type': 'document', 'path': str(config), 'info': payload}]
    if fault == 'missing-config':
        entries = []
    if fault == 'auto-compaction':
        payload['compaction']['auto'] = True
    if fault == 'warming':
        payload['warming'] = True
    if fault == 'later-title':
        entries.append({'type': 'document', 'path': str(tmp_path / 'later.json'),
                        'info': {'agents': {'title': {'system': 'Recreated maintenance'}}}})
    requests = []
    def metadata(path, params, **kwargs):
        requests.append((path, params))
        assert params == {'location[directory]': str(tmp_path)}
        if path == '/api/model':
            if fault == 'activation-timeout':
                raise OpenCodeServerError('plugins not ready', status=503)
            return {'data': []}
        if path == '/api/config':
            return entries
        name = path.rsplit('/', 1)[-1]
        if fault == 'active-agent':
            return {'data': {'id': name, 'hidden': True}}
        body = {'_tag': 'AgentNotFoundError', 'agentID': name, 'message': 'not found'}
        if fault == 'wrong-404':
            body['_tag'] = 'LocationNotFoundError'
        raise OpenCodeServerError('unavailable', status=404, body=json.dumps(body))
    monkeypatch.setattr(server, '_get_with_params', metadata)
    if fault:
        with pytest.raises(OpenCodeServerError, match='maintenance'):
            server._verify_runtime_controls(config, tmp_path)
    else:
        server._verify_runtime_controls(config, tmp_path)
        assert [path for path, _ in requests] == ['/api/model', '/api/config', '/api/agent/title', '/api/agent/summary', '/api/agent/compaction']


@pytest.mark.skipif(shutil.which('opencode') is None, reason='installed OpenCode V2 required; no model or credential needed')
def test_installed_cli_applies_runtime_controls_and_exact_agent_permissions_without_inference(tmp_path):
    from hutch.runtime.opencode import _agent_definition
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    agent_id, agent = _agent_definition('controls-probe', title='Configuration probe',
                                      instructions='No inference is requested.', provider_id='test', model_id='model',
                                      tool_names=set(), workspace=str(workspace))
    with OpenCodeServer(tmp_path / 'profile', agents={agent_id: agent}, cwd=workspace, startup_timeout=20) as server:
        params = {'location[directory]': str(workspace)}
        loaded = server._get_with_params('/api/agent/' + agent_id, params, timeout=5)['data']
        assert loaded['id'] == agent_id
        assert loaded['system'] == agent['system']
        assert loaded['model'] == {'providerID': 'test', 'id': 'model'}
        # V2 appends a native browser denial after the configured rules. Check
        # effective last-match decisions, including defaults, rather than an
        # assumed array suffix that fails on a stricter native rule.
        for expected in agent['permissions']:
            matches = [rule for rule in loaded['permissions']
                       if rule['action'] in ('*', expected['action']) and rule['resource'] == '*']
            assert matches[-1] == expected
        for name in ('title', 'summary', 'compaction'):
            with pytest.raises(OpenCodeServerError) as error:
                server._get_with_params('/api/agent/' + name, params, timeout=5)
            assert error.value.status == 404
            assert json.loads(error.value.body)['_tag'] == 'AgentNotFoundError'


@pytest.mark.skipif(shutil.which('opencode') is None, reason='installed OpenCode V2 required; no model or credential needed')
def test_two_installed_servers_keep_distinct_agents_and_cleanup_shared_profile(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    params = {'location[directory]': str(workspace)}
    paths = []
    with ExitStack() as stack:
        servers = []
        for name in ('first', 'second'):
            agent_id = 'hutch-' + name
            agent = {'mode': 'primary', 'system': name + ' task scope', 'model': 'test/' + name}
            server = stack.enter_context(OpenCodeServer(tmp_path / 'profile', agents={agent_id: agent}, cwd=workspace))
            servers.append((server, agent_id, agent))
            paths.append(server._runtime_config)
        for server, agent_id, expected in servers:
            actual = server._get_with_params('/api/agent/' + agent_id, params, timeout=5)['data']
            assert actual['system'] == expected['system']
            assert actual['model']['id'] == agent_id.removeprefix('hutch-')
            other_id = 'hutch-second' if agent_id == 'hutch-first' else 'hutch-first'
            with pytest.raises(OpenCodeServerError) as error:
                server._get_with_params('/api/agent/' + other_id, params, timeout=5)
            assert error.value.status == 404
        servers[0][0].close()
        assert not paths[0].exists() and paths[1].exists()
        assert servers[1][0]._get_with_params('/api/agent/hutch-second', params, timeout=5)['data']['system'] == 'second task scope'
    assert not any(path.exists() for path in paths)
