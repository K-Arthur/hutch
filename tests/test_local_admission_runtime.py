"""Local HTTP fixtures exercise admission around real runtime tools and decisions."""
from __future__ import annotations

import copy
import threading
import time

import pytest

from hutch.approvals import ApprovalGate, resolve_approval
from hutch.hardware import Gpu, Hardware
from hutch.models import ApprovalMode, Bot, EventType, Run, RunStatus
from hutch.providers.ollama import OllamaProvider
from hutch.runtime import RunAborted
from hutch.runtime.builtin import BuiltinRuntime
from hutch.safety import PolicyEngine
from hutch.tools import build_tools
from hutch.tools.base import ToolContext
from tests.fakes import FakeOllama
from tests.test_runtime_builtin import BIG_BOX, WRITE


def wait_for(predicate):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        if value := predicate():
            return value
        time.sleep(0.005)
    pytest.fail("fixture did not reach the expected state")


def context(store, config, tmp_path, name):
    bot = store.create_bot(Bot(name=name, model="ollama/fake:8b", tools=["files"], selfcheck=False,
                              approval_mode=ApprovalMode.ask))
    run = store.create_run(Run(bot_id=bot.id, prompt=name))
    run = store.claim_run(run.id, name, 30, max_live=20)
    run = store.transition_run(run.id, RunStatus.running, fence=run.fence)
    workspace = tmp_path / name
    workspace.mkdir()
    emit = store.append_event
    policy = PolicyEngine()
    gate = ApprovalGate(store, bot, run, policy, emit, poll_seconds=0.01)
    ctx = ToolContext(bot, run, store, policy, gate, config, workspace, emit=emit)
    return ctx, run, build_tools(bot.tools, ctx)


def execute(rt, ctx, run, tools, result):
    try:
        result["reply"] = rt.execute(run, ctx, tools, lambda: False)
    except BaseException as exc:
        result["error"] = exc


@pytest.mark.parametrize("stop_while_queued", [False, True])
def test_human_wait_releases_slot_and_resumed_turn_waits_without_reserving_usage(store, config, tmp_path, stop_while_queued):
    server = FakeOllama(load_delay=0.001)
    entered, release = threading.Event(), threading.Event()
    writer, other = context(store, config, tmp_path, "writer"), context(store, config, tmp_path, "other")
    threads, results = [], [{}, {}]

    def script(body):
        user = next(m["content"] for m in body["messages"] if m["role"] == "user")
        if user == "other":
            entered.set()
            assert release.wait(5)
            return {"content": "other finished", "prompt_tokens": 10, "completion_tokens": 2}
        if any(m["role"] == "tool" for m in body["messages"]):
            return {"content": "writer finished", "prompt_tokens": 12, "completion_tokens": 2}
        return {"content": "review this write", "tool_calls": [WRITE], "prompt_tokens": 10, "completion_tokens": 3}

    server.script = script
    runtime = lambda: BuiltinRuntime(hardware=BIG_BOX, provider_factory=lambda *args: OllamaProvider(server.url))
    try:
        first = threading.Thread(target=execute, args=(runtime(), *writer, results[0]))
        threads.append(first)
        first.start()
        request = wait_for(lambda: next(iter(store.pending_approvals()), None))
        assert store.get_run(writer[1].id).status is RunStatus.waiting_approval
        second = threading.Thread(target=execute, args=(runtime(), *other, results[1]))
        threads.append(second)
        second.start()
        assert entered.wait(3), "a human wait retained inference authority"
        assert resolve_approval(store, request.id, True, by="fixture")
        wait_for(lambda: store.get_run(writer[1].id).status is RunStatus.waiting_resources)
        with store._lock:
            reservations = store._db.execute("SELECT status FROM usage_reservations WHERE run_id = ?", (writer[1].id,)).fetchall()
        assert [r["status"] for r in reservations] == ["settled"], "a queued next call reserved usage before admission"
        assert "queue position" in store.get_run(writer[1].id).reason
        if stop_while_queued:
            store.request_cancel(writer[1].id)
            first.join(timeout=2)
            assert not first.is_alive() and isinstance(results[0]["error"], RunAborted)
            assert results[0]["error"].reason == "stopped"
    finally:
        release.set()
        for ctx, run, tools in (writer, other):
            if store.pending_approvals(bot_id=ctx.bot.id):
                ctx.gate.cancel_requested = True
        for thread in threads:
            thread.join(timeout=5)
        server.close()
    assert all(not t.is_alive() for t in threads)
    assert results[1] == {"reply": "other finished"}
    assert (writer[0].workspace / "out.md").read_text() == "hello"
    if stop_while_queued:
        with store._lock:
            reservations = store._db.execute("SELECT status FROM usage_reservations WHERE run_id = ?", (writer[1].id,)).fetchall()
        assert [r["status"] for r in reservations] == ["settled"]
        assert len(server.of("/api/chat")) == 2
        return
    assert results[0] == {"reply": "writer finished"}
    assert store.get_run(writer[1].id).queue_ms > 0
    steps = [e.data for e in store.list_events(writer[1].id) if e.type is EventType.step]
    assert steps[-1]["queue_ms"] > 0
    assert any(e.data.get("kind") == "resource_wait" for e in store.list_events(writer[1].id))


def test_memory_pressure_after_approval_refuses_the_next_generation(store, config, tmp_path):
    server = FakeOllama(load_delay=0.001)
    ctx, run, tools = context(store, config, tmp_path, "pressure")
    server.script = lambda body: {"content": "write", "tool_calls": [WRITE], "prompt_tokens": 10, "completion_tokens": 3}
    rt = BuiltinRuntime(hardware=copy.deepcopy(BIG_BOX), provider_factory=lambda *args: OllamaProvider(server.url))
    result = {}
    thread = threading.Thread(target=execute, args=(rt, ctx, run, tools, result))
    thread.start()
    try:
        request = wait_for(lambda: next(iter(store.pending_approvals()), None))
        rt._hw.gpus[0].free_gb = 0.0
        assert resolve_approval(store, request.id, True, by="fixture")
    finally:
        thread.join(timeout=5)
        ctx.gate.cancel_requested = True
        thread.join(timeout=5)
        server.close()
    assert not thread.is_alive()
    assert isinstance(result["error"], RunAborted) and "headroom" in result["error"].detail
    assert len(server.of("/api/chat")) == 1


def test_unknown_gpu_headroom_is_refused_before_loading_or_generation(store, config, tmp_path):
    server = FakeOllama(load_delay=0.001)
    ctx, run, tools = context(store, config, tmp_path, "unknown")
    hardware = Hardware(gpus=[Gpu("unknown", "nvidia", 24)], ram_total_gb=64, ram_available_gb=48)
    try:
        with pytest.raises(RunAborted, match="free GPU memory could not be measured"):
            BuiltinRuntime(hardware=hardware, provider_factory=lambda *args: OllamaProvider(server.url)).execute(
                run, ctx, tools, lambda: False)
        assert not server.of("/api/generate") and not server.of("/api/chat")
    finally:
        server.close()


def test_measured_zero_gpu_memory_never_falls_back_to_total_capacity():
    hardware = Hardware(gpus=[Gpu("busy", "nvidia", 24, free_gb=0)], ram_total_gb=64, ram_available_gb=48)
    assert hardware.budget_gb == 0
