"""A real CLI server must release its store/scheduler despite an open dashboard SSE."""
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest


@pytest.mark.skipif(os.name != "posix", reason="POSIX CLI signal lifecycle; native host uses its own protocol")
def test_serve_exits_after_sigint_while_dashboard_event_stream_remains_open(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    state = tmp_path / "state"
    env = {key: value for key, value in os.environ.items() if key not in {
        "HUTCH_AUTH_TOKEN", "HUTCH_REMOTE_ENABLED", "HUTCH_TRUSTED_PROXIES"}}
    env["HUTCH_STATE_DIR"] = str(state)
    with (tmp_path / "server.log").open("wb") as log:
        process = subprocess.Popen([sys.executable, "-c", "from hutch.cli import app; app()", "serve",
                                    "--host", "127.0.0.1", "--port", str(port)],
                                   env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        try:
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=base, trust_env=False, timeout=3) as client:
                deadline = time.monotonic() + 15
                while True:
                    assert process.poll() is None, "CLI exited before accepting requests"
                    try:
                        ready = client.get("/api/v1/connections/kdeconnect")
                        if ready.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert time.monotonic() < deadline, "CLI did not become ready"
                    time.sleep(.05)
                with client.stream("GET", "/api/v1/changes/stream") as stream:
                    assert stream.status_code == 200
                    assert stream.headers["content-type"].startswith("text/event-stream")
                    process.send_signal(signal.SIGINT)
                    try:
                        code = process.wait(timeout=17)
                    except subprocess.TimeoutExpired:
                        pytest.fail("Open dashboard SSE prevented CLI shutdown for 17 seconds")
                    assert code in {0, -signal.SIGINT}
            with sqlite3.connect(f"file:{state / 'hutch.db'}?mode=ro", uri=True) as db:
                assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                assert db.execute("SELECT count(*) FROM runs WHERE coalesce(lease_owner,'') != ''").fetchone()[0] == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
