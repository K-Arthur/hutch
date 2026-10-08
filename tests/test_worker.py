"""The process executor (ADR-0001/0004): each run is its own OS process in its own session, so Stop is a real kill.

Baseline defect: the timeout path "killed" a run by abandoning a Python thread, which kept executing. These tests start real worker
processes and end them with real signals.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from hutch import procguard
from hutch.approvals import resolve_approval
from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, RunStatus
from hutch.store import Store

pytestmark = pytest.mark.skipif(not procguard.available(), reason="needs /proc (Linux)")
SRC = str(Path(__file__).resolve().parents[1] / "src")


def wait_for(cond, timeout=20.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()


def alive(pid: int) -> bool:
    p = procguard.identity(pid)
    return p is not None and p.state not in ("Z", "X")


@pytest.fixture()
def engine(store, config):
    e = Engine(config, store, executor="process")
    yield e
    e.stop_all()
    e.shutdown(timeout=5)


def asker(store, name="asker"):
    return store.create_bot(Bot(name=name, model="mock/demo", tools=["files", "memory"], approval_mode=ApprovalMode.ask))


def test_a_run_executes_in_its_own_process_and_finishes_cleanly(store, config, engine):
    bot = store.create_bot(Bot(name="auto", model="mock/demo", tools=["files", "memory"], approval_mode=ApprovalMode.auto))
    run = engine.submit(bot, "research the news and write a report")
    engine.dispatch_pending()
    assert wait_for(lambda: store.get_run(run.id).status is RunStatus.succeeded), store.get_run(run.id)
    done = store.get_run(run.id)
    assert done.owner and done.owner != str(os.getpid()), "the run executed in the supervisor's own process"
    assert done.pgid > 0 and done.pgid != os.getpgrp()                   # its own session / process group
    assert done.lease_owner == "" and done.exit_reason == "completed"
    assert (Path(done.workspace) / "report.md").exists()
    assert store.verify_chain(run.id)["ok"]
    transcript = config.run_dir("auto", run.id) / "transcript.jsonl"
    assert len(transcript.read_text().splitlines()) >= len(store.list_events(run.id))
    assert (config.run_dir("auto", run.id) / "worker.log").exists()
    assert wait_for(lambda: not alive(done.pgid), 10)                    # the worker process exited


def test_a_worker_refuses_a_run_it_was_not_given(store, config):
    bot = store.create_bot(Bot(name="auto", model="mock/demo", tools=["files"], approval_mode=ApprovalMode.auto))
    run = Engine(config, store).submit(bot, "x")                         # queued, never claimed
    env = dict(os.environ, HUTCH_STATE_DIR=str(config.state_dir))
    out = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {SRC!r}); from hutch.worker import main; "
                          f"sys.exit(main([{run.id!r}, '--owner', 'someone', '--fence', '1']))"],
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 3 and "not claimed" in out.stderr
    assert store.get_run(run.id).status is RunStatus.pending             # it did nothing to the run


def test_stop_from_another_engine_ends_the_worker_process(store, config, engine):
    bot = asker(store)
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    assert wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)
    pgid = store.get_run(run.id).pgid
    assert alive(pgid)

    Engine(config, store).stop_run(run.id)                               # a different process's engine: database intent only
    assert wait_for(lambda: store.get_run(run.id).status is RunStatus.stopped, 15)
    assert wait_for(lambda: not alive(pgid), 10), "the worker process was left running"
    assert store.get_run(run.id).exit_reason == "stopped"


def test_a_worker_killed_with_sigkill_is_recovered_at_once_not_after_the_lease(store, config, engine):
    bot = asker(store)
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    assert wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)
    pid = store.get_run(run.id).pgid
    t0 = time.time()
    os.kill(pid, signal.SIGKILL)                                         # power loss for this run
    assert wait_for(lambda: store.get_run(run.id).terminal, 10)
    assert time.time() - t0 < 6, "recovery waited for the 30 s lease instead of noticing the exit"
    r = store.get_run(run.id)
    # it was only waiting for a human: no effect had started, so this is a plain failure and NOT "outcome unknown"
    assert r.status is RunStatus.failed and r.exit_reason == "interrupted" and "exited" in r.error and r.lease_owner == ""
    assert store.pending_approvals() == []                               # its approval was expired, not left dangling


def test_a_worker_that_ignores_stop_is_escalated_to_sigkill(store, config, engine, monkeypatch):
    import hutch.engine as engine_mod
    monkeypatch.setattr(engine_mod, "CANCEL_GRACE_SECONDS", 0.5)         # TERM after ~2.5 s, KILL after ~5.5 s
    bot = asker(store)
    run = engine.submit(bot, "write a report")
    engine.dispatch_pending()
    assert wait_for(lambda: store.get_run(run.id).status is RunStatus.waiting_approval)
    pid = store.get_run(run.id).pgid
    os.kill(pid, signal.SIGSTOP)                                         # frozen: it cannot handle SIGTERM or poll the database
    try:
        engine.stop_run(run.id)
        assert wait_for(lambda: store.get_run(run.id).status is RunStatus.stopped, 20), store.get_run(run.id)
        assert wait_for(lambda: not alive(pid), 5)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    assert store.get_run(run.id).exit_reason == "stopped"


SUPERVISOR = """
    import sys, time
    sys.path.insert(0, {src!r})
    from hutch.config import get_config
    from hutch.store import Store
    from hutch.engine import Engine
    cfg = get_config(); st = Store(cfg); eng = Engine(cfg, st, executor="process", lease_seconds=2)
    run = eng.submit(st.get_bot("asker"), "write a report")
    eng.dispatch_pending()
    print("RUN", run.id, flush=True)
    time.sleep(300)
"""


def test_a_worker_outlives_a_dead_supervisor_and_is_adopted_by_the_next(store, config):
    asker(store)
    env = dict(os.environ, HUTCH_STATE_DIR=str(config.state_dir), PYTHONUNBUFFERED="1", HUTCH_LEASE_SECONDS="2")
    sup = subprocess.Popen([sys.executable, "-I", "-c", textwrap.dedent(SUPERVISOR).format(src=SRC)], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    worker_pgid = None
    try:
        run_id = sup.stdout.readline().split()[1]
        assert wait_for(lambda: store.get_run(run_id).status is RunStatus.waiting_approval)
        worker_pgid = store.get_run(run_id).pgid
        os.kill(sup.pid, signal.SIGKILL)                                 # the supervisor dies; the run is NOT its child any more
        sup.wait(timeout=10)
        assert alive(worker_pgid)

        time.sleep(6.5)                                                  # more than three lease periods (2 s each)
        mid = store.get_run(run_id)
        assert mid.status is RunStatus.waiting_approval, "a live worker's run was recovered while it was still running"
        assert mid.lease_owner != "" and alive(worker_pgid)
        assert Engine(config, store).recover_orphans() == []             # the next supervisor adopts it: hands off

        pending = [a for a in store.pending_approvals() if a.run_id == run_id]
        assert pending and resolve_approval(store, pending[0].id, approve=True, by="test")
        assert wait_for(lambda: store.get_run(run_id).status is RunStatus.succeeded, 20), store.get_run(run_id)
        assert wait_for(lambda: not alive(worker_pgid), 10)
    finally:
        if sup.poll() is None:
            sup.kill()
        if worker_pgid and alive(worker_pgid):
            os.kill(worker_pgid, signal.SIGKILL)
