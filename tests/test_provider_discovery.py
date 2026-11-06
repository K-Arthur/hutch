"""Tests for loopback local-inference discovery (no live service required)."""

from __future__ import annotations

import json

import pytest

from hutch.providers.discovery import (
    ENDPOINTS,
    LocalEndpoint,
    parse_models,
    probe_local_services,
    probe_service,
    services_json,
    verified_loopback_url,
)
from hutch.providers.local import HttpResult, ProbeError

LLAMA_MODELS = {"data": [{"id": "qwen3-4b", "owned_by": "llamacpp",
                          "architecture": {"input_modalities": ["text"]},
                          "meta": {"n_ctx": 4096, "n_ctx_train": 262144, "n_params": 4022468096,
                                   "size": 2491323904, "ftype": "Q4_K - Medium"}}]}
LLAMA_PROPS = {"build_info": "b12144-69ee2ecc0", "total_slots": 2,
               "model_path": "models/qwen3-4b.gguf", "default_generation_settings": {"n_ctx": 8192},
               "chat_template_caps": {"supports_tools": True},
               "modalities": {"vision": False, "audio": False}}
LLAMA_SLOTS = [{"id": 0, "n_ctx": 4096, "is_processing": False},
               {"id": 1, "n_ctx": 4096, "is_processing": False}]
LMSTUDIO = {"models": [{"type": "llm", "key": "qwen3-4b", "architecture": "qwen3",
                        "quantization": {"name": "Q4_K_M"}, "size_bytes": 2497280480,
                        "params_string": "4B", "max_context_length": 262144,
                        "capabilities": {"vision": False, "trained_for_tool_use": True},
                        "loaded_instances": [{"id": "qwen3-4b",
                                              "config": {"context_length": 8192, "parallel": 4}}]}]}


class Fake:
    def __init__(self, routes: dict[str, HttpResult | Exception]):
        self.routes = routes
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url: str, timeout: float, bearer: str = "") -> HttpResult:
        self.calls.append((url, bearer))
        for prefix, answer in self.routes.items():
            if url == prefix:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise ProbeError("unreachable", "no service answered")


def _json(payload: dict, status: int = 200) -> HttpResult:
    return HttpResult(status, json.dumps(payload).encode())


def test_only_exact_loopback_plain_http_endpoints_are_accepted():
    assert verified_loopback_url("http://127.0.0.1:11434/api/tags")
    assert verified_loopback_url("http://localhost:1234/v1/models")
    for bad in ("https://127.0.0.1:1/v1/models", "http://example.com/v1/models",
                "http://user:pw@127.0.0.1:1/v1/models", "http://127.0.0.1:1/v1/models#frag"):
        with pytest.raises(ValueError):
            verified_loopback_url(bad)


def test_caller_supplied_non_loopback_endpoint_is_refused_before_any_request():
    fake = Fake({})

    with pytest.raises(ValueError):
        probe_service(LocalEndpoint("evil", "Evil", "http://192.168.1.10/v1/models", "openai"), get=fake)
    assert fake.calls == []


def test_ollama_and_openai_model_lists_are_parsed_and_bounded():
    ollama = {"models": [{"name": "llama3:8b"}, {"name": "qwen2.5:7b"}, {"name": "bad\u0001name"}]}
    assert parse_models("ollama", ollama) == ["llama3:8b", "qwen2.5:7b"]
    openai = {"data": [{"id": "gpt-local"}, {"id": "other/model"}]}
    assert parse_models("openai", openai) == ["gpt-local", "other/model"]
    assert parse_models("openai", {"data": "not-a-list"}) == []
    assert parse_models("ollama", {"models": [{"name": "x" * 300}]}) == []


def test_probe_reports_lmstudio_models_and_the_applied_window_without_credentials():
    fake = Fake({"http://127.0.0.1:1234/v1/models": _json({"data": [{"id": "qwen3-4b"}]}),
                 "http://127.0.0.1:1234/api/v1/models": _json(LMSTUDIO)})
    result = probe_service(LocalEndpoint("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1/models", "openai"),
                           get=fake)
    assert result["reachable"] is True
    assert result["models"] == ["qwen3-4b"]
    assert result["runtime"] == "lmstudio"
    assert result["applied_context"] == {"qwen3-4b": 8192}
    assert result["parallel"] == 4
    assert result["error"] == ""
    assert all(bearer == "" for _url, bearer in fake.calls)


def test_dead_or_malformed_service_is_reported_not_raised():
    dead = Fake({"http://127.0.0.1:11434/api/tags": ProbeError("unreachable", "refused")})
    result = probe_service(ENDPOINTS[0], get=dead)
    assert result["reachable"] is False
    assert "refused" in result["error"]

    malformed = Fake({"http://127.0.0.1:11434/api/tags": HttpResult(200, b"not json")})
    result = probe_service(ENDPOINTS[0], get=malformed)
    assert result["reachable"] is True
    assert "not with a model list" in result["error"]


def test_probe_all_known_endpoints_returns_one_row_each():
    fake = Fake({})
    probed = probe_local_services(get=fake)
    assert set(probed) == {"ollama", "lmstudio", "vllm", "sglang", "llamacpp"}
    rows = services_json(probed)
    assert len(rows) == 5
    assert all(row["reachable"] is False for row in rows)


def test_urls_that_do_not_answer_fall_through_to_the_alternate_port():
    fake = Fake({
        "http://127.0.0.1:9931/v1/models": ProbeError("unreachable", "refused"),
        "http://127.0.0.1:8080/v1/models": _json(LLAMA_MODELS),
        "http://127.0.0.1:8080/health": _json({}),
        "http://127.0.0.1:8080/props": _json(LLAMA_PROPS),
        "http://127.0.0.1:8080/slots": _json(LLAMA_SLOTS),
    })
    result = probe_service(ENDPOINTS[-1], get=fake)
    assert result["url"] == "http://127.0.0.1:8080/v1/models"
    assert result["runtime"] == "llamacpp"
    assert result["applied_context"] == {"qwen3-4b": 4096}
    assert result["parallel"] == 2


def test_a_decoy_answering_v1_models_is_not_labelled_llama_cpp():
    decoy = {"data": [{"id": "not-a-model-server", "owned_by": "organization_owner"}]}
    fake = Fake({
        "http://127.0.0.1:9931/v1/models": HttpResult(404, b""),
        "http://127.0.0.1:8080/v1/models": _json(decoy),
        "http://127.0.0.1:8080/health": HttpResult(404, b""),
        "http://127.0.0.1:8080/props": HttpResult(404, b""),
    })
    result = probe_service(ENDPOINTS[-1], get=fake)
    assert result["reachable"] is True
    assert result["runtime"] == "unknown"
    assert result["confidence"] != "strong"
    assert result["models"] == ["not-a-model-server"]


def test_a_401_is_needs_key_not_a_dead_port():
    fake = Fake({"http://127.0.0.1:1234/v1/models": HttpResult(401, b'{"error":"token required"}')})
    result = probe_service(ENDPOINTS[1], get=fake)
    assert result["reachable"] is True
    assert result["state"] == "needs_key"
    assert "never in the URL" in result["fix"]


def test_a_supplied_key_is_sent_only_to_that_provider_and_never_returned():
    fake = Fake({
        "http://127.0.0.1:9931/v1/models": _json(LLAMA_MODELS),
        "http://127.0.0.1:9931/health": _json({}),
        "http://127.0.0.1:9931/props": _json(LLAMA_PROPS),
        "http://127.0.0.1:9931/slots": _json(LLAMA_SLOTS),
    })

    def credential_for(provider_id: str, url: str) -> str:
        return "secret-token" if provider_id == "llamacpp" else ""

    result = probe_service(ENDPOINTS[-1], get=fake, credential_for=credential_for)
    assert fake.calls and all(bearer == "secret-token" for _url, bearer in fake.calls)
    assert "secret-token" not in json.dumps(result)

    other = Fake({"http://127.0.0.1:1234/v1/models": _json({"data": [{"id": "qwen3-4b"}]}),
                  "http://127.0.0.1:1234/api/v1/models": _json(LMSTUDIO)})
    probe_service(ENDPOINTS[1], get=other, credential_for=credential_for)
    assert other.calls and all(bearer == "" for _url, bearer in other.calls)
