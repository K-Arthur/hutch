"""Structured causes for a tool-bench trial.

Kept apart from the bench runner so a failure can be named without reading a wall of judge prose.
The classes come from real failures recorded in Phase 5: a missing llama.cpp call id, an LM Studio
reasoning-only turn, and a llama.cpp parser that left a complete call body in ``content`` with no
``tool_calls`` at all.
"""

from __future__ import annotations

import json

from .providers.base import ChatResult

_CALL_MARKERS = ("<tool_call", "<|tool_call", "[TOOL_REQUEST]", "<function=")


def looks_like_call(text: str) -> bool:
    """Call-shaped text left in content by a parser that could not turn it into a call.

    Observed live on llama.cpp b12144 with qwen2.5-coder-3b: ``finish_reason: stop``,
    ``tool_calls: null`` and the exact body ``{"name": "read_file", "arguments": {...}}``
    in ``content``. That is a template/parser failure, not a prose answer.
    """
    low = text.lower()
    if any(marker.lower() in low for marker in _CALL_MARKERS):
        return True
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        body = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(body, dict) and "arguments" in body and ("name" in body or "function" in body)


def _protocol_observations(res: ChatResult) -> list[str]:
    """Protocol facts visible even when a call passed: ids, parallelism, reasoning-only."""
    found: list[str] = []
    ids = [tc.id for tc in res.tool_calls]
    if any(not call_id for call_id in ids):
        found.append("missing_id")
    present = [call_id for call_id in ids if call_id]
    if len(present) != len(set(present)):
        found.append("duplicate_id")
    if len(ids) > 1:
        found.append("parallel_calls")
    if not ids and not res.content.strip() and res.thinking.strip():
        found.append("reasoning_only")
    if not ids and looks_like_call(res.content):
        found.append("call_in_content")
    return found


def _failure_cause(res: ChatResult, *, expected_tool: str, expects_call: bool, why: str) -> str:
    """One structured cause for a failed trial, from the result shape and the judge's words."""
    if not expects_call and res.tool_calls:
        return "unexpected_call"
    if res.tool_calls:
        if len(res.tool_calls) > 1:
            return "multiple_calls"
        call = res.tool_calls[0]
        if call.parse_error:
            return "parse_error"
        if expected_tool and call.name != expected_tool:
            return "wrong_tool"
        if why.startswith("arguments do not match"):
            return "schema"
        return "wrong_arguments"
    if res.thinking.strip() and not res.content.strip():
        return "reasoning_only"
    if not res.content.strip():
        return "empty_answer"
    if looks_like_call(res.content):
        return "call_in_content"
    if "ignored the tool result" in why:
        return "ignored_result"
    if why.startswith("did not answer"):
        return "wrong_answer"
    return "no_call"


def classify_call(res: ChatResult, *, expected_tool: str = "", expects_call: bool = True,
                  repaired: bool = True, why: str = "") -> tuple[str, list[str]]:
    """(primary failure cause, every cause observed in this trial).

    Observations count even when the trial passed, so a missing id or a reasoning-only turn is
    visible without pretending it failed. The primary cause is empty for a passed trial.
    """
    causes = _protocol_observations(res)
    if why == "needed type repair":
        causes.append("type_repair")
    if repaired:
        return "", causes
    primary = _failure_cause(res, expected_tool=expected_tool, expects_call=expects_call, why=why)
    if primary not in causes:
        causes.append(primary)
    return primary, causes
