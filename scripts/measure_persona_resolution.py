#!/usr/bin/env python3
"""Measure local response-plan resolution and guidance rendering without model calls."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hutch.persona import (  # noqa: E402
    PersonaStyle,
    contextualize_persona,
    guidance,
    resolve_persona,
)


CASES = (
    ("clear_banter", "Roast my 47 open browser tabs.", (), None),
    ("colloquial_analysis", "Bro, compare SQLite and Postgres for this exact deployment in detail.", (), None),
    ("grounded_current_fact", "What is the latest release? Verify it and cite sources.", (), None),
    ("sensitive_boundary", "Tell me a joke about my debt and bankruptcy options.", (), None),
    ("answer_correction", "Shorter, but keep the lifecycle distinction.",
     ({"role": "assistant", "content": "A worker may outlive a timeout unless cancellation reaches the child."},), "shorter"),
    ("recipient_contract", "Draft a concise email to Alex with the exact JSON status attached.", (), None),
    ("code_contract", "Write a Python function that detects a stale response ID.", (), None),
    ("external_action", "Send the report to my manager.", (), None),
)


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _memory_gib() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 / 1024, 2)
    except (OSError, ValueError, IndexError):
        pass
    return None


def _git_value(*args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, timeout=3)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _resolve(case_index: int) -> tuple[str, str]:
    case_id, prompt, context, correction = CASES[case_index % len(CASES)]
    plan = resolve_persona(
        agent_preset=PersonaStyle(preset="dry_wit", depth="standard"),
        agent_override=PersonaStyle(humor="playful", warmth=60),
        conversation=PersonaStyle(depth="auto", banter=True),
        turn=PersonaStyle(depth="brief") if case_id == "clear_banter" else None,
        revisions={"agent": 17, "conversation": 8},
    )
    contextual = contextualize_persona(
        plan,
        prompt,
        conversation_context=list(context),
        answer_correction=correction,
    )
    return case_id, guidance(contextual)


def measure(samples: int, warmup: int) -> dict:
    for index in range(warmup):
        _resolve(index)

    durations_ms: list[float] = []
    case_counts = {case[0]: 0 for case in CASES}
    output_chars = 0
    for index in range(samples):
        started = time.perf_counter_ns()
        case_id, rendered = _resolve(index)
        durations_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        case_counts[case_id] += 1
        output_chars += len(rendered)

    ordered = sorted(durations_ms)
    p95 = ordered[max(0, math.ceil(0.95 * samples) - 1)]
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": _git_value("rev-parse", "HEAD"),
        "source_worktree_dirty_before_output": bool(_git_value("status", "--porcelain")),
        "scope": "resolve_persona + contextualize_persona + guidance; local Python only; excludes retrieval, engine, provider, network, streaming and rendering",
        "model": None,
        "model_calls": 0,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_model": _cpu_model(),
            "logical_cpus": os.cpu_count(),
            "memory_gib": _memory_gib(),
        },
        "method": {
            "samples": samples,
            "warmup_samples": warmup,
            "case_order": "deterministic round-robin across the listed scenario classes",
            "scenario_classes": list(case_counts),
            "sample_counts_by_case": case_counts,
            "rendered_guidance_characters_total": output_chars,
            "percentile": "nearest-rank",
        },
        "latency_ms": {
            "min": min(durations_ms),
            "p50": statistics.median(durations_ms),
            "p95": p95,
            "max": max(durations_ms),
            "mean": statistics.fmean(durations_ms),
            "target_p95_ms": 20.0,
            "target_met": p95 <= 20.0,
        },
        "limits": [
            "This is routing and prompt-guidance overhead, not response latency or model-quality evidence.",
            "It does not include actual hardware contention, cold imports, network, inference or first-useful-content timing.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.samples < 1 or args.warmup < 0:
        parser.error("samples must be positive and warmup cannot be negative")
    result = measure(args.samples, args.warmup)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    print(json.dumps(result["latency_ms"], sort_keys=True), file=sys.stderr)
    return 0 if result["latency_ms"]["target_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
