"""Receipts bracket the EFFECT (ADR-0003): intent just before the tool acts, receipt just after - never around an approval wait."""

from __future__ import annotations

import threading
import time

from hutch.approvals import resolve_approval
from hutch.models import ApprovalMode, Bot, Event, EventType, Run, RunStatus
from hutch.runtime.steps import call_tool
from hutch.safety import PolicyEngine
from hutch.approvals import ApprovalGate
from hutch.tools import build_tools
from hutch.tools.base import ToolContext


def make(store, config, tmp_path, mode=ApprovalMode.ask, tools=("shell", "files")):
    bot = store.create_bot(Bot(name="r", model="mock/demo", tools=list(tools), approval_mode=mode))
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    emit = lambda ev: store.append_event(ev)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config, workspace=ws, emit=emit)
    return run, ctx, build_tools(bot.tools, ctx)


def test_waiting_for_approval_is_not_an_effect_and_leaves_no_intent(store, config, tmp_path):
    run, ctx, tools = make(store, config, tmp_path)
    out = {}
    t = threading.Thread(target=lambda: out.update(r=call_tool(run, ctx, tools, "write_file", {"path": "a.txt", "content": "hi"})))
    t.start()
    deadline = time.time() + 10
    while time.time() < deadline and not store.pending_approvals():
        time.sleep(0.02)
    assert store.pending_approvals()
    assert store.list_actions(run.id) == [] and store.actions_in_doubt(run.id) == []      # nothing has happened yet
    resolve_approval(store, store.pending_approvals()[0].id, approve=True, by="test")
    t.join(10)
    assert out["r"].ok and (ctx.workspace / "a.txt").read_text() == "hi"
    [a] = store.list_actions(run.id)
    assert a["tool"] == "write_file" and a["status"] == "done" and a["result_digest"] and a["effect"] == "fs"


def test_a_denied_action_has_no_receipt(store, config, tmp_path):
    run, ctx, tools = make(store, config, tmp_path)
    out = {}
    t = threading.Thread(target=lambda: out.update(r=call_tool(run, ctx, tools, "write_file", {"path": "a.txt", "content": "hi"})))
    t.start()
    deadline = time.time() + 10
    while time.time() < deadline and not store.pending_approvals():
        time.sleep(0.02)
    resolve_approval(store, store.pending_approvals()[0].id, approve=False, by="test")
    t.join(10)
    assert not out["r"].ok and not (ctx.workspace / "a.txt").exists()
    assert store.list_actions(run.id) == []


def test_reads_have_no_receipts_and_a_failed_command_is_receipted_as_failed(store, config, tmp_path):
    run, ctx, tools = make(store, config, tmp_path, mode=ApprovalMode.auto)
    assert call_tool(run, ctx, tools, "shell", {"command": "ls"}).ok
    assert store.list_actions(run.id) == []                                  # read-only: nothing to account for
    res = call_tool(run, ctx, tools, "shell", {"command": "echo x > f.txt && exit 3"})
    assert not res.ok
    [a] = store.list_actions(run.id)
    assert a["status"] == "failed" and a["effect"] == "process" and "f.txt" in a["summary"]


def test_if_the_intent_cannot_be_recorded_the_action_does_not_run(store, config, tmp_path, monkeypatch):
    run, ctx, tools = make(store, config, tmp_path, mode=ApprovalMode.auto)

    def broken(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(store, "begin_action", broken)
    res = call_tool(run, ctx, tools, "write_file", {"path": "never.txt", "content": "x"})
    assert not res.ok and "could not be recorded" in res.output
    assert not (ctx.workspace / "never.txt").exists()                       # fail closed: no receipt, no effect


def test_a_run_that_is_being_stopped_cannot_start_a_new_effect(store, config, tmp_path):
    run, ctx, tools = make(store, config, tmp_path, mode=ApprovalMode.auto)
    store.request_cancel(run.id)                                             # a stop arrived from anywhere
    res = call_tool(run, ctx, tools, "write_file", {"path": "late.txt", "content": "x"})
    assert not res.ok and not (ctx.workspace / "late.txt").exists()
