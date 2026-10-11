"""Workspace action tool tests: planning review and gated execution wiring."""

from __future__ import annotations

import uuid

from hutch.actions.execute import ExecutorResult
from hutch.approvals import ApprovalGate
from hutch.models import ApprovalMode, Bot, Run
from hutch.safety import PolicyEngine
from hutch.tools.base import ToolContext
from hutch.tools.workspace_actions import PlanWorkspaceActionTool, RunWorkspacePlanTool


def _ctx(tmp_path, store, config) -> ToolContext:
    bot = store.create_bot(Bot(name=f"ws-{uuid.uuid4().hex[:6]}", model="mock/demo",
                               tools=["workspace"], approval_mode=ApprovalMode.auto))
    run = store.create_run(Run(bot_id=bot.id, prompt="x"))
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    policy = PolicyEngine()
    gate = ApprovalGate(store, bot, run, policy, emit=lambda _e: None)
    return ToolContext(bot=bot, run=run, store=store, policy=policy, gate=gate,
                       config=config, workspace=ws)


def _steps(account: str = "gws_" + "a" * 24) -> list[dict]:
    return [
        {"kind": "cloud_create", "id": "doc", "title": "Create the brief",
         "target": {"service": "docs", "account": account, "parent_id": "folder-1",
                    "display": "Docs 'Brief' -> folder-1"},
         "inputs": {"title": "Brief", "body_text": "Agenda"}},
        {"kind": "cloud_create", "id": "sheet", "title": "Create the tracker",
         "target": {"service": "sheets", "account": account, "parent_id": "folder-1",
                    "display": "Sheets 'Tracker' -> folder-1"},
         "inputs": {"title": "Tracker", "sheet_titles": ["Runs"]}},
        {"kind": "cloud_edit", "id": "row", "title": "Append the row",
         "target": {"service": "sheets", "account": account, "display": "Tracker!Runs"},
         "inputs": {"spreadsheet_id": {"$remote_id": "sheet"},
                    "columns": [{"name": "n", "kind": "integer"}], "rows": [[1]],
                    "sheet_title": "Runs"}},
        {"kind": "notify", "id": "tell", "title": "Email attendees",
         "target": {"service": "calendar", "account": account, "display": "invite a@example.com",
                    "audience": "attendees"},
         "inputs": {"emails": ["a@example.com"]}},
    ]


def test_plan_workspace_action_persists_a_review_with_separate_authority(tmp_path, store, config):
    ctx = _ctx(tmp_path, store, config)
    result = PlanWorkspaceActionTool().run(
        {"intent": "Prepare Thursday's package", "steps": _steps()}, ctx)
    assert result.ok, result.output
    assert result.data["review"]["separate_authority_steps"] == ["tell"]
    assert "need their own approval" in result.output
    row = store.get_action_plan(result.data["plan_id"])
    assert row["status"] == "draft"
    # the reference created the dependency automatically
    plan = row["doc"]
    row_step = next(s for s in plan["steps"] if s["id"] == "row")
    assert row_step["depends_on"] == ["sheet"]


def test_run_workspace_plan_requires_a_connected_account(tmp_path, store, config, monkeypatch):
    ctx = _ctx(tmp_path, store, config)
    planned = PlanWorkspaceActionTool().run(
        {"intent": "x", "steps": _steps()}, ctx)
    assert planned.ok

    class _EmptyClient:
        def accounts(self):
            return []

    monkeypatch.setattr("hutch.tools.workspace_actions._client", lambda ctx: _EmptyClient())
    result = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"],
         "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert not result.ok and "no Google Workspace account" in result.output


def test_run_workspace_plan_executes_with_the_approved_hash(tmp_path, store, config, monkeypatch):
    ctx = _ctx(tmp_path, store, config)
    planned = PlanWorkspaceActionTool().run({"intent": "x", "steps": _steps()}, ctx)
    assert planned.ok

    class _Client:
        def accounts(self):
            from hutch.gsuite.client import WorkspaceAccount
            return [WorkspaceAccount(account_id="gws_" + "a" * 24, label="Test",
                                     scopes=("https://www.googleapis.com/auth/documents",))]

    calls: list[str] = []

    def _executors(client):
        def run(step, plan):
            calls.append(step.id)
            return ExecutorResult(ok=True, remote_id=f"remote-{step.id}")
        return {("cloud_create", "docs"): run, ("cloud_create", "sheets"): run,
                ("cloud_edit", "sheets"): run, ("notify", "calendar"): run}

    monkeypatch.setattr("hutch.tools.workspace_actions._client", lambda ctx: _Client())
    monkeypatch.setattr("hutch.tools.workspace_actions.workspace_executors", _executors)
    monkeypatch.setattr(ctx.gate, "decide", lambda *a, **k: None)

    executed = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"],
         "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert executed.ok, executed.output
    assert executed.data["status"] == "partial"  # the notify step was denied its own approval
    assert calls == ["doc", "sheet", "row"]
    assert "denied" in executed.output

    denied = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"], "approved_hash": "stale-hash"}, ctx)
    assert not denied.ok and "does not match" in denied.output

    with_share = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"],
         "approved_hash": planned.data["approval_scope_hash"],
         "separately_approved": ["tell"]}, ctx)
    assert with_share.ok
    assert with_share.data["status"] == "completed"
