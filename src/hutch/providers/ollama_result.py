"""Fold Ollama's native /api/chat chunks into Hutch's ChatResult.

Kept out of the transport module so the honesty rules - truncation detection and the
reasoning-budget note - stay testable without a server. Ollama reports thinking in
``message.thinking`` and a ``done_reason`` of ``length`` when the output cap stopped it.
"""

from __future__ import annotations

import json
from typing import Any

from .base import ChatRequest, ChatResult, ToolCall, parse_tool_args_state
from .ollama_extras import split_leaked_reasoning
from .openai_result import reasoning_budget_notes

#: A prompt that evaluated at this share of the requested window was almost certainly cut
#: from the front by the runtime; the top of the prompt is where the system text lives.
TRUNCATION_RATIO = 0.98


def fold_ollama_chunks(chunks: list[dict[str, Any]], req: ChatRequest, streamed: bool) -> ChatResult:
    content, thinking, calls = [], [], []
    for chunk in chunks:
        message = chunk.get("message") or {}
        if message.get("content"):
            content.append(message["content"])
        if message.get("thinking"):
            thinking.append(message["thinking"])
        for tool_call in message.get("tool_calls") or []:
            fn = tool_call.get("function", {})
            args, err, state, double = parse_tool_args_state(fn.get("arguments"))
            raw = fn.get("arguments") if isinstance(fn.get("arguments"), str) else (
                json.dumps(fn.get("arguments"), ensure_ascii=False) if fn.get("arguments") is not None else "")
            calls.append(ToolCall(id=tool_call.get("id") or "", name=fn.get("name", ""),
                                  arguments=args, raw=raw or "", parse_error=err,
                                  arguments_state=state, double_decoded=double))
    last = chunks[-1]
    prompt_tokens = int(last.get("prompt_eval_count") or 0)
    completion_tokens = int(last.get("eval_count") or 0)
    eval_ns = last.get("eval_duration") or 0
    split = split_leaked_reasoning("".join(content), "".join(thinking))
    result = ChatResult(
        content=split[0], thinking=split[1], tool_calls=calls, prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens, model=last.get("model", req.model), streamed=streamed,
        load_ms=(last.get("load_duration") or 0) / 1e6, total_ms=(last.get("total_duration") or 0) / 1e6,
        tokens_per_sec=(completion_tokens / (eval_ns / 1e9)) if eval_ns and completion_tokens else None,
        context_window=int(req.num_ctx or 0),
        finish_reason="tool_calls" if calls else ("length" if last.get("done_reason") == "length" else "stop"))
    result.notes.extend(reasoning_budget_notes(
        thinking=result.thinking, content=result.content, tool_calls=len(calls),
        completion_tokens=completion_tokens, reasoning_tokens=0, finish_reason=result.finish_reason))
    if req.num_ctx and prompt_tokens >= int(req.num_ctx * TRUNCATION_RATIO):
        result.prompt_truncated = True
        result.notes.append(f"prompt evaluated {prompt_tokens} tokens against a {req.num_ctx}-token window: "
                            "it was almost certainly truncated from the front")
    return result
