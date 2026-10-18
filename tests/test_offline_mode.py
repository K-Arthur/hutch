from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hutch import sandbox
from hutch.engine import Engine
from hutch.models import Bot, InferenceMode, RunStatus
from hutch.offline import OfflineBrokerSet, broker_socket_path
from hutch.providers.registry import loopback_endpoint, validate_offline_bot, validate_offline_route
from hutch.tools import build_tools


@pytest.fixture()
def offline_client(tmp_path, monkeypatch):
    from hutch.server.app import create_app

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize(("provider", "url", "expected"), [
    ("ollama", None, "http://127.0.0.1:11434"),
    ("ollama", "http://localhost:11434/api", "http://127.0.0.1:11434/api"),
    ("lmstudio", "http://[::1]:1234/v1", "http://[::1]:1234/v1"),
    ("llamacpp", "http://127.8.9.10:8080/v1", "http://127.8.9.10:8080/v1"),
])
def test_offline_endpoint_accepts_loopback_only(provider, url, expected):
    assert loopback_endpoint(provider, url) == expected


@pytest.mark.parametrize("url", [
    "https://models.example.test/v1",
    "http://192.168.1.10:11434",
    "https://[::1]:11434",
    "http://127.0.0.1:99999",
    "http://127.0.0.1:0",
    "http://[::1%25lo]:11434",
    "http://user:secret@127.0.0.1:11434",
    "http://127.0.0.1:11434/api?api_key=secret",
    "http://localhost.localdomain:11434",
])
def test_offline_endpoint_rejects_non_loopback_ambiguous_or_secret_urls(url):
    with pytest.raises(ValueError, match="strict offline"):
        loopback_endpoint("ollama", url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434?token=hidden",
    "http://127.0.0.1:11434#fragment",
    "http://user:secret@127.0.0.1:11434",
    "http://127.0.0.1:0",
    "http://[::1%25lo]:11434",
])
def test_broker_origin_rejects_credentials_queries_and_fragments(url):
    from hutch.offline import _origin

    with pytest.raises(ValueError):
        _origin(url)


def test_offline_route_rejects_hosted_and_unclassified_custom_routes():
    with pytest.raises(ValueError, match="not a local inference route"):
        validate_offline_route("openai/gpt-4o-mini")
    with pytest.raises(ValueError, match="not a local inference route"):
        validate_offline_route("openai-compatible/local", "http://127.0.0.1:8080/v1")
    with pytest.raises(ValueError, match="not a local inference route"):
        validate_offline_route("ollama/model-cloud")


def test_offline_bot_requires_hutch_runtime_loopback_routes_and_contained_shell(monkeypatch):
    monkeypatch.setattr(sandbox, "offline_egress_status", lambda: sandbox.OfflineStatus(True))
    monkeypatch.setattr(sandbox, "status", lambda: sandbox.Status(True))
    monkeypatch.delenv("HUTCH_SANDBOX", raising=False)
    bot = Bot(name="local-only", model="ollama/qwen3:8b", inference_mode="offline",
              tools=["shell", "browser", "web_fetch"], sandbox="strict")
    validate_offline_bot(bot)

    with pytest.raises(ValueError, match="built-in runtime"):
        validate_offline_bot(bot.model_copy(update={"runtime": "pi"}))
    with pytest.raises(ValueError, match="strict shell sandbox"):
        validate_offline_bot(bot.model_copy(update={"sandbox": "off"}))
    with pytest.raises(ValueError, match="shell network"):
        validate_offline_bot(bot.model_copy(update={"shell_network": True}))
    with pytest.raises(ValueError, match="not a local inference route"):
        validate_offline_bot(bot.model_copy(update={"fallbacks": ["anthropic/claude-sonnet"]}))
    with pytest.raises(ValueError, match="not a local inference route"):
        validate_offline_bot(bot.model_copy(update={"task_routes": {"code_analysis": "anthropic/claude-sonnet"}}))


def test_offline_worker_filters_host_network_tools_from_model_specs():
    bot = Bot(name="offline-tools", model="ollama/test-model", inference_mode=InferenceMode.offline,
              tools=["files", "shell", "web_fetch", "browser"], memory_enabled=False)
    ctx = SimpleNamespace(bot=bot, store=SimpleNamespace(get_bot=lambda _id: None))

    assert set(build_tools(bot.tools, ctx, memory_enabled=False)) == {
        "read_file", "list_files", "write_file", "shell",
    }


def test_offline_worker_command_uses_network_namespace_and_credential_free_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "offline_scope_prefix", lambda: ["bwrap", "--die-with-parent", "--unshare-all"])
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: f"/usr/bin/{name}")
    broker_dir = tmp_path / "brokers"
    broker_dir.mkdir()
    state_dir = tmp_path / "state"
    (state_dir / "keys").mkdir(parents=True)
    (state_dir / "connections.json").write_text('{"connections": {"private": {"api_key_env": "SECRET"}}}')
    (state_dir / "keys" / "private.key").write_text("never-mount-this")
    source = {
        "PATH": "/usr/bin", "PYTHONPATH": "/checkout/src", "OPENAI_API_KEY": "never-copy",
        "OLLAMA_HOST": "https://remote.example.test", "HTTPS_PROXY": "http://proxy.example.test",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        "HUTCH_EXECUTOR": "process", "HUTCH_MAX_CONCURRENT": "3",
    }
    argv = sandbox.offline_worker_argv(["/usr/bin/python3", "-m", "hutch.worker"], source, str(state_dir), 30,
                                      str(broker_dir))

    assert argv[:4] == ["/usr/bin/systemd-run", "--user", "--scope", "--quiet"]
    assert "/usr/bin/prlimit" in argv and "--property=MemoryMax=4096M" in argv and "--property=TasksMax=256" in argv
    assert "bwrap" in argv and "--unshare-all" in argv and "--ro-bind" in argv
    assert "OPENAI_API_KEY=never-copy" not in argv
    assert "OLLAMA_HOST=https://remote.example.test" not in argv
    assert "HTTPS_PROXY=http://proxy.example.test" not in argv
    assert "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus" not in argv
    assert "HUTCH_STATE_DIR" in argv and str(state_dir) in argv
    assert "HUTCH_LEASE_SECONDS" in argv and "30" in argv
    assert "HUTCH_EXECUTOR" in argv and "process" in argv
    assert "HUTCH_MAX_CONCURRENT" in argv and "3" in argv
    assert "HUTCH_OFFLINE_BROKER_DIR" in argv and "/run/hutch-offline" in argv
    read_only_mounts = [(argv[index + 1], argv[index + 2])
                        for index, value in enumerate(argv[:-2]) if value == "--ro-bind"]
    safe_connections = Path(next(source for source, target in read_only_mounts
                                 if target == str(state_dir / "connections.json")))
    safe_keys = Path(next(source for source, target in read_only_mounts
                          if target == str(state_dir / "keys")))
    safe_chatgpt = Path(next(source for source, target in read_only_mounts
                            if target == str(state_dir / "chatgpt")))
    assert safe_connections.read_text() == '{"connections": {}}\n'
    assert safe_connections != state_dir / "connections.json"
    assert list(safe_keys.iterdir()) == []
    assert safe_chatgpt != state_dir / "chatgpt"
    assert list(safe_chatgpt.iterdir()) == []


def test_offline_worker_scope_has_full_namespaces_and_uses_a_private_broker_mount():
    prefix = sandbox.offline_scope_prefix()

    assert "--unshare-all" in prefix
    assert "--share-net" not in prefix


def test_offline_broker_uses_configured_private_temp_root(tmp_path, monkeypatch):
    import stat
    import tempfile

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", None)
    brokers = OfflineBrokerSet([])
    try:
        directory = Path(brokers.directory)
        assert directory.parent == tmp_path
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    finally:
        brokers.close()


def test_loopback_http_provider_uses_broker_from_network_isolated_worker(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    from tests.fakes import FakeOllama

    if not sandbox.status().ok:
        pytest.skip("host lacks the resource-limited bubblewrap worker prerequisites")
    fake = FakeOllama()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    brokers = OfflineBrokerSet([fake.url])
    brokers.start()
    monkeypatch.setenv("HUTCH_OFFLINE_BROKER_DIR", brokers.directory)
    worker_code = (
        "from hutch.providers.ollama import OllamaProvider; "
        f"health=OllamaProvider({fake.url!r}).health(); "
        "assert health.ok and health.version == '0.0-fake', health; print(health.version)"
    )
    env = dict(os.environ, HUTCH_STATE_DIR=str(state_dir), HUTCH_LEASE_SECONDS="30")
    argv = sandbox.offline_worker_argv([sys.executable, "-c", worker_code], env, str(state_dir), 30,
                                      brokers.directory)
    try:
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=20, check=False)
        assert result.returncode == 0, result.stderr or result.stdout
        assert "0.0-fake" in result.stdout
        assert fake.of("/api/version")
    finally:
        brokers.close()
        fake.close()


def test_broker_sockets_honor_tmpdir_so_a_full_host_tmp_cannot_block_runs(tmp_path, monkeypatch):
    """ENOSPC on a small /tmp tmpfs must not block local-model broker setup.

    The broker directory is host-side state (mounted into the worker); honor
    TMPDIR like every other temp consumer so tests and constrained hosts can
    move it to disk-backed storage.
    """
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    brokers = OfflineBrokerSet([])
    try:
        assert Path(brokers.directory).is_relative_to(tmp_path)
    finally:
        brokers.close()


def test_offline_worker_cannot_read_saved_provider_credentials(tmp_path):
    import os
    import subprocess
    import sys

    if not sandbox.status().ok:
        pytest.skip("host lacks the resource-limited bubblewrap worker prerequisites")
    state_dir = tmp_path / "state"
    (state_dir / "keys").mkdir(parents=True)
    (state_dir / "connections.json").write_text(
        '{"connections": {"private": {"api_key_env": "PRIVATE_KEY"}}}\n')
    (state_dir / "keys" / "private.key").write_text("fixture-provider-secret")
    (state_dir / "chatgpt").mkdir()
    (state_dir / "chatgpt" / "accounts.json").write_text('{"accounts": {"fixture": {"access_token": "fixture-oauth-secret"}}}\n')
    brokers = OfflineBrokerSet([])
    code = (
        "import json,os,pathlib; "
        "root=pathlib.Path(os.environ['HUTCH_STATE_DIR']); "
        "assert json.loads((root/'connections.json').read_text()) == {'connections': {}}; "
        "assert list((root/'keys').iterdir()) == []; "
        "assert not (root/'keys'/'private.key').exists(); "
        "assert list((root/'chatgpt').iterdir()) == []; "
        "assert not (root/'chatgpt'/'accounts.json').exists(); print('credential files hidden')"
    )
    env = dict(os.environ, HUTCH_STATE_DIR=str(state_dir), HUTCH_LEASE_SECONDS="30")
    argv = sandbox.offline_worker_argv([sys.executable, "-c", code], env, str(state_dir), 30,
                                      brokers.directory)
    try:
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=20, check=False)
        assert result.returncode == 0, result.stderr or result.stdout
        assert "credential files hidden" in result.stdout
    finally:
        brokers.close()


def test_process_engine_runs_fake_local_model_inside_offline_worker(store, config):
    import time

    from tests.fakes import FakeOllama

    if not sandbox.status().ok or not sandbox.offline_egress_status(refresh=True).ok:
        pytest.skip("host lacks a verified resource-limited offline worker")
    fake = FakeOllama({"fake:1b": {"params": "1B", "size": 200_000_000}})
    bot = store.create_bot(Bot(name="offline-process", model="ollama/fake:1b", base_url=fake.url,
                               inference_mode=InferenceMode.offline, tools=[], approval_mode="auto",
                               selfcheck=False))
    engine = Engine(config, store, executor="process", light=True)
    run = engine.submit(bot, "answer from the local fixture")
    try:
        assert engine.dispatch_pending() == 1
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = store.get_run(run.id)
            if current.terminal:
                break
            time.sleep(0.05)
        final = store.get_run(run.id)
        assert final.status is RunStatus.succeeded, (final.status, final.error, final.exit_reason)
        assert fake.of("/api/chat")
        deadline = time.monotonic() + 5
        while run.id in engine._offline_brokers and time.monotonic() < deadline:
            time.sleep(0.05)
        assert run.id not in engine._offline_brokers
    finally:
        engine.stop_all()
        engine.shutdown(timeout=10)
        fake.close()


def test_offline_process_executes_governed_file_shell_read_workflow_without_cloud(store, config, monkeypatch):
    import time
    from tests.fakes import FakeOllama, agent_script
    from hutch.models import EventType
    if not sandbox.status().ok or not sandbox.offline_egress_status(refresh=True).ok:
        pytest.skip("host lacks the verified offline process boundary")
    # This workflow exercises the real shell containment, which the shared
    # fixture deliberately disables for unrelated policy-only tests.
    monkeypatch.delenv("HUTCH_SANDBOX", raising=False)
    fake = FakeOllama({"fake:1b": {"params": "1B", "size": 200_000_000}})
    fake.script = agent_script([
        {"tool_calls": [{"name": "write_file", "arguments": {"path": "input.txt", "content": "offline input\n"}}]},
        {"tool_calls": [{"name": "shell", "arguments": {"command": "cat input.txt > combined.txt"}}]},
        {"tool_calls": [{"name": "read_file", "arguments": {"path": "combined.txt"}}]},
        {"content": "The local artifact was verified."},
    ])
    bot = store.create_bot(Bot(name="offline-files", model="ollama/fake:1b", base_url=fake.url,
                              inference_mode="offline", tools=["files", "shell"], sandbox="strict",
                              approval_mode="auto", selfcheck=False))
    engine = Engine(config, store, executor="process", light=True)
    run = engine.submit(bot, "Write a local input file, copy it with the governed shell, then inspect the copy.")
    try:
        assert engine.dispatch_pending() == 1
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not store.get_run(run.id).terminal:
            time.sleep(.05)
        final = store.get_run(run.id)
        assert final.status is RunStatus.succeeded, (final.status, final.error, final.exit_reason)
        assert (Path(final.workspace) / "combined.txt").read_bytes() == b"offline input\n"
        results = [event.data for event in store.list_events(run.id) if event.type is EventType.tool_result]
        assert {row["tool"] for row in results} >= {"write_file", "shell", "read_file"}
        assert all(row["ok"] for row in results)
        chats = fake.of("/api/chat")
        assert len(chats) == 4
        for request in chats:
            names = {spec["function"]["name"] for spec in request["body"].get("tools", [])}
            assert not names & {"browser", "computer", "web_search", "http_request"}
        assert "offline input" in str(chats[-1]["body"]["messages"])
    finally:
        engine.stop_all()
        engine.shutdown(timeout=10)
        fake.close()


def test_loopback_broker_rejects_authority_and_method_changes(tmp_path):
    import httpx

    from tests.fakes import FakeOllama

    fake = FakeOllama()
    brokers = OfflineBrokerSet([fake.url])
    brokers.start()
    transport = httpx.HTTPTransport(uds=broker_socket_path(brokers.directory, fake.url))
    try:
        with httpx.Client(base_url=fake.url, transport=transport, trust_env=False) as client:
            response = client.get("/api/version")
            assert response.status_code == 200 and response.json()["version"] == "0.0-fake"
            assert client.get("/api/version", headers={"Host": "attacker.invalid"}).status_code == 400
            assert client.patch("/api/version").status_code == 405
        assert len(fake.of("/api/version")) == 1
    finally:
        brokers.close()
        fake.close()


def test_loopback_broker_refuses_a_request_after_close_starts(tmp_path):
    import http.client

    from hutch.offline import LoopbackBroker

    broker = LoopbackBroker("http://127.0.0.1:11434", str(tmp_path))
    upstream = http.client.HTTPConnection("127.0.0.1", 11434)
    broker.close()
    assert broker._register(upstream) is False
    upstream.close()


def test_loopback_broker_rejects_absolute_targets_and_oversized_lengths(tmp_path):
    import socket

    from tests.fakes import FakeOllama

    fake = FakeOllama()
    brokers = OfflineBrokerSet([fake.url])
    brokers.start()
    sock_path = broker_socket_path(brokers.directory, fake.url)

    def send(raw: bytes) -> bytes:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(3)
        try:
            client.connect(sock_path)
            client.sendall(raw)
            chunks = []
            while chunk := client.recv(4096):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            client.close()

    try:
        authority = f"127.0.0.1:{fake.port}".encode()
        absolute = send(b"GET http://attacker.invalid/api/version HTTP/1.1\r\nHost: " + authority +
                        b"\r\nConnection: close\r\n\r\n")
        assert b"400 Bad Request" in absolute
        oversized = send(b"POST /api/chat HTTP/1.1\r\nHost: " + authority +
                         b"\r\nContent-Length: 67108865\r\nConnection: close\r\n\r\n")
        assert b"HTTP/1.1 413 " in oversized
        assert not fake.requests
    finally:
        brokers.close()
        fake.close()


def test_offline_shell_does_not_request_a_host_systemd_scope(monkeypatch, tmp_path):
    from hutch.sandbox import Policy, shell_argv

    monkeypatch.setenv("HUTCH_OFFLINE_RUN", "1")
    argv = shell_argv("printf ok", Policy(workspace=tmp_path))
    assert argv[0] == "/usr/bin/prlimit" or argv[0].endswith("/prlimit")
    assert "systemd-run" not in argv
    assert "--unshare-all" in argv


def test_offline_dispatch_fails_closed_when_host_filter_is_unavailable(store, config, monkeypatch):
    monkeypatch.setattr(sandbox, "offline_egress_status",
                        lambda refresh=False: sandbox.OfflineStatus(False, reason="network namespace failed a local TCP check"))
    bot = store.create_bot(Bot(name="offline-host-gated", model="ollama/test-model", inference_mode="offline", tools=[]))
    engine = Engine(config, store, executor="process")
    run = engine.submit(bot, "must not start")

    assert engine.dispatch_pending() == 0
    final = store.get_run(run.id)
    assert final.status is RunStatus.failed
    assert final.exit_reason == "offline_unavailable"
    assert "network namespace failed" in final.error
    assert not engine._procs
    engine.shutdown()


def test_offline_dispatch_refuses_in_process_executor_even_if_host_filter_passes(store, config, monkeypatch):
    monkeypatch.setattr(sandbox, "offline_egress_status", lambda refresh=False: sandbox.OfflineStatus(True))
    bot = store.create_bot(Bot(name="offline-thread-gated", model="ollama/test-model", inference_mode="offline", tools=[]))
    engine = Engine(config, store, executor="thread")
    run = engine.submit(bot, "must not start")

    assert engine.dispatch_pending() == 0
    final = store.get_run(run.id)
    assert final.status is RunStatus.failed
    assert "supervised process executor" in final.error
    assert not engine._threads
    engine.shutdown()


def test_api_refuses_offline_when_host_filter_is_unavailable(offline_client, monkeypatch):
    monkeypatch.setattr(sandbox, "offline_egress_status",
                        lambda refresh=False: sandbox.OfflineStatus(False, reason="the worker namespace did not block egress"))

    response = offline_client.post("/api/bots", json={
        "name": "offline-not-available", "model": "ollama/test-model", "inference_mode": "offline", "tools": [],
    })

    assert response.status_code == 422
    assert "Strict offline is unavailable" in response.json()["detail"]
    assert "did not block egress" in response.json()["detail"]


def test_api_allows_verified_offline_configuration_but_blocks_hosted_override(offline_client, monkeypatch):
    monkeypatch.setattr(sandbox, "offline_egress_status", lambda refresh=False: sandbox.OfflineStatus(True))
    response = offline_client.post("/api/bots", json={
        "name": "offline-ready", "model": "ollama/test-model", "inference_mode": "offline", "tools": [],
    })
    assert response.status_code == 201, response.text

    override = offline_client.post("/api/bots/offline-ready/run", json={
        "prompt": "must remain local", "model": "openai/gpt-4o-mini",
    })
    assert override.status_code == 409
    assert "Strict offline" in override.json()["detail"]


def test_cli_refuses_offline_when_host_filter_is_unavailable(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from hutch.cli import app

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(sandbox, "offline_egress_status",
                        lambda refresh=False: sandbox.OfflineStatus(False, reason="local interface was reachable"))
    result = CliRunner().invoke(app, ["bot", "create", "offline-cli", "--model", "ollama/test-model",
                                      "--inference-mode", "offline", "--tools", ""])

    assert result.exit_code != 0
    assert "Strict offline is unavailable" in result.output


def test_offline_option_cannot_use_a_hosted_model_override(store, config):
    from hutch.modelchoices import ModelNotUsable, validate_override

    bot = Bot(name="offline-override", model="ollama/test-model", inference_mode="offline", tools=[])
    with pytest.raises(ModelNotUsable, match="Strict offline"):
        validate_override(config, store, bot, "openai/gpt-4o-mini")
