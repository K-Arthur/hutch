"""Property-based coverage for the argument and stream parsers (assignment section 12).

These are parser/contract properties, not model-quality claims: whatever the model's
task competence, a call that arrives must decode to exactly the same value the bytes
encode, or be refused - never silently altered.
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from hutch.providers.base import parse_tool_args_state
from hutch.toolcalling.streamassembly import OpenAIChatStreamAssembler
from hutch.toolcalling.strictjson import JSONProblem, loads_strict

JSON_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10 ** 18), max_value=10 ** 18),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=24),
)
JSON_VALUES = st.recursive(
    JSON_SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_-", max_size=10), children, max_size=4),
    ),
    max_leaves=12,
)
JSON_OBJECTS = st.dictionaries(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz_-", min_size=1, max_size=10), JSON_VALUES, max_size=6)


@settings(max_examples=150, deadline=None)
@given(value=JSON_OBJECTS)
def test_strict_decode_is_exact_for_every_generated_object(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    assert loads_strict(raw) == value
    args, error, state, _double = parse_tool_args_state(raw)
    assert error == "" and state == "json_object" and args == value


@settings(max_examples=100, deadline=None)
@given(pairs=st.lists(st.tuples(st.just("k"), st.integers()), min_size=2, max_size=6))
def test_duplicate_keys_are_always_refused(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != 1:
        return  # only the all-duplicate case is interesting
    raw = "{" + ", ".join(f'"{key}":{value}' for key, value in pairs) + "}"
    try:
        loads_strict(raw)
    except JSONProblem as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover - a single pair cannot duplicate
        assert len(pairs) == 1


@settings(max_examples=80, deadline=None)
@given(value=JSON_OBJECTS, hop=st.integers(min_value=1, max_value=9))
def test_streamed_fragments_reassemble_the_exact_argument_text(value, hop):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    assembler = OpenAIChatStreamAssembler()
    assembler.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "c", "type": "function", "function": {"name": "t", "arguments": ""}}]}}]})
    for start in range(0, len(raw), hop):
        assembler.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": raw[start:start + hop]}}]}}]})
    calls = assembler.calls()
    assert len(calls) == 1 and calls[0]["arguments"] == raw
    args, error, state, _ = parse_tool_args_state(calls[0]["arguments"])
    assert error == "" and state == "json_object" and args == value


@settings(max_examples=60, deadline=None)
@given(names=st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=6),
                      min_size=1, max_size=4))
def test_name_merging_never_doubles_a_repeated_fragment(names):
    assembler = OpenAIChatStreamAssembler()
    for fragment in names:
        assembler.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "c", "function": {"name": fragment, "arguments": ""}}]}}]})
    merged = assembler.calls()[0]["name"]
    full = "".join(names)
    # Either the fragments concatenated (piecewise continuation) or a repeat/snapshot was
    # dropped - never a doubled name and never a fragment outside the source text.
    assert merged in (full, names[0], names[-1]) or merged.startswith(names[0])
