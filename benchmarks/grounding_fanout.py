"""Measured comparison: one-provider serial retrieval vs bounded fan-out.

Mission section 13 asks for a serial baseline, bounded fan-out, and honest caveats instead
of universal "real-time" claims. This script measures **Hutch's own scheduler** on
deterministic fake adapters: identical fixed latencies, no network, no model calls. It is a
scheduler comparison on this machine, not a provider-performance benchmark.

Run: ``.venv/bin/python -m benchmarks.grounding_fanout``  (prints JSON; writes nothing)
"""

from __future__ import annotations

import json
import platform
import statistics
import time

from hutch.grounding import acquire as acquire_mod
from hutch.grounding.clock import SYSTEM_CLOCK
from hutch.grounding.temporal import EvidenceCutoff

LATENCY = 0.5  # seconds per fake adapter, same for every lane
ADAPTERS = ("gdelt", "feeds", "hn", "bluesky")
SAMPLES = 5


def _fake(name: str, latency: float):
    def fn(query, cutoff, budget, clock, cfg, stop):
        time.sleep(latency)
        source = acquire_mod.FoundSource(adapter=name, lane="news", platform="web", kind="article",
                                         url=f"https://{name}.example/{query}", origin_id=f"{name}-{query}",
                                         title=f"{name} result", retrieved_at=clock.now().isoformat())
        outcome = acquire_mod.AdapterOutcome(adapter=name, lane="news", query=query, state="ok",
                                             retained=1, returned=1, latency_ms=latency * 1000)
        return [source], outcome
    return fn


def _serial_baseline(latency: float, cutoff) -> tuple[float, int]:
    """A hand-rolled sequential loop: what a single-lane orchestrator pays for the same work."""
    started = time.monotonic()
    count = 0
    for name in ADAPTERS:
        sources, _outcome = _fake(name, latency)(name, cutoff, acquire_mod.AcquireBudget(),
                                                 SYSTEM_CLOCK, acquire_mod.GroundingConfig(), lambda: False)
        count += len(sources)
    return time.monotonic() - started, count


def _fanout(latency: float, concurrency: int, wall: float, cutoff) -> tuple[float, int]:
    overrides = {name: _fake(name, latency) for name in ADAPTERS}
    started = time.monotonic()
    result = acquire_mod.run_search("bridge", cutoff=cutoff,
                                    budget=acquire_mod.AcquireBudget(max_concurrency=concurrency,
                                                                     wall_seconds=wall,
                                                                     max_total_sources=40),
                                    clock=SYSTEM_CLOCK, cfg=acquire_mod.GroundingConfig(),
                                    lanes=("news", "feeds", "discussion", "social"),
                                    adapter_overrides=overrides)
    return time.monotonic() - started, len(result.sources)


def main() -> None:
    cutoff = EvidenceCutoff.from_clock(SYSTEM_CLOCK, horizon_hours=24)
    serial = [_serial_baseline(LATENCY, cutoff)[0] for _ in range(SAMPLES)]
    bounded = [_fanout(LATENCY, 4, 10.0, cutoff)[0] for _ in range(SAMPLES)]
    deadline = time.monotonic()
    overrides = {name: _fake(name, 1.5) for name in ADAPTERS}
    result = acquire_mod.run_search("bridge", cutoff=cutoff,
                                    budget=acquire_mod.AcquireBudget(max_concurrency=4, wall_seconds=0.6),
                                    clock=SYSTEM_CLOCK, cfg=acquire_mod.GroundingConfig(),
                                    lanes=("news", "feeds", "discussion", "social"),
                                    adapter_overrides=overrides)
    deadline_elapsed = time.monotonic() - deadline
    report = {
        "what": "Hutch grounding fan-out scheduler on deterministic fake adapters (no network)",
        "machine": {"platform": platform.platform(), "python": platform.python_version()},
        "date": "2026-10-11",
        "config": {"adapters": list(ADAPTERS), "per_adapter_latency_s": LATENCY, "samples": SAMPLES},
        "results_s": {
            "serial_baseline_mean": round(statistics.mean(serial), 3),
            "serial_baseline_all": [round(x, 3) for x in serial],
            "bounded_fanout_mean": round(statistics.mean(bounded), 3),
            "bounded_fanout_all": [round(x, 3) for x in bounded],
        },
        "speedup": round(statistics.mean(serial) / statistics.mean(bounded), 2),
        "wall_deadline": {"limit_s": 0.6, "observed_s": round(deadline_elapsed, 3),
                          "deadline_hit": result.deadline_hit,
                          "sources_retained": len(result.sources)},
        "caveats": ("fake fixed latencies on one machine; measures the scheduler, not providers or "
                    "networks; one slow adapter is bounded by per-adapter timeouts and the wall deadline"),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
