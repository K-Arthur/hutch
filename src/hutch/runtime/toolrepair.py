"""Tool-call repair (LM-13) and the loop detector (SR-5).

Small local models fail at tool calling in a few well-documented ways: arguments that are not valid JSON,
double-encoded JSON, a number sent as a string, a missing required field, a made-up tool name, and - worst for
budgets - calling the same tool with the same arguments again and again (OpenCode loops forever on local models;
Gemini CLI "reads the same file 20 times"). So, in order:

1. parse (done by the provider: dict, JSON string, or double-encoded string);
2. COERCE the safe slips silently ("5" -> 5, "true" -> true) and record that it happened;
3. VALIDATE against the tool's JSON schema; if it still fails, give the model ONE retry with the precise error;
4. if it fails again it counts as a *malformed turn* - repeated malformed turns are an escalation trigger (LM-9);
5. the same (tool, arguments) three times in a short window is a loop, and is never executed a third time.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def _is(value: Any, jtype: str) -> bool:
    if jtype in ("integer", "number") and isinstance(value, bool):
        return False
    if jtype == "integer" and isinstance(value, float):
        return value.is_integer()
    t = _TYPES.get(jtype)
    return True if t is None else isinstance(value, t)


def coerce_args(schema: dict[str, Any], args: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fix the slips that are unambiguous. Returns (args, human-readable list of what was changed)."""
    props = (schema or {}).get("properties", {}) or {}
    out, changed = dict(args), []
    for key, spec in props.items():
        if key not in out:
            continue
        jtype, val = spec.get("type"), out[key]
        if jtype == "integer" and isinstance(val, str) and val.strip().lstrip("-").isdigit():
            out[key] = int(val)
        elif jtype == "integer" and isinstance(val, float) and val.is_integer():
            out[key] = int(val)
        elif jtype == "number" and isinstance(val, str):
            try:
                out[key] = float(val)
            except ValueError:
                continue
        elif jtype == "boolean" and isinstance(val, str) and val.strip().lower() in ("true", "false"):
            out[key] = val.strip().lower() == "true"
        elif jtype == "string" and isinstance(val, (int, float)) and not isinstance(val, bool):
            out[key] = str(val)
        elif jtype in ("array", "object") and isinstance(val, str):
            try:
                parsed = json.loads(val)
                if _is(parsed, jtype):
                    out[key] = parsed
            except json.JSONDecodeError:
                continue
        else:
            continue
        if out[key] != val:
            changed.append(f"{key}: {type(val).__name__} -> {jtype}")
    return out, changed


def validate_args(schema: dict[str, Any], args: Any) -> list[str]:
    """Problems with ``args`` against a JSON-schema subset (object, properties, required, type, enum)."""
    if not isinstance(args, dict):
        return [f"arguments must be a JSON object, got {type(args).__name__}"]
    problems: list[str] = []
    props = (schema or {}).get("properties", {}) or {}
    for req in (schema or {}).get("required", []) or []:
        if req not in args or args[req] in (None, ""):
            problems.append(f"missing required argument '{req}'")
    for key, val in args.items():
        spec = props.get(key)
        if spec is None:
            if props and (schema or {}).get("additionalProperties") is False:
                problems.append(f"unknown argument '{key}' (allowed: {', '.join(props)})")
            continue
        jtype = spec.get("type")
        if jtype and not _is(val, jtype):
            problems.append(f"argument '{key}' must be {jtype}, got {type(val).__name__}")
        elif spec.get("enum") and val not in spec["enum"]:
            problems.append(f"argument '{key}' must be one of {spec['enum']}, got {val!r}")
    return problems


def repair_instruction(tool: str, problems: list[str], schema: dict[str, Any]) -> str:
    """The text sent back to the model for its single retry."""
    shown = json.dumps({"properties": (schema or {}).get("properties", {}), "required": (schema or {}).get("required", [])},
                       separators=(",", ":"))
    return (f"Your call to `{tool}` was rejected: {'; '.join(problems)}. "
            f"Call it again with valid arguments. Expected schema: {shown}")


def unknown_tool_message(name: str, available: list[str]) -> str:
    return f"There is no tool named `{name}`. Available tools: {', '.join(sorted(available)) or '(none)'}."


class LoopDetector:
    """The same tool with the same arguments ``threshold`` times within the last ``window`` calls."""

    def __init__(self, threshold: int = 3, window: int = 8):
        self.threshold = threshold
        self._recent: deque[str] = deque(maxlen=window)

    @staticmethod
    def key(name: str, args: dict[str, Any]) -> str:
        return name + ":" + json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))

    def check(self, name: str, args: dict[str, Any]) -> bool:
        """Record the call; True when it is the ``threshold``-th identical one (do not execute it)."""
        k = self.key(name, args)
        self._recent.append(k)
        return sum(1 for x in self._recent if x == k) >= self.threshold
