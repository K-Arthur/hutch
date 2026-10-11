"""Workspace action tools: propose an inspectable plan, then execute it under review.

``plan_workspace_action`` is free — it persists a plan and returns the exact review payload
(targets, effects, authorities, binding hash). ``run_workspace_plan`` is the outward action:
it always asks for approval (never a sticky allowance), refuses a hash that no longer
matches the plan's content, executes through the durable effect ledger, and reports partial
outcomes honestly.
"""

from __future__ import annotations

from typing import Any

from ..actions.execute import ApprovalMismatch, execute_plan, plan_outcome_report
from ..actions.plan import ActionPlan, build_plan, plan_review
from ..google_oauth_config import resolve_google_oauth_client_id
from ..gsuite.client import GoogleWorkspaceClient, GoogleWorkspaceError
from ..gsuite.executors import workspace_executors
from .base import Tool, ToolContext, ToolResult, rehearsed


def _obj(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def _client(ctx: ToolContext) -> GoogleWorkspaceClient:
    client_id, source = resolve_google_oauth_client_id(ctx.store)
    if not client_id:
        raise GoogleWorkspaceError(
            "no Google OAuth client id is configured; set HUTCH_GOOGLE_OAUTH_CLIENT_ID before "
            "connecting Workspace")
    return GoogleWorkspaceClient(ctx.config.state_dir, client_id)


class PlanWorkspaceActionTool(Tool):
    name = "plan_workspace_action"
    description = (
        "Build and persist an inspectable action plan for Google Documents, Sheets, Drive and "
        "Calendar work. Returns every target, effect and authority class plus the approval hash. "
        "Nothing is sent. Use {'$remote_id': '<step id>'} inside inputs to reference a resource "
        "an earlier step creates.")
    parameters = _obj(
        ["intent", "steps"],
        {
            "intent": {"type": "string", "description": "The user's exact request"},
            "summary": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object"}, "description":
                      "{kind: cloud_create|cloud_edit|cloud_move|cloud_share|notify|event_create|"
                      "routine_config|metered_generation|local_draft|read, title, target: {service, "
                      "account, resource_id, parent_id, display, audience}, inputs, depends_on}"},
        },
    )

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        steps = args.get("steps")
        if not isinstance(steps, list) or not steps:
            return ToolResult(ok=False, output="error: provide the plan steps")
        if len(steps) > 40:
            return ToolResult(ok=False, output="error: at most 40 steps per plan")
        try:
            plan = build_plan(
                str(args.get("intent", "")).strip(), steps,
                conversation_id=ctx.run.conversation_id or "", bot_id=ctx.bot.id, run_id=ctx.run.id,
                summary=str(args.get("summary", "")).strip())
        except ValueError as exc:
            return ToolResult(ok=False, output=f"error: the plan is not valid: {exc}")
        review = plan_review(plan)
        if not ctx.dry_run:
            ctx.store.save_action_plan(plan.model_dump(mode="json"))
        lines = [f"Plan {plan.id} ({plan.summary}) — {len(plan.steps)} step(s):"]
        for entry in review["steps"]:
            marker = {"none": "·", "review": "✓", "separate": "!"}[entry["authority"]]
            lines.append(f" {marker} [{entry['kind']}] {entry['title']} → {entry['target'] or entry['service']}")
        if review["separate_authority_steps"]:
            lines.append("Steps marked '!' change sharing or notify people and need their own approval.")
        lines.append(f"Approval hash: {review['approval_scope_hash']}")
        return ToolResult(ok=True, output="\n".join(lines), data={
            "plan_id": plan.id,
            "approval_scope_hash": review["approval_scope_hash"],
            "review": review,
        })


class RunWorkspacePlanTool(Tool):
    name = "run_workspace_plan"
    description = (
        "Execute an approved workspace action plan. Requires the plan's current approval hash "
        "and the connected Google account; always asks for approval, never re-sends a succeeded "
        "step, keeps successful work when a later step fails, and reports uncertain outcomes "
        "instead of retrying them.")
    parameters = _obj(
        ["plan_id", "approved_hash"],
        {
            "plan_id": {"type": "string"},
            "approved_hash": {"type": "string",
                              "description": "The approval hash shown in the plan review"},
            "separately_approved": {"type": "array", "items": {"type": "string"},
                                    "description": "Step ids that received their own approval"},
            "retry_failed": {"type": "boolean",
                             "description": "Re-run definitively failed steps (never uncertain ones)"},
        },
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "web"

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        plan_id = str(args.get("plan_id", "")).strip()
        approved_hash = str(args.get("approved_hash", "")).strip()
        row = ctx.store.get_action_plan(plan_id) if plan_id else None
        if row is None:
            return ToolResult(ok=False, output="error: no such plan; create it with plan_workspace_action")
        plan = ActionPlan.model_validate(row["doc"])
        if ctx.dry_run:
            return rehearsed(f"execute plan {plan.id} ({len(plan.steps)} steps): {plan.summary}")
        current_scope = plan.recompute_approval_scope()
        if approved_hash != current_scope:
            return ToolResult(ok=False, output=(
                "error: the approval does not match this plan's current steps/targets/inputs; "
                "review it again before approving"))
        try:
            client = _client(ctx)
        except GoogleWorkspaceError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        accounts = client.accounts()
        if not accounts:
            return ToolResult(ok=False, output=(
                "error: no Google Workspace account is connected on this machine. Connect one in "
                "Connections (Docs + Sheets + drive.file scopes) and retry; nothing was sent."))
        account_ids = {a.account_id for a in accounts}
        unbound = [s.target.display or s.id for s in plan.steps
                   if s.target.account and s.target.account not in account_ids]
        if unbound:
            return ToolResult(ok=False, output=(
                "error: these steps name an account that is not connected: " + ", ".join(unbound[:5])))
        review = plan_review(plan)
        try:
            ctx.gate.decide(
                "workspace_action", f"execute {len(plan.steps)} step(s): {plan.summary}",
                {"plan_id": plan.id, "approval_scope_hash": approved_hash,
                 "steps": [{"id": s["id"], "kind": s["kind"], "target": s["target"]}
                           for s in review["steps"]]},
                outward=True)
        except Exception as exc:  # noqa: BLE001 - denial and expiry both stop the call
            return ToolResult(ok=False, output=f"error: {exc}")
        executors = workspace_executors(client)
        try:
            executed = execute_plan(
                plan, store=ctx.store, executors=executors, approved_hash=approved_hash,
                separately_approved=set(args.get("separately_approved") or []),
                retry_failed=bool(args.get("retry_failed")))
        except ApprovalMismatch as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        report = plan_outcome_report(executed)
        lines = [f"Plan {executed.id}: {executed.status} ({report['counts']})"]
        for step in report["steps"]:
            detail = step["remote_id"] and f" -> {step['remote_id']}" or ""
            why = f" — {step['error']}" if step["error"] else ""
            lines.append(f" {step['status']}: {step['title']}{detail}{why}")
        if report["remaining"]:
            lines.append("Still open: " + ", ".join(report["remaining"]) +
                         " (retry selectively; uncertain steps need reconciliation first).")
        return ToolResult(ok=True, output="\n".join(lines), data={
            "plan_id": executed.id, "status": executed.status, "report": report})
