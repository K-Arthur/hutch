"""MediaJobService: the honest state machine over ``store.create_media_job`` /
``record_upstream_job`` / ``transition_media_job``.

Status vocabulary. The v54 ``media_jobs.status`` CHECK allows exactly
``queued|running|succeeded|failed|cancelled``, so the service maintains its own
caller-facing vocabulary on top and maps it honestly:

=========================================  =========================================
service status                             store representation
=========================================  =========================================
``submitting``                             ``queued`` (no upstream id yet: not accepted)
``running``                                ``running``
``succeeded``                              ``succeeded`` (+ ``result`` payload)
``failed``                                 ``failed`` (+ ``error``)
``cancelled``                              ``cancelled`` (backend confirmed)
``cancel_unconfirmed``                     ``failed`` + ``error`` starting
                                           ``cancel_unconfirmed:`` + cost note
=========================================  =========================================

``cancel_unconfirmed`` is a REAL, reportable state, never silently rewritten to
``cancelled``: the backend did not confirm the cancellation, so the upstream job
may still be running and billing. The store row is marked ``failed`` (of the five
enumerated store states it is the only honest terminal choice — the job did not
succeed and was not confirmed cancelled) and the error/cost note carry the truth;
:func:`MediaJobService.service_status` restores the precise state for callers.

Billing discipline (failure class A.2 in ``docs/research/outputs-failures-2026-10-10.md``):

* ``submit()`` is the ONLY path that calls a billable backend. A retried submit
  with the same idempotency key and the same canonical request returns the
  EXISTING job without touching the backend. The same key with a different
  request is refused loudly. There is deliberately NO generic retry anywhere in
  this module — a crashed submit leaves a row that reconciliation describes
  honestly instead of replaying the spend.
* ``record_upstream_job`` happens IMMEDIATELY after backend accept, so a crash
  later still leaves enough evidence to reconcile against the upstream job.
* ``finalize()`` consumes expiring result URLs immediately and stores only the
  validated BYTES — never the URL.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Iterable, Optional

from ..store import IdempotencyConflict, Store
from . import validate as media_validate
from .providers.base import MediaBackend
from .storage import (MAX_MEDIA_BYTES, MediaStorage, MediaStorageError,
                      new_job_id, new_media_id)

#: kinds a media job may request (media-block payload kinds)
MEDIA_KINDS = ("image", "video", "animation", "audio")

#: service-level terminal statuses
TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")

_CANCEL_UNCONFIRMED_PREFIX = "cancel_unconfirmed:"
_ORPHAN_SUBMITTING_PREFIX = "orphaned_submitting:"
_ORPHAN_RUNNING_PREFIX = "orphaned_running:"

#: which sniffed formats are coherent with which requested kind — a backend that
#: delivers the wrong kind of bytes gets a loud mismatch, not an incoherent block
_KIND_FORMATS = {
    "image": frozenset({"png", "jpeg", "webp", "svg+xml"}),
    "animation": frozenset({"png", "jpeg", "webp", "svg+xml"}),
    "video": frozenset({"webm", "mp4"}),
    "audio": frozenset({"wav"}),
}


class MediaJobError(ValueError):
    """A media job request could not be honoured honestly."""


class MediaUnavailableError(MediaJobError):
    """No configured backend is capable of this kind. Reported, never substituted."""


def service_status(row: dict[str, Any]) -> str:
    """The service-level status of a stored job row (see module docstring)."""
    status = row.get("status")
    error = row.get("error") or ""
    if status == "queued":
        return "submitting"
    if status == "failed" and error.startswith(_CANCEL_UNCONFIRMED_PREFIX):
        return "cancel_unconfirmed"
    return str(status)


def _canonical_requested(kind: str, prompt: str, *, backend_hint: Optional[str],
                         width: Optional[int], height: Optional[int],
                         seconds: Optional[float], extra: Optional[dict]) -> dict[str, Any]:
    requested: dict[str, Any] = {"kind": kind, "prompt": prompt}
    if backend_hint:
        requested["backend_hint"] = backend_hint
    if width is not None:
        requested["width"] = width
    if height is not None:
        requested["height"] = height
    if seconds is not None:
        requested["seconds"] = seconds
    if extra:
        requested.update(extra)
    return requested


class MediaJobService:
    """Owns media job transactions: the store row, the upstream adapter calls,
    and the media-store commit. Deterministic (local) media goes through
    :meth:`record_local`; provider media goes through :meth:`submit` /
    :meth:`poll` / :meth:`cancel` / :meth:`finalize`."""

    def __init__(self, store: Store, media_store: MediaStorage,
                 backends: Optional[dict[str, MediaBackend]] = None):
        self.store = store
        self.media_store = media_store
        self.backends: dict[str, MediaBackend] = dict(backends or {})
        self._active: set[str] = set()      # job ids THIS instance is driving
        self._lock = threading.Lock()

    # ------------------------------------------------------------- lookups

    def status(self, job_id: str) -> Optional[dict[str, Any]]:
        row = self.store.get_media_job(job_id)
        if row is None:
            return None
        row = dict(row)
        row["service_status"] = service_status(row)
        return row

    def _find_by_key(self, run_id: str, idempotency_key: str) -> Optional[dict[str, Any]]:
        for row in self.store.media_jobs_for_run(run_id, limit=200):
            if row.get("idempotency_key") == idempotency_key:
                return row
        return None

    def backend_for(self, kind: str, backend_hint: Optional[str] = None) -> MediaBackend:
        """Pick a capable backend. A hint names a specific backend; without one the
        alphabetically-first capable backend wins (deterministic). None capable →
        :class:`MediaUnavailableError` — honest absence, never a substitute."""
        if kind not in MEDIA_KINDS:
            raise MediaJobError(f"unknown media kind {kind!r}; known: {', '.join(MEDIA_KINDS)}")
        if backend_hint:
            backend = self.backends.get(backend_hint)
            if backend is None:
                raise MediaUnavailableError(
                    f"backend {backend_hint!r} is not configured; configured backends: "
                    f"{', '.join(sorted(self.backends)) or 'none'}")
            if kind not in backend.capabilities().get("kinds", []):
                raise MediaUnavailableError(
                    f"backend {backend_hint!r} does not list kind {kind!r}")
            return backend
        for name in sorted(self.backends):
            backend = self.backends[name]
            if kind in backend.capabilities().get("kinds", []):
                return backend
        raise MediaUnavailableError(
            f"no configured backend can produce {kind!r} media; hutch does not "
            "substitute stock assets or fabricate previews")

    # ------------------------------------------------------------- validation

    @staticmethod
    def _validate_request(kind: str, prompt: str, width: Optional[int],
                          height: Optional[int], seconds: Optional[float]) -> None:
        if kind not in MEDIA_KINDS:
            raise MediaJobError(f"unknown media kind {kind!r}; known: {', '.join(MEDIA_KINDS)}")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            raise MediaJobError("a media job requires a non-empty prompt of at most 4000 characters")
        for name, value in (("width", width), ("height", height)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                      or not 16 <= value <= 8192):
                raise MediaJobError(f"{name} must be an integer 16–8192")
        if seconds is not None and (isinstance(seconds, bool)
                                    or not isinstance(seconds, (int, float))
                                    or not 0.1 <= float(seconds) <= 600.0):
            raise MediaJobError("seconds must be a number 0.1–600")

    # ------------------------------------------------------------- submit

    def submit(self, *, run_id: str, conversation_id: str, kind: str, prompt: str,
               idempotency_key: str, backend_hint: Optional[str] = None,
               width: Optional[int] = None, height: Optional[int] = None,
               seconds: Optional[float] = None,
               requested_extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Validate, persist a ``submitting`` job, then hand it to the backend.

        Duplicate idempotency key + identical canonical request → the existing job
        is returned WITHOUT calling the backend (no second billing). The same key
        with a different request raises :class:`MediaJobError`.
        """
        self._validate_request(kind, prompt, width, height, seconds)
        if not idempotency_key or not isinstance(idempotency_key, str):
            raise MediaJobError("a media job requires a non-empty idempotency_key")
        backend = self.backend_for(kind, backend_hint)
        requested = _canonical_requested(kind, prompt.strip(), backend_hint=backend_hint,
                                         width=width, height=height, seconds=seconds,
                                         extra=requested_extra)
        try:
            row = self.store.create_media_job(
                run_id=run_id, conversation_id=conversation_id, kind=kind,
                backend=backend.name, idempotency_key=idempotency_key,
                requested=requested)
        except IdempotencyConflict:
            existing = self._find_by_key(run_id, idempotency_key)
            if existing is not None and existing.get("requested") == requested \
                    and existing.get("backend") == backend.name:
                return existing      # honest dedup: the upstream charge already happened once
            raise MediaJobError(
                f"idempotency_key {idempotency_key!r} was already used for a different "
                "media job; reuse it only for an identical retried request") from None
        job_id = row["id"]
        with self._lock:
            self._active.add(job_id)
        try:
            try:
                upstream_id = backend.submit(dict(requested))
                if not isinstance(upstream_id, str) or not upstream_id.strip():
                    raise MediaJobError("the backend accepted the request but returned no "
                                        "upstream job id")
            except Exception as exc:
                return self.store.transition_media_job(
                    job_id, "failed",
                    error=f"upstream submit failed: {exc}",
                    cost_note="no upstream job was accepted, so no provider charge "
                              "should exist — verify against the backend account")
            # IMMEDIATELY after accept: from here on, reconciliation has evidence.
            self.store.record_upstream_job(job_id, upstream_id)
            return self.store.transition_media_job(job_id, "running")
        finally:
            row_now = self.store.get_media_job(job_id)
            if row_now is None or row_now["status"] in TERMINAL_STATUSES:
                with self._lock:
                    self._active.discard(job_id)

    # ------------------------------------------------------------- poll

    def poll(self, job_id: str, backend: Optional[MediaBackend] = None) -> dict[str, Any]:
        """One observation of an in-flight job; terminal upstream states are
        recorded honestly. Success alone does NOT finalize — the bytes are only
        fetched in :meth:`finalize`."""
        row = self.store.get_media_job(job_id)
        if row is None:
            raise KeyError(f"no such media job: {job_id}")
        if row["status"] not in ("queued", "running"):
            return row
        backend = backend or self.backends.get(str(row["backend"]))
        if backend is None:
            return row      # nothing to observe with: unchanged, honestly
        state = backend.poll(row)
        upstream_status = str(state.get("status", "running"))
        if upstream_status == "failed":
            return self.store.transition_media_job(
                job_id, "failed", error=str(state.get("error") or "the upstream job failed"),
                cost_note="the upstream job failed; whether the provider charged for the "
                          "attempt depends on the backend account")
        if upstream_status == "cancelled":
            return self.store.transition_media_job(
                job_id, "cancelled",
                cost_note="the upstream job reported itself cancelled")
        return self.store.get_media_job(job_id) or row

    # ------------------------------------------------------------- cancel

    def cancel(self, job_id: str, backend: Optional[MediaBackend] = None, *,
               wait_seconds: float = 5.0) -> dict[str, Any]:
        """Request cancellation and record the outcome HONESTLY.

        Backend confirmed → ``cancelled``. No confirmation after a bounded wait →
        service status ``cancel_unconfirmed`` (store row failed with a
        ``cancel_unconfirmed:`` error and a cost note): the upstream job may still
        be running and billing, and this state says so.
        """
        row = self.store.get_media_job(job_id)
        if row is None:
            raise KeyError(f"no such media job: {job_id}")
        if row["status"] not in ("queued", "running"):
            return row
        backend = backend or self.backends.get(str(row["backend"]))
        if backend is None:
            raise MediaJobError(
                f"no backend is configured for {row['backend']!r}; the cancellation "
                "cannot be requested or confirmed")
        confirmation = backend.cancel(row)
        if confirmation:
            return self.store.transition_media_job(
                job_id, "cancelled", result={"cancelled_by": "request",
                                             "confirmation": confirmation},
                cost_note="the backend acknowledged the cancellation request")
        # Bounded wait: re-observe a few times before declaring it unconfirmed.
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while time.monotonic() < deadline:
            time.sleep(min(0.5, max(0.05, wait_seconds / 3)))
            state = backend.poll(row)
            observed = str(state.get("status", "running"))
            if observed == "cancelled":
                return self.store.transition_media_job(
                    job_id, "cancelled",
                    cost_note="the backend confirmed the cancellation via poll")
            if observed == "failed":
                return self.store.transition_media_job(
                    job_id, "failed", error=str(state.get("error") or "the upstream job failed"),
                    cost_note="the job failed before the cancellation took effect")
            if observed == "succeeded":
                return self._mark_upstream_succeeded_unfetched(
                    row, "the job completed upstream before the cancellation took effect")
        return self.store.transition_media_job(
            job_id, "failed",
            error=(f"{_CANCEL_UNCONFIRMED_PREFIX} the backend did not confirm the "
                   f"cancellation within {wait_seconds:g}s; the upstream job "
                   f"({row.get('upstream_job_id') or 'id unknown'}) may still be "
                   "running and billing"),
            cost_note=("outcome unknown: treat this job as possibly-billed and verify "
                       "with the backend; it is deliberately NOT recorded as cancelled"))

    # ------------------------------------------------------------- finalize

    def finalize(self, job_id: str, *, alt_text: str,
                 backend: Optional[MediaBackend] = None,
                 poster_bytes: Optional[bytes] = None,
                 poster_format: str = "png",
                 duration_seconds: Optional[float] = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch the finished bytes, validate them, store them, and close the job
        with the media-block payload as its ``result``.

        The fetch happens HERE and now — expiring URLs are consumed immediately
        and only the validated bytes are stored, never the URL. The commit
        protocol's SQLite step is this service's own transaction: the store row
        transitions to ``succeeded`` carrying the payload.
        """
        row = self.store.get_media_job(job_id)
        if row is None:
            raise KeyError(f"no such media job: {job_id}")
        if row["status"] != "running":
            raise MediaJobError(
                f"job {job_id} is {row['status']!r}; only a running job with a "
                "finished upstream result can be finalized")
        backend = backend or self.backends.get(str(row["backend"]))
        if backend is None:
            raise MediaJobError(f"no backend is configured for {row['backend']!r}")
        if not isinstance(alt_text, str) or not alt_text.strip() or len(alt_text.strip()) > 600:
            raise MediaJobError("alt_text is required (1–600 characters, readable)")
        alt_text = alt_text.strip()
        kind = str(row["kind"])
        try:
            raw = backend.fetch(row)
        except Exception as exc:
            return self._fail(job_id, f"the result could not be fetched: {exc}",
                              "the fetch failed after the upstream job was accepted; "
                              "the charge may stand — verify with the backend")
        if not isinstance(raw, (bytes, bytearray)):
            return self._fail(job_id, "protocol violation: the backend's fetch returned "
                              f"{type(raw).__name__} instead of bytes; a URL is never a "
                              "result", "nothing was stored from this fetch")
        try:
            validated = media_validate.validate_media(raw, max_bytes=MAX_MEDIA_BYTES)
        except media_validate.MediaValidationError as exc:
            return self._fail(job_id, f"the result failed validation: {exc}",
                              "no bytes were stored; the provider charge may stand")
        if validated.format not in _KIND_FORMATS.get(kind, frozenset()):
            return self._fail(
                job_id,
                f"the backend delivered {validated.format} for a {kind!r} request; the "
                "mismatch is refused, not papered over",
                "no bytes were stored; the provider charge may stand")
        media_id = new_media_id()
        try:
            staged = self.media_store.stage_bytes(new_job_id(), validated.format,
                                                  "media", validated.scrubbed)
            staged_poster = None
            if poster_bytes is not None:
                if poster_format not in media_validate.MEDIA_FORMATS:
                    raise MediaJobError(f"unsupported poster format {poster_format!r}")
                staged_poster = self.media_store.stage_bytes(
                    staged.job_id, poster_format, "poster", bytes(poster_bytes))
        except (MediaStorageError, MediaJobError) as exc:
            return self._fail(job_id, f"the result could not be staged: {exc}",
                              "no bytes were stored; the provider charge may stand")
        payload: dict[str, Any] = {
            "media_id": media_id,
            "version": 1,
            "sha256": staged.sha256,
            "mime": validated.mime,
            "kind": kind,
            "alt_text": alt_text,
            "backend": str(row["backend"]),
            "generated_by": "deterministic" if str(row["backend"]) == "deterministic" else "provider",
        }
        if validated.width and validated.height:
            payload["width"] = int(validated.width)
            payload["height"] = int(validated.height)
        if duration_seconds is not None and float(duration_seconds) >= 0:
            payload["duration_seconds"] = float(duration_seconds)
        meta = {"kind": kind, "backend": payload["backend"],
                "generated_by": payload["generated_by"], "alt_text": alt_text}
        if validated.width and validated.height:
            meta["width"], meta["height"] = payload["width"], payload["height"]
        if duration_seconds is not None:
            meta["duration_seconds"] = payload["duration_seconds"]

        def insert_row() -> None:
            self.store.transition_media_job(
                job_id, "succeeded", result=payload,
                cost_note=("provider media generation is billable; hutch cannot verify "
                           "the exact charge — check the backend account")
                if payload["generated_by"] == "provider" else None)
        try:
            self.media_store.commit(staged, media_id, 1, meta=meta,
                                    poster=staged_poster, insert_row=insert_row)
        except Exception as exc:
            self.media_store.remove_version(media_id, self.media_store.version_dir_name(1, staged.sha256))
            return self._fail(job_id, f"the result could not be committed: {exc}",
                              "the bytes were validated but never recorded; the provider "
                              "charge may stand")
        final = self.store.get_media_job(job_id) or {}
        return payload, final

    def _fail(self, job_id: str, error: str, cost_note: str) -> dict[str, Any]:
        try:
            return self.store.transition_media_job(job_id, "failed",
                                                   error=error[:2000], cost_note=cost_note)
        except ValueError:
            # Already terminal (a concurrent writer got there first): report the row.
            return self.store.get_media_job(job_id) or {"id": job_id, "status": "failed"}

    # ------------------------------------------------------------- deterministic (local)

    def record_local(self, *, run_id: str, conversation_id: str, kind: str,
                     requested: dict[str, Any], idempotency_key: str,
                     produce: Callable[[], tuple[bytes, dict[str, Any]]]) -> dict[str, Any]:
        """Run deterministic media (no backend, no approval, no billing): create the
        ledger row, call ``produce()`` for (bytes, meta), validate, store, and mark
        the row ``succeeded`` carrying the payload. On failure the row is marked
        ``failed`` with the renderer's error — the source stays with the caller.

        ``meta`` keys: ``format`` (required), ``alt_text`` (required), plus optional
        ``width``/``height``/``duration_seconds``. A retried call with the same key
        and the same canonical request returns the existing row without re-rendering.
        """
        if kind not in MEDIA_KINDS:
            raise MediaJobError(f"unknown media kind {kind!r}; known: {', '.join(MEDIA_KINDS)}")
        if not isinstance(requested, dict):
            raise MediaJobError("requested must be a JSON object")
        canonical = dict(requested)
        canonical.setdefault("kind", kind)
        try:
            row = self.store.create_media_job(
                run_id=run_id, conversation_id=conversation_id, kind=kind,
                backend="deterministic", idempotency_key=idempotency_key,
                requested=canonical)
        except IdempotencyConflict:
            existing = self._find_by_key(run_id, idempotency_key)
            if existing is not None and existing.get("requested") == canonical:
                return existing
            raise MediaJobError(
                f"idempotency_key {idempotency_key!r} was already used for a different "
                "media job") from None
        job_id = row["id"]
        try:
            self.store.transition_media_job(job_id, "running")   # queued→running is the store's guard
            data, meta = produce()
            fmt = str(meta.get("format") or "")
            alt_text = str(meta.get("alt_text") or "").strip()
            if not alt_text or len(alt_text) > 600:
                raise MediaJobError("deterministic media requires alt_text (1–600 characters)")
            validated = media_validate.validate_media(data, expected_format=fmt or None,
                                                      max_bytes=MAX_MEDIA_BYTES)
            if validated.format not in _KIND_FORMATS.get(kind, frozenset()):
                raise MediaJobError(
                    f"the renderer produced {validated.format} for a {kind!r} job")
            media_id = new_media_id()
            staged = self.media_store.stage_bytes(new_job_id(), validated.format,
                                                  "media", validated.scrubbed)
            payload: dict[str, Any] = {
                "media_id": media_id, "version": 1, "sha256": staged.sha256,
                "mime": validated.mime, "kind": kind, "alt_text": alt_text,
                "backend": "deterministic", "generated_by": "deterministic",
            }
            meta_extra: dict[str, Any] = {"kind": kind, "alt_text": alt_text,
                                          "backend": "deterministic",
                                          "generated_by": "deterministic"}
            if validated.width and validated.height:
                payload["width"] = int(validated.width)
                payload["height"] = int(validated.height)
                meta_extra["width"], meta_extra["height"] = payload["width"], payload["height"]
            duration = meta.get("duration_seconds")
            if isinstance(duration, (int, float)) and float(duration) >= 0:
                payload["duration_seconds"] = float(duration)
                meta_extra["duration_seconds"] = payload["duration_seconds"]

            def insert_row() -> None:
                self.store.transition_media_job(job_id, "succeeded", result=payload)
            self.media_store.commit(staged, media_id, 1, meta=meta_extra, insert_row=insert_row)
        except Exception as exc:
            return self._fail(job_id, f"deterministic render failed: {exc}",
                              "nothing was stored and nothing was billed")
        return self.store.get_media_job(job_id) or {}

    # ------------------------------------------------------------- reconcile

    def reconcile(self, *, run_ids: Iterable[str],
                  backends: Optional[dict[str, MediaBackend]] = None,
                  max_jobs_per_run: int = 200) -> dict[str, Any]:
        """Startup honesty pass: every non-terminal job from a previous process is
        orphaned (its driver is gone). Resolve each against the best available
        truth, in this order:

        * backend reachable + upstream id → one poll: record the observed terminal
          state. An upstream SUCCESS is recorded as ``succeeded`` with
          ``result.bytes == "not_fetched"`` — the work happened and may be billed,
          and the record says the bytes were never stored.
        * backend unreachable / no upstream id → the row is marked ``failed`` with
          an ``orphaned_submitting:``/``orphaned_running:`` error and a cost note
          telling the reader to check the backend before re-submitting.

        Jobs this live instance is currently driving (``self._active``) are never
        touched. There is no re-submission here — that would double-spend.
        """
        registry = dict(backends) if backends is not None else dict(self.backends)
        summary: dict[str, Any] = {"examined": 0, "marked_orphaned": 0, "resolved": 0,
                                   "still_running": 0, "skipped_active": 0, "jobs": []}
        with self._lock:
            active = set(self._active)
        for run_id in run_ids:
            for row in self.store.media_jobs_for_run(run_id, limit=max_jobs_per_run):
                summary["examined"] += 1
                if row["status"] not in ("queued", "running"):
                    continue
                if row["id"] in active:
                    summary["skipped_active"] += 1
                    continue
                backend = registry.get(str(row["backend"]))
                upstream_id = row.get("upstream_job_id")
                if backend is not None and upstream_id:
                    state = backend.poll(row)
                    observed = str(state.get("status", "running"))
                    if observed == "cancelled":
                        self.store.transition_media_job(
                            row["id"], "cancelled",
                            cost_note="reconcile: the upstream job reported itself cancelled")
                        summary["resolved"] += 1
                        summary["jobs"].append({"id": row["id"], "resolution": "cancelled"})
                        continue
                    if observed == "failed":
                        self.store.transition_media_job(
                            row["id"], "failed",
                            error=str(state.get("error") or "the upstream job failed"),
                            cost_note="reconcile: the upstream job failed; the charge, if "
                                      "any, depends on the backend account")
                        summary["resolved"] += 1
                        summary["jobs"].append({"id": row["id"], "resolution": "failed"})
                        continue
                    if observed == "succeeded":
                        self._mark_upstream_succeeded_unfetched(row, "reconcile")
                        summary["resolved"] += 1
                        summary["jobs"].append({"id": row["id"],
                                                "resolution": "upstream_succeeded_bytes_unfetched"})
                        continue
                    summary["still_running"] += 1
                    summary["jobs"].append({"id": row["id"], "resolution": "still_running_upstream"})
                    continue
                submitting = row["status"] == "queued"
                prefix = _ORPHAN_SUBMITTING_PREFIX if submitting else _ORPHAN_RUNNING_PREFIX
                detail = (
                    "hutch restarted while the job was submitting; whether the backend "
                    "accepted it is unknown" if submitting else
                    "the backend for this job is not reachable from this process")
                self.store.transition_media_job(
                    row["id"], "failed",
                    error=(f"{prefix} {detail}; upstream job "
                           f"{upstream_id or 'unknown'}, backend {row['backend']!r}"),
                    cost_note=("outcome unknown: the upstream work may have started and "
                               "may be billable — check the backend account before "
                               "re-submitting (the idempotency key still protects "
                               "against a double spend)"))
                summary["marked_orphaned"] += 1
                summary["jobs"].append({"id": row["id"],
                                        "resolution": "orphaned_submitting" if submitting
                                        else "orphaned_running"})
        return summary

    def _mark_upstream_succeeded_unfetched(self, row: dict[str, Any], note: str) -> dict[str, Any]:
        return self.store.transition_media_job(
            row["id"], "succeeded",
            result={"state": "upstream_succeeded", "bytes": "not_fetched",
                    "upstream_job_id": row.get("upstream_job_id"),
                    "note": "the upstream job completed but the result bytes were never "
                            "fetched; no media block can be built from this row"},
            cost_note=(f"{note}: the upstream work completed and may be billed, but hutch "
                       "holds no bytes for it"))
