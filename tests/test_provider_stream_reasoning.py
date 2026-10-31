"""Reasoning text on the streamed path must match the batch path.

Live evidence (2026-10-31, mimo-v2.6-flash on the owner's Token Plan route): the provider sends
``delta.reasoning_content`` in the SSE stream, and a raw wire probe counted 7 reasoning deltas /
50 characters for a one-word answer. Hutch's stream assembler kept only ``content``, so the same
request reported thinking on the batch path and none on the streamed one - while the usage note
still said the provider billed reasoning tokens.

These tests pin the two paths together. The streamed chunk shapes below come from that probe.
"""

from __future__ import annotations

import json

import httpx

from hutch.providers.base import ChatRequest
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.providers.openai_result import REASONING_FIELDS
from hutch.toolcalling.streamassembly import (REASONING_DELTA_FIELDS, OpenAIChatStreamAssembler)

USAGE = {"prompt_tokens": 14, "completion_tokens": 19,
         "completion_tokens_details": {"reasoning_tokens": 15}}


def sse(*chunks: dict) -> bytes:
    lines = [f"data: {json.dumps(chunk)}\n\n" for chunk in chunks]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def streamed_provider(payload: bytes) -> OpenAICompatProvider:
    """A provider whose real client talks to a fixed SSE body."""
    provider = OpenAICompatProvider("https://example.invalid/v1", "k", "mimo")
    provider._client = httpx.Client(base_url="https://example.invalid/v1",
                                    transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)))
    return provider


def test_the_reasoning_field_lists_cannot_drift_apart():
    assert REASONING_DELTA_FIELDS == REASONING_FIELDS


def test_the_assembler_collects_reasoning_deltas_in_arrival_order():
    assembler = OpenAIChatStreamAssembler()
    assembler.feed({"choices": [{"delta": {"role": "assistant", "reasoning_content": "The user wants"}}]})
    assembler.feed({"choices": [{"delta": {"reasoning_content": " the word"}}]})
    assembler.feed({"choices": [{"delta": {"content": "lantern"}}]})
    assembler.feed({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": USAGE})
    assert assembler.reasoning == "The user wants the word"
    assert assembler.content == "lantern"


def test_the_alternative_reasoning_field_is_accepted_on_streams():
    assembler = OpenAIChatStreamAssembler()
    assembler.feed({"choices": [{"delta": {"reasoning": "thinking"}}]})
    assembler.feed({"choices": [{"delta": {"reasoning_content": " thinking"}}]})
    assert assembler.reasoning == "thinking thinking"


def test_a_streamed_call_returns_the_same_thinking_the_batch_parser_would():
    payload = sse(
        {"model": "mimo-v2.6-flash", "choices": [{"delta": {"role": "assistant",
                                                            "reasoning_content": "The user wants me"}}]},
        {"model": "mimo-v2.6-flash", "choices": [{"delta": {"reasoning_content": " to say a word"}}]},
        {"model": "mimo-v2.6-flash", "choices": [{"delta": {"content": "lantern"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        {"choices": [], "usage": USAGE},
    )
    result = streamed_provider(payload).chat(
        ChatRequest(model="mimo-v2.6-flash", messages=[{"role": "user", "content": "Say: lantern"}],
                    stream=True, max_tokens=64))
    assert result.streamed is True
    assert result.content == "lantern"
    assert result.thinking == "The user wants me to say a word"
    assert any("billed 15 of 19 completion tokens as reasoning" in note for note in result.notes)


def test_a_reasoning_only_stream_is_reported_as_no_visible_answer():
    """A low cap can spend every token thinking. That is not a completed answer, and not an error."""
    payload = sse(
        {"model": "mimo-v2.6-flash", "choices": [{"delta": {"role": "assistant",
                                                            "reasoning_content": "thinking hard"}}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
        {"choices": [], "usage": {"prompt_tokens": 15, "completion_tokens": 12,
                                  "completion_tokens_details": {"reasoning_tokens": 11}}},
    )
    result = streamed_provider(payload).chat(
        ChatRequest(model="mimo-v2.6-flash", messages=[{"role": "user", "content": "Say: lantern"}],
                    stream=True, max_tokens=12))
    assert result.content == ""
    assert result.thinking == "thinking hard"
    assert result.finish_reason == "length"
    assert any("no visible answer" in note for note in result.notes)
