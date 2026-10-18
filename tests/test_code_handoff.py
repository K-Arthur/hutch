from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hutch import code_handoff
from hutch.server.app import create_app


def test_opencode_profile_is_restrictive_bounded_and_never_auto_approves():
    task_id = "code_0123456789abcdef01234567"
    profile = code_handoff.task_agent_config(task_id)
    agent_id = profile["default_agent"]
    agent = profile["agents"][agent_id]
    rules = agent["permissions"]

    assert rules[0] == {"action": "*", "resource": "*", "effect": "deny"}
    assert agent["steps"] == 20
    assert any(row == {"action": "shell", "resource": "*", "effect": "ask"} for row in rules)
    assert any(row == {"action": "subagent", "resource": "*", "effect": "deny"} for row in rules)
    assert any(row == {"action": "external_directory", "resource": "*", "effect": "deny"} for row in rules)
    command = code_handoff.opencode_task_command("/usr/bin/opencode", task_id, "review this task")
    assert command[:5] == ["/usr/bin/opencode", "mini", "--standalone", "--agent", agent_id]
    assert "--auto" not in command
    assert "--prompt" in command and command[-1] == "review this task"


def test_terminal_interrupt_exit_is_classified_as_stopped():
    assert code_handoff.was_terminal_interrupt(-2)
    assert code_handoff.was_terminal_interrupt(130)
    assert not code_handoff.was_terminal_interrupt(1)


def test_opencode_environment_uses_a_private_persistent_profile_and_scrubs_host_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("AWS_PROFILE", "host-profile")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "aws-config"))
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", '{"agents":{"build":{"permissions":[]}}}')
    monkeypatch.setenv("OPENCODE_PERMISSION", '{"shell":"allow"}')
    monkeypatch.setenv("OPENCODE_DB", "/tmp/user-opencode.db")
    monkeypatch.setenv("PYTHONPATH", "/tmp/hostile-python")
    config = tmp_path / "task.json"
    config.write_text("{}")
    state_dir = tmp_path / "hutch-state"

    env = code_handoff.safe_opencode_environment(config, state_dir=state_dir)
    paths = code_handoff.opencode_profile_paths(state_dir)
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == str(paths["home"])
    assert env["XDG_CONFIG_HOME"] == str(paths["config_home"])
    assert env["XDG_DATA_HOME"] == str(paths["data_home"])
    assert env["OPENCODE_CONFIG"] == str(config)
    assert env["OPENCODE_DB"] == str(paths["database"])
    assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert env["OPENCODE_AUTO_SHARE"] == "0"
    assert "OPENAI_API_KEY" not in env
    assert "AWS_PROFILE" not in env and "AWS_CONFIG_FILE" not in env
    assert "OPENCODE_CONFIG_CONTENT" not in env
    assert "OPENCODE_PERMISSION" not in env
    assert "PYTHONPATH" not in env
    assert paths["root"].stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize(("auth_json", "expected"), [
    ('[{"provider":"openai","type":"oauth"}]', True),
    ("[]", False),
])
def test_opencode_auth_status_checks_only_the_private_profile(tmp_path, monkeypatch, auth_json, expected):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=auth_json, stderr="")

    monkeypatch.setattr(code_handoff.subprocess, "run", fake_run)
    state_dir = tmp_path / "state"
    assert code_handoff.opencode_profile_has_auth("/fixture/opencode", state_dir=state_dir) is expected
    assert seen["command"] == ["/fixture/opencode", "auth", "list", "--standalone", "--format", "json"]
    assert seen["env"]["OPENCODE_DB"] == str(state_dir / "opencode-profile" / "opencode.db")
    assert seen["cwd"] == state_dir / "opencode-profile" / "home"
    assert seen["capture_output"] and seen["text"]


def test_opencode_login_uses_the_supported_private_profile_flow(tmp_path, monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(code_handoff.subprocess, "run", fake_run)
    monkeypatch.setattr(code_handoff, "opencode_profile_has_auth", lambda executable, *, state_dir: True)
    state_dir = tmp_path / "state"
    code_handoff.opencode_profile_login("/fixture/opencode", state_dir=state_dir)
    assert seen["command"] == ["/fixture/opencode", "auth", "login", "--standalone"]
    assert seen["cwd"] == state_dir / "opencode-profile" / "home"
    assert seen["env"]["OPENCODE_DB"] == str(state_dir / "opencode-profile" / "opencode.db")
    assert "capture_output" not in seen


@pytest.mark.skipif(not hasattr(os, "tcsetpgrp") or sys.platform != "linux", reason="Linux controlling TTY required")
def test_interactive_process_keeps_terminal_and_owns_a_separate_group():
    """The coding runner must get foreground terminal input without leaving task children behind."""
    child_code = r'''
import os, signal, sys, time
print(f"READY tty={int(os.isatty(0))} foreground={int(os.tcgetpgrp(0) == os.getpgrp())}", flush=True)
print("REPLY " + input(), flush=True)
while True:
    time.sleep(1)
'''
    controller_code = r'''
import os, subprocess, sys
from hutch.code_handoff import spawn_interactive, restore_terminal
process, previous_group, session_id = spawn_interactive([sys.executable, "-c", sys.argv[1]])
try:
    print(f"CONTROLLER session={session_id} process_group={process.pid}", flush=True)
    status = process.wait()
finally:
    restore_terminal(previous_group)
print(f"RESTORED foreground={os.tcgetpgrp(0) == os.getpgrp()}", flush=True)
print(f"EXIT={status}", flush=True)
sys.exit(0 if status in (-2, 130) else status)
'''
    harness_code = r'''
import os, pty, select, signal, sys, time
controller_code, child_code = sys.argv[1:3]
pid, master = pty.fork()
if pid == 0:
    os.execv(sys.executable, [sys.executable, "-c", controller_code, child_code])
output = bytearray()
started = time.monotonic()
deadline = started + 25          # one budget for the whole interaction, so a loaded machine
sent_input = False               # cannot turn a slow start into a false failure
sent_interrupt = False
while time.monotonic() < deadline:
    readable, _, _ = select.select([master], [], [], 0.1)
    if not readable:
        continue
    try:
        chunk = os.read(master, 4096)
    except OSError:
        break
    if not chunk:
        break
    output.extend(chunk)
    if b"READY tty=1 foreground=1" in output and not sent_input:
        os.write(master, b"hello from controlling terminal\n")
        sent_input = True
    if b"REPLY hello from controlling terminal" in output and not sent_interrupt:
        os.write(master, b"\x03")
        sent_interrupt = True
    if b"EXIT=" in output:
        break
waited_pid = 0
wait_deadline = started + 40     # the outer subprocess timeout is 60 s; anything longer is a real failure
while waited_pid == 0 and time.monotonic() < wait_deadline:
    waited_pid, status = os.waitpid(pid, os.WNOHANG)
    if waited_pid == 0:
        time.sleep(0.01)
if waited_pid == 0:
    transcript = output.decode(errors="replace")
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    print(transcript)
    raise SystemExit("interactive controller did not finish")
# The controller writes RESTORED and EXIT= as separate writes; drain anything still buffered
# in the pty so a slow second write cannot be mistaken for a missing one.
while True:
    readable, _, _ = select.select([master], [], [], 0.05)
    if not readable:
        break
    try:
        chunk = os.read(master, 4096)
    except OSError:
        break
    if not chunk:
        break
    output.extend(chunk)
os.close(master)
print(output.decode(errors="replace"), end="")
raise SystemExit(os.waitstatus_to_exitcode(status))
'''
    result = subprocess.run([sys.executable, "-c", harness_code, controller_code, child_code],
                            capture_output=True, text=True, timeout=60, check=False)
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert "READY tty=1 foreground=1" in transcript
    assert "REPLY hello from controlling terminal" in transcript
    assert "RESTORED foreground=True" in transcript
    # Depending on whether Python is blocked in input() or sleeping when the
    # terminal sends SIGINT, it reports KeyboardInterrupt (130) or signal death (-2).
    assert "EXIT=-2" in transcript or "EXIT=130" in transcript


def test_project_open_code_plugin_directory_fails_closed(tmp_path):
    worktree = tmp_path / "worktree"
    plugin_dir = worktree / ".opencode" / "plugins"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "untrusted.js").write_text("export default () => ({});")

    with pytest.raises(code_handoff.CodeHandoffError, match="contains OpenCode plugins"):
        code_handoff.assert_no_project_plugins(worktree)


def _git(directory, *args):
    return subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, text=True)


def test_task_worktree_uses_pinned_commit_and_does_not_copy_dirty_source_files(tmp_path):
    project = tmp_path / "source"
    project.mkdir()
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "hutch-test@example.invalid")
    _git(project, "config", "user.name", "Hutch Test")
    (project / "tracked.txt").write_text("committed version\n")
    _git(project, "add", "tracked.txt")
    _git(project, "commit", "-qm", "base")
    record = code_handoff.inspect_project(str(project))
    record.update({"id": "code_0123456789abcdef01234567", "project_name": project.name})
    (project / "tracked.txt").write_text("owner's uncommitted version\n")
    (project / "private-untracked.txt").write_text("must remain in source only\n")

    worktree, branch = code_handoff.create_task_worktree(record, tmp_path / "state")

    assert branch.endswith("89abcdef01234567")
    assert (worktree / "tracked.txt").read_text() == "committed version\n"
    assert not (worktree / "private-untracked.txt").exists()
    assert _git(worktree, "rev-parse", "HEAD").stdout.strip() == record["base_commit"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _prepare_cli_handoff(client, tmp_path, *, key_prefix):
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "hutch-test@example.invalid")
    _git(project, "config", "user.name", "Hutch Test")
    source_readme = project / "README.md"
    source_readme.write_text("A tiny coding fixture.\n")
    _git(project, "add", "README.md")
    _git(project, "commit", "-qm", "base")

    bot = client.post("/api/bots", json={
        "name": "code-helper", "model": "mock/demo", "tools": [],
        "workspace_mode": "folder", "workdir": str(project),
    })
    assert bot.status_code == 201, bot.text
    conversation = client.post("/api/v1/conversations", json={"bot": bot.json()["id"]},
                               headers={"Idempotency-Key": f"{key_prefix}-conversation"}).json()
    sent = client.post(f"/api/v1/conversations/{conversation['id']}/messages",
                       json={"prompt": "Improve this README for new contributors."},
                       headers={"Idempotency-Key": f"{key_prefix}-source"})
    assert sent.status_code == 201, sent.text
    run_id = sent.json()["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/tasks/runs/{run_id}").json()
        if run["terminal"]:
            break
        time.sleep(0.05)
    assert run["status"] == "succeeded"
    messages = client.get(f"/api/v1/conversations/{conversation['id']}").json()["messages"]
    user_message = next(row for row in messages if row["run_id"] == run_id and row["role"] == "user")
    assistant_message = next(row for row in messages if row["run_id"] == run_id and row["role"] == "assistant")
    handoff_response = client.post("/api/v1/code-handoffs", json={
        "conversation_id": conversation["id"], "source_run_id": run_id,
        "source_user_message_id": user_message["id"],
        "source_assistant_message_id": assistant_message["id"],
        "task_brief": "Add one concise contributor setup note to README.md.",
    }, headers={"Idempotency-Key": f"{key_prefix}-reviewed-handoff"})
    assert handoff_response.status_code == 201, handoff_response.text
    return project, source_readme, conversation["id"], handoff_response.json()["id"]


def test_chat_code_handoff_is_reviewed_idempotent_and_does_not_expose_host_paths(client, tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "hutch-test@example.invalid")
    _git(project, "config", "user.name", "Hutch Test")
    (project / "README.md").write_text("A tiny coding fixture.\n")
    _git(project, "add", "README.md")
    _git(project, "commit", "-qm", "base")

    bot_response = client.post("/api/bots", json={
        "name": "code-helper", "model": "mock/demo", "tools": [],
        "workspace_mode": "folder", "workdir": str(project),
    })
    assert bot_response.status_code == 201, bot_response.text
    conversation = client.post("/api/v1/conversations", json={"bot": bot_response.json()["id"]},
                               headers={"Idempotency-Key": "code-handoff-conversation"}).json()
    sent = client.post(f"/api/v1/conversations/{conversation['id']}/messages",
                       json={"prompt": "Help me improve this README for new contributors."},
                       headers={"Idempotency-Key": "code-handoff-source"})
    assert sent.status_code == 201, sent.text
    run_id = sent.json()["id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        state = client.get(f"/api/v1/tasks/runs/{run_id}").json()
        if state["terminal"]:
            break
        time.sleep(0.05)
    assert state["status"] == "succeeded"
    messages = client.get(f"/api/v1/conversations/{conversation['id']}").json()["messages"]
    source_user = next(m for m in messages if m["run_id"] == run_id and m["role"] == "user")
    source_answer = next(m for m in messages if m["run_id"] == run_id and m["role"] == "assistant")
    monkeypatch.setattr(code_handoff, "inspect_opencode", lambda: ("/usr/bin/opencode", "2.0.24"))

    body = {
        "conversation_id": conversation["id"], "source_run_id": run_id,
        "source_user_message_id": source_user["id"], "source_assistant_message_id": source_answer["id"],
        "task_brief": "Improve contributor onboarding and keep the diff focused.",
    }
    headers = {"Idempotency-Key": "reviewed-code-handoff"}
    created = client.post("/api/v1/code-handoffs", json=body, headers=headers)
    assert created.status_code == 201, created.text
    resource = created.json()
    assert resource["status"] == "prepared"
    assert resource["project_name"] == "project"
    assert resource["original_request"] == "Help me improve this README for new contributors."
    assert resource["proposed_brief"] == source_answer["content"]
    assert resource["launch_command"] == f"hutch code run {resource['id']}"
    assert str(project) not in json.dumps(resource)
    with pytest.raises(sqlite3.IntegrityError, match="code handoff request and workspace identity are immutable"):
        with client.app.state.store._tx() as db:
            db.execute("UPDATE code_handoffs SET task_brief = 'silently replaced' WHERE id = ?", (resource["id"],))

    replay = client.post("/api/v1/code-handoffs", json=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["id"] == resource["id"]
    conflict = client.post("/api/v1/code-handoffs", json={**body, "task_brief": "Changed after review."},
                           headers=headers)
    assert conflict.status_code == 409
    listed = client.get(f"/api/v1/code-handoffs?conversation_id={conversation['id']}").json()
    assert [row["id"] for row in listed] == [resource["id"]]
    assert str(project) not in json.dumps(listed)


@pytest.mark.skipif(not hasattr(os, "tcsetpgrp") or sys.platform != "linux", reason="Linux controlling TTY required")
def test_hutch_code_run_interrupts_fake_opencode_and_retains_verified_changes(client, tmp_path, monkeypatch):
    """Exercise the real CLI, process group, persisted status, and retained worktree without a model call."""
    project, source_readme, conversation_id, handoff_id = _prepare_cli_handoff(
        client, tmp_path, key_prefix="code-run")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_opencode = fake_bin / "opencode"
    fake_opencode.write_text("""#!/usr/bin/env python3
import os, signal, sys, time
from pathlib import Path

if sys.argv[1:] == ["--version"]:
    print("opencode v2.0.24")
    raise SystemExit(0)
if sys.argv[1:] == ["mini", "--help"]:
    print("mini --standalone --prompt")
    raise SystemExit(0)
if sys.argv[1:] == ["auth", "list", "--standalone", "--format", "json"]:
    print('[{"provider":"openai","type":"oauth"}]')
    raise SystemExit(0)
if "--auto" in sys.argv:
    raise SystemExit(90)
signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
prompt = sys.argv[sys.argv.index("--prompt") + 1]
print("FAKE_READY tty=%d foreground=%d reviewed=%d isolated=%d private=%d auto=%d" % (
    os.isatty(0), os.tcgetpgrp(0) == os.getpgrp(),
    "Add one concise contributor setup note" in prompt,
    Path.cwd().name.endswith(sys.argv[sys.argv.index("--agent") + 1].removeprefix("hutch-code-")),
    os.environ.get("OPENCODE_DB", "").endswith("/opencode-profile/opencode.db")
    and os.environ.get("HOME", "").endswith("/opencode-profile/home"),
    "--auto" in sys.argv), flush=True)
input("Fixture is ready. Press Enter to apply its reviewed change. ")
readme = Path("README.md")
readme.write_text(readme.read_text() + "Contributor setup: install the project dependencies before running tests.\\n")
print("FAKE_EDITED", flush=True)
while True:
    time.sleep(1)
""", encoding="utf-8")
    fake_opencode.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")

    runner = r'''import sys
from hutch.cli import main
sys.argv = ["hutch", "code", "run", sys.argv[1]]
main()
'''
    harness = r'''import os, pty, select, signal, sys, time
runner, handoff_id = sys.argv[1:3]
child_env = os.environ.copy()
pid, master = pty.fork()
if pid == 0:
    os.execvpe(sys.executable, [sys.executable, "-c", runner, handoff_id], child_env)
output = bytearray()
sent_ready = False
sent_interrupt = False
deadline = time.monotonic() + 18
waited = 0
while time.monotonic() < deadline:
    readable, _, _ = select.select([master], [], [], 0.05)
    if readable:
        try:
            chunk = os.read(master, 8192)
        except OSError:
            chunk = b""
        if chunk:
            output.extend(chunk)
            if b"FAKE_READY tty=1 foreground=1 reviewed=1 isolated=1 private=1 auto=0" in output and not sent_ready:
                os.write(master, b"\n")
                sent_ready = True
            if b"FAKE_EDITED" in output and not sent_interrupt:
                os.write(master, b"\x03")
                sent_interrupt = True
    waited, status = os.waitpid(pid, os.WNOHANG)
    if waited:
        break
if not waited:
    try:
        foreground = os.tcgetpgrp(master)
        os.killpg(foreground, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    os.waitpid(pid, 0)
    print(output.decode(errors="replace"))
    raise SystemExit("hutch code run did not exit after the controlled interrupt")
try:
    while True:
        chunk = os.read(master, 8192)
        if not chunk:
            break
        output.extend(chunk)
except OSError:
    pass
os.close(master)
print(output.decode(errors="replace"), end="")
print("CHILD_EXIT=%d" % os.waitstatus_to_exitcode(status))
raise SystemExit(0)
'''
    process = subprocess.run([sys.executable, "-c", harness, runner, handoff_id],
                              capture_output=True, text=True, timeout=22, check=False, env=os.environ.copy())
    transcript = process.stdout + process.stderr
    assert process.returncode == 0, transcript
    assert "CHILD_EXIT=130" in transcript, transcript
    assert "FAKE_READY tty=1 foreground=1 reviewed=1 isolated=1 private=1 auto=0" in transcript, transcript
    assert "FAKE_EDITED" in transcript, transcript
    assert "Worktree retained at:" in transcript, transcript

    handoffs = client.get(f"/api/v1/code-handoffs?conversation_id={conversation_id}").json()
    record = next(row for row in handoffs if row["id"] == handoff_id)
    assert record["status"] == "stopped"
    assert record["exit_code"] == 130 or record["exit_code"] == -2
    assert record["changed_files"] == 1
    assert record["branch_name"].startswith("hutch/code/")
    assert str(tmp_path) not in json.dumps(handoffs)  # The public status remains host-path-free.
    worktree = Path(client.app.state.store.code_handoff(handoff_id)["worktree_path"])
    assert worktree.is_dir()
    assert "Contributor setup:" in (worktree / "README.md").read_text()
    assert source_readme.read_text() == "A tiny coding fixture.\n"


def test_code_reconcile_keeps_live_runner_then_marks_gone_runner_interrupted(client, tmp_path):
    """Reconciliation must neither signal a live recorded group nor leave a dead owner stuck."""
    from hutch import procguard

    if not procguard.pidfd_available():
        pytest.skip("verified Linux pidfd signaling is required")
    _project, _source_readme, conversation_id, handoff_id = _prepare_cli_handoff(
        client, tmp_path, key_prefix="code-reconcile")
    worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    saved_identity = None
    try:
        identity = procguard.identity(worker.pid)
        assert identity is not None and identity.pgrp == worker.pid
        saved_identity = {
            "pid": worker.pid, "pgid": worker.pid, "starttime": identity.starttime,
            "boot_id": procguard.boot_id(), "session": identity.session,
        }
        store = client.app.state.store
        store.claim_code_handoff(handoff_id)
        store.start_code_handoff(handoff_id, worktree_path="fixture-worktree", branch_name="hutch/code/fixture",
                                 opencode_version="2.0.24", runner_pid=identity.pid,
                                 runner_starttime=identity.starttime, runner_boot_id=saved_identity["boot_id"],
                                 runner_session=identity.session)

        reconcile = r'''import sys
from hutch.cli import main
sys.argv = ["hutch", "code", "reconcile", sys.argv[1]]
main()
'''
        live = subprocess.run([sys.executable, "-c", reconcile, handoff_id], capture_output=True, text=True,
                              timeout=8, check=False, env=os.environ.copy())
        assert live.returncode == 0, live.stdout + live.stderr
        assert "process group is still present" in live.stdout
        assert store.code_handoff(handoff_id)["status"] == "running"
        assert worker.poll() is None

        assert procguard.end_recorded([saved_identity], term_grace=0.5, kill_grace=1) == []
        worker.wait(timeout=3)
        gone = subprocess.run([sys.executable, "-c", reconcile, handoff_id], capture_output=True, text=True,
                              timeout=8, check=False, env=os.environ.copy())
        assert gone.returncode == 0, gone.stdout + gone.stderr
        assert "Marked interrupted after verifying" in gone.stdout
        assert store.code_handoff(handoff_id)["status"] == "interrupted"
        with pytest.raises(ValueError, match="interrupted and cannot be launched again"):
            store.claim_code_handoff(handoff_id)
    finally:
        if worker.poll() is None:
            if saved_identity is not None:
                procguard.end_recorded([saved_identity], term_grace=0.5, kill_grace=1)
            if worker.poll() is None:
                worker.terminate()
            worker.wait(timeout=3)
