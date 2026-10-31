"""The native Gemini route: conversion, SSE assembly, signatures, errors and discovery.

These are contract tests against recorded wire shapes taken from the published discovery document
(v1beta, revision 20261030) and the official docs. They prove the adapter speaks the protocol; they do
not prove a real Gemini key works, which is recorded as an open verification gap.
"""

from __future__ import annotations

import json

import httpx
import pytest

from hutch.connections import ConnectionBook
from hutch.providers.base import ChatRequest, ProviderError
from hutch.providers.connection import provider_for_connection
from hutch.providers.gemini import (DEFAULT_BASE_URL, GeminiProvider, forget_signatures, signature_for)
from hutch.toolcalling.profiles import classify_endpoint, protocol_for_provider
from hutch.providers.registry import make_provider

TOOL = {"type": "function", "function": {
    "name": "write_file", "description": "write a file",
    "parameters": {"$schema": "https://json-schema.org/draft/2020-12/schema",
                   "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}


@pytest.fixture(autouse=True)
def _clean_signatures():
    forget_signatures(DEFAULT_BASE_URL)
    yield
    forget_signatures(DEFAULT_BASE_URL)


def provider(handler, key="test-key") -> GeminiProvider:
    p = GeminiProvider(api_key=key)
    real = p._http()                     # keeps the adapter's base URL and auth header
    p._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=real.base_url,
                             headers=real.headers)
    return p


def req(model="gemini-3.8-flash", messages=None, **kw):
    return ChatRequest(model=model, messages=messages or [{"role": "user", "content": "hello"}], **kw)


def sse(*chunks) -> httpx.Response:
    body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)


# --------------------------------------------------------------- request conversion

def test_request_shape_endpoint_key_header_and_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]},
                                                         "finishReason": "STOP"}],
                                         "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
                                         "modelVersion": "gemini-3.8-flash-001"})

    result = provider(handler).chat(req(messages=[{"role": "system", "content": "be brief"},
                                                 {"role": "user", "content": "hello"}],
                                        tools=[TOOL], max_tokens=64, temperature=0.2, stream=False))
    assert seen["url"].endswith("/v1beta/models/gemini-3.8-flash:generateContent")
    assert "test-key" not in seen["url"] and "key=" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "test-key"
    body = seen["body"]
    assert body["systemInstruction"] == {"parts": [{"text": "be brief"}]}
    assert body["contents"][0] == {"role": "user", "parts": [{"text": "hello"}]}
    assert body["generationConfig"] == {"maxOutputTokens": 64, "temperature": 0.2}
    declaration = body["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "write_file"
    assert "$schema" not in declaration["parametersJsonSchema"]
    assert result.content == "ok" and result.model == "gemini-3.8-flash-001"
    assert (result.prompt_tokens, result.completion_tokens) == (3, 1)


def test_thinking_level_is_only_sent_for_gemini_3_and_later():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]},
                                                         "finishReason": "STOP"}]})

    provider(handler).chat(req(model="gemini-3.8-flash", effort="low", stream=False))
    provider(handler).chat(req(model="gemini-2.5-flash", effort="low", stream=False))
    assert bodies[0]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "LOW"}
    assert "thinkingConfig" not in bodies[1].get("generationConfig", {})


def test_images_are_inline_and_remote_urls_are_refused():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "seen"}]},
                                                         "finishReason": "STOP"}]})

    inline = [{"role": "user", "content": [
        {"type": "text", "text": "what is this"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}}]}]
    provider(handler).chat(req(messages=inline, stream=False))
    parts = bodies[0]["contents"][0]["parts"]
    assert parts[1] == {"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgo="}}

    remote = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}}]}]
    with pytest.raises(ProviderError, match="remote image URL was not fetched"):
        provider(handler).chat(req(messages=remote, stream=False))


def test_a_non_local_ref_is_refused_instead_of_being_dropped():
    tool = {"type": "function", "function": {"name": "f", "parameters": {
        "type": "object", "properties": {"x": {"$ref": "https://evil.test/schema.json"}}}}}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be reached
        raise AssertionError("nothing may be sent with an unresolvable schema")

    with pytest.raises(ProviderError, match="non-local"):
        provider(handler).chat(req(tools=[tool], stream=False))


def test_non_function_tools_are_refused():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("nothing may be sent")

    with pytest.raises(ProviderError, match="function tools only"):
        provider(handler).chat(req(tools=[{"type": "web_search"}], stream=False))


# --------------------------------------------------------------- streaming

def test_sse_stream_accumulates_text_usage_and_endpoint_identity():
    chunks = [
        {"candidates": [{"content": {"parts": [{"text": "Hel"}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "lo"}]}, "finishReason": "STOP"}],
         "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 4,
                           "cachedContentTokenCount": 2, "thoughtsTokenCount": 3},
         "modelVersion": "gemini-3.8-flash-001"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("alt") == "sse"
        assert b'"stream"' not in request.content
        return sse(*chunks)

    result = provider(handler).chat(req())
    assert result.content == "Hello" and result.streamed is True
    assert (result.prompt_tokens, result.completion_tokens, result.cached_tokens) == (11, 4, 2)
    assert result.model == "gemini-3.8-flash-001"
    assert any("thinking token" in note for note in result.notes)


def test_a_stream_without_a_completion_marker_retries_once_without_streaming():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith(":streamGenerateContent"):
            return sse({"candidates": [{"content": {"parts": [{"text": "partial"}]}}]})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "complete"}]},
                                                         "finishReason": "STOP"}]})

    result = provider(handler).chat(req())
    assert len(calls) == 2 and calls[1].endswith(":generateContent")
    assert result.streamed is False and result.content == "complete"


def test_without_the_retry_the_partial_stream_is_reported_as_incomplete():
    def handler(request: httpx.Request) -> httpx.Response:
        return sse({"candidates": [{"content": {"parts": [{"text": "partial"}]}}]})

    with pytest.raises(ProviderError) as caught:
        provider(handler).chat(req(allow_stream_retry=False))
    assert caught.value.kind == "stream" and caught.value.partial_content == "partial"


def test_an_empty_stream_is_a_stream_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return sse({"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}]})

    with pytest.raises(ProviderError, match="without any content"):
        provider(handler).chat(req(allow_stream_retry=False))


# --------------------------------------------------------------- tool calls + signatures

def test_function_call_and_tool_result_round_trip_with_its_thought_signature():
    sent: list[dict] = []

    def first(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [
                {"functionCall": {"name": "write_file", "args": {"path": "a.md"}},
                 "thoughtSignature": "sig-abc"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2},
            "modelVersion": "gemini-3.8-flash-001"})

    p = provider(first)
    result = p.chat(req(tools=[TOOL], stream=False))
    call = result.tool_calls[0]
    assert call.name == "write_file" and call.arguments == {"path": "a.md"}
    assert result.finish_reason == "tool_calls"
    assert signature_for(DEFAULT_BASE_URL, call.id) == "sig-abc"

    def second(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "done"}]},
                                                         "finishReason": "STOP"}]})

    p._client = httpx.Client(transport=httpx.MockTransport(second), base_url=DEFAULT_BASE_URL)
    history = [
        {"role": "user", "content": "write it"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": call.id, "type": "function",
             "function": {"name": "write_file", "arguments": json.dumps({"path": "a.md"})}}]},
        {"role": "tool", "tool_call_id": call.id, "name": "write_file", "content": "wrote a.md"},
    ]
    p.chat(req(messages=history, tools=[TOOL], stream=False))
    contents = sent[0]["contents"]
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["thoughtSignature"] == "sig-abc"
    assert contents[1]["parts"][0]["functionCall"] == {"name": "write_file", "args": {"path": "a.md"},
                                                     "id": call.id}
    assert contents[2]["parts"][0]["functionResponse"] == {"name": "write_file",
                                                           "response": {"result": "wrote a.md"},
                                                           "id": call.id}


def test_missing_thought_signature_is_a_typed_error_with_a_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"content": {"parts": []},
                                                         "finishReason": "MISSING_THOUGHT_SIGNATURE"}]})

    with pytest.raises(ProviderError, match="thought signature") as caught:
        provider(handler).chat(req(tools=[TOOL], stream=False))
    assert caught.value.kind == "bad_request"


# --------------------------------------------------------------- finish reasons and errors

def test_safety_stop_is_a_refusal_with_its_category():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]})

    with pytest.raises(ProviderError) as caught:
        provider(handler).chat(req(stream=False))
    assert caught.value.kind == "refused" and getattr(caught.value, "category", "") == "SAFETY"


def test_a_blocked_prompt_is_a_refusal_not_an_empty_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"},
                                         "candidates": []})

    with pytest.raises(ProviderError) as caught:
        provider(handler).chat(req(stream=False))
    assert caught.value.kind == "refused"


def test_max_tokens_is_truncation_not_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "half"}]},
                                                         "finishReason": "MAX_TOKENS"}]})

    result = provider(handler).chat(req(stream=False))
    assert result.finish_reason == "length" and result.content == "half"


@pytest.mark.parametrize("status,body,kind", [
    (401, {"error": {"code": 401, "message": "API key not valid. Please pass a valid API key.",
                     "status": "UNAUTHENTICATED"}}, "auth"),
    (403, {"error": {"code": 403, "message": "Permission denied", "status": "PERMISSION_DENIED"}}, "auth"),
    (404, {"error": {"code": 404, "message": "models/nope is not found", "status": "NOT_FOUND"}},
     "model_missing"),
    (429, {"error": {"code": 429, "message": "Quota exceeded for this project", "status": "RESOURCE_EXHAUSTED"}},
     "quota"),
    (429, {"error": {"code": 429, "message": "Too many requests, slow down", "status": "RESOURCE_EXHAUSTED"}},
     "rate_limit"),
    (400, {"error": {"code": 400, "message": "The input token count exceeds the maximum", "status": "INVALID_ARGUMENT"}},
     "context"),
    (500, {"error": {"code": 500, "message": "internal", "status": "INTERNAL"}}, "server"),
])
def test_provider_errors_are_typed(status, body, kind):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    with pytest.raises(ProviderError) as caught:
        provider(handler).chat(req(stream=False))
    assert caught.value.kind == kind


def test_the_stored_key_never_appears_in_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}})

    with pytest.raises(ProviderError) as caught:
        provider(handler, key="super-secret").chat(req(stream=False))
    assert "super-secret" not in str(caught.value)


# --------------------------------------------------------------- discovery

def test_model_discovery_paginates_and_skips_non_generating_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1beta/models")
        if request.url.params.get("pageToken"):
            return httpx.Response(200, json={"models": [
                {"name": "models/text-embedding-005", "supportedGenerationMethods": ["embedContent"]}]})
        return httpx.Response(200, json={"models": [
            {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"],
             "inputTokenLimit": 1048576},
            {"name": "models/gemini-3-pro", "supportedGenerationMethods": ["generateContent"]}],
            "nextPageToken": "page-2"})

    ok, detail, names = provider(handler).probe_models()
    assert ok and "authenticated" in detail
    assert names == ["gemini-3-pro", "gemini-3.8-flash"]
    models = {m.name: m for m in provider(handler).list_models()}
    assert models["gemini-3.8-flash"].max_context == 1048576
    assert "text-embedding-005" not in models


def test_a_rejected_key_is_not_reported_as_discovery_failure_only():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": 401, "message": "API key not valid",
                                                   "status": "UNAUTHENTICATED"}})

    ok, detail, names = provider(handler).probe_models()
    assert not ok and names == [] and "rejected" in detail


# --------------------------------------------------------------- wiring: connection, registry

def test_the_google_template_builds_a_gemini_connection_and_provider(tmp_path):
    book = ConnectionBook(tmp_path)
    conn = book.add("google-gemini")
    assert conn.protocol == "gemini" and conn.base_url == DEFAULT_BASE_URL
    assert conn.api_key_env == "GEMINI_API_KEY" and conn.billing == "per_token"
    book.set_key("google-gemini", "k-123")
    built = provider_for_connection(book, "google-gemini", "gemini-3.8-flash")
    assert isinstance(built, GeminiProvider) and built.api_key == "k-123"


def test_the_template_carries_the_documented_endpoint_and_requirements():
    from hutch.connections import load_templates

    template = load_templates()["google-gemini"]
    assert template["base_url"] == "https://generativelanguage.googleapis.com/v1beta"
    assert template["protocol"] == "gemini" and template["api_key_env"] == "GEMINI_API_KEY"
    assert template["billing"] == "per_token" and template["models_endpoint"] is True
    assert template["source"] == "https://ai.google.dev/gemini-api/docs/text-generation"
    assert template["terms"]["requires_ack"] is False


def test_an_ambient_gemini_key_only_travels_to_the_official_host():
    official = make_provider("google", env={"GEMINI_API_KEY": "ambient"})
    assert isinstance(official, GeminiProvider) and official.api_key == "ambient"
    custom = make_provider("google", base_url="https://proxy.example.test/v1beta",
                           env={"GEMINI_API_KEY": "ambient"})
    assert custom.api_key == "" and "generativelanguage.googleapis.com" in custom.auth_hint


def test_vision_claims_are_narrow_to_documented_multimodal_models():
    p = GeminiProvider(api_key="k")
    for model in ("gemini-3.8-flash", "gemini-2.5-pro", "models/gemini-1.5-flash", "gemini-1.0-pro-vision"):
        assert p.supports_vision(model), model
    for model in ("gemini-1.0-pro", "text-embedding-005", "gemma-4-27b", "imagen-5"):
        assert not p.supports_vision(model), model


def test_route_classification_knows_the_gemini_protocol_and_official_host():
    assert protocol_for_provider("google") == "gemini"
    assert classify_endpoint(DEFAULT_BASE_URL) == "official"
    assert classify_endpoint("https://generativelanguage.googleapis.com.evil.test/v1beta") == "custom"
