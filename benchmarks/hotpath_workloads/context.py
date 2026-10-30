"""Prompt/context sizing: context.prompt_tokens and runtime.fitloop.count_tokens on real transcripts.

Builds deterministic transcripts of 10 / 100 / 400 messages with realistic JSON tool calls and
times one sizing call. Also simulates the runtime loop: one count_tokens per step over a growing
transcript, so the cumulative cost can be checked against a quadratic curve (10x steps -> ~100x
time if every step re-counts the whole history).
"""

from __future__ import annotations

import json
import statistics
import time

SAMPLES_FULL = 7
SAMPLES_QUICK = 3
LOOPS = 10
TOOL_NAMES = ["shell", "read_file", "list_files", "write_file", "remember", "recall", "web_fetch", "run_python"]
SYSTEM = ("You are Hutch, a local-first assistant. Follow the operator's instructions, keep tool calls "
          "minimal, never invent file contents, and report uncertainty honestly. ") * 40


def _tools() -> list[dict]:
    from benchmarks.hotpath_workloads import tool_schemas

    schemas = tool_schemas(TOOL_NAMES)
    return [{"type": "function",
             "function": {"name": name, "description": f"benchmark description for {name}",
                          "parameters": schema}} for name, schema in schemas.items()]


def _unit(index: int) -> list[dict]:
    arguments = json.dumps({"path": f"reports/week-{index % 52:02d}.md"}, separators=(",", ":"))
    return [
        {"role": "user", "content": f"Inspect reports/week-{index % 52:02d}.md and summarize the deltas "
                                    "against the previous week, citing the lines that changed."},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": f"call_{index}", "type": "function",
                         "function": {"name": "read_file", "arguments": arguments}}]},
        {"role": "tool", "tool_call_id": f"call_{index}",
         "content": ("line of the report with a number and a short explanation of the change " * 22)[:1200]},
        {"role": "assistant", "content": "The report shows a small increase in the weekly totals; " +
                                         "the changed lines are listed above. " * 8},
    ]


def _transcript(messages: int) -> list[dict]:
    if messages < 2:
        raise ValueError("a transcript needs at least the system message and one turn")
    out = [{"role": "system", "content": SYSTEM}]
    index = 0
    while len(out) < messages:
        out.extend(_unit(index))
        index += 1
    return out[:messages]


def _measure_sizing(fn, n: int) -> list[float]:
    samples = []
    for _ in range(n):
        started = time.perf_counter()
        for _loop in range(LOOPS):
            fn()
        samples.append((time.perf_counter() - started) / LOOPS * 1000.0)
    return samples


def _cumulative_steps(steps: int) -> float:
    """Time a loop that values the whole growing transcript once per step."""
    from hutch.runtime.fitloop import count_tokens

    messages = [{"role": "system", "content": SYSTEM}]
    started = time.perf_counter()
    for step in range(steps):
        messages.extend(_unit(step))
        count_tokens(messages, 0)
    return (time.perf_counter() - started) * 1000.0


def run(quick: bool, state) -> list[dict]:
    from hutch.context import estimate_tokens, prompt_tokens
    from hutch.runtime.fitloop import count_tokens

    n = SAMPLES_QUICK if quick else SAMPLES_FULL
    tools = _tools()
    tool_tokens = estimate_tokens(json.dumps(tools, separators=(",", ":")))
    sizes = [10, 100] if quick else [10, 100, 400]
    cases: list[dict] = []
    for size in sizes:
        messages = _transcript(size)
        prompt_samples = _measure_sizing(lambda messages=messages: prompt_tokens(messages, tools), n)
        count_samples = _measure_sizing(lambda messages=messages: count_tokens(messages, tool_tokens), n)
        tokens = prompt_tokens(messages, tools)
        cases.append({
            "name": f"context.prompt_tokens_{size}msg_ms", "unit": "ms", "samples": prompt_samples,
            "better": "lower", "note": f"{size} messages; message_tokens={tokens[0]:,} tool_tokens={tokens[1]:,}",
            "detail": {"messages": size, "message_tokens": tokens[0], "tool_tokens": tokens[1],
                       "us_per_message": statistics.median(prompt_samples) / size * 1000},
        })
        cases.append({
            "name": f"context.count_tokens_{size}msg_ms", "unit": "ms", "samples": count_samples,
            "better": "lower", "note": f"{size} messages; tool_tokens passed precomputed ({tool_tokens:,})",
            "detail": {"messages": size, "us_per_message": statistics.median(count_samples) / size * 1000},
        })
    steps = [10] if quick else [10, 100]
    cumulative: dict[int, list[float]] = {}
    for step_count in steps:
        samples = [_cumulative_steps(step_count) for _ in range(n)]
        cumulative[step_count] = samples
        cases.append({
            "name": f"context.cumulative_steps_{step_count}_ms", "unit": "ms", "samples": samples,
            "better": "lower",
            "note": f"one count_tokens per step over a growing transcript, {step_count} steps",
            "detail": {"steps": step_count,
                       "us_per_step": statistics.median(samples) / step_count * 1000},
        })
    if len(steps) > 1:
        first, last = steps[0], steps[-1]
        ratios = [high / low if low else 0.0
                  for low, high in zip(cumulative[first], cumulative[last])]
        linear = last / first
        cases.append({
            "name": "context.cumulative_scaling_ratio", "unit": "x", "samples": ratios, "better": "lower",
            "note": f"{last}/{first} steps -> ~{statistics.median(ratios):.1f}x time; linear={linear:.1f}x, "
                    f"quadratic={linear * linear:.1f}x",
            "detail": {"from_steps": first, "to_steps": last,
                       "linear_expectation": linear, "quadratic_expectation": linear * linear},
        })
    return cases
