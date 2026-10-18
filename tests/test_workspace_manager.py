"""WorkspaceManager lifecycle against a fake child process (no bwrap needed).

The fake child is a real subprocess speaking protocol v1 with scriptable
behaviour (normal / pause / deaf / hang / die / flood), so the manager's
discipline is exercised over real pipes: busy rejection without queuing,
the bounded interrupt with its honest interrupt_unconfirmed path, restart
bumping the generation, unexpected death reported as lost, and ProcRegistry
registration with the existing verified-teardown survivor checks.

One optional test runs the REAL contained kernel (bubblewrap + systemd-run +
prlimit); it skips itself when bwrap is missing or strict containment is
unavailable on this host (checked with shutil.which and sandbox.status()).
"""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from hutch import sandbox
from hutch.sandbox import Status
from hutch.tools.base import ProcRegistry
from hutch.workspace import protocol
from hutch.workspace.manager import (
    ContainmentUnavailable,
    WorkspaceManager,
    kernel_argv,
    manager_for_conversation,
)

# --------------------------------------------------------------------- fake child

FAKE_CHILD = r'''
import json, os, signal, sys, time
mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
generation = int(os.environ.get("HUTCH_WORKSPACE_GENERATION", "0"))
flags = {"stop": False}

def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

out({"op": "hello", "status": "ok", "protocol": 1, "generation": generation, "pid": os.getpid()})
if mode in ("deaf", "hang"):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
if mode == "graceful":
    signal.signal(signal.SIGINT, lambda s, f: flags.update(stop=True))
while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        req = json.loads(line)
    except ValueError:
        continue
    op, rid = req.get("op"), req.get("id")
    if op == "ping":
        out({"op": "ping", "id": rid, "status": "ok"})
    elif op == "reset_ns":
        out({"op": "reset_ns", "id": rid, "status": "ok", "generation": generation})
    elif op == "exec":
        if mode == "die":
            os._exit(9)
        if mode == "graceful":
            deadline = time.time() + float(req.get("timeout_ms", 1500)) / 1000.0
            while not flags["stop"] and time.time() < deadline:
                time.sleep(0.05)
            status = "interrupted" if flags["stop"] else "ok"
            out({"op": "exec", "id": rid, "status": "ok",
                 "receipt": {"ordinal": 1, "environment_generation": generation,
                             "started_at": "2026-10-11T00:00:00+00:00",
                             "finished_at": "2026-10-11T00:00:01+00:00",
                             "source_sha256": "0" * 64, "status": status,
                             "stdout_chars_total": 0, "stderr_chars_total": 0},
                 "stdout_tail": "", "stderr_tail": "", "result_repr": "None",
                 "blocks": [], "produced_files": []})
            continue
        if mode == "hang":
            time.sleep(300)
        if mode == "deaf":
            time.sleep(300)
        if mode == "pause":
            time.sleep(1.5)
        if mode == "slow":
            time.sleep(float(req.get("timeout_ms", 1000)) / 1000.0 + 0.3)
        if mode == "flood":
            sys.stdout.write("x" * (5 * 1024 * 1024) + "\n")
            sys.stdout.flush()
            continue
        out({"op": "exec", "id": rid, "status": "ok",
             "receipt": {"ordinal": 1, "environment_generation": generation,
                         "started_at": "2026-10-11T00:00:00+00:00",
                         "finished_at": "2026-10-11T00:00:01+00:00",
                         "source_sha256": "0" * 64, "status": "ok",
                         "stdout_chars_total": 0, "stderr_chars_total": 0},
             "stdout_tail": "", "stderr_tail": "", "result_repr": "None",
             "blocks": [], "produced_files": []})
'''


def fake_spawn(spawns: list[int], mode: str = "normal"):
    """A SpawnFn that starts the fake child and records asked generations."""

    def spawn(workspace: Path, generation: int) -> tuple[subprocess.Popen, dict]:
        spawns.append(generation)
        proc = subprocess.Popen(
            [sys.executable, "-c", FAKE_CHILD, mode],
            cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True,
            env={**os.environ, "HUTCH_WORKSPACE_GENERATION": str(generation)})
        line = _readline_raw(proc.stdout.fileno(), timeout=15)
        hello = json.loads(line) if line else {}
        assert hello.get("op") == "hello", f"fake child did not say hello: {hello!r}"
        return proc, {"python_version": "fake-3", "extras": {"pandas": False, "matplotlib": False}}

    return spawn


def _readline_raw(fd: int, timeout: float) -> str | None:
    """Raw-fd line read (the manager later reads the same fd raw; a buffered
    reader here could swallow bytes os.read would then miss)."""
    buffer = bytearray()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if not ready:
            continue
        chunk = os.read(fd, 65536)
        if not chunk:
            return None
        buffer.extend(chunk)
        if b"\n" in buffer:
            raw, _, _ = bytes(buffer).partition(b"\n")
            return raw.decode("utf-8", "replace")
    return None


def make_manager(store, tmp_path, mode="normal", spawns=None, **kwargs) -> WorkspaceManager:
    return WorkspaceManager(store, "conv-manager-test", tmp_path / "ws",
                            spawn=fake_spawn(spawns if spawns is not None else [], mode),
                            **kwargs)


def wait_for_state(manager: WorkspaceManager, state: str, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if manager.session_info()["status"] == state:
            return True
        time.sleep(0.01)
    return False


@pytest.fixture(autouse=True)
def _fast_interrupt_windows(monkeypatch):
    """Shrink the interrupt ack and parent margins so the runaway-child tests
    stay fast; production values are 3s + 4s."""
    monkeypatch.setattr("hutch.workspace.manager.INTERRUPT_ACK_SECONDS", 0.3)
    monkeypatch.setattr("hutch.workspace.manager.PARENT_RESPONSE_MARGIN_SECONDS", 0.3)


# ---------------------------------------------------------------------- lifecycle


def test_execute_round_trip_and_store_row(store, tmp_path):
    spawns: list[int] = []
    manager = make_manager(store, tmp_path, spawns=spawns)
    response = manager.execute("print('hi')", 30_000)
    assert response["status"] == "ok"
    assert response["receipt"]["environment_generation"] == 1
    assert spawns == [1]
    row = store.get_workspace_session("conv-manager-test")
    assert row["generation"] == 1 and row["status"] == "active"
    fingerprint = json.loads(row["env_fingerprint"])
    assert fingerprint["python_version"] and fingerprint["extras"].keys() == {"pandas", "matplotlib"}
    assert all(isinstance(v, bool) for v in fingerprint["extras"].values())
    info = manager.session_info()
    assert info["status"] == "ready" and info["child_alive"] is True
    workspace = Path(row["workspace_dir"])
    assert (workspace.stat().st_mode & 0o777) == 0o700
    manager.close()


def test_concurrent_execute_is_busy_without_queuing(store, tmp_path):
    manager = make_manager(store, tmp_path, mode="pause")   # the child takes ~1.5s to answer
    first: dict = {}

    def run_first():
        first["value"] = manager.execute("1", 30_000)

    worker = threading.Thread(target=run_first, daemon=True)
    worker.start()
    assert wait_for_state(manager, "busy")
    started = time.monotonic()
    second = manager.execute("2", 5_000)
    elapsed = time.monotonic() - started
    assert second["status"] == "busy"                       # refused immediately, nothing queued
    assert elapsed < 1.0
    worker.join(10)
    assert first["value"]["status"] == "ok"


def test_interrupt_without_ack_marks_unconfirmed_and_offers_reset(store, tmp_path):
    manager = make_manager(store, tmp_path, mode="deaf")    # ignores SIGINT, never answers
    result: dict = {}

    def run_cell():
        result["value"] = manager.execute("while True: pass", 60_000)

    worker = threading.Thread(target=run_cell, daemon=True)
    worker.start()
    assert wait_for_state(manager, "busy")
    interrupt = manager.interrupt()
    assert interrupt["status"] == "interrupt_unconfirmed"   # never a silent claim of success
    assert interrupt["receipt"]["status"] == "interrupt_unconfirmed"
    assert "reset" in interrupt["offer"]
    worker.join(10)
    response = result["value"]
    assert response["status"] == "interrupt_unconfirmed"
    assert response["receipt"]["stdout_chars_total"] == 0   # the outcome was never reported: stated, not faked
    manager.close()
    assert manager.session_info()["status"] in ("stopped", "lost")


def test_interrupt_confirmed_when_the_child_acks(store, tmp_path):
    manager = make_manager(store, tmp_path, mode="graceful")   # catches SIGINT, answers 'interrupted'
    result: dict = {}

    def run_cell():
        result["value"] = manager.execute("1", 60_000)

    worker = threading.Thread(target=run_cell, daemon=True)
    worker.start()
    assert wait_for_state(manager, "busy")
    time.sleep(0.2)                                          # let the request land
    ack = manager.interrupt()
    worker.join(10)
    assert ack["status"] == "interrupted"                    # the protocol ack arrived inside the 3s window
    assert result["value"]["status"] == "ok"
    assert result["value"]["receipt"]["status"] == "interrupted"
    manager.close()


def test_late_child_answer_still_counts(store, tmp_path):
    """A child that answers after its cell deadline but within the parent's
    grace still delivers its REAL receipt (no fabricated timeout)."""
    manager = make_manager(store, tmp_path, mode="slow")     # answers at timeout+0.3s
    response = manager.execute("1", 1_000)
    assert response["status"] == "ok"
    assert response["receipt"]["status"] == "ok"             # not a fabricated timeout
    manager.close()


def test_restart_bumps_generation_and_marks_stale(store, tmp_path):
    spawns: list[int] = []
    manager = make_manager(store, tmp_path, spawns=spawns)
    manager.execute("1", 30_000)
    old_proc = manager.session_info()
    result = manager.restart(reason="reset_workspace tool")
    assert result["ok"] is True and result["survivors"] == 0    # verified teardown
    assert result["stale"] == {"state": "stale", "generation_ended": 1, "generation_started": 2}
    row = store.get_workspace_session("conv-manager-test")
    assert row["generation"] == 2 and row["status"] == "active"
    response = manager.execute("2", 30_000)
    assert response["status"] == "ok"
    assert spawns == [1, 2]                                  # the next start used exactly the reserved generation
    assert response["receipt"]["environment_generation"] == 2
    manager.close()


def test_unexpected_child_death_is_lost(store, tmp_path):
    manager = make_manager(store, tmp_path, mode="die")
    response = manager.execute("1", 30_000)
    assert response["status"] == "lost"
    assert response["error"]["type"] == "WorkspaceLost"
    assert "exited" in response["error"]["value"] or "not accepting" in response["error"]["value"]
    assert response["receipt"]["status"] == "error"          # honest fabricated receipt
    row = store.get_workspace_session("conv-manager-test")
    assert row["status"] == "expired"
    assert manager.session_info()["status"] == "lost"
    manager.close()


def test_death_between_runs_bumps_generation_on_next_execute(store, tmp_path):
    spawns: list[int] = []
    manager = make_manager(store, tmp_path, spawns=spawns)
    manager.execute("1", 30_000)
    manager._proc.kill()                                     # simulate run teardown / crash
    manager._proc.wait(timeout=5)
    response = manager.execute("2", 30_000)
    assert response["status"] == "ok"
    assert spawns == [1, 2]                                  # a NEW generation, not a silent resurrection
    assert response["receipt"]["environment_generation"] == 2
    manager.close()


def test_spawn_registers_in_procregistry_and_teardown_ends_the_tree(store, tmp_path):
    spawns: list[int] = []
    manager = make_manager(store, tmp_path, spawns=spawns)
    registry = ProcRegistry()
    manager.execute("1", 30_000, procs=registry)
    assert registry.alive() == 1                             # the kernel is the run's registered child
    killed = registry.kill_all(grace=1.0)
    assert killed == 1
    assert registry.survivors == []                          # verified teardown: measured, not assumed
    assert manager.session_info()["child_alive"] is False
    manager.close()


def test_busy_restart_refuses_while_a_cell_runs(store, tmp_path):
    manager = make_manager(store, tmp_path, mode="pause")
    done = threading.Event()

    def run_cell():
        manager.execute("1", 30_000)
        done.set()

    worker = threading.Thread(target=run_cell, daemon=True)
    worker.start()
    assert wait_for_state(manager, "busy")
    result = manager.restart()
    assert result["ok"] is False and result["status"] == "busy"
    worker.join(10)
    assert done.wait(5)
    manager.close()


def test_first_start_resumes_from_the_stored_generation(store, tmp_path):
    # a previous run of this conversation already reached generation 4
    store.upsert_workspace_session("conv-manager-test", 4, str(tmp_path / "ws"), status="active")
    spawns: list[int] = []
    manager = make_manager(store, tmp_path, spawns=spawns)
    response = manager.execute("1", 30_000)
    assert response["receipt"]["environment_generation"] == 5   # never reuses an old generation
    assert spawns == [5]
    manager.close()


def test_invalid_conversation_id_is_refused(store, tmp_path):
    with pytest.raises(ValueError):
        WorkspaceManager(store, "../escape", tmp_path / "ws", spawn=fake_spawn([], "normal"))


# ------------------------------------------------------------------- containment


def test_containment_off_fails_closed_before_any_spawn(store, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX", "off")               # conftest default; made explicit here
    manager = WorkspaceManager(store, "conv-off", tmp_path / "ws")   # the REAL spawn path
    response = manager.execute("1", 30_000)
    assert response["status"] == "error"
    assert response["error"]["type"] == "ContainmentUnavailable"
    assert "no uncontained mode" in response["error"]["value"]
    assert manager.session_info()["child_alive"] is False    # nothing was ever spawned
    assert store.get_workspace_session("conv-off") is None


def test_unavailable_containment_probe_fails_closed(store, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX", "strict")
    monkeypatch.setattr(sandbox, "status", lambda refresh=False: Status(False, reason="no bubblewrap here"))
    manager = WorkspaceManager(store, "conv-nobwrap", tmp_path / "ws")
    response = manager.execute("1", 30_000)
    assert response["status"] == "error"
    assert "no bubblewrap here" in response["error"]["value"]
    assert "Nothing was run" in response["error"]["value"] or "fail-closed" in response["error"]["value"]


def test_kernel_argv_builds_the_strict_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX", "strict")
    monkeypatch.setattr(sandbox, "status", lambda refresh=False: Status(True, version="0.13.0-test"))
    ws = tmp_path / "ws"
    ws.mkdir()
    argv = kernel_argv(ws, 4)
    joined = " ".join(argv)
    # scope: systemd-run user scope with cgroup caps, wrapping prlimit
    assert argv[0].endswith("systemd-run")
    assert "--property=MemoryMax=4096M" in argv and "--property=TasksMax=256" in argv
    assert any(part.endswith("/prlimit") or part == "prlimit" for part in argv)
    assert "--cpu=3600" in argv and "--as=4294967296" in argv and "--core=0" in argv
    # bwrap: everything unshared (no network), fresh /proc, private /tmp, only the workspace writable
    assert sandbox.binary() in argv
    assert "--unshare-all" in argv and "--new-session" in argv and "--die-with-parent" in argv
    assert "--proc" in argv and "/proc" in argv
    assert "--tmpfs" in argv and "/tmp" in argv
    assert "--bind" in argv and str(ws.resolve()) in argv
    assert "--share-net" not in argv
    # the fixed environment allowlist behind --clearenv
    assert "--clearenv" in argv
    setenvs: dict[str, str] = {}
    for i, part in enumerate(argv):
        if part == "--setenv":
            setenvs[argv[i + 1]] = argv[i + 2]
    import hutch.workspace.manager as manager_module
    src_root = str(Path(manager_module.__file__).resolve().parents[2])
    assert set(setenvs) == {"PATH", "HOME", "LANG", "TERM", "TMPDIR",
                            "PYTHONPATH", "PYTHONUNBUFFERED", "HUTCH_KERNEL",
                            "HUTCH_WORKSPACE_GENERATION"}
    assert setenvs["PATH"] == sandbox.DEFAULT_PATH
    assert setenvs["HOME"] == str(ws.resolve())
    assert setenvs["LANG"] == "C.UTF-8" and setenvs["TERM"] == "dumb" and setenvs["TMPDIR"] == "/tmp"
    assert setenvs["HUTCH_KERNEL"] == "1" and setenvs["HUTCH_WORKSPACE_GENERATION"] == "4"
    assert setenvs["PYTHONPATH"].split(os.pathsep)[0] == src_root
    # the child entry
    assert argv[-6:] == ["-m", "hutch.workspace.kernel", "--workspace", str(ws.resolve()),
                         "--generation", "4"]


def test_kernel_argv_env_allowlist_is_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX", "strict")
    monkeypatch.setattr(sandbox, "status", lambda refresh=False: Status(True, version="0.13.0-test"))
    from hutch.workspace.manager import kernel_env
    ws = tmp_path / "ws"
    ws.mkdir()
    env = kernel_env(ws, 1)
    assert set(env) == {"PATH", "HOME", "LANG", "TERM", "TMPDIR",
                        "PYTHONPATH", "PYTHONUNBUFFERED", "HUTCH_KERNEL", "HUTCH_WORKSPACE_GENERATION"}
    assert env["HOME"] == str(ws)


def test_kernel_argv_refuses_when_strict_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX", "off")
    with pytest.raises(ContainmentUnavailable):
        kernel_argv(tmp_path, 1)


# ---------------------------------------------------- optional REAL contained test


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap not installed on this host")
def test_real_contained_kernel_round_trip(store, tmp_path, monkeypatch):
    """The only bwrap-dependent test: the real strict profile end to end."""
    monkeypatch.setenv("HUTCH_SANDBOX", "strict")
    probe = sandbox.status(refresh=True)
    if not probe.ok:
        pytest.skip(f"strict containment unavailable on this host: {probe.reason}")
    manager = WorkspaceManager(store, "conv-real", tmp_path / "ws")
    try:
        response = manager.execute("print('contained')\n40 + 2", 60_000)
        assert response["status"] == "ok", response.get("error")
        assert response["receipt"]["status"] == "ok"
        assert response["receipt"]["environment_generation"] == 1
        assert response["result_repr"] == "42"
        assert response["stdout_tail"] == "contained\n"
        row = store.get_workspace_session("conv-real")
        assert row["generation"] == 1 and row["status"] == "active"
        fingerprint = json.loads(row["env_fingerprint"])
        assert set(fingerprint["extras"]) == {"pandas", "matplotlib"}
        # persistence inside one generation
        second = manager.execute("answer_stored = 41 + 1\nanswer_stored", 60_000)
        assert second["result_repr"] == "42"
        assert second["receipt"]["ordinal"] == 2
    finally:
        manager.close()


def test_manager_registry_replaces_on_custom_spawn(store, tmp_path):
    spawns_a: list[int] = []
    first = manager_for_conversation(store, "conv-registry", tmp_path, spawn=fake_spawn(spawns_a))
    spawns_b: list[int] = []
    second = manager_for_conversation(store, "conv-registry", tmp_path, spawn=fake_spawn(spawns_b))
    assert first is not second
    assert first.session_info()["child_alive"] is False       # the replaced manager's child was ended


# ----------------------------------------------------------------------- routes


def _build_app(store, factory):
    from fastapi import FastAPI

    from hutch.workspace.routes import build_workspace_router

    app = FastAPI()
    app.include_router(build_workspace_router(store, factory))
    return app


def test_routes_session_lifecycle(store, tmp_path):
    from fastapi.testclient import TestClient

    spawns: list[int] = []
    manager = make_manager(store, tmp_path, spawns=spawns)
    client = TestClient(_build_app(store, lambda cid: manager))

    response = client.get("/api/v1/conversations/conv-manager-test/workspace/session")
    assert response.status_code == 404                        # no session was ever started

    manager.execute("1", 30_000)
    response = client.get("/api/v1/conversations/conv-manager-test/workspace/session")
    assert response.status_code == 200
    body = response.json()
    assert body["generation"] == 1 and body["store_status"] == "active"
    assert body["status"] == "ready" and body["child_alive"] is True
    assert isinstance(body["env_fingerprint"], dict)
    assert body["env_fingerprint"]["extras"].keys() == {"pandas", "matplotlib"}
    assert body["workspace_dir"] == str(tmp_path / "ws")

    response = client.post("/api/v1/conversations/conv-manager-test/workspace/reset")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True and body["generation"] == 2
    assert body["stale"] == {"state": "stale", "generation_ended": 1, "generation_started": 2}
    assert "in-memory state is gone" in body["detail"]

    response = client.get("/api/v1/conversations/conv-manager-test/workspace/session")
    assert response.json()["generation"] == 2

    response = client.get("/api/v1/conversations/conv-unknown/workspace/session")
    assert response.status_code == 404
    manager.close()


def test_reset_route_refuses_while_a_cell_runs(store, tmp_path):
    from fastapi.testclient import TestClient

    manager = make_manager(store, tmp_path, mode="pause")
    client = TestClient(_build_app(store, lambda cid: manager))
    done = threading.Event()

    def run_cell():
        manager.execute("1", 30_000)
        done.set()

    worker = threading.Thread(target=run_cell, daemon=True)
    worker.start()
    assert wait_for_state(manager, "busy")
    response = client.post("/api/v1/conversations/conv-manager-test/workspace/reset")
    assert response.status_code == 409                        # mirrors the tool honestly: interrupt first
    worker.join(10)
    assert done.wait(5)
    manager.close()
