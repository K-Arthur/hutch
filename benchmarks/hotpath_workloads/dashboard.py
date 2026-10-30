"""Dashboard-scale read/serialization: seeded SQLite store (>=50 bots, >=10k events) through the
FastAPI app with an in-process TestClient (no network, isolated HUTCH_STATE_DIR).

Times the routes the dashboard polls at scale: GET /api/v1/snapshot (bounded consistent state),
GET /api/v1/tasks/runs/{run_id}/events (per-run event page), GET /api/v1/changes (change feed) and
GET /api/bots (roster aggregates). Response byte sizes are recorded so a JSON serialization cost
can be separated from SQL cost later.
"""

from __future__ import annotations

import os
import statistics

SAMPLES_FULL = 7
SAMPLES_QUICK = 3
BOTS_FULL, BOTS_QUICK = 60, 20
EVENTS_FULL, EVENTS_QUICK = 10_000, 2_000


def _seed(bots_n: int, events_n: int) -> tuple[list[str], str]:
    from hutch.config import get_config
    from hutch.models import Bot, Event, EventType, Run
    from hutch.store import Store

    store = Store(get_config())
    try:
        bots = [store.create_bot(Bot(name=f"dash-bot-{index:03d}", model="ollama/qwen3:8b",
                                     tools=["files", "memory", "shell"], description="seeded dashboard bot",
                                     instructions="seeded for dashboard-scale read benchmarks"))
                for index in range(bots_n)]
        runs = []
        for index, bot in enumerate(bots):
            for turn in range(2):
                runs.append(store.create_run(Run(bot_id=bot.id, prompt=f"seeded task {index}-{turn}")))
        for index in range(events_n):
            run = runs[index % len(runs)]
            kind = index % 4
            if kind == 0:
                data = {"role": "assistant", "content": f"step {index}: inspected the report and noted deltas"}
                event_type = EventType.message
            elif kind == 1:
                data = {"call_id": f"call_{index}", "tool": "files",
                        "arguments": '{"path":"reports/week-31.md"}'}
                event_type = EventType.tool_call
            elif kind == 2:
                data = {"call_id": f"call_{index}", "ok": True, "output": "report text " * 20}
                event_type = EventType.tool_result
            else:
                data = {"model_wait_ms": 100.0 + index % 900, "tool_ms": 10.0 + index % 40,
                        "overhead_ms": 0.3, "prompt_tokens": 3000 + index % 500}
                event_type = EventType.step
            store.append_event(Event(run_id=run.id, type=event_type, data=data))
        store.flush_events()
        busiest = max(runs, key=lambda run: len(store.list_events(run.id, limit=1000)))
        run_ids = [run.id for run in runs]
        store.close()
        return run_ids, busiest.id
    except Exception:
        store.close()
        raise


def _request_ms(client, path: str, samples: int) -> tuple[list[float], int, int]:
    first = client.get(path)
    if first.status_code != 200:
        raise RuntimeError(f"GET {path} -> {first.status_code}: {first.text[:300]}")
    samples_ms = []
    for _ in range(samples):
        import time
        started = time.perf_counter()
        response = client.get(path)
        samples_ms.append((time.perf_counter() - started) * 1000.0)
        if response.status_code != 200:
            raise RuntimeError(f"GET {path} -> {response.status_code}: {response.text[:300]}")
    return samples_ms, len(first.content), first.status_code


def run(quick: bool, state) -> list[dict]:
    from fastapi.testclient import TestClient

    from hutch.server.app import create_app

    samples = SAMPLES_QUICK if quick else SAMPLES_FULL
    bots_n = BOTS_QUICK if quick else BOTS_FULL
    events_n = EVENTS_QUICK if quick else EVENTS_FULL
    run_ids, busiest = _seed(bots_n, events_n)
    previous_hosts = os.environ.get("HUTCH_ALLOWED_HOSTS")
    os.environ["HUTCH_ALLOWED_HOSTS"] = (previous_hosts + ",testserver") if previous_hosts else "testserver"
    try:
        app = create_app()
    except BaseException:
        if previous_hosts is None:
            os.environ.pop("HUTCH_ALLOWED_HOSTS", None)
        else:
            os.environ["HUTCH_ALLOWED_HOSTS"] = previous_hosts
        raise
    cases: list[dict] = []
    try:
        client_context = TestClient(app)
    finally:
        pass
    with client_context as client:
        routes = [
            ("dashboard.snapshot_ms", "/api/v1/snapshot?limit=500", "bounded consistent state snapshot"),
            ("dashboard.run_events_500_ms",
             f"/api/v1/tasks/runs/{busiest}/events?limit=500", "per-run event page (500 events)"),
            ("dashboard.changes_ms", "/api/v1/changes", "change feed since the client cursor"),
            ("dashboard.roster_ms", "/api/bots", "roster aggregates for every bot"),
        ]
        for name, path, note in routes:
            route_samples, body_bytes, status = _request_ms(client, path, samples)
            cases.append({
                "name": name, "unit": "ms", "samples": route_samples, "better": "lower",
                "note": f"{note}; HTTP {status}, {body_bytes / 1024:.0f} KiB response, "
                        f"{bots_n} bots / {events_n:,} events",
                "detail": {"path": path, "response_bytes": body_bytes, "bots": bots_n,
                           "events": events_n, "us_per_event": route_samples[0] / events_n * 1e6},
            })
    if previous_hosts is None:
        os.environ.pop("HUTCH_ALLOWED_HOSTS", None)
    else:
        os.environ["HUTCH_ALLOWED_HOSTS"] = previous_hosts
    return cases
