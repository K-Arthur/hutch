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
