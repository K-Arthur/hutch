"""Paired cold-start benchmark for the CLI quick path (before/after source trees).

The quick commands (version, --help, status, bot list) are dominated by Python import time, so
the only meaningful comparison is between two source trees measured in one driver, alternating
samples. Each sample is a fresh OS process running the installed console script with PYTHONPATH
pinned to the tree under test and an isolated HUTCH_STATE_DIR, so bytecode caches, state and
machine load are equivalent for both sides.

Usage:
    # pin the comparison commit into a scratch tree (no checkout switching)
    git archive <before-ref> | tar -x -C /tmp/hutch-before
    python -m benchmarks.cli_startup_ab --before /tmp/hutch-before/src --after src

The JSON record (default: benchmarks/results/cli_startup_ab-<timestamp>.json) keeps every
alternating sample plus min/median/p95, the sha256 of each command stdout and the host load, so
the claim is auditable. --check fails on a stdout difference or a median regression beyond
--tolerance (default 20%), which matches the repository benchmark gate.

This measures control-path CPU only: it does not include model, network or tool latency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "benchmarks" / "results"
CASES: dict[str, list[str]] = {
    "version": ["version"],
    "help": ["--help"],
    "status": ["status"],
    "bot_list": ["bot", "list"],
}


def _percentile(ordered: list[float], fraction: float) -> float:
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _stats(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "min": ordered[0],
        "median": statistics.median(ordered),
        "p95": _percentile(ordered, 0.95),
        "max": ordered[-1],
        "samples": [round(value, 1) for value in samples],
    }


def _load_average() -> list[float]:
    try:
        return [float(part) for part in Path("/proc/loadavg").read_text().split()[:3]]
    except OSError:
        return []


def _command() -> list[str]:
    entry = Path(sys.executable).parent / "hutch"
    if entry.exists():
        return [str(entry)]
    return [sys.executable, "-c", "from hutch.cli import main; main()"]


def _env(src: str, state: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("HUTCH_")}
    env.update(PYTHONPATH=src, HUTCH_STATE_DIR=str(state), COLUMNS="80", TERM="dumb", NO_COLOR="1")
    return env


def _run(src: str, state: Path, args: list[str]) -> tuple[float, int, str]:
    started = time.perf_counter()
    proc = subprocess.run(_command() + args, capture_output=True, env=_env(src, state), timeout=180)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, proc.returncode, hashlib.sha256(proc.stdout).hexdigest()


def _resolved_hutch(src: str) -> str:
    proc = subprocess.run([sys.executable, "-c", "import hutch; print(hutch.__file__)"],
                          capture_output=True, text=True, env=_env(src, Path("/tmp")), timeout=120)
    return proc.stdout.strip()


def _measure_case(name: str, args: list[str], before_src: str, after_src: str,
                  state: Path, samples: int) -> dict:
    # Warm bytecode caches and initialise state on both trees before sampling.
    _run(before_src, state, ["init"])
    for src in (before_src, after_src):
        _run(src, state, args)
    before: list[float] = []
    after: list[float] = []
    loads: list[float] = []
    rc: dict[str, int] = {}
    digests: dict[str, str] = {}
    for _ in range(samples):
        loads.append(_load_average()[0] if _load_average() else 0.0)
        b_ms, rc["before"], digests["before"] = _run(before_src, state, args)
        a_ms, rc["after"], digests["after"] = _run(after_src, state, args)
        before.append(b_ms)
        after.append(a_ms)
    before_stats = _stats(before)
    after_stats = _stats(after)
    delta = (after_stats["median"] - before_stats["median"]) / before_stats["median"] * 100.0
    return {
        "args": args,
        "before": before_stats,
        "after": after_stats,
        "delta_pct": round(delta, 1),
        "returncode": rc,
        "stdout_sha256": digests,
        "stdout_equal": digests["before"] == digests["after"],
        "load_median": round(statistics.median(loads), 2),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, help="src/ directory of the baseline tree")
    parser.add_argument("--after", required=True, help="src/ directory of the candidate tree")
    parser.add_argument("--samples", type=int, default=9, help="alternating samples per case")
    parser.add_argument("--tolerance", type=float, default=0.20,
                        help="median regression fraction that fails --check")
    parser.add_argument("--check", action="store_true", help="fail on stdout change or regression")
    parser.add_argument("--json", type=Path, default=None, help="output path for the record")
    args = parser.parse_args(argv)

    before_src = str(Path(args.before).resolve())
    after_src = str(Path(args.after).resolve())
    for label, src in (("before", before_src), ("after", after_src)):
        if not (Path(src) / "hutch" / "cli.py").is_file():
            parser.error(f"--{label} does not look like a hutch src directory: {src}")

    results_dir = args.json.parent if args.json else DEFAULT_RESULTS
    results_dir.mkdir(parents=True, exist_ok=True)
    state = results_dir / f"cli_startup_ab-state-{os.getpid()}"
    state.mkdir(parents=True, exist_ok=True)

    record: dict = {
        "schema": "hutch/benchmarks/cli_startup_ab/1",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "before_src": before_src,
        "after_src": after_src,
        "resolved": {"before": _resolved_hutch(before_src), "after": _resolved_hutch(after_src)},
        "samples_per_case": args.samples,
        "machine": {"cpus": os.cpu_count(), "python": sys.version.split()[0]},
        "cases": {},
        "notes": [
            "fresh process per sample; PYTHONPATH pins the tree under test",
            "samples alternate before/after within one driver so load drift hits both sides",
            "measures import/control-path CPU only, not model or network latency",
        ],
    }
    failures = 0
    for name, case_args in CASES.items():
        case = _measure_case(name, case_args, before_src, after_src, state, args.samples)
        record["cases"][name] = case
        print(f"{name:9s} before {case['before']['median']:7.0f} ms  "
              f"after {case['after']['median']:7.0f} ms  {case['delta_pct']:+6.1f}%  "
              f"p95 {case['before']['p95']:.0f}->{case['after']['p95']:.0f} ms  "
              f"load {case['load_median']:.1f}  rc {case['returncode']['after']}  "
              f"stdout {'same' if case['stdout_equal'] else 'DIFFERS'}")
        if case["returncode"]["after"] != 0 or not case["stdout_equal"]:
            failures += 1
        if case["after"]["median"] > case["before"]["median"] * (1.0 + args.tolerance):
            failures += 1
            print(f"  FAIL: {name} median regressed beyond {args.tolerance:.0%}")
    record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    destination = args.json or DEFAULT_RESULTS / f"cli_startup_ab-{time.strftime('%Y%m%dT%H%M%S')}.json"
    destination.write_text(json.dumps(record, indent=1))
    print(f"record: {destination}")
    if args.check:
        print("check:", "FAIL" if failures else "PASS")
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
