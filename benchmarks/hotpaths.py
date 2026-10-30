"""Reproducible hot-path benchmark harness for Hutch (Phase 2 profiling, D3/D4 input).

    cd /home/kevina/CodingProjects/hutch/.agents/worktrees/perf-rust
    PYTHONPATH="$PWD/src" /home/kevina/CodingProjects/hutch/.venv/bin/python -m benchmarks.hotpaths \
        [--quick] [--json PATH] [--only validation,store] [--list]

Measures >=8 real operations with n/min/median/p95/max, machine metadata and isolated
HUTCH_STATE_DIR scratch per case. --quick shrinks corpora and sample counts for
development; the default (full) mode is the baseline evidence and uses >=7 samples.

No source code is modified: every number measures the tree this command runs in
(record meta.source_revision / meta.harness_sha256 with the result).
Results are written to benchmarks/results/hotpaths-<UTC date>.json (gitignored).

Workload modules live in benchmarks/hotpath_workloads/ (one per subsystem).
Scratch state defaults to /tmp/hutch-perf-profiler/hotpaths-<pid> and is removed at exit.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
DEFAULT_STATE_ROOT = Path("/tmp/hutch-perf-profiler")

#: Full-mode samples per case; quick mode is for smoke tests only.
FULL_SAMPLES = 7
QUICK_SAMPLES = 3


def _load_average() -> list[float]:
    """1/5/15-minute load average, recorded so a busy desktop cannot silently fake a regression."""
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except (OSError, AttributeError):
        return [0.0, 0.0, 0.0]


def machine() -> dict:
    """Machine/interpreter identity plus the harness digest (reproducibility fingerprint)."""
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    total_memory_mb = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                total_memory_mb = round(int(line.split()[1]) / 1024, 1)
                break
    except (OSError, ValueError, IndexError):
        pass
    try:
        git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE.parent, text=True,
                                           stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=HERE.parent, text=True,
                                             stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        git_head, dirty = "unknown", True
    digest = hashlib.sha256()
    for path in [HERE / "hotpaths.py", *sorted((HERE / "hotpath_workloads").glob("*.py"))]:
        digest.update(path.read_bytes())
    return {
        "cpu": cpu,
        "cores": str(os.cpu_count()),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "total_memory_mb": total_memory_mb or 0.0,
        "load_avg_1m_5m_15m": _load_average(),
        "source_revision": os.environ.get("HUTCH_BENCH_SOURCE_REVISION", git_head),
        "git_head": git_head,
        "working_tree_dirty": dirty,
        "harness_sha256": digest.hexdigest(),
        "measured_on": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sample_schema": 1,
    }


def percentile(samples: list[float], pct: float) -> float:
    """Linear-interpolated percentile (0..100); n>=2."""
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * pct / 100.0
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(samples: list[float]) -> dict:
    mean = statistics.fmean(samples)
    stdev = statistics.stdev(samples) if len(samples) > 1 else 0.0
    return {
        "n": len(samples),
        "min": min(samples),
        "median": statistics.median(samples),
        "mean": mean,
        "p95": percentile(samples, 95),
        "max": max(samples),
        "stdev": stdev,
        "cv_pct": (stdev / mean * 100.0) if mean else 0.0,
        # With n<20 the interpolated p95 sits between the two slowest samples; treat it as max.
        "p95_is_effectively_max": len(samples) < 20,
    }


def _module_list():
    from benchmarks.hotpath_workloads import MODULES
    return MODULES


def run_workload(name: str, module_path: str, quick: bool, state: Path) -> tuple[list[dict], dict | None]:
    """Import and run one workload module; a failure becomes a recorded skip, not a crash."""
    state.mkdir(parents=True, exist_ok=True)
    os.environ["HUTCH_STATE_DIR"] = str(state / "state")
    try:
        module = importlib.import_module(module_path)
        return list(module.run(quick=quick, state=state)), None
    except Exception as exc:  # noqa: BLE001 - a broken case must not hide the rest of the baseline
        detail = f"{type(exc).__name__}: {exc}"
        print(f"[skip] {name}: {detail}", file=sys.stderr)
        traceback.print_exc(limit=3, file=sys.stderr)
        return [], {"module": name, "reason": detail}


def _fmt(value: float, unit: str) -> str:
    if unit in {"us", "ms"}:
        return f"{value:,.3f}"
    if unit == "s":
        return f"{value:,.4f}"
    if unit in {"ev/s", "MB/s"}:
        return f"{value:,.0f}"
    return f"{value:,.3f}"


def report(cases: list[dict], skipped: list[dict], meta: dict) -> str:
    head = (f"{'case':<44}{'n':>4}{'min':>12}{'median':>12}{'p95':>12}{'max':>12}{'cv%':>7}  "
            f"{'unit':<6} note")
    rows = [head, "-" * len(head)]
    for case in cases:
        s = case["stats"]
        rows.append(f"{case['name']:<44}{s['n']:>4}{_fmt(s['min'], case['unit']):>12}"
                    f"{_fmt(s['median'], case['unit']):>12}{_fmt(s['p95'], case['unit']):>12}"
                    f"{_fmt(s['max'], case['unit']):>12}{s['cv_pct']:>7.1f}  "
                    f"{case['unit']:<6} {case.get('note', '')}")
    for skip in skipped:
        rows.append(f"{skip['module'] + ': SKIPPED':<44}{'-':>4}{'-':>12}{'-':>12}{'-':>12}{'-':>12}  "
                    f"{'-':<6} {skip['reason']}")
    rows.append("")
    rows.append(f"machine: {meta['cpu']} ({meta['cores']} threads), {meta['total_memory_mb']:.0f} MB RAM, "
                f"python {meta['python']}, {meta['platform']}")
    rows.append("p95 is interpolated; for n<20 it sits between the two slowest samples and should be read "
                "as max (the JSON marks it p95_is_effectively_max). cv% = stdev/mean.")
    rows.append(f"load avg: {meta['load_avg_1m_5m_15m']} (1m/5m/15m); "
                f"source: {meta['git_head']} dirty={meta['working_tree_dirty']} harness={meta['harness_sha256'][:12]}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="small corpora / fewer samples (development smoke test)")
    ap.add_argument("--json", metavar="PATH", help="JSON output path (default benchmarks/results/hotpaths-<UTC date>.json)")
    ap.add_argument("--only", metavar="NAMES", help="comma-separated workload module names (see --list)")
    ap.add_argument("--list", action="store_true", help="list workload modules and exit")
    args = ap.parse_args(argv)

    modules = _module_list()
    if args.list:
        for name, module_path, description in modules:
            print(f"{name:<12} {module_path:<48} {description}")
        return 0

    selected = modules
    if args.only:
        wanted = {part.strip() for part in args.only.split(",") if part.strip()}
        selected = [row for row in modules if row[0] in wanted]
        unknown = wanted - {row[0] for row in modules}
        if unknown:
            print(f"unknown workload module(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2

    meta = machine()
    quick = args.quick
    state_root = Path(os.environ.get("HUTCH_HOTPATH_STATE_ROOT") or DEFAULT_STATE_ROOT / f"hotpaths-{os.getpid()}")
    shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    skipped: list[dict] = []
    started = time.perf_counter()
    try:
        for name, module_path, _description in selected:
            print(f"[run ] {name} ...", file=sys.stderr)
            measurements, skip = run_workload(name, module_path, quick, state_root / name)
            if skip:
                skipped.append(skip)
                continue
            for item in measurements:
                samples = [float(v) for v in item["samples"]]
                if not samples:
                    skipped.append({"module": name, "reason": f"{item['name']}: no samples"})
                    continue
                cases.append({
                    "name": item["name"],
                    "unit": item["unit"],
                    "better": item.get("better"),
                    "samples": samples,
                    "stats": summarize(samples),
                    "note": item.get("note", ""),
                    "detail": item.get("detail", {}),
                })
    finally:
        if state_root.name.startswith("hotpaths-") and str(state_root).startswith(str(DEFAULT_STATE_ROOT)):
            shutil.rmtree(state_root, ignore_errors=True)

    elapsed = time.perf_counter() - started
    result = {
        "meta": {**meta, "quick": quick, "samples_per_case": QUICK_SAMPLES if quick else FULL_SAMPLES,
                 "elapsed_seconds": round(elapsed, 2), "state_root": str(DEFAULT_STATE_ROOT)},
        "cases": {case["name"]: case for case in cases},
        "skipped": skipped,
    }
    out_path = Path(args.json) if args.json else RESULTS / f"hotpaths-{time.strftime('%Y-%m-%d', time.gmtime())}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n")

    print(report(cases, skipped, meta))
    print(f"\nwrote {out_path} ({len(cases)} cases, {len(skipped)} skipped) in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
