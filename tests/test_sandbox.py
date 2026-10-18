"""T-SANDBOX: a bot's shell is contained by the OS, not by a parser.

Baseline defect (docs/realignment/baseline.md, lead 9): the shell ran as the user with HOME merely redirected, so any script could
read ~/.ssh or open a socket. These tests are attempts to do exactly that, run for real inside bubblewrap.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from hutch import sandbox
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.runtime.steps import call_tool
from hutch.approvals import ApprovalGate
from hutch.safety import PolicyEngine
from hutch.tools import build_tools
from hutch.tools.base import ToolContext

pytestmark = pytest.mark.skipif(not sandbox.status().ok, reason=f"no usable sandbox here: {sandbox.status().reason}")


@pytest.fixture(autouse=True)
def containment_on(monkeypatch):
    monkeypatch.delenv("HUTCH_SANDBOX", raising=False)           # the suite default is 'off'; here the bot's own setting rules
    sandbox.reset_cache()
    yield
    sandbox.reset_cache()


def shell(store, config, tmp_path, command: str, **bot_kw):
    bot_kw.setdefault("sandbox", "strict")
    bot = store.get_bot("sb") or store.create_bot(Bot(name="sb", model="mock/demo", tools=["shell"],
                                                       approval_mode=ApprovalMode.auto, **bot_kw))
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    emit = lambda ev: store.append_event(ev)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config, workspace=ws, emit=emit)
    return call_tool(run, ctx, build_tools(["shell"], ctx), "shell", {"command": command}), ws


def os_sandbox(command: str, workspace: Path, *, policy: sandbox.Policy | None = None):
    """Exercise bubblewrap itself, bypassing Hutch's shell policy parser on purpose."""
    argv = sandbox.shell_argv(command, policy or sandbox.Policy(workspace=workspace))
    return subprocess.run(argv, cwd=workspace, text=True, capture_output=True, timeout=15)


def test_the_shell_cannot_see_the_real_home_or_any_folder_outside_the_workspace(store, config, tmp_path):
    secret = tmp_path / "secret.txt"                                  # a canary outside the workspace
    secret.write_text("TOP-SECRET-CANARY")
    home = Path.home()
    res, ws = shell(store, config, tmp_path, f"cat {secret}; ls {home}; ls /home; echo HOME=$HOME")
    assert "TOP-SECRET-CANARY" not in res.output
    assert f"HOME={ws}" in res.output
    # The security property is "the real home's contents are not visible", not a specific
    # error string: the sandbox's empty mount may legitimately expose only the directory
    # name (e.g. 'kevina' under /home) without any of its entries. Check entries.
    try:
        entries = [name for name in os.listdir(home) if name not in (".", "..")][:12]
    except OSError:
        entries = []
    leaked = [name for name in entries if name in res.output]
    assert not leaked, f"real home entries visible in the sandbox: {leaked}"


def test_a_script_that_reads_dotfiles_by_absolute_path_gets_nothing(store, config, tmp_path):
    """The case the policy parser documents as out of its reach: a script, not a command line."""
    fake_ssh = tmp_path / ".ssh"
    fake_ssh.mkdir()
    (fake_ssh / "id_rsa").write_text("-----BEGIN PRIVATE KEY-----")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "steal.py").write_text(f"print(open({str(fake_ssh / 'id_rsa')!r}).read())\n")
    res, _ = shell(store, config, tmp_path, "python3 steal.py")
    assert "PRIVATE KEY" not in res.output and not res.ok


def test_only_the_workspace_is_writable_and_tmp_is_private(store, config, tmp_path):
    leak = f"leak-{uuid.uuid4().hex}"
    ws = tmp_path / "ws"
    ws.mkdir()
    res = os_sandbox(f"echo kept > out.txt; echo x > /usr/x; echo x > /etc/passwd; touch /tmp/{leak}; echo tmp-ok", ws)
    assert (ws / "out.txt").read_text().strip() == "kept"             # the workspace is the one writable place
    assert "Read-only file system" in res.stderr
    assert "tmp-ok" in res.stdout and not Path("/tmp", leak).exists()  # /tmp inside is a private tmpfs, not the host's
    assert Path("/etc/passwd").stat().st_mode & 0o022 == 0              # (and the host's file was never touched)


def _listener():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    return srv, srv.getsockname()[1]


def test_sandboxed_shell_network_request_fails_closed(store, config, tmp_path):
    srv, port = _listener()
    try:
        probe = f"timeout 5 bash -c 'exec 3<>/dev/tcp/127.0.0.1/{port} && echo CONNECTED'"
        ws = tmp_path / "ws"
        ws.mkdir()
        denied = os_sandbox(probe, ws)
        assert "CONNECTED" not in denied.stdout + denied.stderr, "the sandbox reached the host's loopback"
    finally:
        srv.close()

    result, _ = shell(store, config, tmp_path, "echo must-not-run", shell_network=True)
    assert not result.ok and "network" in result.output.lower() and "Nothing was run" in result.output


def test_the_environment_is_clean_no_keys_or_tokens_leak_in(store, config, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-be-visible")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-should-not-be-visible")
    res, _ = shell(store, config, tmp_path, "printenv")
    assert "should-not-be-visible" not in res.output
    assert "PATH=" in res.output and "HOME=" in res.output


def test_the_host_process_list_is_not_visible(store, config, tmp_path):
    host = len([p for p in os.listdir("/proc") if p.isdigit()])
    res, _ = shell(store, config, tmp_path, "ls /proc | grep -E '^[0-9]+$' | wc -l")
    inside = int(res.output.split()[-1])
    assert inside < 12 < host, f"sandbox sees {inside} processes, host has {host}"


def test_a_process_that_detached_completely_dies_with_the_sandbox(store, config, tmp_path):
    """The case procguard cannot reach from outside (double fork + setsid -> re-parented to init, outside the process group)."""
    marker = "31337"
    res, _ = shell(store, config, tmp_path, f"( setsid sleep {marker} >/dev/null 2>&1 < /dev/null & ); echo detached")
    assert "detached" in res.output
    deadline = time.time() + 5
    while time.time() < deadline and subprocess.run(["pgrep", "-f", f"sleep {marker}"], capture_output=True).returncode == 0:
        time.sleep(0.1)
    assert subprocess.run(["pgrep", "-f", f"sleep {marker}"], capture_output=True).returncode != 0, \
        "a detached process outlived the sandbox"


def test_without_the_sandbox_the_same_detached_process_escapes(store, config, tmp_path):
    """The documented limit of process-group teardown, shown rather than asserted in prose."""
    marker = "31338"
    res, _ = shell(store, config, tmp_path, f"( setsid sleep {marker} >/dev/null 2>&1 < /dev/null & ); echo detached", sandbox="off")
    try:
        time.sleep(0.5)
        assert subprocess.run(["pgrep", "-f", f"sleep {marker}"], capture_output=True).returncode == 0
    finally:
        subprocess.run(["pkill", "-f", f"sleep {marker}"])


def test_it_fails_closed_when_the_sandbox_is_unavailable(store, config, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX_BIN", "/nonexistent/bwrap")
    sandbox.reset_cache()
    res, ws = shell(store, config, tmp_path, "echo ran > ran.txt")
    assert not res.ok and "requires the OS sandbox" in res.output and "Nothing was run" in res.output
    assert not (ws / "ran.txt").exists()
    assert store.list_actions(store.get_bot("sb") and store.list_runs(store.get_bot("sb").id)[0].id) == []   # no intent either


def test_a_bot_with_the_sandbox_off_runs_uncontained_and_the_transcript_says_so(store, config, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("visible-without-sandbox")
    res, _ = shell(store, config, tmp_path, f"cat {secret}", sandbox="off")
    assert "visible-without-sandbox" in res.output
    assert res.data["sandbox"] == "off"
    assert "no OS containment" in sandbox.describe(Bot(name="x", sandbox="off"))


def test_the_global_override_turns_containment_off_and_is_visible(monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX", "off")
    assert sandbox.mode_for(Bot(name="x", sandbox="strict")) == "off"
    monkeypatch.delenv("HUTCH_SANDBOX")
    assert sandbox.mode_for(Bot(name="x", sandbox="strict")) == "strict"


def test_a_file_size_limit_stops_a_runaway_writer(store, config, tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_SANDBOX_FSIZE_MB", "1")
    ws = tmp_path / "ws"
    ws.mkdir()
    res = os_sandbox("dd if=/dev/zero of=big bs=1M count=8", ws,
                     policy=sandbox.Policy(workspace=ws, fsize_mb=1))
    assert (ws / "big").stat().st_size <= 1024 * 1024
    assert res.returncode != 0 and (ws / "big").stat().st_size == 1024 * 1024


def test_memory_limit_is_applied_to_the_sandboxed_command(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    command = "python3 -c \"x=bytearray(96*1024*1024); print('allocated')\""
    res = os_sandbox(command, ws, policy=sandbox.Policy(workspace=ws, memory_mb=32))
    assert res.returncode != 0 and "allocated" not in res.stdout


def test_ambient_readonly_mount_env_cannot_expose_home_secrets(tmp_path, monkeypatch):
    secret_dir = tmp_path / ".ssh"
    secret_dir.mkdir()
    private_key = secret_dir / "id_rsa"
    private_key.write_text("PRIVATE-CANARY")
    monkeypatch.setenv("HUTCH_SANDBOX_RO", str(secret_dir))
    ws = tmp_path / "ws"
    ws.mkdir()
    res = os_sandbox(f"cat {private_key}", ws)
    assert "PRIVATE-CANARY" not in res.stdout + res.stderr
    with pytest.raises(ValueError, match="credentials or secrets"):
        sandbox.shell_argv("true", sandbox.Policy(workspace=ws, extra_ro=(str(secret_dir),)))


def test_explicit_readonly_mount_preserves_mode_at_execution(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    reference = tmp_path / "reference"
    reference.mkdir()
    note = reference / "note.txt"
    note.write_text("REFERENCE-CANARY")
    policy = sandbox.Policy(workspace=ws, extra_ro=(str(reference),))
    res = os_sandbox(f"cat {note}; echo changed > {note}; rm {note}; touch {reference}/new.txt", ws, policy=policy)
    assert "REFERENCE-CANARY" in res.stdout
    assert res.returncode != 0
    assert note.read_text() == "REFERENCE-CANARY"
    assert not (reference / "new.txt").exists()


def test_readonly_mount_rejects_credential_ancestor_and_workspace_cover(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / ".env").write_text("SECRET-CANARY")
    with pytest.raises(ValueError, match="credentials or secrets"):
        sandbox.shell_argv("true", sandbox.Policy(workspace=ws, extra_ro=(str(reference),)))
    with pytest.raises(ValueError, match="cover the writable workspace"):
        sandbox.shell_argv("true", sandbox.Policy(workspace=ws, extra_ro=(str(ws),)))


def test_new_bots_default_to_strict_on_a_capable_host_and_the_value_is_validated():
    assert Bot(name="fresh").sandbox == "strict"
    with pytest.raises(Exception):
        Bot(name="bad", sandbox="maybe")


def test_the_engine_records_the_containment_in_the_run_log(store, config, tmp_path):
    from hutch.engine import Engine
    bot = store.create_bot(Bot(name="logged", model="mock/demo", tools=["shell", "files"], approval_mode=ApprovalMode.auto,
                               sandbox="strict"))
    run = Engine(config, store).run_blocking(bot, "research the news and write a report")
    logs = [e.data for e in store.list_events(run.id) if e.type.value == "log" and "containment" in e.data]
    assert logs and "OS sandbox" in logs[0]["containment"]


def test_the_egress_probe_uses_an_interpreter_inside_its_own_mounts():
    """The Strict Offline probe mounts only the system tree.

    ``shutil.which("python3")`` finds a venv shim when Hutch runs from its venv,
    whose target is not mounted — the probe then failed for an interpreter-path
    reason and Strict Offline reported unavailable. The probe must choose an
    interpreter that exists inside the mounts it creates.
    """
    interpreter = sandbox._mounted_interpreter()
    if interpreter:
        assert Path(interpreter).resolve().is_relative_to("/usr")
    if Path("/usr/bin/python3").exists():
        assert interpreter, "a system python3 exists and must be chosen"
