"""The built-in loop over the provider layer: every guard, exercised against scripted fake models.

Each test names the requirement it proves. Real local models were not available on the dev machine, so the
behaviours a real model would show (silent truncation, malformed calls, loops, stalls, cold loads) are scripted.
"""

from __future__ import annotations

import json
import hashlib
import threading
import time

import pytest

from hutch.approvals import ApprovalGate, resolve_approval
from hutch.hardware import Hardware, Gpu
from hutch.models import (ApprovalMode, Bot, Escalation, Event, EventType, Limits, Run, RunStatus)
from hutch.providers.claude import ClaudeProvider
from hutch.providers.ollama import OllamaProvider
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.providers.pricing import PriceBook
from hutch.runtime import RunAborted
from hutch.runtime.builtin import BuiltinRuntime, reset_connection_cache
from hutch.runtime.ladder import reset_provider_cache
from hutch.safety import PolicyEngine
from hutch.tools import build_tools
from hutch.tools.base import ToolContext
from tests.fakes import FakeAnthropic, FakeOllama, FakeOpenAI, agent_script

BIG_BOX = Hardware(gpus=[Gpu("X", "nvidia", 24.0, False, 24.0)], ram_total_gb=64, ram_available_gb=48)
WRITE = {"name": "write_file", "arguments": {"path": "out.md", "content": "hello"}}


@pytest.fixture(autouse=True)
def _fresh_providers():
    reset_provider_cache()
    reset_connection_cache()


@pytest.fixture()
def ollama():
    s = FakeOllama({"fake:8b": {}, "tiny:1b": {"params": "1.0B", "size": 800_000_000, "ctx": 8192}})
    yield s
    s.close()


@pytest.fixture()
def oai():
    s = FakeOpenAI()
    yield s
    s.close()


def build(store, config, tmp_path, *, model="ollama/fake:8b", tools=("files",), mode=ApprovalMode.auto,
          prompt="write a file", conversation_id="", **bot_kw):
    bot_kw.setdefault("selfcheck", False)
    bot_kw.setdefault("instructions", "be brief")
    bot = Bot(name="rt-bot", model=model, tools=list(tools), approval_mode=mode, description="d", **bot_kw)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt=prompt, conversation_id=conversation_id)
    store.create_run(run)
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    emitted: list[Event] = []

    def emit(ev):
        emitted.append(ev)
        store.append_event(ev)

    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.05)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config, workspace=ws,
                      emit=emit)
    return ctx, run, emitted, build_tools(bot.tools, ctx)


def factory(ollama=None, oai=None, claude=None, lmstudio=None):
    def make(provider, base_url):
        if provider == "ollama":
            return OllamaProvider(ollama.url if ollama else "http://127.0.0.1:9")
        if provider == "openai":
            return OpenAICompatProvider(oai.url + "/v1", "k", "openai")
        if provider == "lmstudio":
            return OpenAICompatProvider(lmstudio.url + "/v1", "", "lmstudio")
        if provider == "anthropic":
            return ClaudeProvider(api_key="sk-test", base_url=claude.url)
        raise AssertionError(provider)
    return make


def runtime(**kw):
    kw.setdefault("hardware", BIG_BOX)
    kw.setdefault("sleep", lambda s: None)
    return BuiltinRuntime(**kw)


def run_it(rt, run, ctx, tools, stop=lambda: False):
    return rt.execute(run, ctx, tools, stop)


def kinds(emitted, kind):
    return [e.data for e in emitted if e.type is EventType.log and e.data.get("kind") == kind]


# ============================================================ LM-1: explicit context, always

def test_local_run_end_to_end_with_exact_accounting_and_a_frozen_prefix(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "writing", "tool_calls": [WRITE], "prompt_tokens": 400, "completion_tokens": 30},
                                  {"content": "done", "prompt_tokens": 460, "completion_tokens": 12}])
    ctx, run, emitted, tools = build(store, config, tmp_path)
    final = run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert final == "done" and (ctx.workspace / "out.md").read_text() == "hello"
    assert (run.steps, run.prompt_tokens, run.completion_tokens, run.tokens) == (2, 860, 42, 902)    # SR-2: exact
    assert run.context_used == 460 and run.context_limit and run.cost_usd == 0.0
    chats = ollama.of("/api/chat")
    assert all(c["body"]["options"]["num_ctx"] == run.context_limit for c in chats)                   # LM-1
    assert all(c["body"]["options"]["num_predict"] == 2048 for c in chats)                            # SR-5 default cap
    steps = [e.data for e in emitted if e.type is EventType.step]
    assert len(steps) == 2 and steps[0]["prefix"] == steps[1]["prefix"]                               # PF-1
    assert chats[0]["body"]["messages"][0] == chats[1]["body"]["messages"][0]                         # same system prompt
    assert chats[0]["body"]["tools"] == chats[1]["body"]["tools"]                                     # same tool list
    assert [t["function"]["name"] for t in chats[0]["body"]["tools"]] == ["list_files", "read_file", "write_file"]
    plan = kinds(emitted, "plan")[0]
    assert plan["window"] == run.context_limit and "no per-token cost" in plan["note"]                # SR-2 visible before


def test_only_the_bots_allowed_tools_reach_the_prompt(store, config, tmp_path, ollama):          # PF-3
    ollama.script = agent_script([{"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path, tools=("remember",))
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    names = [t["function"]["name"] for t in ollama.of("/api/chat")[0]["body"]["tools"]]
    assert names == ["remember"]


def test_a_bot_with_a_context_override_gets_exactly_that_window(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path, num_ctx=12000)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert ollama.of("/api/chat")[0]["body"]["options"]["num_ctx"] == 12000


# ============================================================ LM-3: pre-run warning

def test_a_prompt_that_cannot_fit_is_refused_before_any_model_call(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path, num_ctx=4096, instructions="x" * 60_000)
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert e.value.reason == "context" and "cannot fit" in e.value.detail and "fewer tools" in e.value.detail
    assert not ollama.of("/api/chat"), "no tokens may be spent on a run that cannot work"


def test_a_prompt_that_crowds_the_window_warns_but_runs(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path, num_ctx=4096, instructions="x" * 4_200)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert any(c.get("severity") == "warn" for c in kinds(emitted, "context"))


# ============================================================ LM-2: self-check gates the first run

def test_selfcheck_passes_is_cached_and_not_repeated(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path, selfcheck=True, num_ctx=8192)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert any(c.get("ok") is True for c in kinds(emitted, "selfcheck"))
    first = len(ollama.of("/api/chat"))
    # a second run of the same model + window reuses the cached result: only the real chat is sent
    bot = store.get_bot("rt-bot")
    run2 = Run(bot_id=bot.id, prompt="again")
    store.create_run(run2)
    ctx3 = ToolContext(bot=bot, run=run2, store=store, policy=ctx.policy, gate=ApprovalGate(
        store, bot, run2, ctx.policy, lambda e: store.append_event(e)), config=config, workspace=ctx.workspace,
        emit=lambda e: store.append_event(e))
    ollama.script = agent_script([{"content": "ok"}])
    run_it(runtime(provider_factory=factory(ollama)), run2, ctx3, build_tools(bot.tools, ctx3))
    assert len(ollama.of("/api/chat")) == first + 1


def test_selfcheck_failure_aborts_loudly_and_spends_nothing_further(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "ok"}], recall=False)          # a model that cannot recall
    ctx, run, emitted, tools = build(store, config, tmp_path, selfcheck=True, num_ctx=8192)
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert e.value.reason == "context" and "self-check failed" in e.value.detail
    assert any(c.get("ok") is False and "FAILED" in c["note"] for c in kinds(emitted, "selfcheck"))
    assert ollama.script.calls == 0, "the agent must never have started"


# ============================================================ LM-6: cold load is a visible state

def test_cold_load_is_a_visible_run_state_with_its_measured_time(store, config, tmp_path, ollama):
    ollama.load_delay = 0.3
    ollama.script = agent_script([{"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    # status changes are written atomically by the store (ADR-0003), so the transcript is where they are observed
    statuses = [e.data["status"] for e in store.list_events(run.id) if e.type is EventType.status]
    assert statuses[:2] == ["loading_model", "running"]
    load = kinds(emitted, "load")[0]
    assert load["load_ms"] >= 250 and "cold load" in load["note"]
    assert json.loads(store.kv_get("model_load:fake:8b"))["ms"] >= 250      # remembered for the wait explanation


# ============================================================ LM-13: repair

def test_a_number_sent_as_a_string_is_repaired_silently_and_logged(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"tool_calls": [{"name": "list_files", "arguments": {"path": 5}}]}, {"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert any("repaired list_files" in c["note"] for c in kinds(emitted, "repair"))


def test_a_missing_required_argument_gets_one_retry_with_the_precise_error(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {"content": "x"}}]},
                                  {"tool_calls": [WRITE]}, {"content": "fixed"}])
    ctx, run, emitted, tools = build(store, config, tmp_path)
    assert run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools) == "fixed"
    second = ollama.of("/api/chat")[1]["body"]["messages"]
    assert "missing required argument 'path'" in second[-1]["content"] and "Expected schema" in second[-1]["content"]
    assert (ctx.workspace / "out.md").exists()


def test_an_invented_tool_is_rejected_with_the_list_of_real_ones(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"tool_calls": [{"name": "teleport", "arguments": {}}]}, {"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert "no tool named `teleport`" in ollama.of("/api/chat")[1]["body"]["messages"][-1]["content"]


def test_endless_malformed_calls_without_an_escalation_target_stop_the_run(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {}}]}])
    ctx, run, emitted, tools = build(store, config, tmp_path)
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert e.value.reason == "malformed" and "hutch models bench" in e.value.detail


# ============================================================ SR-5: loop detector

def test_the_same_call_three_times_is_not_executed_a_third_time_and_a_persistent_loop_stops(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"tool_calls": [{"name": "list_files", "arguments": {"path": "."}}]}])
    ctx, run, emitted, tools = build(store, config, tmp_path)
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert e.value.reason == "loop"
    executed = [x for x in emitted if x.type is EventType.tool_result and x.data.get("ok") and x.data["tool"] == "list_files"]
    assert len(executed) == 2, "the 3rd and later identical calls must not run"
    assert len(kinds(emitted, "loop")) >= 2
    assert "NOT run again" in ollama.of("/api/chat")[3]["body"]["messages"][-1]["content"]


# ============================================================ SR-5: thinking off, per-turn cap

def test_thinking_is_sent_off_to_thinking_capable_models_and_the_turn_cap_is_configurable(store, config, tmp_path):
    srv = FakeOllama({"think:8b": {"caps": ["completion", "tools", "thinking"]}})
    try:
        srv.script = agent_script([{"content": "ok"}])
        ctx, run, emitted, tools = build(store, config, tmp_path, model="ollama/think:8b",
                                         limits=Limits(max_turn_tokens=777))
        run_it(runtime(provider_factory=factory(srv)), run, ctx, tools)
        body = srv.of("/api/chat")[0]["body"]
        assert body["think"] is False and body["options"]["num_predict"] == 777
    finally:
        srv.close()


# ============================================================ SR-8: fallback chain

def test_an_unreachable_primary_falls_back_in_order_and_says_so(store, config, tmp_path, oai):
    oai.script = lambda b: {"content": "from the fallback"}
    lm = oai
    ctx, run, emitted, tools = build(store, config, tmp_path, model="ollama/fake:8b", fallbacks=["lmstudio/some-model"])
    final = run_it(runtime(provider_factory=factory(ollama=None, lmstudio=lm)), run, ctx, tools)
    assert final == "from the fallback"
    fb = kinds(emitted, "fallback")[0]
    assert fb["from_model"] == "ollama/fake:8b" and fb["to_model"] == "lmstudio/some-model" and "ollama serve" in fb["reason"]
    assert run.model_used == "lmstudio/some-model"


def test_local_model_routes_never_fall_back_to_hosted_after_local_start_failure(store, config, tmp_path):
    calls = []

    def provider_factory(provider, base_url):
        calls.append(provider)
        if provider == "ollama":
            return OllamaProvider("http://127.0.0.1:9")
        raise AssertionError(f"hosted provider must not be constructed: {provider}")

    ctx, run, emitted, tools = build(store, config, tmp_path, model="ollama/not-installed:7b",
                                     fallbacks=["openai/gpt-4o-mini"], inference_mode="local")
    with pytest.raises(RunAborted, match="not an allowed local model route") as error:
        run_it(runtime(provider_factory=provider_factory), run, ctx, tools)
    assert error.value.reason == "provider_mode"
    assert calls == ["ollama"]
    assert kinds(emitted, "provider_route_blocked")


def test_local_model_routes_reject_cloud_tagged_ollama_fallback(store, config, tmp_path):
    calls = []

    def provider_factory(provider, base_url):
        calls.append(provider)
        return OllamaProvider("http://127.0.0.1:9")

    ctx, run, emitted, tools = build(store, config, tmp_path, model="ollama/not-installed:7b",
                                     fallbacks=["ollama/qwen3-coder:480b-cloud"], inference_mode="local")
    with pytest.raises(RunAborted, match="not an allowed local model route"):
        run_it(runtime(provider_factory=provider_factory), run, ctx, tools)
    assert calls == ["ollama"]
    assert kinds(emitted, "provider_route_blocked")


def test_ollama_cloud_route_with_currency_cap_requires_a_price(store, config, tmp_path):
    from hutch.providers.pricing import PriceBook
    from hutch.runtime.ladder import SpendGuard, make_rung

    ctx, run, emitted, tools = build(store, config, tmp_path, model="mock/demo",
                                     limits=Limits(max_cost_usd=1.0))
    guard = SpendGuard(ctx.store, ctx.bot, run, PriceBook(config.state_dir / "prices.json"))
    refusal = guard.refusal(make_rung("ollama/qwen3-coder:480b-cloud", "fallback"), 100, 100)
    assert refusal and "no price in prices.json" in refusal


def test_a_missing_model_falls_back_instead_of_failing_the_run(store, config, tmp_path, ollama, oai):
    oai.script = lambda b: {"content": "ok"}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="ollama/not-installed:7b", fallbacks=["lmstudio/m"])
    run_it(runtime(provider_factory=factory(ollama=ollama, lmstudio=oai)), run, ctx, tools)
    assert "ollama pull not-installed:7b" in kinds(emitted, "fallback")[0]["reason"]


def test_provider_field_rejection_is_not_retried_or_fallen_back(store, config, tmp_path):
    server = FakeOpenAI()
    server.force_status = (400, {"error": {"message": "Unknown field max_completion_tokens"}}, {})
    calls = []

    def provider_factory(provider, base_url):
        calls.append(provider)
        if provider == "openai":
            return OpenAICompatProvider(server.url + "/v1", "fixture-key", "openai")
        raise AssertionError(f"a rejected request must not trigger a fallback provider: {provider}")

    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o-mini",
                                         fallbacks=["ollama/fake:8b"], tools=())
        with pytest.raises(RunAborted, match="Unknown field max_completion_tokens") as error:
            run_it(runtime(provider_factory=provider_factory), run, ctx, tools)
        assert error.value.reason == "error"
        assert calls and set(calls) == {"openai"}
        assert len(server.of("/v1/chat/completions")) == 1
        assert not kinds(emitted, "fallback")
        assert [row["status"] for row in store.unresolved_usage_reservations()] == ["uncertain"]
    finally:
        server.close()


def test_when_the_whole_chain_is_down_the_error_names_the_last_cause(store, config, tmp_path):
    ctx, run, emitted, tools = build(store, config, tmp_path, model="ollama/fake:8b")
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory()), run, ctx, tools)
    assert e.value.reason == "error" and "ollama serve" in e.value.detail


def test_a_mid_run_outage_falls_back_without_restarting_the_run(store, config, tmp_path, ollama, oai):
    ollama.script = agent_script([{"tool_calls": [WRITE]}])
    oai.script = lambda b: {"content": "finished on the fallback"}
    ctx, run, emitted, tools = build(store, config, tmp_path, fallbacks=["lmstudio/m"])
    rt = runtime(provider_factory=factory(ollama=ollama, lmstudio=oai))
    orig = ollama.script

    def die_after_first(body):
        r = orig(body)
        if orig.calls >= 1 and "secret code word" not in body.get("_full_text", ""):
            ollama.force_status = (500, "boom")
        return r
    ollama.script = die_after_first
    ollama.script.calls = 0
    assert run_it(rt, run, ctx, tools) == "finished on the fallback"
    assert (ctx.workspace / "out.md").exists(), "the work done before the outage is kept"
    assert run.steps == 2


# ============================================================ LM-9 / LM-10: escalation, spend, ask first

def hosted_script(oai, text="rescued by the hosted model"):
    oai.script = lambda b: {"content": text, "prompt_tokens": 1000, "completion_tokens": 100}


def test_repeated_malformed_calls_escalate_one_rung_and_ask_first(store, config, tmp_path, ollama, oai):
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {}}]}])
    hosted_script(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, mode=ApprovalMode.ask,
                                     escalation=Escalation(to=["openai/gpt-4o"], after_malformed=2))
    rt = runtime(provider_factory=factory(ollama=ollama, oai=oai))

    def approver():
        for _ in range(400):
            pend = store.pending_approvals()
            if pend:
                assert pend[0].tool == "escalation" and "hosted model openai/gpt-4o" in pend[0].action
                assert pend[0].detail["what_is_sent"] and pend[0].sticky_key == "" and pend[0].outward
                resolve_approval(store, pend[0].id, approve=True, by="test", sticky=True)
                return
            time.sleep(0.02)
    t = threading.Thread(target=approver)
    t.start()
    final = run_it(rt, run, ctx, tools)
    t.join(timeout=5)
    assert final == "rescued by the hosted model"
    esc = kinds(emitted, "escalation")[0]
    assert esc["from_model"] == "ollama/fake:8b" and esc["to_model"] == "openai/gpt-4o" and esc["hosted"]
    assert "2 malformed" in esc["reason"]
    assert not store.is_sticky_allowed(ctx.bot.id, "escalate:hosted")     # another run requires its own authority
    assert run.cost_usd == pytest.approx((1000 * 2.5 + 100 * 10) / 1e6)     # priced from prices.json (LM-14)


def test_denying_the_first_hosted_call_keeps_the_run_local_and_it_then_fails_cleanly(store, config, tmp_path, ollama, oai):
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {}}]}])
    hosted_script(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, mode=ApprovalMode.ask,
                                     escalation=Escalation(to=["openai/gpt-4o"], after_malformed=2))

    def denier():
        for _ in range(400):
            pend = store.pending_approvals()
            if pend:
                resolve_approval(store, pend[0].id, approve=False, by="test")
                return
            time.sleep(0.02)
    t = threading.Thread(target=denier)
    t.start()
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(ollama=ollama, oai=oai)), run, ctx, tools)
    t.join(timeout=5)
    assert e.value.reason == "malformed" and not oai.of("/v1/chat/completions"), "nothing was sent to the hosted model"
    assert any(c.get("blocked") for c in kinds(emitted, "escalation"))


def test_auto_mode_bots_still_ask_before_their_first_hosted_call(store, config, tmp_path, ollama, oai):   # LM-10
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {}}]}])
    hosted_script(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, mode=ApprovalMode.auto,
                                     escalation=Escalation(to=["openai/gpt-4o"], after_malformed=2))

    def approver():
        for _ in range(400):
            if store.pending_approvals():
                resolve_approval(store, store.pending_approvals()[0].id, approve=True, by="test")
                return
            time.sleep(0.02)
    t = threading.Thread(target=approver)
    t.start()
    assert run_it(runtime(provider_factory=factory(ollama=ollama, oai=oai)), run, ctx, tools)
    t.join(timeout=5)
    assert kinds(emitted, "escalation")


def test_escalation_moves_exactly_one_rung_at_a_time(store, config, tmp_path, ollama, oai, monkeypatch, claude_srv=None):
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {}}]}])
    oai.script = lambda b: {"tool_calls": [{"name": "write_file", "arguments": {}}]}
    ctx, run, emitted, tools = build(store, config, tmp_path, mode=ApprovalMode.auto,
                                     escalation=Escalation(to=["openai/gpt-4o-mini", "openai/gpt-4o"], after_malformed=2))
    store.allow_sticky(ctx.bot.id, "escalate:hosted")
    # Approval behavior is covered separately; this test isolates one-rung model progression.
    monkeypatch.setattr(ctx.gate, "decide", lambda *a, **kw: None)
    with pytest.raises(RunAborted):
        run_it(runtime(provider_factory=factory(ollama=ollama, oai=oai)), run, ctx, tools)
    path = [(c["from_model"], c["to_model"]) for c in kinds(emitted, "escalation") if "from_model" in c]
    assert path == [("ollama/fake:8b", "openai/gpt-4o-mini"), ("openai/gpt-4o-mini", "openai/gpt-4o")]


def test_the_spend_cap_blocks_a_hosted_hop_before_the_call(store, config, tmp_path, ollama, oai):   # SR-2
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {}}]}])
    hosted_script(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, mode=ApprovalMode.auto,
                                     limits=Limits(max_cost_usd=0.00001),
                                     escalation=Escalation(to=["openai/gpt-4o"], after_malformed=2))
    store.allow_sticky(ctx.bot.id, "escalate:hosted")
    with pytest.raises(RunAborted):
        run_it(runtime(provider_factory=factory(ollama=ollama, oai=oai)), run, ctx, tools)
    blocked = [c for c in kinds(emitted, "escalation") if c.get("blocked")]
    assert blocked and "could cost up to" in blocked[0]["note"]
    assert not oai.of("/v1/chat/completions"), "the capped hop must never reach the provider"


def test_a_hosted_model_with_no_price_cannot_run_under_a_cost_cap(store, config, tmp_path, oai):
    hosted_script(oai)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-unpriced",
                                     limits=Limits(max_cost_usd=1.0))
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools)
    assert "no price" in e.value.detail and not oai.requests


def test_a_final_answer_already_paid_for_is_never_discarded_by_the_cap(store, config, tmp_path, oai):
    oai.script = lambda b: {"content": "the answer", "prompt_tokens": 1_000_000, "completion_tokens": 100_000}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o-mini",
                                     limits=Limits(max_cost_usd=100.0))
    assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "the answer"
    assert run.cost_usd == pytest.approx(0.15 + 0.06)


def test_daily_cost_cap_counts_every_run_of_the_bot(store, config, tmp_path, oai):
    oai.script = lambda b: {"content": "ok", "prompt_tokens": 1000, "completion_tokens": 100}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o",
                                     limits=Limits(daily_cost_cap_usd=0.001))
    prior = Run(bot_id=ctx.bot.id, prompt="earlier", cost_usd=0.0009)
    store.create_run(prior)
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools)
    assert e.value.reason == "cost_cap" and "daily cap" in e.value.detail


# ============================================================ context overflow

def test_a_truncated_prompt_aborts_loudly_instead_of_continuing_without_instructions(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "ok"}])
    ollama.truncate = True
    ctx, run, emitted, tools = build(store, config, tmp_path, num_ctx=4096)
    # the runtime reports the evaluated prompt pinned at the window, as real Ollama does after truncating
    orig = ollama.script
    ollama.script = lambda body: {**orig(body), "prompt_tokens": 4096}
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert e.value.reason == "context" and "truncated from the front" in e.value.detail


# ============================================================ Claude: cost, cache, PF-1

def test_hosted_claude_run_prices_cache_reads_and_reports_the_cached_share(store, config, tmp_path):
    srv = FakeAnthropic()
    try:
        srv.script = lambda b: {"content": "done", "input_tokens": 100, "cache_read": 9000, "cache_write": 0,
                                "output_tokens": 50}
        ctx, run, emitted, tools = build(store, config, tmp_path, model="anthropic/claude-opus-5-5")
        assert run_it(runtime(provider_factory=factory(claude=srv)), run, ctx, tools) == "done"
        assert run.cached_tokens == 9000 and run.prompt_tokens == 9100
        assert run.cost_usd == pytest.approx((100 * 4.0 + 9000 * 0.20 + 50 * 20.0) / 1e6)
        assert run.cached_tokens / run.prompt_tokens > 0.98                    # PF-1: the share shown per run
        assert srv.of("/v1/messages")[0]["body"]["cache_control"] == {"type": "ephemeral"}
        assert run.model_used == "anthropic/claude-opus-5-5"
    finally:
        srv.close()


# ============================================================ UI-2: stop aborts the model call

def test_stop_aborts_an_in_flight_model_call_promptly(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "ok"}])
    ollama.stall_once = 20.0
    ctx, run, emitted, tools = build(store, config, tmp_path)
    flag = {"stop": False}

    def stopper():
        time.sleep(0.6)
        flag["stop"] = True
        for hook in list(ctx.cancel_hooks):          # exactly what Engine.stop_run does
            hook()
    threading.Thread(target=stopper, daemon=True).start()
    t0 = time.time()
    with pytest.raises(RunAborted) as e:
        run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools, stop=lambda: flag["stop"])
    assert e.value.reason == "stopped" and time.time() - t0 < 5, "Stop must not wait for the model"


# ============================================================ PF-2: output truncation + artifact

def test_huge_tool_output_is_truncated_for_the_model_and_kept_as_an_artifact(store, config, tmp_path, ollama):
    big = tmp_path / "ws"
    big.mkdir(exist_ok=True)
    (big / "big.txt").write_text("line\n" * 20_000)
    ollama.script = agent_script([{"tool_calls": [{"name": "read_file", "arguments": {"path": "big.txt"}}]}, {"content": "ok"}])
    ctx, run, emitted, tools = build(store, config, tmp_path, tool_limits={"read_file": 1000})
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    tool_msg = ollama.of("/api/chat")[1]["body"]["messages"][-1]["content"]
    assert len(tool_msg) < 1300 and "full output saved as artifact" in tool_msg
    ev = next(e for e in emitted if e.type is EventType.tool_result)
    assert ev.data["chars"] == 100_000
    art = config.run_dir(ctx.bot.name, run.id) / ev.data["artifact"]
    saved = art.read_bytes()
    assert art.stat().st_mode & 0o222 == 0
    assert saved.decode() == "line\n" * 20_000
    assert ev.data["artifact_bytes"] == len(saved)
    assert ev.data["artifact_sha256"] == hashlib.sha256(saved).hexdigest()


def test_successful_write_file_is_snapshotted_for_a_verified_download(store, config, tmp_path, ollama):
    content = "name,total\nInvoice,42\n"
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {
        "path": "reports/monthly.csv", "content": content}}]}, {"content": "created the report"}])
    ctx, run, emitted, tools = build(store, config, tmp_path)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert (ctx.workspace / "reports/monthly.csv").read_text(encoding="utf-8") == content
    event = next(e for e in emitted if e.type is EventType.tool_result)
    file_artifact = event.data["workspace_file"]
    assert file_artifact["name"] == "monthly.csv"
    assert file_artifact["path"] == "reports/monthly.csv"
    snapshot = config.run_dir(ctx.bot.name, run.id) / file_artifact["artifact"]
    saved = snapshot.read_bytes()
    assert saved == content.encode("utf-8") and snapshot.stat().st_mode & 0o222 == 0
    assert file_artifact["bytes"] == len(saved)
    assert file_artifact["sha256"] == hashlib.sha256(saved).hexdigest()


def test_write_file_snapshot_failure_does_not_change_success(store, config, tmp_path, ollama, monkeypatch):
    content = "saved safely in the workspace"
    ollama.script = agent_script([{"tool_calls": [{"name": "write_file", "arguments": {
        "path": "report.txt", "content": content}}]}, {"content": "saved in the workspace"}])
    import hutch.runtime.steps as steps
    def fail_snapshot(ctx, path, content):
        raise ValueError("the file exceeds the 4 MB downloadable snapshot limit")
    monkeypatch.setattr(steps, "snapshot_workspace_file", fail_snapshot)
    ctx, run, emitted, tools = build(store, config, tmp_path)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert (ctx.workspace / "report.txt").read_text(encoding="utf-8") == content
    event = next(e for e in emitted if e.type is EventType.tool_result)
    assert event.data["ok"] is True
    assert "4 MB downloadable snapshot limit" in event.data["workspace_file"]["error"]


def test_rehearsed_write_does_not_attach_an_existing_file(store, config, tmp_path):
    from hutch.runtime.steps import call_tool
    ctx, run, emitted, tools = build(store, config, tmp_path)
    existing = ctx.workspace / "report.txt"
    existing.write_text("previous file", encoding="utf-8")
    ctx.dry_run = True
    call_tool(run, ctx, tools, "write_file", {"path": "report.txt", "content": "proposed file"})
    event = next(e for e in emitted if e.type is EventType.tool_result)
    assert event.data["ok"] is True and event.data["simulated"] is True
    assert "workspace_file" not in event.data
    assert existing.read_text(encoding="utf-8") == "previous file"


def test_workspace_file_snapshot_enforces_its_size_bound(store, config, tmp_path):
    from hutch.runtime.steps import snapshot_workspace_file
    ctx, run, emitted, tools = build(store, config, tmp_path)
    oversized = "x" * 4_000_001
    with pytest.raises(ValueError, match="4 MB downloadable snapshot limit"):
        snapshot_workspace_file(ctx, "too-large.txt", oversized)


def test_run_artifact_storage_has_a_total_bound(store, config, tmp_path):
    from hutch.runtime.steps import MAX_RUN_ARTIFACT_BYTES, save_artifact
    ctx, run, emitted, tools = build(store, config, tmp_path)
    artifact_dir = config.run_dir(ctx.bot.name, run.id) / "artifacts"
    artifact_dir.mkdir(parents=True)
    reserved = artifact_dir / "reserved.txt"
    with reserved.open("wb") as stream:
        stream.truncate(MAX_RUN_ARTIFACT_BYTES)
    with pytest.raises(ValueError, match="16 MB storage limit"):
        save_artifact(ctx, "read_file", "another artifact")


# ============================================================ SR-9 surfaced in the transcript

def test_a_stream_retry_is_visible_in_the_transcript(store, config, tmp_path, ollama):
    ollama.script = agent_script([{"content": "ok"}])
    ollama.fail_stream_once = True
    ctx, run, emitted, tools = build(store, config, tmp_path)
    run_it(runtime(provider_factory=factory(ollama)), run, ctx, tools)
    assert kinds(emitted, "stream_retry") and "without streaming" in kinds(emitted, "stream_retry")[0]["note"]
