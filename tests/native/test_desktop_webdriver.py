"""Opt-in real installed-webview checks; no renderer mock or provider call."""
from __future__ import annotations

import base64
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
            (out / 'validation.json').write_text(json.dumps({
                'contract_version': 1, 'application': Path(application).name,
                'scope': 'actual installed Linux webview, private first-run profile; no inference or connected accounts',
                'http_only_owner_cookie': True, 'external_client_refused': True,
                'separate_google_services': True, 'horizontal_overflow': False,
                'limits': ['No tray/menu or sleep/wake interaction', 'No live service/model or native worker acceptance',
                           'No screenshot visual inspection claimed by this automated test'],
            }, indent=2) + '\n')
        except BaseException:
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
