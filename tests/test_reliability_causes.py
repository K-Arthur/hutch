"""Tool-bench causes: a failure that cannot be named cannot be fixed or disclosed.

Each case corresponds to a real class in the Phase 5 research: missing llama.cpp ids,
LM Studio reasoning-only turns, calls left as parser text, wrong templates and argument
shape failures. These are pure classifications over captured result shapes.
"""

from __future__ import annotations

import json

from hutch.providers.base import ChatResult, ToolCall
from hutch.reliability import Judgement, ProbeResult, Profile, _verdict, classify_trial, probes


def _probe(probe_id: str):
    return next(p for p in probes() if p.id == probe_id)


def _call(name: str = "read_file", *, call_id: str = "call_1", arguments=None,
          parse_error: str = "") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments or {"path": "notes.txt"},
                    parse_error=parse_error)


def test_missing_id_is_visible_even_when_the_call_passed():
    probe = _probe("call_shape")
    result = ChatResult(content="", tool_calls=[_call(call_id="")])
    primary, causes = classify_trial(result, probe, Judgement(True, True))
    assert primary == ""
    assert "missing_id" in causes


def test_duplicate_ids_and_parallel_calls_are_counted():
    probe = _probe("call_shape")
    result = ChatResult(tool_calls=[_call(call_id="same"), _call(call_id="same")])
    primary, causes = classify_trial(result, probe, Judgement(False, False, "made 2 calls where one was asked for"))
    assert primary == "multiple_calls"
    assert {"duplicate_id", "parallel_calls", "multiple_calls"} <= set(causes)


def test_reasoning_only_is_not_an_empty_answer():
    probe = _probe("call_shape")
    result = ChatResult(content="", thinking="I should call read_file with path notes.txt")
    primary, causes = classify_trial(result, probe, Judgement(False, False, "returned nothing"))
    assert primary == "reasoning_only"
    assert "reasoning_only" in causes and "empty_answer" not in causes


def test_call_shaped_text_is_kept_distinct_from_a_prose_answer():
    probe = _probe("call_shape")
    result = ChatResult(content='<tool_call>{"name":"read_file","arguments":{"path":"notes.txt"}}</tool_call>')
    primary, causes = classify_trial(result, probe, Judgement(False, False, "answered in prose instead of calling the tool"))
    assert primary == "call_in_content"
    assert "call_in_content" in causes


def test_a_bare_json_call_left_in_content_is_not_prose():
    """Captured live from llama.cpp b12144 + qwen2.5-coder-3b: finish stop, no tool_calls."""
    probe = _probe("call_shape")
    captured = '{"name": "read_file", "arguments": {"path": "notes.txt"}}'
    primary, causes = classify_trial(ChatResult(content=captured), probe,
                                     Judgement(False, False, "answered in prose instead of calling the tool"))
    assert primary == "call_in_content"
    assert "call_in_content" in causes

    fenced = "```json\n" + captured + "\n```"
    assert classify_trial(
        ChatResult(content=fenced), probe,
        Judgement(False, False, "answered in prose instead of calling the tool"))[0] == "call_in_content"


def test_a_plain_prose_answer_has_no_protocol_cause():
    probe = _probe("call_shape")
    result = ChatResult(content="notes.txt says the meeting moved.")
    primary, causes = classify_trial(result, probe, Judgement(False, False, "answered in prose instead of calling the tool"))
    assert primary == "no_call"
    assert causes == ["no_call"]


def test_parse_error_wrong_tool_and_schema_are_distinct():
    probe = _probe("call_shape")
    parsed = classify_trial(ChatResult(tool_calls=[_call(parse_error="bad json")]), probe,
                            Judgement(False, False, "arguments were not valid JSON (bad json)"))
    assert parsed[0] == "parse_error"

    wrong = classify_trial(ChatResult(tool_calls=[_call(name="write_file")]), probe,
                           Judgement(False, False, "called 'write_file' instead of 'read_file'"))
    assert wrong[0] == "wrong_tool"

    schema = classify_trial(ChatResult(tool_calls=[_call(arguments={})]), probe,
                            Judgement(False, False, "arguments do not match the tool's schema: path is required"))
    assert schema[0] == "schema"


def test_an_unexpected_call_is_named_for_restraint_probes():
    probe = _probe("restraint")
    result = ChatResult(tool_calls=[_call(name="read_file")])
    primary, causes = classify_trial(result, probe,
                                     Judgement(False, False, "called 'read_file' for a question that needs no tool"))
    assert primary == "unexpected_call"
    assert "unexpected_call" in causes


def test_type_repair_is_recorded_without_failing_the_trial():
    probe = _probe("arg_types")
    result = ChatResult(tool_calls=[_call(name="add_item", arguments={"name": "banana", "quantity": 3, "urgent": True})])
    primary, causes = classify_trial(result, probe, Judgement(False, True, "needed type repair"))
    assert primary == ""
    assert "type_repair" in causes


def test_old_profiles_without_causes_still_load():
    old = {"model": "ollama/qwen3:4b", "quant": "Q4_K_M", "runtime": "ollama", "template_hash": "",
           "digest": "", "num_ctx": 8192, "hardware": "", "measured_at": "2026-11-06T00:00:00Z",
           "probes": [{"id": "call_shape", "title": "Forms a valid tool call", "trials": 3,
                       "raw": 2, "repaired": 3, "errors": 0, "detail": "", "median_ms": 12.0}],
           "tokens_per_sec": None, "load_ms": None, "verdict": "reliable", "summary": ""}
    profile = Profile.from_json(json.dumps(old))
    assert profile.probes[0].causes == {}


def test_a_profile_reports_protocol_causes_in_its_summary():
    probe = _probe("call_shape")
    result = ChatResult(tool_calls=[_call(call_id="")])
    _, causes = classify_trial(result, probe, Judgement(True, True))
    probe_result = ProbeResult("call_shape", "Forms a valid tool call", 3, raw=3, repaired=3,
                               causes=dict.fromkeys(causes, 3))
    verdict, summary = _verdict([probe_result], None)
    assert verdict == "reliable"
    assert "3 call(s) had no id" in summary
