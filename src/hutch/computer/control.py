"""Who may inject input into a controlled surface right now, fenced by a generation counter.

Task status says what a *run* is doing; control ownership says who may touch the *surface* (a browser tab, a desktop
window). They differ: a paused run may still be on a surface a person is operating, and a stopped run must not be able to
act even if a queued call is already past its approval. Every transition that changes who may act increments
``generation``; an action captures a ``Ticket`` when it starts and must re-check it immediately before it dispatches, so
a call that was already in flight when a person took over (or stop was requested) cannot land afterwards.

The lease holds no I/O; the tool wires it to the surface and to run events.
"""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


class ControlOwner(str, enum.Enum):
    agent = "agent"                          # Hutch may act, subject to approvals
    human = "human"                          # a person is operating the surface; Hutch must not act
    paused = "paused"                        # nobody is acting; Hutch will not until resumed
    stopping = "stopping"                    # stop requested; cleanup in progress
    stopped = "stopped"                      # cleanup verified; nothing can act
    recovery_required = "recovery_required"  # cleanup could not be verified; a person must reconcile


class StaleControl(Exception):
    """The action's authority is gone: control changed hands, was paused, or the session is stopping/stopped."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Ticket:
    generation: int
    session_id: str


@dataclass(frozen=True)
class Snapshot:
    session_id: str
    owner: ControlOwner
    generation: int
    reason: str
    since_monotonic: float
    fresh_observation_required: bool
    last_frame_id: str

    def public(self) -> dict:
        return {"session_id": self.session_id, "owner": self.owner.value, "generation": self.generation, "reason": self.reason,
                "fresh_observation_required": self.fresh_observation_required, "last_frame_id": self.last_frame_id}


class ControlLease:
    """Thread-safe control state for one surface session."""

    def __init__(self, session_id: str, *, on_change: Optional[Callable[[Snapshot], None]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.session_id = session_id
        self._lock = threading.Lock()
        self._clock = clock
        self._on_change = on_change
        self._owner = ControlOwner.agent
        self._generation = 1
        self._reason = "session started"
        self._since = clock()
        self._fresh_required = True          # nothing has been observed yet
        self._last_frame = ""

    # ------------------------------------------------------------- reading

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> Snapshot:
        return Snapshot(self.session_id, self._owner, self._generation, self._reason, self._since,
                        self._fresh_required, self._last_frame)

    # ----------------------------------------------------------- transitions

    def _move(self, owner: ControlOwner, reason: str, *, fence: bool = True) -> Snapshot:
        with self._lock:
            # The caller's precheck and mutation must not straddle a stop. Validate again atomically here.
            terminal = (ControlOwner.stopping, ControlOwner.stopped, ControlOwner.recovery_required)
            if owner in (ControlOwner.agent, ControlOwner.human, ControlOwner.paused) and self._owner in terminal:
                raise StaleControl(f"the session is {self._owner.value}; control cannot be resumed or taken")
            if owner is ControlOwner.stopping and self._owner in (ControlOwner.stopped, ControlOwner.recovery_required):
                return self._snapshot_locked()
            self._owner = owner
            self._reason = reason
            self._since = self._clock()
            if fence:
                self._generation += 1
                self._fresh_required = True
            snap = self._snapshot_locked()
        if self._on_change is not None:
            try:
                self._on_change(snap)
            except Exception:
                pass                          # observers never alter ownership
        return snap

    def take_over(self, reason: str = "a person took control") -> Snapshot:
        """A person operates the surface. Anything in flight for the previous generation is now stale."""
        with self._lock:
            if self._owner in (ControlOwner.stopping, ControlOwner.stopped, ControlOwner.recovery_required):
                raise StaleControl(f"the session is {self._owner.value}; control cannot be taken")
        return self._move(ControlOwner.human, reason)

    def hand_back(self, reason: str = "the person handed control back") -> Snapshot:
        """Return control to Hutch. A new generation starts and a fresh observation is required before coordinate input."""
        with self._lock:
            if self._owner in (ControlOwner.stopping, ControlOwner.stopped, ControlOwner.recovery_required):
                raise StaleControl(f"the session is {self._owner.value}; it cannot be resumed")
            self._fresh_required = True
        return self._move(ControlOwner.agent, reason)

    def pause(self, reason: str = "paused") -> Snapshot:
        with self._lock:
            if self._owner in (ControlOwner.stopping, ControlOwner.stopped, ControlOwner.recovery_required):
                return self._snapshot_locked()
        return self._move(ControlOwner.paused, reason)

    def request_stop(self, reason: str = "stop requested") -> Snapshot:
        """Fence everything immediately; cleanup is confirmed separately by ``confirm_stopped``."""
        with self._lock:
            if self._owner in (ControlOwner.stopped, ControlOwner.recovery_required):
                return self._snapshot_locked()
        return self._move(ControlOwner.stopping, reason)

    def confirm_stopped(self, survivors: int = 0) -> Snapshot:
        """Cleanup finished. ``survivors`` > 0 means something the session started may still be alive."""
        if survivors:
            return self._move(ControlOwner.recovery_required,
                              f"{survivors} process(es) could not be confirmed ended", fence=False)
        return self._move(ControlOwner.stopped, "stopped and cleanup verified", fence=False)

    # ------------------------------------------------------------ observation

    def note_observation(self, frame_id: str) -> None:
        """A fresh observation was delivered; coordinate input may rely on it until something invalidates it."""
        with self._lock:
            self._last_frame = frame_id
            self._fresh_required = False

    def invalidate_observation(self, reason: str = "the surface changed") -> None:
        with self._lock:
            self._fresh_required = True
            self._reason = reason if self._owner is ControlOwner.agent else self._reason

    # ----------------------------------------------------------------- acting

    def begin_action(self, *, needs_fresh_observation: bool = False) -> Ticket:
        """Capture the authority an action starts with. Raises ``StaleControl`` if the agent may not act now."""
        with self._lock:
            if self._owner is not ControlOwner.agent:
                raise StaleControl(self._why_not_locked())
            if needs_fresh_observation and self._fresh_required:
                raise StaleControl("the surface changed since the last observation; observe again before using "
                                   "coordinates")
            return Ticket(self._generation, self.session_id)

    def check(self, ticket: Ticket, *, needs_fresh_observation: bool = False) -> None:
        """Call immediately before dispatching input. Raises ``StaleControl`` if the ticket no longer authorizes it."""
        with self._lock:
            if ticket.session_id != self.session_id or ticket.generation != self._generation:
                raise StaleControl(f"control changed while the action was waiting ({self._owner.value}); the action "
                                   "was not dispatched")
            if self._owner is not ControlOwner.agent:
                raise StaleControl(self._why_not_locked())
            if needs_fresh_observation and self._fresh_required:
                raise StaleControl("the surface changed after the observation this action was based on")

    def _why_not_locked(self) -> str:
        return {
            ControlOwner.human: "a person is controlling this surface; Hutch will not act until control is handed back",
            ControlOwner.paused: "this session is paused; Hutch will not act until it is resumed",
            ControlOwner.stopping: "this session is being stopped; no further action will run",
            ControlOwner.stopped: "this session was stopped; no further action will run",
            ControlOwner.recovery_required: ("this session stopped but cleanup could not be verified; a person must "
                                             "reconcile it before any further action"),
        }.get(self._owner, "the agent does not currently hold control")
