"""Capacity must stay occupied while recorded processes are unreaped (even after terminal status)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

from hutch.models import ApprovalMode, Bot, Run, RunStatus, Task
from hutch.store import Store


def test_open_run_procs_block_a_new_claim_after_terminal(store: Store):
    bot = store.create_bot(Bot(name="cap-a", model="mock/demo", tools=["files"], approval_mode=ApprovalMode.auto))
    finished = store.submit_run(
        Run(bot_id=bot.id, prompt="done", status=RunStatus.succeeded),
        Task(bot_id=bot.id, prompt="done"),
    )
    # Simulate a lingering recorded worker after the run row went terminal.
    store.add_proc(finished.id, pid=os.getpid(), pgid=os.getpid(), starttime=1, kind="worker")
    assert store.occupying_capacity(finished.id)

    queued = store.submit_run(Run(bot_id=bot.id, prompt="next"), Task(bot_id=bot.id, prompt="next"))
    assert store.claim_run(queued.id, "owner-b", 30, max_live=2) is None

    store.close_procs(finished.id)
    assert not store.occupying_capacity(finished.id)
    claimed = store.claim_run(queued.id, "owner-b", 30, max_live=2)
    assert claimed is not None and claimed.id == queued.id


def test_stubborn_grandchild_keeps_global_slot_until_reaped(store: Store, tmp_path):
    """A child that ignores SIGTERM still occupies capacity until the registry ends it."""
    bot_a = store.create_bot(Bot(name="slot-a", model="mock/demo", tools=["shell"], approval_mode=ApprovalMode.auto))
    bot_b = store.create_bot(Bot(name="slot-b", model="mock/demo", tools=["shell"], approval_mode=ApprovalMode.auto))
    run_a = store.submit_run(Run(bot_id=bot_a.id, prompt="hold"), Task(bot_id=bot_a.id, prompt="hold"))
    claimed = store.claim_run(run_a.id, "sup", 30, max_live=1)
    assert claimed is not None
    store.transition_run(run_a.id, RunStatus.running, fence=claimed.fence)

    # Detached child that ignores TERM and keeps the pipe open briefly.
    script = tmp_path / "stubborn.py"
    script.write_text(
        "import os, signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(30)\n"
    )
    child = subprocess.Popen([sys.executable, "-I", str(script)], start_new_session=True)
    try:
        identity_start = 1
        try:
            with open(f"/proc/{child.pid}/stat") as fh:
                identity_start = int(fh.read().split(")")[-1].split()[19])
        except OSError:
            pass
        store.add_proc(run_a.id, child.pid, child.pid, identity_start, "tool")
        live = store.get_run(run_a.id)
        store.transition_run(run_a.id, RunStatus.succeeded, fence=live.fence,
                             fields={"reason": "cleanup pending"})
        # Terminal, but unreaped proc still holds the sole global slot.
        run_b = store.submit_run(Run(bot_id=bot_b.id, prompt="wait"), Task(bot_id=bot_b.id, prompt="wait"))
        assert store.claim_run(run_b.id, "sup", 30, max_live=1) is None

        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
        store.end_proc(run_a.id, child.pid)
        assert store.claim_run(run_b.id, "sup", 30, max_live=1) is not None
    finally:
        if child.poll() is None:
            os.kill(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
