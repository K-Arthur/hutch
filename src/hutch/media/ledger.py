"""Read-only queries over ``media_jobs`` that span runs.

``Store.media_jobs_for_run`` needs a run id, but a job that outlives its run (a five-minute video)
is found by what is still open, not by who started it. ``store.py`` is frozen, so these queries sit
here and use the store's own lock and connection, as ``slots`` and ``code_review`` do.
"""

from __future__ import annotations

from typing import Any, Optional

from .status import service_status

OPEN_STATUSES = ("queued", "running")


def list_jobs(store: Any, *, open_only: bool = True, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    where = "WHERE status IN ('queued','running')" if open_only else ""
    with store._lock:
        rows = store._db.execute(
            f"SELECT * FROM media_jobs {where} ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,)).fetchall()
    return [describe(store._media_job_row(row)) for row in rows]


def get_job(store: Any, job_id: str) -> Optional[dict[str, Any]]:
    row = store.get_media_job(job_id)
    return describe(row) if row else None


def describe(row: dict[str, Any]) -> dict[str, Any]:
    """The fields a person needs, without the raw prompt (kept in the row, shown truncated)."""
    requested = row.get("requested") if isinstance(row.get("requested"), dict) else {}
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    prompt = str(requested.get("prompt") or "")
    return {
        "id": row["id"], "run_id": row["run_id"], "kind": row["kind"], "backend": row["backend"],
        "status": service_status(row), "upstream_job_id": row.get("upstream_job_id"),
        "prompt_preview": prompt[:200], "prompt_chars": len(prompt),
        "error": row.get("error"), "cost_note": row.get("cost_note"),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "media": ({"media_id": result["media_id"], "version": result.get("version", 1),
                   "sha256": result.get("sha256"), "mime": result.get("mime"),
                   "content_url": f"/api/v1/media/{result['media_id']}/versions/"
                                  f"{result.get('version', 1)}/content"}
                  if result.get("media_id") else None),
    }


def sweep_orphans(store: Any, spool: Any, *, older_than_seconds: float = 7 * 86400.0) -> int:
    """Remove held results nothing references: entries of jobs that are no longer open and are
    older than the bound. A held result of a job still open is never touched."""
    with store._lock:
        rows = store._db.execute(
            "SELECT upstream_job_id FROM media_jobs WHERE status IN ('queued','running') "
            "AND upstream_job_id IS NOT NULL").fetchall()
    return spool.sweep(keep={row[0] for row in rows}, older_than_seconds=older_than_seconds)
