"""Local model choices must cover every runtime, not only Ollama (G3)."""

from __future__ import annotations

from dataclasses import asdict

from hutch.hardware import Hardware, RuntimeInfo
from hutch.localchoices import local_choices
from hutch.providers.base import ModelMeta


class Bot:
    num_ctx = 32768


def _hw(*names: str, ram: float = 64.0) -> Hardware:
    return Hardware(ram_total_gb=ram, ram_available_gb=ram * 0.8,
                    runtimes=[RuntimeInfo(name=name, reachable=True) for name in names])


def _row(provider: str, model: ModelMeta, *, applied: int | None, parallel: int | None = None,
         state: str = "ready") -> dict:
    return {"provider": provider, "title": provider, "runtime": provider,
            "url": f"http://127.0.0.1:9/{provider}",
            "reachable": True, "models": [model.name], "model_meta": [asdict(model)],
            "state": state, "applied_context": {model.name: applied} if applied else {},
            "parallel": parallel, "policy_detail": "", "error": ""}


def _no_ollama(monkeypatch):
    monkeypatch.setattr("hutch.localchoices._runtime_rows", lambda state_dir=None: [])


def test_llamacpp_models_are_first_class_choices_with_the_per_slot_window(monkeypatch):
    _no_ollama(monkeypatch)
    meta = ModelMeta(name="qwen3-4b", size_bytes=2 * 1024 ** 3, max_context=262144,
                     capabilities=["tools"])
    monkeypatch.setattr("hutch.localchoices._runtime_rows",
                        lambda state_dir=None: [_row("llamacpp", meta, applied=4096, parallel=2)])
    choices = local_choices(Bot(), _hw("llama.cpp"), provider=None)
    assert len(choices) == 1
    choice = choices[0]
    assert choice.spec == "llamacpp/qwen3-4b"
    assert choice.group == "On this machine"
    assert choice.state == "ready"
    assert "loaded at 4k tokens per request" in choice.note
    assert "2 slots" in choice.note
    assert any("endpoint" in line for line in choice.detail)


def test_lmstudio_uses_the_applied_window_not_the_trained_maximum(monkeypatch):
    _no_ollama(monkeypatch)
    meta = ModelMeta(name="qwen3-4b", size_bytes=2.4 * 1024 ** 3, max_context=262144)
    monkeypatch.setattr("hutch.localchoices._runtime_rows",
                        lambda state_dir=None: [_row("lmstudio", meta, applied=8192, parallel=4)])
    choice = local_choices(Bot(), _hw("lmstudio"), provider=None)[0]
    assert "8k tokens" in choice.note
    assert "262144" not in choice.note
    assert "across 4 slots" not in choice.note
    assert "parallel 4" in choice.note
    assert choice.spec == "lmstudio/qwen3-4b"


def test_a_model_that_cannot_fit_is_not_ready(monkeypatch):
    _no_ollama(monkeypatch)
    meta = ModelMeta(name="big", size_bytes=8 * 1024 ** 3, max_context=32768)
    monkeypatch.setattr("hutch.localchoices._runtime_rows", lambda state_dir=None: [_row("llamacpp", meta, applied=None)])
    choice = local_choices(Bot(), _hw("llama.cpp", ram=4.0), provider=None)[0]
    assert choice.state == "wont_fit"
    assert choice.fix


def test_an_embedding_model_is_not_offered_as_a_chat_route(monkeypatch):
    _no_ollama(monkeypatch)
    meta = ModelMeta(name="embed", size_bytes=100 * 1024 ** 2, capabilities=["embedding"])
    monkeypatch.setattr("hutch.localchoices._runtime_rows", lambda state_dir=None: [_row("lmstudio", meta, applied=None)])
    assert local_choices(Bot(), _hw("lmstudio"), provider=None) == []


def test_a_key_protected_runtime_adds_no_choice(monkeypatch):
    _no_ollama(monkeypatch)
    meta = ModelMeta(name="qwen3-4b", size_bytes=2 * 1024 ** 3)
    row = _row("lmstudio", meta, applied=None, state="needs_key")
    row["fix"] = "store a key"
    monkeypatch.setattr("hutch.localchoices._runtime_rows", lambda hw: [row])
    assert local_choices(Bot(), _hw("lmstudio"), provider=None) == []


def test_an_ollama_cloud_row_stays_hosted(monkeypatch):
    class Provider:
        def list_models(self):
            return []

    monkeypatch.setattr("hutch.localchoices._runtime_rows", lambda state_dir=None: [])
    monkeypatch.setattr("hutch.modelchoices._cached", lambda key, fn, ttl=5.0: fn())
    monkeypatch.setattr("hutch.modelview.installed",
                        lambda provider: {"gpt-oss:20b-cloud": ModelMeta(name="gpt-oss:20b-cloud")})
    choices = local_choices(Bot(), _hw("ollama"), provider=Provider())
    assert len(choices) == 1
    assert choices[0].group == "Hosted"
    assert choices[0].hosted is True
    assert "ollama.com" in choices[0].note
