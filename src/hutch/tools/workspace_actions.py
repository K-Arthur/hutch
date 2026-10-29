"""Workspace action tools: propose an inspectable plan, then execute it under review.

``plan_workspace_action`` is free; it persists a plan and returns the exact review payload
(targets, effects, authorities, binding hash). ``run_workspace_plan`` is the outward action:
it always asks for approval (never a sticky allowance), refuses a hash that no longer
matches the plan's content, executes through the durable effect ledger, and reports partial
outcomes honestly.
"""

from __future__ import annotations

import base64
import hashlib
import os
import stat
from typing import Any

from ..actions.execute import ApprovalMismatch, execute_plan, plan_outcome_report
from ..actions.plan import ActionPlan, build_plan, plan_review
from ..google_calendar import GoogleCalendarBook
from ..google_oauth_config import resolve_google_oauth_client_id
from ..gsuite.client import GoogleWorkspaceClient, GoogleWorkspaceError
from ..gsuite.executors import workspace_executors
from ..gsuite.executors import MAX_LOCAL_UPLOAD
from .base import Tool, ToolContext, ToolResult, rehearsed
from .filewrite import destination, parent_fd


def _read_approved_upload_source(path_value: str, ctx: ToolContext) -> tuple[bytes, dict[str, Any]]:
    """Read a regular workspace file through no-follow directory descriptors."""
    decision = ctx.policy.check_path(path_value, ctx.workspace, write=False)
    if decision.verdict.value == "deny":
        raise ValueError(decision.reason)
    workspace, parts = destination(path_value, ctx.workspace)
    with parent_fd(workspace, parts) as parent:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Drive upload source must be a regular file without symlinks")
            if before.st_size > MAX_LOCAL_UPLOAD:
                raise ValueError("Drive upload source exceeds the single-upload limit")
            content = stream.read(MAX_LOCAL_UPLOAD + 1)
            after = os.fstat(stream.fileno())
    if len(content) > MAX_LOCAL_UPLOAD:
        raise ValueError("Drive upload source exceeds the single-upload limit")
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or len(content) != after.st_size):
        raise ValueError("Drive upload source changed while it was being reviewed")
    digest = hashlib.sha256(content).hexdigest()
    try:
        text = content.decode("utf-8")
        is_text = True
    except UnicodeDecodeError:
        text = ""
        is_text = False
    if is_text:
        preview = text[:4_000]
        preview_kind = "utf8"
    else:
        preview = base64.b64encode(content[:192]).decode("ascii")
        preview_kind = "base64-prefix"
    return content, {
        "path": path_value,
        "size_bytes": len(content),
        "sha256": digest,
        "preview_kind": preview_kind,
        "preview": preview,
        "preview_truncated": len(text) > 4_000 if is_text else len(content) > 192,
    }


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
                   if s.target.account and s.target.account not in account_ids
                   and s.target.service in ("docs", "sheets", "drive")]
        if unbound:
            return ToolResult(ok=False, output=(
                "error: these steps name an account that is not connected: " + ", ".join(unbound[:5])))
        prepared_uploads: dict[str, bytes] = {}
        upload_sources: dict[str, dict[str, Any]] = {}
        for step in plan.steps:
            if step.kind != "cloud_create" or step.target.service != "drive":
                continue
            path_value = step.inputs.get("local_path")
            if not isinstance(path_value, str):
                continue
            try:
                content, source = _read_approved_upload_source(path_value, ctx)
            except (OSError, ValueError) as exc:
                return ToolResult(ok=False, output=f"error: Drive upload source cannot be reviewed: {exc}")
            previous = prepared_uploads.get(path_value)
            if previous is not None and previous != content:
                return ToolResult(ok=False, output=(
                    "error: Drive upload source changed while the plan was being prepared; review it again"))
            prepared_uploads[path_value] = content
            upload_sources[step.id] = source
        calendar_book = None
        calendar_steps = [s for s in plan.steps
                          if s.target.service == "calendar" and s.kind in ("event_create", "cloud_edit")]
        if calendar_steps:
            grant_reader = getattr(ctx.store, "google_calendar_grant", None)
            grant = grant_reader(ctx.bot.id) if callable(grant_reader) else None
            if not grant:
                return ToolResult(ok=False, output=(
                    "error: this Bot has no Google Calendar connection grant; connect a calendar "
                    "account and grant it before approving a calendar step. Nothing was sent."))
            for step in calendar_steps:
                if step.target.account and step.target.account != grant.get("account_id"):
                    return ToolResult(ok=False, output=(
                        "error: calendar steps must use this Bot's granted calendar account "
                        f"({grant.get('account_id')}), not {step.target.account}"))
                if step.kind == "event_create" and not grant.get("allow_event_creation"):
                    return ToolResult(ok=False, output=(
                        "error: this Bot's Calendar grant does not include event creation; "
                        "reconnect it with that explicit option before planning an event"))
            oauth_client_id, _source = resolve_google_oauth_client_id(ctx.store)
            calendar_book = GoogleCalendarBook(ctx.config.state_dir, oauth_client_id)
            connected = {str(a.get("id")) for a in calendar_book.accounts()}
            for step in calendar_steps:
                if step.target.account and step.target.account not in connected:
                    return ToolResult(ok=False, output=(
                        f"error: calendar account {step.target.account} is not connected on this machine"))
        review = plan_review(plan)
        for entry in review["steps"]:
            if entry["id"] in upload_sources:
                entry["upload_source"] = upload_sources[entry["id"]]
        try:
            ctx.gate.decide(
                "workspace_action", f"execute {len(plan.steps)} step(s): {plan.summary}",
                {"plan_id": plan.id, "approval_scope_hash": approved_hash,
                 "steps": [{"id": s["id"], "kind": s["kind"], "target": s["target"],
                            "inputs": s["inputs"], **({"upload_source": s["upload_source"]}
                                                       if "upload_source" in s else {})}
                           for s in review["steps"]]},
                outward=True)
        except Exception as exc:  # noqa: BLE001 - denial and expiry both stop the call
            return ToolResult(ok=False, output=f"error: {exc}")
        separately_approved: set[str] = set()
        for step in plan.ordered_steps():
            if step.authority() != "separate":
                continue
            try:
                ctx.gate.decide(
                    "workspace_action_separate",
                    f"separately approve {step.kind}: {step.title}",
                    {"plan_id": plan.id, "step_id": step.id, "kind": step.kind,
                     "target": step.target.model_dump(mode="json"),
                     "request_hash": step.request_hash},
                    outward=True)
            except Exception as exc:  # noqa: BLE001 - each separate grant is an independent decision
                continue
            separately_approved.add(step.id)
        def read_prepared_upload(path_value: str) -> bytes:
            try:
                return prepared_uploads[path_value]
            except KeyError:
                raise ValueError("Drive upload source was not included in the reviewed plan") from None

        executors = workspace_executors(client, read_local_file=read_prepared_upload,
                                        calendar_book=calendar_book)
        try:
            executed = execute_plan(
                plan, store=ctx.store, executors=executors, approved_hash=approved_hash,
                separately_approved=separately_approved,
                retry_failed=bool(args.get("retry_failed")))
        except (ApprovalMismatch, ValueError) as exc:
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
