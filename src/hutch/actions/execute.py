"""Plan execution: ordered steps, one effect journal, honest partial outcomes.

``execute_plan`` is the only place an approved plan turns into external effects:

* The approval must match the plan's *current* ``approval_scope_hash``; anything else is
  refused before the first effect.
* Steps run in dependency order. A failed, denied or uncertain step skips its dependents,  a Docs brief that was never created cannot be shared.
* Every journaled step begins a durable effect row keyed by the step's idempotency key
  *before* the executor runs. A key already ``succeeded`` is reused (no duplicate remote
  write); ``uncertain`` is never retried automatically, it stays visible until the
  caller reconciles.
* A definite failure may be retried explicitly: the engine flips the failed effect to
  prepared and runs only the steps that are not already succeeded. Successful effects are
  never repeated.
* Executors report ``verified`` separately from ``ok``: a write that landed but failed
  read-back is a failure with the remote id preserved, not a success.

This module performs no I/O itself; executors do, and they are injected.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .plan import ActionPlan, JOURNALED_KINDS, PlanStep

Executor = Callable[[PlanStep, ActionPlan], "ExecutorResult"]


@dataclass
class ExecutorResult:
    ok: bool
    remote_id: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    verification: list[str] = field(default_factory=list)
    error: str = ""
    uncertain: bool = False  # the effect may have happened; never auto-retried

    @property
    def verified(self) -> bool:
        return self.ok and not self.verification


class ApprovalMismatch(ValueError):
    """The given approval does not match this plan's exact content."""


class MissingSeparateAuthority(ValueError):
    """A step of separate authority was executed without its own grant."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolve_inputs(value: Any, plan: "ActionPlan") -> Any:
    """Resolve ``{"$remote_id": "<step id>"}`` references against earlier steps' results.

    The reference is what the review approves ("append to the sheet this plan creates");
    the concrete id exists only during execution. An unresolved reference raises rather
    than silently sending a placeholder.
    """
    if isinstance(value, dict):
        if set(value.keys()) == {"$remote_id"}:
            dep = plan.step(str(value["$remote_id"]))
            if dep is None or not dep.remote_id:
                raise ValueError(
                    f"step reference {value['$remote_id']!r} is unresolved; its step has not succeeded")
            return dep.remote_id
        return {k: _resolve_inputs(v, plan) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_inputs(v, plan) for v in value]
    return value


def _effect_id(step: PlanStep) -> str:
    digest = hashlib.sha256(f"{step.id}|{step.idempotency_key}|{step.request_hash}".encode()).hexdigest()
    return f"eff_{digest[:16]}"


def execute_plan(plan: ActionPlan, *, store, executors: dict[str, Executor],
                 approved_hash: str, separately_approved: Optional[set[str]] = None,
                 dry_run: bool = False,
                 progress: Optional[Callable[[str, dict], None]] = None,
                 retry_failed: bool = False) -> ActionPlan:
    """Execute an approved plan and return it with per-step outcomes (also persisted).

    ``executors`` maps a step kind to its implementation. ``retry_failed=True`` flips
    definitively-failed effects back to prepared and re-runs those steps (and skipped
    dependents); uncertain outcomes are still never retried here.
    """
    separately_approved = set(separately_approved or ())
    current_scope = plan.recompute_approval_scope()
    if approved_hash != current_scope:
        raise ApprovalMismatch(
            "the approval does not match this plan's current steps/targets/inputs; "
            "re-review the plan before executing")

    if not dry_run:
        plan.status = "executing"
    plan.updated_at = _now()
    if not dry_run:
        store.save_action_plan(plan.model_dump(mode="json"))

    def emit(kind: str, payload: dict) -> None:
        if progress:
            progress(kind, payload)

    skipped: set[str] = set()
    for step in plan.ordered_steps():
        if any(dep in skipped for dep in step.depends_on):
            step.status = "skipped"
            step.error = "a dependency did not succeed"
            skipped.add(step.id)
            emit("step_skipped", {"step": step.id})
            continue
        if step.status == "succeeded":
            continue  # an explicit retry must not repeat completed work

        if step.authority() == "separate" and step.id not in separately_approved:
            step.status = "denied"
            step.error = ("this step changes sharing or notifies people; it needs its own "
                          "approval and did not run")
            skipped.add(step.id)
            emit("step_denied", {"step": step.id})
            continue

        executor = executors.get((step.kind, step.target.service)) or executors.get(step.kind)
        if executor is None:
            step.status = "failed"
            step.error = f"no executor is registered for {step.kind}"
            skipped.add(step.id)
            emit("step_failed", {"step": step.id, "error": step.error})
            continue

        if dry_run:
            step.status = "succeeded"
            step.verification = ["dry run: nothing was sent"]
            emit("step_dry_run", {"step": step.id})
            continue

        try:
            effective = step.model_copy(deep=True)
            effective.inputs = _resolve_inputs(step.inputs, plan)
        except ValueError as exc:
            step.status = "failed"
            step.error = str(exc)
            skipped.add(step.id)
            emit("step_failed", {"step": step.id, "error": step.error})
            continue

        step.status = "running"
        emit("step_started", {"step": step.id})

        journaled = step.kind in JOURNALED_KINDS and bool(step.idempotency_key)
        effect_id = ""
        if journaled:
            effect_id = _effect_id(step)
            effect = store.begin_synthesis_effect(
                effect_id=effect_id, plan_id=plan.id, step_id=step.id, kind=step.kind,
                idempotency_key=step.idempotency_key, request_hash=step.request_hash,
                target=step.target.model_dump(mode="json"),
            )
            effect_id = str(effect["id"])
            step.receipt_id = effect["id"]
            if not effect.get("created"):
                status = effect.get("status")
                if status == "succeeded":
                    step.status = "succeeded"
                    step.remote_id = str(effect.get("remote_id") or "")
                    step.verification = list((effect.get("result_json") or {}).get("verification") or [])
                    emit("step_reused", {"step": step.id, "remote_id": step.remote_id})
                    continue
                if status == "uncertain":
                    step.status = "uncertain"
                    step.remote_id = str(effect.get("remote_id") or "")
                    step.error = ("a previous attempt's outcome is unknown; reconcile it before "
                                  "this step may run again")
                    skipped.add(step.id)
                    emit("step_uncertain", {"step": step.id})
                    continue
                if status == "failed":
                    if not retry_failed:
                        step.status = "failed"
                        step.error = str((effect.get("result_json") or {}).get("error") or
                                         "a previous attempt failed; pass retry_failed to try again")
                        skipped.add(step.id)
                        emit("step_failed", {"step": step.id, "error": step.error})
                        continue
                    if not store.claim_synthesis_effect_for_retry(effect_id):
                        latest = store.find_synthesis_effect(step.idempotency_key) or {}
                        if latest.get("status") == "succeeded":
                            step.status = "succeeded"
                            step.remote_id = str(latest.get("remote_id") or "")
                            emit("step_reused", {"step": step.id, "remote_id": step.remote_id})
                        else:
                            step.status = "uncertain"
                            step.error = "another attempt claimed this effect; reconcile it before retrying"
                            skipped.add(step.id)
                            emit("step_uncertain", {"step": step.id})
                        continue
                if status == "prepared":
                    error = ("a previous attempt stopped before recording its outcome; reconcile it before "
                             "this step may run again")
                    store.finish_synthesis_effect(
                        effect_id, status="uncertain", result={"error": error})
                    step.status = "uncertain"
                    step.error = error
                    skipped.add(step.id)
                    emit("step_uncertain", {"step": step.id})
                    continue

        try:
            outcome = executor(effective, plan)
        except Exception as exc:  # noqa: BLE001 - an executor crash is a step failure
            outcome = ExecutorResult(ok=False, error=f"executor raised {type(exc).__name__}: {exc}")

        if outcome.ok and outcome.verified:
            step.status = "succeeded"
            step.remote_id = outcome.remote_id
            step.verification = []
            if journaled:
                store.finish_synthesis_effect(
                    effect_id, status="succeeded",
                    result={**outcome.result, "verification": []},
                    remote_id=outcome.remote_id)
            emit("step_succeeded", {"step": step.id, "remote_id": outcome.remote_id})
        elif outcome.uncertain:
            step.status = "uncertain"
            step.remote_id = outcome.remote_id
            step.error = outcome.error or "the provider did not confirm the outcome"
            skipped.add(step.id)
            if journaled:
                store.finish_synthesis_effect(
                    effect_id, status="uncertain",
                    result={"error": step.error, **outcome.result},
                    remote_id=outcome.remote_id)
            emit("step_uncertain", {"step": step.id, "error": step.error})
        else:
            step.status = "failed"
            step.remote_id = outcome.remote_id
            step.verification = list(outcome.verification)
            step.error = outcome.error or ("verification failed: " + "; ".join(outcome.verification[:3])
                                           if outcome.verification else "the step failed")
            skipped.add(step.id)
            if journaled:
                store.finish_synthesis_effect(
                    effect_id, status="failed",
                    result={"error": step.error, "verification": outcome.verification,
                            **outcome.result},
                    remote_id=outcome.remote_id)
            emit("step_failed", {"step": step.id, "error": step.error})

    statuses = [s.status for s in plan.steps]
    succeeded = sum(1 for s in statuses if s == "succeeded")
    blocked = [s for s in statuses if s in ("failed", "uncertain", "denied", "skipped")]
    if dry_run:
        plan.status = "approved"
    elif not blocked:
        plan.status = "completed"
    elif succeeded:
        plan.status = "partial"
    else:
        plan.status = "failed"
    plan.updated_at = _now()
    if not dry_run:
        store.save_action_plan(plan.model_dump(mode="json"))
    emit("plan_finished", {"plan": plan.id, "status": plan.status,
                           "succeeded": succeeded, "blocked": len(blocked)})
    return plan


def plan_outcome_report(plan: ActionPlan) -> dict[str, Any]:
    """What actually happened, per step, in the shape a receipt or UI needs."""
    steps = []
    for step in sorted(plan.steps, key=lambda s: s.index):
        steps.append({
            "id": step.id,
            "kind": step.kind,
            "title": step.title,
            "status": step.status,
            "target": step.target.display or step.target.resource_id or step.target.parent_id,
            "service": step.target.service,
            "remote_id": step.remote_id,
            "verification": step.verification,
            "error": step.error,
        })
    counts: dict[str, int] = {}
    for s in plan.steps:
        counts[s.status] = counts.get(s.status, 0) + 1
    return {
        "plan_id": plan.id,
        "status": plan.status,
        "counts": counts,
        "steps": steps,
        "resolved": [s["id"] for s in steps if s["status"] == "succeeded"],
        "remaining": [s["id"] for s in steps if s["status"] in ("failed", "uncertain", "denied", "pending")],
    }
