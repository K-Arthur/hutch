"""Adversarial evidence for the contained Python kernel (mission section 4/12).

The workspace kernel is the one place Hutch executes model-generated code, so
its containment is verified here with REAL bubblewrap processes against owned
sentinels — never inferred from the launch arguments alone. Each test asserts
the exact allowed and denied effects:

* host sentinels (fake credentials, the real state directory, the store
  database, another conversation's workspace) are unreadable by absolute path;
* there is no IPv4/IPv6 loopback, no DNS, and no host Unix socket;
* writes land only in the workspace; a private ``/tmp`` write never appears on
  the host; ``/etc`` and the interpreter tree are read-only;
* the PID namespace sees only the sandbox (pid 1 = bwrap, pid 2 = the kernel);
* a detached, setsid'd descendant dies with the session — the "double-forked
  child outlives the run" failure class;
* with containment off/unavailable the manager refuses before any spawn;
* the effective backend identity and argv are the strict profile, recorded.

These tests skip (never silently pass) when bubblewrap or message limits make
the host incapable of the strict profile. `tests/test_workspace_bounds.py`
separately covers finite budgets (output, memory, runaway cells).
"""

from __future__ import annotations

import json
import os
import socket
import shutil
import textwrap
import threading
import time
from pathlib import Path

import pytest

from hutch import sandbox
from hutch.workspace.manager import WorkspaceManager, kernel_argv

pytestmark = pytest.mark.skipif(
    shutil.which("bwrap") is None or shutil.which("systemd-run") is None or shutil.which("prlimit") is None,
    reason="strict containment needs bwrap + systemd-run + prlimit",
)


@pytest.fixture()
def strict(monkeypatch):
    """Turn containment on and prove the host can actually provide it."""
    monkeypatch.setenv("HUTCH_SANDBOX", "strict")
    probe = sandbox.status(refresh=True)
    if not probe.ok:
        pytest.skip(f"strict containment unavailable on this host: {probe.reason}")
    return probe


def _summary(response: dict) -> dict:
    """The one JSON line the probe cells print, or a loud failure."""
    if response.get("status") != "ok":
        raise AssertionError(f"probe cell did not complete: {response!r}")
    lines = [line for line in (response.get("stdout_tail") or "").splitlines() if line.strip()]
    assert lines, f"probe cell printed nothing: {response!r}"
    return json.loads(lines[-1])


def _run(manager: WorkspaceManager, body: str) -> dict:
    return _summary(manager.execute(textwrap.dedent(body), 60_000))


# --------------------------------------------------------------- sentinel reads


def test_host_credential_and_state_sentinels_are_unreadable(store, config, tmp_path, strict):
    """Cross-boundary reads by absolute path return no bytes and no exception detail leak."""
    fake_home = tmp_path / "fake-home"
    (fake_home / ".ssh").mkdir(parents=True)
    sentinel = fake_home / ".ssh" / "id_rsa"
    sentinel.write_text("SENTINEL-LOGIN-KEY-MATERIAL\n")
    state_dir = Path(config.state_dir)
    state_sentinel = state_dir / "connections-sentinel.json"
    state_sentinel.parent.mkdir(parents=True, exist_ok=True)
    state_sentinel.write_text('{"token": "SENTINEL-STATE-TOKEN"}\n')
    db_path = Path(config.db_path)
    assert db_path.exists(), "store fixture must have created the database"

    manager = WorkspaceManager(store, "conv-sentinels", tmp_path / "ws")
    try:
        probe = _run(manager, f"""
            import json
            targets = {json.dumps([str(sentinel), str(state_sentinel), str(db_path)])}
            results = {{}}
            for target in targets:
                try:
                    results[target] = open(target, "r").read()
                except Exception as exc:
                    results[target] = type(exc).__name__
            # baseline: an ordinary read of the workspace itself must work
            open("input.txt", "w").write("usable scratch input")
            results["workspace"] = open("input.txt").read()
            print(json.dumps(results))
        """)
    finally:
        manager.close()
    for target in (sentinel, state_sentinel, db_path):
        value = probe[str(target)]
        assert value != "usable scratch input"
        assert "SENTINEL" not in value, f"sentinel leaked: {value!r}"
        assert value in {"FileNotFoundError", "PermissionError", "IsADirectoryError", "NotADirectoryError"}, value
    assert probe["workspace"] == "usable scratch input"
    # The sentinels were readable from the host (the fixture is honest)
    assert "SENTINEL-LOGIN-KEY-MATERIAL" in sentinel.read_text()


def test_another_conversations_workspace_is_invisible(store, config, tmp_path, strict):
    other = tmp_path / "other-ws"
    other.mkdir()
    (other / "private.csv").write_text("cross-session-secret\n")
    manager = WorkspaceManager(store, "conv-a", tmp_path / "ws-a")
    try:
        probe = _run(manager, f"""
            import json
            try:
                value = open({str(other / 'private.csv')!r}).read()
            except Exception as exc:
                value = type(exc).__name__
            print(json.dumps({{"cross_session": value}}))
        """)
    finally:
        manager.close()
    assert "cross-session-secret" not in probe["cross_session"]
    assert probe["cross_session"] in {"FileNotFoundError", "PermissionError"}


# --------------------------------------------------------- network and sockets


def test_no_ipv4_ipv6_dns_or_host_unix_socket(store, config, tmp_path, strict):
    """Egress is denied with owned listeners; a never-connected listener is a negative control."""
    accepted = threading.Event()

    tcp4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp4.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp4.bind(("127.0.0.1", 0))
    tcp4.listen(1)
    tcp4.settimeout(0.2)
    tcp4_port = tcp4.getsockname()[1]
    tcp6 = None
    tcp6_port = None
    if socket.has_ipv6:
        try:
            tcp6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            tcp6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tcp6.bind(("::1", 0))
            tcp6.listen(1)
            tcp6.settimeout(0.2)
            tcp6_port = tcp6.getsockname()[1]
        except OSError:
            tcp6 = None
    unix_path = tmp_path / "host-broker.sock"
    unix_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    unix_listener.bind(str(unix_path))
    unix_listener.listen(1)
    unix_listener.settimeout(0.2)

    def accept_any(listener):
        try:
            conn, _ = listener.accept()
            accepted.set()
            conn.close()
        except (socket.timeout, OSError):
            pass

    accept_threads = [threading.Thread(target=accept_any, args=(tcp4,), daemon=True)]
    if tcp6 is not None:
        accept_threads.append(threading.Thread(target=accept_any, args=(tcp6,), daemon=True))
    accept_threads.append(threading.Thread(target=accept_any, args=(unix_listener,), daemon=True))
    for thread in accept_threads:
        thread.start()

    manager = WorkspaceManager(store, "conv-egress", tmp_path / "ws")
    try:
        probe = _run(manager, f"""
            import json, socket
            result = {{}}
            for label, family, address in (
                ("ipv4", socket.AF_INET, ("127.0.0.1", {tcp4_port})),
            ):
                s = socket.socket(family, socket.SOCK_STREAM)
                s.settimeout(2)
                result[label] = s.connect_ex(address)
                s.close()
            result["ipv6"] = None
            if socket.has_ipv6 and {tcp6_port!r} is not None:
                s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                s.settimeout(2)
                result["ipv6"] = s.connect_ex(("::1", {tcp6_port or 0}))
                s.close()
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect({str(unix_path)!r})
                result["unix"] = "connected"
                s.close()
            except Exception as exc:
                result["unix"] = type(exc).__name__
            try:
                socket.getaddrinfo("example.com", 80)
                result["dns"] = "resolved"
            except Exception as exc:
                result["dns"] = type(exc).__name__
            print(json.dumps(result))
        """)
    finally:
        manager.close()
    if tcp6 is not None:
        tcp6.close()
    unix_listener.close()
    tcp4.close()
    for thread in accept_threads:
        thread.join(timeout=0.5)
    assert probe["ipv4"] != 0, "the sandbox connected to a host loopback listener"
    if probe["ipv6"] is not None:
        assert probe["ipv6"] != 0, "the sandbox connected to a host IPv6 listener"
    assert probe["unix"] != "connected", "the sandbox connected to a host Unix socket"
    assert probe["dns"] != "resolved", "DNS resolved inside the sandbox"
    assert not accepted.is_set(), "a host listener accepted a connection from the sandbox"


# ------------------------------------------------------------------- writes


def test_writes_are_confined_to_the_workspace(store, config, tmp_path, strict):
    workspace = tmp_path / "ws-writes"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    etc_probe = Path("/etc/hutch-containment-probe")
    manager = WorkspaceManager(store, "conv-writes", workspace)
    try:
        probe = _run(manager, f"""
            import json, os
            result = {{}}
            open("kept.txt", "w").write("inside the workspace")
            result["inside"] = open("kept.txt").read()
            try:
                # an existing read-only mount cannot be modified
                open("/etc/passwd", "a").write("nope")
                result["etc_ro"] = "wrote"
            except Exception as exc:
                result["etc_ro"] = type(exc).__name__
            try:
                # a new name in the sandbox-private /etc stays inside the sandbox
                open("/etc/hutch-containment-probe", "w").write("private")
                result["etc_new"] = "sandbox-private"
            except Exception as exc:
                result["etc_new"] = type(exc).__name__
            try:
                open({str(outside_dir / 'leak.txt')!r}, "w").write("nope")
                result["outside"] = "wrote"
            except Exception as exc:
                result["outside"] = type(exc).__name__
            open("/tmp/private-probe.txt", "w").write("private tmp")
            result["tmp_writable"] = open("/tmp/private-probe.txt").read()
            result["usr_writable"] = os.access("/usr", os.W_OK)
            print(json.dumps(result))
        """)
    finally:
        manager.close()
    assert probe["inside"] == "inside the workspace"
    assert probe["etc_ro"] != "wrote", "a read-only /etc mount was writable"
    assert probe["etc_new"] in {"sandbox-private", "PermissionError", "OSError"}
    assert probe["outside"] != "wrote"
    assert probe["tmp_writable"] == "private tmp"          # the sandbox's own tmpfs
    assert probe["usr_writable"] is False
    assert (workspace / "kept.txt").read_text() == "inside the workspace"
    assert not etc_probe.exists()
    assert not (outside_dir / "leak.txt").exists()
    assert not Path("/tmp/private-probe.txt").exists(), "the private tmp leaked onto the host"


# ------------------------------------------------------------ process isolation


def test_pid_namespace_sees_only_the_sandbox(store, config, tmp_path, strict):
    manager = WorkspaceManager(store, "conv-pidns", tmp_path / "ws-pid")
    try:
        probe = _run(manager, """
            import json, os
            pids = sorted(int(p) for p in os.listdir("/proc") if p.isdigit())
            print(json.dumps({"pids": pids, "pid": os.getpid(), "host_pytest_pid_visible": %d in pids}))
        """ % os.getpid())
    finally:
        manager.close()
    assert probe["host_pytest_pid_visible"] is False
    assert probe["pid"] == 2, "the kernel must be pid 2 in its own namespace (bwrap is pid 1)"
    assert set(probe["pids"]) <= {1, 2}, f"unexpected processes visible: {probe['pids']}"


def _marker_processes(marker: str) -> list[int]:
    found = []
    my_pid = os.getpid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == my_pid:
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ")
        except OSError:
            continue
        if marker.encode() in cmdline:
            found.append(int(entry.name))
    return found


def test_a_detached_descendant_dies_with_the_session(store, config, tmp_path, strict):
    """The double-fork escape cannot outlive the contained session (mission: cleanup)."""
    marker = f"hutch-detached-{os.urandom(4).hex()}"
    manager = WorkspaceManager(store, "conv-detach", tmp_path / "ws-detach")
    try:
        probe = _run(manager, f"""
            import json, subprocess, sys
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(120)  # {marker}"],
                start_new_session=True)
            print(json.dumps({{"child_pid": child.pid}}))
        """)
        assert probe["child_pid"] > 0
        for _ in range(50):
            if _marker_processes(marker):
                break
            time.sleep(0.1)
        assert _marker_processes(marker), "the detached descendant was never visible; the probe is vacuous"
    finally:
        manager.close()
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline and _marker_processes(marker):
        time.sleep(0.1)
    assert _marker_processes(marker) == [], "a detached descendant outlived the contained session"


# ------------------------------------------------------- fail-closed + identity
# (tool-level fail-closed coverage for HUTCH_SANDBOX=off and an unavailable probe
# lives in tests/test_tools_python_exec.py; manager-level in
# tests/test_workspace_manager.py. This file keeps only real-process evidence.)


def test_effective_backend_identity_and_argv_are_the_strict_profile(store, config, tmp_path, strict):
    argv = kernel_argv(tmp_path / "ws-identity", 1)
    text = " ".join(argv)
    assert "--unshare-all" in argv and "--die-with-parent" in argv
    assert "--clearenv" in argv
    assert "systemd-run" in argv[0]
    assert "--property=MemoryMax=" in text and "--property=TasksMax=" in text
    assert any(a.startswith("--cpu=") for a in argv)
    assert any(a.startswith("--as=") for a in argv)
    assert any(a.startswith("--fsize=") for a in argv)
    assert "--core=0" in argv
    assert strict.backend == "bubblewrap+systemd-user-scope"
    assert "bubblewrap" in strict.version
    # and the profile actually executes, reporting its own identity + clean env
    manager = WorkspaceManager(store, "conv-identity", tmp_path / "ws-identity")
    try:
        probe = _run(manager, """
            import json, os, sys
            keys = sorted(os.environ)
            print(json.dumps({
                "executable": sys.executable,
                "kernel_marker": os.environ.get("HUTCH_KERNEL"),
                "generation": os.environ.get("HUTCH_WORKSPACE_GENERATION"),
                "env_keys": keys,
                "cwd": os.getcwd(),
            }))
        """)
    finally:
        manager.close()
    assert probe["kernel_marker"] == "1"
    assert probe["generation"] == "1"
    assert probe["cwd"] == str((tmp_path / "ws-identity").resolve())
    forbidden = {"HUTCH_STATE_DIR", "HUTCH_SANDBOX", "HUTCH_OFFLINE_BROKER_DIR", "HUTCH_TESTING", "OPENAI_API_KEY"}
    assert not (set(probe["env_keys"]) & forbidden), probe["env_keys"]
