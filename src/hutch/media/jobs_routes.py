"""Dashboard API for media jobs that outlive the tool call that started them.

* ``GET  /api/v1/media/jobs?open=true&limit=50``  jobs across runs, newest first
* ``GET  /api/v1/media/jobs/{id}``
* ``POST /api/v1/media/jobs/{id}/advance``         observe once; fetch and store if finished
* ``POST /api/v1/media/jobs/{id}/cancel``          ask the provider to cancel

These paths are absent from ``REMOTE_ROUTE_CAPABILITIES`` on purpose: a job can spend the owner's
money and carries their prompt, so a paired phone is denied by default. The routes build their
backends per request from the connections and keys that exist now.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from . import resume
from .backends import build_backends
from .jobs import MediaJobService
from .ledger import get_job, list_jobs, sweep_orphans
from .spool import MediaSpool
from .storage import MediaStorage

_JOB_ID_RE = re.compile(r"^mj_[0-9a-f]{16}$")


def build_jobs_router(store: Any, media_store: MediaStorage, state_dir: Path | None = None) -> APIRouter:
    router = APIRouter()
    state = Path(state_dir) if state_dir is not None else media_store.root.parent

    def service() -> MediaJobService:
        backends = build_backends(state, spool=MediaSpool(media_store.root))
        return MediaJobService(store, media_store, backends=backends)

    def checked(job_id: str) -> str:
        if not _JOB_ID_RE.fullmatch(job_id):
            raise HTTPException(404, "no such media job")
        return job_id

    @router.get("/api/v1/media/jobs")
    def jobs(open: bool = True, limit: int = 50) -> dict[str, Any]:
        try:                       # housekeeping: week-old held results of finished jobs
            sweep_orphans(store, MediaSpool(media_store.root))
        except OSError:
            pass
        return {"jobs": list_jobs(store, open_only=open, limit=limit)}

    @router.get("/api/v1/media/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        found = get_job(store, checked(job_id))
        if found is None:
            raise HTTPException(404, "no such media job")
        return found

    @router.post("/api/v1/media/jobs/{job_id}/advance")
    def advance(job_id: str) -> dict[str, Any]:
        try:
            return resume.advance(service(), store, checked(job_id))
        except KeyError:
            raise HTTPException(404, "no such media job") from None

    @router.post("/api/v1/media/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        try:
            return resume.cancel(service(), checked(job_id))
        except KeyError:
            raise HTTPException(404, "no such media job") from None

    return router
