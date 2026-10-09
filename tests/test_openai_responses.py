from __future__ import annotations

import json

import httpx
import pytest

from hutch.providers import ChatRequest, ProviderError
from hutch.providers.openai_responses import OpenAIResponsesProvider


def sse(*events):
    return "".join("data: " + json.dumps(event, separators=(",", ":")) + "\n\n" for event in events)


def completed(output, *, text="Done", status="completed", usage=None):
    return {"type": "response.completed", "response": {
        "status": status, "model": "gpt-fixture", "output": output,
        "usage": usage or {"input_tokens": 23, "output_tokens": 7,
                            "input_tokens_details": {"cached_tokens": 3}},
        "output_text": text,
    }}


def test_responses_request_uses_only_supported_fields_and_converts_hutch_history():
    requests = []

    def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert request.url == "https://api.openai.com/v1/responses"
        assert request.headers["authorization"] == "Bearer fixture-access"
        assert payload["store"] is False and payload["stream"] is True
        for unsupported in ("max_output_tokens", "temperature", "top_p", "previous_response_id",
                            "background", "conversation", "metadata", "user"):
            assert unsupported not in payload
        assert payload["instructions"] == "follow policy\n\nbe concise"
        assert payload["input"] == [
            {"type": "additional_tools", "role": "developer", "tools": [
                {"type": "function", "name": "lookup", "parameters": {"type": "object"},
                 "strict": False, "description": "find a record"}
            ]},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "using a tool"},
            {"type": "function_call", "call_id": "call-1", "name": "lookup", "arguments": "{\"q\":1}"},
            {"type": "function_call_output", "call_id": "call-1", "output": "found"},
            {"role": "user", "content": "finish"},
        ]
        assert "tools" not in payload
        events = sse(
            {"type": "response.output_text.delta", "delta": "Done"},
            completed([{"type": "message", "content": [{"type": "output_text", "text": "Done"}]}]),
        )
        return httpx.Response(200, text=events, headers={"content-type": "text/event-stream"})

    provider = OpenAIResponsesProvider("fixture-access", transport=httpx.MockTransport(handler))
    result = provider.chat(ChatRequest(model="gpt-fixture", max_tokens=32, temperature=0.2,
        messages=[{"role": "system", "content": "follow policy"},
                  {"role": "developer", "content": "be concise"},
                  {"role": "user", "content": "first"},
                  {"role": "assistant", "content": "using a tool", "tool_calls": [
                      {"id": "call-1", "type": "function", "function": {
                          "name": "lookup", "arguments": "{\"q\":1}"}}]},
                  {"role": "tool", "tool_call_id": "call-1", "content": "found"},
                  {"role": "user", "content": "finish"}],
        tools=[{"type": "function", "function": {"name": "lookup", "description": "find a record",
                 "parameters": {"type": "object"}}}]))
    assert result.content == "Done"
    assert result.model == "gpt-fixture"
    assert (result.prompt_tokens, result.completion_tokens, result.cached_tokens) == (23, 7, 3)
    assert "provider-enforced output-token ceiling" in result.notes[0]
    assert len(requests) == 1


def test_completed_function_calls_are_correlated_and_parsed():
    event = completed([{"type": "function_call", "call_id": "call-9", "name": "write_file",
                        "arguments": "{\"path\":\"note.txt\"}"}])
    provider = OpenAIResponsesProvider("fixture-access", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text=sse(event), headers={"content-type": "text/event-stream"})))
    result = provider.chat(ChatRequest(model="gpt-fixture", messages=[{"role": "user", "content": "write"}]))
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call-9"
    assert result.tool_calls[0].arguments == {"path": "note.txt"}
    assert result.finish_reason == "tool_calls"


def test_stream_must_finish_with_explicit_completed_event_and_does_not_retry():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text="data: [DONE]\n\n", headers={"content-type": "text/event-stream"})

    request = ChatRequest(model="gpt-fixture", messages=[{"role": "user", "content": "hello"}])
    provider = OpenAIResponsesProvider("fixture-access", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="without a completed response"):
        provider.chat(request)
    assert len(bodies) == 1
    assert request.allow_stream_retry is False


@pytest.mark.parametrize(("kind", "code", "expected"), [
    ("response.incomplete", "server_error", "server"),
    ("response.failed", "usage_limit_reached", "rate_limit"),
    ("response.failed", "content_filter", "refused"),
])
def test_terminal_failure_events_keep_their_meaning_and_are_never_retried(kind, code, expected):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text=sse({"type": kind, "response": {
            "status": "incomplete" if kind.endswith("incomplete") else "failed",
            "error": {"code": code, "message": "fixture terminal result"}}}),
            headers={"content-type": "text/event-stream"})

    request = ChatRequest(model="gpt-fixture", messages=[{"role": "user", "content": "hello"}])
    provider = OpenAIResponsesProvider("fixture-access", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as raised:
        provider.chat(request)
    assert raised.value.kind == expected
    assert len(bodies) == 1


def test_provider_refuses_unofficial_hosts_and_requires_streaming():
    with pytest.raises(ProviderError, match="may only be sent"):
        OpenAIResponsesProvider("secret", base_url="https://api.openai.com.attacker.invalid/v1")
    provider = OpenAIResponsesProvider("fixture-access", transport=httpx.MockTransport(
        lambda request: pytest.fail("non-streaming must not send a request")))
    with pytest.raises(ProviderError, match="requires streaming"):
        provider.chat(ChatRequest(model="gpt-fixture", stream=False,
                                  messages=[{"role": "user", "content": "hello"}]))


def test_unpaired_hutch_tool_history_is_rejected_before_http():
    provider = OpenAIResponsesProvider("fixture-access", transport=httpx.MockTransport(
        lambda request: pytest.fail("invalid history must not reach OpenAI")))
    with pytest.raises(ProviderError, match="no call id"):
        provider.chat(ChatRequest(model="gpt-fixture", messages=[
            {"role": "assistant", "tool_calls": [{"function": {"name": "lookup", "arguments": "{}"}}]},
        ]))
