from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from openbot.config import get_config
from openbot.engine import Engine, bot_prompt_for_schedule
from openbot.models import ApprovalMode, Bot, CatchUpPolicy, RunStatus, Schedule
from openbot.store import Store


def mock_bot(name="runner", tools=("shell", "files", "memory"), **kw) -> Bot:
    defaults = dict(
        name=name, description="test bot", instructions="do the thing",
        model="mock/demo", tools=list(tools), approval_mode=ApprovalMode.auto,
    )
    defaults.update(kw)
    return Bot(**defaults)


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

    # slow runtime: patch MockRuntime to block until released
    import openbot.runtime.mock as mock_mod
    orig = mock_mod.MockRuntime.execute

    def slow_execute(self, run, ctx, tools, stop):
        release.wait(timeout=10)
        return orig(self, run, ctx, tools, stop)

    mock_mod.MockRuntime.execute = slow_execute
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
        mock_mod.MockRuntime.execute = orig
        release.set()


def test_timeout_kills_run(store, config):
    import threading
    bot = store.create_bot(mock_bot(name="slowpoke"))
    from openbot.models import Limits
    bot.limits = Limits(timeout_seconds=2)
    store.upsert_bot(bot)

    import openbot.runtime.mock as mock_mod
    orig = mock_mod.MockRuntime.execute
    blocker = threading.Event()

    def slow_execute(self, run, ctx, tools, stop):
        blocker.wait(timeout=30)
        return orig(self, run, ctx, tools, stop)

    mock_mod.MockRuntime.execute = slow_execute
    try:
        engine = Engine(config, store)
        engine.submit(bot, "will hang")
        engine.dispatch_pending()
        deadline = time.time() + 15
        runs = store.list_runs(bot.id)
        while time.time() < deadline:
            runs = store.list_runs(bot.id)
            if runs and runs[0].status.value in ("failed", "stopped", "succeeded"):
                break
            time.sleep(0.2)
        assert runs[0].exit_reason == "timeout"
        assert runs[0].status is RunStatus.failed
    finally:
        mock_mod.MockRuntime.execute = orig
        blocker.set()


def test_bot_prompt_for_schedule_mentions_standing_task():
    bot = mock_bot(instructions="Collect all new issues and summarize.")
    prompt = bot_prompt_for_schedule(bot)
    assert "scheduled run" in prompt and "Collect all new issues" in prompt
