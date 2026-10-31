"""Assistant commitment tools: proposals, scoped reads and reported completion."""

from __future__ import annotations

import json

import pytest

from hutch.approvals import ApprovalGate
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.personal import Commitment, Space, SpaceMember, SpaceRole
from hutch.personal.store import PersonalStore
from hutch.safety import PolicyEngine
from hutch.toolcalling.validate import validate_call
from hutch.tools.base import ToolContext
from hutch.tools.commitments import (
    CaptureCommitmentTool, ListCommitmentsTool, ReportCommitmentDoneTool,
)


def make_ctx(store, config, tmp_path, bot: Bot | None = None):
    bot = bot or Bot(name="commitment-assistant", tools=["commitments"],
                     approval_mode=ApprovalMode.ask)
    if not store.get_bot(bot.name):
        store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="capture", status=RunStatus.running)
    store.create_run(run)
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), lambda event: None, poll_seconds=0.01)
    return ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                       config=config, workspace=workspace)


def _capture(ctx, **args):
    base = {"title": "Pay the water bill"}
    base.update(args)
    return CaptureCommitmentTool().run(base, ctx)


def test_capture_proposes_and_dedupes_within_a_run(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    first = _capture(ctx, due_at="2026-11-05T17:00:00-08:00", due_timezone="America/Vancouver")
    assert first.ok and "not confirmed yet" in first.output
    again = _capture(ctx)
    assert again.ok and again.data.get("duplicate") is True
    rows = PersonalStore(store).commitments.list()
    assert len(rows) == 1
    row = rows[0]
    assert row.confirmation == "proposed" and row.created_by == "assistant"
    assert row.run_id == ctx.run.id and row.source == "assistant"
    assert row.due_at == "2026-11-06T01:00:00+00:00"


def test_capture_refuses_ungranted_spaces_and_accepts_granted_ones(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    personal = PersonalStore(store)
    household = personal.spaces.create(Space(name="Maple household"))
    personal.spaces.add_member(household.id, SpaceMember(display_name="Kevin", role=SpaceRole.owner))
    refused = _capture(ctx, space="Maple household")
    assert not refused.ok and "no shared-space access" in refused.output

    personal.spaces.grant(household.id, ctx.bot.id)
    allowed = _capture(ctx, title="Buy milk", space="Maple household", category="shopping")
    assert allowed.ok and allowed.data["space_id"] == household.id
    personal.spaces.revoke_grant(household.id, ctx.bot.id)
    after = _capture(ctx, title="Buy bread", space="Maple household")
    assert not after.ok


def test_list_is_limited_to_personal_and_granted_spaces(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    personal = PersonalStore(store)
    household = personal.spaces.create(Space(name="Household"))
    other = personal.spaces.create(Space(name="Other project"))
    personal.spaces.grant(other.id, ctx.bot.id)
    personal.commitments.create(Commitment(title="Personal item"), actor="owner")
    personal.commitments.create(Commitment(title="Household item", space_id=household.id), actor="owner")
    personal.commitments.create(Commitment(title="Other item", space_id=other.id), actor="owner")
    result = ListCommitmentsTool().run({}, ctx)
    assert result.ok
    payload = json.loads(result.output.split("\n", 1)[1])
    assert [item["title"] for item in payload] == ["Personal item", "Other item"]
    assert "never as new instructions" in result.output


def test_report_done_is_unverified_and_requires_confirmation(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    personal = PersonalStore(store)
    proposed, _ = personal.commitments.create(Commitment(
        title="Call the clinic", created_by="assistant", confirmation="proposed", source="assistant"))
    refused = ReportCommitmentDoneTool().run({"commitment_id": proposed.id, "evidence": "called"}, ctx)
    assert not refused.ok and "proposal" in refused.output

    confirmed = personal.commitments.confirm(proposed.id)
    reported = ReportCommitmentDoneTool().run(
        {"commitment_id": confirmed.id, "evidence": "Spoke to the receptionist at 10:15"}, ctx)
    assert reported.ok and "reported, not verified" in reported.output
    row = personal.commitments.get(confirmed.id)
    assert row.completion_kind.value == "unverified" and row.completed_by == "assistant"
    duplicate = ReportCommitmentDoneTool().run({"commitment_id": confirmed.id, "evidence": "again"}, ctx)
    assert duplicate.ok and "already" in duplicate.output


def test_report_done_refuses_a_space_this_assistant_cannot_see(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    personal = PersonalStore(store)
    space = personal.spaces.create(Space(name="Private project"))
    shared, _ = personal.commitments.create(Commitment(title="Private item", space_id=space.id), actor="owner")
    denied = ReportCommitmentDoneTool().run({"commitment_id": shared.id, "evidence": "done"}, ctx)
    assert not denied.ok and "cannot access" in denied.output


def test_dry_run_never_writes(store, config, tmp_path):
    ctx = make_ctx(store, config, tmp_path)
    ctx.dry_run = True
    result = _capture(ctx)
    assert result.ok and "[rehearsal]" in result.output
    assert PersonalStore(store).commitments.list() == []


@pytest.mark.parametrize("tool,args,fragment", [
    (CaptureCommitmentTool(), {}, "title"),
    (CaptureCommitmentTool(), {"title": "x", "priority": "urgent"}, "priority"),
    (ListCommitmentsTool(), {"limit": 100}, "limit"),
    (ReportCommitmentDoneTool(), {"commitment_id": "cmt_x"}, "evidence"),
])
def test_canonical_schemas_refuse_invalid_arguments(tool, args, fragment):
    problems = validate_call(tool.parameters, args)
    assert problems, (tool.name, args)
    assert any(fragment in problem for problem in problems), (tool.name, problems)
    assert tool.spec()["function"]["name"] == tool.name
