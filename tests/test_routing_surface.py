"""Routing surface: fallbacks/escalation/compaction round-trip, refusal policy, served identity (SR-8/LM-9)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.models import ApprovalMode, Bot, Escalation
from hutch.providers import ProviderError
from hutch.runtime import RunAborted
from hutch.runtime.ladder import Ladder, make_rung
from hutch.server.app import create_app

from tests.test_runtime_budget_gate import _running
from tests.test_runtime_builtin import build, factory, kinds, run_it, runtime


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as c:
        c.store = c.app.state.store
        c.config = c.app.state.config
        yield c


def test_routing_fields_round_trip_through_the_bot_api(client):
    bot = client.store.create_bot(Bot(name="routing-bot", model="mock/demo"))
    patched = client.patch(f"/api/bots/{bot.id}", json={
        "fallbacks": ["anthropic/claude-haiku-4-5", "ollama/fake:8b"],
        "escalation": {"to": ["anthropic/claude-opus-5-5"], "on_context_overflow": True},
        "compaction": "off",
    })
    assert patched.status_code == 200, patched.text
    detail = client.get(f"/api/bots/{bot.id}").json()
    assert detail["fallbacks"] == ["anthropic/claude-haiku-4-5", "ollama/fake:8b"]
    assert detail["escalation"]["to"] == ["anthropic/claude-opus-5-5"]
    assert detail["compaction"] == "off"

    cleared = client.patch(f"/api/bots/{bot.id}", json={"fallbacks": []})
    assert cleared.status_code == 200
    assert client.get(f"/api/bots/{bot.id}").json()["fallbacks"] == []

    invalid = client.patch(f"/api/bots/{bot.id}", json={"fallbacks": ["not a model spec"]})
    assert invalid.status_code == 422
    invalid_escalation = client.patch(f"/api/bots/{bot.id}", json={"escalation": {"to": [""]}})
    assert invalid_escalation.status_code == 422


def test_runtime_never_falls_back_around_a_provider_refusal(store):
    """A refusal is an answer, not availability: even with fallbacks configured, none is tried."""
    bot = store.create_bot(Bot(name="refusal-bot", model="mock/demo",
                               fallbacks=["ollama/fake:8b", "anthropic/claude-haiku-4-5"]))
    ladder = Ladder(bot)
    fallback = ladder.next_fallback()
    assert fallback is not None and fallback.spec == "ollama/fake:8b"  # control: a fallback exists

    instance = runtime()
    refusal = ProviderError("refused", "the provider declined this request", provider="mock")
    refusal.category = "provider_refusal"  # type: ignore[attr-defined]
    import types
    assert instance._recover(types.SimpleNamespace(bot=bot), None, ladder, None, refusal, [], [], 100) is None
    assert ladder.current.spec == bot.model, "the ladder never moved to a fallback rung"


def test_the_served_model_is_reported_when_it_differs_from_the_request(store, config, tmp_path):
    from tests.fakes import FakeOpenAI
    oai = FakeOpenAI()
    oai.script = lambda body: {"content": "served", "model": "vendor/actually-served",
                               "prompt_tokens": 10, "completion_tokens": 5}
    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="openai/gpt-4o",
                                         mode=ApprovalMode.auto)
        run = _running(store, ctx, run)
        assert run_it(runtime(provider_factory=factory(oai=oai)), run, ctx, tools) == "served"
    finally:
        oai.close()
    provider_logs = kinds(emitted, "provider")
    assert provider_logs and provider_logs[0]["served"] == "vendor/actually-served"


def test_a_safety_refusal_ends_the_run_without_trying_the_fallback(store, config, tmp_path):
    from tests.fakes import FakeAnthropic, FakeOpenAI
    claude = FakeAnthropic()
    claude.script = lambda body: {"refusal": "cyber"}
    oai = FakeOpenAI()
    oai.script = lambda body: {"content": "should never be asked"}
    try:
        ctx, run, emitted, tools = build(store, config, tmp_path, model="anthropic/claude-haiku-4-5",
                                         mode=ApprovalMode.auto, fallbacks=["openai/gpt-4o"])
        run = _running(store, ctx, run)
        with pytest.raises(RunAborted) as failure:
            run_it(runtime(provider_factory=factory(claude=claude, oai=oai)), run, ctx, tools)
        assert failure.value.reason == "refused"
    finally:
        claude.close()
        oai.close()
    assert not oai.of("/v1/chat/completions"), "a safety refusal must not be routed around to another provider"
