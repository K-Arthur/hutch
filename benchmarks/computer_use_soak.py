#!/usr/bin/env python3
"""Bounded soak for computer use: many observe/act cycles on the real browser and the isolated desktop.

Measures what the brief asks to be measured, separately from inference (there is no model in this loop):
  * wall time per step (observe, act+verify) as median / p90,
  * resident memory of the process tree (this process + browser driver + compositor + apps), sampled each cycle,
  * the run's frame-store size and frame count (must plateau: the store evicts),
  * whether a held key/button or a leftover process remains afterwards.

Run:  PYTHONPATH=src python benchmarks/computer_use_soak.py --cycles 60 --json out.json
Everything stays on loopback and in disposable sessions; nothing paid or personal is touched.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hutch import procguard  # noqa: E402
from hutch.computer.frames import FrameStore  # noqa: E402
from hutch.models import Bot  # noqa: E402
from hutch.tools.base import ProcRegistry  # noqa: E402

PAGE = (b"<!doctype html><title>soak</title><main><h1>Soak page</h1>"
        b"<label>Note <input id='note' name='note' autocomplete='off'></label>"
        b"<button id='go' type='button' onclick=\"document.title='clicked ' + Date.now()\">Go</button>"
        b"<canvas id='c' width='300' height='120' style='display:block'></canvas></main>")


class _H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(PAGE)
        self.close_connection = True

    def log_message(self, *_):
        pass


def rss_mb(pids: list[int]) -> float:
    total = 0
    for pid in pids:
        try:
            for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1])
                    break
        except OSError:
            pass
    return total / 1024.0


def tree_pids(root: int) -> list[int]:
    return [root] + [p.pid for p in procguard.descendants(root)]


def stats(values: list[float]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    return {"n": len(values), "median_ms": round(statistics.median(ordered), 1),
            "p90_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))], 1),
            "max_ms": round(ordered[-1], 1)}


class Gate:
    def decide(self, *a, **k):
        return None

    def cancelled(self):
        return False


def make_ctx(config, name: str, workspace: Path, **bot_kw):
    return SimpleNamespace(config=config, bot=Bot(name=name, **bot_kw), run=SimpleNamespace(id=f"run-{name}"),
                           workspace=workspace, gate=Gate(), dry_run=False, begin_effect=lambda: None,
                           emit=lambda e: None, on_finish=[], cancel_hooks=[], procs=ProcRegistry(), headless=True,
                           policy=SimpleNamespace(check_url=lambda u: __import__("hutch.safety", fromlist=["x"]).Decision(
                               __import__("hutch.safety", fromlist=["x"]).Verdict.allow, "soak", rule="allow:soak")))


def soak_browser(config, cycles: int) -> dict:
    from hutch.tools.browser import BrowserTool
    origin = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    origin.daemon_threads = True
    threading.Thread(target=origin.serve_forever, daemon=True).start()
    port = origin.server_address[1]
    workspace = Path(tempfile.mkdtemp(prefix="soak-ws-"))
    ctx = make_ctx(config, "soak-browser", workspace, local_dev_origins=[f"http://localhost:{port}"])
    tool = BrowserTool()
    observe_ms, act_ms, rss, frames_bytes, split = [], [], [], [], []
    store = FrameStore(config.run_dir("soak-browser", "run-soak-browser"))
    try:
        assert tool.run({"action": "goto", "url": f"http://localhost:{port}/"}, ctx).ok
        pids = tree_pids(os.getpid())
        for cycle in range(cycles):
            t = time.monotonic()
            obs = tool.run({"action": "observe"}, ctx)
            observe_ms.append((time.monotonic() - t) * 1000)
            assert obs.ok, obs.output
            frame_id = obs.data["observation"]["frame_id"]
            t = time.monotonic()
            if cycle % 3 == 0:
                res = tool.run({"action": "type", "selector": "#note", "text": f"cycle {cycle}"}, ctx)
            elif cycle % 3 == 1:
                res = tool.run({"action": "click", "selector": "#go"}, ctx)
            else:
                obs = tool.run({"action": "observe"}, ctx)
                res = tool.run({"action": "click_at", "frame_id": obs.data["observation"]["frame_id"], "x": 20, "y": 120},
                               ctx)
            act_ms.append((time.monotonic() - t) * 1000)
            assert res.ok, res.output
            usage = store.usage()
            frames_bytes.append(usage["bytes"])
            if cycle % 5 == 0 or cycle == cycles - 1:
                tree = tree_pids(os.getpid())
                rss.append(round(rss_mb(tree), 1))
                me = rss_mb([os.getpid()])
                driver = [d.pid for root in procguard.children(os.getpid()) for d in [root]]
                driver_mb = rss_mb([p for r in driver for p in [r]])
                browser_mb = rss_mb([p for p in tree if p != os.getpid() and p not in driver])
                split.append({"cycle": cycle, "python_mb": round(me, 1), "driver_mb": round(driver_mb, 1),
                              "browser_mb": round(browser_mb, 1)})
        return {"surface": "browser", "cycles": cycles, "observe": stats(observe_ms), "act_verify": stats(act_ms),
                "rss_mb_samples": rss, "rss_split": split, "frame_store_bytes_max": max(frames_bytes),
                "frame_store_final": store.usage()}
    finally:
        tool._teardown()
        origin.shutdown()


def soak_desktop(config, cycles: int) -> dict:
    from hutch.tools.computer import ComputerTool
    workspace = Path(tempfile.mkdtemp(prefix="soak-ws-"))
    (workspace / "soak.txt").write_text("")
    ctx = make_ctx(config, "soak-desktop", workspace, computer_apps=["kwrite"])
    tool = ComputerTool()
    step_ms, rss, frames_bytes = [], [], []
    store = FrameStore(config.run_dir("soak-desktop", "run-soak-desktop"))
    try:
        launched = tool.run({"action": "launch", "app": "kwrite", "path": "soak.txt"}, ctx)
        assert launched.ok, launched.output
        frame = launched.data["observation"]["frame_id"]
        for cycle in range(cycles):
            t = time.monotonic()
            if cycle % 2 == 0:
                res = tool.run({"action": "click", "frame_id": frame, "x": 640, "y": 400}, ctx)
            else:
                res = tool.run({"action": "type", "frame_id": frame, "text": "x"}, ctx)
            step_ms.append((time.monotonic() - t) * 1000)
            assert res.ok, res.output
            frame = res.data["observation"]["frame_id"]
            frames_bytes.append(store.usage()["bytes"])
            if cycle % 5 == 0 or cycle == cycles - 1:
                roots = [os.getpid()] + [p.pid for p in tool._desktop._procs if p.poll() is None]
                pids = []
                for root in roots:
                    pids.extend(tree_pids(root) if root != os.getpid() else [root])
                rss.append(round(rss_mb(sorted(set(pids))), 1))
        input_proc = tool._input._proc if tool._input is not None else None
        held_clean = tool._input is not None and tool._input.alive
        return {"surface": "desktop", "cycles": cycles, "act_observe_verify": stats(step_ms),
                "rss_mb_samples": rss, "frame_store_bytes_max": max(frames_bytes),
                "frame_store_final": store.usage(), "input_worker_alive": bool(held_clean),
                "input_worker_pid": getattr(input_proc, "pid", None)}
    finally:
        tool._shutdown(ctx)
        ctx.procs.kill_all(0.2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=40)
    parser.add_argument("--surface", choices=["browser", "desktop", "both"], default="both")
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    state = tempfile.mkdtemp(prefix="soak-state-")
    os.environ["HUTCH_STATE_DIR"] = state
    from hutch.config import get_config
    config = get_config()
    report: dict = {"python": sys.version.split()[0], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    started = time.monotonic()
    if args.surface in ("browser", "both"):
        report["browser"] = soak_browser(config, args.cycles)
    if args.surface in ("desktop", "both"):
        report["desktop"] = soak_desktop(config, args.cycles)
    report["elapsed_s"] = round(time.monotonic() - started, 1)
    leftovers = [p.pid for p in procguard.descendants(os.getpid())]
    report["leftover_descendants_at_exit"] = leftovers
    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        Path(args.json).write_text(text)
    return 0 if not leftovers else 1


if __name__ == "__main__":
    raise SystemExit(main())
