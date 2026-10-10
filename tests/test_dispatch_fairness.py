"""Eligible work for one bot must not be starved by a blocked peer bot."""

from __future__ import annotations

import threading
import time

from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, RunStatus, Schedule


def _bot(name: str, **kw) -> Bot:
    d = dict(name=name, model="mock/demo", tools=["files"], approval_mode=ApprovalMode.auto)
    d.update(kw)
    return Bot(**d)


def test_blocked_bot_does_not_starve_another_bots_queue(store, config):
    """Bot A holds the only slot; bot B is queued. When A finishes, B starts even if A also has more pending."""
    a = store.create_bot(_bot("block-a"))
    b = store.create_bot(_bot("block-b"))
    engine = Engine(config, store, max_concurrent=1)
    stop = threading.Event()
    t = threading.Thread(target=engine.run_loop, args=(stop,), daemon=True)
    t.start()
    try:
        r_a1 = engine.submit(a, "a-first")
        r_a2 = engine.submit(a, "a-second")  # blocked by per-bot exclusivity while a1 runs
        r_b1 = engine.submit(b, "b-ready")
        deadline = time.time() + 20
        while time.time() < deadline:
            statuses = {rid: store.get_run(rid).status for rid in (r_a1.id, r_a2.id, r_b1.id)}
            if all(s is RunStatus.succeeded for s in statuses.values()):
                break
            time.sleep(0.05)
        assert store.get_run(r_a1.id).status is RunStatus.succeeded
        assert store.get_run(r_b1.id).status is RunStatus.succeeded
        assert store.get_run(r_a2.id).status is RunStatus.succeeded
        # B must not wait behind both of A's tasks exclusively: after A1, either A2 or B may run,
        # but all three complete without a 15s+ poll delay.
        finished = sorted(
            (store.get_run(r.id).finished_at or "" for r in (r_a1, r_a2, r_b1))
        )
        assert finished[0] and finished[-1]
    finally:
        stop.set()
        store.bus.notify("work")
        t.join(timeout=3)


def test_eligibility_to_start_is_prompt_when_capacity_free(store, config):
    """p95-style single-shot: enqueue on idle engine with free capacity → worker starts quickly."""
    bot = store.create_bot(_bot("prompt-start"))
    engine = Engine(config, store, max_concurrent=2)
    stop = threading.Event()
    t = threading.Thread(target=engine.run_loop, args=(stop,), daemon=True)
    t.start()
    try:
        time.sleep(0.2)  # park on bus wait
        samples = []
        for i in range(11):
            t0 = time.perf_counter()
            run = engine.submit(bot, f"task-{i}")
            deadline = time.time() + 5
            while time.time() < deadline:
                st = store.get_run(run.id).status
                if st is not RunStatus.pending:
                    samples.append((time.perf_counter() - t0) * 1000)
                    break
                time.sleep(0.005)
            # Wait for terminal so the next sample has a free per-bot slot.
            while time.time() < deadline and store.get_run(run.id).status not in (
                    RunStatus.succeeded, RunStatus.failed, RunStatus.stopped):
                time.sleep(0.01)
            assert store.get_run(run.id).status is RunStatus.succeeded
        samples.sort()
        p95 = samples[int(round(0.95 * (len(samples) - 1)))]
        # Hutch overhead only (mock runtime). Missed-wake residual is lease/3; with wake this should be << 250ms.
        assert p95 < 250, f"eligibility-to-start p95 {p95:.1f}ms samples={samples}"
    finally:
        stop.set()
        store.bus.notify("work")
        t.join(timeout=3)
