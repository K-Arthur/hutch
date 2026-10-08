from __future__ import annotations

import pytest

from hutch.approvals import ApprovalGate, DeniedError
from hutch.models import ApprovalMode, ApprovalRequest, Bot, Event, EventType, Run, RunStatus
from hutch.safety import PolicyEngine
from hutch.tools import build_tools, expand_tools
from hutch.tools.base import ToolContext


def make_ctx(store, config, tmp_path, bot: Bot | None = None, approval_mode=ApprovalMode.ask):
    bot = bot or Bot(name="tester", instructions="test", tools=["shell", "files", "memory"], approval_mode=approval_mode)
    if not store.get_bot(bot.name):
        store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="test", status=RunStatus.running)    # a gate only ever waits inside a run that has started
    store.create_run(run)
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)

    emitted: list[Event] = []
    def emit(ev: Event):
        emitted.append(ev)
        store.append_event(ev)

    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(
        bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
        config=config, workspace=workspace, emit=emit,
    )
    ctx._emitted = emitted  # for assertions
    return ctx


def test_expand_tool_groups():
    assert expand_tools(["files", "memory", "shell"]) == [
        "read_file", "list_files", "write_file", "remember", "recall", "shell",
    ]
    assert expand_tools(["shell", "shell"]) == ["shell"]


def test_shell_readonly_runs_without_asking(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    tools = build_tools(["shell"], ctx)
    res = tools["shell"].run({"command": "echo hello && pwd"}, ctx)
    assert res.ok
    assert "hello" in res.output
    assert str(ctx.workspace) in res.output
    assert store.pending_approvals() == []  # nothing asked


def test_shell_drains_both_streams_with_a_bounded_capture(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path, approval_mode=ApprovalMode.auto)
    tools = build_tools(["shell"], ctx)
    command = "python3 -c 'import sys; sys.stdout.write(\"x\"*1100000); sys.stderr.write(\"y\"*1100000)'"
    result = tools["shell"].run({"command": command, "timeout": 10}, ctx)
    assert len(result.output.encode("utf-8")) < 1_100_000
    assert "output clipped while draining" in result.output


def test_shell_denied_action_reports_denial(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    tools = build_tools(["shell"], ctx)
    res = tools["shell"].run({"command": "sudo pacman -Syu"}, ctx)
    assert not res.ok
    assert "deny" in res.output.lower()
    # no approval request created for hard-denied actions
    assert store.pending_approvals() == []


def test_shell_ask_creates_approval_and_sticky_skips(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    tools = build_tools(["shell"], ctx)

    # Simulate a human approving with "always allow"
    def auto_approver():
        import time as _t
        for _ in range(200):
            pend = store.pending_approvals()
            if pend:
                from hutch.approvals import resolve_approval
                resolve_approval(store, pend[0].id, approve=True, by="test", sticky=True)
                return
            _t.sleep(0.01)

    import threading
    t = threading.Thread(target=auto_approver); t.start()
    res = tools["shell"].run({"command": "rm -rf build/"}, ctx)
    t.join(timeout=5)
    assert res.ok or "exit" in res.output  # rm of missing dir may exit non-zero — the point is it RAN

    # second identical call: sticky allow means no new approval
    res2 = tools["shell"].run({"command": "rm -rf build/"}, ctx)
    assert "sticky-allowed" in res2.output or res2.ok


def test_shell_auto_mode_skips_asking(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path, approval_mode=ApprovalMode.auto)
    tools = build_tools(["shell"], ctx)
    res = tools["shell"].run({"command": "mkdir -p build && rm -rf build"}, ctx)
    assert res.ok
    assert store.pending_approvals() == []


def test_files_jail(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    tools = build_tools(["files"], ctx)

    (ctx.workspace / "note.txt").write_text("hello")
    assert tools["read_file"].run({"path": "note.txt"}, ctx).output == "hello"
    denied = tools["read_file"].run({"path": "../../secrets"}, ctx)
    assert not denied.ok and "escape" in denied.output

    outside = tools["write_file"].run({"path": "/tmp/evil.txt", "content": "x"}, ctx)
    assert not outside.ok
    outside2 = tools["write_file"].run({"path": str(tmp_path / "x.txt"), "content": "x"}, ctx)
    assert not outside2.ok


def test_files_write_with_sticky_allow(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    store.allow_sticky(ctx.bot.id, "files:write")
    tools = build_tools(["files"], ctx)
    res = tools["write_file"].run({"path": "out/report.md", "content": "# hi"}, ctx)
    assert res.ok
    assert (ctx.workspace / "out" / "report.md").read_text() == "# hi"


def test_memory_tools_scoped_to_bot(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    tools = build_tools(["memory"], ctx)
    tools["remember"].run({"key": "style", "value": "concise"}, ctx)
    res = tools["recall"].run({}, ctx)
    assert "style: concise" in res.output

    other = Bot(name="other", instructions="", tools=[])
    store.create_bot(other)
    assert store.recall_all(other.id) == []  # no cross-bot leakage


def test_memory_equal_content_keeps_bot_scope_through_recall_and_forget(store, config, tmp_path):
    a = make_ctx(store, config, tmp_path)
    b = make_ctx(store, config, tmp_path, bot=Bot(name="separate-memory", tools=["memory"]))
    tools = build_tools(["memory"], a)
    for ctx in (a, b):
        assert tools["remember"].run({"key": "style", "value": "concise"}, ctx).ok
        assert "style: concise" in tools["recall"].run({}, ctx).output
    assert store.forget(a.bot.id, "style")
    assert "style: concise" not in tools["recall"].run({}, a).output
    assert "style: concise" in tools["recall"].run({}, b).output


def test_webfetch_denies_private_and_allows_check(store, config, tmp_path, monkeypatch):
    ctx = make_ctx(store, config, tmp_path)
    tools = build_tools(["web_fetch"], ctx)

    res = tools["web_fetch"].run({"url": "http://169.254.169.254/meta"}, ctx)
    assert not res.ok and "error" in res.output.lower()
    res = tools["web_fetch"].run({"url": "file:///etc/passwd"}, ctx)
    assert not res.ok

    from hutch.netguard import Fetched
    import hutch.tools.webfetch as wf

    def fake_safe_get(url, **kw):
        assert url == "https://example.com/x"
        return Fetched(status=200, reason="OK", headers={"content-type": "text/html"},
                       text="<html><body>hi there</body></html>", url=url)
    monkeypatch.setattr(wf, "safe_get", fake_safe_get)
    res = tools["web_fetch"].run({"url": "https://example.com/x"}, ctx)
    assert res.ok and "hi there" in res.output


def test_shell_home_is_workspace(store, config, tmp_path):
    """Bots must not see the user's real HOME (~/.ssh etc.)."""
    ctx = make_ctx(store, config, tmp_path)
    tools = build_tools(["shell"], ctx)
    res = tools["shell"].run({"command": "echo $HOME"}, ctx)
    assert str(ctx.workspace) in res.output
