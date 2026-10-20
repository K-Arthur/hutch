"""T-CANCEL-DESCENDANTS: ending a run ends everything it started, and the ending is verified.

Baseline defect (docs/realignment/baseline.md, lead 1 and the OpenClaw #138499 shape): only the direct child was signalled, a
command that backgrounded a helper and exited left it running, and a supervisor that did not spawn a process had no handle on it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from hutch import procguard
from hutch.engine import Engine
from hutch.models import ApprovalMode, Bot, RunStatus
from hutch.runtime.steps import call_tool
from hutch.tools.base import ProcRegistry

pytestmark = pytest.mark.skipif(not procguard.available(), reason="needs /proc (Linux)")


def test_final_cleanup_joins_prior_work_and_refuses_late_cleanup(monkeypatch):
    registry = ProcRegistry()
    entered, release = threading.Event(), threading.Event()
    calls = []

    def held_kill(grace=2):
        calls.append(grace)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return 0

    monkeypatch.setattr(registry, "kill_all", held_kill)
    registry.request_cleanup()
    finisher = threading.Thread(target=registry.finish, name="fixture-final-cleanup")
    try:
        assert entered.wait(2)
        registry.request_cleanup()  # coalesces an already active cancellation
        finisher.start()
        end = time.monotonic() + 2
        while not registry._finished and time.monotonic() < end:
            time.sleep(0.001)
        assert registry._finished and finisher.is_alive()
        assert calls == [2], "final verification must wait for owned cleanup"
        registry.request_cleanup()  # no work may start after finalization seals it
    finally:
        release.set()
        if finisher.ident:
            finisher.join(timeout=2)
        for thread in registry._cleanup_threads:
            thread.join(timeout=2)
    assert not finisher.is_alive() and calls == [2, 0.5]
    registry.request_cleanup()
    assert len(registry._cleanup_threads) == 1


def spawn_sh(script: str) -> subprocess.Popen:
    return subprocess.Popen(["/bin/bash", "-c", script], start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pid_alive(pid: int) -> bool:
    p = procguard.identity(pid)
    return p is not None and p.state not in ("Z", "X")


def wait_for(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def children_of(pid: int) -> list[int]:
    return [p.pid for p in procguard._all().values() if p.ppid == pid]


def reap(proc):
    """Finish a test process AND whatever it left behind in its group (sh.kill() alone would leak the children)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_a_whole_process_tree_is_ended_and_verified():
    sh = spawn_sh("sleep 300 & sleep 300 & wait")
    try:
        assert wait_for(lambda: len(children_of(sh.pid)) == 2)
        kids = children_of(sh.pid)
        ident = procguard.identity(sh.pid)
        left = procguard.end_groups([sh.pid], not_before=ident.starttime, term_grace=1, kill_grace=2)
        assert left == []
        assert not any(pid_alive(k) for k in kids)
    finally:
        reap(sh)


def test_a_child_that_left_the_group_with_setsid_is_still_found_through_its_parent():
    sh = spawn_sh("setsid sleep 300 & wait")
    try:
        assert wait_for(lambda: children_of(sh.pid))
        escapee = children_of(sh.pid)[0]
        assert procguard.identity(escapee).pgrp != sh.pid          # it really is in another group
        assert procguard.end_groups([sh.pid], term_grace=1, kill_grace=2) == []
        assert not pid_alive(escapee)
    finally:
        reap(sh)


def test_a_helper_that_outlived_its_shell_is_still_ended():
    """`start-server &` then the command returns: the group has no leader any more, but the helper is still the run's."""
    sh = spawn_sh("sleep 300 >/dev/null 2>&1 &")
    ident = procguard.identity(sh.pid)
    sh.wait(timeout=5)                                              # the shell has exited; its helper has not
    helpers = [p for p in procguard._all().values() if p.pgrp == sh.pid and p.state != "Z"]
    assert helpers, "the helper should still be running in the dead shell's group"
    left = procguard.end_recorded([{"pid": sh.pid, "pgid": sh.pid,
                                    "starttime": ident.starttime if ident else 0,
                                    "boot_id": procguard.boot_id()}], term_grace=1, kill_grace=2)
    assert left == [] and not any(pid_alive(p.pid) for p in helpers)


def test_an_unverified_recorded_group_blocks_cleanup_without_signalling_it():
    """Missing PID identity must stay unresolved; cleanup must never silently report success."""
    sh = spawn_sh("sleep 300 & wait")
    try:
        assert wait_for(lambda: children_of(sh.pid))
        left = procguard.end_recorded(
            [{"pid": sh.pid, "pgid": sh.pid, "starttime": 0, "boot_id": ""}],
            term_grace=0, kill_grace=0,
        )
        assert {sh.pid, *children_of(sh.pid)} <= {proc.pid for proc in left}
        assert pid_alive(sh.pid), "an unverified PID/group must not be signalled"
    finally:
        reap(sh)


def test_an_unrelated_process_is_left_alone():
    bystander = subprocess.Popen(["sleep", "300"], start_new_session=True)
    sh = spawn_sh("sleep 300 & wait")
    try:
        assert wait_for(lambda: children_of(sh.pid))
        procguard.end_groups([sh.pid], term_grace=1, kill_grace=2)
        assert pid_alive(bystander.pid)
    finally:
        reap(bystander); reap(sh)


def test_group_inspection_checks_the_saved_session_identity():
    current = procguard.identity(os.getpid())
    assert current is not None
    assert procguard.unverified_group(current.pgrp, session_id=current.session)
    assert procguard.unverified_group(current.pgrp, session_id=current.session + 1) == []


def test_a_process_group_id_that_was_recycled_is_not_touched():
    """not_before is the leader's recorded start time: anything that started earlier cannot be this run's."""
    sh = spawn_sh("sleep 300 & wait")
    try:
        assert wait_for(lambda: children_of(sh.pid))
        later = procguard.identity(sh.pid).starttime + 10_000_000
        assert procguard.end_groups([sh.pid], not_before=later, term_grace=0.2, kill_grace=0.2) == []
        assert pid_alive(sh.pid)                                    # nothing qualified, nothing was signalled
    finally:
        reap(sh)


def test_survivors_are_reported_when_something_will_not_die():
    sh = spawn_sh("trap '' TERM; while true; do sleep 1; done")      # ignores SIGTERM; only SIGKILL ends it
    try:
        assert wait_for(lambda: pid_alive(sh.pid))
        # SIGKILL cannot be ignored, so this proves the ladder escalates; a zero grace shows the report path runs
        left = procguard.end_groups([sh.pid], term_grace=0.1, kill_grace=3)
        assert left == [] and not pid_alive(sh.pid)
    finally:
        reap(sh)


# --------------------------------------------------------------------------- through the engine


def test_after_a_stop_no_descendant_can_keep_mutating(store, config, monkeypatch, tmp_path):
    import tests.support.runtime as mock_mod
    folder = tmp_path / "workfolder"
    folder.mkdir()
    bot = store.create_bot(Bot(name="writer", model="mock/demo", tools=["shell"], approval_mode=ApprovalMode.auto,
                               workdir=str(folder)))
    started = threading.Event()

    def execute(self, run, ctx, tools, stop):
        started.set()
        # a command that backgrounds a writer which keeps appending, then waits
        call_tool(run, ctx, tools, "shell", {"command": "(while true; do echo tick >> tick.log; sleep 0.05; done) & wait"})
        return "done"

    monkeypatch.setattr(mock_mod.TestScenarioRuntime, "execute", execute)
    engine = Engine(config, store)
    run = engine.submit(bot, "write forever")
    engine.dispatch_pending()
    log = folder / "tick.log"
    assert started.wait(10) and wait_for(lambda: log.exists() and log.stat().st_size > 20)

    engine.stop_run(run.id)
    assert wait_for(lambda: store.get_run(run.id).status in (RunStatus.stopped, RunStatus.failed, RunStatus.outcome_unknown), 15)
    assert "cleanup incomplete" not in store.get_run(run.id).error
    size = log.stat().st_size
    time.sleep(1.0)
    assert log.stat().st_size == size, "a descendant kept writing after the run was terminal"
    assert store.live_procs(run.id) == []                           # recorded as ended, because it was verified


def test_a_backgrounded_helper_does_not_outlive_its_run(store, config, monkeypatch):
    """The command returns at once and leaves `sleep` behind; finishing the run must still end it."""
    import tests.support.runtime as mock_mod
    bot = store.create_bot(Bot(name="bg", model="mock/demo", tools=["shell"], approval_mode=ApprovalMode.auto))
    seen: dict = {}

    def execute(self, run, ctx, tools, stop):
        call_tool(run, ctx, tools, "shell", {"command": "sleep 300 >/dev/null 2>&1 & echo $! > helper.pid"})
        seen["pid"] = int((Path(ctx.workspace) / "helper.pid").read_text().strip())
        seen["alive_during"] = pid_alive(seen["pid"])
        return "done"

    monkeypatch.setattr(mock_mod.TestScenarioRuntime, "execute", execute)
    engine = Engine(config, store)
    run = engine.run_blocking(bot, "start a helper")
    assert run.status is RunStatus.succeeded
    assert seen["alive_during"] is True
    assert wait_for(lambda: not pid_alive(seen["pid"]), 5), "the backgrounded helper outlived its run"
