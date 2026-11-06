"""A spent reasoning budget is a state with a cause, not an empty reply.

Real evidence: Ollama issue #17978 (qwen3-vl-thinking, eval_count == num_predict,
done_reason "length", message.content empty) and LM Studio qwen3-4b (64 completion tokens,
64 reasoning tokens, empty content).
"""

from __future__ import annotations

from hutch.providers.base import ChatRequest
from hutch.providers.ollama_result import fold_ollama_chunks
from hutch.providers.openai_result import build_result, reasoning_budget_notes


def test_length_with_reasoning_only_names_the_budget():
    notes = reasoning_budget_notes(thinking="thinking hard", content="", tool_calls=0,
                                   completion_tokens=64, reasoning_tokens=64, finish_reason="length")
    assert any("billed 64 of 64 completion tokens as reasoning" in n for n in notes)
    assert any("output limit was reached while the model was reasoning" in n for n in notes)
    assert any("no visible answer" in n for n in notes)


def test_a_visible_answer_is_not_reported_as_empty():
    notes = reasoning_budget_notes(thinking="thinking", content="lantern", tool_calls=0,
                                   completion_tokens=64, reasoning_tokens=40, finish_reason="stop")
    assert len(notes) == 1 and "as reasoning" in notes[0]


def test_a_tool_call_is_not_an_empty_answer():
    notes = reasoning_budget_notes(thinking="thinking", content="", tool_calls=1,
                                   completion_tokens=64, reasoning_tokens=40, finish_reason="tool_calls")
    assert len(notes) == 1 and "as reasoning" in notes[0]


def test_reasoning_without_reported_tokens_is_still_disclosed():
    notes = reasoning_budget_notes(thinking="I should call the tool", content="", tool_calls=0,
                                   completion_tokens=30, reasoning_tokens=0, finish_reason="stop")
    assert any("no visible answer" in n for n in notes)


def test_an_ordinary_empty_result_gains_no_reasoning_note():
    assert reasoning_budget_notes(thinking="", content="", tool_calls=0, completion_tokens=0,
                                  reasoning_tokens=0, finish_reason="stop") == []


def test_build_result_uses_the_shared_note_for_length():
    result = build_result("", [], {"prompt_tokens": 22, "completion_tokens": 12,
                                   "completion_tokens_details": {"reasoning_tokens": 12}},
                          "length", "m", provider_name="lmstudio", thinking="thinking")
    assert result.finish_reason == "length"
    assert any("output limit was reached" in note for note in result.notes)
    assert any("no visible answer" in note for note in result.notes)


def _chunk(*, content: str = "", thinking: str = "", done_reason: str = "stop",
           prompt: int = 20, eval_count: int = 10, done: bool = True) -> dict:
    return {"model": "qwen3:4b", "done": done, "done_reason": done_reason,
            "message": {"role": "assistant", "content": content, "thinking": thinking},
            "prompt_eval_count": prompt, "eval_count": eval_count,
            "eval_duration": 1_000_000_000, "total_duration": 1_200_000_000}


def test_native_ollama_reasoning_only_length_is_reported():
    result = fold_ollama_chunks([_chunk(thinking="re-evaluating the document", done_reason="length",
                                        eval_count=512)], ChatRequest(model="qwen3:4b", messages=[], num_ctx=4096),
                                streamed=True)
    assert result.content == ""
    assert result.finish_reason == "length"
    assert result.thinking == "re-evaluating the document"
    assert any("output limit was reached" in note for note in result.notes)


def test_native_ollama_normal_answer_keeps_thinking_without_an_empty_note():
    result = fold_ollama_chunks([_chunk(content="The cat is orange.", thinking="a cat photo")],
                                ChatRequest(model="qwen3:4b", messages=[], num_ctx=4096), streamed=True)
    assert result.content == "The cat is orange."
    assert result.thinking == "a cat photo"
    assert result.finish_reason == "stop"
    assert not any("no visible answer" in note for note in result.notes)


def test_native_ollama_truncation_and_usage_survive_the_extraction():
    result = fold_ollama_chunks([_chunk(content="ok", prompt=4090, eval_count=5)],
                                ChatRequest(model="qwen3:4b", messages=[], num_ctx=4096), streamed=True)
    assert result.prompt_truncated is True
    assert result.prompt_tokens == 4090 and result.completion_tokens == 5
    assert result.tokens_per_sec == 5.0
    assert result.load_ms == 0.0 and result.total_ms == 1200.0
