"""Media serving routes: hash re-verified at serve time, correct MIME, ETag.

``build_media_router(store, media_store)`` returns a FastAPI ``APIRouter`` with:

* ``GET /api/v1/media/{media_id}/versions/{version}/content``
* ``GET /api/v1/media/{media_id}/versions/{version}/poster``

Serving re-verifies the stored bytes against the version manifest (size +
SHA-256) before anyone sees them: a missing version is an honest 404, corrupted
bytes an honest 410 Gone — never unverified content, never a plausible guess.

Authorization follows the document routes' pattern (``server/app.py``): routes
carry NO per-route dependency; the app-level ``dependencies=[Depends(authorize_remote_route)]``
plus ``SecurityMiddleware`` own authentication when the integrator mounts this
router inside ``create_app``. When wiring it up, add paired-phone capability
entries for these two GETs to ``REMOTE_ROUTE_CAPABILITIES`` ("monitor"), the same
way the document download routes are registered.

ETag is the verified SHA-256, so ``If-None-Match`` gets a cheap 304.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from .storage import MediaIntegrityError, MediaStorage, MediaStorageError

_MEDIA_ID_RE = re.compile(r"^media_[0-9a-f]{16}$")


def build_media_router(store: Any, media_store: MediaStorage) -> APIRouter:
    """Build the media serving router. ``store`` is held for the integrator's
    row-based checks (schema v55 has no media-versions table; when one lands the
    routes can cross-check the manifest against it). ``media_store`` is the
    :class:`MediaStorage` whose ``read_version``/``read_poster`` re-verify bytes.
    """
    router = APIRouter()

    def _verified(media_id: str, version: int, reader) -> tuple[bytes, dict[str, Any]]:
        if not _MEDIA_ID_RE.fullmatch(media_id) or not isinstance(version, int) or version < 1:
            raise HTTPException(404, "no such media version")
        try:
            return reader(media_id, version)
        except MediaIntegrityError as exc:
            # 410 Gone: the version existed but its bytes no longer match the
            # recorded version. Honest, cacheable-nothing, never a silent substitute.
            raise HTTPException(410, str(exc)) from None
        except MediaStorageError as exc:
            raise HTTPException(404, str(exc)) from None

    @router.get("/api/v1/media/{media_id}/versions/{version}/content")
    def media_content(media_id: str, version: int, request: Request) -> Response:
        data, manifest = _verified(media_id, version, media_store.read_version)
        sha = str(manifest["sha256"])
        etag = f'"{sha}"'
        headers = {
            "Cache-Control": "private, max-age=31536000, immutable",
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
            "X-Hutch-Artifact-Verified": "sha256",
            "Accept-Ranges": "bytes",
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        filename = str(manifest.get("storage_name") or "media")
        headers["Content-Disposition"] = f'inline; filename="{filename}"'
        # Verified single-range support, so media elements can seek without downloading
        # the whole asset (video/audio). Multi-range falls back to a full 200; an
        # unsatisfiable range is an honest 416. Bytes were hash-verified above, so a
        # range slice cannot bypass verification.
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", request.headers.get("range", "").strip())
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else len(data) - 1
            if start >= len(data) or end < start:
                raise HTTPException(416, "requested range not satisfiable")
            end = min(end, len(data) - 1)
            headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
            return Response(content=data[start:end + 1], status_code=206,
                            media_type=str(manifest["mime"]), headers=headers)
        return Response(content=data, media_type=str(manifest["mime"]), headers=headers)

    @router.get("/api/v1/media/{media_id}/versions/{version}/poster")
    def media_poster(media_id: str, version: int, request: Request) -> Response:
        data, poster = _verified(media_id, version, media_store.read_poster)
        sha = str(poster["sha256"])
        etag = f'"{sha}"'
        headers = {
            "Cache-Control": "private, max-age=31536000, immutable",
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
            "X-Hutch-Artifact-Verified": "sha256",
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        filename = str(poster.get("name") or "poster")
        headers["Content-Disposition"] = f'inline; filename="{filename}"'
        return Response(content=data, media_type=str(poster["mime"]), headers=headers)

    return router
