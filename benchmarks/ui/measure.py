"""CLI: paired/interleaved browser A/B for dashboard live-update performance.

    PYTHONPATH=$PWD/src <venv>/bin/python -m benchmarks.ui.measure \
        --a-tree <ROOT> [--b-tree <ROOT>] [--reps N] \
        [--viewports 1440x900,900x900,360x800] [--out DIR] [--single-tree]

Each tree is served by its own subprocess (benchmarks.ui._serve) with an
isolated HUTCH_STATE_DIR and PYTHONPATH=<tree>/src, seeded with >=20 bots, a
completed run with >=200 events, and a live run created per measured rep.
Reps are interleaved A/B/B/A when --b-tree is given, so both sides see the same
host load in adjacent time windows. Load average is recorded before and after
every rep; a rep over the pre-registered ceiling is retried once and its first
attempt is kept in the raw evidence, flagged discarded.

Single-tree mode (default when --b-tree is omitted) is the pre-change baseline.
Passing the same tree as --a-tree and --b-tree produces an A=A paired run, which
is how the harness estimates its own noise floor.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from . import browser as browser_driver
from . import report, summary

SERVE_SCRIPT = Path(__file__).with_name("_serve.py")
DEFAULT_VIEWPORTS = "1440x900,900x900,360x800"
DEFAULT_LOAD_CEILING = 24.0   # 3x the 8 threads; the host runs other agents, see README


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paired browser A/B for dashboard live updates.")
    parser.add_argument("--a-tree", required=True, help="tree served as side A (baseline)")
    parser.add_argument("--b-tree", default=None, help="tree served as side B (candidate)")
    parser.add_argument("--reps", type=int, default=3, help="reps per viewport per side (default 3)")
    parser.add_argument("--viewports", default=DEFAULT_VIEWPORTS)
    parser.add_argument("--out", default=str(Path(__file__).parent / "results"))
    parser.add_argument("--single-tree", action="store_true",
                        help="force single-side mode even if --b-tree is given")
    parser.add_argument("--bursts", type=int, default=8, help="scripted SSE bursts per rep")
    parser.add_argument("--burst-size", type=int, default=6, help="log events per burst")
    parser.add_argument("--seed-events", type=int, default=5, help="log seed events in each live run")
    parser.add_argument("--seed-bots", type=int, default=20)
    parser.add_argument("--completed-events", type=int, default=210)
    parser.add_argument("--load-ceiling", type=float, default=DEFAULT_LOAD_CEILING,
                        help="1-min load average ceiling; violators are retried once")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--label", default="ui-ab")
    parser.add_argument("--keep-state", action="store_true")
    parser.add_argument("--timeout", type=float, default=40.0, help="per page-interaction timeout (s)")
    return parser.parse_args(argv)


def _loadavg() -> list:
    try:
        return [round(float(part), 2) for part in Path("/proc/loadavg").read_text().split()[:3]]
    except OSError:
        return []


def _machine_metadata() -> dict:
    meta = {"platform": platform.platform(), "machine": platform.machine(),
            "python": sys.version.split()[0], "python_executable": sys.executable,
            "nproc": os.cpu_count()}
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                meta["cpu"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                meta["mem_total_gb"] = round(int(line.split()[1]) / 1024 / 1024, 1)
                break
    except OSError:
        pass
    try:
        from importlib.metadata import version
        meta["playwright"] = version("playwright")
    except Exception:
        meta["playwright"] = None
    return meta


def _git(tree: Path) -> dict:
    info = {"tree": str(tree)}
    for key, args in (("head", ["rev-parse", "HEAD"]),
                      ("branch", ["rev-parse", "--abbrev-ref", "HEAD"]),
                      ("describe", ["describe", "--always", "--dirty"])):
        try:
            result = subprocess.run(["git", "-C", str(tree)] + args, capture_output=True,
                                    text=True, timeout=20)
            info[key] = result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            info[key] = None
    try:
        dirty = subprocess.run(["git", "-C", str(tree), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=20)
        info["dirty"] = [line.strip() for line in dirty.stdout.splitlines() if line.strip()][:50]
    except (OSError, subprocess.SubprocessError):
        info["dirty"] = None
    return info


def _http_json(url: str, payload=None, timeout: float = 60.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="GET" if payload is None else "POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class Side:
    """One app tree served in its own process, with its own isolated state."""

    def __init__(self, name: str, tree: str, state_dir: Path):
        self.name = name
        self.tree = Path(tree).expanduser().resolve()
        self.state_dir = state_dir
        self.proc = None
        self.port = None
        self.control_port = None
        self.base_url = None
        self.control_url = None
        self._stdout: queue.Queue = queue.Queue()
        self._stderr: list = []
        self.git = _git(self.tree)
        self.seed_info = None

    # ------------------------------------------------------------ lifecycle

    def start(self, python: str, timeout: float = 120.0) -> None:
        if not (self.tree / "src" / "hutch").is_dir():
            raise RuntimeError("not a hutch tree (missing src/hutch): " + str(self.tree))
        env = os.environ.copy()
        env.update({
            "PYTHONPATH": str(self.tree / "src"),
            "HUTCH_STATE_DIR": str(self.state_dir),
            "HUTCH_ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
            "HUTCH_MAX_CONCURRENT": "4",
        })
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(
            [python, str(SERVE_SCRIPT), "--state-dir", str(self.state_dir)],
            cwd=str(self.tree), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1)
        threading.Thread(target=self._pump_stdout, name="stdout-" + self.name, daemon=True).start()
        threading.Thread(target=self._pump_stderr, name="stderr-" + self.name, daemon=True).start()
        try:
            line = self._stdout.get(timeout=timeout)
        except queue.Empty:
            self.stop()
            raise RuntimeError("tree " + str(self.tree) + " did not print READY in "
                               + str(timeout) + "s; stderr tail:\n" + "".join(self._stderr[-40:]))
        info = json.loads(line)
        self.port = int(info["port"])
        self.control_port = int(info["control_port"])
        self.base_url = "http://127.0.0.1:" + str(self.port)
        self.control_url = "http://127.0.0.1:" + str(self.control_port)
        self._wait_ready()

    def _pump_stdout(self) -> None:
        for line in self.proc.stdout:  # type: ignore[union-attr]
            self._stdout.put(line.strip())

    def _pump_stderr(self) -> None:
        for line in self.proc.stderr:  # type: ignore[union-attr]
            self._stderr.append(line)

    def _wait_ready(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("app process exited during startup; stderr tail:\n"
                                   + "".join(self._stderr[-40:]))
            try:
                _http_json(self.base_url + "/api/overview", timeout=2.0)
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("app did not answer /api/overview within " + str(timeout) + "s")

    def seed(self, bots: int, completed_events: int, live_seed_events: int) -> None:
        self.seed_info = _http_json(self.control_url + "/seed", {
            "bots": bots, "completed_events": completed_events,
            "live_seed_events": live_seed_events})["seed"]

    def new_live_run(self, seed_events: int, token: str = "") -> dict:
        return _http_json(self.control_url + "/live_run",
                          {"seed_events": seed_events, "token": token})

    def burst(self, run_id: str, count: int, label: str, token: str = "") -> dict:
        return _http_json(self.control_url + "/burst",
                          {"run_id": run_id, "count": count, "label": label, "token": token},
                          timeout=60.0)

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.poll() is None:
                _http_json(self.control_url + "/shutdown", {}, timeout=5.0)
        except Exception:
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)


def parse_viewports(raw: str) -> list:
    viewports = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        width, height = chunk.lower().split("x")
        viewports.append({"label": width + "x" + height,
                          "width": int(width), "height": int(height)})
    if not viewports:
        raise SystemExit("no viewports parsed from " + raw)
    return viewports


def build_sequence(mode: str, reps: int) -> list:
    """Interleave sides: single-tree A,A,A; paired A,B,B,A,A,B (ABBA groups)."""
    if mode == "single":
        return [("A", index) for index in range(reps)]
    pattern = ["A", "B", "B", "A"]
    raw = []
    while len(raw) < 2 * reps:
        raw.extend(pattern)
    raw = raw[:2 * reps]
    counters = {"A": 0, "B": 0}
    sequence = []
    for side in raw:
        sequence.append((side, counters[side]))
        counters[side] += 1
    return sequence


def _measure_position(browser, side: Side, viewport: dict, rep: int, order: int,
                      args: argparse.Namespace, screenshot_path, out_dir: Path) -> dict:
    load_before = _loadavg()
    started = time.monotonic()
    measurement = browser_driver.measure_rep(
        browser, side, base_url=side.base_url, viewport={"width": viewport["width"],
                                                         "height": viewport["height"]},
        rep_index=rep, bursts=args.bursts, burst_size=args.burst_size,
        seed_events=args.seed_events, screenshot_path=screenshot_path,
        timeout_ms=int(args.timeout * 1000))
    duration = time.monotonic() - started
    load_after = _loadavg()
    ceiling = args.load_ceiling
    discarded = bool((load_before and load_before[0] > ceiling)
                     or (load_after and load_after[0] > ceiling))
    return {
        "side": side.name,
        "tree": str(side.tree),
        "viewport": viewport["label"],
        "viewport_px": {"width": viewport["width"], "height": viewport["height"]},
        "rep": rep,
        "order": order,
        "attempt": 0,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_s": round(duration, 2),
        "loadavg_before": load_before,
        "loadavg_after": load_after,
        "discarded": discarded,
        "screenshot": (str(Path(screenshot_path).relative_to(out_dir))
                       if screenshot_path else None),
        "measurement": measurement,
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    screenshots = out / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    state_root = Path(tempfile.mkdtemp(prefix=".state-", dir=str(out)))
    mode = "paired" if (args.b_tree and not args.single_tree) else "single"
    viewports = parse_viewports(args.viewports)
    sequence = build_sequence(mode, args.reps)

    sides = {"A": Side("A", args.a_tree, state_root / "A")}
    if mode == "paired":
        sides["B"] = Side("B", args.b_tree, state_root / "B")
    raw_reps = []
    errors = []
    browser_metadata = {}
    load_start = _loadavg()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    try:
        for side in sides.values():
            print("starting tree " + side.name + ": " + str(side.tree), flush=True)
            side.start(args.python)
            side.seed(args.seed_bots, args.completed_events, args.seed_events)
            print("  seeded: " + json.dumps(side.seed_info), flush=True)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser, browser_metadata = browser_driver.launch(playwright)
            for viewport in viewports:
                for order, (side_name, rep) in enumerate(sequence):
                    side = sides[side_name]
                    screenshot_path = None
                    if rep == 0:
                        screenshot_path = str(screenshots / (side_name + "-" + viewport["label"] + ".png"))
                    attempts = []
                    for attempt in range(2):
                        print("measuring " + side_name + " " + viewport["label"] + " rep " + str(rep)
                              + (" (retry)" if attempt else ""), flush=True)
                        try:
                            record = _measure_position(browser, side, viewport, rep, order,
                                                       args, screenshot_path, out)
                        except Exception as error:  # keep going: one bad rep must not lose the run
                            errors.append({"side": side_name, "viewport": viewport["label"],
                                           "rep": rep, "error": f"{type(error).__name__}: {error}"})
                            break
                        record["attempt"] = attempt
                        attempts.append(record)
                        raw_reps.append(record)
                        if not record["discarded"]:
                            break
                        print("  load " + str(record["loadavg_before"]) + " over ceiling "
                              + str(args.load_ceiling) + "; retrying once", flush=True)
                    if attempts and record["discarded"]:
                        print("  kept discarded attempt after retry", flush=True)
            browser.close()
    finally:
        for side in sides.values():
            try:
                side.stop()
            except Exception as error:
                errors.append({"side": side.name, "stop_error": f"{type(error).__name__}: {error}"})
        if not args.keep_state:
            shutil.rmtree(state_root, ignore_errors=True)

    finished_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    payload = {
        "schema": 1,
        "kind": "hutch-ui-browser-ab",
        "label": args.label,
        "mode": mode,
        "command": " ".join([sys.executable, "-m", "benchmarks.ui.measure"] + sys.argv[1:]),
        "started_at": started_at,
        "finished_at": finished_at,
        "repo_root": str(repo_root),
        "config": {
            "viewports": viewports, "reps": args.reps, "bursts_per_rep": args.bursts,
            "burst_size_events": args.burst_size, "seed_live_events": args.seed_events,
            "seed_bots": args.seed_bots, "completed_run_events": args.completed_events,
            "load_ceiling": args.load_ceiling, "timeout_s": args.timeout,
            "sequence": [{"order": order, "side": side, "rep": rep}
                         for order, (side, rep) in enumerate(sequence)],
            "python": args.python,
        },
        "machine": {**_machine_metadata(), "loadavg_start": load_start,
                    "loadavg_end": _loadavg(), "browser": browser_metadata},
        "sides": {name: {"tree": str(side.tree), "git": side.git, "seed": side.seed_info,
                         "port": side.port}
                  for name, side in sides.items()},
        "raw_reps": raw_reps,
        "errors": errors,
    }
    payload["analysis"] = report.analyze(payload)
    output = out / (args.label + "-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("wrote " + str(output), flush=True)
    summary.print_summary(payload)
    return 0 if raw_reps else 1


if __name__ == "__main__":
    sys.exit(main())
