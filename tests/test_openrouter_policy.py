import math

import pytest
import httpx

from hutch.connections import ConnectionBook
from hutch.providers.base import ChatRequest
from hutch.providers.connection import provider_for_connection
from hutch.providers.openrouter_policy import validate_policy
from hutch.providers.openai_compat import OpenAICompatProvider


def test_named_router_connection_preserves_usage_and_endpoint_controls(config, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-not-a-real-key")
    book = ConnectionBook(config.state_dir)
    policy = {"data_collection": "deny", "require_parameters": True, "allow_fallbacks": False,
              "order": ["fixture-provider"], "max_price": {"prompt": 1, "completion": 2}}
    book.add("openrouter", name="eval-router", openrouter_policy=policy)
    provider = provider_for_connection(book, "eval-router", "deepseek/test")
    request = ChatRequest(model="deepseek/test", messages=[], max_tokens=64)
    body = provider._body(request, stream=False)
    assert body["provider"] == policy
    assert body["usage"] == {"include": True}
    assert body["max_completion_tokens"] == 64
    body["provider"]["order"].append("must-not-persist")
    assert provider._body(request, stream=False)["provider"]["order"] == ["fixture-provider"]
    assert ConnectionBook(config.state_dir).get("eval-router").openrouter_policy == policy


@pytest.mark.parametrize("policy", [
    {"api_key": "no-arbitrary-fields"}, {"data_collection": "sometimes"},
    {"allow_fallbacks": "false"}, {"order": []}, {"order": [1]},
    {"max_price": {}}, {"max_price": {"completion": -1}},
    {"max_price": {"prompt": math.nan}}, {"max_price": {"request": True}},
    {"max_price": {"prompt": 10 ** 1000}},
    {"max_price": {"unknown_dimension": 0}},
])
def test_invalid_policy_is_rejected(policy):
    with pytest.raises(ValueError):
        validate_policy(policy)


def test_router_controls_cannot_escape_to_custom_provider(config):
    with pytest.raises(ValueError, match="OpenRouter connection"):
        ConnectionBook(config.state_dir).add("custom-openai", name="custom-test",
            base_url="https://example.test/v1", openrouter_policy={"data_collection": "deny"})


def test_free_price_ceiling_is_not_dropped():
    assert validate_policy({"max_price": {"prompt": 0, "completion": 0, "request": 0}}) == {
        "max_price": {"prompt": 0, "completion": 0, "request": 0}}


def test_exhausted_quota_is_terminal_but_transient_throttle_is_retryable():
    provider = OpenAICompatProvider("https://openrouter.ai/api/v1", provider_name="openrouter")
    response = httpx.Response(429, json={"error": {"code": "insufficient_quota", "message": "Limit reached"}})
    error = provider._error_from_response(response)
    assert error.kind == "quota" and not error.retryable
    response = httpx.Response(429, json={"error": {"message": "Requests per minute exceeded"}})
    error = provider._error_from_response(response)
    assert error.kind == "rate_limit" and error.retryable


def test_routing_policy_changes_invalidate_route_qualification(config):
    from hutch.route_identity import route_tuple
    book = ConnectionBook(config.state_dir)
    book.add("openrouter", name="eval-router", openrouter_policy={"data_collection": "deny"})
    before = route_tuple(provider="eval-router", model="fixture/model", connections=book)
    book.update("eval-router", openrouter_policy={"data_collection": "allow"})
    after = route_tuple(provider="eval-router", model="fixture/model", connections=book)
    assert before != after


def test_connection_api_round_trips_controls_and_rejects_invalid_policy(config, monkeypatch):
    from fastapi.testclient import TestClient
    from hutch.server.app import create_app
    with TestClient(create_app()) as client:
        policy = {"data_collection": "deny", "max_price": {"prompt": 0, "completion": 0}}
        result = client.post("/api/connections", json={"template": "openrouter", "name": "eval-router",
                                                       "openrouter_policy": policy})
        assert result.status_code == 201
        assert ConnectionBook(config.state_dir).get("eval-router").openrouter_policy == policy
        result = client.get("/api/v1/connections")
        assert result.status_code == 200
        assert next(row for row in result.json() if row["name"] == "eval-router")["openrouter_policy"] == policy
        result = client.post("/api/connections", json={"template": "openrouter", "name": "invalid-router",
                                                       "openrouter_policy": {"allow_fallbacks": "no"}})
        assert result.status_code == 422
        assert ConnectionBook(config.state_dir).get("invalid-router") is None
