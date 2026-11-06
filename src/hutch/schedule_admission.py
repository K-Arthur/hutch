"""Scheduled-occurrence admission: conditions, approval parking and reconciliation.

The scheduler claim itself is the single winner (``Store.submit_scheduled``). This
module adds three decisions around it, in order:

1. evaluate the bounded policy conditions; a false condition skips the window
   visibly and creates no run;
2. create a prompt run as ``waiting_approval`` when the policy requires it, so no
   dispatcher can ever see it as pending;
3. reconcile the human decision: approved moves the parked run back to pending,
   denied or expired moves it to skipped. Reconciliation is idempotent.

The body was moved out of ``Engine.scheduler_claims`` so the frozen engine file
shrinks and the policy logic stays testable on its own.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from .models import ApprovalRequest, ApprovalStatus, Event, EventType, Run, RunStatus, Task, iso, utcnow
from .schedule_conditions import ConditionError, evaluate_conditions, schedule_context
from .schedule_policy import get_policy
from .scheduler import MAX_CATCHUP_WINDOWS, DueClaim, Scheduler


def _skip_due(store, due: DueClaim, reason: str) -> None:
    windows = MAX_CATCHUP_WINDOWS if due.missed_uncertain else max(due.missed + 1, 1)
    store.skip_scheduled_occurrence(
        schedule_id=due.schedule.id, bot_id=due.bot.id, occurrence=iso(due.occurrence),
        expected_marker=due.marker, reason=reason, windows=windows,
        uncertain=due.missed_uncertain,
    )


def _reconciliation_error(store, run_id: str, detail: str) -> None:
    """Record a reconciliation failure instead of swallowing it."""
    try:
        store.append_event(Event(run_id=run_id, type=EventType.log,
                                 data={"error": f"schedule approval reconciliation failed: {detail}"[:500]}))
    except Exception:
        pass


def _skip_run(store, run: Run, reason: str, *, approval_id: str = "") -> None:
    current = store.get_run(run.id) or run
    if current.status is not RunStatus.waiting_approval:
        return
    try:
        store.set_status(current, RunStatus.skipped,
                         event={"reason": reason, "approval_id": approval_id},
                         fields={"reason": reason})
    except Exception as exc:
        _reconciliation_error(store, run.id, str(exc))


def _park_run(store, run: Run, due: DueClaim) -> bool:
    """Create the pre-run approval for a run already inserted as waiting_approval."""
    from .approvals import action_fingerprint

    detail = {
        "bot": due.bot.name,
        "schedule": due.schedule.name,
        "schedule_id": due.schedule.id,
        "occurrence": iso(due.occurrence),
        "timezone": due.schedule.timezone,
        "trigger": due.schedule.trigger.value,
        "cron": due.schedule.cron,
        "prompt_chars": len(due.schedule.prompt or ""),
    }
    ttl = int(store.config.default_approval_ttl_seconds)
    request = ApprovalRequest(
        run_id=run.id, bot_id=due.bot.id, tool="schedule",
        action=f"Run scheduled task: {due.schedule.name}"[:300],
        detail=detail, rule="schedule approval required", risk="medium",
        ttl_seconds=ttl, expires_at=iso(utcnow() + timedelta(seconds=ttl)),
        action_hash=action_fingerprint("schedule", detail, "", False),
    )
    try:
        store.create_approval(request, begin_wait=True)
        with store._tx() as db:
            db.execute(
                "INSERT INTO schedule_approval_requests "
                "(run_id, approval_id, bot_id, schedule_id, occurrence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run.id, request.id, due.bot.id, due.schedule.id, iso(due.occurrence), iso(utcnow())),
            )
    except Exception:
        try:
            store.decide_approval(request.id, ApprovalStatus.expired, "schedule_setup_failed")
        except Exception:
            pass
        _skip_run(store, run, "schedule_approval_setup_failed", approval_id=request.id)
        return False
    return True


def _claim_workflow(store, scheduler: Scheduler, due: DueClaim, owner_id: str) -> Run | None:
    from .workflow import persistence as wfstore
    from .workflow import submit as wfsubmit

    definition = wfstore.definition(store, due.schedule.workflow_definition_id)
    revision = wfstore.revision(store, due.schedule.workflow_revision_id or "")
    if (definition is None or not definition.get("active") or revision is None
            or str(revision["definition_id"]) != str(definition["id"])):
        reason = "the linked saved workflow is missing or inactive"
        scheduler._note_blocked(due.schedule, "workflow_not_ready", reason)
        scheduler._note_skipped(due.bot, 1, due.schedule, reason="workflow_not_ready")
        scheduler.mark_dispatched(due.bot, due.occurrence, due.schedule)
        return None
    occurrence = iso(due.occurrence)
    request_data = {
        "schedule_id": due.schedule.id,
        "workflow_definition_id": due.schedule.workflow_definition_id,
        "workflow_revision_id": due.schedule.workflow_revision_id,
        "workflow_inputs": due.schedule.workflow_inputs,
        "occurrence": occurrence,
    }
    request_hash = hashlib.sha256(json.dumps(
        request_data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    schedule_claim = {
        "schedule_id": due.schedule.id,
        "occurrence": occurrence,
        "expected_marker": due.marker,
        "claimed_by": owner_id,
        "missed_windows": due.missed,
    }
    try:
        submission = wfsubmit.submit_workflow(
            store, bot=due.bot, plan=revision["plan"], inputs=due.schedule.workflow_inputs,
            save_definition=False, revision_id=str(revision["id"]), origin="schedule",
            schedule_id=due.schedule.id,
            idem_key=f"schedule:{due.schedule.id}:{occurrence}",
            request_hash=request_hash, schedule_claim=schedule_claim,
        )
    except wfstore.ScheduleClaimLost:
        return None
    except (wfsubmit.PlanInputError, wfsubmit.PlanNotSubmittable, KeyError, ValueError) as exc:
        reason = str(exc)[:300]
        scheduler._note_blocked(due.schedule, "workflow_not_ready", reason)
        scheduler._note_skipped(due.bot, 1, due.schedule, reason="workflow_not_ready")
        scheduler.mark_dispatched(due.bot, due.occurrence, due.schedule)
        return None
    return store.get_run(submission.attempt_run_id)


def _claim_prompt(store, scheduler: Scheduler, due: DueClaim, owner_id: str,
                  approval_required: bool) -> Run | None:
    from .engine import bot_prompt_for_schedule

    run = Run(
        bot_id=due.bot.id, prompt=bot_prompt_for_schedule(due.bot, due.schedule),
        missed_windows=due.missed, origin="schedule", schedule_id=due.schedule.id,
        status=RunStatus.waiting_approval if approval_required else RunStatus.pending,
        reason="schedule_approval_pending" if approval_required else "",
    )
    task = Task(bot_id=due.bot.id, kind="scheduled", prompt=run.prompt)
    occurrence_marker = iso(due.occurrence)
    won = store.submit_scheduled(
        run, task, occurrence=occurrence_marker, expected_marker=due.marker,
        new_marker=occurrence_marker, claimed_by=owner_id, schedule_id=due.schedule.id,
        note={"scheduled_run": run.id, "schedule_id": due.schedule.id,
              "missed_windows": due.missed, "missed_uncertain": due.missed_uncertain,
              "approval_required": approval_required, "occurrence": occurrence_marker},
    )
    if won is None:
        return None
    if approval_required and not _park_run(store, won, due):
        return None
    return won


def reconcile_decisions(store) -> int:
    """Retry decisions that were recorded but not yet moved a parked run.

    ``resolve_approval_ex`` reconciles immediately, but a crash between the
    approval commit and the run transition must not strand the run. This scan is
    bounded and runs on every scheduler beat.
    """
    with store._lock:
        rows = store._db.execute(
            "SELECT a.doc, a.status FROM schedule_approval_requests s "
            "JOIN approvals a ON a.id = s.approval_id "
            "WHERE s.reconciled_at = '' AND a.status != 'pending' LIMIT 50",
        ).fetchall()
    for row in rows:
        request = ApprovalRequest.model_validate_json(row["doc"])
        request.status = ApprovalStatus(row["status"])
        reconcile_decision(store, request)
    return len(rows)


def claim_due_schedules(store, scheduler: Scheduler, owner_id: str) -> list[Run]:
    """Claim every due occurrence, applying conditions and approval parking."""
    reconcile_decisions(store)
    reconcile_orphans(store)
    created: list[Run] = []
    for due in scheduler.due_claims():
        try:
            policy = get_policy(store, due.bot.id, due.schedule.id)
        except (ConditionError, ValueError) as exc:
            scheduler._note_blocked(due.schedule, "policy_invalid", str(exc)[:300])
            _skip_due(store, due, "policy_invalid")
            continue
        if policy.conditions:
            allowed, reason = evaluate_conditions(
                policy.conditions,
                schedule_context(due.bot, due.schedule, due.occurrence, due.missed),
            )
            if not allowed:
                scheduler._note_skipped(due.bot, due.missed + 1, due.schedule, reason="condition_not_met")
                _skip_due(store, due, "condition_not_met")
                continue
        if policy.approval_required and due.schedule.workflow_definition_id:
            scheduler._note_blocked(
                due.schedule, "policy_unsupported",
                "linked saved workflows keep their own step approvals")
            _skip_due(store, due, "policy_unsupported")
            continue
        if due.schedule.workflow_definition_id:
            run = _claim_workflow(store, scheduler, due, owner_id)
        else:
            run = _claim_prompt(store, scheduler, due, owner_id, bool(policy.approval_required))
        if run is not None:
            created.append(run)
    return created


def _mark_reconciled(store, run_id: str) -> None:
    with store._tx() as db:
        db.execute(
            "UPDATE schedule_approval_requests SET reconciled_at = ? "
            "WHERE run_id = ? AND reconciled_at = ''",
            (iso(utcnow()), run_id),
        )


def reconcile_decision(store, request: ApprovalRequest | None) -> None:
    """Move a parked run after an approval decision. Safe to call more than once."""
    if request is None or request.tool != "schedule":
        return
    if request.status is ApprovalStatus.pending:
        return
    with store._lock:
        row = store._db.execute(
            "SELECT run_id, reconciled_at FROM schedule_approval_requests WHERE approval_id = ?",
            (request.id,),
        ).fetchone()
    if row is None or row["reconciled_at"]:
        return
    run = store.get_run(row["run_id"])
    if run is None:
        _mark_reconciled(store, row["run_id"])
        return
    if run.status is RunStatus.waiting_approval:
        if request.status is ApprovalStatus.approved:
            target, reason = RunStatus.pending, "schedule_approval_approved"
        else:
            target = RunStatus.skipped
            reason = ("schedule_approval_expired" if request.status is ApprovalStatus.expired
                      else "schedule_approval_denied")
        try:
            store.set_status(run, target, event={"reason": reason, "approval_id": request.id},
                             fields={"reason": "" if target is RunStatus.pending else reason})
        except Exception as exc:
            _reconciliation_error(store, run.id, str(exc))
    _mark_reconciled(store, row["run_id"])
    store.bus.notify("work", "runs", f"run:{run.id}")


def reconcile_orphans(store) -> int:
    """Fail closed on a parked run whose approval mapping never landed."""
    with store._lock:
        rows = store._db.execute(
            "SELECT r.id FROM runs r LEFT JOIN schedule_approval_requests s ON s.run_id = r.id "
            "WHERE r.status = ? AND json_extract(r.doc, '$.origin') = 'schedule' "
            "AND json_extract(r.doc, '$.reason') = 'schedule_approval_pending' "
            "AND s.run_id IS NULL LIMIT 50",
            (RunStatus.waiting_approval.value,),
        ).fetchall()
    recovered = 0
    for row in rows:
        run = store.get_run(row["id"])
        if run is None:
            continue
        try:
            store.set_status(run, RunStatus.skipped,
                             event={"reason": "schedule_approval_missing"},
                             fields={"reason": "schedule_approval_missing"})
            recovered += 1
        except Exception:
            continue
    return recovered
