"""Control ownership: who may act, and that a stale action can never land (deterministic, no browser)."""

from __future__ import annotations

import threading

import pytest

from hutch.computer.control import ControlLease, ControlOwner, StaleControl


def test_a_new_session_is_agent_controlled_but_needs_an_observation_for_coordinates():
    lease = ControlLease("s1")
    assert lease.snapshot().owner is ControlOwner.agent
    lease.begin_action()                                        # semantic actions need no frame
    with pytest.raises(StaleControl, match="observe again"):
        lease.begin_action(needs_fresh_observation=True)
    lease.note_observation("f000001")
    assert lease.begin_action(needs_fresh_observation=True).generation == lease.snapshot().generation


def test_takeover_fences_an_action_that_was_already_in_flight():
    lease = ControlLease("s1")
    ticket = lease.begin_action()
    lease.take_over("phone user took control")
    with pytest.raises(StaleControl, match="control changed"):
        lease.check(ticket)
    with pytest.raises(StaleControl, match="a person is controlling"):
        lease.begin_action()


def test_handing_back_starts_a_new_generation_and_requires_a_fresh_observation():
    lease = ControlLease("s1")
    lease.note_observation("f000001")
    old = lease.begin_action()
    lease.take_over()
    snap = lease.hand_back()
    assert snap.owner is ControlOwner.agent and snap.generation > old.generation
    with pytest.raises(StaleControl):
        lease.check(old)                                        # a plan made before the handoff cannot continue
    with pytest.raises(StaleControl, match="observe again"):
        lease.begin_action(needs_fresh_observation=True)
    lease.note_observation("f000002")
    lease.begin_action(needs_fresh_observation=True)


def test_navigation_invalidates_the_observation_not_the_authority():
    lease = ControlLease("s1")
    lease.note_observation("f000001")
    ticket = lease.begin_action(needs_fresh_observation=True)
    lease.invalidate_observation("the page navigated")
    with pytest.raises(StaleControl, match="after the observation"):
        lease.check(ticket, needs_fresh_observation=True)
    lease.check(ticket)                                         # semantic input is still authorized


def test_stop_is_terminal_and_blocks_everything():
    lease = ControlLease("s1")
    ticket = lease.begin_action()
    lease.request_stop()
    with pytest.raises(StaleControl):
        lease.check(ticket)
    for call in (lease.begin_action, lease.take_over, lease.hand_back):
        with pytest.raises(StaleControl):
            call()
    assert lease.confirm_stopped(0).owner is ControlOwner.stopped
    with pytest.raises(StaleControl, match="was stopped"):
        lease.begin_action()


def test_unverified_cleanup_requires_recovery_and_cannot_be_resumed():
    lease = ControlLease("s1")
    lease.request_stop()
    snap = lease.confirm_stopped(survivors=2)
    assert snap.owner is ControlOwner.recovery_required and "2 process" in snap.reason
    with pytest.raises(StaleControl, match="reconcile"):
        lease.begin_action()
    with pytest.raises(StaleControl):
        lease.hand_back()


def test_pause_blocks_and_hand_back_resumes():
    lease = ControlLease("s1")
    lease.pause()
    with pytest.raises(StaleControl, match="paused"):
        lease.begin_action()
    assert lease.hand_back("resumed").owner is ControlOwner.agent
    lease.begin_action()


def test_observers_see_every_transition_and_cannot_break_ownership():
    seen = []
    lease = ControlLease("s1", on_change=lambda s: (seen.append((s.owner.value, s.generation)), 1 / 0))
    lease.take_over()
    lease.hand_back()
    lease.request_stop()
    assert [owner for owner, _ in seen] == ["human", "agent", "stopping"]
    assert [g for _, g in seen] == sorted(g for _, g in seen) and len({g for _, g in seen}) == 3
    assert lease.snapshot().owner is ControlOwner.stopping


def test_a_race_between_takeover_and_dispatch_never_lets_both_win():
    """Hammer check(): once take_over() returned, no ticket from before it may pass."""
    for _ in range(200):
        lease = ControlLease("s1")
        ticket = lease.begin_action()
        done = threading.Event()
        landed_after = []

        def dispatcher():
            while not done.is_set():
                try:
                    lease.check(ticket)
                except StaleControl:
                    return
        thread = threading.Thread(target=dispatcher)
        thread.start()
        lease.take_over()
        done.set()
        thread.join()
        try:
            lease.check(ticket)
            landed_after.append(True)
        except StaleControl:
            pass
        assert not landed_after
