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


def test_supervisor_tick_compacts_the_resource_outbox_at_a_bounded_interval(store, config, monkeypatch):
    engine = Engine(config, store, light=True)
    calls = []
    monkeypatch.setattr(store, "prune_resource_changes", lambda keep: calls.append(keep) or 0)
    engine.tick()
    engine.tick()
    assert calls == [50_000]
    monkeypatch.setattr("hutch.engine.time.monotonic", lambda: engine._last_resource_change_prune + 301)
    engine.tick()
    assert calls == [50_000, 50_000]


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
    import tests.support.runtime as mock_mod

    bot = store.create_bot(_bot(name="sleeper"))
    engine = Engine(config, store)

    def execute(self, run, ctx, tools, stop):
        # a shell that forks a long-running helper, like a build or a dev server
        tools["shell"].run({"command": "sleep 120 & echo $! > helper.pid; wait"}, ctx)
        return "done"

    monkeypatch.setattr(mock_mod.TestScenarioRuntime, "execute", execute)
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
    while time.time() < deadline and not store.get_run(run.id).terminal:       # 'cancelling' is visible until teardown is verified
        time.sleep(0.05)
    while time.time() < deadline and _alive(helper):
        time.sleep(0.05)

    assert store.get_run(run.id).status in (RunStatus.stopped, RunStatus.failed)
    assert not _alive(helper), "stop left the forked helper running"
    assert time.time() - t0 < 8


def test_stop_unblocks_a_run_waiting_for_approval(store, config, monkeypatch):
    import tests.support.runtime as mock_mod
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


# ----------------------------------------------------------------- orphan recovery / shutdown

def test_a_run_whose_process_died_is_marked_interrupted_and_frees_its_bot(store, config):
    bot = store.create_bot(_bot(name="orphan-bot"))
    dead = store.create_run(__import__("hutch.models", fromlist=["Run"]).Run(
        bot_id=bot.id, prompt="x", status=RunStatus.running, owner="2147483646"))   # no such pid
    req = store.create_approval(ApprovalRequest(run_id=dead.id, bot_id=bot.id, tool="shell", action="rm x"))
    engine = Engine(config, store)
    recovered = engine.recover_orphans()
    assert [r.id for r in recovered] == [dead.id]
    fixed = store.get_run(dead.id)
    assert fixed.status is RunStatus.failed and fixed.exit_reason == "interrupted"
    assert "exited before it finished" in fixed.error
    assert store.get_approval(req.id).status.value == "expired"
    # the per-bot lock is released: a new run for this bot can start
    fresh = engine.submit(bot, "research again")
    engine.dispatch_pending()
    deadline = time.time() + 10
    while time.time() < deadline and store.get_run(fresh.id).status is not RunStatus.succeeded:
        time.sleep(0.05)
    assert store.get_run(fresh.id).status is RunStatus.succeeded


def test_runs_owned_by_a_live_process_are_never_touched(store, config):
    bot = store.create_bot(_bot(name="live-bot"))
    mine = store.create_run(__import__("hutch.models", fromlist=["Run"]).Run(
        bot_id=bot.id, prompt="x", status=RunStatus.running, owner=str(os.getpid())))
    queued = store.create_run(__import__("hutch.models", fromlist=["Run"]).Run(bot_id=bot.id, prompt="y"))
    assert Engine(config, store).recover_orphans() == []
    assert store.get_run(mine.id).status is RunStatus.running and store.get_run(queued.id).status is RunStatus.pending


def test_shutdown_lets_in_flight_runs_record_their_outcome(store, config):
    bot = store.create_bot(_bot(name="down-bot", approval_mode=ApprovalMode.ask))
    engine = Engine(config, store)
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    deadline = time.time() + 10
    while time.time() < deadline and store.get_run(run.id).status is not RunStatus.waiting_approval:
        time.sleep(0.05)
    engine.shutdown(timeout=8)
    assert store.get_run(run.id).status in (RunStatus.stopped, RunStatus.failed)   # recorded, not left 'running'
