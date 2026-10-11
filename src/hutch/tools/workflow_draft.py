"""The model-facing authoring gate: draft a plan, never start one.

A model may only *author* a workflow when the authoring role is qualified for the exact
route it is running on (probed evidence - see :mod:`hutch.workflow.qualify`). This tool is
the whole model-facing surface for authoring, and it deliberately cannot execute anything:

* it validates and compiles the submitted plan and returns precise diagnostics;
* it checks the plan's envelope against this Bot's authority and qualifies every model
  role it names;
* it returns the plan hash and the bounded structure so the person can review it;
* it does **not** admit, dispatch or schedule anything. Starting a reviewed plan is the
  person's action (``hutch workflow run`` or the Studio control), which keeps "the model
  wrote a plan" and "we agreed to run it" as separate decisions.

When the route is not qualified the tool explains the missing evidence and the options,
and a guessed direct call is refused with the same explanation rather than silently
falling back to a different model.
"""
from __future__ import annotations

from typing import Any

from .base import Tool, ToolContext, ToolResult

MAX_PLAN_CHARS = 200_000


class DraftWorkflowTool(Tool):
    name = "draft_workflow"
    description = (
        "Validate a dynamic-workflow plan without running it. Use this when the operator asks for a "
        "workflow or wants a reusable procedure: submit a plan as JSON and you get back compile "
        "diagnostics, the plan hash and the bounded structure. This tool never starts work; a person "
        "starts a reviewed plan."
    )
    parameters = {
        "type": "object",
        "required": ["plan"],
        "properties": {
            "plan": {"type": "object", "description": "The plan document (schema_version 1)."},
            "name": {"type": "string", "description": "Optional definition name to save under."},
            "save": {"type": "boolean", "description": "Save it as an inactive definition for review."},
        },
        "additionalProperties": False,
    }

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return ""            # writes no receipt: drafting is not an effect on the world

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        from ..workflow import persistence as wstore
        from ..workflow import qualify
        from ..workflow import submit as wfsubmit
        from ..workflow.compile import PlanInvalid, compile_plan, plan_structure

        plan = args.get("plan")
        if not isinstance(plan, dict):
            return ToolResult(ok=False, output="error: 'plan' must be a JSON object")
        import json

        if len(json.dumps(plan, default=str)) > MAX_PLAN_CHARS:
            return ToolResult(ok=False, output="error: the plan is too large to review here")
        gate = qualify.assess("author", spec=ctx.bot.model, store=ctx.store,
                              base_url=ctx.bot.base_url or None)
        if not gate.allowed:
            return ToolResult(
                ok=False,
                output=("error: this route is not qualified to author workflows. " + gate.summary()
                        + " Options: have the person write or import the plan, run an existing reviewed "
                          "plan, or record a passed probe for this exact route revision."),
                data={"qualification": gate.as_dict()})
        try:
            compiled = compile_plan(plan)
        except PlanInvalid as exc:
            return ToolResult(ok=False,
                              output="the plan did not compile:\n" + "\n".join(
                                  d.render() for d in exc.diagnostics[:12]),
                              data={"diagnostics": [d.render() for d in exc.diagnostics[:12]]})
        try:
            verdicts = wfsubmit.check_authority(compiled, ctx.bot, store=ctx.store)
        except wfsubmit.PlanNotSubmittable as exc:
            return ToolResult(ok=False, output=f"this Bot may not run that plan: {exc}")
        structure = plan_structure(plan)
        summary = [f"plan {compiled.plan.name!r} compiles: {len(compiled.nodes)} sites, "
                   f"hash {compiled.plan_hash[:12]}…",
                   "structure: " + ", ".join(f"{item['site_id']}({item['kind']})" for item in structure)]
        for verdict in verdicts:
            summary.append(f"role {verdict['role']} on {verdict['route']['spec'] if verdict['route'] else '?'}: "
                           f"{verdict['state']}")
        saved_note = ""
        if args.get("save"):
            saved = wstore.save_definition(ctx.store, name=str(args.get("name") or compiled.plan.name),
                                           plan=compiled.plan.model_dump(by_alias=True, exclude_none=True,
                                                                         mode="json"),
                                           source="model", created_by="model")
            saved_note = f"\nsaved as an inactive definition (revision {saved['revision']}); nothing was started."
        return ToolResult(ok=True, output="\n".join(summary) + saved_note,
                          data={"plan_hash": compiled.plan_hash, "nodes": len(compiled.nodes),
                                "roles": verdicts, "structure": structure,
                                "started": False})
