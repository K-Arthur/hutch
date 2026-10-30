"""SQLite event path: append_event throughput and list_events read latency at 1k / 10k events.

Each append sample writes to a fresh run of exactly N events (isolated HUTCH_STATE_DIR from the
runner), flushes, then reads the same run back through list_events. This is the production write
shape: per-event outbox intent transaction plus the batched canonical writer.
"""

from __future__ import annotations

import time

SAMPLES_FULL = 7
SAMPLES_QUICK = 3


def _open_store():
    from hutch.config import get_config
    from hutch.store import Store

    return Store(get_config())


def run(quick: bool, state) -> list[dict]:
    from hutch.models import Bot, Event, EventType, Run

    n = SAMPLES_QUICK if quick else SAMPLES_FULL
    sizes = [(500, "500")] if quick else [(1000, "1k"), (10000, "10k")]
    store = _open_store()
    try:
        bot = store.create_bot(Bot(name="bench-events"))
        cases: list[dict] = []
        for size, label in sizes:
            rates: list[float] = []
            read_ms: list[float] = []
            for sample in range(n):
                run = store.create_run(Run(bot_id=bot.id, prompt=f"bench-{label}-{sample}"))
                started = time.perf_counter()
                for index in range(size):
                    store.append_event(Event(run_id=run.id, type=EventType.log,
                                             data={"i": index, "text": "x" * 48}))
                store.flush_events()
                elapsed = time.perf_counter() - started
                rates.append(size / elapsed)
                started = time.perf_counter()
                events = store.list_events(run.id)
                read_ms.append((time.perf_counter() - started) * 1000.0)
                if len(events) != size:
                    raise RuntimeError(f"list_events returned {len(events)} of {size} events")
            cases.append({
                "name": f"store.append_{label}_ev_s", "unit": "ev/s", "samples": rates, "better": "higher",
                "note": f"append_event + flush_events, {size:,} events per run",
                "detail": {"batch_median_ms": 1000.0 * size / sorted(rates)[len(rates) // 2]},
            })
            cases.append({
                "name": f"store.list_events_{label}_ms", "unit": "ms", "samples": read_ms,
                "better": "lower", "note": f"flush + full list_events read of {size:,} events",
                "detail": {"events": size},
            })
        return cases
    finally:
        store.close()
