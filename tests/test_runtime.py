from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

import openbot.runtime.builtin as builtin_mod
from openbot.approvals import ApprovalGate, resolve_approval
from openbot.models import ApprovalMode, Bot, Event, EventType, Run, RunStatus
from openbot.runtime import MockRuntime, OpenCodeRuntime, PiRuntime, RunAborted, get_runtime, BuiltinRuntime
from openbot.safety import PolicyEngine
from openbot.tools import build_tools
from openbot.tools.base import ToolContext


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

    assert "report.md" in final
    assert (ctx.workspace / "report.md").exists()
    assert any(e.type is EventType.tool_call for e in emitted)
    assert any(e.type is EventType.message for e in emitted)
    assert store.recall_all(ctx.bot.id)  # memory was written
    assert run.steps >= 3


def test_mock_runtime_ask_mode_pauses_for_approval(store, config, tmp_path):
    ctx, run, _ = make_ctx(store, config, tmp_path, approval_mode=ApprovalMode.ask)
    tools = build_tools(ctx.bot.tools, ctx)

    def auto_approver():
        for _ in range(500):
            pend = store.pending_approvals()
            if pend:
                resolve_approval(store, pend[0].id, approve=True, by="test", sticky=False)
                return
            time.sleep(0.01)

    t = threading.Thread(target=auto_approver)
    t.start()
    final = MockRuntime().execute(run, ctx, tools, stop=lambda: False)
    t.join(timeout=5)
    assert "report.md" in final
    assert len(store.pending_approvals()) == 0


def test_mock_runtime_stop_requested(store, config, tmp_path):
    ctx, run, _ = make_ctx(store, config, tmp_path)
    tools = build_tools(ctx.bot.tools, ctx)
    with pytest.raises(RunAborted) as exc:
        MockRuntime().execute(run, ctx, tools, stop=lambda: True)
    assert exc.value.reason == "stopped"


def _fake_openai_sequence(responses):
    """Return a fake OpenAI constructor whose chat yields the given responses."""
    calls = {"n": 0}

    class FakeCompletions:
        def create(self, **kwargs):
            r = responses[min(calls["n"], len(responses) - 1)]
            calls["n"] += 1
            return r

    class FakeClient:
        def __init__(self, *a, **kw):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    return FakeClient


def _tool_call_response(call_id, name, args_json):
    tc = SimpleNamespace(id=call_id,
                         function=SimpleNamespace(name=name, arguments=args_json))
    msg = SimpleNamespace(content=None, tool_calls=[tc])
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                           usage=SimpleNamespace(total_tokens=120))


def _final_response(text):
    msg = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                           usage=SimpleNamespace(total_tokens=80))


def test_builtin_loop_tool_call_flow(store, config, tmp_path, monkeypatch):
    ctx, run, _ = make_ctx(store, config, tmp_path)
    ctx.bot.model = "openai/gpt-4o-mini"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    responses = [
        _tool_call_response("c1", "write_file",
                            '{"path": "hello.md", "content": "# from builtin loop"}'),
        _final_response("Wrote hello.md as requested."),
    ]
    FakeClient = _fake_openai_sequence(responses)
    monkeypatch.setattr(builtin_mod, "OpenAI", FakeClient)

    tools = build_tools(["files"], ctx)
    final = BuiltinRuntime().execute(run, ctx, tools, stop=lambda: False)
    assert final == "Wrote hello.md as requested."
    assert (ctx.workspace / "hello.md").read_text() == "# from builtin loop"
    assert run.tokens == 200


def test_builtin_loop_provider_errors_abort(store, config, tmp_path, monkeypatch):
    ctx, run, _ = make_ctx(store, config, tmp_path)
    ctx.bot.model = "openai/gpt-4o-mini"

    class ExplodingClient:
        def __init__(self, *a, **kw):
            self.chat = SimpleNamespace(completions=SimpleNamespace(
                create=self._boom))

        def _boom(self, **kw):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(builtin_mod, "OpenAI", ExplodingClient)
    with pytest.raises(RunAborted) as exc:
        BuiltinRuntime().execute(run, ctx, {}, stop=lambda: False)
    assert exc.value.reason == "error"
    assert "connection refused" in exc.value.detail


def test_builtin_loop_token_cap_aborts(store, config, tmp_path, monkeypatch):
    ctx, run, _ = make_ctx(store, config, tmp_path)
    ctx.bot.model = "openai/gpt-4o-mini"
    from openbot.models import Limits
    ctx.bot.limits = Limits(daily_token_cap=50)
    # pre-consume cap
    run.tokens = 1000
    store.update_run(run)

    with pytest.raises(RunAborted) as exc:
        BuiltinRuntime().execute(run, ctx, {}, stop=lambda: False)
    assert exc.value.reason == "token_cap"


def test_missing_external_runtime_binaries_fail_gracefully(store, config, tmp_path):
    ctx, run, _ = make_ctx(store, config, tmp_path)
    with pytest.raises(RunAborted) as exc:
        PiRuntime(binary="not-a-real-pi-binary").execute(run, ctx, {}, stop=lambda: False)
    assert "not found on PATH" in exc.value.detail
    with pytest.raises(RunAborted) as exc:
        OpenCodeRuntime(binary="not-a-real-opencode-binary").execute(run, ctx, {}, stop=lambda: False)
    assert "not found on PATH" in exc.value.detail
