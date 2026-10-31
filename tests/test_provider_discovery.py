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


def test_only_exact_loopback_plain_http_endpoints_are_accepted():
    assert verified_loopback_url("http://127.0.0.1:11434/api/tags")
    assert verified_loopback_url("http://localhost:1234/v1/models")
    for bad in ("https://127.0.0.1:1/v1/models", "http://example.com/v1/models",
                "http://user:pw@127.0.0.1:1/v1/models", "http://127.0.0.1:1/v1/models#frag"):
        with pytest.raises(ValueError):
            verified_loopback_url(bad)


def test_caller_supplied_non_loopback_endpoint_is_refused_before_any_request():
    requested = []

    def get(url, timeout):
        requested.append(url)
        return b"{}"

    with pytest.raises(ValueError):
        probe_service(LocalEndpoint("evil", "Evil", "http://192.168.1.10/v1/models", "openai"), get=get)
    assert requested == []


def test_ollama_and_openai_model_lists_are_parsed_and_bounded():
    ollama = {"models": [{"name": "llama3:8b"}, {"name": "qwen2.5:7b"}, {"name": "bad\u0001name"}]}
    assert parse_models("ollama", ollama) == ["llama3:8b", "qwen2.5:7b"]
    openai = {"data": [{"id": "gpt-local"}, {"id": "other/model"}]}
    assert parse_models("openai", openai) == ["gpt-local", "other/model"]
    assert parse_models("openai", {"data": "not-a-list"}) == []
    assert parse_models("ollama", {"models": [{"name": "x" * 300}]}) == []


def test_probe_reports_reachable_models_without_credentials():
    def get(url, timeout):
        assert timeout == 0.5
        return json.dumps({"data": [{"id": "model-a"}]}).encode()

    result = probe_service(LocalEndpoint("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1/models", "openai"),
                           get=get)
    assert result["reachable"] is True
    assert result["models"] == ["model-a"]
    assert result["error"] == ""


def test_dead_or_malformed_service_is_reported_not_raised():
    def dead(url, timeout):
        raise OSError("connection refused")

    result = probe_service(ENDPOINTS[0], get=dead)
    assert result["reachable"] is False
    assert result["error"] == "no service answered"

    def malformed(url, timeout):
        return b"not json"

    result = probe_service(ENDPOINTS[0], get=malformed)
    assert result["reachable"] is False
    assert "not with a model list" in result["error"]


def test_probe_all_known_endpoints_returns_one_row_each():
    def get(url, timeout):
        raise OSError("refused")

    probed = probe_local_services(get=get)
    assert set(probed) == {"ollama", "lmstudio", "vllm", "sglang", "llamacpp"}
    rows = services_json(probed)
    assert len(rows) == 5
    assert all(row["reachable"] is False for row in rows)
