"""Unit-preserving, bounded compaction: pairing invariants, progress checks, attempt caps (LM-3)."""

from __future__ import annotations

from hutch.runtime.fitloop import (
    COMPACTED_CLOSE,
    COMPACTED_OPEN,
    Destination,
    count_tokens,
    fit_or_compact,
    split_units,
)


def _assistant_with_calls(*ids: str) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": i, "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"}} for i in ids]}


def test_units_keep_assistant_tool_calls_with_their_results():
    messages = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "do it"},
                _assistant_with_calls("a", "b"),
                {"role": "tool", "tool_call_id": "a", "content": "one"},
                {"role": "tool", "tool_call_id": "b", "content": "two"},
                {"role": "user", "content": "next"}]
    units = split_units(messages)
    assert [len(unit) for unit in units] == [1, 1, 3, 1]
    assert units[2][1]["tool_call_id"] == "a" and units[2][2]["tool_call_id"] == "b"


def test_orphan_tool_result_is_its_own_opaque_unit():
    messages = [{"role": "system", "content": "sys"},
                {"role": "tool", "tool_call_id": "missing", "content": "orphan"},
                {"role": "user", "content": "hi"}]
    assert [len(unit) for unit in split_units(messages)] == [1, 1, 1]


def test_cross_tool_result_after_another_message_is_not_absorbed():
    messages = [{"role": "assistant", "content": None, "tool_calls": [{"id": "a"}]},
                {"role": "user", "content": "interjection"},
                {"role": "tool", "tool_call_id": "a", "content": "late"}]
    units = split_units(messages)
    assert [unit[0]["role"] for unit in units] == ["assistant", "user", "tool"]


def test_a_fitting_request_is_untouched():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "short"}]
    result = fit_or_compact(messages, Destination("ollama", "m", window_tokens=8192, reserve_tokens=1024))
    assert result.status == "ok" and result.messages is messages


def test_an_unknown_window_is_reported_honestly_without_compacting():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "x" * 100_000}]
    calls: list[int] = []
    result = fit_or_compact(messages, Destination("openai", "m", window_tokens=0, reserve_tokens=100),
                            summarize=lambda units, destination: calls.append(1) or "summary")
    assert result.status == "unknown_window" and not calls


def test_overflow_without_a_summarizer_blocks_and_preserves_the_history():
    messages = [{"role": "system", "content": "sys"}] + \
               [{"role": "user", "content": "x" * 40_000} for _ in range(4)]
    result = fit_or_compact(messages, Destination("ollama", "m", window_tokens=8192, reserve_tokens=1024))
    assert result.status == "wont_fit" and result.messages is messages


def test_compaction_keeps_system_and_tail_units_byte_identical_and_bounds_the_block():
    system = {"role": "system", "content": "sys " + "s" * 200}
    middle = [{"role": "user", "content": f"middle turn {n} " + "m" * 20_000} for n in range(3)]
    tail = [{"role": "user", "content": "latest question"}, _assistant_with_calls("z"),
            {"role": "tool", "tool_call_id": "z", "content": "latest result"}]
    messages = [system, *middle, *tail]
    result = fit_or_compact(
        messages, Destination("ollama", "m", window_tokens=16_384, reserve_tokens=2048),
        summarize=lambda units, destination: "the task: keep the constraints; completed: steps 1-3")
    assert result.status == "compacted" and result.attempts == 1
    assert result.messages[0] is system
    assert result.messages[-3:] == tail                      # the whole latest unit, untouched
    synthetic = [m for m in result.messages if COMPACTED_OPEN in str(m.get("content", ""))]
    assert len(synthetic) == 1 and COMPACTED_CLOSE in synthetic[0]["content"]
    assert "not new instructions" in synthetic[0]["content"]
    assert result.actions and result.actions[0].first_unit == 1 and result.actions[0].last_unit == 4
    assert result.after_tokens < result.before_tokens


def test_a_nonshrinking_summary_is_rejected_within_the_bound():
    middle = [{"role": "user", "content": "m" * 6_000} for _ in range(4)]
    messages = [{"role": "system", "content": "sys"}, *middle, {"role": "user", "content": "t" * 100_000}]
    calls: list[int] = []

    def summarizer(units, destination):
        calls.append(1)
        return "n" * 30_000      # capped to the 8k synthetic-block bound: no real progress

    result = fit_or_compact(messages, Destination("ollama", "m", window_tokens=8192, reserve_tokens=512),
                            summarize=summarizer)
    assert result.status == "compact_failed"
    assert calls == [1]                                       # no-progress detection stops immediately
    assert result.messages is messages                        # the original history survives
    assert "real progress" in result.note


def test_an_impossible_fit_stops_after_the_bounded_attempts():
    messages = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "middle " + "m" * 40_000},
                {"role": "user", "content": "older " + "o" * 40_000},
                {"role": "user", "content": "tail " + "t" * 200_000}]
    calls: list[int] = []
    result = fit_or_compact(
        messages, Destination("ollama", "m", window_tokens=4096, reserve_tokens=256),
        summarize=lambda units, destination: calls.append(1) or "short summary")
    assert result.status == "compact_failed"
    assert len(calls) == 2 and result.attempts == 2           # bounded; no credit-consuming loop
    assert result.messages is messages
    assert "attempt budget" in result.note


def test_count_tokens_includes_tool_definitions():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert count_tokens(messages, 1_000) == count_tokens(messages) + 1_000
