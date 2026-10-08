from __future__ import annotations

import threading
import time

import pytest

from hutch.approvals import ApprovalGate, resolve_approval
from hutch.models import ApprovalMode, Bot, Event, EventType, Run, RunStatus
from hutch.runtime import MockRuntime, OpenCodeRuntime, PiRuntime, RunAborted, get_runtime, BuiltinRuntime
from hutch.safety import PolicyEngine
from hutch.tools import build_tools
from hutch.tools.base import ToolContext


def make_ctx(store, config, tmp_path, approval_mode=ApprovalMode.auto, tools=("shell", "files", "memory")):
    bot = Bot(name="tester", instructions="be brief", model="mock/demo",
              tools=list(tools), approval_mode=approval_mode)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="research the weekly news and summarize")
    store.create_run(run)
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    emitted: list[Event] = []

    def emit(ev: Event):
        emitted.append(ev)
        store.append_event(ev)

    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=config, workspace=workspace, emit=emit)
    return ctx, run, emitted


def test_get_runtime_dispatch():
    assert get_runtime(Bot(name="a", model="mock/demo")).kind == "mock"
    assert get_runtime(Bot(name="b", runtime="pi")).kind == "pi"
    assert get_runtime(Bot(name="c", runtime="opencode")).kind == "opencode"
    assert get_runtime(Bot(name="d", model="openai/gpt-4o-mini")).kind == "builtin"


def test_mock_runtime_end_to_end(store, config, tmp_path):
    ctx, run, emitted = make_ctx(store, config, tmp_path)
    tools = build_tools(ctx.bot.tools, ctx)
    final = MockRuntime().execute(run, ctx, tools, stop=lambda: False)

    assert (ctx.workspace / "report.md").exists()
    # This summary is a demo of the real tool layer, while its saved reference
    # fact remains a proposal until reviewed in chat.
    proposals = [item for item in store.recall_all(ctx.bot.id) if item.status == "proposed"]
    assert proposals
    assert "human review" in final
    assert any(e.type is EventType.tool_call for e in emitted)
    assert any(e.type is EventType.message for e in emitted)
    assert store.recall_all(ctx.bot.id)  # memory was written
    assert run.steps >= 3


def test_mock_runtime_ask_mode_pauses_for_approval(store, config, tmp_path):
    ctx, run, _ = make_ctx(store, config, tmp_path, approval_mode=ApprovalMode.ask)
    # This direct runtime fixture has no supervisor to claim its run. Put its
    # unowned fixture row into the same running state a claimed worker uses.
    store.transition_run(run.id, RunStatus.running, fence=0)
    run.status = RunStatus.running
    tools = build_tools(ctx.bot.tools, ctx)

    stop_approver = threading.Event()

    def auto_approver():
        deadline = time.monotonic() + 5
        while not stop_approver.is_set() and time.monotonic() < deadline:
            pend = store.pending_approvals()
            if pend:
                resolve_approval(store, pend[0].id, approve=True, by="test", sticky=False)
            else:
                stop_approver.wait(0.01)

    t = threading.Thread(target=auto_approver)
    t.start()
    try:
        final = MockRuntime().execute(run, ctx, tools, stop=lambda: False)
    finally:
        stop_approver.set()
        t.join(timeout=2)
        assert not t.is_alive(), "approval helper must exit before the Store fixture closes"
    assert (ctx.workspace / "report.md").exists()
    assert "human review" in final
    assert len(store.pending_approvals()) == 0


def test_mock_runtime_stop_requested(store, config, tmp_path):
    ctx, run, _ = make_ctx(store, config, tmp_path)
    tools = build_tools(ctx.bot.tools, ctx)
    with pytest.raises(RunAborted) as exc:
        MockRuntime().execute(run, ctx, tools, stop=lambda: True)
    assert exc.value.reason == "stopped"


def test_builtin_loop_token_cap_aborts(store, config, tmp_path, monkeypatch):
    ctx, run, _ = make_ctx(store, config, tmp_path)
    ctx.bot.model = "openai/gpt-4o-mini"
    from hutch.models import Limits
    ctx.bot.limits = Limits(daily_token_cap=50)
    # pre-consume cap
    run.tokens = 1000
    store.update_run(run)

    with pytest.raises(RunAborted) as exc:
        BuiltinRuntime().execute(run, ctx, {}, stop=lambda: False)
    assert exc.value.reason == "token_cap"


def test_external_runtimes_fail_closed_until_governance_exists(store, config, tmp_path):
    ctx, run, _ = make_ctx(store, config, tmp_path)
    with pytest.raises(RunAborted, match="disabled until Hutch can contain"):
        PiRuntime(binary="not-a-real-pi-binary").execute(run, ctx, {}, stop=lambda: False)
    with pytest.raises(RunAborted, match="disabled until Hutch can broker"):
        OpenCodeRuntime(binary="not-a-real-opencode-binary").execute(run, ctx, {}, stop=lambda: False)
