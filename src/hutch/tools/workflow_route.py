"""Review-aware workflow recommendation inside an already-running chat turn.

This is a selector capability, not a planner or executor. The built-in runtime exposes it
only when the active model has passed the exact-profile selector probe. Suggest returns a
durable, inspectable recommendation and never starts work. Auto can start only an activated
saved definition inside the current conversation's and Bot's reviewed scope.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .base import Tool, ToolContext, ToolResult

SIGNALS = frozenset({
    "conversational", "single_step", "repeatable_procedure", "needs_verification",
    "depends_on_results", "independent_items", "known_inputs",
})


class WorkflowRouteTool(Tool):
    name = "recommend_workflow"
    description = (
        "Use only when the current request may benefit from a workflow. Classify its structure using the supplied "
        "boolean signals and, when appropriate, select a matching saved workflow by exact name or ID. This is a "
        "selector action: in Suggest it only returns a review card; in Auto it may start only an activated saved "
        "workflow that passes the current reviewed scope. It cannot create a plan, change permissions, or approve actions. "
        "For ordinary conversation or one bounded step, do not call this tool."
    )
    parameters = {
        "type": "object",
        "required": ["signals"],
        "properties": {
            "signals": {
                "type": "object",
                "properties": {name: {"type": "boolean"} for name in sorted(SIGNALS)},
                "additionalProperties": False,
            },
            "workflow": {"type": "string", "maxLength": 160,
                         "description": "An exact saved workflow name or ID, if one directly matches."},
            "inputs": {"type": "object", "description": "Inputs required by that saved workflow, drawn from the current request."},
        },
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        from ..connections import ConnectionBook
        from ..workflow import persistence as wstore
        from ..workflow import qualify, routing
        from ..workflow import submit as wfsubmit

        if not ctx.run.conversation_id or ctx.run.parent_run_id or ctx.run.workflow_step:
            return ToolResult(ok=False, output="workflow selection is available only in a local owner chat turn")
        if ctx.run.origin.startswith("remote:"):
            return ToolResult(ok=False, output="workflow selection and launch are local-owner actions")
        if ctx.run.rehearsal:
            return ToolResult(ok=False, output="workflow selection is unavailable in rehearsal; nothing was started")

        live_bot = ctx.store.get_bot(ctx.bot.id)
        conversation = ctx.store.get_conversation(ctx.run.conversation_id)
        if live_bot is None or conversation is None or conversation.get("bot_id") != ctx.bot.id:
            return ToolResult(ok=False, output="the current assistant or conversation is unavailable")
        saved_policy = ctx.store.get_conversation_workflow_policy(ctx.run.conversation_id)
        override = str(saved_policy["mode"]) if saved_policy else "inherit"
        mode = getattr(live_bot, "workflow_mode", "suggest") if override == "inherit" else override
        if mode not in ("suggest", "auto"):
            return ToolResult(ok=False, output="workflow mode is Off for this conversation; no workflow was selected")

        profile = ctx.model_execution_profile or {}
        active_spec = str(ctx.run.model_used or "")
        execution_hash = profile.get("fingerprint")
        verdict = qualify.assess(
            "selector", spec=active_spec, store=ctx.store,
            connections=ConnectionBook(ctx.config.state_dir), base_url=live_bot.base_url or None,
            execution_profile_hash=execution_hash if isinstance(execution_hash, str) else None,
        )
        if not verdict.allowed:
            return ToolResult(ok=False, output="workflow selector qualification no longer applies: " + verdict.summary(),
                              data={"qualification": verdict.as_dict()})

        raw_signals = args.get("signals")
        if not isinstance(raw_signals, dict) or set(raw_signals) - SIGNALS:
            return ToolResult(ok=False, output="signals must contain only the declared workflow-shape booleans")
        if any(not isinstance(value, bool) for value in raw_signals.values()):
            return ToolResult(ok=False, output="every workflow-shape signal must be true or false")
        signals = {name: bool(raw_signals.get(name, False)) for name in SIGNALS}
        requested = args.get("workflow", "")
        if not isinstance(requested, str) or len(requested) > 160:
            return ToolResult(ok=False, output="workflow must be an exact saved name or ID")

        definitions = wstore.list_definitions(ctx.store, limit=200)
        candidate = next((item for item in definitions
                          if requested and requested in (str(item.get("id", "")), str(item.get("name", "")))), None)
        if requested and candidate is None:
            return ToolResult(ok=False, output="that workflow is not in this workspace's saved definitions")
        recommendation = routing.recommend(
            signals=signals,
            saved_workflow=str(candidate["name"]) if candidate is not None else "",
        )
        projection: dict[str, Any] = {
            **recommendation.as_dict(), "policy": mode, "status": "suggested",
            "definition_id": str(candidate["id"]) if candidate is not None else "",
        }
        if recommendation.route == "direct":
            return ToolResult(ok=True, output="No workflow is recommended; continue directly.",
                              data={"workflow_recommendation": projection})

        if mode == "suggest":
            return ToolResult(ok=True,
                              output=(f"Suggested route: {recommendation.route}. {recommendation.why} "
                                      f"Nothing was started. Simpler option: {recommendation.simpler}"),
                              data={"workflow_recommendation": projection})

        # Auto is deliberately a saved-workflow fast path. It does not infer or save a new
        # plan, and every call re-reads current policy before touching the scheduler.
        if recommendation.route != "saved_workflow" or candidate is None:
            projection.update(status="not_started", why=(recommendation.why +
                " Auto can start only an activated saved workflow in the reviewed scope; this request will stay direct."))
            return ToolResult(ok=True, output=projection["why"],
                              data={"workflow_recommendation": projection})

        inputs = args.get("inputs", {})
        if not isinstance(inputs, dict):
            return ToolResult(ok=False, output="workflow inputs must be an object")
        request_body = {"workflow_id": str(candidate["id"]), "inputs": inputs,
                        "conversation_id": ctx.run.conversation_id, "auto": True}
        digest = hashlib.sha256(json.dumps(request_body, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode()).hexdigest()
        call_index = ctx.tool_call_index if isinstance(ctx.tool_call_index, int) else 0
        idempotency = hashlib.sha256(
            f"auto-workflow:{ctx.run.id}:{ctx.run.steps}:{call_index}".encode()).hexdigest()[:48]
        try:
            submission = wfsubmit.submit_saved(
                ctx.store, bot=live_bot, definition=str(candidate["id"]), inputs=inputs,
                origin="workflow_auto", conversation_id=ctx.run.conversation_id,
                idem_key=idempotency, request_hash=digest, auto=True,
            )
        except (wfsubmit.PlanInputError, wfsubmit.PlanNotSubmittable) as exc:
            projection.update(status="not_started", why=f"Auto did not start this workflow: {exc}")
            return ToolResult(ok=True, output=projection["why"],
                              data={"workflow_recommendation": projection})
        ctx.store.bus.notify("work")
        projection.update(status="started", workflow_run_id=submission.workflow_run_id,
                           attempt_run_id=submission.attempt_run_id)
        return ToolResult(ok=True,
                          output=(f"Started reviewed workflow {candidate['name']!r} in the current Auto scope. "
                                  f"Workflow run {submission.workflow_run_id}; nothing outside its saved plan was authorized."),
                          data={"workflow_recommendation": projection})
