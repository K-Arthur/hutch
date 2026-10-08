"""T-CROSS-PROCESS-STOP, late-worker fencing, T-HOST-SLEEP and T-RECEIPT-RECOVERY.

These use real processes. Baseline defect D1: ``hutch stop-all`` from another process printed "stop requested" and changed nothing,
because Stop flipped an in-memory flag in the calling process only.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, RunStatus, utcnow
from hutch.runtime.steps import call_tool
from hutch.store import Store

SRC = str(Path(__file__).resolve().parents[1] / "src")


def spawn(config, code: str) -> subprocess.Popen:
    env = dict(os.environ, HUTCH_STATE_DIR=str(config.state_dir), PYTHONUNBUFFERED="1")
    prelude = f"import sys; sys.path.insert(0, {SRC!r})\n"
    return subprocess.Popen([sys.executable, "-I", "-c", prelude + textwrap.dedent(code)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def wait_for(cond, timeout=15.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = cond()
        if v:
            return v
        time.sleep(step)
    return cond()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        return open(f"/proc/{pid}/stat").read().split(") ")[1][0] != "Z"
    except OSError:
        return False


OWNER_SCRIPT = """
    import time
    from hutch.config import get_config
    from hutch.store import Store
    from hutch.engine import Engine
    from hutch.models import RunStatus
    cfg = get_config(); st = Store(cfg); eng = Engine(cfg, st)
    bot = st.get_bot("asker")
    run = eng.submit(bot, "write a report")
    eng.dispatch_pending()
    print("RUN", run.id, flush=True)
    while st.get_run(run.id).status in (RunStatus.pending, RunStatus.running, RunStatus.waiting_approval, RunStatus.cancelling):
        time.sleep(0.05)
    print("FINAL", st.get_run(run.id).status.value, flush=True)
    eng.shutdown(timeout=3); st.close()
"""


def test_stop_from_another_process_ends_a_run_that_process_owns(store, config):
    store.create_bot(Bot(name="asker", model="mock/demo", tools=["files", "memory"], approval_mode=ApprovalMode.ask))
    owner = spawn(config, OWNER_SCRIPT)
    try:
        run_id = owner.stdout.readline().split()[1]
        assert wait_for(lambda: store.get_run(run_id).status is RunStatus.waiting_approval), "the owner never reached the approval"

        t0 = time.time()
        stopper = Engine(config, store)                       # a DIFFERENT process's engine: it owns no threads
        assert stopper.stop_run(run_id)
        assert store.get_run(run_id).status in (RunStatus.cancelling, RunStatus.stopped)   # recorded at once, not "requested"

        final = owner.stdout.readline().split()
        assert final == ["FINAL", "stopped"], (final, owner.stderr.read() if owner.poll() is not None else "")
        assert owner.wait(timeout=15) == 0
        assert time.time() - t0 < 10
        run = store.get_run(run_id)
        assert run.status is RunStatus.stopped and run.finished_at and run.lease_owner == ""
        assert store.pending_approvals() == [] or all(a.run_id != run_id for a in store.pending_approvals())
    finally:
        if owner.poll() is None:
            owner.kill()


def test_stop_all_from_a_cli_process_reaches_a_run_owned_by_the_daemon(store, config):
    """Same defect through the real CLI entry point, the way the baseline journey J7 reproduced it."""
    store.create_bot(Bot(name="asker", model="mock/demo", tools=["files", "memory"], approval_mode=ApprovalMode.ask))
    owner = spawn(config, OWNER_SCRIPT)
    try:
        run_id = owner.stdout.readline().split()[1]
        assert wait_for(lambda: store.get_run(run_id).status is RunStatus.waiting_approval)
        env = dict(os.environ, HUTCH_STATE_DIR=str(config.state_dir))
        hutch = Path(sys.executable).parent / "hutch"
        cli = subprocess.run([str(hutch), "stop-all"], env=env, capture_output=True, text=True, timeout=60)
        assert cli.returncode == 0 and "stop requested" in cli.stdout
        assert owner.stdout.readline().split() == ["FINAL", "stopped"]
        assert owner.wait(timeout=15) == 0
    finally:
        if owner.poll() is None:
            owner.kill()


def test_a_worker_that_lost_its_lease_is_fenced_and_cannot_change_the_outcome(store, config, monkeypatch):
    """A suspended laptop: the heartbeat stops, another process recovers the run, then the old worker wakes up."""
    import hutch.runtime.mock as mock_mod
    bot = store.create_bot(Bot(name="sleeper", model="mock/demo", tools=["files"], approval_mode=ApprovalMode.auto))
    release, entered, outcome = threading.Event(), threading.Event(), {}
    orig = mock_mod.MockRuntime.execute

    def slow(self, run, ctx, tools, stop):
        entered.set()
        release.wait(timeout=20)
        try:
            outcome["tool"] = call_tool(run, ctx, tools, "write_file", {"path": "late.txt", "content": "zombie"})   # a late action
            ctx.store.update_run(run)
        except Exception as exc:
            outcome["raised"] = type(exc).__name__
        return orig(self, run, ctx, tools, stop)

    monkeypatch.setattr(mock_mod.MockRuntime, "execute", slow)
    owner = Engine(config, store, lease_seconds=30)
    run = owner.submit(bot, "write a file")
    owner.dispatch_pending()
    assert entered.wait(10)
    owner._hb_stop.set()                                              # the process is "suspended": no more heartbeats
    store._db.execute("UPDATE runs SET lease_expires_at = ? WHERE id = ?",
                      ((utcnow() - timedelta(seconds=5)).isoformat(), run.id))
    store._db.commit()

    rescuer = Engine(config, store)                                   # another process notices the lapsed lease
    recovered = rescuer.recover_orphans()
    assert [r.id for r in recovered] == [run.id]
    after = store.get_run(run.id)
    assert after.status is RunStatus.failed and after.exit_reason == "interrupted" and after.fence >= 2
    n_events = len(store.list_events(run.id))

    release.set()                                                     # the old worker wakes up and carries on
    assert wait_for(lambda: "tool" in outcome or "raised" in outcome)
    time.sleep(1.0)
    final = store.get_run(run.id)
    assert final.status is RunStatus.failed and final.exit_reason == "interrupted"      # the zombie did not rewrite history
    assert "tool" in outcome and not outcome["tool"].ok               # its late write_file was refused at admission (fence)...
    assert "no longer owns" in outcome["tool"].output
    assert not (Path(final.workspace) / "late.txt").exists()          # ...so the effect did not happen
    assert len(store.list_events(run.id)) == n_events                 # and it added nothing to the transcript


def test_a_stopped_run_stays_cancelling_until_its_worker_unwinds(store, config, monkeypatch):
    """A thread cannot be killed safely, so cancellation stays visible until it exits and cannot write after terminal status."""
    import hutch.engine as engine_mod
    import hutch.runtime.mock as mock_mod
    monkeypatch.setattr(engine_mod, "CANCEL_GRACE_SECONDS", 0.3)
    bot = store.create_bot(Bot(name="stuck", model="mock/demo", tools=["files"], approval_mode=ApprovalMode.auto))
    release, entered = threading.Event(), threading.Event()
    late: dict = {}

    def stuck(self, run, ctx, tools, stop):
        entered.set()
        release.wait(timeout=30)                                      # ignores stop(): cannot be cancelled
        late["tool"] = call_tool(run, ctx, tools, "write_file", {"path": "after.txt", "content": "x"})
        return "late"

    monkeypatch.setattr(mock_mod.MockRuntime, "execute", stuck)
    engine = Engine(config, store)
    run = engine.submit(bot, "hang")
    engine.dispatch_pending()
    assert entered.wait(10)
    engine.stop_run(run.id)
    assert wait_for(lambda: store.get_run(run.id).status.value == "cancelling", timeout=5)
    assert store.get_run(run.id).status.value not in ("stopped", "failed", "outcome_unknown")
    release.set()
    assert wait_for(lambda: "tool" in late)
    assert wait_for(lambda: store.get_run(run.id).status.value in ("stopped", "failed", "outcome_unknown"), timeout=5)
    done = store.get_run(run.id)
    events = len(store.list_events(run.id))
    time.sleep(0.5)
    assert store.get_run(run.id).status is done.status
    assert not late["tool"].ok and "action was not started" in late["tool"].output
    assert len(store.list_events(run.id)) == events
    assert not (Path(done.workspace) / "after.txt").exists()


# ----------------------------------------------------------------------------- crash after an effect, before its receipt

CRASH_SCRIPT = """
    import time
    from pathlib import Path
    from hutch.config import get_config
    from hutch.store import Store
    from hutch.engine import Engine
    import hutch.runtime.mock as mock_mod
    from hutch.runtime.steps import call_tool
    def execute(self, run, ctx, tools, stop):
        # the effect: append to a log inside the bot's own folder, then keep working (so we can be killed mid-action)
        call_tool(run, ctx, tools, "shell", {"command": "echo hit >> effects.log && sleep 60"})
        return "never reached"
    mock_mod.MockRuntime.execute = execute
    cfg = get_config(); st = Store(cfg); eng = Engine(cfg, st, lease_seconds=2)
    bot = st.get_bot("deployer")
    run = eng.submit(bot, "deploy")
    eng.dispatch_pending()
    print("RUN", run.id, flush=True)
    time.sleep(120)
"""


def test_a_crash_after_an_effect_but_before_its_receipt_is_reported_and_never_replayed(store, config, tmp_path):
    folder = tmp_path / "deploy-folder"
    folder.mkdir()
    store.create_bot(Bot(name="deployer", model="mock/demo", tools=["shell"], approval_mode=ApprovalMode.auto,
                         workdir=str(folder)))
    proc = spawn(config, CRASH_SCRIPT)
    sleeper_pid = None
    try:
        run_id = proc.stdout.readline().split()[1]
        log = folder / "effects.log"
        assert wait_for(lambda: log.exists() and log.read_text().count("hit") == 1), "the effect never happened"
        doubt = wait_for(lambda: store.actions_in_doubt(run_id))
        assert [d["tool"] for d in doubt] == ["shell"] and "effects.log" in doubt[0]["summary"]
        recorded = wait_for(lambda: store.live_procs(run_id))                 # the owner recorded what it started
        assert len(recorded) == 1 and recorded[0]["kind"] == "shell"
        shell_pid = recorded[0]["pid"]
        assert _alive(shell_pid)

        os.kill(proc.pid, signal.SIGKILL)                             # power loss: no cleanup runs
        proc.wait(timeout=10)
        # the lease (2 s) lapses; a restarted supervisor ticks several times
        survivor = Engine(config, store)
        assert wait_for(lambda: survivor.recover_orphans() or store.get_run(run_id).status is RunStatus.outcome_unknown,
                        timeout=15)
        for _ in range(3):
            survivor.tick()
        time.sleep(0.5)

        run = store.get_run(run_id)
        assert run.status is RunStatus.outcome_unknown and run.exit_reason == "interrupted"
        assert "may have happened" in run.error and "effects.log" in run.error
        assert [d["tool"] for d in store.list_actions(run_id) if d["status"] == "unknown"] == ["shell"]
        assert log.read_text().count("hit") == 1, "the action was replayed after the crash"
        # the crashed owner's command was still running (its own session survives its parent); recovery ended it and says so
        assert wait_for(lambda: not _alive(shell_pid), 10), "recovery left the crashed owner's process running"
        assert store.live_procs(run_id) == []
        assert len(store.list_runs(bot_id=store.get_bot("deployer").id)) == 1, "a restart must not start a new run by itself"
    finally:
        if proc.poll() is None:
            proc.kill()
        # the shell's own session survives its parent; clean up the helper this test started
        import subprocess as sp
        out = sp.run(["pgrep", "-f", "echo hit >> effects.log"], capture_output=True, text=True).stdout.split()
        for pid in out:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (ProcessLookupError, ValueError):
                pass
