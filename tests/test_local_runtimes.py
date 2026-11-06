"""Adapter and admission tests for local runtimes (no live server required)."""

from __future__ import annotations

import json

from hutch.context import plan_context
from hutch.hardware import Hardware
from hutch.providers.base import Health, ModelMeta
from hutch.providers.local import HttpResult, ProbeError
from hutch.providers.local.admission import admit_local
from hutch.providers.local.llamacpp import LlamaCppRuntime
from hutch.providers.local.lmstudio import LMStudioRuntime
from hutch.providers.local.openai_generic import OpenAIGenericRuntime

LLAMA_MODELS = {"data": [{"id": "qwen3-4b", "owned_by": "llamacpp",
                          "architecture": {"input_modalities": ["text"]},
                          "meta": {"n_ctx": 8192, "n_ctx_train": 262144, "n_params": 4022468096,
                                   "size": 2491323904, "ftype": "Q4_K - Medium"}}]}
LLAMA_PROPS = {"build_info": "b12144-69ee2ecc0", "total_slots": 2,
               "model_path": "models/qwen3-4b.gguf", "default_generation_settings": {"n_ctx": 8192},
               "chat_template_caps": {"supports_tools": True},
               "modalities": {"vision": False, "audio": False}}
LMSTUDIO = {"models": [{"type": "llm", "key": "qwen3-4b", "architecture": "qwen3",
                        "quantization": {"name": "Q4_K_M"}, "size_bytes": 2497280480,
                        "params_string": "4B", "max_context_length": 262144,
                        "capabilities": {"vision": False, "trained_for_tool_use": True},
                        "loaded_instances": [{"id": "qwen3-4b",
                                              "config": {"context_length": 8192, "parallel": 4}}]}]}


def _json(payload: dict, status: int = 200) -> HttpResult:
    return HttpResult(status, json.dumps(payload).encode())


class Fake:
    def __init__(self, routes: dict[str, HttpResult | Exception], post: dict[str, HttpResult] | None = None):
        self.routes = routes
        self.post_routes = post or {}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url: str, timeout: float, bearer: str = "") -> HttpResult:
        self.calls.append((url, bearer))
        answer = self.routes.get(url)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise ProbeError("unreachable", "no service answered")
        return answer

    def post(self, url: str, payload: dict, timeout: float, bearer: str = "") -> HttpResult:
        answer = self.post_routes.get(url)
        if answer is None:
            raise ProbeError("unreachable", "no service answered")
        return answer


def test_llamacpp_reads_the_per_slot_window_not_the_headline_context():
    fake = Fake({
        "http://h/props": _json(LLAMA_PROPS),
        "http://h/health": _json({}),
        "http://h/v1/models": _json(LLAMA_MODELS),
        "http://h/slots": _json([{"id": 0, "n_ctx": 4096}, {"id": 1, "n_ctx": 4096}]),
    })
    runtime = LlamaCppRuntime("http://h/v1", http=fake)
    state = runtime.state()
    assert state.state == "ready"
    assert state.identity.runtime == "llamacpp"
    assert state.identity.version == "b12144-69ee2ecc0"
    assert state.loaded["qwen3-4b"].applied_context == 4096
    assert state.loaded["qwen3-4b"].parallel == 2
    assert state.models[0].max_context == 262144
    assert state.models[0].applied_context == 4096
    assert "tools" in state.models[0].capabilities


def test_llamacpp_turns_an_absolute_model_path_into_a_usable_id():
    models = {"data": [{"id": "/models/qwen3-4b.gguf", "owned_by": "llamacpp"}]}
    fake = Fake({
        "http://h/props": _json({**LLAMA_PROPS, "model_path": "/models/qwen3-4b.gguf"}),
        "http://h/health": _json({}),
        "http://h/v1/models": _json(models),
        "http://h/slots": _json([{"id": 0, "n_ctx": 4096}]),
    })
    state = LlamaCppRuntime("http://h", http=fake).state()
    assert state.models[0].name == "qwen3-4b"
    assert "qwen3-4b" in state.loaded


def test_llamacpp_falls_back_to_props_when_slots_are_disabled():
    fake = Fake({
        "http://h/props": _json(LLAMA_PROPS),
        "http://h/health": _json({}),
        "http://h/v1/models": _json(LLAMA_MODELS),
        "http://h/slots": HttpResult(404, b""),
    })
    state = LlamaCppRuntime("http://h", http=fake).state()
    assert state.loaded["qwen3-4b"].applied_context == 8192
    assert state.loaded["qwen3-4b"].parallel == 2


def test_llamacpp_loading_is_a_state_not_an_error():
    fake = Fake({
        "http://h/health": HttpResult(503, b'{"error":{"message":"Loading model"}}'),
        "http://h/props": _json(LLAMA_PROPS),
        "http://h/v1/models": _json(LLAMA_MODELS),
        "http://h/slots": _json([{"id": 0, "n_ctx": 8192}]),
    })
    state = LlamaCppRuntime("http://h", http=fake).state()
    assert state.state == "loading"
    assert "loading" in state.detail.lower()


def test_llamacpp_401_is_needs_key():
    fake = Fake({"http://h/health": _json({}), "http://h/props": HttpResult(401, b""),
                 "http://h/v1/models": HttpResult(401, b"")})
    state = LlamaCppRuntime("http://h", http=fake).state()
    assert state.state == "needs_key"
    assert "API key" in state.detail


def test_lmstudio_reports_the_applied_window_not_the_trained_maximum():
    fake = Fake({"http://h/api/v1/models": _json(LMSTUDIO)})
    state = LMStudioRuntime("http://h/v1", http=fake, post=Fake({}).post).state()
    assert state.state == "ready"
    assert state.identity.runtime == "lmstudio"
    assert state.models[0].max_context == 262144
    assert state.models[0].applied_context == 8192
    assert state.loaded["qwen3-4b"].applied_context == 8192
    assert state.loaded["qwen3-4b"].parallel == 4
    assert state.models[0].capabilities == ["tools"]


def test_lmstudio_load_echoes_the_applied_window():
    post = Fake({}, post={"http://h/api/v1/models/load": _json(
        {"type": "llm", "status": "loaded", "load_config": {"context_length": 4096}})})
    runtime = LMStudioRuntime("http://h", http=Fake({}), post=post.post)
    assert runtime.load("qwen3-4b", 4096) == 4096


def test_openai_generic_names_vllm_only_from_the_response():
    fake = Fake({"http://h/v1/models": _json({"data": [{"id": "m", "owned_by": "vllm"}]})})
    state = OpenAIGenericRuntime("vllm", "http://h", http=fake).state()
    assert state.identity.runtime == "vllm"
    assert state.identity.confidence == "strong"
    assert state.models[0].max_context is None
    assert state.policy == "unknown"


def test_openai_generic_does_not_name_a_decoy():
    fake = Fake({"http://h/v1/models": _json({"data": [{"id": "m", "owned_by": "somebody"}]})})
    state = OpenAIGenericRuntime("vllm", "http://h", http=fake).state()
    assert state.identity.runtime == "unknown"
    assert state.identity.confidence == "weak"
    assert state.models[0].name == "m"


def test_plan_context_keeps_a_measured_window_over_the_wanted_one():
    hw = Hardware(ram_total_gb=64, ram_available_gb=48)
    plan = plan_context(None, hw, 32768, 4096, local=True, applied=8192, slots=2, policy="unknown")
    assert plan.num_ctx == 8192
    assert plan.applied == 8192
    assert plan.blocked is False
    assert "8,192 tokens applied" in plan.note
    assert "wanted 32,768" in plan.note


def test_admission_uses_the_llamacpp_slot_window(monkeypatch):
    state = LlamaCppRuntime("http://h", http=Fake({
        "http://h/props": _json(LLAMA_PROPS),
        "http://h/health": _json({}),
        "http://h/v1/models": _json(LLAMA_MODELS),
        "http://h/slots": _json([{"id": 0, "n_ctx": 4096}, {"id": 1, "n_ctx": 4096}]),
    })).state()
    monkeypatch.setattr("hutch.providers.local.admission.adapter_for", lambda *a, **k: _FakeAdapter(state))
    admission = admit_local("llamacpp", provider=None, base_url="http://h", model="qwen3-4b",
                            want=32768, min_ctx=4096, hardware=Hardware(ram_total_gb=64, ram_available_gb=48))
    assert admission.blocked is False
    assert admission.num_ctx == 4096
    assert admission.slots == 2
    assert "per request" in admission.note


def test_admission_refuses_a_missing_model_on_a_live_server(monkeypatch):
    state = LlamaCppRuntime("http://h", http=Fake({
        "http://h/props": _json(LLAMA_PROPS),
        "http://h/health": _json({}),
        "http://h/v1/models": _json(LLAMA_MODELS),
        "http://h/slots": _json([{"id": 0, "n_ctx": 4096}]),
    })).state()
    monkeypatch.setattr("hutch.providers.local.admission.adapter_for", lambda *a, **k: _FakeAdapter(state))
    admission = admit_local("llamacpp", provider=None, base_url="http://h", model="other-model",
                            want=8192, min_ctx=4096, hardware=Hardware(ram_total_gb=64, ram_available_gb=48))
    assert admission.blocked is True
    assert admission.error_kind == "model_missing"


def test_admission_refuses_a_key_protected_server(monkeypatch):
    state = LlamaCppRuntime("http://h", http=Fake({
        "http://h/health": _json({}), "http://h/props": HttpResult(401, b""),
        "http://h/v1/models": HttpResult(401, b"")})).state()
    monkeypatch.setattr("hutch.providers.local.admission.adapter_for", lambda *a, **k: _FakeAdapter(state))
    admission = admit_local("llamacpp", provider=None, base_url="http://h", model="qwen3-4b",
                            want=8192, min_ctx=4096, hardware=Hardware(ram_total_gb=64, ram_available_gb=48),
                            credential="")
    assert admission.blocked is True
    assert admission.error_kind == "auth"


def test_admission_loads_a_cold_lmstudio_model_at_a_fitted_window(monkeypatch):
    poster = Fake({}, post={"http://h/api/v1/models/load": _json(
        {"type": "llm", "status": "loaded", "load_config": {"context_length": 8192}})})
    cold = LMStudioRuntime("http://h", http=Fake({"http://h/api/v1/models": _json(
        {"models": [{**LMSTUDIO["models"][0], "loaded_instances": []}]})}),
        post=poster.post).state()
    adapter = _FakeAdapter(cold)
    adapter.loads = []
    adapter.load = lambda model, context_length: adapter.loads.append((model, context_length)) or 8192
    monkeypatch.setattr("hutch.providers.local.admission.adapter_for", lambda *a, **k: adapter)
    admission = admit_local("lmstudio", provider=None, base_url="http://h", model="qwen3-4b",
                            want=16384, min_ctx=4096, hardware=Hardware(ram_total_gb=64, ram_available_gb=48))
    assert admission.blocked is False
    assert admission.num_ctx == 8192
    assert adapter.loads == [("qwen3-4b", 16384)]


def test_admission_reports_an_unknown_window_instead_of_guessing(monkeypatch):
    state = OpenAIGenericRuntime("vllm", "http://h", http=Fake(
        {"http://h/v1/models": _json({"data": [{"id": "m", "owned_by": "vllm"}]})})).state()
    monkeypatch.setattr("hutch.providers.local.admission.adapter_for", lambda *a, **k: _FakeAdapter(state))
    admission = admit_local("vllm", provider=None, base_url="http://h", model="m",
                            want=16384, min_ctx=4096, hardware=Hardware(ram_total_gb=64, ram_available_gb=48))
    assert admission.blocked is False
    assert admission.num_ctx is None
    assert admission.state == "unknown"
    assert "does not report the window" in admission.note


class _FakeAdapter:
    def __init__(self, state):
        self._state = state

    def state(self):
        return self._state

    def load(self, model, context_length):
        return None


class _FakeOllama:
    def __init__(self, meta):
        self._meta = meta

    def show(self, model):
        return self._meta

    def health(self):
        return Health(ok=True)


def test_admission_keeps_ollama_on_its_measured_fit_path():
    meta = ModelMeta(name="qwen3:4b", size_bytes=2 * 1024 ** 3, max_context=32768)
    admission = admit_local("ollama", provider=_FakeOllama(meta), base_url="http://ollama", model="qwen3:4b",
                            want=16384, min_ctx=4096, hardware=Hardware(ram_total_gb=8, ram_available_gb=6))
    assert admission.blocked is False
    assert admission.num_ctx and admission.num_ctx <= 16384
    assert admission.fit_status in ("fits", "tight")


def test_admission_refuses_an_ollama_model_that_cannot_fit():
    meta = ModelMeta(name="huge", size_bytes=64 * 1024 ** 3)
    admission = admit_local("ollama", provider=_FakeOllama(meta), base_url="http://ollama", model="huge",
                            want=16384, min_ctx=4096, hardware=Hardware(ram_total_gb=8, ram_available_gb=6))
    assert admission.blocked is True
    assert admission.error_kind == "oom"
