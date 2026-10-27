"""Opt-in real installed-webview checks; no renderer mock or provider call."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
from urllib.parse import urlsplit

import httpx
import pytest

from tests.support.artifacts import artifact_path
from hutch import procguard


def _port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def test_installed_desktop_owns_a_private_working_webview(tmp_path):
    application = os.environ.get('HUTCH_DESKTOP_BINARY')
    if not application:
        pytest.skip('set HUTCH_DESKTOP_BINARY to an installed or bundled native app')
    assert Path(application).is_file(), 'the explicitly selected desktop binary must exist'
    driver = shutil.which('tauri-driver')
    assert driver, 'install pinned tauri-driver for native validation'
    assert shutil.which('WebKitWebDriver'), 'install the matching native WebKit driver'
    assert procguard.available() and procguard.pidfd_available(), 'Linux native validation requires verified cleanup'
    port, native_port = _port(), _port()
    while native_port == port:
        native_port = _port()
    env = {**os.environ, 'HUTCH_STATE_DIR': str(tmp_path / 'state'),
           'XDG_DATA_HOME': str(tmp_path / 'data'), 'XDG_CONFIG_HOME': str(tmp_path / 'config'),
           'XDG_CACHE_HOME': str(tmp_path / 'cache')}
    # All profile data is fresh. Never import account keys, a developer profile
    # or a browser session just to make this native journey appear connected.
    for name in ('HUTCH_AUTH_TOKEN', 'HUTCH_REMOTE_ENABLED', 'HUTCH_TESTING', 'HUTCH_SANDBOX', 'PYTHONPATH',
                 'OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'):
        env.pop(name, None)
    log = tmp_path / 'native-driver.log'
    session = None
    with log.open('wb') as stream, httpx.Client(base_url=f'http://127.0.0.1:{port}',
                                               timeout=45, trust_env=False) as client:
        # tauri-driver 2.1.0 binds its intermediary to loopback itself; its
        # --native-host option configures only the underlying WebKit driver.
        process = subprocess.Popen([driver, '--port', str(port),
            '--native-host', '127.0.0.1', '--native-port', str(native_port)], env=env,
            stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, start_new_session=True)
        owner = procguard.identity(process.pid)
        assert owner is not None and owner.pgrp == process.pid
        try:
            deadline = time.monotonic() + 20
            while True:
                assert process.poll() is None, 'native driver exited before readiness; inspect its isolated log'
                try:
                    status = client.get('/status', timeout=1)
                    if status.status_code == 200 and status.json().get('value', {}).get('ready') is True:
                        break
                except httpx.TransportError:
                    pass
                assert time.monotonic() < deadline, 'native driver did not become ready'
                time.sleep(.1)
            response = client.post('/session', json={'capabilities': {'alwaysMatch': {
                'tauri:options': {'application': str(Path(application).resolve())}}}})
            assert response.status_code == 200, 'native WebDriver session could not start; inspect its isolated log'
            session = response.json()['value']['sessionId']

            def execute(script, args=()):
                result = client.post(f'/session/{session}/execute/sync', json={'script': script, 'args': list(args)})
                assert result.status_code == 200, 'native script command failed'
                value = result.json()['value']
                assert not (isinstance(value, dict) and value.get('error')), 'native script returned a WebDriver error'
                return value

            def execute_async(script, args=()):
                result = client.post(f'/session/{session}/execute/async', json={'script': script, 'args': list(args)})
                assert result.status_code == 200, 'native async script command failed'
                value = result.json()['value']
                assert not (isinstance(value, dict) and value.get('error')), 'native async script returned a WebDriver error'
                return value

            def app_api(path, options=None):
                result = execute_async('''const done = arguments[arguments.length-1];
                  api(arguments[0], arguments[1]).then(value => done({ok:true, value}))
                    .catch(() => done({ok:false}));''', (path, options or {}))
                assert result.get('ok') is True, 'owned native app API request failed'
                return result['value']

            deadline = time.monotonic() + 45
            while not execute("return !!document.querySelector('#first-run-readiness');"):
                assert time.monotonic() < deadline, 'installed app did not open its first-run workspace'
                time.sleep(.1)
            origin = execute('return location.origin;')
            parsed = urlsplit(origin)
            assert parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port
            assert not execute("return document.cookie.includes('hutch_auth=');"), 'owner cookie must be HttpOnly'
            # A plain external HTTP client lacks the webview's owner authority.
            assert httpx.get(origin + '/api/bots', trust_env=False, timeout=5).status_code == 401
            assert execute("return typeof window.__TAURI__ === 'undefined';")
            execute("location.hash = '#/connections'; return true;")
            deadline = time.monotonic() + 20
            while not execute("return !!document.querySelector('[data-connection-entry]');"):
                assert time.monotonic() < deadline, 'Apps & AI did not render in the installed webview'
                time.sleep(.1)
            labels = execute("return document.body.innerText;")
            for label in ('Google Drive', 'Google Docs', 'Google Sheets', 'Google Calendar'):
                assert label in labels
            assert execute('return document.documentElement.scrollWidth <= innerWidth + 1;')
            screenshot = client.get(f'/session/{session}/screenshot')
            assert screenshot.status_code == 200
            pixels = base64.b64decode(screenshot.json()['value'], validate=True)
            assert pixels.startswith(b'\x89PNG\r\n\x1a\n') and len(pixels) <= 5_000_000
            out = artifact_path('native-desktop')
            out.mkdir(parents=True, exist_ok=True)
            (out / 'installed-connections.png').write_bytes(pixels)
            # Prove the bundled Python contains the actual pure workflow module,
            # and WebKit can review/save its result. The named local route is
            # deliberately unused: no installed model or account is required.
            report_bot = app_api('/bots', {'method':'POST', 'body': {
                'name':'native-report-check', 'model':'ollama/unused-native-fixture',
                'tools':[], 'instructions':'Native deterministic report fixture.',
            }})
            assert report_bot['name'] == 'native-report-check'
            execute("location.hash = '#/chat/native-report-check'; return true;")
            deadline = time.monotonic() + 20
            while not execute("return !!document.querySelector('#composer-menu-btn');"):
                assert time.monotonic() < deadline, 'native report chat did not render'
                time.sleep(.1)
            execute("document.querySelector('#composer-menu-btn').click(); document.querySelector('#campaign-report-open').click(); return true;")
            source = ('campaign,impressions,clicks,spend,conversions,revenue,daily_budget\n'
                      'Search,10000,1000,300,20,1000,250\nSocial,20000,400,150,0,0,200\n')
            execute('''const field=document.querySelector('#campaign-source'); field.value=arguments[0];
              field.dispatchEvent(new Event('input',{bubbles:true}));
              document.querySelector('#modal-confirm').click(); return true;''', (source,))
            deadline = time.monotonic() + 20
            while not execute("return document.querySelector('#campaign-preview')?.hidden === false;"):
                assert time.monotonic() < deadline, 'native report preview did not render'
                time.sleep(.1)
            assert execute("return document.querySelector('#campaign-preview').textContent.includes('Reporting period unknown');")
            assert execute("return document.querySelector('#campaign-preview tbody tr:nth-child(2) td:nth-child(4)').textContent;") == '—'
            assert not app_api('/v1/workflows/runs?bot=native-report-check')['items']
            execute("document.querySelector('#modal-confirm').click(); return true;")
            deadline = time.monotonic() + 20
            report_detail = None
            while time.monotonic() < deadline:
                reports = app_api('/v1/workflows/runs?bot=native-report-check')['items']
                if reports:
                    assert len(reports) == 1
                    report_detail = app_api('/v1/workflows/runs/' + reports[0]['id'])
                    if report_detail['workflow']['status'] in ('succeeded', 'failed', 'stopped'):
                        break
                time.sleep(.1)
            assert report_detail and report_detail['workflow']['status'] == 'succeeded', 'native report did not complete'
            assert report_detail['attempt']['tokens'] == 0 and report_detail['attempt']['cost_usd'] == 0
            verification = next(node for node in report_detail['nodes'] if node['site_id'] == 'verify')
            assert verification['result']['verified'] is True
            artifacts = report_detail['workflow']['result']['artifacts']
            assert len(artifacts) == 3
            metrics = next(artifact for artifact in artifacts if artifact['name'] == 'campaign-metrics')
            download_path = ('/api/v1/tasks/runs/' + metrics['run_id'] + '/artifacts/'
                             + Path(metrics['artifact']).name)
            download = execute_async('''const done=arguments[arguments.length-1];
              fetch(arguments[0],{credentials:'same-origin'}).then(async response =>
                done({status:response.status,text:await response.text()})).catch(()=>done({status:0}));''', (download_path,))
            assert download['status'] == 200
            assert hashlib.sha256(download['text'].encode()).hexdigest() == metrics['sha256']
            rows = list(csv.DictReader(io.StringIO(download['text'])))
            assert rows[0]['campaign'] == 'Search' and rows[0]['cpa'] == '15' and rows[0]['alert'] == ''
            assert rows[1]['campaign'] == 'Social' and rows[1]['cpa'] == '' and rows[1]['alert'] == 'zero_conversions'
            (out / 'validation.json').write_text(json.dumps({
                'contract_version': 1, 'application': Path(application).name,
                'scope': 'actual installed Linux webview, private first-run profile; no inference or connected accounts',
                'http_only_owner_cookie': True, 'external_client_refused': True,
                'separate_google_services': True, 'horizontal_overflow': False,
                'campaign_report': {'preview_before_admission':True, 'artifacts':3,
                                    'download_sha256_verified':True, 'undefined_cpa_preserved':True,
                                    'unknown_period_not_inferred':True, 'model_tokens':0},
                'limits': ['No tray/menu or sleep/wake interaction', 'No live service/model or native worker acceptance',
                           'No screenshot visual inspection claimed by this automated test'],
            }, indent=2) + '\n')
        except BaseException:
            if session:
                try:
                    # This is a fresh credential-free profile. Return only
                    # display text and URL components without query/fragment;
                    # never emit cookie values or serialized page internals.
                    view = execute('''return {origin: location.origin, path: location.pathname,
                      title: document.title, text: document.body?.innerText?.slice(0, 2000)};''')
                    cookies = client.get(f'/session/{session}/cookie', timeout=5)
                    names = []
                    if cookies.status_code == 200:
                        names = [{key: row.get(key) for key in ('name', 'domain', 'path', 'httpOnly', 'sameSite')}
                                 for row in cookies.json().get('value', []) if isinstance(row, dict)]
                    diagnostic = json.dumps({'native_view': view, 'cookie_attributes_only': names})
                    print(re.sub(r'\b[0-9a-fA-F]{32,}\b', '<redacted identifier>', diagnostic))
                except Exception:
                    print('Native display diagnostics unavailable; no page or cookie values emitted.')
            # No account/model credentials enter this fresh profile. Still
            # withhold long opaque identifiers from bounded startup diagnostics.
            diagnostic = log.read_text(errors='replace')[-8000:]
            print(re.sub(r'\b[0-9a-fA-F]{32,}\b', '<redacted identifier>', diagnostic))
            raise
        finally:
            if session:
                try:
                    client.delete(f'/session/{session}', timeout=10)
                except httpx.TransportError:
                    pass
            remaining = procguard.end_recorded([{'pid': owner.pid, 'pgid': owner.pgrp,
                'session': owner.session, 'starttime': owner.starttime, 'boot_id': procguard.boot_id()}],
                term_grace=2, kill_grace=3)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            assert not remaining, 'owned native driver descendants remain after cleanup'
