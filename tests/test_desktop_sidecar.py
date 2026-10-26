import json
import os
import subprocess
import sys
import threading
import queue
import time
from pathlib import Path

import httpx
import pytest


@pytest.fixture(params=["source", "frozen"])
def sidecar_command(request):
    if request.param == "source":
        return [sys.executable, "-m", "hutch.desktop"]
    executable = os.environ.get("HUTCH_FROZEN_BACKEND")
    if not executable:
        pytest.skip("set HUTCH_FROZEN_BACKEND to validate a built native backend")
    assert Path(executable).is_file(), "the configured frozen backend must exist"
    return [executable]


def test_desktop_sidecar_has_private_readiness_and_stops_when_host_closes(tmp_path, sidecar_command):
    from hutch.server.security import auth_digest
    token, nonce = "fixture-token-" + "a" * 32, "fixture-nonce-" + "b" * 16
    env = {**os.environ, "HUTCH_STATE_DIR": str(tmp_path / "state"),
           "HUTCH_TRUSTED_PROXIES": "127.0.0.1", "HUTCH_REMOTE_ENABLED": "1"}
    process = subprocess.Popen(sidecar_command, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps({"token": token, "nonce": nonce}) + "\n")
        process.stdin.flush()
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        line = lines.get(timeout=35)
        assert token not in line
        ready = json.loads(line)
        assert ready["protocol"] == 1 and ready["pid"] == process.pid and ready["nonce"] == nonce
        base = f"http://127.0.0.1:{ready['port']}"
        with httpx.Client(base_url=base, trust_env=False) as client:
            assert client.get("/api/v1/connections").status_code == 401
            client.cookies.set("hutch_auth", auth_digest(token))
            assert client.get("/api/v1/connections").status_code == 200
            assert client.get("/").status_code == 200
            assert client.get("/static/app.js").status_code == 200
            assert client.get("/static/model-switcher.css").status_code == 200
            assert client.post("/api/v1/conversations", headers={"Origin": "https://attacker.example"},
                               json={}).status_code == 403
        process.stdin.close()
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_sidecar_rejects_malformed_handshake_without_echoing_input(sidecar_command):
    result = subprocess.run(sidecar_command, input="private-invalid-secret\n",
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 2
    assert "private-invalid-secret" not in result.stdout + result.stderr


def test_desktop_launches_owned_worker_and_records_a_real_file_effect(tmp_path, sidecar_command):
    from hutch.server.security import auth_digest
    from tests.fakes import FakeOllama, agent_script

    fake = FakeOllama({"bundle:1b": {"params": "1B", "size": 500_000_000}})
    fake.script = agent_script([
        {"tool_calls": [{"name": "write_file", "arguments": {"path": "result.txt", "content": "packaged worker verified"}}]},
        {"content": "Created result.txt."},
    ])
    token, nonce = "desktop-worker-token-" + "a" * 32, "worker-test-nonce-1234"
    state = tmp_path / "state"
    process = subprocess.Popen(sidecar_command, env={**os.environ, "HUTCH_STATE_DIR": str(state), "OLLAMA_HOST": fake.url},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps({"token": token, "nonce": nonce}) + "\n")
        process.stdin.flush()
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        ready = json.loads(lines.get(timeout=35))
        with httpx.Client(base_url=f"http://127.0.0.1:{ready['port']}", trust_env=False, timeout=10) as client:
            client.cookies.set("hutch_auth", auth_digest(token))
            created = client.post("/api/bots", json={"name": "desktop-test", "model": "ollama/bundle:1b",
                "tools": ["files"], "memory_enabled": False, "approval_mode": "auto"})
            assert created.status_code == 201, created.text
            submitted = client.post("/api/bots/desktop-test/run", json={"prompt": "Write result.txt."})
            assert submitted.status_code == 201, submitted.text
            run_id = submitted.json()["id"]
            deadline = time.monotonic() + 60
            result = {}
            while time.monotonic() < deadline:
                response = client.get(f"/api/runs/{run_id}")
                assert response.status_code == 200, response.text
                result = response.json()
                if result["status"] in {"succeeded", "failed", "stopped", "outcome_unknown"}:
                    break
                time.sleep(.1)
            assert result["status"] == "succeeded", result
        from hutch.config import hutchConfig
        config = hutchConfig(state_dir=state)
        assert (config.run_dir("desktop-test", run_id) / "workspace/result.txt").read_text() == "packaged worker verified"
        import sqlite3
        # Independent readback verifies an effect receipt, not the model's completion text.
        with sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True) as database:
            assert database.execute("SELECT COUNT(*) FROM tool_actions WHERE run_id = ? AND status = 'done'", (run_id,)).fetchone()[0] == 1
        process.stdin.close()
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        fake.close()


@pytest.mark.parametrize("legacy", [False, True])
def test_packaged_notion_sdk_negotiates_and_reads_through_its_own_protocol_schemas(sidecar_command, tmp_path, legacy):
    """Packaging must preserve dynamically selected modern/legacy MCP wire models."""
    script = r'''
import json, os
from importlib.metadata import version
import httpx
from hutch.integrations.notion_mcp import NotionMCP, revision
legacy = os.environ['HUTCH_TEST_LEGACY_MCP'] == '1'
schema = {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}
class Book:
    def access_token(self, account):
        assert account == 'fixture-account'
        return 'packaged-fixture-token'
async def handle(request):
    assert str(request.url) == 'https://mcp.notion.com/mcp'
    assert request.headers['authorization'] == 'Bearer packaged-fixture-token'
    if request.method == 'GET':
        return httpx.Response(405)
    if request.method == 'DELETE':
        return httpx.Response(204)
    body = json.loads(request.content)
    method = body['method']
    if method == 'server/discover':
        if legacy:
            return httpx.Response(400, json={'jsonrpc':'2.0','id':body['id'],'error':{'code':-32601,'message':'legacy'}})
        result = {'supportedVersions':['2026-07-28'],'capabilities':{'tools':{}}}
    elif method == 'initialize':
        result = {'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}
    elif method == 'notifications/initialized':
        return httpx.Response(202)
    elif method == 'tools/list':
        result = {'tools':[{'name':'notion-search','inputSchema':schema}]}
    elif method == 'tools/call':
        assert body['params']['name'] == 'notion-search'
        result = {'content':[{'type':'text','text':'Verified packaged Notion read'}],'isError':False}
    else:
        raise AssertionError(method)
    if not legacy:
        result.update(ttlMs=0,cacheScope='private',resultType='complete')
    return httpx.Response(200,json={'jsonrpc':'2.0','id':body['id'],'result':result})
client = NotionMCP(Book(),'fixture-account',transport=httpx.MockTransport(handle))
catalog = client.discover()
result = client.call('notion-search',{'query':'meeting notes'},revision(catalog['tools']['notion-search']))
assert result['ok'] and result['output'] == 'Verified packaged Notion read'
print(json.dumps({'sdk':version('mcp'),'protocol':result['protocol'],'ok':result['ok']}))
'''
    result = subprocess.run([sidecar_command[0], "-c", script], capture_output=True, text=True, timeout=30,
                            env={**os.environ, "HUTCH_STATE_DIR": str(tmp_path / "state"),
                                 "HUTCH_TEST_LEGACY_MCP": "1" if legacy else "0"})
    assert result.returncode == 0, result.stderr[-3000:]
    assert json.loads(result.stdout) == {"sdk": "2.3.0", "protocol": "2025-06-18" if legacy else "2026-07-28", "ok": True}
