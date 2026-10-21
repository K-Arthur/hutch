"""Typed workflow API: definitions, revisions, runs, nodes, questions, qualifications.

Registered from ``create_app`` like the page sub-registrars, so the JSON surface keeps one
app factory while this module keeps the workflow resource in one place. Every route is
``/api/v1`` and owner-only by default (the startup route inventory leaves unmapped routes
local); mutations need an ``Idempotency-Key``. Validation and amendment preview are
read-only: they compile and check authority without admitting work.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from ..models import Bot, iso, utcnow
from ..workflow import persistence as wstore
from ..workflow import qualify
from ..workflow import routing
from ..workflow import submit as wfsubmit
from ..workflow.compile import CEILINGS, PlanInvalid, compile_plan, plan_structure

MAX_PLAN_BYTES = CEILINGS["max_plan_bytes"]


# ------------------------------------------------------------------- resources

class WorkflowDefinitionResource(BaseModel):
    id: str
    name: str
    description: str = ""
    active: bool = False
    source: str = "operator"
    revisions: int = 0
    latest_revision_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class WorkflowDefinitionPage(BaseModel):
    items: list[WorkflowDefinitionResource]
    limit: int
    offset: int


class WorkflowPlanResource(BaseModel):
    definition_id: Optional[str] = None
    revision_id: Optional[str] = None
    revision: Optional[int] = None
    plan_hash: str
    plan: dict[str, Any]


class DiagnosticResource(BaseModel):
    code: str
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"


class WorkflowValidationResource(BaseModel):
    ok: bool
    plan_hash: Optional[str] = None
    diagnostics: list[DiagnosticResource] = Field(default_factory=list)
    warnings: list[DiagnosticResource] = Field(default_factory=list)
    roles: list[dict[str, Any]] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    node_count: int = 0


class WorkflowRunResource(BaseModel):
    id: str
    definition_id: Optional[str] = None
    revision_id: str
    plan_hash: str
    bot_id: str
    conversation_id: str = ""
    status: str
    reason: str = ""
    origin: str = "operator"
    attempt_run_id: str = ""
    stop_requested: bool = False
    pause_requested: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    ledger: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    finished_at: Optional[str] = None


class WorkflowNodeResource(BaseModel):
    site_id: str
    instance_key: str
    kind: str
    status: str
    attempt: int = 1
    run_id: Optional[str] = None
    input_hash: str = ""
    result: Any = None
    error: Any = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class WorkflowQuestionResource(BaseModel):
    id: str
    site_id: str
    instance_key: str
    question: str
    options: list[str] = Field(default_factory=list)
    status: str
    revision_id: str = ""
    attempt_run_id: str = ""
    answer: str = ""
    asked_at: str
    expires_at: str
    answered_at: Optional[str] = None


class PhoneWorkflowNodeResource(BaseModel):
    site_id: str
    instance_number: int
    kind: str
    status: str


class PhoneWorkflowPlannedStepResource(BaseModel):
    site_id: str
    kind: str
    depth: int = 0
    bounded: bool = False


class PhoneWorkflowRunSummary(BaseModel):
    id: str
    title: str
    bot_display_name: str
    status: str
    stop_requested: bool = False
    pause_requested: bool = False
    pause_ready: bool = False
    created_at: str
    updated_at: str
    step_count: int = 0
    planned_step_count: int = 0
    needs_you: int = 0


class PhoneWorkflowRunPage(BaseModel):
    items: list[PhoneWorkflowRunSummary]
    limit: int
    offset: int


class PhoneWorkflowRunDetail(PhoneWorkflowRunSummary):
    revision_id: str
    planned_steps: list[PhoneWorkflowPlannedStepResource] = Field(default_factory=list)
    nodes: list[PhoneWorkflowNodeResource] = Field(default_factory=list)


class PhoneWorkflowQuestionResource(BaseModel):
    id: str
    workflow_run_id: str
    workflow_title: str
    bot_display_name: str
    site_id: str
    question: str
    options: list[str] = Field(default_factory=list)
    expires_at: str


class PhoneWorkflowQuestionPage(BaseModel):
    items: list[PhoneWorkflowQuestionResource]
    limit: int
    offset: int


class PhoneWorkflowMutationResource(BaseModel):
    workflow_run_id: str
    status: str
    question_id: Optional[str] = None
    stop_requested: Optional[bool] = None


class WorkflowRunPage(BaseModel):
    items: list[WorkflowRunResource]
    limit: int
    offset: int


class WorkflowRunDetail(BaseModel):
    workflow: WorkflowRunResource
    attempt: Optional[dict[str, Any]] = None
    nodes: list[WorkflowNodeResource] = Field(default_factory=list)
    questions: list[WorkflowQuestionResource] = Field(default_factory=list)
    plan: Optional[dict[str, Any]] = None
    structure: list[dict[str, Any]] = Field(default_factory=list)
    pause_available: bool = False
    pause_after_work_available: bool = False
    resume_available: bool = False


class WorkflowAmendmentPreviewRequest(BaseModel):
    expected_revision_id: str = Field(min_length=1, max_length=100)
    # The active orchestration attempt ID is the opaque generation token; replacement
    # after recovery makes a preview captured by an older owner stale.
    expected_generation: str = Field(min_length=1, max_length=100)
    plan: dict[str, Any]
    inputs: Optional[dict[str, Any]] = None


class WorkflowAmendmentAdoptRequest(WorkflowAmendmentPreviewRequest):
    cancel_pending_questions: bool = False


class WorkflowAmendmentDrainRequest(WorkflowAmendmentPreviewRequest):
    pass


class WorkflowAmendmentFieldChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class WorkflowAmendmentNodeDiff(BaseModel):
    site_id: str
    change: Literal["added", "removed", "changed"]
    fields: list[WorkflowAmendmentFieldChange] = Field(default_factory=list)
    dependencies_changed: Optional[bool] = None


class WorkflowAmendmentNodeState(BaseModel):
    site_id: str
    instance_key: str
    status: str


class WorkflowAmendmentReuseResource(WorkflowAmendmentNodeState):
    input_hash: str


class WorkflowAmendmentInvalidationResource(WorkflowAmendmentNodeState):
    reason: str


class WorkflowAmendmentCarryResource(WorkflowAmendmentNodeState):
    run_id: str
    input_hash: str
    model: str
    role: str
    role_state: str
    binding_fingerprint: str
    instruction_hash: str
    output_schema: Optional[dict[str, Any]] = None
    max_steps: int
    timeout_seconds: int
    reason: str = ""


class WorkflowAmendmentDrainedResource(WorkflowAmendmentNodeState):
    run_id: str
    reason: str = ""


class WorkflowAmendmentDrainableResource(WorkflowAmendmentNodeState):
    run_id: str
    cancel_requested: bool = False
    reason: str = ""


class WorkflowAmendmentDrainEntry(BaseModel):
    site_id: str
    instance_key: str
    run_id: str
    status: str


class WorkflowAmendmentDrainResult(BaseModel):
    workflow_run_id: str
    revision_id: str
    attempt_run_id: str
    requested: list[WorkflowAmendmentDrainEntry] = Field(default_factory=list)
    message: str


class WorkflowAmendmentBudgetResource(BaseModel):
    current: Optional[int] = None
    proposed: Optional[int] = None
    effective_if_adopted: Optional[int] = None
    used: Optional[int] = None
    remaining_now: Optional[int] = None


class WorkflowAmendmentQuiescenceResource(BaseModel):
    workflow_status: str
    attempt_status: str = ""
    attempt_parked: bool = False
    owned_work_quiet: bool = False
    owned_work_carryable: bool = False
    active_nodes: list[WorkflowAmendmentNodeState] = Field(default_factory=list)
    carry_active_nodes: list[WorkflowAmendmentCarryResource] = Field(default_factory=list)
    drainable_active_nodes: list[WorkflowAmendmentDrainableResource] = Field(default_factory=list)
    drained_active_nodes: list[WorkflowAmendmentDrainedResource] = Field(default_factory=list)
    pending_question_ids: list[str] = Field(default_factory=list)
    required: bool = False


class WorkflowAmendmentPreviewResource(BaseModel):
    workflow_run_id: str
    current_revision_id: str
    current_generation: str
    current_plan_hash: str
    candidate_plan_hash: str
    candidate_inputs: dict[str, Any] = Field(default_factory=dict)
    plan_changed: bool = False
    changed_fields: list[WorkflowAmendmentFieldChange] = Field(default_factory=list)
    nodes: list[WorkflowAmendmentNodeDiff] = Field(default_factory=list)
    added_sites: list[str] = Field(default_factory=list)
    removed_sites: list[str] = Field(default_factory=list)
    changed_sites: list[str] = Field(default_factory=list)
    reuse: list[WorkflowAmendmentReuseResource] = Field(default_factory=list)
    invalidate: list[WorkflowAmendmentInvalidationResource] = Field(default_factory=list)
    budgets: dict[str, WorkflowAmendmentBudgetResource] = Field(default_factory=dict)
    roles: list[dict[str, Any]] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    eligible: bool = Field(
        default=False,
        description="The candidate passes current authority and budget checks; this is not adoption readiness.",
    )
    quiescence: WorkflowAmendmentQuiescenceResource


class WorkflowAmendmentAdoptResource(BaseModel):
    workflow_run_id: str
    history_id: str
    previous_revision_id: str
    revision_id: str
    attempt_run_id: str
    plan_hash: str
    cancelled_question_ids: list[str] = Field(default_factory=list)
    preview: WorkflowAmendmentPreviewResource


class WorkflowAmendmentHistorySummary(BaseModel):
    id: str
    previous_revision_id: str
    adopted_revision_id: str
    previous_attempt_run_id: str
    previous_status: str
    previous_plan_hash: str
    adopted_plan_hash: str
    created_at: str


class WorkflowAmendmentHistoryPage(BaseModel):
    items: list[WorkflowAmendmentHistorySummary]
    limit: int
    offset: int


class WorkflowAmendmentHistoryDetail(WorkflowAmendmentHistorySummary):
    preview: WorkflowAmendmentPreviewResource
    nodes: list[WorkflowNodeResource] = Field(default_factory=list)
    questions: list[WorkflowQuestionResource] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class WorkflowSubmissionResource(BaseModel):
    workflow_run_id: str
    attempt_run_id: str
    revision_id: str
    definition_id: Optional[str] = None
    plan_hash: str
    roles: list[dict[str, Any]] = Field(default_factory=list)


class SaveDefinitionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    plan: dict[str, Any]
    description: str = Field(default="", max_length=1000)
    note: str = Field(default="", max_length=500)
    activate: bool = False


class SubmitPlanRequest(BaseModel):
    plan: dict[str, Any]
    inputs: dict[str, Any] = Field(default_factory=dict)
    bot: str = Field(min_length=1, max_length=120)
    conversation_id: str = Field(default="", max_length=100)
    definition_name: str = Field(default="", max_length=120)
    save_definition: bool = True
    source: Literal["operator", "model"] = "operator"
    planning_model: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=500)
    #: Marks this submission as an *automatic* start, which must fit the Bot's
    #: preauthorized workflow scope. A person's explicit start leaves it false.
    auto: bool = False


class RunSavedRequest(BaseModel):
    bot: str = Field(min_length=1, max_length=120)
    conversation_id: str = Field(default="", max_length=100)
    inputs: dict[str, Any] = Field(default_factory=dict)
    auto: bool = False


class WorkflowStopRequest(BaseModel):
    expected_revision_id: str = Field(min_length=1, max_length=100)


class WorkflowPauseRequest(WorkflowStopRequest):
    expected_generation: str = Field(min_length=1, max_length=100)


class WorkflowPauseMutationResource(BaseModel):
    workflow_run_id: str
    revision_id: str
    attempt_run_id: str
    status: str
    paused: bool
    parked: bool = False


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class QualificationRequest(BaseModel):
    bot: str = Field(min_length=1, max_length=120)
    role: Literal["worker", "verifier"]
    reason: str = Field(min_length=1, max_length=500)
    scope: dict[str, Any] = Field(default_factory=dict)


class QualificationProbeRequest(BaseModel):
    bot: str = Field(min_length=1, max_length=120)
    role: Literal["author", "selector"]
    campaign_id: str = Field(default="dynamic-workflows-initial", min_length=1, max_length=80,
                             pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")


class QualificationProbeResource(BaseModel):
    id: str
    campaign_id: str
    provider: str
    model: str
    role: str
    status: str
    route_revision: str
    execution_profile: dict[str, Any]
    requests: list[dict[str, Any]] = Field(default_factory=list)
    reason: str = ""


class WorkflowPolicyRequest(BaseModel):
    """The operator's workflow policy for one Bot. Saving a policy starts nothing."""

    bot: str = Field(min_length=1, max_length=120)
    mode: Literal["off", "suggest", "auto"]
    definitions: list[str] = Field(default_factory=list, max_length=50)
    max_nodes: Optional[int] = Field(default=None, ge=1, le=2_000)
    max_model_calls: Optional[int] = Field(default=None, ge=0, le=500)
    max_tokens: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    max_wall_seconds: Optional[int] = Field(default=None, ge=5, le=86_400)
    max_fanout: Optional[int] = Field(default=None, ge=1, le=100)


class ConversationWorkflowPolicyRequest(BaseModel):
    mode: Literal["inherit", "off", "suggest", "auto"]
    expected_revision: int = Field(default=0, ge=0)


def _structure(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return plan_structure(plan)


def _plan_size(plan: dict[str, Any]) -> None:
    if len(json.dumps(plan, default=str)) > MAX_PLAN_BYTES:
        raise HTTPException(413, f"the plan exceeds {MAX_PLAN_BYTES} bytes")


def _bot_or_404(store: Any, ref: str) -> Bot:
    bot = store.get_bot(ref)
    if bot is None:
        raise HTTPException(404, "no such Bot")
    return bot


def _definition_resource(row: dict[str, Any]) -> WorkflowDefinitionResource:
    return WorkflowDefinitionResource(
        id=str(row["id"]), name=str(row["name"]), description=str(row.get("description") or ""),
        active=bool(row.get("active")), source=str(row.get("source") or "operator"),
        revisions=int(row.get("revisions") or 0), created_at=str(row.get("created_at") or ""),
        latest_revision_id=(str(row["latest_revision_id"]) if row.get("latest_revision_id") else None),
        updated_at=str(row.get("updated_at") or ""))


def _node_resource(row: dict[str, Any]) -> WorkflowNodeResource:
    return WorkflowNodeResource(
        site_id=str(row["site_id"]), instance_key=str(row["instance_key"]), kind=str(row["kind"]),
        status=str(row["status"]), attempt=int(row.get("attempt") or 1),
        run_id=(str(row["run_id"]) if row.get("run_id") else None),
        input_hash=str(row.get("input_hash") or ""),
        result=row["result"] if "result" in row else None,
        error=row["error"] if "error" in row else None,
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"))


def _question_resource(row: dict[str, Any]) -> WorkflowQuestionResource:
    return WorkflowQuestionResource(
        id=str(row["id"]), site_id=str(row["site_id"]), instance_key=str(row["instance_key"]),
        question=str(row["question"]), options=list(row.get("options") or []),
        status=str(row["status"]), revision_id=str(row.get("revision_id") or ""),
        attempt_run_id=str(row.get("attempt_run_id") or ""), answer=str(row.get("answer") or ""),
        asked_at=str(row["asked_at"]), expires_at=str(row["expires_at"]),
        answered_at=row.get("answered_at"))


def _run_resource(row: dict[str, Any]) -> WorkflowRunResource:
    return WorkflowRunResource(
        id=str(row["id"]), definition_id=row.get("definition_id"), revision_id=str(row["revision_id"]),
        plan_hash=str(row["plan_hash"]), bot_id=str(row["bot_id"]),
        conversation_id=str(row.get("conversation_id") or ""), status=str(row["status"]),
        reason=str(row.get("reason") or ""), origin=str(row.get("origin") or "operator"),
        attempt_run_id=str(row.get("attempt_run_id") or ""),
        stop_requested=bool(row.get("stop_requested")), pause_requested=bool(row.get("pause_requested")),
        inputs=row.get("inputs") or {},
        budget=row.get("budget") or {}, ledger=row.get("ledger") or {}, result=row.get("result") or {},
        created_at=str(row.get("created_at") or ""), updated_at=str(row.get("updated_at") or ""),
        finished_at=row.get("finished_at"))


def _phone_workflow_nodes(store: Any, row: dict[str, Any]) -> list[dict[str, Any]]:
    """Project observed nodes and question-backed ask instances without exposing runtime keys."""
    wf_id = str(row["id"])
    revision_id = str(row.get("revision_id") or "")
    attempt_run_id = str(row.get("attempt_run_id") or "")
    raw_nodes = wstore.nodes(store, wf_id)
    identities = {(str(node["site_id"]), str(node["instance_key"])) for node in raw_nodes}
    observed: list[dict[str, Any]] = [
        {"site_id": str(node["site_id"]), "instance_key": str(node["instance_key"]),
         "kind": str(node["kind"]), "status": str(node["status"])}
        for node in raw_nodes
    ]
    question_status = {"pending": "waiting", "answered": "succeeded",
                       "expired": "failed", "cancelled": "cancelled"}
    for question in wstore.questions(store, wf_id):
        identity = (str(question["site_id"]), str(question["instance_key"]))
        if (identity in identities or str(question.get("revision_id") or "") != revision_id
                or str(question.get("attempt_run_id") or "") != attempt_run_id):
            continue
        observed.append({"site_id": identity[0], "instance_key": identity[1], "kind": "ask",
                         "status": question_status.get(str(question.get("status") or ""), "unknown")})
        identities.add(identity)
    site_counts: dict[str, int] = {}
    projected = []
    for item in observed:
        site_id = item["site_id"]
        site_counts[site_id] = site_counts.get(site_id, 0) + 1
        projected.append({"site_id": site_id, "instance_number": site_counts[site_id],
                          "kind": item["kind"], "status": item["status"]})
    return projected


def _phone_workflow_summary(store: Any, row: dict[str, Any]) -> dict[str, Any]:
    revision = wstore.revision(store, str(row.get("revision_id") or ""))
    plan = (revision or {}).get("plan") or {}
    bot = store.get_bot(str(row.get("bot_id") or ""))
    nodes = _phone_workflow_nodes(store, row)
    pending = [question for question in wstore.questions(store, str(row["id"]), status="pending")
               if str(question.get("revision_id") or "") == str(row.get("revision_id") or "")
               and str(question.get("attempt_run_id") or "") == str(row.get("attempt_run_id") or "")]
    pause_controls = wstore.workflow_pause_controls(store, str(row["id"]))
    return {
        "id": str(row["id"]),
        "title": str(plan.get("name") or "Workflow"),
        "bot_display_name": str((bot.display_name if bot else "") or (bot.name if bot else "Assistant")),
        "status": str(row.get("status") or "unknown"),
        "stop_requested": bool(row.get("stop_requested")),
        "pause_requested": bool(row.get("pause_requested")),
        "pause_ready": pause_controls["pause_ready"],
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "step_count": len(nodes),
        "planned_step_count": len(_structure(plan)),
        "needs_you": len(pending),
    }


def _phone_workflow_question(store: Any, row: dict[str, Any]) -> PhoneWorkflowQuestionResource:
    revision = wstore.revision(store, str(row.get("revision_id") or ""))
    plan = (revision or {}).get("plan") or {}
    bot = store.get_bot(str(row.get("bot_id") or ""))
    options = row.get("options")
    if options is None:
        raw_options = row.get("options_json") or "[]"
        options = json.loads(raw_options) if isinstance(raw_options, str) else []
    return PhoneWorkflowQuestionResource(
        id=str(row["id"]), workflow_run_id=str(row["workflow_run_id"]),
        workflow_title=str(plan.get("name") or "Workflow"),
        bot_display_name=str((bot.display_name if bot else "") or (bot.name if bot else "Assistant")),
        site_id=str(row["site_id"]),
        question=str(row["question"]), options=list(options), expires_at=str(row["expires_at"]))


def register_workflow_api(app: Any, store: Any, engine: Any, *, idempotency_key: Any,
                          request_digest: Any) -> None:
    """Attach the workflow routes to the existing app factory.

    ``idempotency_key``/``request_digest`` are the app's own helpers, passed in rather than
    re-implemented, so a paired phone's receipts stay isolated per credential exactly as they
    are everywhere else.
    """

    def _idempotency(request: Request, payload: Any) -> tuple[str, str]:
        return idempotency_key(request), request_digest(payload)

    @app.get("/api/v1/workflows", response_model=WorkflowDefinitionPage)
    def list_workflows(limit: int = 50, offset: int = 0) -> WorkflowDefinitionPage:
        try:
            rows = wstore.list_definitions(store, limit=limit, offset=offset)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return WorkflowDefinitionPage(items=[_definition_resource(row) for row in rows],
                                      limit=limit, offset=offset)

    @app.post("/api/v1/workflows", response_model=WorkflowDefinitionResource, status_code=201)
    def save_workflow(payload: SaveDefinitionRequest, request: Request) -> WorkflowDefinitionResource:
        _plan_size(payload.plan)
        _idempotency(request, payload.model_dump())
        try:
            saved = wstore.save_definition(store, name=payload.name, plan=payload.plan,
                                           description=payload.description, note=payload.note,
                                           source="operator", activate=payload.activate)
        except PlanInvalid as exc:
            raise HTTPException(422, {"code": "plan_invalid",
                                      "diagnostics": [d.render() for d in exc.diagnostics]}) from None
        row = wstore.definition(store, saved["definition_id"])
        assert row is not None
        return _definition_resource(row)

    @app.get("/api/v1/workflows/runs", response_model=WorkflowRunPage)
    def list_workflow_runs(bot: str = "", limit: int = 50, offset: int = 0) -> WorkflowRunPage:
        bot_id = ""
        if bot:
            bot_id = _bot_or_404(store, bot).id
        try:
            rows = wstore.list_workflow_runs(store, bot_id=bot_id, limit=limit, offset=offset)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return WorkflowRunPage(items=[_run_resource(row) for row in rows], limit=limit, offset=offset)

    @app.get("/api/v1/phone/workflows/runs", response_model=PhoneWorkflowRunPage)
    def list_phone_workflow_runs(limit: int = 40, offset: int = 0) -> PhoneWorkflowRunPage:
        try:
            rows = wstore.list_workflow_runs(store, limit=limit, offset=offset)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return PhoneWorkflowRunPage(
            items=[PhoneWorkflowRunSummary(**_phone_workflow_summary(store, row)) for row in rows],
            limit=limit, offset=offset)

    @app.get("/api/v1/phone/workflows/runs/{wf_id}", response_model=PhoneWorkflowRunDetail)
    def get_phone_workflow_run(wf_id: str) -> PhoneWorkflowRunDetail:
        row = wstore.workflow_run(store, wf_id)
        if row is None:
            raise HTTPException(404, "no such workflow run")
        summary = _phone_workflow_summary(store, row)
        summary["revision_id"] = str(row["revision_id"])
        revision = wstore.revision(store, str(row["revision_id"]))
        plan = (revision or {}).get("plan") or {}
        summary["planned_steps"] = [PhoneWorkflowPlannedStepResource(
            site_id=str(step.get("site_id") or ""), kind=str(step.get("kind") or "unknown"),
            depth=int(step.get("depth") or 0), bounded=bool(step.get("bounded")))
            for step in _structure(plan)]
        nodes = [PhoneWorkflowNodeResource(**node) for node in _phone_workflow_nodes(store, row)]
        return PhoneWorkflowRunDetail(**summary, nodes=nodes)

    @app.get("/api/v1/phone/workflows/questions", response_model=PhoneWorkflowQuestionPage)
    def list_phone_workflow_questions(limit: int = 100, offset: int = 0) -> PhoneWorkflowQuestionPage:
        try:
            rows = wstore.pending_questions_for_review(store, limit=limit, offset=offset)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return PhoneWorkflowQuestionPage(
            items=[_phone_workflow_question(store, row) for row in rows], limit=limit, offset=offset)

    @app.post("/api/v1/phone/workflows/questions/{question_id}/answer",
              response_model=PhoneWorkflowMutationResource)
    def answer_phone_workflow_question(
            question_id: str, payload: AnswerRequest, request: Request) -> PhoneWorkflowMutationResource:
        _idempotency(request, {"question": question_id, "answer": payload.answer})
        try:
            outcome = wfsubmit.answer(store, question_id, payload.answer)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if outcome == "missing":
            raise HTTPException(404, "no such question")
        if outcome == "expired":
            raise HTTPException(409, {"code": "question_expired", "message": "this question expired unanswered"})
        row = wstore.question(store, question_id)
        if row is None or (outcome == "already" and row["status"] != "answered"):
            raise HTTPException(409, {"code": "question_not_answerable",
                                      "message": f"this question is {row['status'] if row else 'missing'}"})
        if outcome != "already":
            engine.store.bus.notify("work")
        return PhoneWorkflowMutationResource(
            workflow_run_id=str(row["workflow_run_id"]), question_id=question_id, status=str(row["status"]))

    @app.post("/api/v1/phone/workflows/runs/{wf_id}/stop", response_model=PhoneWorkflowMutationResource)
    def stop_phone_workflow_run(
            wf_id: str, payload: WorkflowStopRequest, request: Request) -> PhoneWorkflowMutationResource:
        _idempotency(request, {"stop": wf_id, **payload.model_dump()})
        try:
            stopped = wfsubmit.stop_workflow(store, wf_id, expected_revision_id=payload.expected_revision_id)
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        engine.store.bus.notify("work")
        current = wstore.workflow_run(store, wf_id)
        return PhoneWorkflowMutationResource(
            workflow_run_id=wf_id, status=str((current or {}).get("status") or "unknown"),
            stop_requested=bool(stopped.get("stop_requested")))

    @app.get("/api/v1/workflows/qualifications")
    def list_qualifications(limit: int = 100, offset: int = 0) -> dict[str, Any]:
        try:
            return {"items": store.list_role_qualifications(limit=limit, offset=offset)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/v1/workflows/qualifications/assess")
    def assess_role(bot: str, role: str, requires_tools: bool = False) -> dict[str, Any]:
        resolved = _bot_or_404(store, bot)
        connections = qualify.connections_for_store(store)
        execution_profile_hash = None
        if role in qualify.PROBE_ONLY_ROLES:
            try:
                from ..providers import make_provider, parse_spec
                from ..providers.connection import provider_for_connection
                from ..route_identity import default_endpoint
                from ..workflow.probes import inspect_probe_profile

                provider_name, _model = parse_spec(resolved.model)
                route = qualify.route_ref(resolved.model, base_url=resolved.base_url or None,
                                          connections=connections)
                endpoint = route.endpoint
                connection = connections.get(provider_name) if connections is not None else None
                provider = (provider_for_connection(connections, provider_name, _model) if connection else
                            make_provider(provider_name,
                                          resolved.base_url or default_endpoint(provider_name) or None))
                _name, _revision, profile = inspect_probe_profile(
                    spec=resolved.model, endpoint=endpoint, provider=provider)
                execution_profile_hash = profile["fingerprint"]
            except Exception:
                execution_profile_hash = None
        try:
            verdict = qualify.assess(role, spec=resolved.model, store=store,
                                     base_url=resolved.base_url or None,
                                     connections=connections,
                                     requires_tools=requires_tools,
                                     execution_profile_hash=execution_profile_hash)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return verdict.as_dict()

    @app.post("/api/v1/workflows/qualifications/probe", response_model=QualificationProbeResource,
              status_code=200)
    def run_qualification_probe(payload: QualificationProbeRequest, request: Request) -> QualificationProbeResource:
        key, digest = _idempotency(request, payload.model_dump())
        bot = _bot_or_404(store, payload.bot)
        try:
            from ..providers import make_provider, parse_spec
            from ..providers.connection import provider_for_connection
            from ..route_identity import default_endpoint
            from ..workflow.probes import run_probe_suite

            provider_name, _model = parse_spec(bot.model)
            connections = qualify.connections_for_store(store)
            route = qualify.route_ref(bot.model, base_url=bot.base_url or None, connections=connections)
            endpoint = route.endpoint
            connection = connections.get(provider_name) if connections is not None else None
            provider = (provider_for_connection(connections, provider_name, _model) if connection else
                        make_provider(provider_name, bot.base_url or default_endpoint(provider_name) or None))
            result = run_probe_suite(
                store, spec=bot.model, role=payload.role, endpoint=endpoint,
                provider=provider, campaign_id=payload.campaign_id,
                idempotency_scope="api:v1:workflows:qualifications:probe", idempotency_key=key,
                request_hash=digest)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(409, {"code": "qualification_probe_unavailable", "message": str(exc)}) from None
        except Exception as exc:
            from ..providers import ProviderError
            if isinstance(exc, ProviderError):
                raise HTTPException(409, {"code": "qualification_probe_unavailable", "message": str(exc)}) from None
            raise
        return QualificationProbeResource(**result.as_dict())

    @app.get("/api/v1/workflows/qualifications/probes/{probe_run_id}")
    def get_qualification_probe(probe_run_id: str) -> dict[str, Any]:
        row = store.workflow_probe_run(probe_run_id)
        if row is None:
            raise HTTPException(404, "no such qualification probe")
        row.pop("idempotency_scope", None)
        row.pop("idempotency_key", None)
        row.pop("request_hash", None)
        row.pop("scope", None)
        return row

    @app.get("/api/v1/workflows/policy")
    def get_workflow_policy(bot: str) -> dict[str, Any]:
        resolved = _bot_or_404(store, bot)
        return {"bot": resolved.name, "mode": getattr(resolved, "workflow_mode", "suggest"),
                "limits": routing.auto_scope(resolved)}

    @app.get("/api/v1/workflows/conversations/{conversation_id}/policy")
    def get_conversation_workflow_policy(conversation_id: str) -> dict[str, Any]:
        try:
            conversation = store.get_conversation(conversation_id)
            if conversation is None:
                raise KeyError(conversation_id)
            saved = store.get_conversation_workflow_policy(conversation_id)
        except KeyError:
            raise HTTPException(404, "no such conversation") from None
        bot = _bot_or_404(store, str(conversation["bot_id"]))
        override = str(saved["mode"]) if saved else "inherit"
        effective = getattr(bot, "workflow_mode", "suggest") if override == "inherit" else override
        scope = routing.auto_scope(bot)
        auto_ready = (getattr(bot, "workflow_mode", "suggest") == "auto"
                      and isinstance(scope.get("definitions"), list) and bool(scope["definitions"])
                      and all(isinstance(scope.get(key), int) and not isinstance(scope.get(key), bool)
                              for key in routing.AUTO_CAPS))
        return {"conversation_id": conversation_id, "bot": bot.name,
                "mode": effective, "override": override,
                "revision": int(saved["revision"]) if saved else 0,
                "updated_at": saved.get("updated_at") if saved else None,
                "bot_mode": getattr(bot, "workflow_mode", "suggest"),
                "limits": scope, "auto_available": auto_ready}

    @app.post("/api/v1/workflows/conversations/{conversation_id}/policy")
    def set_conversation_workflow_policy(conversation_id: str,
                                         payload: ConversationWorkflowPolicyRequest,
                                         request: Request) -> dict[str, Any]:
        key, digest = _idempotency(request, {"conversation_id": conversation_id,
                                             **payload.model_dump()})
        try:
            conversation = store.get_conversation(conversation_id)
            if conversation is None:
                raise KeyError(conversation_id)
        except KeyError:
            raise HTTPException(404, "no such conversation") from None
        bot = _bot_or_404(store, str(conversation["bot_id"]))
        if payload.mode == "auto":
            scope = routing.auto_scope(bot)
            if getattr(bot, "workflow_mode", "suggest") != "auto":
                raise HTTPException(409, {"code": "auto_scope_not_reviewed",
                                          "message": "configure a reviewed Bot-level Auto scope before enabling Auto in this conversation"})
            if (not isinstance(scope.get("definitions"), list) or not scope["definitions"]
                    or any(not isinstance(scope.get(key), int) or isinstance(scope.get(key), bool)
                           for key in routing.AUTO_CAPS)):
                raise HTTPException(409, {"code": "auto_scope_incomplete",
                                          "message": "Auto requires saved workflow names and explicit limits for nodes, model requests, tokens, time, and fan-out"})
        try:
            saved, _created = store.set_conversation_workflow_policy(
                conversation_id, payload.mode, expected_revision=payload.expected_revision,
                idem_key=key, request_hash=digest)
        except Exception as exc:
            from ..store import IdempotencyConflict, RevisionConflict
            if isinstance(exc, IdempotencyConflict):
                raise HTTPException(409, str(exc)) from None
            if isinstance(exc, RevisionConflict):
                raise HTTPException(409, {"code": "workflow_policy_revision_conflict",
                                          "message": str(exc)}) from None
            if isinstance(exc, KeyError):
                raise HTTPException(404, "no such conversation") from None
            raise
        override = str(saved["mode"])
        effective = getattr(bot, "workflow_mode", "suggest") if override == "inherit" else override
        scope = routing.auto_scope(bot)
        auto_ready = (getattr(bot, "workflow_mode", "suggest") == "auto"
                      and isinstance(scope.get("definitions"), list) and bool(scope["definitions"])
                      and all(isinstance(scope.get(key), int) and not isinstance(scope.get(key), bool)
                              for key in routing.AUTO_CAPS))
        return {"conversation_id": conversation_id, "bot": bot.name,
                "mode": effective, "override": override,
                "revision": int(saved["revision"]), "updated_at": saved["updated_at"],
                "bot_mode": getattr(bot, "workflow_mode", "suggest"),
                "limits": scope, "auto_available": auto_ready}

    @app.get("/api/v1/workflows/{ref}", response_model=WorkflowPlanResource)
    def get_workflow(ref: str) -> WorkflowPlanResource:
        entry = wstore.definition(store, ref)
        if entry is None:
            raise HTTPException(404, "no such workflow")
        revision = wstore.latest_revision(store, str(entry["id"]))
        if revision is None:
            raise HTTPException(404, "this workflow has no revision")
        return WorkflowPlanResource(definition_id=str(entry["id"]), revision_id=str(revision["id"]),
                                    revision=int(revision["revision"]),
                                    plan_hash=str(revision["plan_hash"]), plan=revision["plan"])

    @app.post("/api/v1/workflows/{ref}/activate", response_model=WorkflowDefinitionResource)
    def activate_workflow(ref: str, request: Request) -> WorkflowDefinitionResource:
        entry = wstore.definition(store, ref)
        if entry is None:
            raise HTTPException(404, "no such workflow")
        _idempotency(request, {"activate": str(entry["id"])})
        wstore.set_active(store, str(entry["id"]), True)
        row = wstore.definition(store, str(entry["id"]))
        assert row is not None
        return _definition_resource(row)

    @app.post("/api/v1/workflows/validate", response_model=WorkflowValidationResource)
    def validate_workflow(payload: SubmitPlanRequest, request: Request) -> WorkflowValidationResource:
        """Compile, check authority and qualify roles - admitting and executing nothing."""
        _plan_size(payload.plan)
        _idempotency(request, payload.model_dump())
        try:
            compiled = compile_plan(payload.plan)
        except PlanInvalid as exc:
            return WorkflowValidationResource(
                ok=False, diagnostics=[DiagnosticResource(code=d.code, path=d.path, message=d.message,
                                                          severity=d.severity) for d in exc.diagnostics])
        bot = _bot_or_404(store, payload.bot)
        try:
            roles = wfsubmit.check_authority(compiled, bot, store=store)
        except wfsubmit.PlanNotSubmittable as exc:
            blocked = routing.explain_block(bot, [{"role": "worker", "allowed": False,
                                                   "reasons": [str(exc)], "route": None}])
            return WorkflowValidationResource(
                ok=False, plan_hash=compiled.plan_hash, node_count=len(compiled.nodes),
                required_tools=sorted(wfsubmit.required_tools(compiled)),
                diagnostics=[DiagnosticResource(code="authority", path="",
                                                message=" ".join(blocked) or str(exc))],
                warnings=[DiagnosticResource(code=w.code, path=w.path, message=w.message,
                                             severity="warning") for w in compiled.warnings])
        return WorkflowValidationResource(
            ok=True, plan_hash=compiled.plan_hash, node_count=len(compiled.nodes),
            required_tools=sorted(wfsubmit.required_tools(compiled)), roles=roles,
            warnings=[DiagnosticResource(code=w.code, path=w.path, message=w.message,
                                         severity="warning") for w in compiled.warnings])

    @app.post("/api/v1/workflows/plans", response_model=WorkflowSubmissionResource, status_code=201)
    def submit_plan(payload: SubmitPlanRequest, request: Request) -> WorkflowSubmissionResource:
        _plan_size(payload.plan)
        key, digest = _idempotency(request, payload.model_dump())
        bot = _bot_or_404(store, payload.bot)
        if payload.conversation_id:
            conversation = store.get_conversation(payload.conversation_id)
            if conversation is None:
                raise HTTPException(404, "no such conversation")
            if str(conversation["bot_id"]) != bot.id:
                raise HTTPException(422, "the conversation belongs to a different assistant")
        try:
            submission = wfsubmit.submit_workflow(
                store, bot=bot, plan=payload.plan, inputs=payload.inputs,
                definition_name=payload.definition_name, save_definition=payload.save_definition,
                origin="api", conversation_id=payload.conversation_id,
                source=payload.source, planning_model=payload.planning_model,
                note=payload.note, idem_key=key, request_hash=digest, auto=payload.auto)
        except wfsubmit.PlanInputError as exc:
            raise HTTPException(422, {"code": "plan_inputs", "message": str(exc)}) from None
        except wfsubmit.PlanNotSubmittable as exc:
            raise HTTPException(409, {"code": "plan_not_submittable", "message": str(exc)}) from None
        except PlanInvalid as exc:
            raise HTTPException(422, {"code": "plan_invalid",
                                      "diagnostics": [d.render() for d in exc.diagnostics]}) from None
        return WorkflowSubmissionResource(
            workflow_run_id=submission.workflow_run_id, attempt_run_id=submission.attempt_run_id,
            revision_id=submission.revision_id, definition_id=submission.definition_id,
            plan_hash=submission.plan_hash, roles=submission.verdicts)

    @app.post("/api/v1/workflows/{ref}/runs", response_model=WorkflowSubmissionResource, status_code=201)
    def run_saved_workflow(ref: str, payload: RunSavedRequest, request: Request) -> WorkflowSubmissionResource:
        key, digest = _idempotency(request, {"ref": ref, **payload.model_dump()})
        bot = _bot_or_404(store, payload.bot)
        if payload.conversation_id:
            conversation = store.get_conversation(payload.conversation_id)
            if conversation is None:
                raise HTTPException(404, "no such conversation")
            if str(conversation["bot_id"]) != bot.id:
                raise HTTPException(422, "the conversation belongs to a different assistant")
        try:
            submission = wfsubmit.submit_saved(store, bot=bot, definition=ref, inputs=payload.inputs,
                                               origin="api", idem_key=key, request_hash=digest,
                                               auto=payload.auto, conversation_id=payload.conversation_id)
        except KeyError:
            raise HTTPException(404, "no such workflow") from None
        except wfsubmit.PlanInputError as exc:
            raise HTTPException(422, {"code": "plan_inputs", "message": str(exc)}) from None
        except wfsubmit.PlanNotSubmittable as exc:
            raise HTTPException(409, {"code": "plan_not_submittable", "message": str(exc)}) from None
        except PlanInvalid as exc:
            raise HTTPException(422, {"code": "plan_invalid",
                                      "diagnostics": [d.render() for d in exc.diagnostics]}) from None
        return WorkflowSubmissionResource(
            workflow_run_id=submission.workflow_run_id, attempt_run_id=submission.attempt_run_id,
            revision_id=submission.revision_id, definition_id=submission.definition_id,
            plan_hash=submission.plan_hash, roles=submission.verdicts)

    @app.get("/api/v1/workflows/runs/{wf_id}", response_model=WorkflowRunDetail)
    def get_workflow_run(wf_id: str) -> WorkflowRunDetail:
        try:
            view = wfsubmit.status(store, wf_id)
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        revision = wstore.revision(store, str(view["workflow"]["revision_id"]))
        plan = revision["plan"] if revision else None
        workflow = view["workflow"]
        pause_controls = view["pause_controls"]
        return WorkflowRunDetail(
            workflow=_run_resource(workflow), attempt=view["attempt"],
            nodes=[_node_resource(node) for node in view["nodes"]],
            questions=[_question_resource(question) for question in view["questions"]],
            plan=plan, structure=_structure(plan) if plan else [],
            pause_available=pause_controls["pause_available"],
            pause_after_work_available=pause_controls["pause_after_work_available"],
            resume_available=pause_controls["resume_available"])

    @app.post("/api/v1/workflows/runs/{wf_id}/amendments/preview",
              response_model=WorkflowAmendmentPreviewResource)
    def preview_workflow_amendment(
            wf_id: str, payload: WorkflowAmendmentPreviewRequest) -> WorkflowAmendmentPreviewResource:
        """Compile a proposed revision and expose conservative reuse/invalidation decisions."""
        from ..workflow import amendments

        _plan_size(payload.plan)
        try:
            preview = amendments.preview(
                store, workflow_run_id=wf_id, plan=payload.plan,
                expected_revision_id=payload.expected_revision_id,
                expected_generation=payload.expected_generation,
                inputs=payload.inputs,
            )
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        except amendments.AmendmentConflict as exc:
            raise HTTPException(409, {"code": "amendment_revision_conflict", "message": str(exc)}) from None
        except wfsubmit.PlanInputError as exc:
            raise HTTPException(422, {"code": "amendment_inputs", "message": str(exc)}) from None
        except PlanInvalid as exc:
            raise HTTPException(422, {"code": "plan_invalid",
                                      "diagnostics": [d.render() for d in exc.diagnostics]}) from None
        return WorkflowAmendmentPreviewResource(**preview)

    @app.post("/api/v1/workflows/runs/{wf_id}/amendments/drain",
              response_model=WorkflowAmendmentDrainResult)
    def drain_workflow_amendment_steps(
            wf_id: str, payload: WorkflowAmendmentDrainRequest,
            request: Request) -> WorkflowAmendmentDrainResult:
        """Request cancellation only for affected, tool-free child steps on a parked run."""
        from ..workflow import amendments

        _plan_size(payload.plan)
        key, digest = _idempotency(request, payload.model_dump())
        scope = f"api:v1:workflow-amendment-drain:{wf_id}"
        try:
            replay = store.idempotency_replay(scope, key, digest)
        except Exception as exc:
            from ..store import IdempotencyConflict
            if isinstance(exc, IdempotencyConflict):
                raise HTTPException(409, str(exc)) from None
            raise
        if replay is not None:
            return WorkflowAmendmentDrainResult(**replay)
        try:
            result = amendments.drain_affected(
                store, workflow_run_id=wf_id, plan=payload.plan,
                expected_revision_id=payload.expected_revision_id,
                expected_generation=payload.expected_generation,
                inputs=payload.inputs, idem_key=key, request_hash=digest)
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        except amendments.AmendmentConflict as exc:
            raise HTTPException(409, {"code": "amendment_revision_conflict", "message": str(exc)}) from None
        except wfsubmit.PlanInputError as exc:
            raise HTTPException(422, {"code": "amendment_inputs", "message": str(exc)}) from None
        except PlanInvalid as exc:
            raise HTTPException(422, {"code": "plan_invalid",
                                      "diagnostics": [d.render() for d in exc.diagnostics]}) from None
        except wfsubmit.PlanNotSubmittable as exc:
            raise HTTPException(409, {"code": "amendment_not_eligible", "message": str(exc)}) from None
        except ValueError as exc:
            raise HTTPException(409, {"code": "amendment_drain_unavailable", "message": str(exc)}) from None
        try:
            with store._tx() as db:
                replay = store._idempotency_replay(db, scope, key, digest)
                if replay is None:
                    db.execute("INSERT INTO idempotency_keys (scope, key, request_hash, response_json, created_at) "
                               "VALUES (?, ?, ?, ?, ?)",
                               (scope, key, digest, json.dumps(result, sort_keys=True, separators=(",", ":")),
                                iso(utcnow())))
                else:
                    result = replay
        except Exception as exc:
            from ..store import IdempotencyConflict
            if isinstance(exc, IdempotencyConflict):
                raise HTTPException(409, str(exc)) from None
            raise
        return WorkflowAmendmentDrainResult(**result)

    @app.post("/api/v1/workflows/runs/{wf_id}/amendments/adopt",
              response_model=WorkflowAmendmentAdoptResource)
    def adopt_workflow_amendment(
            wf_id: str, payload: WorkflowAmendmentAdoptRequest,
            request: Request) -> WorkflowAmendmentAdoptResource:
        """Adopt only while parked; active children and processes are never killed here."""
        from ..workflow import amendments

        _plan_size(payload.plan)
        key, digest = _idempotency(request, payload.model_dump())
        scope = f"api:v1:workflow-amendments:{wf_id}"
        replay = store.idempotency_replay(scope, key, digest)
        if replay is not None:
            return WorkflowAmendmentAdoptResource(**replay)
        try:
            result = amendments.adopt(
                store, workflow_run_id=wf_id, plan=payload.plan,
                expected_revision_id=payload.expected_revision_id,
                expected_generation=payload.expected_generation,
                inputs=payload.inputs,
                cancel_pending_questions=payload.cancel_pending_questions,
                idem_key=key, request_hash=digest)
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        except amendments.AmendmentConflict as exc:
            raise HTTPException(409, {"code": "amendment_revision_conflict", "message": str(exc)}) from None
        except wfsubmit.PlanInputError as exc:
            raise HTTPException(422, {"code": "amendment_inputs", "message": str(exc)}) from None
        except PlanInvalid as exc:
            raise HTTPException(422, {"code": "plan_invalid",
                                      "diagnostics": [d.render() for d in exc.diagnostics]}) from None
        except wfsubmit.PlanNotSubmittable as exc:
            raise HTTPException(409, {"code": "amendment_not_eligible", "message": str(exc)}) from None
        except wstore.AmendmentSnapshotLimit as exc:
            raise HTTPException(413, {"code": "amendment_history_too_large", "message": str(exc)}) from None
        except ValueError as exc:
            raise HTTPException(409, {"code": "amendment_not_quiescent", "message": str(exc)}) from None
        engine.store.bus.notify("work")
        return WorkflowAmendmentAdoptResource(**result)

    @app.get("/api/v1/workflows/runs/{wf_id}/amendments",
             response_model=WorkflowAmendmentHistoryPage)
    def list_workflow_amendments(wf_id: str, limit: int = 50, offset: int = 0) -> WorkflowAmendmentHistoryPage:
        if wstore.workflow_run(store, wf_id) is None:
            raise HTTPException(404, "no such workflow run")
        try:
            items = wstore.amendment_history_summaries(store, wf_id, limit=limit, offset=offset)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return WorkflowAmendmentHistoryPage(items=[WorkflowAmendmentHistorySummary(**item) for item in items],
                                            limit=limit, offset=offset)

    @app.get("/api/v1/workflows/runs/{wf_id}/amendments/{amendment_id}",
             response_model=WorkflowAmendmentHistoryDetail)
    def get_workflow_amendment(wf_id: str, amendment_id: str) -> WorkflowAmendmentHistoryDetail:
        item = wstore.amendment_history_detail(store, wf_id, amendment_id)
        if item is None:
            raise HTTPException(404, "no such workflow amendment")
        return WorkflowAmendmentHistoryDetail(
            id=str(item["id"]), previous_revision_id=str(item["previous_revision_id"]),
            adopted_revision_id=str(item["adopted_revision_id"]),
            previous_attempt_run_id=str(item["previous_attempt_run_id"]),
            previous_status=str(item["previous_status"]),
            previous_plan_hash=str(item["previous_plan_hash"]),
            adopted_plan_hash=str(item["adopted_plan_hash"]), created_at=str(item["created_at"]),
            preview=WorkflowAmendmentPreviewResource(**item["preview"]),
            nodes=[_node_resource(row) for row in item["nodes"]],
            questions=[_question_resource(row) for row in item["questions"]],
            result=item["result"])

    @app.post("/api/v1/workflows/runs/{wf_id}/stop", response_model=WorkflowRunResource)
    def stop_workflow_run(wf_id: str, payload: WorkflowStopRequest, request: Request) -> WorkflowRunResource:
        _idempotency(request, {"stop": wf_id, **payload.model_dump()})
        try:
            wfsubmit.stop_workflow(store, wf_id, expected_revision_id=payload.expected_revision_id)
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        engine.store.bus.notify("work")
        row = wstore.workflow_run(store, wf_id)
        assert row is not None
        return _run_resource(row)

    def _set_workflow_pause(wf_id: str, payload: WorkflowPauseRequest, request: Request,
                            paused: bool) -> WorkflowPauseMutationResource:
        key, digest = _idempotency(request, {"workflow_run_id": wf_id, "paused": paused,
                                              **payload.model_dump()})
        try:
            response = wstore.set_workflow_pause(
                store, wf_id, paused=paused, expected_revision_id=payload.expected_revision_id,
                expected_generation=payload.expected_generation, idem_key=key, request_hash=digest)
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        except Exception as exc:
            from ..store import IdempotencyConflict
            if isinstance(exc, IdempotencyConflict):
                raise HTTPException(409, str(exc)) from None
            raise
        return WorkflowPauseMutationResource(**response)

    @app.post("/api/v1/workflows/runs/{wf_id}/pause", response_model=WorkflowPauseMutationResource)
    def pause_workflow_run(wf_id: str, payload: WorkflowPauseRequest, request: Request) -> WorkflowPauseMutationResource:
        return _set_workflow_pause(wf_id, payload, request, True)

    @app.post("/api/v1/workflows/runs/{wf_id}/resume", response_model=WorkflowPauseMutationResource)
    def resume_workflow_run(wf_id: str, payload: WorkflowPauseRequest, request: Request) -> WorkflowPauseMutationResource:
        return _set_workflow_pause(wf_id, payload, request, False)

    @app.post("/api/v1/workflows/questions/{question_id}/answer", response_model=WorkflowQuestionResource)
    def answer_workflow_question(question_id: str, payload: AnswerRequest, request: Request) -> WorkflowQuestionResource:
        _idempotency(request, {"question": question_id, "answer": payload.answer})
        outcome = wfsubmit.answer(store, question_id, payload.answer)
        if outcome == "missing":
            raise HTTPException(404, "no such question")
        if outcome == "expired":
            raise HTTPException(409, {"code": "question_expired", "message": "this question expired unanswered"})
        if outcome == "already":
            row = wstore.question(store, question_id)
            if row is None or row["status"] != "answered":
                raise HTTPException(409, {"code": "question_not_answerable",
                                          "message": f"this question is {row['status'] if row else 'missing'}"})
            return _question_resource(row)
        engine.store.bus.notify("work")
        row = wstore.question(store, question_id)
        assert row is not None
        return _question_resource(row)

    @app.post("/api/v1/workflows/policy")
    def set_workflow_policy(payload: WorkflowPolicyRequest, request: Request) -> dict[str, Any]:
        """Set how Hutch may use workflows for one Bot. Nothing is started or scheduled."""
        _idempotency(request, payload.model_dump())
        bot = _bot_or_404(store, payload.bot)
        limits: dict[str, Any] = {}
        if payload.mode == "auto":
            if not payload.definitions:
                raise HTTPException(422, "Auto requires at least one reviewed saved workflow")
            for name in payload.definitions:
                definition = wstore.definition(store, name)
                if definition is None or not definition.get("active"):
                    raise HTTPException(422, f"Auto workflow {name!r} must exist and be activated before it is scoped")
            limits["definitions"] = list(payload.definitions)
            for key in ("max_nodes", "max_model_calls", "max_tokens", "max_wall_seconds", "max_fanout"):
                value = getattr(payload, key)
                if value is None:
                    raise HTTPException(422, f"Auto requires an explicit {key} limit")
                limits[key] = int(value)
        bot.workflow_mode = payload.mode
        bot.workflow_limits = limits
        store.upsert_bot(bot, preserve_schedules=True)
        return {"bot": bot.name, "mode": bot.workflow_mode, "limits": bot.workflow_limits,
                "note": "saved; saving a policy starts nothing and grants no schedule"}

    @app.post("/api/v1/workflows/qualifications", status_code=201)
    def acknowledge_qualification(payload: QualificationRequest, request: Request) -> dict[str, Any]:
        _idempotency(request, payload.model_dump())
        bot = _bot_or_404(store, payload.bot)
        try:
            verdict = qualify.acknowledge_limited(store, spec=bot.model, role=payload.role,
                                                  reason=payload.reason, scope=payload.scope,
                                                  base_url=bot.base_url or None,
                                                  connections=qualify.connections_for_store(store))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return verdict.as_dict()

    @app.delete("/api/v1/workflows/qualifications")
    def revoke_qualification(bot: str, role: str, request: Request) -> dict[str, Any]:
        _idempotency(request, {"revoke": bot, "role": role})
        resolved = _bot_or_404(store, bot)
        try:
            removed = qualify.revoke(store, spec=resolved.model, role=role,
                                     base_url=resolved.base_url or None,
                                     connections=qualify.connections_for_store(store))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"removed": removed}
