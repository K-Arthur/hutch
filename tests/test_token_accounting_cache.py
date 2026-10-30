"""Equivalence and bound tests for transcript token-accounting caches (perf D6-B).

The cached functions must return exactly the previous formulas; the cache is only a
performance mechanism. Reference implementations below are the pre-cache code, kept here
so a future change to either formula fails loudly instead of silently drifting.
"""

from __future__ import annotations

import json
import math
import random
import threading

from hutch.context import (
    IMAGE_TOKEN_ESTIMATE,
    PER_MESSAGE_OVERHEAD,
    _content_tokens,
    clear_token_caches,
    estimate_tokens,
    prompt_tokens,
)
from hutch.runtime.fitloop import _message_tokens as fitloop_message_tokens
from hutch.runtime.fitloop import count_tokens
from hutch.token_cache import MessageTokenCache, SequenceTokenCache


def _ref_prompt_tokens(messages, tools):
    msg = sum(_content_tokens(m.get("content")) + PER_MESSAGE_OVERHEAD
              + sum(estimate_tokens(json.dumps(tc)) for tc in (m.get("tool_calls") or []))
              for m in messages)
    tool = estimate_tokens(json.dumps(tools, separators=(",", ":"))) if tools else 0
    return msg, tool


def _ref_count_tokens(messages, tool_tokens=0):
    total = 0
    for message in messages:
        text = str(message.get("content") or "")
        tokens = int(math.ceil(len(text) / 3.2)) + 6
        for call in message.get("tool_calls") or []:
            tokens += int(math.ceil(len(json.dumps(call, separators=(",", ":"))) / 3.2))
        total += tokens
    return total + tool_tokens


def _corpus(seed: int = 7, length: int = 120):
    rng = random.Random(seed)
    messages = []
    for index in range(length):
        role = ("system", "user", "assistant", "tool")[index % 4]
        kind = index % 6
        if kind == 0:
            content = None
        elif kind == 1:
            content = "x" * rng.randint(0, 400)
        elif kind == 2:
            content = [{"type": "text", "text": "hello " * rng.randint(0, 40)},
                       {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
        elif kind == 3:
            content = [{"type": "custom", "value": {"nested": [1, 2, 3]}}]
        elif kind == 4:
            content = {"structured": True, "items": list(range(rng.randint(0, 8)))}
        else:
            content = "short reply"
        message = {"role": role, "content": content}
        if role == "assistant" and rng.random() < 0.7:
            message["tool_calls"] = [
                {"id": f"call_{index}_{n}", "type": "function",
                 "function": {"name": "shell", "arguments": json.dumps({"command": f"ls {n}", "pad": "y" * n})}}
                for n in range(rng.randint(1, 3))
            ]
        if rng.random() < 0.1:
            message["images"] = ["frame-1"]
        messages.append(message)
    return messages


def _tools():
    return [{"type": "function", "function": {"name": f"tool_{n}",
                                             "description": "d" * (n * 7),
                                             "parameters": {"type": "object",
                                                            "properties": {"a": {"type": "string"}}}}}
            for n in range(6)]


def test_prompt_tokens_is_identical_to_the_reference_formula():
    for seed in (1, 2, 3, 7, 11):
        messages = _corpus(seed, length=150)
        tools = _tools()
        assert prompt_tokens(messages, tools) == _ref_prompt_tokens(messages, tools)
        assert prompt_tokens(messages, []) == _ref_prompt_tokens(messages, [])
    assert prompt_tokens([], []) == (0, 0)


def test_count_tokens_is_identical_to_the_reference_formula():
    for seed in (1, 2, 3, 7, 11):
        messages = _corpus(seed, length=150)
        assert count_tokens(messages) == _ref_count_tokens(messages)
        assert count_tokens(messages, tool_tokens=123) == _ref_count_tokens(messages, 123)
    assert count_tokens([]) == 0


def test_repeated_counts_reuse_cached_estimates():
    clear_token_caches()
    messages = _corpus(length=80)
    tools = _tools()
    first = prompt_tokens(messages, tools)
    for _ in range(5):
        assert prompt_tokens(messages, tools) == first
    assert fitloop_message_tokens(messages[0]) == _ref_count_tokens(messages[:1])
    for _ in range(5):
        count_tokens(messages)
    from hutch import context as context_module
    assert context_module._MESSAGE_TOKENS.info()["hits"] >= 5 * len(messages)
    assert context_module._MESSAGE_TOKENS.info()["misses"] <= len(messages)


def test_replacing_a_message_content_invalidates_only_that_estimate():
    clear_token_caches()
    messages = _corpus(length=10)
    before = prompt_tokens(messages, [])
    messages[3]["content"] = "a much longer replacement content " * 20
    after = prompt_tokens(messages, [])
    assert after == _ref_prompt_tokens(messages, [])
    assert after != before


def test_non_formula_metadata_does_not_invalidate_an_estimate():
    clear_token_caches()
    messages = _corpus(length=6)
    first = prompt_tokens(messages, [])
    messages[0]["images"] = ["frame-9"]
    messages[1]["computer_observation"] = True
    assert prompt_tokens(messages, []) == first


def test_tool_definition_estimate_reuses_the_same_schema_objects():
    clear_token_caches()
    tools = _tools()
    first = prompt_tokens([], tools)
    assert prompt_tokens([], list(tools))[1] == first[1]
    from hutch import context as context_module
    assert context_module._TOOL_TOKENS.info()["hits"] >= 1


def test_caches_are_bounded_and_clearable():
    cache = MessageTokenCache(max_entries=8)
    for index in range(50):
        ref = {"n": index}
        assert cache.get(ref, ref, None, lambda ref=ref: ref["n"]) == index
    assert cache.info()["size"] <= 8
    sequence = SequenceTokenCache(max_entries=4)
    for index in range(20):
        ref = {"n": index}
        assert sequence.get((ref,), lambda ref=ref: ref["n"]) == index
    assert sequence.info()["size"] <= 4
    cache.clear()
    assert cache.info() == {"size": 0, "hits": 0, "misses": 0, "max_entries": 8}
    clear_token_caches()
    messages = [{"role": "user", "content": f"message {index}"} for index in range(5000)]
    prompt_tokens(messages, [])
    from hutch import context as context_module
    assert context_module._MESSAGE_TOKENS.info()["size"] <= context_module._MESSAGE_TOKENS.info()["max_entries"]


def test_cached_prompt_tokens_is_consistent_under_concurrent_reads():
    clear_token_caches()
    messages = _corpus(length=60)
    tools = _tools()
    expected = _ref_prompt_tokens(messages, tools)
    errors: list[BaseException] = []

    def worker():
        try:
            for _ in range(25):
                assert prompt_tokens(messages, tools) == expected
                assert count_tokens(messages) == _ref_count_tokens(messages)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors