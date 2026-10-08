"""T-STATE-MACHINE: only table transitions are possible; terminal states are absorbing; labels exist for every state."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from hutch.lifecycle import LABELS, LIVE, NEEDS_PERSON, TERMINAL, TRANSITIONS, allowed
from hutch.models import ACTIVE_STATUSES, Run, RunStatus

ALL = list(RunStatus)


def test_every_status_has_a_row_and_a_label():
    assert set(TRANSITIONS) == set(RunStatus) == set(LABELS)
    assert all(LABELS[s] for s in RunStatus)


def test_terminal_states_are_absorbing():
    for s in TERMINAL:
        assert TRANSITIONS[s] == frozenset(), f"{s.value} must not be left"


def test_active_and_terminal_partition_the_states():
    assert set(ACTIVE_STATUSES) | TERMINAL == set(RunStatus)
    assert not (set(ACTIVE_STATUSES) & TERMINAL)


def test_a_live_run_can_always_be_ended_so_nothing_gets_stuck():
    """Whatever a live run is doing, recovery or a stop can end it; a state with no way out would hold its bot forever."""
    for s in LIVE:
        assert TRANSITIONS[s] & TERMINAL, f"{s.value} has no route to a terminal state"


def test_a_queued_run_can_be_cancelled_or_started_but_not_marked_done():
    assert allowed(RunStatus.pending, RunStatus.running) and allowed(RunStatus.pending, RunStatus.stopped)
    assert not allowed(RunStatus.pending, RunStatus.succeeded)       # nothing succeeds without running


def test_cancelling_never_turns_into_success():
    """Stop always wins: a run that was being cancelled cannot report that it succeeded."""
    assert not allowed(RunStatus.cancelling, RunStatus.succeeded)
    assert not allowed(RunStatus.recovering, RunStatus.succeeded)
    assert not allowed(RunStatus.recovering, RunStatus.running)      # a recovered run is never resumed in the middle


def test_people_are_asked_only_when_something_needs_them():
    assert NEEDS_PERSON == {RunStatus.waiting_approval, RunStatus.waiting_human, RunStatus.outcome_unknown}


def test_run_json_carries_labels_for_the_ui():
    d = Run(bot_id="b", prompt="x", status=RunStatus.stopped).model_dump()
    assert d["status_label"] == "Cancelled" and d["terminal"] is True and d["needs_person"] is False
    d = Run(bot_id="b", prompt="x", status=RunStatus.waiting_approval).model_dump()
    assert d["status_label"] == "Waiting for you" and d["terminal"] is False and d["needs_person"] is True


@given(st.lists(st.sampled_from(ALL), min_size=1, max_size=40))
def test_any_walk_that_only_takes_legal_steps_never_leaves_a_terminal_state(targets):
    state, ended = RunStatus.pending, False
    for to in targets:
        if allowed(state, to):
            assert not ended, "moved after reaching a terminal state"
            state = to
            ended = state in TERMINAL
    assert (state in TERMINAL) == ended


@pytest.mark.parametrize("frm", [s for s in RunStatus if s in TERMINAL])
@pytest.mark.parametrize("to", ALL)
def test_nothing_leaves_a_terminal_state(frm, to):
    assert not allowed(frm, to)
