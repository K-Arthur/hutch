"""Turning an OpenAI-shaped completion into Hutch's ChatResult.

Kept apart from the transport adapter because this is where the honesty rules live, and they are easier
to read - and to test - on their own:

* a truncated stream or a capped answer is reported as ``length`` even when tool calls are present;
* a provider that reports no usage gets a note saying the counts are estimates, rather than a silent zero;
* reasoning text some servers return alongside the answer is kept, not discarded. Those tokens are billed,
  so dropping them would hide both the cost and the reason a short cap produced no visible answer.
"""

from __future__ import annotations

import math
from typing import Any

from .base import ChatResult, ToolCall

#: Field names seen in the wild for a model's thinking alongside its answer.
REASONING_FIELDS = ("reasoning_content", "reasoning")


def reasoning_text(message: dict[str, Any]) -> str:
    """The model's reasoning text, from the first known field that carries a non-empty string."""
    for field_name in REASONING_FIELDS:
        value = message.get(field_name)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def reasoning_budget_notes(*, thinking: str, content: str, tool_calls: int, completion_tokens: int,
                           reasoning_tokens: int, finish_reason: str) -> list[str]:
    """Honest notes for a turn whose output budget went to reasoning.

    ``finish_reason == "length"`` is the stronger fact: the server stopped at the cap, not because
    the model had finished. A turn with visible content or a tool call is not this state.
    """
    notes: list[str] = []
    if reasoning_tokens > 0:
        notes.append(f"the provider billed {reasoning_tokens} of {completion_tokens} completion tokens "
                     "as reasoning")
    if content.strip() or tool_calls or not (thinking.strip() or reasoning_tokens > 0):
        return notes
    if finish_reason == "length":
        notes.append("the output limit was reached while the model was reasoning; it returned no visible "
                     "answer. Raise the output limit or ask for a shorter answer")
    else:
        notes.append("the model returned no visible answer; raise the output limit or ask for a shorter answer")
    return notes


def build_result(content: str, tcs: list[ToolCall], usage: dict[str, Any], finish: str, model: str,
                 *, provider_name: str, num_ctx: int = 0, streamed: bool = True,
                 thinking: str = "") -> ChatResult:
    details = usage.get("prompt_tokens_details") or {}
    # Truncation is the stronger fact: a partially streamed tool call must never be reported as complete.
    reason = "length" if finish == "length" else ("tool_calls" if tcs else "stop")
    reported = None
    raw_cost = usage.get("cost")
    if raw_cost is not None and not isinstance(raw_cost, bool):
        try:
            candidate = float(raw_cost)
            if math.isfinite(candidate) and candidate >= 0:
                reported = candidate
        except (TypeError, ValueError, OverflowError):
            reported = None
    completion_tokens = int(usage.get("completion_tokens") or 0)
    res = ChatResult(content=content, tool_calls=tcs, prompt_tokens=int(usage.get("prompt_tokens") or 0),
                     completion_tokens=completion_tokens,
                     cached_tokens=int(details.get("cached_tokens") or 0), finish_reason=reason, model=model,
                     streamed=streamed, context_window=int(num_ctx or 0), reported_cost_usd=reported,
                     thinking=thinking)
    if reported is not None:
        res.notes.append("the provider reported this call's charge (usage.cost)")
    if not usage:
        res.notes.append("the server reported no token usage; counts are estimates")
    raw_reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    reasoning_tokens = (raw_reasoning_tokens if isinstance(raw_reasoning_tokens, int)
                        and not isinstance(raw_reasoning_tokens, bool) and raw_reasoning_tokens > 0 else 0)
    res.notes.extend(reasoning_budget_notes(
        thinking=thinking, content=content, tool_calls=len(tcs), completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens, finish_reason=reason))
    return res
