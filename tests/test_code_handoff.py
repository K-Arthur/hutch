from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time

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


def test_opencode_environment_removes_inherited_credentials_and_config_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", '{"agents":{"build":{"permissions":[]}}}')
    monkeypatch.setenv("OPENCODE_PERMISSION", '{"shell":"allow"}')
    monkeypatch.setenv("OPENCODE_DB", "/tmp/user-opencode.db")
    monkeypatch.setenv("PYTHONPATH", "/tmp/hostile-python")
    config = tmp_path / "task.json"
    config.write_text("{}")

    env = code_handoff.safe_opencode_environment(config, cache_home=tmp_path / "cache")
    assert env["PATH"] == "/usr/bin"
    assert env["OPENCODE_CONFIG"] == str(config)
    assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert env["OPENCODE_AUTO_SHARE"] == "0"
    assert "OPENAI_API_KEY" not in env
    assert "OPENCODE_CONFIG_CONTENT" not in env
    assert "OPENCODE_PERMISSION" not in env
    assert "OPENCODE_DB" not in env
    assert "PYTHONPATH" not in env


@pytest.mark.skipif(not hasattr(os, "tcsetpgrp") or sys.platform != "linux", reason="Linux controlling TTY required")
def test_interactive_process_keeps_terminal_and_owns_a_separate_group():
    """The coding runner must get foreground terminal input without leaving task children behind."""
    child_code = r'''
import os, sys, time
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
deadline = time.monotonic() + 8
sent_input = False
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
    if b"RESTORED foreground=True" in output:
        break
waited_pid = 0
wait_deadline = time.monotonic() + 2
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
os.close(master)
print(output.decode(errors="replace"), end="")
raise SystemExit(os.waitstatus_to_exitcode(status))
'''
    result = subprocess.run([sys.executable, "-c", harness_code, controller_code, child_code],
                            capture_output=True, text=True, timeout=15, check=False)
    transcript = result.stdout + result.stderr
    assert result.returncode == 0, transcript
    assert "READY tty=1 foreground=1" in transcript
    assert "REPLY hello from controlling terminal" in transcript
    assert "RESTORED foreground=True" in transcript
    assert "EXIT=-2" in transcript


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
