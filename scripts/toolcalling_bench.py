#!/usr/bin/env python
"""Measure tool-calling compilation and validation overhead - no model calls.

This exists so the budgets in docs/realignment/tool-calling.md are measured, not
invented. Run it after any change to the compiler, lowering, or validator:

    PYTHONPATH=src python scripts/toolcalling_bench.py

Numbers are wall-clock milliseconds on the machine that runs this (cold = fresh
cache, warm = cached immutable plan). Inference time is explicitly excluded: the
script never touches a provider.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any

from hutch.context import prompt_tokens
from hutch.toolcalling.compiler import clear_plan_cache, compile_plan
from hutch.toolcalling.profiles import resolve_profile
from hutch.toolcalling.strictjson import loads_strict
from hutch.toolcalling.validate import validate_call


class _Tool:
    def __init__(self, name: str, index: int) -> None:
        self.name = name
        self.description = f"Tool {index} for the benchmark: reads a record by id and returns its fields."
        self.parameters = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Record id"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "mode": {"type": "string", "enum": ["summary", "full"]},
                "labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id"],
            "additionalProperties": False,
        }


def _median_ms(fn, rounds: int = 7) -> float:
    samples = []
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return round(statistics.median(samples), 3)


def _catalog(size: int) -> dict[str, _Tool]:
    return {f"bench_tool_{index:03d}": _Tool(f"bench_tool_{index:03d}", index) for index in range(size)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tools", default="1,10,100")
    parser.add_argument("--rounds", type=int, default=7)
    args = parser.parse_args()

    profile_native = resolve_profile(provider="vllm", endpoint="http://localhost:8000/v1", model="bench")
    profile_constrained = profile_native
    call = {"id": "abc-123", "limit": 3, "mode": "summary", "labels": ["a", "b"]}
    schema = _Tool("x", 0).parameters
    raw = json.dumps(call, separators=(",", ":"))

    rows: list[dict[str, Any]] = []
    for size in (int(part) for part in args.tools.split(",")):
        tools = _catalog(size)
        clear_plan_cache()
        cold_ms = _median_ms(lambda: (clear_plan_cache(),
                                      compile_plan(tools=tools, profile=profile_native, strategy="native")),
                             rounds=max(1, args.rounds // 2))
        warm_ms = _median_ms(lambda: compile_plan(tools=tools, profile=profile_native, strategy="native"),
                             rounds=args.rounds)
        constrained_cold = _median_ms(
            lambda: (clear_plan_cache(),
                     compile_plan(tools=tools, profile=profile_constrained, strategy="constrained")),
            rounds=max(1, args.rounds // 2))
        plan_native = compile_plan(tools=tools, profile=profile_native, strategy="native")
        plan_constrained = compile_plan(tools=tools, profile=profile_constrained, strategy="constrained")
        messages = [{"role": "system", "content": plan_constrained.prompt_contract}]
        prompt_only, _ = prompt_tokens(messages, [])
        _, wire_tokens = prompt_tokens([], [dict(t) for t in plan_native.wire_tools])
        rows.append({
            "tools": size,
            "native_cold_ms": cold_ms,
            "native_warm_ms": warm_ms,
            "constrained_cold_ms": constrained_cold,
            "native_wire_tokens": wire_tokens,
            "constrained_contract_tokens": prompt_only,
            "envelope_schema_bytes": len(json.dumps(plan_constrained.envelope_schema or {})),
            "diagnostics": len(plan_constrained.diagnostics),
        })

    validation_ms = _median_ms(lambda: validate_call(schema, call), rounds=200)
    decode_ms = _median_ms(lambda: loads_strict(raw), rounds=200)
    print(json.dumps({"rows": rows, "validate_call_ms": validation_ms, "strict_decode_ms": decode_ms}, indent=2))


if __name__ == "__main__":
    main()
