"""Vision capability for local OpenAI-compatible routes, from the runtime's own fields."""

from __future__ import annotations

import json

from hutch.providers.local import HttpResult, ProbeError
from hutch.providers.local.vision import local_vision_supported
from hutch.providers.openai_compat import OpenAICompatProvider

LLAMA_PROPS = {"build_info": "b12144-69ee2ecc0", "total_slots": 2,
               "model_path": "models/qwen2.5-vl.gguf", "default_generation_settings": {"n_ctx": 8192},
               "chat_template_caps": {"supports_tools": True},
               "modalities": {"vision": True, "audio": False}}


def _json(payload: dict, status: int = 200) -> HttpResult:
    return HttpResult(status, json.dumps(payload).encode())


class Fake:
    def __init__(self, routes: dict[str, HttpResult | Exception]):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float, bearer: str = "") -> HttpResult:
        self.calls.append(url)
        answer = self.routes.get(url)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise ProbeError("unreachable", "no service answered")
        return answer


def _llamacpp(*, vision: bool) -> Fake:
    models = {"data": [{"id": "qwen2.5-vl", "owned_by": "llamacpp",
                        "architecture": {"input_modalities": ["text", "image"] if vision else ["text"]},
                        "meta": {"n_ctx": 8192, "n_ctx_train": 32768, "n_params": 3750000000,
                                 "size": 1929901056, "ftype": "Q4_K - Medium"}}]}
    props = {**LLAMA_PROPS, "modalities": {"vision": vision, "audio": False}}
    return Fake({
        "http://h/health": _json({}),
        "http://h/props": _json(props),
        "http://h/v1/models": _json(models),
        "http://h/slots": _json([{"id": 0, "n_ctx": 4096}, {"id": 1, "n_ctx": 4096}]),
    })


def test_llamacpp_vision_comes_from_props_and_input_modalities():
    assert local_vision_supported("llamacpp", "http://h/v1", "qwen2.5-vl", http=_llamacpp(vision=True)) is True
    assert local_vision_supported("llamacpp", "http://h/v1", "qwen2.5-vl", http=_llamacpp(vision=False)) is False


def test_llamacpp_unknown_model_is_not_promised_vision():
    fake = _llamacpp(vision=True)
    assert local_vision_supported("llamacpp", "http://h", "some-other-model", http=fake) is False


def test_lmstudio_vision_comes_from_capabilities():
    payload = {"models": [{"type": "llm", "key": "qwen2.5-vl", "architecture": "qwen2.5vl",
                           "quantization": {"name": "Q4_K_M"}, "size_bytes": 1929901056,
                           "max_context_length": 32768,
                           "capabilities": {"vision": True, "trained_for_tool_use": True},
                           "loaded_instances": []}]}
    fake = Fake({"http://h/api/v1/models": _json(payload)})
    assert local_vision_supported("lmstudio", "http://h/v1", "qwen2.5-vl", http=fake) is True

    payload["models"][0]["capabilities"] = {"vision": False, "trained_for_tool_use": True}
    fake = Fake({"http://h/api/v1/models": _json(payload)})
    assert local_vision_supported("lmstudio", "http://h/v1", "qwen2.5-vl", http=fake) is False


def test_unreadable_runtime_and_foreign_provider_are_never_promised():
    dead = Fake({})
    assert local_vision_supported("llamacpp", "http://h", "qwen2.5-vl", http=dead) is False
    assert local_vision_supported("openai-compatible", "http://h", "qwen2.5-vl", http=dead) is None
    assert local_vision_supported("vllm", "http://h", "qwen2.5-vl", http=dead) is None
    assert local_vision_supported("llamacpp", "", "qwen2.5-vl", http=dead) is False


def test_openai_compat_provider_uses_the_local_adapter(monkeypatch):
    seen: list[tuple] = []

    class Dummy:
        def capabilities(self, model: str) -> list[str]:
            return ["vision", "tools"]

    def adapter_for(provider_id, base_url, credential="", **options):
        seen.append((provider_id, base_url, credential))
        return Dummy()

    monkeypatch.setattr("hutch.providers.local.adapter_for", adapter_for)
    provider = OpenAICompatProvider("http://127.0.0.1:9931/v1", "secret", provider_name="llamacpp")
    assert provider.supports_vision("qwen2.5-vl") is True
    assert seen == [("llamacpp", "http://127.0.0.1:9931/v1", "secret")]


def test_openai_compat_provider_does_not_claim_vision_for_an_unknown_route(monkeypatch):
    monkeypatch.setattr("hutch.providers.local.adapter_for",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be asked")))
    provider = OpenAICompatProvider("http://example.test/v1", provider_name="openai-compatible")
    assert provider.supports_vision("some-model") is False
