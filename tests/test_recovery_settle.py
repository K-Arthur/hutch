"""A recovery that cannot verify its processes settles only when settling abandons nothing real.

The first unverifiable cleanup defers (tests/test_claims.py). A retry settles the run as `outcome_unknown` only when every
survivor is unverifiable and the host can inspect processes at all. A survivor known to be alive, or a host with no
process inspection, keeps the run stopping: closing those records would stop tracking something that may still run.
"""

from __future__ import annotations

import pytest

from hutch import procguard
from hutch.engine import Engine
from hutch.models import Bot, Run, RunStatus, Task

UNVERIFIABLE = procguard.Proc(4242, 0, 4242, 0, 1, "?")
ALIVE = procguard.Proc(4243, 1, 4243, 1, 1, "S")


def _expired_run(store, name):
    bot = store.create_bot(Bot(name=name, model="ollama/llama3.2:3b", tools=["files"]))
    run = store.submit_run(Run(bot_id=bot.id, prompt="work"), Task(bot_id=bot.id, prompt="work"))
    worker = store.claim_run(run.id, "dead-worker", 1)
    store.transition_run(run.id, RunStatus.running, fence=worker.fence)
    with store._lock:
        store._db.execute("UPDATE runs SET lease_expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (run.id,))
        store._db.commit()
    return run.id


def _recover_twice(store, config, monkeypatch, run_id, left, available=True):
    monkeypatch.setattr(Engine, "_end_recorded_processes", lambda *_: list(left))
    monkeypatch.setattr(procguard, "available", lambda: available)
    engine = Engine(config, store)
    assert engine._recover_one(store.get_run(run_id)) is None            # the first attempt always defers
    with store._lock:                                                    # the one-second retry lease has lapsed
        store._db.execute("UPDATE runs SET lease_expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (run_id,))
        store._db.commit()
    return engine._recover_one(store.get_run(run_id))


def test_a_retry_that_finds_only_unverifiable_survivors_settles_as_outcome_unknown(store, config, monkeypatch):
    run_id = _expired_run(store, "unverifiable-only")
    settled = _recover_twice(store, config, monkeypatch, run_id, [UNVERIFIABLE])
    assert settled is not None and settled.status is RunStatus.outcome_unknown
    assert "could not be verified after repeated attempts" in settled.error
    assert store.get_run(run_id).status is RunStatus.outcome_unknown and not store.live_procs(run_id)


@pytest.mark.parametrize("left", [[ALIVE], [UNVERIFIABLE, ALIVE]], ids=["alive", "alive-and-unverifiable"])
def test_a_survivor_known_to_be_alive_keeps_the_run_stopping(store, config, monkeypatch, left):
    run_id = _expired_run(store, "alive-survivor")
    assert _recover_twice(store, config, monkeypatch, run_id, left) is None
    waiting = store.get_run(run_id)
    assert waiting.status is RunStatus.recovering and waiting.lease_owner == f"cleanup-pending:{run_id}"
    assert "cleanup incomplete" in waiting.reason


def test_a_host_without_process_inspection_never_settles(store, config, monkeypatch):
    run_id = _expired_run(store, "no-inspection")
    assert _recover_twice(store, config, monkeypatch, run_id, [UNVERIFIABLE], available=False) is None
    assert store.get_run(run_id).status is RunStatus.recovering
