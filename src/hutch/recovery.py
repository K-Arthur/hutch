"""Bounded reconciliation for runs whose owner process cannot be verified.

A recovery attempt fences the run, ends its recorded processes and only then decides an outcome. Some process
identities cannot be verified at all (a pid reused by an unrelated program, a pgid that now matches any live
group, or a row from before boot ids). Those must not keep a run "Stopping" forever: the first attempt defers
with a short lease so another supervisor beat can retry, and when the retry still cannot verify the processes
Hutch closes the process records and settles the run as outcome_unknown instead of claiming it is working.
"""

from __future__ import annotations

from typing import Optional

from . import procguard
from .models import Event, EventType, Run, RunStatus

CLEANUP_MARK = "cleanup-pending:"
#: Returned when the first unverifiable cleanup was deferred; the caller must stop, not settle the run.
DEFERRED = object()


def settle_unverifiable_cleanup(store, run: Run, owned: Run, left: list) -> Optional[Run]:
    """Defer the first unverifiable cleanup; settle the retry so a ghost cannot stay live forever.

    Returns the settled run, `DEFERRED` when this attempt kept the run stopping/recovering for a retry, or
    None when there is nothing left to clean up and the caller should keep the normal recovery path.
    """
    if not left:
        return None
    detail = f"cleanup incomplete: still running or unverified: {procguard.describe(left)}"
    if not (run.lease_owner or "").startswith(CLEANUP_MARK):
        store.defer_recovery(owned, detail)
        store.append_event(Event(run_id=run.id, type=EventType.error,
                                 data={"error": detail, "kind": "cleanup_incomplete",
                                       "pids": [p.pid for p in left]}))
        store.flush_events()
        return DEFERRED
    from .store import IllegalTransition, LeaseLost
    store.close_procs(run.id)
    error = ("process cleanup could not be verified after repeated attempts; the run is marked outcome "
             "unknown and no longer claims to be working: " + procguard.describe(left))
    try:
        return store.transition_run(run.id, RunStatus.outcome_unknown, fence=owned.fence,
                                    exit_reason="interrupted", error=error,
                                    event={"reason": "interrupted", "error": error})
    except (IllegalTransition, LeaseLost, KeyError):
        return None
