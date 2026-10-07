"""Human-in-the-loop approval flow.

A tool that wants to perform an "ask" action creates an ApprovalRequest in the
store and waits — on the wake bus, not a poll loop — until a human resolves it
from the dashboard or CLI, or until its deadline passes, in which case the
answer is DENY. Fail-closed is the point: silence never becomes consent (the
"agent emailed real lawyers" class of incident).

The request carries everything a person needs to decide well (UI-5): the
command split into parsed segments, the rule that fired, the risk class, and the
deadline (shown as a countdown). Actions that send something *outward* (SR-4)
always ask — sticky allows and auto mode do not apply to them.
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Callable, Optional

from .models import (
    ApprovalMode,
    ApprovalRequest,
    ApprovalStatus,
    Bot,
    Event,
    EventType,
    Run,
    iso,
    utcnow,
)
from .safety import Decision, PolicyEngine, Verdict
from .store import Store

#: safety re-check of the database while waiting. Normal wake-ups arrive over the bus (in-process)
#: or the wake hub (other processes); this only bounds the damage if a datagram is ever lost.
SAFETY_RECHECK_SECONDS = 30.0


class DeniedError(Exception):
    """The action was denied by policy or by a human."""


class ApprovalGate:
    """Consults policy + sticky allows + plan grants + human decisions for one run."""

    def __init__(
        self,
        store: Store,
        bot: Bot,
        run: Run,
        policy: PolicyEngine,
        emit: Callable[[Event], None],
        poll_seconds: float = SAFETY_RECHECK_SECONDS,
    ):
        self.store = store
        self.bot = bot
        self.run = run
        self.policy = policy
        self.emit = emit
        self.poll_seconds = poll_seconds
        self.ttl = store.config.default_approval_ttl_seconds  # unanswered approvals expire as denied

    # The engine sets this when the user hits "stop" so gates unblock quickly.
    cancel_requested: bool = False

    def decide(self, tool: str, action: str, detail: dict, decision: Optional[Decision] = None,
               outward: bool = False, ask_in_auto: bool = False) -> None:
        """Raise DeniedError unless the action may proceed.

        ``ask_in_auto``: ask even for a bot in auto mode (sticky allows and plan grants still apply). Used for the
        first call to a hosted model (LM-10): spending money and sending the conversation to a third party is not
        something "auto" should do silently on a bot that was set up to run locally.
        """
        if decision is None:
            decision = Decision(Verdict.ask, action, f"{tool}:*")
        outward = outward or decision.outward
        if decision.verdict is Verdict.allow and not outward:
            return
        if decision.verdict is Verdict.deny:
            self.emit(Event(run_id=self.run.id, type=EventType.log,
                            data={"denied": action, "reason": decision.reason, "rule": decision.rule}))
            raise DeniedError(f"denied by policy: {decision.reason}")

        # Sticky allows and plan grants never cover outward actions (SR-4).
        if not outward:
            if decision.sticky_key and self.store.is_sticky_allowed(self.bot.id, decision.sticky_key):
                self.emit(Event(run_id=self.run.id, type=EventType.log,
                                data={"note": f"sticky-allowed: {decision.sticky_key}"}))
                return
            if decision.sticky_key and self.run.plan_id and self.store.use_plan_grant(
                    self.run.plan_id, decision.sticky_key, self.bot.name):
                self.emit(Event(run_id=self.run.id, type=EventType.log,
                                data={"note": f"plan-granted: {decision.sticky_key}", "plan": self.run.plan_id}))
                return
            # "auto" mode skips asks (the hard-deny list already ran), but never for outward actions.
            if self.bot.approval_mode is ApprovalMode.auto and not ask_in_auto:
                return

        now = utcnow()
        req = ApprovalRequest(
            run_id=self.run.id, bot_id=self.bot.id, tool=tool,
            action=action, detail=detail,
            sticky_key="" if outward else decision.sticky_key,
            segments=list(decision.segments), rule=decision.rule or decision.reason,
            risk=decision.risk or ("high" if outward else "medium"), outward=outward,
            ttl_seconds=self.ttl, expires_at=iso(now + timedelta(seconds=self.ttl)),
            plan_id=self.run.plan_id,
        )
        self.store.create_approval(req)
        self.emit(Event(run_id=self.run.id, type=EventType.approval_request,
                        data={"approval_id": req.id, "tool": tool, "action": action,
                              "rule": req.rule, "risk": req.risk, "outward": outward,
                              "expires_at": req.expires_at, "detail": detail,
                              "segments": req.segments}))
        self._wait(req, action)

    def _wait(self, req: ApprovalRequest, action: str) -> None:
        from .models import RunStatus
        self.store.ensure_listening()  # so an approval from another process wakes us immediately
        bus = self.store.bus
        topics = {f"approval:{req.id}": 0, f"approval:wake:{self.run.id}": 0}
        deadline = time.monotonic() + self.ttl
        prev_status = self.run.status
        self.run.status = RunStatus.waiting_approval
        self.store.update_run(self.run)
        try:
            while True:
                for t in topics:
                    topics[t] = bus.version(t)  # read BEFORE checking state: no lost wake-ups
                if self.cancel_requested:
                    self._resolve(req, ApprovalStatus.expired, "stopped")
                    raise DeniedError("run was stopped while awaiting approval")
                current = self.store.get_approval(req.id)
                if current is None or current.status is not ApprovalStatus.pending:
                    status = current.status if current else ApprovalStatus.expired
                    if status is ApprovalStatus.approved:
                        self.emit(Event(run_id=self.run.id, type=EventType.approval_resolved,
                                        data={"approval_id": req.id, "result": "approved",
                                              "by": current.decided_by if current else ""}))
                        return
                    self.emit(Event(run_id=self.run.id, type=EventType.approval_resolved,
                                    data={"approval_id": req.id, "result": status.value}))
                    raise DeniedError(f"action rejected ({status.value}): {action}")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._resolve(req, ApprovalStatus.expired, "timeout")
                    self.emit(Event(run_id=self.run.id, type=EventType.approval_resolved,
                                    data={"approval_id": req.id, "result": "expired (denied)"}))
                    raise DeniedError(f"approval expired without answer: {action}")
                bus.wait_any(topics, timeout=min(remaining, self.poll_seconds))
        finally:
            if self.run.status is RunStatus.waiting_approval:
                self.run.status = prev_status if prev_status is not RunStatus.waiting_approval else RunStatus.running
                self.store.update_run(self.run)

    def wait_for_human(self, reason: str, url: str = "") -> None:
        """Park the run until a person clears a login / CAPTCHA / 2FA wall (UI-1 "Needs you").

        Hutch never attempts these challenges itself. The run shows as ``waiting_human`` with the
        cause and a Resume button; if nobody comes back before the deadline the run fails rather
        than spinning forever.
        """
        from .models import RunStatus
        self.store.ensure_listening()
        bus = self.store.bus
        self.store.consume_resume(self.run.id)  # drop any stale resume flag
        prev = self.run.status
        self.run.status = RunStatus.waiting_human
        self.store.update_run(self.run)
        deadline = time.monotonic() + self.ttl
        self.emit(Event(run_id=self.run.id, type=EventType.human_needed,
                        data={"reason": reason, "url": url,
                              "expires_at": iso(utcnow() + timedelta(seconds=self.ttl))}))
        topics = {f"human:{self.run.id}": 0, f"approval:wake:{self.run.id}": 0}
        try:
            while True:
                for t in topics:
                    topics[t] = bus.version(t)
                if self.cancel_requested:
                    raise DeniedError("run was stopped while waiting for a person")
                if self.store.consume_resume(self.run.id):
                    self.emit(Event(run_id=self.run.id, type=EventType.human_resumed, data={"url": url}))
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DeniedError(f"nobody cleared the login wall within {self.ttl}s: {reason}")
                bus.wait_any(topics, timeout=min(remaining, self.poll_seconds))
        finally:
            if self.run.status is RunStatus.waiting_human:
                self.run.status = prev if prev is not RunStatus.waiting_human else RunStatus.running
                self.store.update_run(self.run)

    def _resolve(self, req: ApprovalRequest, status: ApprovalStatus, by: str) -> None:
        req.status = status
        req.resolved_at = iso(utcnow())
        req.decided_by = by
        self.store.update_approval(req)


def resolve_approval(store: Store, approval_id: str, approve: bool, by: str = "human",
                     sticky: bool = False, plan_scope: int = 0) -> Optional[ApprovalRequest]:
    """Resolve a pending approval from CLI/dashboard.

    ``sticky`` remembers "always allow" for the bot (refused for outward actions).
    ``plan_scope`` > 0 grants the same action to the rest of the plan, bounded to that many uses (CO-10).
    """
    req = store.get_approval(approval_id)
    if req is None or req.status is not ApprovalStatus.pending:
        return req
    req.status = ApprovalStatus.approved if approve else ApprovalStatus.denied
    req.resolved_at = iso(utcnow())
    req.decided_by = by
    store.update_approval(req)
    if approve and sticky and req.sticky_key and not req.outward:
        store.allow_sticky(req.bot_id, req.sticky_key)
    if approve and plan_scope > 0 and req.plan_id and req.sticky_key and not req.outward:
        store.grant_plan(req.plan_id, req.sticky_key, max_uses=plan_scope, granted_by=by)
    return req


def expire_stale_approvals(store: Store, ttl_seconds: int = 600) -> list[ApprovalRequest]:
    """Deny-by-timeout any approval past its deadline; called by the scheduler loop."""
    import datetime as _dt
    expired: list[ApprovalRequest] = []
    now = utcnow()
    for req in store.pending_approvals():
        if req.expires_at:
            deadline = _dt.datetime.fromisoformat(req.expires_at)
        else:
            deadline = _dt.datetime.fromisoformat(req.created_at) + _dt.timedelta(seconds=ttl_seconds)
        if now > deadline:
            req.status = ApprovalStatus.expired
            req.resolved_at = iso(now)
            req.decided_by = "timeout"
            store.update_approval(req)
            expired.append(req)
    return expired
