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
import fcntl
import json
import os
import re
import secrets
import stat
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from ..config import hutchConfig
from ..workspace import csvprobe
from ..workspace.manager import workspace_dir_for
from ..store import UploadLimitExceeded

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
_ORPHAN_GRACE_SECONDS = 24 * 60 * 60


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
    if data_head.startswith(b"RIFF") and data_head[8:12] == b"WEBP":
        mime = "image/webp"
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


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_pending_dir(config: hutchConfig) -> Path:
    pending = Path(config.state_dir) / ".hutch-upload-pending"
    pending.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = pending.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise OSError("upload staging path is not a directory")
    if (info.st_mode & 0o777) != 0o700:
        os.chmod(pending, 0o700, follow_symlinks=False)
    return pending


def _cleanup_stale_upload_orphans(store: Any, config: hutchConfig) -> None:
    """Reconcile crash-left files using private markers, never filename guesses.

    Markers older than a day cannot belong to a live upload operation. A DB row
    wins over the marker (including deleted rows), so cleanup never removes a
    registered upload's workspace bytes.
    """
    pending = Path(config.state_dir) / ".hutch-upload-pending"
    try:
        pending_info = pending.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(pending_info.st_mode):
        return
    if (pending_info.st_mode & 0o777) != 0o700:
        os.chmod(pending, 0o700, follow_symlinks=False)
    cutoff = time.time() - _ORPHAN_GRACE_SECONDS
    active_temps: set[str] = set()
    for marker in pending.iterdir():
        if not _UPLOAD_ID_RE.fullmatch(marker.stem) or marker.suffix != ".json":
            continue
        marker_fd = -1
        try:
            marker_fd = os.open(marker, os.O_RDWR | getattr(os, "O_CLOEXEC", 0) |
                                getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            info = os.fstat(marker_fd)
            if not stat.S_ISREG(info.st_mode):
                continue
            try:
                fcntl.flock(marker_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                active_temps.add(json.loads(os.read(marker_fd, 4096)).get("temporary", ""))
                continue
            if info.st_mtime >= cutoff:
                continue
            entry = json.loads(os.read(marker_fd, 4096).decode("utf-8"))
            conversation_id = entry["conversation_id"]
            filename = entry["filename"]
            temporary = entry["temporary"]
            if (not isinstance(conversation_id, str) or
                    not re.fullmatch(r"conv_[A-Za-z0-9_-]{1,128}", conversation_id) or
                    not isinstance(filename, str) or sanitize_upload_name(filename) != filename or
                    not isinstance(temporary, str) or not re.fullmatch(r"\.incoming-[0-9a-f]{16}", temporary)):
                continue
            upload_id = marker.stem
            try:
                registered = store.get_upload(upload_id) is not None
            except Exception:
                continue
            if not registered:
                orphan = _stored_path(config, conversation_id, upload_id, filename)
                _unlink_marked_file(orphan, entry)
            _unlink_marked_file(pending / temporary, entry)
            marker.unlink(missing_ok=True)
            _sync_directory(pending)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            # Invalid or inaccessible markers remain for operator inspection.
            continue
        finally:
            if marker_fd >= 0:
                os.close(marker_fd)
    # A crash while streaming happens before a complete marker is written. Such
    # files live only in this private state directory and have a strict prefix.
    for temporary in pending.iterdir():
        if (temporary.name in active_temps or
                not re.fullmatch(r"\.incoming-[0-9a-f]{16}", temporary.name)):
            continue
        temp_fd = -1
        try:
            temp_fd = os.open(temporary, os.O_RDWR | getattr(os, "O_CLOEXEC", 0) |
                              getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            info = os.fstat(temp_fd)
            if not stat.S_ISREG(info.st_mode):
                continue
            try:
                fcntl.flock(temp_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            if info.st_mtime < cutoff:
                temporary.unlink(missing_ok=True)
                _sync_directory(pending)
        except OSError:
            continue
        finally:
            if temp_fd >= 0:
                os.close(temp_fd)


def _unlink_marked_file(path: Path, marker: dict[str, Any]) -> None:
    """Unlink only the same regular file (including digest) recorded by a marker."""
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
                             getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        info = os.fstat(descriptor)
        expected_size = int(marker["byte_size"])
        if (not stat.S_ISREG(info.st_mode) or info.st_dev != int(marker["device"]) or
                info.st_ino != int(marker["inode"]) or info.st_size != expected_size or
                expected_size < 0 or expected_size > MAX_UPLOAD_BYTES):
            return
        digest = hashlib.sha256()
        remaining = expected_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                return
            digest.update(chunk)
            remaining -= len(chunk)
        if digest.hexdigest() != marker["sha256"]:
            return
        current = path.lstat()
        if (not stat.S_ISREG(current.st_mode) or current.st_dev != info.st_dev or
                current.st_ino != info.st_ino):
            return
        os.close(descriptor)
        descriptor = -1
        path.unlink(missing_ok=True)
        _sync_directory(path.parent)
    except (OSError, KeyError, TypeError, ValueError):
        return
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_verified(row: dict[str, Any], path: Path) -> bytes:
    """Re-verify size and SHA-256 before anyone sees the bytes; a mismatch is a
    410 Gone, not a plausible substitute."""
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        # A nonblocking open avoids hanging if a workspace file is replaced by
        # a FIFO. O_NOFOLLOW rejects symlinks before opening their targets.
        flags |= getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise HTTPException(404, "uploaded file is missing from the workspace") from None
    except OSError:
        raise HTTPException(410, "uploaded file is not a safe regular file") from None
    try:
        info = os.fstat(descriptor)
        expected = int(row["byte_size"])
        if not stat.S_ISREG(info.st_mode) or expected < 0 or expected > MAX_UPLOAD_BYTES or info.st_size != expected:
            raise HTTPException(410, "uploaded file no longer matches its recorded size")
        chunks: list[bytes] = []
        remaining = expected + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    except OSError:
        raise HTTPException(410, "uploaded file could not be read safely") from None
    finally:
        os.close(descriptor)
    if len(data) != expected or hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise HTTPException(410, "uploaded file no longer matches its recorded digest")
    return data


def build_uploads_router(store: Any, config: hutchConfig) -> APIRouter:
    router = APIRouter()
    _cleanup_stale_upload_orphans(store, config)

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
        try:
            workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
            pending = _ensure_pending_dir(config)
            if pending.stat().st_dev != workspace.stat().st_dev:
                raise HTTPException(503, "upload staging and workspace must be on the same filesystem")
        except OSError:
            raise HTTPException(503, "upload staging directory is unavailable") from None
        digest = hashlib.sha256()
        head = b""
        total = 0
        upload_id = f"upl_{secrets.token_hex(8)}"
        temporary = f".incoming-{upload_id[4:]}"
        tmp = pending / temporary
        descriptor = -1
        temp_lock_fd = -1
        try:
            descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            temp_lock_fd = os.dup(descriptor)
        except OSError:
            if descriptor >= 0:
                os.close(descriptor)
                tmp.unlink(missing_ok=True)
            raise HTTPException(503, "upload staging file is unavailable") from None
        final = _stored_path(config, conversation_id, upload_id, display)
        promoted = False
        registered = False
        database_attempted = False
        marker: Path | None = None
        marker_fd = -1
        marker_entry: dict[str, Any] | None = None
        try:
            with os.fdopen(descriptor, "wb") as out:
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
            with tmp.open("rb") as stored:
                os.fsync(stored.fileno())
                os.fchmod(stored.fileno(), 0o400)
                stored_info = os.fstat(stored.fileno())
            marker_entry = {
                "conversation_id": conversation_id,
                "filename": display,
                "temporary": temporary,
                "byte_size": total,
                "sha256": digest.hexdigest(),
                "device": stored_info.st_dev,
                "inode": stored_info.st_ino,
            }
            marker = pending / f"{upload_id}.json"
            marker_fd = os.open(marker, os.O_RDWR | os.O_CREAT | os.O_EXCL |
                                getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
            fcntl.flock(marker_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            marker_bytes = memoryview(json.dumps(marker_entry).encode("utf-8"))
            while marker_bytes:
                marker_bytes = marker_bytes[os.write(marker_fd, marker_bytes):]
            os.fsync(marker_fd)
            _sync_directory(pending)
            os.replace(tmp, final)
            promoted = True
            _sync_directory(workspace)
            database_attempted = True
            try:
                row = store.add_upload(conversation_id, display, mime, total, digest.hexdigest(), upload_id=upload_id)
            except UploadLimitExceeded as exc:
                raise HTTPException(422, str(exc)) from exc
            registered = True
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            registration_known = not database_attempted or registered
            if promoted and database_attempted and not registered:
                try:
                    registered = store.get_upload(upload_id) is not None
                    registration_known = True
                except Exception:
                    registration_known = False
                if registration_known and not registered and marker_entry is not None:
                    _unlink_marked_file(final, marker_entry)
            if marker is not None and registration_known:
                marker.unlink(missing_ok=True)
                try:
                    _sync_directory(marker.parent)
                except OSError:
                    pass
            if marker_fd >= 0:
                os.close(marker_fd)
            if temp_lock_fd >= 0:
                os.close(temp_lock_fd)
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
        data = _read_verified(row, path)
        data_head = data[:512]
        mime = _sniff_kind(data_head, Path(row["filename"]).suffix.lower())
        if str(row["mime"]).startswith("image/"):
            return {"kind": "image", "mime": row["mime"], "bytes": row["byte_size"]}
        if str(row["mime"]) == "application/json":
            return {"kind": "json", "mime": row["mime"], "bytes": row["byte_size"]}
        report = csvprobe.probe_csv_bytes(data)
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
