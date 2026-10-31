"""Stopping the dashboard is prompt and quiet, even with a browser's event streams open (owner report).

Every Ctrl+C used to wait ten seconds and print an ASGI traceback, because open event streams held uvicorn's
graceful shutdown until its timeout cancelled them. The streams now end themselves the moment the server is asked
to exit. The first test drives the real server class over real sockets; the second runs the real `hutch serve`
process and sends it SIGINT, which is exactly what a terminal does.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from hutch.server.app import create_app
from hutch.server.runner import GracefulServer

STREAMS = ("/stream/live", "/api/v1/changes/stream", "/api/v1/events/stream")


@pytest.fixture(autouse=True)
def _streams_allowed_again():
    """The shutdown flag is process-wide: never let these tests leave it set for the SSE tests that follow."""
    from hutch.server import sse
    sse.SHUTTING_DOWN.clear()
    yield
    sse.SHUTTING_DOWN.clear()


def test_open_streams_end_the_moment_the_server_is_asked_to_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    server = GracefulServer(uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="error", timeout_graceful_shutdown=10))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    base = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    ended: list[str] = []

    def hold(path: str) -> None:
        try:
            with httpx.stream("GET", base + path, timeout=30) as response:
                for _ in response.iter_lines():
                    pass
            ended.append(path)
        except httpx.HTTPError:
            ended.append(path)          # the connection closing is also an ending

    holders = [threading.Thread(target=hold, args=(path,), daemon=True) for path in STREAMS]
    for holder in holders:
        holder.start()
    time.sleep(1.0)                     # all three are open and idle now
    started = time.monotonic()
    server.should_exit = True
    thread.join(timeout=8)
    elapsed = time.monotonic() - started
    assert not thread.is_alive(), "the server must stop"
    assert elapsed < 4, f"stopping took {elapsed:.1f}s: streams were holding shutdown"
    for holder in holders:
        holder.join(timeout=3)
    assert sorted(ended) == sorted(STREAMS)


def test_a_server_started_after_a_shutdown_in_the_same_process_allows_streams(tmp_path, monkeypatch):
    from hutch.server import sse

    sse.begin_shutdown()
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    server = GracefulServer(uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    try:
        assert not sse.SHUTTING_DOWN.is_set()
    finally:
        server.should_exit = True
        thread.join(timeout=8)


@pytest.mark.skipif(shutil.which("hutch") is None and not (Path(sys.executable).parent / "hutch").exists(), reason="the hutch script is not installed")
def test_hutch_serve_stops_on_ctrl_c_in_under_a_few_seconds_with_no_traceback(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    exe = str(Path(sys.executable).parent / "hutch") if (Path(sys.executable).parent / "hutch").exists() else shutil.which("hutch")
    env = dict(os.environ, HUTCH_STATE_DIR=str(tmp_path / "state"), OLLAMA_HOST="http://127.0.0.1:9")
    process = subprocess.Popen([exe, "serve", "--port", str(port)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    sockets: list[socket.socket] = []
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            pytest.fail("hutch serve did not start")
        for path in STREAMS:
            held = socket.create_connection(("127.0.0.1", port), timeout=5)
            held.sendall(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nAccept: text/event-stream\r\n\r\n".encode())
            sockets.append(held)
        time.sleep(1.0)
        started = time.monotonic()
        os.killpg(process.pid, signal.SIGINT)
        code = process.wait(timeout=20)
        elapsed = time.monotonic() - started
        _out, err = process.communicate()
        assert code == 0, (code, err[-400:])
        assert elapsed < 5, f"Ctrl+C took {elapsed:.1f}s"
        assert "Traceback" not in err and "timeout graceful shutdown" not in err, err[-600:]
    finally:
        for held in sockets:
            held.close()
        if process.poll() is None:
            process.kill()
