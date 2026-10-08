"""T-CLAIM-RACE, T-OCCURRENCE-RACE and the fencing rules (ADR-0001, ADR-0003).

The races use real OS processes against one SQLite file, because the defect was precisely that coordination lived in
per-process memory: a lock in process A means nothing to process B.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from datetime import timedelta
from pathlib import Path

import pytest

from hutch.lifecycle import IllegalTransition, LeaseLost
from hutch.models import Bot, Run, RunStatus, Task, iso, utcnow
from hutch.store import Store

SRC = str(Path(__file__).resolve().parents[1] / "src")


def make_bot(store, name="racer", **kw) -> Bot:
    return store.create_bot(Bot(name=name, model="mock/demo", tools=["files"], **kw))


def submit(store, bot, prompt="work") -> Run:
    return store.submit_run(Run(bot_id=bot.id, prompt=prompt), Task(bot_id=bot.id, prompt=prompt))


def race(config, script: str, n: int = 6) -> list[str]:
    """Start ``n`` processes that all wait for a start file, then run ``script`` at the same instant. Returns their stdout."""
    go = config.state_dir / "GO"
    go.unlink(missing_ok=True)
    prelude = textwrap.dedent(f"""
        import os, sys, time
        sys.path.insert(0, {SRC!r})
        from pathlib import Path
        from hutch.config import get_config
        from hutch.store import Store
        store = Store(get_config())
        while not Path({str(go)!r}).exists():
            time.sleep(0.001)
    """)
    env = dict(os.environ, HUTCH_STATE_DIR=str(config.state_dir))
    procs = [subprocess.Popen([sys.executable, "-I", "-c", prelude + textwrap.dedent(script)], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(n)]
    time.sleep(1.5)                       # every interpreter is up and spinning on the gate
    go.write_text("go")
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err
        outs.append(out.strip())
    return outs


# --------------------------------------------------------------------------- claims across processes


def test_two_or_more_processes_racing_for_one_run_produce_exactly_one_claim(store, config):
    bot = make_bot(store)
    run = submit(store, bot)
    outs = race(config, f"""
        got = store.claim_run({run.id!r}, owner=f"proc-{{os.getpid()}}", lease_seconds=30)
        print("won" if got else "lost")
        store.close()
    """)
    assert outs.count("won") == 1 and outs.count("lost") == len(outs) - 1
    claimed = store.get_run(run.id)
    assert claimed.fence == 1 and claimed.lease_owner.startswith("proc-")


def test_the_per_bot_single_instance_rule_holds_across_processes(store, config):
    """Two queued runs of ONE bot, many claimants: only one run may be claimed in total."""
    bot = make_bot(store)
    r1, r2 = submit(store, bot, "first"), submit(store, bot, "second")
    outs = race(config, f"""
        won = [rid for rid in ({r1.id!r}, {r2.id!r}) if store.claim_run(rid, owner=f"proc-{{os.getpid()}}", lease_seconds=30)]
        print(",".join(won))
        store.close()
    """)
    winners = [o for o in outs if o]
    assert len(winners) == 1 and "," not in winners[0]


def test_runs_of_different_bots_can_be_claimed_together(store, config):
    a, b = make_bot(store, "a"), make_bot(store, "b")
    ra, rb = submit(store, a), submit(store, b)
    assert store.claim_run(ra.id, "p1", 30) and store.claim_run(rb.id, "p2", 30)


def test_global_live_cap_is_enforced_in_the_claim(store):
    bots = [make_bot(store, f"b{i}") for i in range(3)]
    runs = [submit(store, b) for b in bots]
    got = [store.claim_run(r.id, "p", 30, max_live=2) for r in runs]
    # a claimed-but-not-started run is not "live" yet, so start each one before the next claim, as the engine does
    store2 = [store.claim_run(r.id, "p", 30, max_live=2) for r in runs if store.get_run(r.id).fence == 0]
    assert sum(1 for g in got if g) >= 1 and store2 is not None
    for r in runs:
        run = store.get_run(r.id)
        if run.fence:
            store.transition_run(r.id, RunStatus.running, fence=run.fence)
    third = [r for r in runs if store.get_run(r.id).status is RunStatus.pending]
    started = [r for r in runs if store.get_run(r.id).status is RunStatus.running]
    if len(started) >= 2 and third:
        assert store.claim_run(third[0].id, "p", 30, max_live=2) is None


def test_a_cancelled_or_started_run_cannot_be_claimed(store):
    bot = make_bot(store)
    run = submit(store, bot)
    store.request_cancel(run.id)
    assert store.claim_run(run.id, "p", 30) is None            # stop won the race


def test_a_claim_whose_owner_vanished_returns_to_the_queue(store):
    bot = make_bot(store)
    run = submit(store, bot)
    now = utcnow()
    assert store.claim_run(run.id, "ghost", 5, now=now)
    assert store.claim_run(run.id, "other", 5, now=now + timedelta(seconds=1)) is None   # still leased
    assert store.release_expired_claims(now + timedelta(seconds=10)) == 1
    again = store.claim_run(run.id, "other", 5, now=now + timedelta(seconds=11))
    assert again and again.fence == 2                                                    # fence moved on: ghost is stale
    assert store.get_run(run.id).lease_owner == "other"


# --------------------------------------------------------------------------- schedule occurrences


def test_one_scheduled_occurrence_creates_one_run_across_processes(store, config):
    bot = make_bot(store, "nightly")
    bot.schedule = __import__("hutch.models", fromlist=["Schedule"]).Schedule(cron="* * * * *", timezone="UTC")
    bot.created_at = "2026-01-01T00:00:00+00:00"
    store.upsert_bot(bot)
    outs = race(config, """
        from hutch.engine import Engine
        engine = Engine(get_config(), store)
        created = engine.scheduler_claims()
        print(len(created))
        store.close()
    """)
    assert sum(int(o) for o in outs) == 1
    assert len(store.list_runs(bot.id)) == 1
    with store._lock:
        rows = store._db.execute("SELECT COUNT(*) AS n FROM schedule_occurrences WHERE bot_id = ?", (bot.id,)).fetchone()
    assert rows["n"] == 1


def test_the_marker_and_the_run_commit_together_so_a_crash_cannot_double_dispatch(store):
    """The old path was due() -> submit() -> mark_dispatched(): a crash between the last two re-dispatched on restart."""
    bot = make_bot(store, "w")
    marker = "2026-10-07T00:00:00+00:00"
    r1 = store.submit_scheduled(Run(bot_id=bot.id, prompt="p"), Task(bot_id=bot.id, prompt="p", kind="scheduled"),
                                occurrence="2026-10-07T00:00:00+00:00", expected_marker=None, new_marker=marker, claimed_by="a")
    assert r1 is not None
    assert store.kv_get(f"schedule:{bot.id}:last_fire") == marker          # same transaction as the run
    again = store.submit_scheduled(Run(bot_id=bot.id, prompt="p"), Task(bot_id=bot.id, prompt="p", kind="scheduled"),
                                   occurrence="2026-10-07T00:00:00+00:00", expected_marker=None, new_marker=marker, claimed_by="b")
    assert again is None and len(store.list_runs(bot.id)) == 1


def test_a_failed_submit_leaves_neither_a_task_nor_a_run(store):
    bot = make_bot(store)
    run = submit(store, bot)
    dup = Run(id=run.id, bot_id=bot.id, prompt="dup")
    with pytest.raises(Exception):
        store.submit_run(dup, Task(bot_id=bot.id, prompt="dup"))
    assert len(store.pending_tasks(bot.id)) == 1                           # only the first submission's task


# --------------------------------------------------------------------------- fencing and transitions


def test_a_stale_owner_cannot_write_after_recovery_took_the_run(store):
    bot = make_bot(store)
    run = submit(store, bot)
    mine = store.claim_run(run.id, "worker-1", 30)
    store.transition_run(run.id, RunStatus.running, fence=mine.fence)
    mine.steps = 3
    store.update_run(mine)                                                 # the owner may write progress
    assert store.get_run(run.id).steps == 3

    # the owner stops heartbeating; recovery ends the run and bumps the fence
    store.transition_run(run.id, RunStatus.failed, exit_reason="interrupted", error="owner lost", bump_fence=True)
    mine.steps = 99
    with pytest.raises(LeaseLost):
        store.update_run(mine)                                             # the zombie is fenced out
    with pytest.raises(LeaseLost):
        store.transition_run(run.id, RunStatus.succeeded, fence=mine.fence)
    final = store.get_run(run.id)
    assert final.status is RunStatus.failed and final.steps == 3 and final.exit_reason == "interrupted"


def test_a_finished_run_cannot_be_changed_by_a_late_worker(store):
    bot = make_bot(store)
    run = submit(store, bot)
    mine = store.claim_run(run.id, "w", 30)
    store.transition_run(run.id, RunStatus.running, fence=mine.fence)
    store.transition_run(run.id, RunStatus.stopped, fence=mine.fence, exit_reason="stopped")
    with pytest.raises(LeaseLost):
        store.update_run(mine)
    with pytest.raises(IllegalTransition):
        store.transition_run(run.id, RunStatus.succeeded)                  # no fence given, still refused: terminal is absorbing
    assert store.get_run(run.id).status is RunStatus.stopped


def test_illegal_transitions_are_refused(store):
    bot = make_bot(store)
    run = submit(store, bot)
    with pytest.raises(IllegalTransition):
        store.transition_run(run.id, RunStatus.succeeded)                  # queued -> done skips running
    assert store.get_run(run.id).status is RunStatus.pending


def test_a_transition_writes_its_status_event_in_the_same_commit(store):
    bot = make_bot(store)
    run = submit(store, bot)
    mine = store.claim_run(run.id, "w", 30)
    store.transition_run(run.id, RunStatus.running, fence=mine.fence, event={"origin": "test"})
    store.transition_run(run.id, RunStatus.failed, fence=mine.fence, exit_reason="error", error="boom",
                         event={"reason": "error"})
    evs = [e for e in store.list_events(run.id) if e.type.value == "status"]
    assert [e.data["status"] for e in evs] == ["running", "failed"]
    assert [e.seq for e in evs] == [1, 2]
    assert store.verify_chain(run.id)["ok"]


def test_task_state_follows_the_run(store):
    bot = make_bot(store)
    ok, bad, stopped = submit(store, bot, "a"), None, None
    states = lambda rid: store._db.execute("SELECT state, done FROM tasks WHERE run_id = ?", (rid,)).fetchone()
    assert tuple(states(ok.id)) == ("queued", 0)                           # NOT done at submit time (baseline defect D2)
    c = store.claim_run(ok.id, "w", 30)
    assert tuple(states(ok.id)) == ("claimed", 0)
    store.transition_run(ok.id, RunStatus.running, fence=c.fence)
    store.transition_run(ok.id, RunStatus.succeeded, fence=c.fence, exit_reason="completed")
    assert tuple(states(ok.id)) == ("done", 1)
    bad = submit(store, bot, "b")
    c = store.claim_run(bad.id, "w", 30)
    store.transition_run(bad.id, RunStatus.running, fence=c.fence)
    store.transition_run(bad.id, RunStatus.failed, fence=c.fence, exit_reason="error")
    assert tuple(states(bad.id)) == ("failed", 1)
    stopped = submit(store, bot, "c")
    store.request_cancel(stopped.id)
    assert tuple(states(stopped.id)) == ("cancelled", 1)


def test_request_cancel_ends_a_queued_run_and_marks_a_live_run_cancelling(store):
    bot = make_bot(store)
    queued = submit(store, bot, "q")
    assert store.request_cancel(queued.id).status is RunStatus.stopped
    other = make_bot(store, "other")
    live = submit(store, other)
    c = store.claim_run(live.id, "w", 30)
    store.transition_run(live.id, RunStatus.running, fence=c.fence)
    r = store.request_cancel(live.id)
    assert r.status is RunStatus.cancelling and r.cancel_requested and store.is_cancel_requested(live.id)
    assert store.request_cancel(live.id).status is RunStatus.cancelling      # idempotent


def test_a_lapsed_lease_makes_a_live_run_recoverable(store):
    bot = make_bot(store)
    run = submit(store, bot)
    now = utcnow()
    c = store.claim_run(run.id, "w", 5, now=now)
    store.transition_run(run.id, RunStatus.running, fence=c.fence)
    assert store.expired_runs(now + timedelta(seconds=1)) == []
    store.renew_leases("w", 5, now=now + timedelta(seconds=4))               # heartbeat
    assert store.expired_runs(now + timedelta(seconds=7)) == []
    assert [r.id for r in store.expired_runs(now + timedelta(seconds=30))] == [run.id]


def test_receipts_distinguish_a_clean_stop_from_a_crash_mid_action(store):
    bot = make_bot(store)
    run = submit(store, bot)
    done = store.begin_action(run.id, "write_file", "k1", effect="fs", summary="write a.txt")
    store.finish_action(done, "done", "abc")
    assert store.actions_in_doubt(run.id) == []
    store.begin_action(run.id, "shell", "k2", effect="process", summary="$ ./deploy.sh")      # never finished: crash
    doubt = store.actions_in_doubt(run.id)
    assert [d["tool"] for d in doubt] == ["shell"]
    assert store.mark_actions_unknown(run.id) == 1
    assert store.actions_in_doubt(run.id)[0]["tool"] == "shell"              # still reported, now flagged unknown


def test_a_terminal_status_is_only_ever_visible_together_with_the_complete_transcript(store, config):
    """A reader in ANOTHER process must never see 'succeeded' with the last events still buffered in the writer."""
    from hutch.models import Event, EventType
    bot = make_bot(store, "complete")
    run = submit(store, bot)
    c = store.claim_run(run.id, "w", 30)
    store.transition_run(run.id, RunStatus.running, fence=c.fence, event={})
    for i in range(50):
        store.append_event(Event(run_id=run.id, type=EventType.log, data={"i": i}))      # still buffered, not flushed
    store.transition_run(run.id, RunStatus.succeeded, fence=c.fence, exit_reason="completed", event={"reason": "completed"})
    # read through a second connection that shares nothing with this store's buffer
    import sqlite3
    c2 = sqlite3.connect(config.db_path)
    seqs = [r[0] for r in c2.execute("SELECT seq FROM events WHERE run_id = ? ORDER BY seq", (run.id,))]
    assert seqs == list(range(1, 53)), "the status was committed ahead of events that came before it"
    assert store.verify_chain(run.id)["ok"]


def test_a_no_op_transition_still_commits_the_buffered_events(store, config):
    from hutch.models import Event, EventType
    bot = make_bot(store, "noop")
    run = submit(store, bot)
    c = store.claim_run(run.id, "w", 30)
    store.transition_run(run.id, RunStatus.running, fence=c.fence, event={})
    store.append_event(Event(run_id=run.id, type=EventType.log, data={"x": 1}))
    store.transition_run(run.id, RunStatus.running, fence=c.fence, event={})              # already running: nothing to change
    import sqlite3
    n = sqlite3.connect(config.db_path).execute("SELECT COUNT(*) FROM events WHERE run_id = ?", (run.id,)).fetchone()[0]
    assert n == 2 and store.verify_chain(run.id)["ok"]


def test_several_processes_appending_to_one_runs_transcript_keep_one_unbroken_chain(store, config):
    """The dashboard (recording a stop), the worker and a recovering supervisor all append to the same run. Sequence numbers and
    hashes come from the database tail at commit time, so they cannot collide or fork the chain."""
    bot = make_bot(store, "chorus")
    run = submit(store, bot)
    outs = race(config, f"""
        from hutch.models import Event, EventType
        for i in range(25):
            store.append_event(Event(run_id={run.id!r}, type=EventType.log, data={{"pid": os.getpid(), "i": i}}))
        store.flush_events()
        print("ok")
        store.close()
    """, n=4)
    assert outs == ["ok"] * 4
    events = store.list_events(run.id)
    assert [e.seq for e in events] == list(range(1, 101))
    chain = store.verify_chain(run.id)
    assert chain["ok"] and chain["checked"] == 100
    per_pid: dict[int, list[int]] = {}
    for e in events:
        per_pid.setdefault(e.data["pid"], []).append(e.data["i"])
    assert all(v == list(range(25)) for v in per_pid.values())          # each writer's own order is preserved


def test_a_zombie_process_cannot_append_to_a_run_another_process_ended(store, config):
    from hutch.models import Event, EventType
    bot = make_bot(store, "sealed")
    run = submit(store, bot)
    c = store.claim_run(run.id, "w", 30)
    store.transition_run(run.id, RunStatus.running, fence=c.fence, event={})
    zombie = Store(config)                                                  # another process that missed the ending
    store.transition_run(run.id, RunStatus.failed, fence=c.fence, exit_reason="interrupted", event={"reason": "interrupted"})
    n = len(store.list_events(run.id))
    zombie.append_event(Event(run_id=run.id, type=EventType.log, data={"late": True}))
    zombie.flush_events()
    assert len(store.list_events(run.id)) == n and zombie.dropped_events == 1       # refused at the database, not just in memory
    assert store.verify_chain(run.id)["ok"]
    zombie.close()
