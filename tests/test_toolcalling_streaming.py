"""Streaming assembly and native response-shape tolerance.

Corpus-level contract tests (vLLM #39380 numeric corruption class, llama.cpp flat
tool-call shape, missing call ids, duplicate events). These are parser/contract
tests, not live-model reproductions.
"""

from __future__ import annotations

import json

import pytest

from hutch.providers.base import parse_tool_args_state
from hutch.providers.openai_compat import OpenAICompatProvider
from hutch.providers.base import ChatRequest
from hutch.toolcalling.streamassembly import (OpenAIChatStreamAssembler, StreamAssemblyError,
                                              should_reject_empty_stream)
from tests.fakes import FakeOpenAI


@pytest.fixture()
def oai():
    server = FakeOpenAI()
    yield server
    server.close()

CORPUS = [
    '{"path": "a.txt"}',
    '{"text": "brace } and quote \\" and backslash \\\\ inside"}',
    '{"n": -1.25e-3, "big": 9007199254740993, "s": "h\u00e9llo \u2603 \\u2603"}',
    '{"a": 0.45, "b": 1.1, "c": 0.92, "d": 3000}',
    '{"nested": {"arr": [1, {"x": "}"}], "empty": {}, "null": null}}',
    '{"scientific": 6.02e23, "neg": -0.0, "escaped": "line\\nbreak"}',
    '{}',
]


def stream_one(raw: str, *, step: int = 1, name: str = "read_file", call_id: str = "c1"):
    asm = OpenAIChatStreamAssembler()
    asm.feed({"model": "m", "choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": call_id, "type": "function", "function": {"name": name, "arguments": ""}}]}}]})
    for start in range(0, len(raw), step):
        asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": raw[start:start + step]}}]}}]})
    asm.feed({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    asm.feed({"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 2}})
    return asm


@pytest.mark.parametrize("raw", CORPUS)
def test_argument_fragments_reassemble_exactly_at_every_split_point(raw):
    for step in (1, 2, 3, 5, 7, len(raw) or 1):
        calls = stream_one(raw, step=step).calls()
        assert len(calls) == 1
        assert calls[0]["arguments"] == raw, f"split step {step} changed the argument text"
        args, err, state, _ = parse_tool_args_state(calls[0]["arguments"])
        assert err == "" and state == "json_object"
        assert args == json.loads(raw)


def test_numbers_are_never_reformatted_by_the_client():
    raw = '{"decimal": 0.45, "neg": -1.1, "exp": 1e-7, "big": 123456789012345678901234567890}'
    asm = stream_one(raw, step=1)
    assert asm.calls()[0]["arguments"] == raw          # exact text, not a re-encoding
    args = json.loads(asm.calls()[0]["arguments"])
    assert args["decimal"] == 0.45 and args["exp"] == 1e-7
    assert args["big"] == 123456789012345678901234567890


def test_interleaved_calls_assemble_by_index():
    asm = OpenAIChatStreamAssembler()
    asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "a", "function": {"name": "read", "arguments": '{"p'}},
        {"index": 1, "id": "b", "function": {"name": "write", "arguments": '{"q'}}]}}]})
    asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 1, "function": {"arguments": '": 1}'}},
        {"index": 0, "function": {"arguments": '": 2}'}}]}}]})
    asm.feed({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    calls = asm.calls()
    assert [(c["id"], c["name"], c["arguments"]) for c in calls] == [
        ("a", "read", '{"p": 2}'), ("b", "write", '{"q": 1}')]


@pytest.mark.parametrize(("fragments", "expected"), [
    (["read_file", "read_file"], "read_file"),                      # repeated chunk
    (["read_", "file"], "read_file"),                               # piecewise
    (["read", "read_file"], "read_file"),                           # cumulative snapshot
    (["read_file", "file"], "read_file"),                           # re-sent tail
    (["", "read_file", ""], "read_file"),
])
def test_name_merging_handles_repeats_and_cumulative_snapshots(fragments, expected):
    asm = OpenAIChatStreamAssembler()
    for fragment in fragments:
        asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "c", "function": {"name": fragment, "arguments": ""}}]}}]})
    assert asm.calls()[0]["name"] == expected


def test_missing_index_continues_the_call_but_a_new_id_starts_one():
    asm = OpenAIChatStreamAssembler()
    asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"id": "a", "function": {"name": "read_file", "arguments": '{"p'}}]}}]})
    asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"function": {"arguments": 'ath": "x"}'}}]}}]})
    asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"id": "b", "function": {"name": "write_file", "arguments": "{}"}}]}}]})
    calls = asm.calls()
    assert len(calls) == 2
    assert calls[0]["name"] == "read_file" and calls[0]["arguments"] == '{"path": "x"}'
    assert calls[1]["name"] == "write_file" and calls[1]["id"] == "b"


def test_conflicting_ids_are_reported_and_the_first_is_kept():
    asm = OpenAIChatStreamAssembler()
    asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "first", "function": {"name": "t", "arguments": ""}}]}}]})
    asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "second", "function": {"arguments": "{}"}}]}}]})
    assert asm.calls()[0]["id"] == "first"
    assert any("two different ids" in note for note in asm.notes)


def test_bounds_and_malformed_chunks_raise_instead_of_growing():
    asm = OpenAIChatStreamAssembler(max_argument_bytes=32)
    asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "c", "function": {"name": "t", "arguments": "x" * 20}}]}}]})
    with pytest.raises(StreamAssemblyError, match="exceeded"):
        asm.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": "y" * 20}}]}}]})
    for bad in ("not a dict", 42, ["choices"]):
        with pytest.raises(StreamAssemblyError):
            OpenAIChatStreamAssembler().feed(bad)
    with pytest.raises(StreamAssemblyError):
        OpenAIChatStreamAssembler().feed({"choices": [{"delta": {"tool_calls": [{"index": 0,
                                                                                "function": {"arguments": 5}}]}}]})


def test_an_empty_stream_is_distinguishable_from_a_real_but_empty_answer():
    empty = OpenAIChatStreamAssembler()
    assert should_reject_empty_stream(empty) is True
    answered = OpenAIChatStreamAssembler()
    answered.feed({"choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "stop"}]})
    answered.mark_done()
    assert should_reject_empty_stream(answered) is False
    usage_only = OpenAIChatStreamAssembler()
    usage_only.feed({"choices": [], "usage": {"prompt_tokens": 1}})
    assert should_reject_empty_stream(usage_only) is False


def test_content_and_finish_are_tracked_from_the_delta_stream():
    asm = OpenAIChatStreamAssembler()
    asm.feed({"model": "m2", "choices": [{"index": 0, "delta": {"content": "he"}}]})
    asm.feed({"choices": [{"index": 0, "delta": {"content": "llo"}, "finish_reason": "length"}]})
    assert asm.content == "hello" and asm.finish == "length" and asm.model == "m2"


# ------------------------------------------------------------------ provider shapes

def req():
    return ChatRequest(model="m", messages=[{"role": "user", "content": "x"}], stream=False)


def test_full_response_accepts_the_flat_llamacpp_tool_call_shape():
    """llama.cpp's documented sample has name/arguments at top level, no function envelope."""
    payload = {"model": "m", "choices": [{"finish_reason": "tool", "message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"name": "read_file", "arguments": '{"path": "a.txt"}'}]}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4}}
    result = OpenAICompatProvider("http://localhost:8080/v1", "", "llamacpp")._from_full(payload, req())
    assert result.finish_reason == "tool_calls"
    call = result.tool_calls[0]
    assert call.name == "read_file" and call.arguments == {"path": "a.txt"} and call.id == ""


def test_full_response_reads_object_arguments_and_keeps_raw_text():
    payload = {"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
        {"id": "c9", "function": {"name": "read_file", "arguments": {"path": "b"}}}]}}]}
    result = OpenAICompatProvider("http://localhost:8080/v1", "", "llamacpp")._from_full(payload, req())
    call = result.tool_calls[0]
    assert call.id == "c9" and call.arguments == {"path": "b"} and json.loads(call.raw) == {"path": "b"}


def test_full_response_refusal_and_content_filter_are_typed_not_answers():
    from hutch.providers import ProviderError
    refusal = {"choices": [{"finish_reason": "stop", "message": {"content": None,
                                                                 "refusal": "I cannot help with that."}}]}
    with pytest.raises(ProviderError) as exc:
        OpenAICompatProvider("http://localhost:8080/v1", "", "llamacpp")._from_full(refusal, req())
    assert exc.value.kind == "refused"
    filtered = {"choices": [{"finish_reason": "content_filter", "message": {"content": ""}}]}
    with pytest.raises(ProviderError) as exc:
        OpenAICompatProvider("http://localhost:8080/v1", "", "llamacpp")._from_full(filtered, req())
    assert exc.value.kind == "refused"


def test_transcript_normalization_is_equivalent_streamed_and_not(oai):
    """The same provider script yields identical calls whether streamed or not."""
    from hutch.providers import ChatRequest as CR
    oai.script = lambda body: {"content": "", "tool_calls": [
        {"id": "c1", "name": "read_file", "arguments": '{"path": "a.txt", "n": 0.45}'}]}
    provider = OpenAICompatProvider(oai.url + "/v1", "k", "openai-compatible")
    streamed = provider.chat(CR(model="m", messages=[{"role": "user", "content": "go"}],
                                stream=True, num_ctx=None))
    plain = provider.chat(CR(model="m", messages=[{"role": "user", "content": "go"}],
                             stream=False, num_ctx=None))
    assert [c.name for c in streamed.tool_calls] == [c.name for c in plain.tool_calls] == ["read_file"]
    assert streamed.tool_calls[0].arguments == plain.tool_calls[0].arguments
    assert streamed.tool_calls[0].raw == plain.tool_calls[0].raw == '{"path": "a.txt", "n": 0.45}'
