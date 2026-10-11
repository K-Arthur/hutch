from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from hutch.persona import PersonaStyle, contextualize_persona, resolve_persona
from hutch.persona_preview import PREVIEW_PROMPT, preview_messages
from hutch.providers.base import ChatRequest, record_adapter_receipt
from hutch.providers.claude import ClaudeProvider
from hutch.providers.ollama import OllamaProvider
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.providers.openai_responses import OpenAIResponsesProvider
from tests.fakes import FakeOllama, FakeOpenAI


def _preview_request(*, stream: bool = False) -> ChatRequest:
    style = PersonaStyle(preset="dry_wit", depth="brief", humor="playful")
    plan = contextualize_persona(resolve_persona(agent_override=style), PREVIEW_PROMPT)
    return ChatRequest(model="fixture-model", messages=preview_messages(plan), max_tokens=128,
                       num_ctx=4096, stream=stream, capture_adapter_receipt=True)


def _assert_safe_receipt(request: ChatRequest, *, adapter: str, cap: int | None, cap_field: str | None,
                         stream: bool) -> None:
    receipt = request.adapter_receipt
    assert receipt == {
        "adapter": adapter,
        "model": "fixture-model",
        "stream": stream,
        "output_token_cap": cap,
        "output_cap_field": cap_field,
        "message_count": 2,
        "message_roles": ["system", "user"],
        "system_instructions_present": True,
        "tool_schema_count": 0,
        "structured_output": False,
    }
    encoded = json.dumps(receipt)
    assert PREVIEW_PROMPT not in encoded
    assert "houseplants" not in encoded and "Response style chosen" not in encoded
    assert "authorization" not in encoded and "endpoint" not in encoded and "account" not in encoded


def _style_in_messages(messages) -> None:
    assert messages[0]["role"] == "system"
    assert "Response style chosen for this run" in messages[0]["content"]
    assert "Playful wording is allowed when this turn is clearly playful and low-stakes" in messages[0]["content"]
    assert messages[-1]["content"] == PREVIEW_PROMPT


def test_ollama_receipt_is_derived_from_native_serialized_request():
    server = FakeOllama({"fixture-model": {}})
    try:
        request = _preview_request()
        OllamaProvider(server.url).chat(request)
        sent = server.of("/api/chat")[0]["body"]
        _style_in_messages(sent["messages"])
        assert sent["options"]["num_predict"] == 128 and sent["stream"] is False
        _assert_safe_receipt(request, adapter="ollama-native-chat", cap=128,
                             cap_field="options.num_predict", stream=False)
    finally:
        server.close()


def test_openai_compatible_receipt_uses_serialized_chat_completions_fields():
    server = FakeOpenAI()
    try:
        request = _preview_request()
        OpenAICompatProvider(server.url + "/v1", "fixture-key", "openai-compatible").chat(request)
        sent = server.of("/v1/chat/completions")[0]["body"]
        _style_in_messages(sent["messages"])
        assert sent["max_tokens"] == 128 and sent["stream"] is False
        _assert_safe_receipt(request, adapter="openai-chat-completions", cap=128,
                             cap_field="max_tokens", stream=False)
    finally:
        server.close()


def test_official_openai_receipt_names_the_completion_cap_field():
    request = _preview_request()
    provider = OpenAICompatProvider("https://api.openai.com/v1", "fixture-key", "openai")
    body = provider._body(request, stream=False)
    record_adapter_receipt(request, "openai-chat-completions", body, stream=False)
    assert body["max_completion_tokens"] == 128
    _assert_safe_receipt(request, adapter="openai-chat-completions", cap=128,
                         cap_field="max_completion_tokens", stream=False)


def test_openai_responses_receipt_reports_the_missing_output_cap_honestly():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["instructions"].startswith("You are answering a fixed, fictional sample")
        assert "Response style chosen for this run" in body["instructions"]
        assert body["input"] == [{"role": "user", "content": PREVIEW_PROMPT}]
        return httpx.Response(200, text=(
            'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
            'data: {"type":"response.completed","response":{"status":"completed",'
            '"model":"fixture-model","output":[],"usage":{"input_tokens":2,"output_tokens":1}}}\n\n'
        ), headers={"content-type": "text/event-stream"})

    request = _preview_request(stream=True)
    OpenAIResponsesProvider("fixture-access", transport=httpx.MockTransport(handler)).chat(request)
    assert len(requests) == 1 and "max_output_tokens" not in requests[0]
    _assert_safe_receipt(request, adapter="openai-responses", cap=None, cap_field=None, stream=True)


def test_anthropic_receipt_uses_sdk_message_arguments_without_credentials(monkeypatch):
    import hutch.providers.claude as claude_module

    class Messages:
        kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="ok")],
                usage=SimpleNamespace(input_tokens=2, output_tokens=1),
                stop_reason="end_turn", model="fixture-model",
            )

    client = SimpleNamespace(messages=Messages())
    monkeypatch.setattr(claude_module, "_sdk", lambda: SimpleNamespace(Timeout=lambda *a, **kw: "fixture"))
    provider = ClaudeProvider(api_key="secret-fixture-key", base_url="https://api.anthropic.com")
    monkeypatch.setattr(provider, "_c", lambda: client)
    request = _preview_request()
    provider.chat(request)
    sent = client.messages.kwargs
    assert sent["system"].startswith("You are answering a fixed, fictional sample")
    assert "Response style chosen for this run" in sent["system"]
    assert sent["messages"][-1]["content"] == PREVIEW_PROMPT
    assert sent["max_tokens"] == 128
    _assert_safe_receipt(request, adapter="anthropic-messages", cap=128,
                         cap_field="max_tokens", stream=False)


def test_adapter_receipt_capture_is_opt_in():
    request = ChatRequest(model="fixture-model", messages=[{"role": "user", "content": "private message"}])
    record_adapter_receipt(request, "openai-chat-completions", {
        "model": "fixture-model", "messages": request.messages, "authorization": "secret-token",
        "endpoint": "https://private.example/", "max_tokens": 8,
    }, stream=False)
    assert request.adapter_receipt is None
