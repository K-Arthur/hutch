"""Workspace action tool tests: planning review and gated execution wiring."""

from __future__ import annotations

import hashlib
import uuid

from hutch.actions.execute import ExecutorResult
from hutch.approvals import ApprovalGate
from hutch.gsuite.client import WorkspaceAccount
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


def _drive_upload(path: str, account: str = "gws_" + "a" * 24) -> list[dict]:
    return [{"kind": "cloud_create", "id": "upload", "title": "Upload reviewed file",
             "target": {"service": "drive", "account": account, "parent_id": "folder-1",
                        "display": "Shared folder"},
             "inputs": {"name": "source.txt", "local_path": path, "mime_type": "text/plain"}}]


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

    def _executors(client, *, read_local_file=None, calendar_book=None):
        def run(step, plan):
            calls.append(step.id)
            return ExecutorResult(ok=True, remote_id=f"remote-{step.id}")
        return {("cloud_create", "docs"): run, ("cloud_create", "sheets"): run,
                ("cloud_edit", "sheets"): run, ("notify", "calendar"): run}

    monkeypatch.setattr("hutch.tools.workspace_actions._client", lambda ctx: _Client())
    monkeypatch.setattr("hutch.tools.workspace_actions.workspace_executors", _executors)
    approvals: list[tuple[str, dict]] = []
    deny_separate = True

    def _approve(tool, action, detail, **kwargs):
        approvals.append((tool, detail))
        if tool == "workspace_action_separate" and deny_separate:
            raise PermissionError("separate approval declined")

    monkeypatch.setattr(ctx.gate, "decide", _approve)

    executed = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"],
         "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert executed.ok, executed.output
    assert executed.data["status"] == "partial"  # the notify step was denied its own approval
    assert calls == ["doc", "sheet", "row"]
    assert "denied" in executed.output
    assert [tool for tool, _ in approvals] == ["workspace_action", "workspace_action_separate"]
    assert approvals[1][1]["step_id"] == "tell"

    denied = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"], "approved_hash": "stale-hash"}, ctx)
    assert not denied.ok and "does not match" in denied.output

    with_share = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"],
         "approved_hash": planned.data["approval_scope_hash"],
         "separately_approved": ["tell"]}, ctx)
    assert with_share.ok
    assert with_share.data["status"] == "partial"
    assert calls[-3:] == ["doc", "sheet", "row"]

    deny_separate = False
    approved_separately = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"],
         "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert approved_separately.ok
    assert approved_separately.data["status"] == "completed"
    assert calls[-1] == "tell"


def test_drive_upload_denies_sources_outside_workspace_before_approval(tmp_path, store, config, monkeypatch):
    ctx = _ctx(tmp_path, store, config)
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    planned = PlanWorkspaceActionTool().run({"intent": "upload", "steps": _drive_upload(str(outside))}, ctx)
    assert planned.ok

    class _Client:
        def accounts(self):
            return [WorkspaceAccount("gws_" + "a" * 24, "Test", ())]

    approvals = []
    monkeypatch.setattr("hutch.tools.workspace_actions._client", lambda _ctx: _Client())
    monkeypatch.setattr(ctx.gate, "decide", lambda *args, **kwargs: approvals.append((args, kwargs)))
    result = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"], "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert not result.ok and "escapes the workspace jail" in result.output
    assert approvals == []


def test_drive_upload_refuses_symlink_sources_before_approval(tmp_path, store, config, monkeypatch):
    ctx = _ctx(tmp_path, store, config)
    real = ctx.workspace / "real.txt"
    real.write_text("private")
    (ctx.workspace / "alias.txt").symlink_to(real)
    planned = PlanWorkspaceActionTool().run({"intent": "upload", "steps": _drive_upload("alias.txt")}, ctx)
    assert planned.ok

    class _Client:
        def accounts(self):
            return [WorkspaceAccount("gws_" + "a" * 24, "Test", ())]

    approvals = []
    monkeypatch.setattr("hutch.tools.workspace_actions._client", lambda _ctx: _Client())
    monkeypatch.setattr(ctx.gate, "decide", lambda *args, **kwargs: approvals.append((args, kwargs)))
    result = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"], "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert not result.ok and "cannot be reviewed" in result.output
    assert approvals == []


def test_drive_upload_freezes_reviewed_source_bytes_and_discloses_digest(tmp_path, store, config, monkeypatch):
    ctx = _ctx(tmp_path, store, config)
    source = ctx.workspace / "source.txt"
    original = b"reviewed upload payload"
    source.write_bytes(original)
    planned = PlanWorkspaceActionTool().run({"intent": "upload", "steps": _drive_upload("source.txt")}, ctx)
    assert planned.ok

    class _Client:
        def accounts(self):
            return [WorkspaceAccount("gws_" + "a" * 24, "Test", ())]

    seen: list[bytes] = []

    def _executors(_client, *, read_local_file, calendar_book=None):
        def upload(step, _plan):
            seen.append(read_local_file(step.inputs["local_path"]))
            return ExecutorResult(ok=True, remote_id="drive-file-1")
        return {("cloud_create", "drive"): upload}

    approval_details = []

    def _approve(_tool, _action, detail, **_kwargs):
        approval_details.append(detail)
        source.write_bytes(b"changed after approval request")

    monkeypatch.setattr("hutch.tools.workspace_actions._client", lambda _ctx: _Client())
    monkeypatch.setattr("hutch.tools.workspace_actions.workspace_executors", _executors)
    monkeypatch.setattr(ctx.gate, "decide", _approve)
    result = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"], "approved_hash": planned.data["approval_scope_hash"]}, ctx)

    assert result.ok and result.data["status"] == "completed"
    assert seen == [original]
    step_review = approval_details[0]["steps"][0]
    assert step_review["inputs"]["local_path"] == "source.txt"
    assert step_review["upload_source"]["size_bytes"] == len(original)
    assert step_review["upload_source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert step_review["upload_source"]["preview"] == original.decode()


def test_event_plan_requires_the_bot_calendar_grant_then_executes(tmp_path, store, config, monkeypatch):
    account = "gcal_" + "b" * 24
    ctx = _ctx(tmp_path, store, config)
    steps = [{"kind": "event_create", "id": "meet", "title": "Create the meeting",
              "target": {"service": "calendar", "account": account,
                         "display": "Calendar 'primary' 2026-10-12 09:00"},
              "inputs": {"summary": "Design review", "start": "2026-10-12T09:00:00",
                         "end": "2026-10-12T10:00:00", "timezone": "America/Los_Angeles",
                         "reminders": {"popup": 10}}}]
    planned = PlanWorkspaceActionTool().run({"intent": "book a review", "steps": steps}, ctx)
    assert planned.ok, planned.output

    class _Client:
        def accounts(self):
            from hutch.gsuite.client import WorkspaceAccount
            return [WorkspaceAccount(account_id="gws_" + "a" * 24, label="T", scopes=())]

    monkeypatch.setattr("hutch.tools.workspace_actions._client", lambda ctx: _Client())
    missing = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"], "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert not missing.ok and "Calendar connection grant" in missing.output

    store.set_google_calendar_grant(ctx.bot.id, account, "primary", "Personal",
                                    allow_event_creation=True)
    created: list[dict] = []

    class _Book:
        def __init__(self, state_dir, client_id):
            pass

        def accounts(self):
            return [{"id": account, "label": "Personal", "status": "connected"}]

        def create_event(self, account_id, calendar_id, *, summary, start, end,
                         description="", reminders=None, before_write=None):
            created.append({"account_id": account_id, "calendar_id": calendar_id,
                            "summary": summary, "start": start, "reminders": reminders})
            return {"id": "event-9", "summary": summary, "start": start, "end": end}

    monkeypatch.setattr("hutch.tools.workspace_actions.GoogleCalendarBook", _Book)
    monkeypatch.setattr(ctx.gate, "decide", lambda *a, **k: None)
    executed = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"], "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert executed.ok, executed.output
    assert executed.data["status"] == "completed"
    assert created and created[0]["calendar_id"] == "primary"
    assert created[0]["reminders"] == {"popup": 10}
    assert executed.data["report"]["steps"][0]["remote_id"] == "event-9"


def test_reminder_step_never_clears_reminders_by_accident(tmp_path, store, config, monkeypatch):
    account = "gcal_" + "b" * 24
    ctx = _ctx(tmp_path, store, config)
    steps = [{"kind": "cloud_edit", "id": "remind", "title": "Set the reminder",
              "target": {"service": "calendar", "account": account, "resource_id": "event-9",
                         "display": "event-9 reminders"},
              "inputs": {"event_id": "event-9", "calendar_id": "primary"}}]  # no reminders key
    planned = PlanWorkspaceActionTool().run({"intent": "set a reminder", "steps": steps}, ctx)
    assert planned.ok

    class _Client:
        def accounts(self):
            from hutch.gsuite.client import WorkspaceAccount
            return [WorkspaceAccount(account_id="gws_" + "a" * 24, label="T", scopes=())]

    class _Book:
        def __init__(self, *a, **k):
            pass

        def accounts(self):
            return [{"id": account, "status": "connected"}]

        def update_event_reminders(self, *a, **k):
            raise AssertionError("must not run without explicit reminders or reset_default")

    monkeypatch.setattr("hutch.tools.workspace_actions._client", lambda ctx: _Client())
    monkeypatch.setattr("hutch.tools.workspace_actions.GoogleCalendarBook", _Book)
    monkeypatch.setattr(ctx.gate, "decide", lambda *a, **k: None)
    store.set_google_calendar_grant(ctx.bot.id, account, "primary", "Personal")
    executed = RunWorkspacePlanTool().run(
        {"plan_id": planned.data["plan_id"], "approved_hash": planned.data["approval_scope_hash"]}, ctx)
    assert executed.ok and executed.data["status"] == "failed"
    assert "reset_default" in executed.output
