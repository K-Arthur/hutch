"""Typed workflow API: definitions, revisions, runs, nodes, questions, qualifications.

Registered from ``create_app`` like the page sub-registrars, so the JSON surface keeps one
app factory while this module keeps the workflow resource in one place. Every route is
``/api/v1`` and owner-only by default (the startup route inventory leaves unmapped routes
local), every command needs an ``Idempotency-Key``, and nothing here executes a plan: the
validate route compiles and checks authority without admitting, dispatching or reading
anything live.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from ..models import Bot
from ..workflow import persistence as wstore
from ..workflow import qualify
from ..workflow import submit as wfsubmit
from ..workflow.compile import CEILINGS, PlanInvalid, compile_plan

MAX_PLAN_BYTES = CEILINGS["max_plan_bytes"]


# ------------------------------------------------------------------- resources

class WorkflowDefinitionResource(BaseModel):
    id: str
    name: str
    description: str = ""
    active: bool = False
    source: str = "operator"
    revisions: int = 0
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
    status: str
    reason: str = ""
    origin: str = "operator"
    attempt_run_id: str = ""
    stop_requested: bool = False
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
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class WorkflowQuestionResource(BaseModel):
    id: str
    site_id: str
    instance_key: str
    question: str
    options: list[str] = Field(default_factory=list)
    status: str
    answer: str = ""
    asked_at: str
    expires_at: str
    answered_at: Optional[str] = None


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
    definition_name: str = Field(default="", max_length=120)
    save_definition: bool = True
    source: Literal["operator", "model"] = "operator"
    planning_model: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=500)


class RunSavedRequest(BaseModel):
    bot: str = Field(min_length=1, max_length=120)
    inputs: dict[str, Any] = Field(default_factory=dict)


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class QualificationRequest(BaseModel):
    bot: str = Field(min_length=1, max_length=120)
    role: Literal["worker", "verifier"]
    reason: str = Field(min_length=1, max_length=500)
    scope: dict[str, Any] = Field(default_factory=dict)


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _idempotency(request: Request, payload: Any) -> tuple[str, str]:
    key = request.headers.get("idempotency-key", "").strip()
    if not key:
        raise HTTPException(428, "an Idempotency-Key header is required for this command")
    if len(key) > 128 or any(not (32 <= ord(char) < 127) for char in key):
        raise HTTPException(422, "Idempotency-Key must be 1-128 printable ASCII characters")
    return key, _digest(payload)


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
        updated_at=str(row.get("updated_at") or ""))


def _node_resource(row: dict[str, Any]) -> WorkflowNodeResource:
    return WorkflowNodeResource(
        site_id=str(row["site_id"]), instance_key=str(row["instance_key"]), kind=str(row["kind"]),
        status=str(row["status"]), attempt=int(row.get("attempt") or 1),
        run_id=(str(row["run_id"]) if row.get("run_id") else None),
        input_hash=str(row.get("input_hash") or ""), result=row.get("result") or {},
        error=row.get("error") or {}, started_at=row.get("started_at"),
        finished_at=row.get("finished_at"))


def _question_resource(row: dict[str, Any]) -> WorkflowQuestionResource:
    return WorkflowQuestionResource(
        id=str(row["id"]), site_id=str(row["site_id"]), instance_key=str(row["instance_key"]),
        question=str(row["question"]), options=list(row.get("options") or []),
        status=str(row["status"]), answer=str(row.get("answer") or ""),
        asked_at=str(row["asked_at"]), expires_at=str(row["expires_at"]),
        answered_at=row.get("answered_at"))


def _run_resource(row: dict[str, Any]) -> WorkflowRunResource:
    return WorkflowRunResource(
        id=str(row["id"]), definition_id=row.get("definition_id"), revision_id=str(row["revision_id"]),
        plan_hash=str(row["plan_hash"]), bot_id=str(row["bot_id"]), status=str(row["status"]),
        reason=str(row.get("reason") or ""), origin=str(row.get("origin") or "operator"),
        attempt_run_id=str(row.get("attempt_run_id") or ""),
        stop_requested=bool(row.get("stop_requested")), inputs=row.get("inputs") or {},
        budget=row.get("budget") or {}, ledger=row.get("ledger") or {}, result=row.get("result") or {},
        created_at=str(row.get("created_at") or ""), updated_at=str(row.get("updated_at") or ""),
        finished_at=row.get("finished_at"))


def _structure(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The planned shape, flattened for a compact accessible list (never a fake graph)."""
    out: list[dict[str, Any]] = []

    def walk(nodes: list[dict[str, Any]], parent: str, depth: int) -> None:
        for node in nodes:
            site = f"{parent}.{node.get('id')}" if parent else str(node.get("id"))
            out.append({"site_id": site, "kind": node.get("kind"), "title": node.get("title") or "",
                        "parent": parent or None, "depth": depth,
                        "bounded": node.get("kind") in ("map", "expand", "branch", "repeat")})
            for body in ("body", "then", "else"):
                children = node.get(body)
                if isinstance(children, list) and children:
                    walk(children, site, depth + 1)

    nodes = plan.get("nodes")
    if isinstance(nodes, list):
        walk(nodes, "", 0)
    return out


def register_workflow_api(app: Any, store: Any, engine: Any) -> None:
    """Attach the workflow routes to the existing app factory."""

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

    @app.get("/api/v1/workflows/qualifications")
    def list_qualifications(limit: int = 100, offset: int = 0) -> dict[str, Any]:
        try:
            return {"items": store.list_role_qualifications(limit=limit, offset=offset)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/v1/workflows/qualifications/assess")
    def assess_role(bot: str, role: str, requires_tools: bool = False) -> dict[str, Any]:
        resolved = _bot_or_404(store, bot)
        try:
            verdict = qualify.assess(role, spec=resolved.model, store=store, requires_tools=requires_tools)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return verdict.as_dict()

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
            return WorkflowValidationResource(
                ok=False, plan_hash=compiled.plan_hash, node_count=len(compiled.nodes),
                required_tools=sorted(wfsubmit.required_tools(compiled)),
                diagnostics=[DiagnosticResource(code="authority", path="", message=str(exc))],
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
        try:
            submission = wfsubmit.submit_workflow(
                store, bot=bot, plan=payload.plan, inputs=payload.inputs,
                definition_name=payload.definition_name, save_definition=payload.save_definition,
                origin="api", source=payload.source, planning_model=payload.planning_model,
                note=payload.note, idem_key=key, request_hash=digest)
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
        try:
            submission = wfsubmit.submit_saved(store, bot=bot, definition=ref, inputs=payload.inputs,
                                               origin="api", idem_key=key, request_hash=digest)
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

    @app.get("/api/v1/workflows/runs/{wf_id}", response_model=WorkflowRunDetail)
    def get_workflow_run(wf_id: str) -> WorkflowRunDetail:
        try:
            view = wfsubmit.status(store, wf_id)
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        revision = wstore.revision(store, str(view["workflow"]["revision_id"]))
        plan = revision["plan"] if revision else None
        return WorkflowRunDetail(
            workflow=_run_resource(view["workflow"]), attempt=view["attempt"],
            nodes=[_node_resource(node) for node in view["nodes"]],
            questions=[_question_resource(question) for question in view["questions"]],
            plan=plan, structure=_structure(plan) if plan else [])

    @app.post("/api/v1/workflows/runs/{wf_id}/stop", response_model=WorkflowRunResource)
    def stop_workflow_run(wf_id: str, request: Request) -> WorkflowRunResource:
        _idempotency(request, {"stop": wf_id})
        try:
            wfsubmit.stop_workflow(store, wf_id)
        except KeyError:
            raise HTTPException(404, "no such workflow run") from None
        engine.store.bus.notify("work")
        row = wstore.workflow_run(store, wf_id)
        assert row is not None
        return _run_resource(row)

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

    @app.post("/api/v1/workflows/qualifications", status_code=201)
    def acknowledge_qualification(payload: QualificationRequest, request: Request) -> dict[str, Any]:
        _idempotency(request, payload.model_dump())
        bot = _bot_or_404(store, payload.bot)
        try:
            verdict = qualify.acknowledge_limited(store, spec=bot.model, role=payload.role,
                                                  reason=payload.reason, scope=payload.scope)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return verdict.as_dict()

    @app.delete("/api/v1/workflows/qualifications")
    def revoke_qualification(bot: str, role: str, request: Request) -> dict[str, Any]:
        _idempotency(request, {"revoke": bot, "role": role})
        resolved = _bot_or_404(store, bot)
        try:
            removed = qualify.revoke(store, spec=resolved.model, role=role)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"removed": removed}
