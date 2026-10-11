"""Durable, content-addressed storage for synthesis artifacts.

Layout under ``<state>/synthesis``::

    synthesis/
      .staging/<job>/                       per-job private staging
      .staging/<job>.json                   commit journal (before promotion)
      <manifest_id>/<kind>/v<NNN>-<sha8>/<storage name>   immutable versions

The commit protocol mirrors ``documents/storage.py``: stage complete bytes and fsync →
write the journal → promote with ``os.replace`` into a fresh version directory → fsync the
directories → insert the SQLite row (caller's transaction) → clear the journal. A crash
between promotion and the row insert leaves a version no query can reach, and
:meth:`SynthesisStorage.reconcile` removes exactly those; a row whose bytes went missing
fails verification at read time instead of serving something unverified.

Failed validation is never promoted as ready: callers stage, validate, then commit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from ..config import hutchConfig

#: artifact kinds this store accepts; anything else is refused, never disguised
SYNTHESIS_KINDS = ("script", "audio_segment", "audio_overview", "transcript", "infographic",
                   "brief", "table", "companion")

MIME_BY_SUFFIX = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "svg": "image/svg+xml",
    "png": "image/png",
    "pdf": "application/pdf",
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
}

#: per-kind byte ceilings; audio is bigger than the rest on purpose
MAX_KIND_BYTES = {
    "audio_overview": 128_000_000,
    "audio_segment": 64_000_000,
    "transcript": 8_000_000,
    "infographic": 16_000_000,
    "script": 4_000_000,
    "brief": 16_000_000,
    "table": 16_000_000,
    "companion": 4_000_000,
}
MAX_RUN_SYNTHESIS_BYTES = 512_000_000

_MANIFEST_ID_RE = re.compile(r"^syn_[0-9a-f]{16}$")
_VERSION_DIR_RE = re.compile(r"^v(\d{3})-([0-9a-f]{8})$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_STORAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_JOB_RE = re.compile(r"^[0-9a-f]{8,48}$")


class SynthesisStorageError(ValueError):
    """The artifact request could not be honoured; nothing was promoted."""


class SynthesisIntegrityError(SynthesisStorageError):
    """Stored bytes no longer match their recorded hash/size."""


def new_artifact_id() -> str:
    return f"art_{secrets.token_hex(8)}"


def new_job_id() -> str:
    return secrets.token_hex(12)


def sanitize_storage_name(display_name: str, suffix: str) -> str:
    """ASCII-safe storage name; the extension is normalized to the real container."""
    raw = str(display_name or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-_")
    if raw.lower().endswith(f".{suffix}"):
        raw = raw[: -(len(suffix) + 1)]
    raw = (raw or "artifact")[:100].strip(".-_") or "artifact"
    name = f"{raw}.{suffix}"
    if not _STORAGE_NAME_RE.fullmatch(name):
        raise SynthesisStorageError("the artifact name could not be made safe for storage")
    return name


def mime_for(name: str) -> str:
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return MIME_BY_SUFFIX.get(suffix, "application/octet-stream")


def next_kind_version(store, manifest_id: str, kind: str) -> int:
    """Artifact versions are unique per (manifest, kind); re-renders never overwrite history."""
    existing = store.list_synthesis_artifacts(manifest_id, kind=kind, limit=500)
    return (max(int(a["version"]) for a in existing) + 1) if existing else 1


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@dataclass
class StagedArtifact:
    job_id: str
    path: Path
    storage_name: str
    sha256: str
    bytes: int
    kind: str
    mime: str


class SynthesisStorage:
    """Filesystem half of the synthesis pipeline; identity lives in the SQLite store."""

    def __init__(self, config: hutchConfig):
        self.root = config.synthesis_dir
        self.staging = self.root / ".staging"

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise SynthesisStorageError("the synthesis store root is not a private directory")
        os.chmod(self.root, 0o700)
        self.staging.mkdir(exist_ok=True, mode=0o700)
        if self.staging.is_symlink() or not self.staging.is_dir():
            raise SynthesisStorageError("the synthesis staging directory is not a private directory")

    def stage_bytes(self, kind: str, display_name: str, data: bytes, *,
                    job_id: Optional[str] = None) -> StagedArtifact:
        if kind not in SYNTHESIS_KINDS:
            raise SynthesisStorageError(f"unsupported artifact kind: {kind}")
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise SynthesisStorageError("artifact bytes are empty")
        limit = MAX_KIND_BYTES[kind]
        if len(data) > limit:
            raise SynthesisStorageError(f"{kind} exceeds the {limit // 1_000_000} MB storage limit")
        suffix = display_name.rsplit(".", 1)[-1].lower() if "." in display_name else ""
        if suffix not in MIME_BY_SUFFIX:
            raise SynthesisStorageError(f"unsupported artifact extension: {suffix or '(none)'}")
        jid = job_id or new_job_id()
        if not _JOB_RE.fullmatch(jid):
            raise SynthesisStorageError("invalid staging job id")
        self.ensure_root()
        job_dir = self.staging / jid
        try:
            job_dir.mkdir(mode=0o700)
        except FileExistsError:
            raise SynthesisStorageError("staging job already exists") from None
        if job_dir.is_symlink() or not job_dir.is_dir():
            raise SynthesisStorageError("the staging directory is not a private directory")
        name = sanitize_storage_name(display_name, suffix)
        path = job_dir / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        digest = hashlib.sha256(bytes(data)).hexdigest()
        return StagedArtifact(job_id=jid, path=path, storage_name=name, sha256=digest,
                              bytes=len(data), kind=kind, mime=mime_for(name))

    def version_dir_name(self, version: int, sha256: str) -> str:
        return f"v{version:03d}-{sha256[:8]}"

    def version_rel_path(self, manifest_id: str, kind: str, version: int, sha256: str,
                         storage_name: str) -> str:
        return f"{manifest_id}/{kind}/{self.version_dir_name(version, sha256)}/{storage_name}"

    def commit(self, staged: StagedArtifact, manifest_id: str, version: int, *,
               insert_row: Optional[Callable[[], None]] = None) -> str:
        """Promote staged bytes to an immutable version and record it via ``insert_row``.

        If ``insert_row`` raises, the promotion is rolled back so nothing unverifiable
        remains reachable.
        """
        if not _MANIFEST_ID_RE.fullmatch(manifest_id):
            raise SynthesisStorageError("invalid manifest id")
        if not isinstance(version, int) or not 1 <= version <= 999:
            raise SynthesisStorageError("artifact version must be 1-999")
        self.ensure_root()
        kind = staged.kind
        manifest_dir = self.root / manifest_id
        kind_dir = manifest_dir / kind
        for directory in (manifest_dir, kind_dir):
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError:
                pass
            if directory.is_symlink() or not directory.is_dir():
                raise SynthesisStorageError("the artifact directory is not a private directory")
        version_dir = kind_dir / self.version_dir_name(version, staged.sha256)
        rel_path = self.version_rel_path(manifest_id, kind, version, staged.sha256,
                                         staged.storage_name)
        journal = self.staging / f"{staged.job_id}.json"
        payload = {"manifest_id": manifest_id, "kind": kind, "version": version,
                   "rel_path": rel_path, "sha256": staged.sha256, "bytes": staged.bytes,
                   "staged": str(staged.path)}
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
            _fsync_dir(kind_dir)
            if insert_row is not None:
                insert_row()
        except BaseException:
            if promoted:
                shutil.rmtree(version_dir, ignore_errors=True)
                _fsync_dir(kind_dir)
            journal.unlink(missing_ok=True)
            raise
        journal.unlink(missing_ok=True)
        try:
            staged.path.parent.rmdir()
        except OSError:
            pass
        return rel_path

    def _walk_open(self, rel_parts: tuple[str, ...]) -> int:
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

    def read_artifact(self, rel_path: str, expected_sha256: str, expected_bytes: int) -> bytes:
        """Read one artifact, verifying its recorded size and hash before anyone sees it."""
        if not _SHA_RE.fullmatch(expected_sha256) or not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise SynthesisStorageError("this artifact has no verifiable content hash")
        parts = PurePosixPath(rel_path).parts
        if (len(parts) != 4 or not _MANIFEST_ID_RE.fullmatch(parts[0])
                or parts[1] not in SYNTHESIS_KINDS
                or not _VERSION_DIR_RE.fullmatch(parts[2])
                or not _STORAGE_NAME_RE.fullmatch(parts[3])):
            raise SynthesisStorageError("invalid artifact storage path")
        try:
            fd = self._walk_open(parts)
        except (OSError, FileNotFoundError):
            raise SynthesisStorageError("artifact file is missing") from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise SynthesisStorageError("artifact is not a regular file")
            if info.st_size != expected_bytes:
                raise SynthesisIntegrityError("artifact size no longer matches its record")
            digest = hashlib.sha256()
            chunks: list[bytes] = []
            with os.fdopen(fd, "rb") as stream:
                fd = -1  # fdopen owns the descriptor now
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(chunk)
                    chunks.append(chunk)
            if digest.hexdigest() != expected_sha256:
                raise SynthesisIntegrityError("artifact bytes no longer match their record")
            return b"".join(chunks)
        finally:
            if fd >= 0:
                os.close(fd)

    def discard_staging(self, job_id: str) -> None:
        if not _JOB_RE.fullmatch(job_id):
            return
        shutil.rmtree(self.staging / job_id, ignore_errors=True)
        (self.staging / f"{job_id}.json").unlink(missing_ok=True)

    def reconcile(self, is_known: Callable[[str], bool]) -> list[str]:
        """Remove promoted version files no DB row references (crash between promote and insert).

        ``is_known`` receives the manifest-relative path (``<manifest>/<kind>/vNNN-...``).
        Staging leftovers are discarded. Returns removed version directories.
        """
        removed: list[str] = []
        if not self.root.is_dir():
            return removed
        for manifest_dir in sorted(self.root.iterdir()):
            if not manifest_dir.is_dir() or manifest_dir.name.startswith("."):
                continue
            for kind_dir in sorted(manifest_dir.iterdir()):
                if not kind_dir.is_dir():
                    continue
                for version_dir in sorted(kind_dir.iterdir()):
                    if not version_dir.is_dir():
                        continue
                    rel = f"{manifest_dir.name}/{kind_dir.name}/{version_dir.name}"
                    if not is_known(rel):
                        shutil.rmtree(version_dir, ignore_errors=True)
                        removed.append(rel)
        for job_dir in (sorted(self.staging.iterdir()) if self.staging.is_dir() else []):
            if job_dir.name.endswith(".json"):
                continue
            shutil.rmtree(job_dir, ignore_errors=True)
        return removed
