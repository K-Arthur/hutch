"""Reproducible deterministic workflow engine soak for isolated state.

Run from the repository root with a fresh HUTCH_STATE_DIR. This exercises the real
saved-workflow admission and interpreter through the engine's thread executor. The
test-only scenario runtime is used for model-route readiness; the workflow plan itself
is evaluated by Hutch's production interpreter and makes no model or network calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from hutch.config import get_config
from hutch.models import Bot, RunStatus
from hutch.store import Store
from hutch.workflow import persistence as wstore
from hutch.workflow import submit as wfsubmit
from hutch.engine import Engine


PLAN = {
    "name": "deterministic-process-soak",
    "inputs": {},
    "envelope": {"tools": []},
    "budget": {"max_nodes": 2, "max_model_calls": 0, "max_fanout": 1},
    "nodes": [
        {"kind": "transform", "id": "value", "op": "constant", "args": {"value": 42}},
        {"kind": "verify", "id": "verified", "checks": [
            {"kind": "schema", "ref": "value", "schema": {"type": "integer", "minimum": 42}}
        ]},
    ],
    "outputs": ["value"],
}

SOURCES = (
    "src/hutch/engine.py",
    "src/hutch/store.py",
    "src/hutch/workflow/engine.py",
    "src/hutch/workflow/persistence.py",
    "src/hutch/workflow/runtime.py",
    "src/hutch/workflow/submit.py",
    "tests/support/runtime.py",
    "docs/realignment/artifacts/workflow-studio/workflow-soak-2026-10-11/workflow_process_soak.py",
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=600.0)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--run-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration_seconds <= 0 or args.interval_seconds <= 0:
        parser.error("duration and interval must be positive")
    if not os.environ.get("HUTCH_STATE_DIR"):
        parser.error("set HUTCH_STATE_DIR to a fresh disposable directory")

    # The app intentionally refuses to run mock/demo through its production worker.
    # Tests inject this scenario runtime only as a readiness fixture; WorkflowRuntime
    # remains the real interpreter for the saved declarative plan.
    os.environ["HUTCH_TESTING"] = "1"
    sys.path.insert(0, str(Path.cwd()))
    from hutch import engine as engine_module
    from hutch.runtime import get_runtime as production_runtime
    from tests.support.runtime import test_runtime_for
    engine_module.get_runtime = lambda bot: test_runtime_for(bot, production_runtime)

    config = get_config()
    if config.db_path.exists():
        parser.error(f"refusing to reuse existing state database: {config.db_path}")
    config.ensure()
    started_at = iso_now()
    started = time.monotonic()
    end_at = started + args.duration_seconds
    store = Store(config)
    engine = Engine(config, store, max_concurrent=1, executor="thread",
                    owner_id="dynamic-workflow-soak", light=True)
    bot = store.create_bot(Bot(name="workflow-soak", model="mock/demo", tools=[]))
    saved = wstore.save_definition(store, name=PLAN["name"], plan=PLAN,
                                   source="operator", activate=False)
    definition_id = str(saved["definition_id"])
    completed: list[dict[str, object]] = []
    total_ticks = 0
    peak_active_runs = 0
    failure: str | None = None
    next_start = started

    try:
        while time.monotonic() < end_at:
            now = time.monotonic()
            if now < next_start:
                engine.tick()
                total_ticks += 1
                time.sleep(min(1.0, next_start - now, end_at - now))
                continue

            run_started = time.monotonic()
            submission = wfsubmit.submit_saved(
                store, bot=bot, definition=definition_id, origin="operator")
            run_deadline = min(end_at, run_started + args.run_timeout_seconds)
            while time.monotonic() < run_deadline:
                engine.tick()
                total_ticks += 1
                peak_active_runs = max(peak_active_runs, len(store.active_runs()))
                view = wfsubmit.status(store, submission.workflow_run_id)
                status = str(view["workflow"]["status"])
                attempt = store.get_run(submission.attempt_run_id)
                if status in {"succeeded", "failed", "stopped", "outcome_unknown"}:
                    if status != "succeeded" or attempt is None or attempt.status != RunStatus.succeeded:
                        raise RuntimeError(f"workflow {submission.workflow_run_id} ended {status}: {view}")
                    outcome = view["workflow"]["result"]["output_outcomes"]
                    if outcome["verified"] != ["value"]:
                        raise RuntimeError(f"workflow output was not verified: {outcome}")
                    with store._lock:
                        model_requests = int(store._db.execute(
                            "SELECT COUNT(*) FROM usage_reservations WHERE workflow_run_id = ?",
                            (submission.workflow_run_id,)).fetchone()[0])
                    if model_requests:
                        raise RuntimeError(f"deterministic soak unexpectedly reserved {model_requests} model requests")
                    completed.append({
                        "workflow_run_id": submission.workflow_run_id,
                        "attempt_run_id": submission.attempt_run_id,
                        "elapsed_seconds": round(time.monotonic() - run_started, 3),
                        "status": status,
                        "verified_outputs": outcome["verified"],
                        "model_requests": model_requests,
                    })
                    print(json.dumps({"workflow_runs": len(completed),
                                      "elapsed_seconds": round(time.monotonic() - started, 1),
                                      "latest_status": status}, sort_keys=True), flush=True)
                    break
                time.sleep(0.05)
            else:
                raise TimeoutError(f"workflow {submission.workflow_run_id} exceeded the run timeout")

            next_start = run_started + args.interval_seconds
    except Exception as exc:  # persist the exact failure with the run history
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        elapsed = time.monotonic() - started
        try:
            engine.shutdown()
        finally:
            store.close()

    root = Path.cwd()
    payload = {
        "test": "deterministic saved-workflow process-executor soak",
        "started_at": started_at,
        "finished_at": iso_now(),
        "duration_seconds_requested": args.duration_seconds,
        "duration_seconds_actual": round(elapsed, 3),
        "interval_seconds": args.interval_seconds,
        "run_timeout_seconds": args.run_timeout_seconds,
        "python": sys.version,
        "platform": platform.platform(),
        "executor": "thread",
        "test_runtime": "tests.support.runtime.test_runtime_for; used only for route readiness",
        "workflow_interpreter": "production hutch.workflow.runtime.WorkflowRuntime",
        "max_concurrent": 1,
        "model_requests": 0,
        "network_requests": 0,
        "workflow_runs": len(completed),
        "engine_ticks": total_ticks,
        "peak_active_runs": peak_active_runs,
        "results": completed,
        "parent_max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "child_max_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "failure": failure,
        "source_sha256": {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in SOURCES
        },
        "state_dir": str(config.state_dir),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in (
        "finished_at", "duration_seconds_actual", "workflow_runs", "engine_ticks",
        "parent_max_rss_kib", "child_max_rss_kib", "failure")}, sort_keys=True), flush=True)
    return 0 if failure is None and len(completed) >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
