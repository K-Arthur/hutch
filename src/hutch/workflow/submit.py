"""Plan submission: validate, gate, admit.

This is where a plan becomes work, and it is deliberately strict. Submission:

1. validates the caller's inputs against the plan's declared inputs (types, bounds,
   unknown keys - no coercion, no invented defaults);
2. compiles the plan (identity, references, envelopes, cardinality - fail closed);
3. checks the plan's **declared envelope against the Bot's actual authority**: the tools
   and skills it names must be within what this Bot may use, the models must resolve, and
   ``network: local_model_only`` must be genuinely satisfiable - a workflow can never
   widen a Bot;
4. qualifies every model role the plan needs *before* anything is queued, so a blocked
   model is a submission-time refusal with the reason and the options, not a surprise
   half-way through a run;
5. admits the instance and its first orchestration attempt atomically.

Model-authored plans additionally require the authoring role to be qualified for the
planning model; an operator-submitted plan is authored by the person and needs no such
gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..models import Bot, Run, Task
from ..providers.pricing import is_local_route
from ..tools import expand_tools
from . import persistence as wstore
from . import qualify
from .compile import CompiledPlan, PlanInvalid, compile_plan
from .plan import CEILINGS, Plan


class PlanInputError(ValueError):
    """The supplied inputs do not match the plan's declared inputs."""


class PlanNotSubmittable(ValueError):
    """The plan is valid but this Bot may not run it as declared."""


#: Per-step bounds. They are named here once and carried in the workflow's budget so the
#: interpreter and the step contract cannot disagree.
STEP_MAX_STEPS = 12
STEP_MAX_SECONDS = 600


@dataclass
class Submission:
    workflow_run_id: str
    attempt_run_id: str
    revision_id: str
    definition_id: Optional[str]
    plan_hash: str
    verdicts: list[dict[str, Any]] = None  # type: ignore[assignment]


def validate_inputs(plan: Plan, inputs: Optional[dict[str, Any]]) -> dict[str, Any]:
    supplied = dict(inputs or {})
    unknown = sorted(set(supplied) - set(plan.inputs))
    if unknown:
        raise PlanInputError(f"unknown inputs: {unknown}")
    resolved: dict[str, Any] = {}
    for name, spec in plan.inputs.items():
        if name in supplied:
            value = supplied[name]
        elif spec.default is not None:
            value = spec.default
        elif spec.required:
            raise PlanInputError(f"missing required input {name!r}")
        else:
            continue
        resolved[name] = _check_input(name, spec, value)
    return resolved


def _check_input(name: str, spec: Any, value: Any) -> Any:
    kind = spec.type
    ok = {
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }[kind]
    if not ok:
        raise PlanInputError(f"input {name!r} must be {kind}, got {type(value).__name__}")
    if kind == "string":
        if spec.max_length and len(value) > spec.max_length:
            raise PlanInputError(f"input {name!r} is longer than {spec.max_length} characters")
        if len(value) > CEILINGS["max_input_chars"]:
            raise PlanInputError(
                f"input {name!r} is longer than {CEILINGS['max_input_chars']} characters")
    if kind == "array" and len(value) > CEILINGS["max_fanout"] * 10:
        raise PlanInputError(f"input {name!r} has more than {CEILINGS['max_fanout'] * 10} items")
    if kind == "array" and spec.max_items is not None and len(value) > spec.max_items:
        raise PlanInputError(f"input {name!r} has more than {spec.max_items} items")
    return value


def required_tools(compiled: CompiledPlan) -> set[str]:
    """Every governed tool the plan can reach, including command checks and repair steps."""
    needed: set[str] = set()
    for entry in compiled.nodes:
        node = entry.node
        if node.kind == "tool":
            needed.add(node.tool)
        elif node.kind == "agent":
            needed.update(node.tools)
        elif node.kind == "verify":
            for check in node.checks:
                if check.kind == "command":
                    needed.add("shell")
    return needed


def check_authority(compiled: CompiledPlan, bot: Bot, *, store: Any = None) -> list[dict[str, Any]]:
    """Refuse a plan that asks for more than this Bot has. Returns role verdicts."""
    envelope = compiled.plan.envelope
    allowed_tools = set(expand_tools(bot.tools))
    declared = set(envelope.tools) | required_tools(compiled)
    outside = sorted(declared - allowed_tools)
    if outside:
        raise PlanNotSubmittable(
            f"this plan declares tools the Bot does not allow: {outside}. "
            f"Add them to the Bot deliberately, or narrow the plan's envelope.")
    outside_skills = sorted(set(envelope.skills) - set(bot.skills))
    if outside_skills:
        raise PlanNotSubmittable(
            f"this plan declares skills the Bot is not bound to: {outside_skills}. "
            f"Bind them to the Bot deliberately, or narrow the plan's envelope.")
    specs = [spec for spec in envelope.models if spec not in ("$bot", "$default")]
    if envelope.network == "local_model_only":
        candidates = specs + [bot.model]
        hosted = [spec for spec in candidates if not _is_local(spec, bot)]
        if hosted:
            raise PlanNotSubmittable(
                f"this plan requires local-model-only execution, but these routes are not local: "
                f"{hosted}. Choose a local route for the Bot, or change the plan's network policy.")
    verdicts: list[dict[str, Any]] = []
    connections = qualify.connections_for_store(store)
    for entry in compiled.nodes:
        node = entry.node
        if node.kind != "agent":
            continue
        spec = bot.model if node.model in ("", "$bot", "$default") else node.model
        verdict = qualify.assess("worker" if node.role != "verifier" else "verifier",
                                 spec=spec, store=store, connections=connections,
                                 base_url=bot.base_url or None,
                                 requires_tools=bool(node.tools),
                                 requires_structured_output=node.output_schema is not None)
        verdicts.append({"node": entry.site_id, **verdict.as_dict()})
        if not verdict.allowed:
            raise PlanNotSubmittable(
                f"node {entry.site_id} cannot run in its declared role: {verdict.summary()}")
    return verdicts


def _is_local(spec: str, bot: Bot) -> bool:
    provider, _, model = spec.partition("/")
    if not model:
        provider, model = bot.model.partition("/")
    return bool(is_local_route(provider, model))


def _gate_auto(store: Any, bot: Bot, *, compiled: CompiledPlan, definition: Any,
               plan_name: str) -> None:
    from . import routing

    allowed, why = routing.check_auto(bot=bot, definition=definition,
                                      budget=compiled.plan.budget.model_dump(mode="json"),
                                      plan_name=plan_name)
    if not allowed:
        raise PlanNotSubmittable(f"an automatic start was refused: {why}")


def _admit(store: Any, *, bot: Bot, compiled: CompiledPlan, revision_id: str,
           definition_id: Optional[str], inputs: dict[str, Any], origin: str,
           conversation_id: str, idem_key: str, request_hash: str,
           plan_payload: dict[str, Any], schedule_id: str = "",
           schedule_claim: Optional[dict[str, Any]] = None) -> Submission:
    """The one admission path: instance + first orchestration attempt, idempotently."""
    attempt = Run(bot_id=bot.id, prompt=f"workflow: {compiled.plan.name}"[:4_000], kind="workflow",
                  origin=origin, schedule_id=schedule_id, conversation_id=conversation_id)
    task = Task(bot_id=bot.id, kind="workflow", prompt=attempt.prompt)
    workflow, created = wstore.submit_workflow_run(
        store, plan=plan_payload, definition_id=definition_id, revision_id=revision_id,
        plan_hash=compiled.plan_hash, bot_id=bot.id, inputs=inputs,
        budget=step_budget(compiled), origin=origin, conversation_id=conversation_id,
        run=attempt, task=task, idem_key=idem_key, request_hash=request_hash,
        schedule_claim=schedule_claim)
    if not created:
        return _from_record(workflow)
    return Submission(workflow_run_id=str(workflow["id"]), attempt_run_id=attempt.id,
                      revision_id=revision_id, definition_id=definition_id,
                      plan_hash=compiled.plan_hash, verdicts=[])


def step_budget(compiled: CompiledPlan) -> dict[str, Any]:
    """The plan's budget plus the two per-step bounds the interpreter enforces.

    Kept in one place so the interpreter, the step contract and every submission agree on
    what a model step may spend.
    """
    return {**compiled.plan.budget.model_dump(mode="json"),
            "max_steps_per_node": STEP_MAX_STEPS, "max_step_seconds": STEP_MAX_SECONDS}


def submit_workflow(store: Any, *, bot: Bot, plan: dict[str, Any] | Plan,
                    inputs: Optional[dict[str, Any]] = None, definition_name: str = "",
                    save_definition: bool = True, activate_definition: bool = False,
                    origin: str = "operator", conversation_id: str = "",
                    source: str = "operator", planning_model: str = "",
                    planning_profile_hash: str = "",
                    created_by: str = "", note: str = "",
                    idem_key: str = "", request_hash: str = "",
                    auto: bool = False, revision_id: str = "", schedule_id: str = "",
                    schedule_claim: Optional[dict[str, Any]] = None) -> Submission:
    """Validate, gate and admit one workflow instance.

    ``revision_id`` names an already-saved revision to run as-is; otherwise the plan is
    saved as a new revision (``save_definition=False`` with no ``revision_id`` is refused
    rather than silently saving one).
    """
    compiled = compile_plan(plan)
    resolved_inputs = validate_inputs(compiled.plan, inputs)
    if idem_key:
        replay = store.idempotency_replay("api:v1:workflow-runs", idem_key, request_hash)
        if replay is not None:
            return _replayed(store, replay)
    verdicts = check_authority(compiled, bot, store=store)
    if source == "model":
        if not planning_model:
            raise PlanNotSubmittable("a model-authored plan must name the planning model")
        gate = qualify.assess("author", spec=planning_model, store=store,
                              base_url=bot.base_url or None,
                              execution_profile_hash=planning_profile_hash or None)
        if not gate.allowed:
            raise PlanNotSubmittable(
                f"the planning model is not qualified to author workflows: {gate.summary()}")

    definition_id: Optional[str] = None
    plan_payload = compiled.plan.model_dump(by_alias=True, exclude_none=True, mode="json")
    if save_definition:
        name = definition_name or compiled.plan.name
        saved = wstore.save_definition(store, name=name, plan=plan_payload,
                                       description=compiled.plan.description, note=note,
                                       created_by=created_by, source=source,
                                       activate=activate_definition)
        definition_id, revision_id = saved["definition_id"], saved["revision_id"]
    elif revision_id:
        existing = wstore.revision(store, revision_id)
        if existing is None:
            raise PlanNotSubmittable(f"no such revision: {revision_id}")
        if str(existing["plan_hash"]) != compiled.plan_hash:
            raise PlanNotSubmittable(
                "the submitted plan does not match that revision's hash; save it as a new revision")
        definition_id = str(existing["definition_id"])
        plan_payload = existing["plan"]
    else:
        raise PlanNotSubmittable("submission needs either a saved definition or an existing revision")
    if auto:
        definition_row = wstore.definition(store, definition_id) if definition_id else None
        _gate_auto(store, bot, compiled=compiled, definition=definition_row,
                   plan_name=compiled.plan.name)
    submission = _admit(store, bot=bot, compiled=compiled, revision_id=revision_id,
                        definition_id=definition_id, inputs=resolved_inputs, origin=origin,
                        conversation_id=conversation_id, idem_key=idem_key,
                        request_hash=request_hash, plan_payload=plan_payload,
                        schedule_id=schedule_id, schedule_claim=schedule_claim)
    submission.verdicts = verdicts
    return submission


def submit_saved(store: Any, *, bot: Bot, definition: str, inputs: Optional[dict[str, Any]] = None,
                 origin: str = "operator", conversation_id: str = "",
                 idem_key: str = "", request_hash: str = "", auto: bool = False) -> Submission:
    """Run a saved definition's latest revision without a planning call of any kind."""
    entry = wstore.definition(store, definition)
    if entry is None:
        raise KeyError(definition)
    revision = wstore.latest_revision(store, str(entry["id"]))
    if revision is None:
        raise KeyError(definition)
    compiled = compile_plan(revision["plan"])
    resolved_inputs = validate_inputs(compiled.plan, inputs)
    if idem_key:
        replay = store.idempotency_replay("api:v1:workflow-runs", idem_key, request_hash)
        if replay is not None:
            return _replayed(store, replay)
    if auto:
        _gate_auto(store, bot, compiled=compiled, definition=entry,
                   plan_name=str(entry["name"]))
    verdicts = check_authority(compiled, bot, store=store)
    submission = _admit(store, bot=bot, compiled=compiled, revision_id=str(revision["id"]),
                        definition_id=str(entry["id"]), inputs=resolved_inputs, origin=origin,
                        conversation_id=conversation_id, idem_key=idem_key,
                        request_hash=request_hash, plan_payload=revision["plan"])
    submission.verdicts = verdicts
    return submission


def _from_record(workflow: dict[str, Any]) -> Submission:
    return Submission(workflow_run_id=str(workflow["id"]),
                      attempt_run_id=str(workflow.get("attempt_run_id") or ""),
                      revision_id=str(workflow["revision_id"]),
                      definition_id=workflow.get("definition_id"),
                      plan_hash=str(workflow["plan_hash"]), verdicts=[])


def _replayed(store: Any, replay: dict[str, Any]) -> Submission:
    row = wstore.workflow_run(store, str(replay["workflow_run_id"]))
    if row is None:
        raise RuntimeError("an idempotent workflow response points to missing state")
    return _from_record(row)


def stop_workflow(store: Any, wf_id: str, *, expected_revision_id: str = "") -> dict[str, Any]:
    return wstore.request_workflow_stop(store, wf_id, expected_revision_id=expected_revision_id)


def answer(store: Any, question_id: str, text: str) -> str:
    return wstore.answer_question(store, question_id, text)


def status(store: Any, wf_id: str) -> dict[str, Any]:
    """The authoritative view: instance, nodes, questions and attempt - one read model."""
    workflow = wstore.workflow_run(store, wf_id)
    if workflow is None:
        raise KeyError(wf_id)
    attempt = store.get_run(str(workflow["attempt_run_id"])) if workflow["attempt_run_id"] else None
    return {
        "workflow": workflow,
        "attempt": {"run_id": attempt.id, "status": attempt.status.value, "error": attempt.error,
                    "reason": attempt.reason, "exit_reason": attempt.exit_reason} if attempt else None,
        "nodes": wstore.nodes(store, wf_id),
        "questions": wstore.questions(store, wf_id),
    }


__all__ = ["Submission", "PlanInputError", "PlanNotSubmittable", "validate_inputs",
           "required_tools", "check_authority", "submit_workflow", "submit_saved",
           "stop_workflow", "answer", "status"]
