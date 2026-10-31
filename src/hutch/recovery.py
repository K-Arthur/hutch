"""Bounded reconciliation for runs whose owner process cannot be verified.

A recovery attempt fences the run, ends its recorded processes and only then decides an outcome. Some process
identities can never be verified (the recorded leader pid was reused by an unrelated program, or the record
carries no identity). Those must not keep a run "Stopping" forever: the first attempt defers with a short lease
so another supervisor beat can retry, and when the retry still finds only unverifiable survivors Hutch closes
the process records and settles the run as outcome_unknown instead of claiming it is working.

Two cases always keep deferring, because settling would abandon something real. A survivor known to be alive
(it outlived the signals) keeps its run stopping, and so does a host where process inspection is not available
at all: there nothing can be verified, so nothing may be declared gone.
"""

from __future__ import annotations

from typing import Optional

from . import procguard
from .models import Event, EventType, Run, RunStatus

CLEANUP_MARK = "cleanup-pending:"
#: Returned when the first unverifiable cleanup was deferred; the caller must stop, not settle the run.
DEFERRED = object()


def _only_unverifiable(left: list) -> bool:
    """True when nothing left is known to be alive and the host can inspect processes at all."""
    return procguard.available() and all(p.state == "?" for p in left)


def settle_unverifiable_cleanup(store, run: Run, owned: Run, left: list) -> Optional[Run]:
    """Defer the first unverifiable cleanup; settle a retry that still finds only unverifiable survivors.

    Returns the settled run, `DEFERRED` when this attempt kept the run stopping/recovering for a retry, or
    None when there is nothing left to clean up and the caller should keep the normal recovery path.
    """
    if not left:
        return None
    detail = f"cleanup incomplete: still running or unverified: {procguard.describe(left)}"
    if not (run.lease_owner or "").startswith(CLEANUP_MARK) or not _only_unverifiable(left):
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


def unclosed_proc_runs(store, limit: int = 256) -> list[str]:
    """Runs that still hold unreaped process rows, whatever their status.

    A supervisor killed mid-run never executes its own cleanup, so a run can reach a terminal status while its `run_procs` rows
    stay open. Those rows keep occupying a capacity slot and make the bot look busy forever, and because the run is terminal the
    normal orphan scan does not see it. The caller decides whether the pids are really gone before freeing anything.
    """
    with store._lock:
        rows = store._db.execute("SELECT DISTINCT run_id FROM run_procs WHERE ended_at IS NULL AND detached_at IS NULL LIMIT ?",
                                 (int(limit),)).fetchall()
    return [row["run_id"] for row in rows]


def release_settled_process_rows(store, threads, pid_alive) -> None:
    """Free capacity held by process rows whose processes are provably gone.

    A run whose supervising process was killed (SIGTERM, OOM, a closed terminal) can end terminal with `run_procs` rows still
    open; `claim_run` keeps counting the stale row as capacity, so every later run of that bot sits in `pending` for ever with no
    error. The safety rule that made those rows count still holds: a row is closed only when every recorded pid is dead, so a live
    descendant of an interrupted run keeps its slot, and a single live pid leaves the whole set alone.
    """
    from .models import ACTIVE_STATUSES
    for run_id in unclosed_proc_runs(store):
        if run_id in threads:
            continue
        procs = store.live_procs(run_id)
        if not procs or any(pid_alive(str(p.get("pid") or "")) for p in procs):
            continue
        status = getattr(store.get_run(run_id), "status", None)
        if status is not None and status in ACTIVE_STATUSES and status is not RunStatus.pending:
            continue          # still owned by an expired/orphan pass; let it settle the run
        try:
            store.close_procs(run_id)
        except Exception:  # noqa: BLE001 - reconciliation must never break a supervisor tick
            continue
