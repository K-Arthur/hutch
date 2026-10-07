"""Model slots (LM-6): batching by loaded model, gating by free slots, fairness, and measured swap cost."""

from __future__ import annotations

from datetime import timedelta

import pytest

from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, Run, RunStatus, iso, utcnow
from hutch.providers.ollama import OllamaProvider
from hutch.slots import FAIRNESS_SECONDS, ModelSlots, default_capacity, measure_swap, record_swap, recorded_swaps
from tests.fakes import FakeOllama


def mk(store, name, model):
    return store.create_bot(Bot(name=name, model=model, approval_mode=ApprovalMode.auto))


def pend(store, bot, age=0):
    r = Run(bot_id=bot.id, prompt="x", created_at=iso(utcnow() - timedelta(seconds=age)))
    return store.create_run(r)


def running(store, bot):
    return store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))


def test_capacity_follows_memory_tier_and_can_be_overridden(store, monkeypatch):
    assert default_capacity("small") == 1 and default_capacity("xl") == 2
    assert ModelSlots(store, tier="large").capacity == 2
    monkeypatch.setenv("HUTCH_MODEL_SLOTS", "3")
    assert ModelSlots(store, tier="tiny").capacity == 3


def test_runs_sharing_the_busy_model_start_but_a_different_model_waits(store):
    a, b, c = mk(store, "a", "ollama/llama"), mk(store, "b", "ollama/llama"), mk(store, "c", "ollama/qwen")
    active = [running(store, a)]
    p_b, p_c = pend(store, b), pend(store, c)
    slots = ModelSlots(store, capacity=1, loaded=lambda: {"ollama/llama"})
    allowed = slots.filter([p_c, p_b], active)
    assert [r.id for r in allowed] == [p_b.id], "only the run that shares the loaded model may start"
    assert "waiting for a model slot" in slots.last_blocked[p_c.id] and "ollama/llama" in slots.last_blocked[p_c.id]
    w = slots.reason(p_c)
    assert "HUTCH_MODEL_SLOTS" in w.fix and w.href == "/models"


def test_with_a_free_slot_a_second_model_may_load(store):
    a, c = mk(store, "a", "ollama/llama"), mk(store, "c", "ollama/qwen")
    slots = ModelSlots(store, capacity=2, loaded=lambda: set())
    assert [r.id for r in slots.filter([pend(store, c)], [running(store, a)])] != []


def test_queued_runs_are_batched_by_the_already_loaded_model(store):
    """Alternating A, B, A, B would swap on every run; the loaded model's runs go first."""
    a, b = mk(store, "a", "ollama/llama"), mk(store, "b", "ollama/qwen")
    runs = [pend(store, a if i % 2 == 0 else b, age=100 - i) for i in range(6)]       # a,b,a,b,a,b in arrival order
    slots = ModelSlots(store, capacity=1, loaded=lambda: {"ollama/qwen"})
    order = [store.get_bot(r.bot_id).name for r in slots.filter(runs, [])]
    assert order[0] == "b" and order[:3] == ["b", "b", "b"], order
    assert len(order) == 3 and set(order) == {"b"}, "with one slot, only the loaded model's runs dispatch now"


def test_a_starving_run_jumps_the_queue(store):
    a, b = mk(store, "a", "ollama/llama"), mk(store, "b", "ollama/qwen")
    old = pend(store, a, age=FAIRNESS_SECONDS + 60)
    fresh = pend(store, b, age=1)
    slots = ModelSlots(store, capacity=1, loaded=lambda: {"ollama/qwen"})
    assert slots.filter([fresh, old], [])[0].id == old.id


def test_hosted_and_mock_runs_are_never_constrained_and_cause_no_http(store):
    calls = []
    slots = ModelSlots(store, capacity=1, loaded=lambda: calls.append(1) or set())
    hosted, mock = mk(store, "h", "anthropic/claude-opus-5-5"), mk(store, "m", "mock/demo")
    runs = [pend(store, hosted), pend(store, mock)]
    assert len(slots.filter(runs, [running(store, mk(store, "z", "ollama/x"))])) == 2
    assert not calls, "the runtime must not be queried when no local model is queued"


def test_the_engine_installs_the_scheduler_and_explains_a_slot_wait(store, config, monkeypatch):
    monkeypatch.setenv("HUTCH_MODEL_SLOTS", "1")
    engine = Engine(config, store)
    assert engine.slot_filter == engine.slots.filter and engine.slot_reason == engine.slots.reason
    engine.slots._loaded_fn = lambda: set()
    a, c = mk(store, "a", "ollama/llama"), mk(store, "c", "ollama/qwen")
    running(store, a)
    waiting = pend(store, c)
    assert engine.dispatch_pending() == 0, "a second local model must not start while the only slot is taken"
    from hutch.views import explain_run
    w = explain_run(store, waiting, engine, c)
    assert "waiting for a model slot" in w.cause.lower()


# ----------------------------------------------------------------- swap latency

@pytest.fixture()
def two_models():
    s = FakeOllama({"model-a:8b": {}, "model-b:8b": {}}, max_loaded=1, load_delay=0.15)
    yield s
    s.close()


def test_swap_latency_is_measured_for_a_pair_and_recorded(two_models, store):
    rep = measure_swap(OllamaProvider(two_models.url), "model-a:8b", "model-b:8b")
    assert rep.evicted, "with one slot, loading B must evict A"
    assert rep.cold_a_ms >= 120 and rep.swap_a_to_b_ms >= 120 and rep.swap_b_to_a_ms >= 120
    assert "->" in rep.summary and "cold load" in rep.summary
    record_swap(store, rep)
    got = recorded_swaps(store)
    assert got and got[0]["a"] == "model-a:8b" and got[0]["swap_a_to_b_ms"] == pytest.approx(rep.swap_a_to_b_ms)
    assert not [r for r in two_models.of("/api/chat")], "measuring must not generate tokens"


def test_two_pairs_are_measured_independently_and_a_roomy_runtime_reports_no_swap(store):
    s = FakeOllama({"a:1b": {}, "b:1b": {}, "c:1b": {}}, max_loaded=2, load_delay=0.05)
    try:
        p = OllamaProvider(s.url)
        r1, r2 = measure_swap(p, "a:1b", "b:1b"), measure_swap(p, "b:1b", "c:1b")
        assert not r1.evicted and "no swap cost" in r1.summary           # both fit: nothing was unloaded
        record_swap(store, r1)
        record_swap(store, r2)
        assert {(x["a"], x["b"]) for x in recorded_swaps(store)} == {("a:1b", "b:1b"), ("b:1b", "c:1b")}
    finally:
        s.close()
