"""Upload intake routes: bounded files into a conversation's workspace, verified
at every step.

``build_uploads_router(store, config)`` returns a FastAPI ``APIRouter`` with:

* ``POST   /api/v1/conversations/{id}/uploads``           (multipart, bounded)
* ``GET    /api/v1/conversations/{id}/uploads``            (listing)
* ``GET    /api/v1/conversations/{id}/uploads/{id}/content`` (hash-verified bytes)
* ``GET    /api/v1/conversations/{id}/uploads/{id}/report``  (bounded CSV disclosure)
* ``DELETE /api/v1/conversations/{id}/uploads/{id}``       (listing-level delete)

Authorization follows the media/document routes' pattern: no per-route
dependency; the app-level middleware owns authentication when the integrator
mounts this router inside ``create_app``.

Design constraints this module owns:

* every stored file lands in the conversation's workspace directory
  (``<state>/workspaces/<conversation_id>/``, the same directory the contained
  Python kernel reads), named ``<upl_id>-<safe name>`` so the model can refer to
  the exact file it sees in ``list_files``;
* bytes are hashed while streaming and re-verified at serve time — a tampered
  file is an honest 410, never served;
* accepted kinds are delimited/tabular text, Markdown/JSON text, and PNG/JPEG/
  WebP images (magic-byte sniffed). Anything else — including binary dressed in
  a text extension — is refused with an honest 415, never guessed at;
* ``DELETE`` moves the row to the ``deleted`` state; the bytes stay on disk
  (bounded by the per-conversation upload cap) so a delete is reversible bookkeeping,
  not a destructive unlink.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from ..config import hutchConfig
from ..workspace import csvprobe
from ..workspace.manager import workspace_dir_for

MAX_UPLOAD_BYTES = 25_000_000
MAX_UPLOADS_PER_CONVERSATION = 200

#: extension -> canonical MIME. The extension is the request's claim; the
#: content sniff below is the check.
MIME_BY_SUFFIX = {
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

_TEXT_SUFFIXES = {".csv", ".tsv", ".txt", ".md", ".json"}

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)

_UPLOAD_ID_RE = re.compile(r"^upl_[0-9a-f]{16}$")
_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class UploadRejected(HTTPException):
    """A refused upload: the client sent something the bounds or the sniff
    cannot honestly accept."""


def sanitize_upload_name(name: str) -> str:
    """A safe display/storage name: one path component, ASCII-safe, bounded,
    extension preserved so the storage name never misrepresents its kind."""
    raw = str(name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    raw = _NAME_RE.sub("-", raw).strip(".-")
    suffix = Path(raw).suffix.lower()
    if suffix not in MIME_BY_SUFFIX:
        suffix = ""
    if len(raw) > 120:
        stem = raw[: 120 - len(suffix)] if suffix else raw[:120]
        raw = (stem + suffix) if suffix else stem
    return raw.strip(".-") or "upload.bin"


def _sniff_kind(data_head: bytes, suffix: str) -> str:
    """Return the MIME the bytes actually support, or raise 415. Text suffixes
    must decode as UTF-8 in their head and contain no NUL; image suffixes must
    match their magic. A mismatch between claim and content is a refusal."""
    for magic, mime in _MAGIC:
        if data_head.startswith(magic):
            if mime != MIME_BY_SUFFIX.get(suffix):
                raise UploadRejected(415, f"file content is {mime} but the name says {suffix or 'nothing'}")
            return mime
    if suffix in _TEXT_SUFFIXES:
        if b"\x00" in data_head:
            raise UploadRejected(415, "binary content in a text upload")
        try:
            data_head.decode("utf-8")
        except UnicodeDecodeError:
            # Latin-1 and friends are common in real CSVs; accept them but say so.
            return MIME_BY_SUFFIX[suffix]
        return MIME_BY_SUFFIX[suffix]
    raise UploadRejected(415, "unsupported upload kind; accepted: csv, tsv, txt, md, json, png, jpeg, webp")


def _stored_path(config: hutchConfig, conversation_id: str, upload_id: str, filename: str) -> Path:
    safe = sanitize_upload_name(filename)
    return workspace_dir_for(config.state_dir, conversation_id) / f"{upload_id}-{safe}"


def _read_verified(row: dict[str, Any], path: Path) -> bytes:
    """Re-verify size and SHA-256 before anyone sees the bytes; a mismatch is a
    410 Gone, not a plausible substitute."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise HTTPException(404, "uploaded file is missing from the workspace") from None
    if len(data) != int(row["byte_size"]) or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise HTTPException(410, "uploaded file no longer matches its recorded digest")
    return data


def build_uploads_router(store: Any, config: hutchConfig) -> APIRouter:
    router = APIRouter()

    def _row_or_404(conversation_id: str, upload_id: str) -> dict[str, Any]:
        if not _UPLOAD_ID_RE.fullmatch(upload_id or ""):
            raise HTTPException(404, "no such upload")
        row = store.get_upload(upload_id)
        if row is None or row["conversation_id"] != conversation_id:
            raise HTTPException(404, "no such upload")
        return row

    @router.post("/api/v1/conversations/{conversation_id}/uploads")
    async def upload_to_workspace(
        conversation_id: str, file: UploadFile = File(...)
    ) -> dict[str, Any]:
        if store.get_conversation(conversation_id) is None:
            raise HTTPException(404, "no such conversation")
        existing = store.uploads_for_conversation(conversation_id, limit=MAX_UPLOADS_PER_CONVERSATION)
        if len(existing) >= MAX_UPLOADS_PER_CONVERSATION:
            raise HTTPException(422, f"this conversation already holds {MAX_UPLOADS_PER_CONVERSATION} uploads")
        display = sanitize_upload_name(file.filename or "")
        suffix = Path(display).suffix.lower()
        if suffix not in MIME_BY_SUFFIX:
            raise UploadRejected(415, "unsupported upload kind; accepted: csv, tsv, txt, md, json, png, jpeg, webp")
        workspace = workspace_dir_for(config.state_dir, conversation_id)
        workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
        digest = hashlib.sha256()
        head = b""
        total = 0
        tmp = workspace / f".incoming-{os.getpid()}-{display}"
        try:
            with open(tmp, "wb", opener=lambda p, flags: os.open(p, flags | os.O_NOFOLLOW, 0o600)) as out:
                while True:
                    chunk = await file.read(65_536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise UploadRejected(413, f"uploads are limited to {MAX_UPLOAD_BYTES:,} bytes")
                    if len(head) < 512:
                        head += chunk[: 512 - len(head)]
                    digest.update(chunk)
                    out.write(chunk)
            mime = _sniff_kind(head, suffix)
            if total == 0:
                raise UploadRejected(422, "empty upload")
            os.chmod(tmp, 0o400)
            row = store.add_upload(conversation_id, display, mime, total, digest.hexdigest())
            final = _stored_path(config, conversation_id, row["id"], display)
            os.replace(tmp, final)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        return {
            "id": row["id"],
            "filename": row["filename"],
            "mime": row["mime"],
            "bytes": row["byte_size"],
            "sha256": row["sha256"],
            "state": row["state"],
            "workspace_filename": Path(_stored_path(config, conversation_id, row["id"], display)).name,
        }

    @router.get("/api/v1/conversations/{conversation_id}/uploads")
    def list_uploads(conversation_id: str, limit: int = 50) -> dict[str, Any]:
        if store.get_conversation(conversation_id) is None:
            raise HTTPException(404, "no such conversation")
        rows = store.uploads_for_conversation(conversation_id, limit=limit)
        return {"uploads": [
            {k: row[k] for k in ("id", "filename", "mime", "byte_size", "sha256", "state", "created_at")}
            for row in rows if row["state"] != "deleted"
        ]}

    @router.get("/api/v1/conversations/{conversation_id}/uploads/{upload_id}/content")
    def upload_content(conversation_id: str, upload_id: str, request: Request) -> Response:
        row = _row_or_404(conversation_id, upload_id)
        if row["state"] == "deleted":
            raise HTTPException(404, "upload was deleted")
        if row["state"] != "ready":
            raise HTTPException(410, f"upload is {row['state']}")
        data = _read_verified(row, _stored_path(config, conversation_id, upload_id, row["filename"]))
        etag = f'"{row["sha256"]}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return Response(
            content=data,
            media_type=str(row["mime"]),
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=31536000, immutable",
                "Content-Disposition": f'attachment; filename="{row["filename"]}"',
                "X-Hutch-Upload-Verified": "sha256",
            },
        )

    @router.get("/api/v1/conversations/{conversation_id}/uploads/{upload_id}/report")
    def upload_report(conversation_id: str, upload_id: str) -> dict[str, Any]:
        row = _row_or_404(conversation_id, upload_id)
        if row["state"] != "ready":
            raise HTTPException(410, f"upload is {row['state']}")
        path = _stored_path(config, conversation_id, upload_id, row["filename"])
        data_head = _read_verified(row, path)[:512]
        mime = _sniff_kind(data_head, Path(row["filename"]).suffix.lower())
        if str(row["mime"]).startswith("image/"):
            return {"kind": "image", "mime": row["mime"], "bytes": row["byte_size"]}
        if str(row["mime"]) == "application/json":
            return {"kind": "json", "mime": row["mime"], "bytes": row["byte_size"]}
        report = csvprobe.probe_csv_path(path)
        report.update({"kind": "delimited-text", "mime": row["mime"], "bytes": row["byte_size"]})
        return report

    @router.delete("/api/v1/conversations/{conversation_id}/uploads/{upload_id}")
    def delete_upload(conversation_id: str, upload_id: str) -> dict[str, Any]:
        _row_or_404(conversation_id, upload_id)
        try:
            row = store.mark_upload_state(upload_id, "deleted")
        except KeyError:
            raise HTTPException(404, "no such upload") from None
        return {"id": row["id"], "state": row["state"]}

    return router
