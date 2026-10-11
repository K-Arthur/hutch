"""Durable, content-addressed storage for generated documents.

Layout under ``<state>/documents``::

    documents/
      .staging/<job>/                       per-job private staging
      .staging/<job>.json                   commit journal, written before promotion
      <doc_id>/v<NNN>-<sha8>/<storage name> immutable promoted versions

Commit protocol: stage the bytes and fsync them → write the journal → promote with
``os.replace`` into a fresh per-version directory → fsync both directories → insert the
SQLite row (the caller's transaction) → clear the journal. A crash between promotion and
the row insert leaves a version that no query can reach, so reconciliation deletes it:
versions without rows are invisible and deleting them loses nothing. A row whose bytes
went missing is handled at serve time — the recorded size and SHA-256 are re-checked and
the request fails honestly instead of serving unverified bytes.

Every path component is created without following symlinks (``O_NOFOLLOW`` +
``dir_fd`` walks, mirroring ``tools/filewrite.py``), version files are chmod ``0400``,
and directories are ``0700``. Renames are ordered so the previous good version is never
exposed partially: staged bytes are complete before promotion starts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from ..config import hutchConfig

#: formats hutch can genuinely produce; anything else is refused, never disguised
DOCUMENT_FORMATS = ("pdf", "docx", "xlsx", "pptx", "md", "txt", "csv", "json", "yaml", "zip")

MIME_BY_FORMAT = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "yaml": "application/yaml",
    "zip": "application/zip",
}

MAX_DOCUMENT_BYTES = 32_000_000
MAX_DOCUMENTS_PER_RUN = 16
MAX_NAME_CHARS = 120
_STAGING_INFIX = ".staging"
_DOC_ID_RE = re.compile(r"^doc_[0-9a-f]{16}$")
_VERSION_DIR_RE = re.compile(r"^v(\d{3})-[0-9a-f]{8}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_STORAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DocumentStorageError(ValueError):
    """A document request could not be honoured; nothing was promoted."""


class DocumentIntegrityError(DocumentStorageError):
    """Stored bytes no longer match their recorded version."""


def new_document_id() -> str:
    return f"doc_{secrets.token_hex(8)}"


def new_job_id() -> str:
    return secrets.token_hex(12)


def sanitize_storage_name(display_name: str, fmt: str) -> str:
    """Derive a safe ASCII storage name; the display name is preserved separately.

    The canonical format extension is always kept so a storage name can never
    misrepresent its type (a non-ASCII name that slugs to nothing still gets one).
    """
    raw = str(display_name or "").strip()
    raw = raw.replace("\\", "/").rsplit("/", 1)[-1]
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-_")
    if len(raw) > MAX_NAME_CHARS:
        stem, dot, ext = raw.rpartition(".")
        raw = (stem[: MAX_NAME_CHARS - len(ext) - 1] + "." + ext) if dot else raw[:MAX_NAME_CHARS]
        raw = raw.strip(".-_")
    suffix = f".{fmt}"
    if not raw.endswith(suffix):
        dot = raw.rfind(".")
        stem = raw[:dot] if dot > 0 else raw
        raw = (re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")[: MAX_NAME_CHARS - len(suffix)]
               or "document") + suffix
    if not _STORAGE_NAME_RE.fullmatch(raw):
        raise DocumentStorageError("the file name could not be made safe for storage")
    return raw


@dataclass
class StagedDocument:
    job_id: str
    path: Path
    storage_name: str
    sha256: str
    bytes: int
    format: str


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class DocumentStorage:
    """Filesystem half of the document pipeline; identity lives in the SQLite store."""

    def __init__(self, config: hutchConfig):
        self.root = config.documents_dir
        self.staging = self.root / _STAGING_INFIX

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise DocumentStorageError("the document store root is not a private directory")
        os.chmod(self.root, 0o700)
        self.staging.mkdir(exist_ok=True, mode=0o700)
        if self.staging.is_symlink() or not self.staging.is_dir():
            raise DocumentStorageError("the document staging directory is not a private directory")

    def stage_bytes(self, job_id: str, fmt: str, display_name: str, data: bytes) -> StagedDocument:
        """Write complete candidate bytes into private staging and fsync them."""
        if fmt not in DOCUMENT_FORMATS:
            raise DocumentStorageError(f"unsupported document format: {fmt}")
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise DocumentStorageError("document bytes are empty")
        if len(data) > MAX_DOCUMENT_BYTES:
            raise DocumentStorageError(
                f"document exceeds the {MAX_DOCUMENT_BYTES // 1_000_000} MB storage limit")
        if not re.fullmatch(r"[0-9a-f]{8,48}", job_id):
            raise DocumentStorageError("invalid staging job id")
        self.ensure_root()
        job_dir = self.staging / job_id
        try:
            job_dir.mkdir(mode=0o700)
        except FileExistsError:
            raise DocumentStorageError("staging job already exists") from None
        if job_dir.is_symlink() or not job_dir.is_dir():
            raise DocumentStorageError("the staging directory is not a private directory")
        storage_name = sanitize_storage_name(display_name, fmt)
        path = job_dir / storage_name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        digest = hashlib.sha256(data).hexdigest()
        return StagedDocument(job_id=job_id, path=path, storage_name=storage_name,
                              sha256=digest, bytes=len(data), format=fmt)

    def version_dir_name(self, version: int, sha256: str) -> str:
        return f"v{version:03d}-{sha256[:8]}"

    def version_rel_path(self, document_id: str, version: int, sha256: str, storage_name: str) -> str:
        return f"{document_id}/{self.version_dir_name(version, sha256)}/{storage_name}"

    def commit(self, staged: StagedDocument, document_id: str, version: int, *,
               insert_row: Callable[[], None]) -> str:
        """Promote staged bytes to an immutable version and record it via ``insert_row``.

        ``insert_row`` must insert the ``document_versions`` row (its own transaction).
        If it raises, the promotion is rolled back so nothing unverifiable remains.
        """
        if not _DOC_ID_RE.fullmatch(document_id):
            raise DocumentStorageError("invalid document id")
        if not isinstance(version, int) or not 1 <= version <= 999:
            raise DocumentStorageError("document version must be 1–999")
        self.ensure_root()
        doc_dir = self.root / document_id
        try:
            doc_dir.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if doc_dir.is_symlink() or not doc_dir.is_dir():
            raise DocumentStorageError("the document directory is not a private directory")
        version_dir = doc_dir / self.version_dir_name(version, staged.sha256)
        rel_path = self.version_rel_path(document_id, version, staged.sha256, staged.storage_name)
        journal = self.staging / f"{staged.job_id}.json"
        payload = {"document_id": document_id, "version": version, "rel_path": rel_path,
                   "sha256": staged.sha256, "bytes": staged.bytes, "staged": str(staged.path)}
        fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        promoted = False
        try:
            version_dir.mkdir(mode=0o700)
            target = version_dir / staged.storage_name
            os.replace(staged.path, target)
            promoted = True
            os.chmod(target, 0o400)
            _fsync_dir(version_dir)
            _fsync_dir(doc_dir)
            insert_row()
        except BaseException:
            if promoted:
                shutil.rmtree(version_dir, ignore_errors=True)
                _fsync_dir(doc_dir)
            journal.unlink(missing_ok=True)
            raise
        journal.unlink(missing_ok=True)
        try:
            staged.path.parent.rmdir()
        except OSError:
            pass
        return rel_path

    def _walk_open(self, rel_parts: tuple[str, ...]) -> int:
        """Open ``rel_parts`` under the root without following symlinks; returns a dirfd/file fd."""
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        dir_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            for part in rel_parts[:-1]:
                next_fd = os.open(part, flags | getattr(os, "O_DIRECTORY", 0), dir_fd=dir_fd)
                os.close(dir_fd)
                dir_fd = next_fd
            return os.open(rel_parts[-1], flags, dir_fd=dir_fd)
        finally:
            os.close(dir_fd)

    def read_version(self, rel_path: str, expected_sha256: str, expected_bytes: int) -> bytes:
        """Read a version and verify it against its recorded size and hash before anyone sees it."""
        if not _SHA_RE.fullmatch(expected_sha256) or not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise DocumentStorageError("this version has no verifiable content hash")
        parts = PurePosixPath(rel_path).parts
        if (len(parts) != 3 or not _DOC_ID_RE.fullmatch(parts[0])
                or not _VERSION_DIR_RE.fullmatch(parts[1]) or not _STORAGE_NAME_RE.fullmatch(parts[2])):
            raise DocumentStorageError("invalid document storage path")
        try:
            fd = self._walk_open(parts)
        except (OSError, FileNotFoundError):
            raise DocumentStorageError("document version file is missing") from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise DocumentStorageError("document version is not a regular file")
            if info.st_size != expected_bytes:
                raise DocumentIntegrityError("document size no longer matches its recorded version")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)
        if len(data) != expected_bytes:
            raise DocumentIntegrityError("document size no longer matches its recorded version")
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256:
            raise DocumentIntegrityError("document failed its recorded SHA-256 integrity check")
        return data

    def version_path_for_serve(self, rel_path: str) -> Path:
        """Resolve a version path after the hash check for streaming responses."""
        return self.root.joinpath(*PurePosixPath(rel_path).parts)

    def remove_version(self, rel_path: str) -> None:
        parts = PurePosixPath(rel_path).parts
        if len(parts) != 3:
            return
        shutil.rmtree(self.root / parts[0] / parts[1], ignore_errors=True)


def reconcile_documents_store(config: hutchConfig, version_exists: Callable[[str, int], bool],
                              *, max_staging_age: float = 24 * 3600) -> dict[str, int]:
    """Crash recovery: delete unreferenced versions and abandoned staging.

    ``version_exists(document_id, version)`` must consult the committed SQLite rows.
    A promoted version without a row was never visible, so deletion loses nothing;
    staging older than ``max_staging_age`` has no live owner (jobs are bounded by the
    run that created them, and live runs never leave staging for a day).
    """
    storage = DocumentStorage(config)
    removed_versions = removed_staging = 0
    if not storage.root.is_dir():
        return {"removed_versions": 0, "removed_staging": 0}
    if storage.staging.is_dir():
        now = time.time()
        for entry in list(storage.staging.iterdir()):
            try:
                age = now - entry.stat(follow_symlinks=False).st_mtime
            except OSError:
                continue
            if age <= max_staging_age:
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
                removed_staging += 1
            elif entry.is_file() and not entry.is_symlink():
                entry.unlink(missing_ok=True)
                removed_staging += 1
    for doc_dir in list(storage.root.iterdir()):
        if not doc_dir.is_dir() or doc_dir.is_symlink() or doc_dir.name == _STAGING_INFIX:
            continue
        if not _DOC_ID_RE.fullmatch(doc_dir.name):
            continue
        document_id = doc_dir.name
        live_versions = 0
        for version_dir in list(doc_dir.iterdir()):
            match = _VERSION_DIR_RE.fullmatch(version_dir.name) if version_dir.is_dir() and not version_dir.is_symlink() else None
            if match is None:
                continue
            if version_exists(document_id, int(match.group(1))):
                live_versions += 1
                continue
            shutil.rmtree(version_dir, ignore_errors=True)
            removed_versions += 1
        if live_versions == 0:
            shutil.rmtree(doc_dir, ignore_errors=True)
    return {"removed_versions": removed_versions, "removed_staging": removed_staging}
