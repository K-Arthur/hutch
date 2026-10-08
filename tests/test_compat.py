from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from hutch.compat import compatibility_matrix
from hutch.providers.base import ChatRequest
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.server.app import create_app


def test_versioned_matrix_has_status_and_dated_policy_evidence_for_every_route():
    matrix = compatibility_matrix()
    assert matrix["version"] == 1
    assert matrix["reviewed_on"] == "2026-10-08"
    routes = {route["id"]: route for route in matrix["routes"]}
    assert {
        "openai-chat-completions", "anthropic-messages", "ollama-native",
        "openai-compatible-connection", "opencode-go-connection", "sign-in-with-chatgpt",
        "opencode-harness", "pi-harness", "consumer-plan-oauth",
    } <= routes.keys()
    for route in routes.values():
        assert route["state"] in {"supported", "experimental", "unavailable", "blocked"}
        date.fromisoformat(route["verified_on"])
        assert isinstance(route["hutch_request_mapping"]["sent"], list)
        assert isinstance(route["hutch_request_mapping"]["omitted"], list)
        for evidence in route["policy_evidence"]:
            assert evidence["url"].startswith("https://")
            date.fromisoformat(evidence["observed_on"])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    with TestClient(create_app()) as test_client:
        yield test_client


def test_versioned_compatibility_endpoint_returns_typed_route_records(client):
    response = client.get("/api/v1/compatibility")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    route = next(row for row in body["routes"] if row["id"] == "openai-compatible-connection")
    assert route["state"] == "supported"
    assert "model-specific" in route["models"]
    assert route["hutch_request_mapping"]["omitted"]
    assert route["policy_evidence"]


def test_openai_request_mapping_strips_unimplemented_fields_and_uses_exact_host():
    request = ChatRequest(
        model="gpt-fixture", messages=[{"role": "user", "content": "hello"}], tools=[{
            "type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}
        }], max_tokens=19, temperature=0.2, num_ctx=8192, think=False, effort="high", stream=True,
    )
    official = OpenAICompatProvider("https://api.openai.com/v1", "fixture-key", "openai")
    body = official._body(request, stream=True)
    assert body == {
        "model": "gpt-fixture", "messages": request.messages, "tools": request.tools, "stream": True,
        "max_completion_tokens": 19, "temperature": 0.2, "stream_options": {"include_usage": True},
    }
    assert "num_ctx" not in body and "think" not in body and "effort" not in body
    assert "reasoning_effort" not in body and "response_format" not in body


@pytest.mark.parametrize("url", [
    "https://api.openai.com.attacker.invalid/v1",
    "https://proxy.example/api.openai.com/v1",
    "http://api.openai.com/v1",
    "https://api.openai.com:8443/v1",
])
def test_openai_token_parameter_does_not_trust_lookalike_or_insecure_endpoint(url):
    provider = OpenAICompatProvider(url)
    body = provider._body(ChatRequest(model="fixture", messages=[], max_tokens=3), stream=False)
    assert body["max_tokens"] == 3
    assert "max_completion_tokens" not in body
