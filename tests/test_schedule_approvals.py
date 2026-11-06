"""Scheduled occurrences park before execution and reconcile exactly once."""

from __future__ import annotations

from datetime import timedelta

from hutch.approvals import expire_stale_approvals, resolve_approval_ex
from hutch.engine import Engine
from hutch.models import ApprovalStatus, Bot, CatchUpPolicy, Run, RunStatus, Schedule, iso, utcnow
from hutch.schedule_admission import reconcile_decision, reconcile_decisions, reconcile_orphans
from hutch.schedule_policy import put_policy
from hutch.scheduler import Scheduler


def _seed(store, name: str = "approval-bot", *, approval: bool = True, conditions=None) -> Bot:
    bot = store.create_bot(Bot(
        name=name, display_name=name.title(), tools=[],
        schedule=Schedule(name="Nightly release check", cron="0 3 * * *", timezone="UTC",
                          catch_up=CatchUpPolicy.coalesce, prompt="Check releases."),
    ))
    store.kv_set(f"{bot.schedule.id}:last_fire", iso(utcnow() - timedelta(days=1)))
    put_policy(store, bot.id, bot.schedule.id, approval_required=approval, conditions=conditions or [])
    return bot


def _claim(store, config):
    return Engine(config, store).scheduler_claims()


def test_due_schedule_parks_before_execution_and_approval_releases_it(store, config):
    bot = _seed(store)
    created = _claim(store, config)
    assert len(created) == 1
    run = store.get_run(created[0].id)
    assert run.status is RunStatus.waiting_approval
    assert run.reason == "schedule_approval_pending"

    requests = store.pending_approvals()
    assert len(requests) == 1
    request = requests[0]
    assert request.tool == "schedule"
    assert request.detail["schedule_id"] == bot.schedule.id
    assert "Check releases." not in str(request.detail)
    assert "prompt" not in request.detail
    assert store._db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 1

    store.flush_events()
    assert [event.type.value for event in store.list_events(run.id)] == ["approval_request"]

    result = resolve_approval_ex(store, request.id, True, by="test")
    assert result.won
    released = store.get_run(run.id)
    assert released.status is RunStatus.pending
    assert released.reason == ""
    with store._lock:
        mapping = store._db.execute(
            "SELECT reconciled_at FROM schedule_approval_requests WHERE run_id = ?", (run.id,)).fetchone()
    assert mapping["reconciled_at"]


def test_denial_skips_the_parked_run(store, config):
    _seed(store)
    run = _claim(store, config)[0]
    request = store.pending_approvals()[0]
    resolve_approval_ex(store, request.id, False, by="test")
    skipped = store.get_run(run.id)
    assert skipped.status is RunStatus.skipped
    assert skipped.reason == "schedule_approval_denied"
    # A second reconciliation of the same decision changes nothing.
    reconcile_decision(store, store.get_approval(request.id))
    assert store.get_run(run.id).status is RunStatus.skipped


def test_expiry_skips_the_parked_run_through_the_real_expiry_path(store, config):
    _seed(store)
    run = _claim(store, config)[0]
    request = store.pending_approvals()[0]
    past = iso(utcnow() - timedelta(seconds=1))
    with store._tx() as db:
        db.execute("UPDATE approvals SET expires_at = ? WHERE id = ?", (past, request.id))
        db.execute("UPDATE approvals SET doc = json_set(doc, '$.expires_at', ?) WHERE id = ?",
                   (past, request.id))
    expired = expire_stale_approvals(store)
    assert [item.id for item in expired] == [request.id]
    skipped = store.get_run(run.id)
    assert skipped.status is RunStatus.skipped
    assert skipped.reason == "schedule_approval_expired"


def test_a_lost_decision_is_retried_on_the_next_scheduler_beat(store, config):
    _seed(store)
    run = _claim(store, config)[0]
    request = store.pending_approvals()[0]
    store.decide_approval(request.id, ApprovalStatus.approved, "test")
    assert store.get_run(run.id).status is RunStatus.waiting_approval
    assert reconcile_decisions(store) == 1
    assert store.get_run(run.id).status is RunStatus.pending


def test_false_condition_skips_without_creating_a_run(store, config):
    bot = _seed(store, approval=False)
    due = Scheduler(store).due_claims()[0]
    weekday = due.occurrence.weekday()
    put_policy(store, bot.id, bot.schedule.id, approval_required=False,
               conditions=[{"field": "occurrence_weekday", "op": "ne", "value": weekday}])
    assert _claim(store, config) == []
    with store._lock:
        count = store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot.id,)).fetchone()[0]
        skip = store._db.execute("SELECT value FROM kv WHERE key = ?",
                                 (f"{bot.schedule.id}:last_skip",)).fetchone()
    assert count == 0
    assert "condition_not_met" in skip["value"]


def test_true_condition_still_parks_for_approval(store, config):
    _seed(store, conditions=[{"field": "schedule_timezone", "op": "eq", "value": "UTC"}])
    created = _claim(store, config)
    assert len(created) == 1
    assert store.get_run(created[0].id).status is RunStatus.waiting_approval


def test_legacy_approval_policy_on_a_linked_workflow_fails_closed(store, config):
    bot = store.create_bot(Bot(
        name="workflow-legacy", display_name="Workflow Legacy", tools=[],
        schedule=Schedule(name="Workflow routine", cron="0 3 * * *", timezone="UTC",
                          workflow_definition_id="wf-1", workflow_revision_id="rev-1"),
    ))
    store.kv_set(f"{bot.schedule.id}:last_fire", iso(utcnow() - timedelta(days=1)))
    with store._tx() as db:
        db.execute("INSERT INTO schedule_policies "
                   "(bot_id, schedule_id, approval_required, conditions_json, revision, updated_at) "
                   "VALUES (?, ?, 1, '[]', 1, ?)",
                   (bot.id, bot.schedule.id, iso(utcnow())))
    assert _claim(store, config) == []
    with store._lock:
        runs = store._db.execute("SELECT COUNT(*) FROM runs WHERE bot_id = ?", (bot.id,)).fetchone()[0]
        skip = store._db.execute("SELECT value FROM kv WHERE key = ?",
                                 (f"{bot.schedule.id}:last_skip",)).fetchone()
    assert runs == 0
    assert "policy_unsupported" in skip["value"]


def test_orphan_parked_run_is_failed_closed_but_a_tool_wait_is_untouched(store):
    bot = _seed(store, approval=False)
    orphan = store.create_run(Run(
        bot_id=bot.id, prompt="orphan", origin="schedule", schedule_id=bot.schedule.id,
        status=RunStatus.waiting_approval, reason="schedule_approval_pending",
    ))
    tool_wait = store.create_run(Run(
        bot_id=bot.id, prompt="tool wait", origin="schedule", schedule_id=bot.schedule.id,
        status=RunStatus.waiting_approval, reason="tool_approval",
    ))
    assert reconcile_orphans(store) == 1
    assert store.get_run(orphan.id).status is RunStatus.skipped
    assert store.get_run(orphan.id).reason == "schedule_approval_missing"
    assert store.get_run(tool_wait.id).status is RunStatus.waiting_approval
