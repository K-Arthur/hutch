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
import base64
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


def instrument(obj, method, samples):
    original = getattr(obj, method)
    def measured(*args, **kwargs):
        started = time.monotonic()
        try:
            return original(*args, **kwargs)
        finally:
            samples.append((time.monotonic() - started) * 1000)
    setattr(obj, method, measured)


def handoff(lease):
    from hutch.computer.control import StaleControl
    lease.take_over("bounded soak: human intervention")
    try:
        lease.begin_action()
    except StaleControl:
        pass
    else:
        raise AssertionError("agent authority overlapped human ownership")
    lease.hand_back("bounded soak: explicit handback")


class Gate:
    def decide(self, *a, **k):
        return None

    def cancelled(self):
        return False


def make_ctx(config, name: str, workspace: Path, **bot_kw):
    return SimpleNamespace(config=config, bot=Bot(name=name, **bot_kw), run=SimpleNamespace(id=f"run-{name}"),
                           workspace=workspace, gate=Gate(), dry_run=False, begin_effect=lambda: None,
                           emit=lambda e: None, on_finish=[], cancel_hooks=[], procs=ProcRegistry(), headless=True,
                           policy=__import__("hutch.safety", fromlist=["PolicyEngine"]).PolicyEngine())


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
    capture_ms, semantic_ms, verify_ms, wire_ms, frame_bytes = [], [], [], [], []
    errors, navigation, takeovers = 0, 0, []
    report = {}
    store = FrameStore(config.run_dir("soak-browser", "run-soak-browser"))
    try:
        assert tool.run({"action": "goto", "url": f"http://localhost:{port}/"}, ctx).ok
        page = tool._tabs[tool._active_tab]
        instrument(page, "screenshot", capture_ms)
        instrument(page, "evaluate", semantic_ms)
        pids = tree_pids(os.getpid())
        for cycle in range(cycles):
            if cycle % 10 == 0:
                t = time.monotonic()
                handoff(tool._lease)
                takeovers.append((time.monotonic() - t) * 1000)
            if cycle % 7 == 0:
                assert tool.run({"action": "goto", "url": f"http://localhost:{port}/?cycle={cycle}"}, ctx).ok
                navigation += 1
            if cycle % 9 == 0:
                refused = tool.run({"action": "type", "selector": "#missing", "text": "must not substitute"}, ctx)
                assert not refused.ok and page.locator("#note").input_value() != "must not substitute"
                errors += 1
            t = time.monotonic()
            obs = tool.run({"action": "observe"}, ctx)
            observe_ms.append((time.monotonic() - t) * 1000)
            assert obs.ok, obs.output
            from hutch.computer.frames import ImageRef
            png = store.load(ImageRef.from_internal(obs.data["images"][0]))
            frame_bytes.append(len(png))
            t = time.monotonic()
            payload = json.dumps({"images": [base64.b64encode(png).decode()]})
            wire_ms.append((time.monotonic() - t) * 1000)
            assert len(payload) < 3000000
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
            t = time.monotonic()
            if cycle % 3 == 0:
                assert page.locator("#note").input_value() == f"cycle {cycle}"
            elif cycle % 3 == 1:
                assert page.title().startswith("clicked ")
            verify_ms.append((time.monotonic() - t) * 1000)
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
        from hutch.computer.budgets import profile_usage
        report = {"surface": "browser", "cycles": cycles, "observe": stats(observe_ms), "act_verify": stats(act_ms),
                "rss_mb_samples": rss, "rss_split": split, "frame_store_bytes_max": max(frames_bytes),
                "frame_store_final": store.usage(), "profile_final": profile_usage(config.browser_profile_dir(ctx.bot.id)),
                "capture_encode_driver_roundtrip": stats(capture_ms), "semantic_driver_roundtrip": stats(semantic_ms),
                "independent_state_verification": stats(verify_ms), "image_wire_serialization": stats(wire_ms),
                "image_bytes_max": max(frame_bytes), "navigation_count": navigation, "refused_missing_targets": errors,
                "lease_takeover_handback": stats(takeovers)}
        return report
    finally:
        t = time.monotonic()
        tool._emergency_stop()
        tool._teardown()
        report["stop_and_cleanup_ms"] = round((time.monotonic() - t) * 1000, 1)
        origin.shutdown()
        origin.server_close()


def soak_desktop(config, cycles: int) -> dict:
    from hutch.tools.computer import ComputerTool
    workspace = Path(tempfile.mkdtemp(prefix="soak-ws-"))
    (workspace / "soak.txt").write_text("")
    ctx = make_ctx(config, "soak-desktop", workspace, computer_apps=["kwrite"])
    tool = ComputerTool()
    step_ms, rss, frames_bytes = [], [], []
    capture_ms, input_ms, persist_ms, split, takeovers = [], [], [], [], []
    report = {}
    store = FrameStore(config.run_dir("soak-desktop", "run-soak-desktop"))
    try:
        launched = tool.run({"action": "launch", "app": "kwrite", "path": "soak.txt"}, ctx)
        assert launched.ok, launched.output
        instrument(tool._desktop, "capture_png", capture_ms)
        instrument(tool._session._frames, "save", persist_ms)
        for method in ("click", "type_text", "chord"):
            instrument(tool._input, method, input_ms)
        frame = launched.data["observation"]["frame_id"]
        for cycle in range(cycles):
            if cycle % 10 == 0:
                t = time.monotonic()
                handoff(tool._lease)
                takeovers.append((time.monotonic() - t) * 1000)
                fresh = tool.run({"action": "observe"}, ctx)
                assert fresh.ok, fresh.output
                frame = fresh.data["observation"]["frame_id"]
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
                compositor = [p.pid for proc in tool._desktop._procs[:2] for p in procguard.descendants(proc.pid)]
                compositor += [p.pid for p in tool._desktop._procs[:2]]
                split.append({"cycle": cycle, "python_mb": round(rss_mb([os.getpid()]), 1),
                              "compositor_bus_mb": round(rss_mb(sorted(set(compositor))), 1),
                              "apps_mb": round(rss_mb(sorted(set(pids) - set(compositor) - {os.getpid()})), 1)})
        saved = tool.run({"action": "key", "frame_id": frame, "keys": "ctrl+s"}, ctx)
        assert saved.ok, saved.output
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and (workspace / "soak.txt").read_text().rstrip("\n") != "x" * (cycles // 2):
            time.sleep(.05)
        assert (workspace / "soak.txt").read_text().rstrip("\n") == "x" * (cycles // 2), "actual saved editor state differs"
        input_proc = tool._input._proc if tool._input is not None else None
        input_state = tool._input._send({"cmd": "state"})
        assert input_state["held_keys"] == 0 and input_state["held_buttons"] == 0, "input remains held after the workflow"
        report = {"surface": "desktop", "cycles": cycles, "act_observe_verify": stats(step_ms),
                "rss_mb_samples": rss, "frame_store_bytes_max": max(frames_bytes),
                "frame_store_final": store.usage(), "input_worker_alive": tool._input.alive,
                "held_keys": input_state["held_keys"], "held_buttons": input_state["held_buttons"],
                "input_worker_pid": getattr(input_proc, "pid", None), "rss_split": split,
                "capture_encode_subprocess_roundtrip": stats(capture_ms), "input_acknowledgement": stats(input_ms),
                "frame_validate_persist": stats(persist_ms), "lease_takeover_handback": stats(takeovers),
                "saved_editor_chars": len((workspace / "soak.txt").read_text())}
        return report
    finally:
        t = time.monotonic()
        tool._emergency_stop()
        tool._shutdown(ctx)
        ctx.procs.kill_all(0.2)
        report["stop_and_cleanup_ms"] = round((time.monotonic() - t) * 1000, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=40)
    parser.add_argument("--surface", choices=["browser", "desktop", "both"], default="both")
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    if not 2 <= args.cycles <= 200:
        parser.error("cycles must be between 2 and 200")
    state = tempfile.mkdtemp(prefix="soak-state-")
    os.environ["HUTCH_STATE_DIR"] = state
    from hutch.config import get_config
    config = get_config()
    report: dict = {"python": sys.version.split()[0], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "model_server": "absent; loopback probe separately recorded", "inference": "not run",
                    "scope": "deterministic driver tasks; lease handoff, not HTTP/physical-phone latency",
                    "measurement_notes": "RSS sums may double-count shared mappings and are sampled. Capture includes encoding and protocol/file roundtrip; encoder CPU and transport are not separately instrumented."}
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
