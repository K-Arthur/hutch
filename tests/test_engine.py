from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from hutch.config import get_config
from hutch.engine import Engine, bot_prompt_for_schedule
from hutch.models import ApprovalMode, Bot, CatchUpPolicy, EventType, RunStatus, Schedule
from hutch.store import Store


def mock_bot(name="runner", tools=("shell", "files", "memory"), **kw) -> Bot:
    defaults = dict(
        name=name, description="test bot", instructions="do the thing",
        model="mock/demo", tools=list(tools), approval_mode=ApprovalMode.auto,
    )
    defaults.update(kw)
    return Bot(**defaults)


def test_run_stays_cancelling_until_prior_cleanup_finishes(store, config, monkeypatch):
    import threading
    import hutch.engine as engine_module
    from hutch.tools.base import ProcRegistry
    started, cleanup, finalizing, release = (threading.Event() for _ in range(4))
    finish = ProcRegistry.finish

    class Runtime:
        kind = "fixture"
        def execute(self, run, ctx, tools, stop):
            started.set()
            while not stop():
                time.sleep(0.001)
            return "stopped fixture"

    def held_kill(self, grace=2):
        cleanup.set()
        assert release.wait(5)
        return 0

    def observed_finish(self, grace=0.5):
        finalizing.set()
        finish(self, grace)

    monkeypatch.setattr(engine_module, "get_runtime", lambda _: Runtime())
    monkeypatch.setattr(ProcRegistry, "kill_all", held_kill)
    monkeypatch.setattr(ProcRegistry, "finish", observed_finish)
    engine = Engine(config, store)
    run = engine.submit(store.create_bot(mock_bot(tools=[])), "cancel fixture")
    engine.dispatch_pending()
    try:
        assert started.wait(2)
        engine.stop_run(run.id)
        assert cleanup.wait(2) and finalizing.wait(2)
        assert store.get_run(run.id).status is RunStatus.cancelling
        assert engine._threads[run.id].is_alive()
    finally:
        release.set()
        engine.shutdown(timeout=3)
    assert store.get_run(run.id).status is RunStatus.stopped
    assert not any(t.name == "hutch-process-cleanup" and t.is_alive() for t in threading.enumerate())


def test_run_blocking_success_flow(store, config, tmp_path):
    bot = store.create_bot(mock_bot())
    engine = Engine(config, store)
    run = engine.run_blocking(bot, "research the news about X and summarize")

    assert run.status is RunStatus.succeeded
    assert run.exit_reason == "completed"
    assert run.workspace and "workspace" in run.workspace
    assert run.steps >= 3

    events = store.list_events(run.id)
    kinds = [e.type.value for e in events]
    assert "tool_call" in kinds and "message" in kinds
    assert events[-1].data["status"] == "succeeded"

    # append-only transcript on disk mirrors events
    store.flush_transcripts()
    transcript_dir = config.run_dir(bot.name, run.id)
    lines = (transcript_dir / "transcript.jsonl").read_text().splitlines()
    assert len(lines) >= len(events)
    json.loads(lines[0])

    # workspace artifacts
    from pathlib import Path
    assert (Path(run.workspace) / "report.md").exists()


def test_scheduled_tick_creates_catchup_run(store, config):
    bot = store.create_bot(mock_bot(
        name="weekly", schedule=Schedule(cron="* * * * *", timezone="UTC",
                                         catch_up=CatchUpPolicy.coalesce),
        created_at="2026-01-01T00:00:00+00:00",
    ))
    engine = Engine(config, store)
    created = engine.tick()
    assert len(created) == 1
    run = store.get_run(created[0].id)
    assert run.missed_windows >= 1

    # wait for the async worker to finish, then check success
    for _ in range(100):
        if store.get_run(run.id).status.value in ("succeeded", "failed", "stopped"):
            break
        time.sleep(0.05)
    assert store.get_run(run.id).status is RunStatus.succeeded

    # second tick immediately after: not due again (no double dispatch)
    assert engine.tick() == []


def test_stop_run_marks_stopped(store, config):
    bot = store.create_bot(mock_bot())
    engine = Engine(config, store)
    run = engine.submit(bot, "slow job")
    engine.stop_run(run.id)
    # pending run stopped before start
    updated = store.get_run(run.id)
    assert updated.status is RunStatus.stopped


def test_per_bot_single_instance(store, config):
    """Two queued runs of one bot never execute concurrently."""
    import threading
    bot = store.create_bot(mock_bot(name="solo"))
    release = threading.Event()

    # slow test scenario runtime: block until the test releases it
    import tests.support.runtime as mock_mod
    orig = mock_mod.TestScenarioRuntime.execute

    def slow_execute(self, run, ctx, tools, stop):
        release.wait(timeout=10)
        return orig(self, run, ctx, tools, stop)

    mock_mod.TestScenarioRuntime.execute = slow_execute
    try:
        engine = Engine(config, store)
        r1 = engine.submit(bot, "first")
        r2 = engine.submit(bot, "second")
        engine.dispatch_pending()
        time.sleep(0.3)
        active = [r for r in store.active_runs() if r.status.value in ("running", "waiting_approval")]
        assert len(active) <= 1  # never two live runs for one bot
        release.set()
        deadline = time.time() + 10
        while time.time() < deadline:
            statuses = {store.get_run(r1.id).status, store.get_run(r2.id).status}
            if statuses <= {RunStatus.succeeded, RunStatus.failed, RunStatus.stopped}:
                break
            time.sleep(0.1)
        engine.dispatch_pending()  # now second can go
        deadline = time.time() + 10
        while time.time() < deadline and store.get_run(r2.id).status is RunStatus.pending:
            time.sleep(0.1)
        time.sleep(0.5)
        assert store.get_run(r2.id).status is not RunStatus.pending
    finally:
        mock_mod.TestScenarioRuntime.execute = orig
        release.set()


def test_timeout_kills_run(store, config):
    import threading
    bot = store.create_bot(mock_bot(name="slowpoke"))
    from hutch.models import Limits
    bot.limits = Limits(timeout_seconds=2)
    store.upsert_bot(bot)

    import tests.support.runtime as mock_mod
    orig = mock_mod.TestScenarioRuntime.execute
    blocker = threading.Event()

    def slow_execute(self, run, ctx, tools, stop):
        blocker.wait(timeout=30)
        return orig(self, run, ctx, tools, stop)

    mock_mod.TestScenarioRuntime.execute = slow_execute
    engine = Engine(config, store)
    try:
        engine.submit(bot, "will hang")
        engine.dispatch_pending()
        deadline = time.time() + 10
        while time.time() < deadline:
            run = store.list_runs(bot.id)[0]
            if run.status.value == "cancelling":
                break
            time.sleep(0.2)
        else:
            pytest.fail("timeout was not surfaced while the runtime thread was blocked")
        assert run.exit_reason == "" and run.status is RunStatus.cancelling
        # Python cannot safely kill an uncooperative thread. Keep cancellation visible until it exits.
        blocker.set()
        deadline = time.time() + 10
        while time.time() < deadline:
            run = store.list_runs(bot.id)[0]
            if run.status in (RunStatus.failed, RunStatus.stopped, RunStatus.succeeded):
                break
            time.sleep(0.1)
        assert run.exit_reason == "timeout"
        assert run.status is RunStatus.failed
    finally:
        mock_mod.TestScenarioRuntime.execute = orig
        blocker.set()
        engine.shutdown()


def test_bot_prompt_for_schedule_mentions_standing_task():
    bot = mock_bot(instructions="Collect all new issues and summarize.")
    prompt = bot_prompt_for_schedule(bot)
    assert "scheduled run" in prompt and "Collect all new issues" in prompt


def test_scheduled_task_prompt_is_separate_from_bot_instructions():
    bot = mock_bot(instructions="You are a careful research assistant.",
                   schedule=Schedule(cron="0 9 * * 1", prompt="Review the new release notes and report changes."))
    prompt = bot_prompt_for_schedule(bot)
    assert "Review the new release notes and report changes." in prompt
    assert "careful research assistant" not in prompt


def test_retired_legacy_route_fails_before_a_worker_or_action(store, config, monkeypatch):
    monkeypatch.delenv("HUTCH_TESTING", raising=False)
    bot = store.create_bot(mock_bot(name="legacy-route", tools=["files"]))
    engine = Engine(config, store, executor="process")
    run = engine.submit(bot, "write a report")

    assert engine.dispatch_pending() == 0
    saved = store.get_run(run.id)
    assert saved.status is RunStatus.failed and saved.exit_reason == "model_unavailable"
    assert not any(event.type is EventType.tool_call for event in store.list_events(run.id))
    assert not engine._procs and not engine._threads
    engine.shutdown()
