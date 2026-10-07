"""Scheduler loop sleeps until work exists (PF-5) and Stop really stops (UI-2)."""

from __future__ import annotations

import os
import threading
import time
from datetime import timedelta

from hutch.engine import MAX_SLEEP_SECONDS, Engine
from hutch.models import ApprovalMode, ApprovalRequest, Bot, RunStatus, Schedule, iso, utcnow
from hutch.store import Store


def _bot(name="loopbot", **kw) -> Bot:
    d = dict(name=name, model="mock/demo", tools=["shell", "files", "memory"],
             approval_mode=ApprovalMode.auto)
    d.update(kw)
    return Bot(**d)


# ------------------------------------------------------------- next_wakeup

def test_idle_engine_sleeps_for_the_safety_cap(store, config):
    engine = Engine(config, store)
    assert engine.next_wakeup() == MAX_SLEEP_SECONDS


def test_next_wakeup_is_time_to_next_scheduled_fire(store, config):
    store.create_bot(_bot(schedule=Schedule(cron="0 3 * * *", timezone="UTC")))
    engine = Engine(config, store)
    now = utcnow().replace(hour=2, minute=58, second=0, microsecond=0)
    assert abs(engine.next_wakeup(now) - 120) < 2


def test_sleep_is_capped_so_a_suspended_laptop_cannot_oversleep(store, config):
    """CLOCK_MONOTONIC stops during suspend; the cap bounds how late a due run can be after resume."""
    store.create_bot(_bot(schedule=Schedule(cron="0 3 * * *", timezone="UTC")))
    now = utcnow().replace(hour=1, minute=0, second=0, microsecond=0)
    assert Engine(config, store).next_wakeup(now) == MAX_SLEEP_SECONDS


def test_paused_bots_do_not_wake_the_loop(store, config):
    store.create_bot(_bot(schedule=Schedule(cron="* * * * *", timezone="UTC"), paused=True))
    assert Engine(config, store).next_wakeup() == MAX_SLEEP_SECONDS


def test_next_wakeup_honours_pending_approval_expiry(store, config):
    bot = store.create_bot(_bot())
    run = store.create_run(__import__("hutch.models", fromlist=["Run"]).Run(bot_id=bot.id, prompt="x"))
    soon = iso(utcnow() + timedelta(seconds=7))
    store.create_approval(ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="shell",
                                          action="rm x", expires_at=soon))
    assert 5 < Engine(config, store).next_wakeup() <= 7.5


# ------------------------------------------------------------------- loop

def test_idle_loop_does_not_spin(store, config):
    engine = Engine(config, store)
    ticks = []
    orig = engine.tick
    engine.tick = lambda: (ticks.append(time.monotonic()), orig())[1]
    stop = threading.Event()
    t = threading.Thread(target=engine.run_loop, args=(stop,), daemon=True)
    t.start()
    time.sleep(1.5)
    stop.set()
    store.bus.notify("work")
    t.join(timeout=3)
    assert len(ticks) <= 2, f"idle loop ticked {len(ticks)} times in 1.5s"


def test_new_work_wakes_a_sleeping_loop_immediately(store, config):
    engine = Engine(config, store)
    stop = threading.Event()
    t = threading.Thread(target=engine.run_loop, args=(stop,), daemon=True)
    t.start()
    time.sleep(0.3)  # loop is now parked on a 300 s sleep
    bot = store.create_bot(_bot(name="wakeme", schedule=Schedule(cron="* * * * *", timezone="UTC"),
                                created_at="2026-01-01T00:00:00+00:00"))
    deadline = time.time() + 5
    runs = []
    while time.time() < deadline and not runs:
        runs = store.list_runs(bot.id)
        time.sleep(0.05)
    stop.set()
    store.bus.notify("work")
    t.join(timeout=3)
    assert runs, "loop did not wake for a newly created, already-due bot"
    assert runs[0].origin == "schedule"


def test_finishing_run_frees_capacity_and_starts_the_queued_run(store, config):
    """No timer drives this: a run finishing notifies the bus and the loop dispatches the next."""
    a = store.create_bot(_bot(name="aaa"))
    b = store.create_bot(_bot(name="bbb"))
    engine = Engine(config, store, max_concurrent=1)
    stop = threading.Event()
    t = threading.Thread(target=engine.run_loop, args=(stop,), daemon=True)
    t.start()
    r1 = engine.submit(a, "research one")
    r2 = engine.submit(b, "research two")
    deadline = time.time() + 15
    while time.time() < deadline:
        if all(store.get_run(r.id).status is RunStatus.succeeded for r in (r1, r2)):
            break
        time.sleep(0.05)
    stop.set()
    store.bus.notify("work")
    t.join(timeout=3)
    assert store.get_run(r1.id).status is RunStatus.succeeded
    assert store.get_run(r2.id).status is RunStatus.succeeded


# ---------------------------------------------------------------- stop

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie is dead for our purposes
        return open(f"/proc/{pid}/stat").read().split(") ")[1][0] != "Z"
    except OSError:
        return False


def test_stop_kills_child_processes_not_just_the_loop(store, config, monkeypatch):
    import hutch.runtime.mock as mock_mod

    bot = store.create_bot(_bot(name="sleeper"))
    engine = Engine(config, store)

    def execute(self, run, ctx, tools, stop):
        # a shell that forks a long-running helper, like a build or a dev server
        tools["shell"].run({"command": "sleep 120 & echo $! > helper.pid; wait"}, ctx)
        return "done"

    monkeypatch.setattr(mock_mod.MockRuntime, "execute", execute)
    run = engine.submit(bot, "start a long job")
    engine.dispatch_pending()

    pidfile = None
    deadline = time.time() + 10
    while time.time() < deadline:
        r = store.get_run(run.id)
        if r.workspace and (pidfile := __import__("pathlib").Path(r.workspace) / "helper.pid").exists() \
                and pidfile.read_text().strip():
            break
        time.sleep(0.05)
    helper = int(pidfile.read_text().strip())
    assert _alive(helper)

    t0 = time.time()
    engine.stop_run(run.id)
    deadline = time.time() + 10
    while time.time() < deadline and store.get_run(run.id).status.value in ("running", "pending"):
        time.sleep(0.05)
    while time.time() < deadline and _alive(helper):
        time.sleep(0.05)

    assert store.get_run(run.id).status in (RunStatus.stopped, RunStatus.failed)
    assert not _alive(helper), "stop left the forked helper running"
    assert time.time() - t0 < 8


def test_stop_unblocks_a_run_waiting_for_approval(store, config, monkeypatch):
    import hutch.runtime.mock as mock_mod
    bot = store.create_bot(_bot(name="asker", approval_mode=ApprovalMode.ask))
    engine = Engine(config, store)
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    deadline = time.time() + 10
    while time.time() < deadline and store.get_run(run.id).status is not RunStatus.waiting_approval:
        time.sleep(0.05)
    assert store.get_run(run.id).status is RunStatus.waiting_approval

    t0 = time.time()
    engine.stop_run(run.id)
    deadline = time.time() + 10
    while time.time() < deadline and store.get_run(run.id).status is RunStatus.waiting_approval:
        time.sleep(0.05)
    assert time.time() - t0 < 3, "stop took too long to unblock the approval wait"
    assert store.pending_approvals() == []
    del mock_mod
