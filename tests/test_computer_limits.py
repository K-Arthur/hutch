"""Run-level action limits: a hard cap, and refusal once actions stop changing anything.

These are the two harness-side causes of the worst computer-use failures -- a run that loops forever, and a run nobody
bounded -- so the behaviour is pinned here without a desktop: the budget is plain accounting, and the tool wiring is
checked through a fake session.
"""

from __future__ import annotations

import pytest

from hutch.computer.limits import ActionBudget, fingerprint_of
from hutch.tools.computer_contract import STATEFUL
from hutch.tools.computer_dispatch import account


def test_the_cap_refuses_instead_of_looping():
    budget = ActionBudget(max_actions=3)
    assert budget.spend("observe", stateful=False) is None
    assert budget.spend("click", stateful=True) is None
    assert budget.spend("observe", stateful=False) is None
    refusal = budget.spend("click", stateful=True)
    assert refusal is not None and refusal.kind == "budget"
    assert "whole computer action budget" in refusal.message()
    assert "Nothing was dispatched" in refusal.message()
    assert budget.state()["refusals"] == 1


def test_a_refusal_does_not_consume_the_budget():
    budget = ActionBudget(max_actions=1)
    budget.spend("observe", stateful=False)
    assert budget.spend("observe", stateful=False).kind == "budget"
    assert budget.actions == 1


def test_three_unchanged_actions_stop_further_actions_but_not_observation():
    budget = ActionBudget(stall_limit=3)
    for _ in range(3):
        budget.note(stateful=True, changed=False, fingerprint="sha-a")
    assert budget.state()["stalled"] is True
    # Observation is still allowed: looking is how an agent recovers from being stuck.
    assert budget.spend("observe", stateful=False) is None
    refusal = budget.spend("click", stateful=True)
    assert refusal is not None and refusal.kind == "stalled"
    assert "changed nothing on screen" in refusal.message()
    assert "try a different element" in refusal.message()


def test_a_changed_screen_clears_the_stall():
    budget = ActionBudget(stall_limit=2)
    budget.note(stateful=True, changed=False, fingerprint="sha-a")
    budget.note(stateful=True, changed=False, fingerprint="sha-a")
    assert budget.state()["stalled"] is True
    budget.note(stateful=True, changed=True, fingerprint="sha-b")
    assert budget.state()["stalled"] is False
    assert budget.spend("click", stateful=True) is None


def test_a_verified_effect_counts_as_progress_even_without_a_visual_change():
    """set_text can verify by reading the element back; that is progress even if the framebuffer matched."""
    budget = ActionBudget(stall_limit=1)
    budget.note(stateful=True, changed=False, fingerprint="sha-a", verified=True)
    assert budget.state()["stalled"] is False
    assert budget.spend("set_text", stateful=True) is None


def test_a_different_frame_restarts_the_count():
    budget = ActionBudget(stall_limit=2)
    budget.note(stateful=True, changed=False, fingerprint="sha-a")
    budget.note(stateful=True, changed=False, fingerprint="sha-b")
    assert budget.state()["unchanged_actions"] == 1
    assert budget.state()["stalled"] is False


def test_only_stateful_actions_count_toward_a_stall():
    budget = ActionBudget(stall_limit=1)
    for _ in range(5):
        budget.note(stateful=False, changed=False, fingerprint="sha-a")
    assert budget.state()["stalled"] is False


def test_every_stateful_action_in_the_contract_is_covered():
    assert set(STATEFUL) == {"launch", "click", "type", "key", "activate", "set_text"}


def test_accounting_reads_the_frame_a_session_reported():
    class Result:
        ok = True
        output = "observed"
        data = {"observation": {"image": {"sha256": "abc123"}}, "visual_change": True}

    budget = ActionBudget()
    account(budget, "click", Result())
    assert budget.actions == 0          # spending happens before dispatch, not in accounting
    assert budget.state()["stalled"] is False
    assert Result.data["limits"]["unchanged_actions"] == 0


def test_fingerprint_ignores_absent_or_malformed_observations():
    assert fingerprint_of({}) == ""
    assert fingerprint_of({"observation": None}) == ""
    assert fingerprint_of({"observation": {"image": None}}) == ""
    assert fingerprint_of({"observation": {"image": {"sha256": 5}}}) == ""
    assert fingerprint_of({"observation": {"image": {"sha256": "deadbeef"}}}) == "deadbeef"


# ---------------------------------------------------------------- wiring


class FakeSession:
    """A session whose actions change nothing, the way a stuck agent experiences it."""

    semantic = False

    def observe(self):
        from hutch.computer.desktop import DesktopResult
        return DesktopResult(True, "observed", {"observation": {"image": {"sha256": "same"}},
                                                "images": []})

    def click(self, frame_id, x, y, *, button="left", count=1):
        from hutch.computer.desktop import DesktopResult
        return DesktopResult(True, "clicked", {"outcome": "dispatched", "visual_change": False,
                                               "observation": {"image": {"sha256": "same"}}})

    def elements(self, *, root="", limit=200):
        from hutch.computer.desktop import DesktopResult
        return DesktopResult(True, "tree", {"elements": {"nodes": []}, "snapshot_id": "a0001"})


def _tool_with(session):
    from hutch.tools.computer import ComputerTool
    tool = ComputerTool()
    tool._session = session
    tool._lease = __import__("hutch.computer.control", fromlist=["ControlLease"]).ControlLease("s")
    return tool


@pytest.fixture()
def bare_ctx():
    from types import SimpleNamespace

    class Gate:
        def decide(self, *args, **kwargs):
            return None

    return SimpleNamespace(bot=SimpleNamespace(id="b", computer_apps=["kwrite"]), run=SimpleNamespace(id="r"),
                           workspace=None, gate=Gate(), dry_run=False, begin_effect=lambda: None,
                           emit=lambda event: None, procs=SimpleNamespace(register=lambda *a, **k: None),
                           policy=None, config=None)


def test_the_tool_refuses_a_fourth_action_that_changes_nothing(bare_ctx, monkeypatch):
    tool = _tool_with(FakeSession())
    monkeypatch.setattr("hutch.computer.resources.authority", lambda ctx, kind: None)
    monkeypatch.setattr("hutch.computer.resources.workspace_grant", lambda ctx: {})
    frame = "f000001"
    for _ in range(3):
        result = tool.run({"action": "click", "frame_id": frame, "x": 10, "y": 10}, bare_ctx)
        assert result.ok, result.output
    refused = tool.run({"action": "click", "frame_id": frame, "x": 10, "y": 10}, bare_ctx)
    assert not refused.ok
    assert refused.data["outcome"] == "not_dispatched" and refused.data["stalled"] is True
    assert "report what you can see and stop" in refused.output
    # Looking is still allowed, and the run event data carries what happened.
    looked = tool.run({"action": "observe"}, bare_ctx)
    assert looked.ok and looked.data["limits"]["stalled"] is True
