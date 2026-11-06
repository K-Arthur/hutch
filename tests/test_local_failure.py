"""Local failures map to one recovery action and a sentence a person can act on."""

from __future__ import annotations

import types

import pytest

from hutch.hardware import Hardware
from hutch.providers.base import ModelMeta, ProviderError
from hutch.providers.local import lifecycle
from hutch.providers.local.base import Loaded, READY, RuntimeState
from hutch.runtime.outcomes import classify_local_failure, exit_reason

HARDWARE = Hardware(ram_total_gb=64, ram_available_gb=48)


def _state(*, reachable=True, state=READY, models=("m",), loaded=("m",)):
    result = RuntimeState("llamacpp", reachable=reachable, state=state)
    result.models = [ModelMeta(name=name) for name in models]
    result.loaded = {name: Loaded(model=name, applied_context=4096) for name in loaded}
    return result


def test_an_oom_kill_is_reloaded_once_then_stopped():
    exc = ProviderError("server", "Ollama error mid-stream: llama runner process has terminated: signal: killed")
    first = classify_local_failure(exc, "ollama")
    assert first.kind == "oom"
    assert first.action == "reload"
    assert "out of memory" in first.message
    kept = classify_local_failure(exc, "ollama", partial=True)
    assert kept.action == "stop"
    assert "kept and marked incomplete" in kept.message


def test_a_restart_or_broken_stream_is_reloaded_once_when_nothing_was_delivered():
    exc = ProviderError("stream", "the response stream broke: connection reset")
    failure = classify_local_failure(exc, "llamacpp")
    assert failure.action == "reload"
    assert "reloads the model once" in failure.message
    assert classify_local_failure(exc, "llamacpp", partial=True).action == "stop"


def test_the_real_killed_runner_wrapper_is_recognised():
    exc = ProviderError(
        "server", "Ollama error mid-stream: an error was encountered while running the model: unexpected EOF")
    failure = classify_local_failure(exc, "ollama")
    assert failure.action == "reload"
    assert failure.kind == "server"
    stopped = classify_local_failure(exc, "ollama", partial=True)
    assert stopped.action == "stop"
    assert "kept and marked incomplete" in stopped.message


def test_a_loading_503_is_not_a_fallback():
    exc = ProviderError("server", 'llama.cpp returned HTTP 503: {"message":"Loading model"}')
    failure = classify_local_failure(exc, "llamacpp")
    assert failure.action == "reload"
    assert "still loading" in failure.message


@pytest.mark.parametrize("provider", ["anthropic", "openai", "openrouter"])
def test_hosted_failures_keep_the_existing_recovery(provider):
    failure = classify_local_failure(ProviderError("server", "signal: killed"), provider)
    assert failure.action == "stop"
    assert failure.message == ""


def test_context_and_auth_still_stop_without_a_new_message():
    for kind in ("context", "auth", "refused"):
        failure = classify_local_failure(ProviderError(kind, "detail"), "ollama")
        assert failure.action == "stop"
        assert failure.message == ""


def test_exit_reason_is_unchanged_for_the_run_ledger():
    assert exit_reason(ProviderError("context", "x")) == "context"
    assert exit_reason(ProviderError("refused", "x")) == "refused"
    assert exit_reason(ProviderError("oom", "x")) == "error"


class _Ollama:
    def __init__(self, loaded: bool):
        self.loaded = loaded
        self.preloads: list[tuple[str, str]] = []

    def is_loaded(self, model):
        return self.loaded

    def preload(self, model, keep_alive):
        self.preloads.append((model, keep_alive))
        return 1557.0


def test_ensure_loaded_measures_an_ollama_cold_load():
    provider = _Ollama(loaded=False)
    phases: list[bool] = []
    observed = lifecycle.ensure_loaded("ollama", provider=provider, model="qwen3:4b",
                                       num_ctx=4096, on_loading=phases.append)
    assert observed.blocked is False
    assert observed.waited_ms == 1557.0
    assert "cold load" in observed.detail
    assert provider.preloads == [("qwen3:4b", "10m")]
    assert phases == [True, False]


def test_ensure_loaded_does_not_reload_a_resident_ollama_model():
    provider = _Ollama(loaded=True)
    observed = lifecycle.ensure_loaded("ollama", provider=provider, model="qwen3:4b", num_ctx=4096)
    assert observed.detail == "qwen3:4b is already loaded"
    assert provider.preloads == []


def test_refresh_refuses_an_ollama_model_that_was_removed():
    provider = _Ollama(loaded=False)
    provider.show = lambda model: None
    with pytest.raises(ProviderError, match="no longer installed"):
        lifecycle.refresh_local_route("ollama", provider, "gone", 4096, HARDWARE)


def test_refresh_lets_a_route_that_cannot_be_read_answer_for_itself(monkeypatch):
    adapter = types.SimpleNamespace(state=lambda: _state(reachable=False, state="unreachable", models=(), loaded=()))
    monkeypatch.setattr("hutch.providers.local.adapter_for", lambda *a, **k: adapter)
    monkeypatch.setattr(lifecycle, "load_fixed_runtime",
                        lambda *a, **k: pytest.fail("an unreadable route must not be loaded blindly"))
    lifecycle.refresh_local_route("llamacpp", types.SimpleNamespace(base_url="http://h"), "m",
                                  4096, HARDWARE)


def test_refresh_leaves_hosted_routes_alone(monkeypatch):
    monkeypatch.setattr("hutch.providers.local.adapter_for",
                        lambda *a, **k: pytest.fail("a hosted route must not be introspected"))
    lifecycle.refresh_local_route("openai", types.SimpleNamespace(base_url="https://api.openai.com/v1"),
                                  "gpt-4o", 4096, HARDWARE)


def test_refresh_reloads_a_fixed_route_whose_model_was_evicted(monkeypatch):
    adapter = types.SimpleNamespace(state=lambda: _state(models=("m",), loaded=()))
    monkeypatch.setattr("hutch.providers.local.adapter_for", lambda *a, **k: adapter)
    calls: list[dict] = []

    def fake_load(provider_id, base_url, model, context_length, credential="", **kwargs):
        calls.append({"provider_id": provider_id, "model": model, "context_length": context_length})
        return lifecycle.LoadObservation(READY, READY, 840.0, "loaded m in 0.8s (cold load)")

    monkeypatch.setattr(lifecycle, "load_fixed_runtime", fake_load)
    logged: list[tuple] = []
    lifecycle.refresh_local_route("llamacpp", types.SimpleNamespace(base_url="http://h"), "m", 4096,
                                  HARDWARE, log=lambda kind, message, **kw: logged.append((kind, message, kw)))
    assert calls == [{"provider_id": "llamacpp", "model": "m", "context_length": 4096}]
    assert logged and logged[0][0] == "load" and logged[0][2]["load_ms"] == 840.0


def test_refresh_leaves_a_loaded_fixed_route_alone(monkeypatch):
    adapter = types.SimpleNamespace(state=lambda: _state())
    monkeypatch.setattr("hutch.providers.local.adapter_for", lambda *a, **k: adapter)
    monkeypatch.setattr(lifecycle, "load_fixed_runtime",
                        lambda *a, **k: pytest.fail("a loaded route must not be loaded again"))
    lifecycle.refresh_local_route("llamacpp", types.SimpleNamespace(base_url="http://h"), "m", 4096, HARDWARE)


def test_lmstudio_will_not_load_without_a_fitted_window(monkeypatch):
    adapter = types.SimpleNamespace(state=lambda: _state(models=("m",), loaded=()))
    monkeypatch.setattr("hutch.providers.local.adapter_for", lambda *a, **k: adapter)
    observed = lifecycle.ensure_loaded("lmstudio", base_url="http://h", model="m", num_ctx=0)
    assert observed.blocked is False
    assert "will not pre-load" in observed.detail
