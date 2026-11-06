"""The install job record and the pure folding of one pull event into it.

Kept apart from ``model_install`` so the registry/worker stays under the file cap and the
event arithmetic can be tested without a runtime. The job is plain data; ``_apply`` only
reads the runtime's counters and never invents progress.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import iso, utcnow
from .install_plan import InstallPlan

_MAX_STATUS_CHARS = 200


def _apply_plan(job: InstallJob, plan: InstallPlan) -> None:
    """Copy the preflight facts onto the job without turning an unknown into a zero."""
    job.size_bytes = plan.size_bytes
    job.size_source = plan.size_source
    job.model_dir = plan.model_dir
    job.model_dir_source = plan.model_dir_source
    job.free_bytes = plan.free_bytes
    job.reserve_bytes = plan.reserve_bytes
    job.fit_status = plan.fit_status
    job.fit_label = plan.fit_label
    job.fit_reason = plan.fit_reason
    job.fit_effective_ctx = plan.fit_effective_ctx
    job.fit_estimated = plan.fit_estimated
    job.planned_eta_seconds = plan.eta_seconds
    job.speed_bytes_per_s = plan.speed_bytes_per_s
    job.speed_measured_at = plan.speed_measured_at
    job.warnings = list(plan.warnings)


@dataclass
class InstallJob:
    id: str
    model: str
    state: str = "starting"          # starting | running | done | failed | cancelled
    status: str = ""
    completed: int = 0
    total: int = 0
    digest: str = ""
    error: str = ""
    error_code: str = ""
    error_message: str = ""
    action: str = ""
    resumed: bool = False
    received_bytes: int = 0
    started_at: str = field(default_factory=lambda: iso(utcnow()))
    updated_at: str = field(default_factory=lambda: iso(utcnow()))
    finished_at: str = ""
    cancel_requested: bool = False
    # Preflight facts (unknowns stay empty/None) and the live measured rate.
    size_bytes: Optional[int] = None
    size_source: str = "unknown"
    model_dir: str = ""
    model_dir_source: str = "unknown"
    free_bytes: Optional[int] = None
    reserve_bytes: int = 0
    fit_status: str = ""
    fit_label: str = ""
    fit_reason: str = ""
    fit_effective_ctx: int = 0
    fit_estimated: bool = False
    planned_eta_seconds: Optional[float] = None
    speed_bytes_per_s: Optional[float] = None
    speed_measured_at: str = ""
    bytes_per_second: Optional[float] = None
    eta_seconds: Optional[float] = None
    warnings: list[str] = field(default_factory=list)
    _blob_digest: str = ""
    _blob_started: float = 0.0
    _blob_base: int = 0

    @property
    def percent(self) -> Optional[float]:
        """Percent of the *current* blob. None when the runtime has not said how large it is."""
        if not self.total:
            return None
        return round(min(100.0, 100.0 * self.completed / self.total), 1)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id, "model": self.model, "state": self.state, "status": self.status,
            "completed": self.completed, "total": self.total, "percent": self.percent,
            "digest": self.digest, "error": self.error, "error_code": self.error_code,
            "error_message": self.error_message, "action": self.action,
            "resumed": self.resumed, "received_bytes": self.received_bytes,
            "started_at": self.started_at, "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_requested,
            "size_bytes": self.size_bytes, "size_source": self.size_source,
            "model_dir": self.model_dir, "model_dir_source": self.model_dir_source,
            "free_bytes": self.free_bytes, "reserve_bytes": self.reserve_bytes,
            "fit_status": self.fit_status, "fit_label": self.fit_label, "fit_reason": self.fit_reason,
            "fit_effective_ctx": self.fit_effective_ctx, "fit_estimated": self.fit_estimated,
            "planned_eta_seconds": self.planned_eta_seconds,
            "speed_bytes_per_s": self.speed_bytes_per_s, "speed_measured_at": self.speed_measured_at,
            "bytes_per_second": self.bytes_per_second, "eta_seconds": self.eta_seconds,
            "warnings": list(self.warnings),
        }


def _apply(job: InstallJob, event: dict[str, Any]) -> None:
    """Fold one runtime event into the job. Unknown keys are ignored, not guessed at.

    A pull stream reports one blob at a time, so ``total``/``completed`` describe the
    current blob, not the whole model. The live rate is therefore measured from the first
    byte this attempt received for that blob; a resumed blob starts at a nonzero count and
    does not make the rate look faster than the link.
    """
    now = time.monotonic()
    status = str(event.get("status") or "")
    if status:
        job.status = status[:_MAX_STATUS_CHARS]
    digest = event.get("digest")
    new_blob = bool(isinstance(digest, str) and digest and digest != job._blob_digest)
    if isinstance(digest, str) and digest:
        job.digest = digest
        if new_blob:
            job._blob_digest = digest

    total = event.get("total")
    if isinstance(total, (int, float)) and total > 0:
        # A new blob restarts the byte counters; showing 100% of the old one would lie.
        if job.total and job.completed >= job.total and total != job.total:
            job.completed = 0
        if int(total) != job.total:
            job.total = int(total)
            new_blob = True

    completed = event.get("completed")
    if isinstance(completed, (int, float)) and completed >= 0:
        if job.completed and int(completed) < job.completed:
            new_blob = True          # the same blob restarted; measure the new attempt
        job.completed = int(completed)
        job.received_bytes = max(job.received_bytes, job.completed)

    if new_blob:
        job._blob_started = now
        job._blob_base = job.completed
        job.bytes_per_second = None
        job.eta_seconds = None
    elif job._blob_started and job.completed > job._blob_base:
        elapsed = now - job._blob_started
        if elapsed >= 1.0:
            rate = (job.completed - job._blob_base) / elapsed
            job.bytes_per_second = rate
            job.eta_seconds = max(0.0, (job.total - job.completed) / rate) if job.total else None

    if event.get("error"):
        job.error = str(event["error"])[:_MAX_STATUS_CHARS * 2]
    job.updated_at = iso(utcnow())
