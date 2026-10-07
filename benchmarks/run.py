"""Benchmarks for PF-5/6/7/11/13, with a regression gate (PF-12).

    python -m benchmarks.run                 # measure, print, write benchmarks/results/latest.json
    python -m benchmarks.run --record        # also (over)write the baseline for this machine
    python -m benchmarks.run --check         # compare with the baseline; exit 1 on a >20% regression

Everything is offline (mock model). Numbers are machine-specific: baselines are keyed by
$HUTCH_BENCH_BASELINE (default "local"), so CI records its own on first run and compares afterwards.
The draft's targets are *proposals*; they are printed next to each metric but only the regression
gate fails the build.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
TOLERANCE = 0.20

#: name -> (unit, better, absolute floor below which a delta is noise, proposed target or None)
METRICS: dict[str, tuple[str, str, float, float | None]] = {
    "cli_version_ms": ("ms", "lower", 25.0, None),
    "cli_status_ms": ("ms", "lower", 25.0, 300.0),            # PF-6
    "events_per_sec": ("ev/s", "higher", 500.0, 1000.0),       # PF-7
    "step_overhead_ms": ("ms", "lower", 0.5, 50.0),            # PF-11
    "idle_rss_daemon_mb": ("MB", "lower", 4.0, 150.0),         # PF-13
    "idle_rss_serve_mb": ("MB", "lower", 4.0, 150.0),          # PF-13
    "idle_cpu_daemon_s_per_hour": ("s/h", "lower", 30.0, None),# PF-5
    "idle_cpu_serve_s_per_hour": ("s/h", "lower", 30.0, None), # PF-5
}


def _hutch_cmd() -> list[str]:
    exe = Path(sys.executable).parent / "hutch"
    return [str(exe)] if exe.exists() else [sys.executable, "-m", "hutch.cli"]


def _env(state: Path) -> dict[str, str]:
    return dict(os.environ, HUTCH_STATE_DIR=str(state))


def bench_cli(state: Path, runs: int = 11) -> dict[str, float]:
    subprocess.run(_hutch_cmd() + ["init"], env=_env(state), capture_output=True, check=True)
    out = {}
    for name, args in (("cli_version_ms", ["version"]), ("cli_status_ms", ["status"])):
        subprocess.run(_hutch_cmd() + args, env=_env(state), capture_output=True)  # warm the page cache
        samples = []
        for _ in range(runs):
            t = time.perf_counter()
            subprocess.run(_hutch_cmd() + args, env=_env(state), capture_output=True, check=True)
            samples.append((time.perf_counter() - t) * 1000)
        out[name] = round(min(samples), 1)  # min is the stable estimator of CPU-bound latency under noise
    return out


def bench_events(state: Path, n: int = 20_000) -> dict[str, float]:
    os.environ["HUTCH_STATE_DIR"] = str(state)
    from hutch.config import get_config
    from hutch.models import Bot, Event, EventType, Run
    from hutch.store import Store
    store = Store(get_config())
    bot = store.create_bot(Bot(name="bench"))
    run = store.create_run(Run(bot_id=bot.id, prompt="bench"))
    rates = []
    for _ in range(3):
        t = time.perf_counter()
        for i in range(n):
            store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i, "pad": "x" * 64}))
        store.flush_events()
        rates.append(n / (time.perf_counter() - t))
    assert store.count_events(run.id) == 3 * n
    store.close()
    return {"events_per_sec": round(statistics.median(rates))}


def bench_step_overhead(state: Path, runs: int = 12) -> dict[str, float]:
    os.environ["HUTCH_STATE_DIR"] = str(state)
    from hutch.config import get_config
    from hutch.engine import Engine
    from hutch.models import ApprovalMode, Bot
    from hutch.store import Store
    config = get_config()
    store = Store(config)
    engine = Engine(config, store)
    bot = store.create_bot(Bot(name="steps", model="mock/demo", tools=["shell", "files", "memory"],
                               approval_mode=ApprovalMode.auto))
    overhead = steps = 0.0
    for _ in range(runs):
        run = engine.run_blocking(bot, "research the weekly news and summarize")
        overhead += run.overhead_ms
        steps += max(run.steps, 1)
    store.close()
    return {"step_overhead_ms": round(overhead / steps, 3)}


def _rss_mb(pid: int) -> float:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024.0
    return 0.0


def _cpu_seconds(pid: int) -> float:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _idle_profile(argv: list[str], state: Path, ready, warm: float, window: float) -> tuple[float, float]:
    proc = subprocess.Popen(argv, env=_env(state), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        deadline = time.time() + 30
        while time.time() < deadline and not ready():
            time.sleep(0.1)
        time.sleep(warm)
        cpu0, t0 = _cpu_seconds(proc.pid), time.time()
        time.sleep(window)
        cpu = (_cpu_seconds(proc.pid) - cpu0) / (time.time() - t0) * 3600
        return round(_rss_mb(proc.pid), 1), round(cpu, 2)
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)


def bench_idle(state: Path, window: float = 8.0) -> dict[str, float]:
    out: dict[str, float] = {}
    rss, cpu = _idle_profile(_hutch_cmd() + ["daemon"], state, ready=lambda: True, warm=2.5, window=window)
    out["idle_rss_daemon_mb"], out["idle_cpu_daemon_s_per_hour"] = rss, cpu
    port = _free_port()

    def up() -> bool:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5).read()
            return True
        except Exception:
            return False

    rss, cpu = _idle_profile(_hutch_cmd() + ["serve", "--port", str(port)], state, ready=up, warm=2.5, window=window)
    out["idle_rss_serve_mb"], out["idle_cpu_serve_s_per_hour"] = rss, cpu
    return out


def machine() -> dict[str, str]:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {"cpu": cpu, "cores": str(os.cpu_count()), "python": platform.python_version(),
            "platform": platform.platform(), "measured_on": time.strftime("%Y-%m-%d")}


def measure(quick: bool = False) -> dict:
    work = Path(tempfile.mkdtemp(prefix="hutch-bench-"))
    try:
        metrics: dict[str, float] = {}
        metrics.update(bench_cli(work / "cli", runs=5 if quick else 11))
        metrics.update(bench_events(work / "events", n=5_000 if quick else 20_000))
        metrics.update(bench_step_overhead(work / "steps", runs=4 if quick else 12))
        subprocess.run(_hutch_cmd() + ["init"], env=_env(work / "idle"), capture_output=True, check=True)
        metrics.update(bench_idle(work / "idle", window=4.0 if quick else 8.0))
        return {"meta": machine(), "metrics": metrics}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def baseline_path() -> Path:
    return ROOT / "baselines" / f"{os.environ.get('HUTCH_BENCH_BASELINE', 'local')}.json"


def compare(current: dict, baseline: dict) -> list[str]:
    """Return human-readable regressions (empty list = pass)."""
    bad = []
    for name, (unit, better, floor, _target) in METRICS.items():
        if name not in current["metrics"] or name not in baseline["metrics"]:
            continue
        cur, base = current["metrics"][name], baseline["metrics"][name]
        worse = (cur - base) if better == "lower" else (base - cur)
        if worse > floor and worse > abs(base) * TOLERANCE:
            bad.append(f"{name}: {cur}{unit} vs baseline {base}{unit} "
                       f"({worse / max(abs(base), 1e-9) * 100:+.0f}% worse; limit {TOLERANCE * 100:.0f}%)")
    return bad


def report(result: dict, baseline: dict | None) -> str:
    rows = [f"{'metric':<30}{'value':>12}{'baseline':>12}{'target':>10}"]
    for name, (unit, better, _floor, target) in METRICS.items():
        cur = result["metrics"].get(name)
        if cur is None:
            continue
        base = baseline["metrics"].get(name) if baseline else None
        mark = ""
        if target is not None:
            ok = cur <= target if better == "lower" else cur >= target
            mark = "ok" if ok else "MISS"
        rows.append(f"{name:<30}{str(cur) + unit:>12}{(str(base) + unit) if base is not None else '-':>12}"
                    f"{(str(target) if target is not None else '-'):>10} {mark}")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true", help="write the baseline for this machine")
    ap.add_argument("--check", action="store_true", help="fail on a >20%% regression vs the baseline")
    ap.add_argument("--record-if-missing", action="store_true", help="CI: record a baseline on first run")
    ap.add_argument("--quick", action="store_true", help="fewer samples (smoke test)")
    args = ap.parse_args()

    result = measure(quick=args.quick)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "latest.json").write_text(json.dumps(result, indent=2) + "\n")
    path = baseline_path()
    baseline = json.loads(path.read_text()) if path.exists() else None
    print(report(result, baseline))
    print(f"\nmachine: {result['meta']['cpu']} ({result['meta']['cores']} cores), python {result['meta']['python']}")

    if args.record or (args.record_if_missing and baseline is None):
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n")
        print(f"baseline recorded -> {path.relative_to(ROOT.parent)}")
        return 0
    if args.check:
        if baseline is None:
            print("no baseline for this machine yet: run with --record first", file=sys.stderr)
            return 2
        bad = compare(result, baseline)
        if bad:
            print("\nPERFORMANCE REGRESSION (>20%):", *bad, sep="\n  ", file=sys.stderr)
            return 1
        print("\nno regression beyond 20%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
