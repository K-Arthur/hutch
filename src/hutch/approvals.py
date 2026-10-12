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

import hashlib
import json
import time
from datetime import timedelta
from dataclasses import dataclass
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


def action_fingerprint(tool: str, detail: dict, sticky_key: str = "", outward: bool = False) -> str:
    """A short, stable fingerprint of exactly what is being asked for. A decision is bound to it: if the action changes (other
    arguments, another destination) it is a different action and needs its own approval."""
    canon = json.dumps({"tool": tool, "detail": detail, "sticky": sticky_key, "outward": outward},
                       sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode()).hexdigest()[:32]


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
        self.last_authorization = None

    # The engine sets this when the user hits "stop" so gates unblock quickly.
    cancel_requested: bool = False

    def decide(self, tool: str, action: str, detail: dict, decision: Optional[Decision] = None,
               outward: bool = False, ask_in_auto: bool = False) -> None:
        """Raise DeniedError unless the action may proceed.

        ``ask_in_auto`` asks even for auto bots. ``outward`` also excludes sticky grants and
        applies to provider account/destination changes: auto must not silently send a
        conversation to another service or billing relationship.
        """
        if decision is None:
            decision = Decision(Verdict.ask, action, f"{tool}:*")
        from .action_receipts import freeze
        detail = freeze(detail)
        self.last_authorization = None
        outward = outward or decision.outward
        def authorized(source, request=None):
            self.last_authorization = {
                "tool": tool, "detail": detail, "source": source, "rule": decision.rule or decision.reason,
                "sticky_key": "" if outward else decision.sticky_key, "outward": outward,
                "action_hash": action_fingerprint(tool, detail, "" if outward else decision.sticky_key, outward),
                "approval_id": request.id if request else None,
                "expires_at": request.expires_at if request else None,
            }
        if decision.verdict is Verdict.allow and not outward:
            authorized("policy")
            return
        if decision.verdict is Verdict.deny:
            self.emit(Event(run_id=self.run.id, type=EventType.log,
                            data={"denied": action, "reason": decision.reason, "rule": decision.rule}))
            raise DeniedError(f"denied by policy: {decision.reason}")

        # Sticky allows never cover outward actions (SR-4).
        if not outward:
            if decision.sticky_key and self.store.is_sticky_allowed(self.bot.id, decision.sticky_key):
                self.emit(Event(run_id=self.run.id, type=EventType.log,
                                data={"note": f"sticky-allowed: {decision.sticky_key}"}))
                authorized("standing_permission")
                return
            # "auto" mode skips asks (the hard-deny list already ran), but never for outward actions.
            if self.bot.approval_mode is ApprovalMode.auto and not ask_in_auto:
                authorized("bot_auto_permission")
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
            action_hash=action_fingerprint(tool, detail, "" if outward else decision.sticky_key, outward),
        )
        prev_status = self.run.status
        # Register cross-process delivery before the durable request becomes
        # visible. A reviewer can decide as soon as the UI receives it.
        self.store.ensure_listening()
        self.store.create_approval(req, expected_fence=self.run.fence, begin_wait=True)
        if req.status is ApprovalStatus.expired:
            self.emit(Event(run_id=self.run.id, type=EventType.approval_resolved,
                            data={"approval_id": req.id, "result": "expired", "by": req.decided_by}))
            raise DeniedError("run stopped before the approval request was admitted")
        from .models import RunStatus
        self.run.status = RunStatus.waiting_approval
        # Store commits the review event with admission and status. A crash
        # here cannot leave a waiting run without its inline review details.
        self._wait(req, action, prev_status=prev_status)
        authorized("reviewed_once", req)

    def _wait(self, req: ApprovalRequest, action: str, *, prev_status=None) -> None:
        from .models import RunStatus
        self.store.ensure_listening()  # so an approval from another process wakes us immediately
        bus = self.store.bus
        topics = {f"approval:{req.id}": 0, f"approval:wake:{self.run.id}": 0}
        deadline = time.monotonic() + self.ttl
        prev_status = prev_status or self.run.status
        if self.run.status is not RunStatus.waiting_approval and not self.store.set_status(self.run, RunStatus.waiting_approval):
            self._resolve(req, ApprovalStatus.expired, "stopped")          # the run cannot wait now (stopping, ended): do not
            raise DeniedError(f"the run is {self.run.status.value}; the action was not approved")
        try:
            while True:
                for t in topics:
                    topics[t] = bus.version(t)  # read BEFORE checking state: no lost wake-ups
                if self.cancelled():
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
                    _, outcome = self.store.decide_approval(req.id, ApprovalStatus.expired, "timeout")
                    if outcome == "already":
                        continue          # a person decided in the same instant: honour that decision, not the timeout
                    self.emit(Event(run_id=self.run.id, type=EventType.approval_resolved,
                                    data={"approval_id": req.id, "result": "expired (denied)"}))
                    raise DeniedError(f"approval expired without answer: {action}")
                bus.wait_any(topics, timeout=min(remaining, self.poll_seconds))
        finally:
            if self.run.status is RunStatus.waiting_approval:
                self.store.set_status(self.run, prev_status if prev_status is not RunStatus.waiting_approval
                                      else RunStatus.running)

    def cancelled(self) -> bool:
        """A stop was requested: in this process (the flag) or in any other (the database)."""
        return self.cancel_requested or self.store.is_cancel_requested(self.run.id)

    def wait_for_human(self, reason: str, url: str = "", handoff: str = "") -> None:
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
        if not self.store.set_status(self.run, RunStatus.waiting_human):
            raise DeniedError(f"the run is {self.run.status.value}; it will not wait for a person")
        deadline = time.monotonic() + self.ttl
        self.emit(Event(run_id=self.run.id, type=EventType.human_needed,
                        data={"reason": reason, "url": url,
                              "handoff": handoff,
                              "expires_at": iso(utcnow() + timedelta(seconds=self.ttl))}))
        topics = {f"human:{self.run.id}": 0, f"approval:wake:{self.run.id}": 0}
        try:
            while True:
                for t in topics:
                    topics[t] = bus.version(t)
                if self.cancelled():
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
                self.store.set_status(self.run, prev if prev is not RunStatus.waiting_human else RunStatus.running)

    def _resolve(self, req: ApprovalRequest, status: ApprovalStatus, by: str) -> None:
        self.store.decide_approval(req.id, status, by)


@dataclass
class Resolution:
    """What a resolve call did: ``outcome`` is won | already | expired | mismatch | missing (see ``Store.decide_approval``)."""

    request: Optional[ApprovalRequest]
    outcome: str

    @property
    def won(self) -> bool:
        return self.outcome == "won"


def resolve_approval_ex(store: Store, approval_id: str, approve: bool, by: str = "human", sticky: bool = False,
                        expected_hash: Optional[str] = None, idem_key: Optional[str] = None,
                        request_hash: Optional[str] = None) -> Resolution:
    """Resolve a pending approval from the CLI, dashboard or API - atomically, once.

    Only the call that actually decided it (``won``) may grant an "always" rule; a request that lost the race, expired or was
    shown a different action changes nothing. ``expected_hash`` is the ``action_hash`` the person was shown: if the stored action
    is different, nothing is decided. ``sticky`` remembers "always allow" for the bot (refused for outward actions).
    """
    req, outcome = store.decide_approval(
        approval_id, ApprovalStatus.approved if approve else ApprovalStatus.denied, by, expected_hash=expected_hash,
        sticky=sticky, idem_key=idem_key, request_hash=request_hash)
    return Resolution(req, outcome)


def resolve_approval(store: Store, approval_id: str, approve: bool, by: str = "human",
                     sticky: bool = False, plan_scope: int = 0) -> Optional[ApprovalRequest]:
    """Back-compatible form of ``resolve_approval_ex``: returns the request as it now stands (decided by us or by someone
    else). ``plan_scope`` is accepted and ignored: plan-wide grants were referenced but never implemented."""
    return resolve_approval_ex(store, approval_id, approve, by=by, sticky=sticky).request


def expire_stale_approvals(store: Store, ttl_seconds: int = 600) -> list[ApprovalRequest]:
    """Deny-by-timeout any approval past its deadline; called by the scheduler loop. Each is decided by the same atomic
    compare-and-swap as a human decision, so a person answering at the last moment is not overwritten."""
    import datetime as _dt
    expired: list[ApprovalRequest] = []
    now = utcnow()
    for req in store.pending_approvals():
        if req.expires_at:
            deadline = _dt.datetime.fromisoformat(req.expires_at)
        else:
            deadline = _dt.datetime.fromisoformat(req.created_at) + _dt.timedelta(seconds=ttl_seconds)
        if now > deadline:
            done, outcome = store.decide_approval(req.id, ApprovalStatus.expired, "timeout")
            if outcome == "won" and done is not None:
                expired.append(done)
    return expired
