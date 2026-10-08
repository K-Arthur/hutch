"""The run lifecycle: ONE definition of which state may follow which (ADR-0003).

Status used to be assigned in scattered places from several threads and processes, so a late worker could overwrite a terminal
state and two writers could disagree. Now every change goes through ``Store.transition_run``, which consults ``TRANSITIONS`` and
applies the change in SQL together with the fence check and the status event.

Terminal states are absorbing: nothing leaves them. A recovered or finished run is never resumed in the middle; "continue" starts a
new run in the same conversation.
"""

from __future__ import annotations

from .models import ACTIVE_STATUSES, RunStatus

P = RunStatus

TERMINAL: frozenset[RunStatus] = frozenset({P.succeeded, P.failed, P.stopped, P.outcome_unknown, P.skipped})

#: active and owned by somebody (everything active except a queued run)
LIVE: frozenset[RunStatus] = frozenset(ACTIVE_STATUSES) - {P.pending}

_END = {P.failed, P.stopped, P.outcome_unknown}      # how any live run may be ended by recovery or a stop

TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    P.pending: frozenset({P.loading_model, P.running, P.waiting_resources, P.cancelling, P.stopped, P.failed, P.skipped,
                         P.outcome_unknown}),
    P.waiting_resources: frozenset({P.pending, P.loading_model, P.running, P.cancelling, P.recovering} | _END),
    P.loading_model: frozenset({P.running, P.waiting_resources, P.waiting_approval, P.cancelling, P.recovering} | _END),
    P.running: frozenset({P.loading_model, P.waiting_approval, P.waiting_human, P.waiting_resources, P.succeeded,
                          P.cancelling, P.recovering} | _END),
    P.waiting_approval: frozenset({P.running, P.loading_model, P.waiting_human, P.cancelling, P.recovering} | _END),
    P.waiting_human: frozenset({P.running, P.waiting_approval, P.cancelling, P.recovering} | _END),
    P.recovering: frozenset({P.cancelling} | _END),
    P.cancelling: frozenset({P.recovering} | _END),
    P.succeeded: frozenset(),
    P.failed: frozenset(),
    P.stopped: frozenset(),
    P.outcome_unknown: frozenset(),
    P.skipped: frozenset(),
}

#: what a person reads (the stored value is for machines)
LABELS: dict[RunStatus, str] = {
    P.pending: "Queued",
    P.loading_model: "Loading the model",
    P.running: "Working",
    P.waiting_approval: "Waiting for you",
    P.waiting_human: "Needs you",
    P.waiting_resources: "Waiting for a free slot or quota",
    P.recovering: "Recovering",
    P.cancelling: "Stopping",
    P.succeeded: "Done",
    P.failed: "Failed",
    P.stopped: "Cancelled",
    P.outcome_unknown: "Needs review",
    P.skipped: "Skipped",
}

#: states in which a person has something to do
NEEDS_PERSON: frozenset[RunStatus] = frozenset({P.waiting_approval, P.waiting_human, P.outcome_unknown})


class IllegalTransition(Exception):
    """The requested move is not in ``TRANSITIONS`` for the run's current state."""

    def __init__(self, run_id: str, frm: RunStatus, to: RunStatus):
        super().__init__(f"run {run_id}: {frm.value} -> {to.value} is not a legal transition")
        self.run_id, self.frm, self.to = run_id, frm, to


class LeaseLost(Exception):
    """The caller no longer owns this run (stale fence, or the run already finished). It must stop acting on it now."""

    def __init__(self, run_id: str, detail: str = "ownership of the run was lost"):
        super().__init__(f"run {run_id}: {detail}")
        self.run_id = run_id


def allowed(frm: RunStatus, to: RunStatus) -> bool:
    return to in TRANSITIONS[frm]


def is_terminal(status: RunStatus) -> bool:
    return status in TERMINAL
