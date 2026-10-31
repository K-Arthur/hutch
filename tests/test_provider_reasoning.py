"""Reasoning text and the honest accounting around it.

Grounded in a real reply from the owner's Xiaomi Token Plan route (mimo-v2.6-flash, 2026-10-31), which
returns its thinking in ``reasoning_content`` while ``content`` carries only the answer:

    {"message": {"content": "HUTCH_LIVE_OK",
                 "reasoning_content": "The user is asking me to say ...",
                 "role": "assistant", "tool_calls": []},
     "usage": {"completion_tokens": 32, "prompt_tokens": 15,
               "completion_tokens_details": {"reasoning_tokens": 25}}}

Those tokens are billed. Dropping the text hides both the charge and why a small output cap can return
no visible answer at all.
"""

from __future__ import annotations

from hutch.providers.openai_result import build_result, reasoning_text


def test_reasoning_content_is_kept_rather_than_dropped():
    message = {"content": "HUTCH_LIVE_OK", "reasoning_content": "  thinking about it  "}
    assert reasoning_text(message) == "  thinking about it  "
    result = build_result("HUTCH_LIVE_OK", [], {"prompt_tokens": 15, "completion_tokens": 32}, "stop",
                          "mimo-v2.6-flash", provider_name="xiaomi", thinking=reasoning_text(message))
    assert result.content == "HUTCH_LIVE_OK"
    assert result.thinking == "  thinking about it  "


def test_a_generic_reasoning_field_is_accepted():
    assert reasoning_text({"reasoning": "why"}) == "why"
    assert reasoning_text({"reasoning_content": "", "reasoning": "why"}) == "why"
    assert reasoning_text({}) == ""
    assert reasoning_text({"reasoning_content": None}) == ""


def test_billed_reasoning_tokens_are_reported():
    usage = {"prompt_tokens": 15, "completion_tokens": 32,
             "completion_tokens_details": {"reasoning_tokens": 25}}
    result = build_result("HUTCH_LIVE_OK", [], usage, "stop", "mimo-v2.6-flash", provider_name="xiaomi")
    assert any("25 of 32 completion tokens as reasoning" in note for note in result.notes)


def test_an_answer_that_is_all_reasoning_says_so():
    """A capped request can spend every token thinking and return nothing visible."""
    usage = {"prompt_tokens": 22, "completion_tokens": 12,
             "completion_tokens_details": {"reasoning_tokens": 12}}
    result = build_result("", [], usage, "length", "mimo-v2.6-flash", provider_name="xiaomi")
    assert result.content == "" and result.finish_reason == "length"
    assert any("no visible answer" in note for note in result.notes)


def test_a_normal_answer_gains_no_reasoning_noise():
    result = build_result("hello", [], {"prompt_tokens": 3, "completion_tokens": 2}, "stop", "m", provider_name="p")
    assert result.notes == []


def test_missing_usage_is_never_reported_as_zero_cost():
    result = build_result("hello", [], {}, "stop", "m", provider_name="p")
    assert any("no token usage" in note for note in result.notes)
    assert result.prompt_tokens == 0 and result.completion_tokens == 0
