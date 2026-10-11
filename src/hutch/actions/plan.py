"""Inspectable action plans: what will happen, to what, under whose authority.

A request like "make me a brief for Thursday's meeting and put the table in the shared
folder" becomes an :class:`ActionPlan` — an ordered list of typed steps with explicit
targets. The plan is the unit a person reviews: :func:`plan_review` renders it, and
:func:`approval_scope_hash` binds the review to the exact content of every step. Changing
a step's inputs, target or idempotency key changes the hash, so a stale approval cannot
authorize a different write.

Authorities are classified per step, not per plan:

* ``none``      reads and local drafts — no external effect.
* ``review``    metered generation and cloud writes covered by the plan's one review.
* ``separate``  sharing and notifications — these never ride a bundle review.

The engine (``execute``) is a separate module; this module performs no I/O.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

ActionKind = Literal[
    "read",                # fetch something (no lasting effect)
    "local_draft",         # synthesize/derive locally (artifact, no remote effect)
    "metered_generation",  # a paid provider call (audio, images)
    "cloud_create",        # create a Docs/Sheets/Drive/Calendar object
    "cloud_edit",          # change an existing remote object
    "cloud_move",          # move/place an existing object
    "cloud_share",         # change who can see something
    "notify",              # message/invite people
    "event_create",
    "routine_config",      # configure a Hutch routine / reminder
]

Authority = Literal["none", "review", "separate"]

AUTHORITY_BY_KIND: dict[str, Authority] = {
    "read": "none",
    "local_draft": "none",
    "metered_generation": "review",
    "cloud_create": "review",
    "cloud_edit": "review",
    "cloud_move": "review",
    "event_create": "review",
    "routine_config": "review",
    "cloud_share": "separate",
    "notify": "separate",
}

#: kinds whose execution is journaled in the durable effect ledger
JOURNALED_KINDS = {
    "metered_generation", "cloud_create", "cloud_edit", "cloud_move",
    "cloud_share", "notify", "event_create", "routine_config",
}

PlanStatus = Literal["draft", "awaiting_approval", "approved", "executing",
                     "completed", "partial", "failed", "revoked"]

StepStatus = Literal["pending", "ready", "running", "succeeded", "failed",
                     "uncertain", "skipped", "denied"]

Service = Literal["local", "synthesis", "docs", "sheets", "drive", "calendar", "tasks", "routine"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class PlanTarget(BaseModel):
    """Exactly where an effect lands, with the identity a receipt must echo."""

    model_config = ConfigDict(extra="forbid")

    service: Service
    account: str = ""       # connection/principal id ("gws_..." / "gcal_...")
    resource_id: str = ""   # file/sheet/document/event id once known
    parent_id: str = ""     # destination folder/calendar ("drive folder id", calendar id)
    display: str = ""       # what the reviewer sees: the exact target's name/url
    audience: str = ""      # people or scope that will be able to see the result
    details: dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"stp_{secrets.token_hex(8)}")
    index: int = 0
    kind: ActionKind
    title: str
    description: str = ""
    target: PlanTarget
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    request_hash: str = ""
    idempotency_key: str = ""
    status: StepStatus = "pending"
    remote_id: str = ""
    error: str = ""
    verification: list[str] = Field(default_factory=list)
    receipt_id: str = ""  # syn_effects row id once attempted
    is_separate_authority: bool = False

    @model_validator(mode="after")
    def _kind_and_target(self) -> "PlanStep":
        if not self.title:
            self.title = f"{self.kind} on {self.target.service}"
        if self.kind not in AUTHORITY_BY_KIND:
            raise ValueError(f"unknown action kind {self.kind!r}")
        if not self.target.service:
            raise ValueError("every step target names a service")
        if not self.request_hash:
            self.request_hash = content_hash({
                "kind": self.kind,
                "target": self.target.model_dump(mode="json"),
                "inputs": self.inputs,
            })
        self.is_separate_authority = AUTHORITY_BY_KIND[self.kind] == "separate"
        return self

    def authority(self) -> Authority:
        return AUTHORITY_BY_KIND[self.kind]


class ActionPlan(BaseModel):
    """One reviewable plan. Its ``approval_scope_hash`` is what a review approves."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"plan_{secrets.token_hex(8)}")
    conversation_id: str = ""
    bot_id: str = ""
    run_id: str = ""
    intent: str = ""
    summary: str = ""
    policy_revision: str = "v1"
    steps: list[PlanStep] = Field(default_factory=list)
    status: PlanStatus = "draft"
    approval_scope_hash: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    notes: list[str] = Field(default_factory=list)

    def step(self, step_id: str) -> Optional[PlanStep]:
        return next((s for s in self.steps if s.id == step_id), None)

    def ordered_steps(self) -> list[PlanStep]:
        """Dependency order (stable by index within the same dependency depth)."""
        by_id = {s.id: s for s in self.steps}
        seen: set[str] = set()
        order: list[PlanStep] = []

        def visit(step: PlanStep, stack: frozenset[str]) -> None:
            if step.id in seen:
                return
            if step.id in stack:  # pragma: no cover - build_plan rejects cycles
                raise ValueError("dependency cycle")
            for dep in step.depends_on:
                visit(by_id[dep], stack | {step.id})
            seen.add(step.id)
            order.append(step)

        for step in sorted(self.steps, key=lambda s: s.index):
            visit(step, frozenset())
        return order

    def recompute_approval_scope(self) -> str:
        # Re-derive each step's request hash from its *current* content first, so a
        # post-build mutation of inputs/target cannot hide behind a stale hash.
        for step in self.steps:
            step.request_hash = content_hash({
                "kind": step.kind,
                "target": step.target.model_dump(mode="json"),
                "inputs": step.inputs,
            })
        self.approval_scope_hash = approval_scope_hash(self)
        return self.approval_scope_hash


def approval_scope_hash(plan: "ActionPlan") -> str:
    """The exact content a person approved: plans, targets, inputs, keys, policy revision."""
    return content_hash({
        "plan": plan.id,
        "policy_revision": plan.policy_revision,
        "steps": [
            {
                "id": s.id,
                "index": s.index,
                "kind": s.kind,
                "authority": s.authority(),
                "target": s.target.model_dump(mode="json"),
                "request_hash": s.request_hash,
                "idempotency_key": s.idempotency_key,
                "depends_on": sorted(s.depends_on),
            }
            for s in sorted(plan.steps, key=lambda s: s.index)
        ],
    })


def build_plan(intent: str, step_specs: list[dict[str, Any]], *,
               conversation_id: str = "", bot_id: str = "", run_id: str = "",
               policy_revision: str = "v1", summary: str = "") -> ActionPlan:
    """Validate a step list into a plan: kinds, targets, dependencies, idempotency keys.

    ``{"$remote_id": "<step id>"}`` references inside inputs create a dependency on that
    step automatically — the review approves the reference, execution resolves the id.

    Raises ``ValueError`` for anything that would make execution ambiguous (unknown
    dependency, dependency cycle, duplicate step ids).
    """
    if not step_specs:
        raise ValueError("an action plan needs at least one step")
    plan = ActionPlan(
        conversation_id=conversation_id, bot_id=bot_id, run_id=run_id, intent=intent,
        summary=summary or intent, policy_revision=policy_revision,
    )
    ids: set[str] = set()
    for index, spec in enumerate(step_specs):
        step = PlanStep(index=index, **spec)
        if step.id in ids:
            raise ValueError(f"duplicate step id {step.id}")
        ids.add(step.id)
        if not step.idempotency_key and step.kind in JOURNALED_KINDS:
            step.idempotency_key = f"{plan.id}:{index}:{step.request_hash[:16]}"
        plan.steps.append(step)
    for step in plan.steps:
        refs = input_step_refs(step.inputs)
        for ref in refs:
            if ref not in ids:
                raise ValueError(f"step {step.id} references unknown step {ref}")
            if ref not in step.depends_on:
                step.depends_on.append(ref)
        for dep in step.depends_on:
            if dep not in ids:
                raise ValueError(f"step {step.id} depends on unknown step {dep}")
    plan.ordered_steps()  # raises on cycles
    plan.recompute_approval_scope()
    return plan


def input_step_refs(value: Any) -> set[str]:
    """Every ``{"$remote_id": ...}`` reference inside a step input tree."""
    refs: set[str] = set()
    if isinstance(value, dict):
        if set(value.keys()) == {"$remote_id"}:
            refs.add(str(value["$remote_id"]))
        for v in value.values():
            refs |= input_step_refs(v)
    elif isinstance(value, list):
        for v in value:
            refs |= input_step_refs(v)
    return refs


def plan_review(plan: "ActionPlan") -> dict[str, Any]:
    """The exact review payload: targets, effects, authorities, and the binding hash."""
    review_steps = []
    for step in sorted(plan.steps, key=lambda s: s.index):
        review_steps.append({
            "id": step.id,
            "kind": step.kind,
            "authority": step.authority(),
            "title": step.title,
            "description": step.description,
            "service": step.target.service,
            "account": step.target.account,
            "target": step.target.display or step.target.resource_id or step.target.parent_id,
            "audience": step.target.audience,
            "idempotency_key": step.idempotency_key,
        })
    separate = [s["id"] for s in review_steps if s["authority"] == "separate"]
    return {
        "plan_id": plan.id,
        "intent": plan.intent,
        "summary": plan.summary,
        "status": plan.status,
        "policy_revision": plan.policy_revision,
        "steps": review_steps,
        "separate_authority_steps": separate,
        "review_note": (
            "Approving this plan authorizes exactly these steps on these targets. Steps "
            "listed under separate_authority_steps need their own decision and will not "
            "run from this approval."
        ),
        "approval_scope_hash": plan.approval_scope_hash or plan.recompute_approval_scope(),
    }


def next_plan_version_marker(plan: "ActionPlan") -> str:
    """A short stable marker for receipts: plan id + scope hash prefix."""
    return f"{plan.id}@{plan.approval_scope_hash[:12]}"
