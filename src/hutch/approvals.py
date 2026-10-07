"""Human-in-the-loop approval flow.

A tool that wants to perform an "ask" action creates an ApprovalRequest in the
store and blocks (polling) until a human resolves it from the dashboard or CLI,
or until a TTL expires — in which case the answer is DENY. Fail-closed is the
point: silence never becomes consent (the "agent emailed real lawyers" class of
incident).
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .models import ApprovalRequest, ApprovalStatus, Bot, EventType, Event, Run, iso, utcnow
from .safety import Decision, PolicyEngine, Verdict
from .store import Store


class DeniedError(Exception):
    """The action was denied by policy or by a human."""


class ApprovalGate:
    """Consults policy + sticky allows + human decisions for one run."""

    def __init__(
        self,
        store: Store,
        bot: Bot,
        run: Run,
        policy: PolicyEngine,
        emit: Callable[[Event], None],
        poll_seconds: float = 0.4,
    ):
        self.store = store
        self.bot = bot
        self.run = run
        self.policy = policy
        self.emit = emit
        self.poll_seconds = poll_seconds
        self.ttl = 600  # seconds; unanswered approvals expire as denied

    # The engine sets this when the user hits "stop" so gates unblock quickly.
    cancel_requested: bool = False

    def decide(self, tool: str, action: str, detail: dict, decision: Optional[Decision] = None) -> None:
        """Raise DeniedError unless the action may proceed."""
        if decision is None:
            decision = Decision(Verdict.ask, action, f"{tool}:*")
        if decision.verdict is Verdict.allow:
            return
        if decision.sticky_key and self.store.is_sticky_allowed(self.bot.id, decision.sticky_key):
            self.emit(Event(run_id=self.run.id, type=EventType.log,
                            data={"note": f"sticky-allowed: {decision.sticky_key}"}))
            return
        if decision.verdict is Verdict.deny:
            self.emit(Event(run_id=self.run.id, type=EventType.log,
                            data={"denied": action, "reason": decision.reason}))
            raise DeniedError(f"denied by policy: {decision.reason}")

        # Verdict.ask — auto mode still asks for nothing (denylist already passed)
        from .models import ApprovalMode
        if self.bot.approval_mode is ApprovalMode.auto:
            return

        req = ApprovalRequest(
            run_id=self.run.id, bot_id=self.bot.id, tool=tool,
            action=action, detail=detail, sticky_key=decision.sticky_key,
        )
        self.store.create_approval(req)
        self.emit(Event(run_id=self.run.id, type=EventType.approval_request,
                        data={"approval_id": req.id, "tool": tool, "action": action, **detail}))

        deadline = time.monotonic() + self.ttl
        while True:
            if self.cancel_requested:
                self._resolve(req, ApprovalStatus.expired, "stopped")
                raise DeniedError("run was stopped while awaiting approval")
            current = self.store.get_approval(req.id)
            if current is None or current.status is not ApprovalStatus.pending:
                status = current.status if current else ApprovalStatus.expired
                if status is ApprovalStatus.approved:
                    self.emit(Event(run_id=self.run.id, type=EventType.approval_resolved,
                                    data={"approval_id": req.id, "result": "approved"}))
                    return
                raise DeniedError(f"action rejected ({status.value}): {action}")
            if time.monotonic() > deadline:
                self._resolve(req, ApprovalStatus.expired, "timeout")
                self.emit(Event(run_id=self.run.id, type=EventType.approval_resolved,
                                data={"approval_id": req.id, "result": "expired (denied)"}))
                raise DeniedError(f"approval expired without answer: {action}")
            time.sleep(self.poll_seconds)

    def _resolve(self, req: ApprovalRequest, status: ApprovalStatus, by: str) -> None:
        req.status = status
        req.resolved_at = iso(utcnow())
        req.decided_by = by
        self.store.update_approval(req)


def resolve_approval(store: Store, approval_id: str, approve: bool, by: str = "human",
                     sticky: bool = False) -> Optional[ApprovalRequest]:
    """Resolve a pending approval from CLI/dashboard; optionally remember 'always allow'."""
    req = store.get_approval(approval_id)
    if req is None or req.status is not ApprovalStatus.pending:
        return req
    req.status = ApprovalStatus.approved if approve else ApprovalStatus.denied
    req.resolved_at = iso(utcnow())
    req.decided_by = by
    store.update_approval(req)
    if approve and sticky and req.sticky_key:
        store.allow_sticky(req.bot_id, req.sticky_key)
    return req


def expire_stale_approvals(store: Store, ttl_seconds: int = 600) -> list[ApprovalRequest]:
    """Deny-by-timeout any approval older than ttl; called by the daemon loop."""
    import datetime as _dt
    expired: list[ApprovalRequest] = []
    now = utcnow()
    for req in store.pending_approvals():
        created = _dt.datetime.fromisoformat(req.created_at)
        if (now - created).total_seconds() > ttl_seconds:
            req.status = ApprovalStatus.expired
            req.resolved_at = iso(now)
            req.decided_by = "timeout"
            store.update_approval(req)
            expired.append(req)
    return expired
