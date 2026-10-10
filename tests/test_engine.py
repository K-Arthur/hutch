from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from hutch.config import get_config
from hutch.engine import Engine, bot_prompt_for_schedule
from hutch.models import ApprovalMode, Bot, CatchUpPolicy, EventType, Run, RunStatus, Schedule, Task
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
    snapshot = store.run_capability_snapshot(run.id)
    assert snapshot is not None
    assert snapshot["bot_id"] == bot.id
    assert snapshot["tools"] == sorted(snapshot["tools"])

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


def test_offline_capability_snapshot_is_credential_free_and_disables_network_tools():
    bot = mock_bot(tools=("browser", "web_fetch", "shell", "files"),
                   inference_mode="offline", shell_network=True,
                   base_url="http://127.0.0.1:8080/v1?token=not-for-the-snapshot")

    snapshot = Engine.capability_snapshot(bot)

    assert "browser" not in snapshot["tools"]
    assert "web_fetch" not in snapshot["tools"]
    assert snapshot["shell_network"] is False
    assert snapshot["browser_handoff"] is False
    assert "base_url" not in snapshot
    assert "not-for-the-snapshot" not in json.dumps(snapshot)


def test_reviewed_cross_bot_task_fails_before_worker_if_specialist_policy_changes(store, config):
    coordinator = store.create_bot(mock_bot(name="reviewed-coordinator", tools=[]))
    bot = store.create_bot(mock_bot(name="reviewed-specialist", tools=[]))
    store.set_workspace_coordinator(coordinator.id)
    store.set_workspace_specialists([bot.id])
    parent, _ = store.create_conversation(coordinator.id, "", idem_key="policy-parent", request_hash="policy-parent")
    parent_run = store.create_run(Run(bot_id=coordinator.id, prompt="Original", status=RunStatus.succeeded))
    with store._tx() as db:
        db.execute("INSERT INTO conversation_runs (conversation_id, run_id, attached_at) VALUES (?, ?, ?)",
                   (parent["id"], parent_run.id, parent_run.created_at))
        store._insert_conversation_message(db, message_id="policy-user", conversation_id=parent["id"], seq=1,
                                           run_id=parent_run.id, role="user", content="Original", created_at=parent_run.created_at)
        store._insert_conversation_message(db, message_id="policy-answer", conversation_id=parent["id"], seq=2,
                                           run_id=parent_run.id, role="assistant", content="Suggested brief", created_at=parent_run.created_at)
    prompt = "Reviewed brief"
    run = Run(bot_id=bot.id, prompt=prompt, origin="workspace_task")
    task = Task(bot_id=bot.id, kind="on_demand", prompt=prompt)
    store.submit_workspace_task(
        parent_conversation_id=parent["id"], source_run_id=parent_run.id,
        source_user_message_id="policy-user", source_assistant_message_id="policy-answer",
        target_bot_id=bot.id, task_brief=prompt, assumptions="", run=run, task=task,
        capability_snapshot=Engine.capability_snapshot(bot), idem_key="policy-child", request_hash="policy-child")
    changed = bot.model_copy(update={"tools": ["files"]})
    store._db.execute("UPDATE bots SET doc = ? WHERE id = ?", (changed.model_dump_json(), bot.id))
    store._db.commit()
    claimed = store.claim_run(run.id, "reviewed-task-test", lease_seconds=30, max_live=2)
    assert claimed is not None

    engine = Engine(config, store)
    try:
        assert engine._start_worker(changed, claimed) is False
        stopped = store.get_run(run.id)
        assert stopped.status is RunStatus.failed
        assert stopped.exit_reason == "workspace_task_policy_changed"
        assert "permissions or workspace changed" in stopped.error
        assert run.id not in engine._procs and run.id not in engine._threads
    finally:
        engine.shutdown(timeout=1)


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
