"""Advance, resume and cancel a media job outside the tool call that started it.

``create_media`` waits a bounded time for a job, then returns; a video that takes five minutes is
still running upstream, and the provider will bill for it whether or not anyone is watching. These
operations act on the ledger row, so they work after the run ended and after a restart:

* ``advance`` observes the job once; if the provider says it finished, it fetches and stores the
  result (the bytes are validated and hashed like any media) and records the usage row;
* ``cancel`` asks the provider to cancel and records what it acknowledged (``cancel_unconfirmed``
  when it did not).

Neither creates a new billable request; the job was approved when it was created. A job whose
backend is no longer configured (the key was removed) is reported as blocked, never guessed at.
"""

from __future__ import annotations

from typing import Any

from .cost import estimate
from .jobs import TERMINAL_STATUSES, MediaJobError, MediaJobService
from .ledger import describe
from .usage import measured_usage, record_media_usage


def default_alt_text(kind: str, prompt: str) -> str:
    if kind == "audio":
        return f"Speech: {prompt[:200]}"[:600]
    return f"Generated {kind} from the prompt: {prompt[:400]}"[:600]


def advance(service: MediaJobService, store: Any, job_id: str) -> dict[str, Any]:
    row = service.status(job_id)
    if row is None:
        raise KeyError(job_id)
    if row["status"] in TERMINAL_STATUSES:
        return {"action": "none", "note": "the job already finished", "job": describe(row)}
    backend = service.backends.get(str(row["backend"]))
    if backend is None:
        return _blocked(row)
    observed = backend.poll(row)
    row = service.poll(job_id, backend)
    if row["status"] != "running" or observed.get("status") != "succeeded":
        return {"action": "polled", "observed": {k: observed[k] for k in ("status", "note", "error")
                                                   if k in observed}, "job": describe(row)}
    return _finalize(service, store, backend, row)


def _blocked(row: dict[str, Any]) -> dict[str, Any]:
    return {"action": "blocked", "job": describe(row),
            "note": f"backend {row['backend']!r} is not configured on this machine (its key or "
                    "connection is gone), so the job can be neither observed nor finished; "
                    "restore the credential to resume it"}


def _finalize(service: MediaJobService, store: Any, backend: Any, row: dict[str, Any]) -> dict[str, Any]:
    requested = row.get("requested") or {}
    prompt = str(requested.get("prompt") or "")
    kind = str(row["kind"])
    probe = getattr(backend, "duration_seconds", None)
    duration = probe(row) if kind == "audio" and callable(probe) else None
    spoken = measured_usage(backend, kind, row)         # before finalize releases the held copy
    try:
        payload, final = service.finalize(row["id"], alt_text=default_alt_text(kind, prompt),
                                          duration_seconds=duration)
    except MediaJobError as exc:
        current = service.status(row["id"]) or row
        if current["status"] in TERMINAL_STATUSES:       # another request finished it first
            return {"action": "none", "note": "the job was finished by another request",
                    "job": describe(current)}
        return {"action": "failed", "note": str(exc), "job": describe(current)}
    if final.get("status") != "succeeded":
        return {"action": "failed", "note": str(final.get("error") or ""), "job": describe(final)}
    if not payload:
        # A concurrent finalizer stored the bytes and closed the row after our initial status
        # check. It also owns the usage record; this request must not count it a second time.
        return {"action": "none", "note": "the job was finished by another request",
                "job": describe(final)}
    note = _usage(store, backend, kind, row, requested, spoken)
    return {"action": "finalized", "note": note, "job": describe(final)}


def _usage(store: Any, backend: Any, kind: str, row: dict[str, Any], requested: dict[str, Any],
           spoken: Any) -> str:
    run = store.get_run(str(row["run_id"]))
    if run is None:
        return "usage was not recorded: the run that started this job no longer exists"
    price = getattr(getattr(backend, "route", None), "price", "")
    detail = {"cost_basis": estimate(price, requested).as_dict()}
    note, _, _ = record_media_usage(store, run_id=run.id, bot_id=run.bot_id, backend=backend,
                                    kind=kind, job=row, request=requested, detail=detail,
                                    spoken=spoken)
    return note


def cancel(service: MediaJobService, job_id: str, *, wait_seconds: float = 2.0) -> dict[str, Any]:
    row = service.status(job_id)
    if row is None:
        raise KeyError(job_id)
    if row["status"] in TERMINAL_STATUSES:
        return {"action": "none", "note": "the job already finished", "job": describe(row)}
    if service.backends.get(str(row["backend"])) is None:
        return _blocked(row)
    final = service.cancel(job_id, wait_seconds=wait_seconds)
    return {"action": "cancel", "job": describe(final)}
