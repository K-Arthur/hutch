"""Launch one Hutch app tree plus its benchmark control API (run as a script).

The harness executes this file by path with cwd=<tree> and
PYTHONPATH=<tree>/src so 'import hutch' resolves *that* tree. The control API
lives in the same process as the app, which is the whole point: scripted SSE
bursts go through the app's own Store, so the in-process bus wakes the live run
stream immediately (a second process writing the SQLite file could not wake the
server's bus).

Usage: <python> _serve.py --state-dir DIR [--seed-bots 20] [--host 127.0.0.1]

It prints one JSON line {"ok": true, "port": ..., "control_port": ...} once both
servers are accepting connections. The harness then calls:

  POST /seed       {"bots": 20, "completed_events": 210, "live_seed_events": 5}
  POST /live_run   {"seed_events": 5}
  POST /burst      {"run_id": ..., "count": 6, "label": "burst-3-0"}
  POST /shutdown
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _free_port(host: str) -> int:
    """Reserve-then-release a loopback port for the app (the control port does the same)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class BenchState:
    """Mutable seed handles shared by the control handler (all calls serialized)."""

    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.bots = []
        self.completed_run_id = None
        self.initial_live_run_id = None
        self.burst_runs = []

    # ------------------------------------------------------------------ seed

    def seed(self, bots: int = 20, completed_events: int = 210,
             live_seed_events: int = 5) -> dict:
        from hutch.models import Bot, Event, EventType, Run, RunStatus

        started = time.monotonic()
        with self.lock:
            created = []
            for index in range(bots):
                bot = self.store.create_bot(Bot(
                    name=f"bench-bot-{index:02d}",
                    display_name=f"Bench Bot {index:02d}",
                    model="ollama/qwen3:4b",
                    tools=["shell", "files", "memory"],
                    description="Synthetic assistant for the dashboard live-update benchmark.",
                ))
                created.append(bot)
            self.bots = created

            completed = self.store.create_run(Run(
                bot_id=created[0].id,
                prompt="Completed benchmark transcript with a bounded 200-event window.",
                status=RunStatus.running,
                started_at=_utcnow_iso(),
            ))
            for index in range(completed_events):
                if index % 7 == 0:
                    event = Event(run_id=completed.id, type=EventType.message,
                                  data={"role": "assistant", "content": f"Completed transcript message {index}."})
                elif index % 11 == 0:
                    event = Event(run_id=completed.id, type=EventType.step,
                                  data={"n": index // 11 + 1, "model_ms": 40, "tool_ms": 10,
                                        "overhead_ms": 4, "queue_ms": 0})
                else:
                    event = Event(run_id=completed.id, type=EventType.log,
                                  data={"note": f"Completed transcript event {index}."})
                self.store.append_event(event)
            self.store.flush_events()
            completed.status = RunStatus.succeeded
            completed.finished_at = _utcnow_iso()
            completed.steps = max(1, completed_events // 11)
            self.store.update_run(completed)
            self.completed_run_id = completed.id

            live = self._create_live_run(live_seed_events, "uibseed-initial")
            self.initial_live_run_id = live["run_id"]
            return {
                "bots": [bot.name for bot in created],
                "bot_count": len(created),
                "completed_run_id": completed.id,
                "completed_events": completed_events,
                "live_run_id": live["run_id"],
                "live_seed_events": live_seed_events,
                "seed_ms": round((time.monotonic() - started) * 1000, 1),
            }

    def _create_live_run(self, seed_events: int, token: str = "") -> dict:
        from hutch.models import Event, EventType, Run, RunStatus

        bot = self.bots[1] if len(self.bots) > 1 else self.bots[0]
        run = self.store.create_run(Run(
            bot_id=bot.id,
            prompt="Live benchmark run: receives scripted SSE bursts.",
            status=RunStatus.running,
            started_at=_utcnow_iso(),
        ))
        for index in range(seed_events):
            note = f"Seed transcript note {index}." + (f" {token}" if token else "")
            self.store.append_event(Event(run_id=run.id, type=EventType.log, data={"note": note}))
        self.store.flush_events()
        self.store.flush_transcripts()
        self.burst_runs.append(run.id)
        return {"run_id": run.id, "seed_events": seed_events, "bot_name": bot.name}

    # --------------------------------------------------------------- burst

    def burst(self, run_id: str, count: int, label: str, token: str = "") -> dict:
        from hutch.models import Event, EventType

        with self.lock:
            queued_at = time.monotonic()
            for index in range(count):
                note = f"{label} note {index + 1} of {count}." + (f" {token}" if token else "")
                self.store.append_event(Event(
                    run_id=run_id, type=EventType.log, data={"note": note}))
            queued = time.monotonic()
            self.store.flush_events()
            committed = time.monotonic()
            return {
                "run_id": run_id,
                "count": count,
                "label": label,
                "queued_monotonic": queued_at,
                "queue_ms": round((queued - queued_at) * 1000, 3),
                "commit_monotonic": committed,
                "flush_ms": round((committed - queued) * 1000, 3),
            }


def _make_handler(state: BenchState, shutdown: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):  # noqa: A002 - silence access log
            return

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self):  # noqa: N802 - stdlib naming
            if self.path != "/health":
                self._send(404, {"error": "unknown path"})
                return
            self._send(200, {"ok": True, "pid": os.getpid(),
                             "bots": len(state.bots), "runs": len(state.burst_runs)})

        def do_POST(self):  # noqa: N802 - stdlib naming
            try:
                body = self._body()
                if self.path == "/seed":
                    self._send(200, {"ok": True, "seed": state.seed(
                        bots=int(body.get("bots", 20)),
                        completed_events=int(body.get("completed_events", 210)),
                        live_seed_events=int(body.get("live_seed_events", 5)))})
                elif self.path == "/live_run":
                    with state.lock:
                        live = state._create_live_run(int(body.get("seed_events", 5)),
                                                      str(body.get("token", "")))
                    self._send(200, {"ok": True, **live})
                elif self.path == "/burst":
                    self._send(200, {"ok": True, **state.burst(
                        str(body["run_id"]), int(body.get("count", 6)),
                        str(body.get("label", "burst")), str(body.get("token", "")))})
                elif self.path == "/shutdown":
                    self._send(200, {"ok": True})
                    shutdown.set()
                else:
                    self._send(404, {"error": "unknown path"})
            except Exception as error:  # keep harness failures readable
                traceback.print_exc(file=sys.stderr)
                self._send(500, {"ok": False, "error": f"{type(error).__name__}: {error}"})

    return Handler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hutch UI benchmark server.")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ready-file", default="")
    args = parser.parse_args(argv)

    os.environ["HUTCH_STATE_DIR"] = args.state_dir
    os.environ.setdefault("HUTCH_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
    os.environ.setdefault("HUTCH_MAX_CONCURRENT", "4")
    Path(args.state_dir).mkdir(parents=True, exist_ok=True)

    import uvicorn

    from hutch.server.app import create_app

    app = create_app()                      # creates app.state.store immediately
    state = BenchState(app.state.store)
    app_port = _free_port(args.host)
    server = uvicorn.Server(uvicorn.Config(
        app, host=args.host, port=app_port, log_level="error", lifespan="on", access_log=False))
    app_thread = threading.Thread(target=server.run, name="bench-app", daemon=True)
    app_thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        if not app_thread.is_alive():
            raise SystemExit("uvicorn thread exited before startup")
        time.sleep(0.02)
    if not server.started:
        raise SystemExit("uvicorn did not start within 30 seconds")

    shutdown = threading.Event()
    control = ThreadingHTTPServer((args.host, 0), _make_handler(state, shutdown))
    control.daemon_threads = True
    control_thread = threading.Thread(target=control.serve_forever, name="bench-control", daemon=True)
    control_thread.start()

    ready = {"ok": True, "port": app_port, "control_port": int(control.server_address[1]),
             "pid": os.getpid(), "app_thread_alive": app_thread.is_alive()}
    line = json.dumps(ready)
    print(line, flush=True)
    if args.ready_file:
        Path(args.ready_file).write_text(line + "\n", encoding="utf-8")

    try:
        while not shutdown.wait(0.25):
            if not app_thread.is_alive():
                break
    finally:
        try:
            server.should_exit = True
            app_thread.join(timeout=10)
        finally:
            control.shutdown()
    print(json.dumps({"ok": True, "stopped": True}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
