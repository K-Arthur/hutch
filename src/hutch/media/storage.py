"""Durable, content-addressed storage for generated media (stills, SVG, audio, video).

Layout under ``<state>/media``::

    media/
      .staging/<job>/                       per-job private staging
      .staging/<job>.json                   commit journal, written before promotion
      <media_id>/v<NNN>-<sha8>/<name>       immutable promoted versions
      <media_id>/v<NNN>-<sha8>/manifest.json  self-describing version metadata

Commit protocol (mirrors ``documents/storage.py``): stage the bytes and fsync them →
write the journal → promote with ``os.replace`` into a fresh per-version directory
(manifest first, then content) → fsync both directories → insert the SQLite row (the
CALLER's transaction — this module returns paths and hashes and never opens the
database) → clear the journal. A crash between promotion and the row insert leaves a
version that no query can reach, so reconciliation deletes it. Schema v54 has no
media-versions table, so every promoted version carries its own ``manifest.json``
(mime, sha256, size, kind, dimensions...) and serving re-verifies size + SHA-256
against it before anyone sees bytes — a row whose bytes went missing fails honestly
instead of serving unverified content.

Every path component is created without following symlinks (``O_NOFOLLOW`` +
``dir_fd`` walks, mirroring ``documents/storage.py`` and ``tools/filewrite.py``),
version files are chmod ``0400``, and directories are ``0700``.
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
from typing import Any, Callable, Optional, Union

from ..config import hutchConfig

#: formats hutch can genuinely produce/accept; anything else is refused, never disguised
MEDIA_FORMATS = ("png", "jpeg", "webp", "svg+xml", "webm", "mp4", "wav")

MIME_BY_FORMAT = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "svg+xml": "image/svg+xml",
    "webm": "video/webm",
    "mp4": "video/mp4",
    "wav": "audio/wav",
}

EXT_BY_FORMAT = {
    "png": ".png",
    "jpeg": ".jpg",
    "webp": ".webp",
    "svg+xml": ".svg",
    "webm": ".webm",
    "mp4": ".mp4",
    "wav": ".wav",
}

FORMAT_BY_MIME = {mime: fmt for fmt, mime in MIME_BY_FORMAT.items()}

#: 96 MB hard ceiling on one media asset (video-sized, not novel-sized)
MAX_MEDIA_BYTES = 96_000_000

#: most assets one staging job may hold (content + poster + alternates)
MAX_MEDIA_PER_JOB = 8

MAX_NAME_CHARS = 120
_MAX_MANIFEST_CHARS = 16_000
_STAGING_INFIX = ".staging"
_MEDIA_ID_RE = re.compile(r"^media_[0-9a-f]{16}$")
_VERSION_DIR_RE = re.compile(r"^v(\d{3})-[0-9a-f]{8}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_STORAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MANIFEST_NAME = "manifest.json"

#: manifest keys a caller may set via ``commit(meta=...)``; everything else is derived
_MANIFEST_META_KEYS = frozenset({
    "kind", "width", "height", "duration_seconds", "alt_text", "backend", "generated_by",
})


class MediaStorageError(ValueError):
    """A media request could not be honoured; nothing was promoted."""


class MediaIntegrityError(MediaStorageError):
    """Stored bytes no longer match their recorded version."""


def new_media_id() -> str:
    """A fresh media id ('media_' + 16 lowercase hex), matching the block contract."""
    return f"media_{secrets.token_hex(8)}"


def new_job_id() -> str:
    """A fresh staging job id (24 hex chars)."""
    return secrets.token_hex(12)


@dataclass
class StagedMedia:
    job_id: str
    path: Path
    storage_name: str
    sha256: str
    bytes: int
    format: str


def sanitize_media_name(display_name: str, fmt: str) -> str:
    """Derive a safe ASCII storage name; the canonical format extension is always kept
    so a storage name can never misrepresent its type."""
    if fmt not in MEDIA_FORMATS:
        raise MediaStorageError(f"unsupported media format: {fmt}")
    raw = str(display_name or "").strip()
    raw = raw.replace("\\", "/").rsplit("/", 1)[-1]
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-_")
    if len(raw) > MAX_NAME_CHARS:
        stem, dot, ext = raw.rpartition(".")
        raw = (stem[: MAX_NAME_CHARS - len(ext) - 1] + "." + ext) if dot else raw[:MAX_NAME_CHARS]
        raw = raw.strip(".-_")
    suffix = EXT_BY_FORMAT[fmt]
    dot = raw.rfind(".")
    stem = raw[:dot] if dot > 0 else raw
    raw = (re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")[: MAX_NAME_CHARS - len(suffix)]
           or "media") + suffix
    if not _STORAGE_NAME_RE.fullmatch(raw):
        raise MediaStorageError("the file name could not be made safe for storage")
    return raw


def _fsync_dir(path: Union[Path, int]) -> None:
    if isinstance(path, int):
        fd = path
        os.fsync(fd)
        return
    handle = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


class MediaStorage:
    """Filesystem half of the media pipeline; identity lives in the caller's rows."""

    def __init__(self, config_or_root: Union[hutchConfig, Path, str]):
        if isinstance(config_or_root, hutchConfig):
            self.root = config_or_root.state_dir / "media"
        else:
            self.root = Path(config_or_root)
        self.staging = self.root / _STAGING_INFIX

    # ------------------------------------------------------------- layout

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise MediaStorageError("the media store root is not a private directory")
        os.chmod(self.root, 0o700)
        self.staging.mkdir(exist_ok=True, mode=0o700)
        if self.staging.is_symlink() or not self.staging.is_dir():
            raise MediaStorageError("the media staging directory is not a private directory")

    def version_dir_name(self, version: int, sha256: str) -> str:
        return f"v{version:03d}-{sha256[:8]}"

    def version_rel_path(self, media_id: str, version: int, sha256: str, storage_name: str) -> str:
        return f"{media_id}/{self.version_dir_name(version, sha256)}/{storage_name}"

    # ------------------------------------------------------------- staging

    def stage_bytes(self, job_id: str, fmt: str, display_name: str, data: bytes) -> StagedMedia:
        """Write complete candidate bytes into private staging and fsync them.

        At most ``MAX_MEDIA_PER_JOB`` assets may share one staging job (a video and
        its poster, alternates for a batch); a ninth is refused before it is written.
        """
        if fmt not in MEDIA_FORMATS:
            raise MediaStorageError(f"unsupported media format: {fmt}")
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise MediaStorageError("media bytes are empty")
        if len(data) > MAX_MEDIA_BYTES:
            raise MediaStorageError(
                f"media exceeds the {MAX_MEDIA_BYTES // 1_000_000} MB storage limit")
        if not re.fullmatch(r"[0-9a-f]{8,48}", job_id):
            raise MediaStorageError("invalid staging job id")
        self.ensure_root()
        job_dir = self.staging / job_id
        try:
            job_dir.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if job_dir.is_symlink() or not job_dir.is_dir():
            raise MediaStorageError("the staging directory is not a private directory")
        existing = [entry for entry in list(job_dir.iterdir())
                    if entry.is_file() and not entry.is_symlink()]
        if len(existing) >= MAX_MEDIA_PER_JOB:
            raise MediaStorageError(
                f"staging job already holds {len(existing)} assets; the per-job limit is "
                f"{MAX_MEDIA_PER_JOB}")
        storage_name = sanitize_media_name(display_name, fmt)
        path = job_dir / storage_name
        if path.exists() or path.is_symlink():
            raise MediaStorageError("a staged asset with this name already exists in the job")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        digest = hashlib.sha256(data).hexdigest()
        return StagedMedia(job_id=job_id, path=path, storage_name=storage_name,
                           sha256=digest, bytes=len(data), format=fmt)

    # ------------------------------------------------------------- commit

    def commit(self, staged: StagedMedia, media_id: str, version: int, *,
               insert_row: Callable[[], None],
               meta: Optional[dict[str, Any]] = None,
               poster: Optional[StagedMedia] = None) -> str:
        """Promote staged bytes to an immutable version and record it via ``insert_row``.

        ``insert_row`` must persist the identity row (its own transaction — for the
        v54 schema that is a ``media_jobs`` transition carrying the payload). If it
        raises, the promotion is rolled back so nothing unverifiable remains.
        ``poster`` optionally promotes a second staged asset (from the SAME staging
        job) into the same version directory; the manifest records its hash so the
        /poster route can re-verify it.
        """
        if not _MEDIA_ID_RE.fullmatch(media_id):
            raise MediaStorageError("invalid media id")
        if not isinstance(version, int) or not 1 <= version <= 999:
            raise MediaStorageError("media version must be 1–999")
        if poster is not None and poster.job_id != staged.job_id:
            raise MediaStorageError("a poster must be staged under the same staging job")
        if poster is not None and poster.path == staged.path:
            raise MediaStorageError("the poster must be a distinct staged asset")
        manifest: dict[str, Any] = {
            "media_id": media_id,
            "version": version,
            "format": staged.format,
            "mime": MIME_BY_FORMAT[staged.format],
            "sha256": staged.sha256,
            "bytes": staged.bytes,
            "storage_name": staged.storage_name,
        }
        for key, value in dict(meta or {}).items():
            if key not in _MANIFEST_META_KEYS:
                raise MediaStorageError(f"unknown media manifest field: {key}")
            if value is not None:
                manifest[key] = value
        if poster is not None:
            manifest["poster"] = {
                "name": poster.storage_name,
                "format": poster.format,
                "mime": MIME_BY_FORMAT[poster.format],
                "sha256": poster.sha256,
                "bytes": poster.bytes,
            }
        if len(json.dumps(manifest)) > _MAX_MANIFEST_CHARS:
            raise MediaStorageError("media manifest metadata exceeds the storage limit")
        self.ensure_root()
        media_dir = self.root / media_id
        try:
            media_dir.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if media_dir.is_symlink() or not media_dir.is_dir():
            raise MediaStorageError("the media directory is not a private directory")
        version_dir = media_dir / self.version_dir_name(version, staged.sha256)
        rel_path = self.version_rel_path(media_id, version, staged.sha256, staged.storage_name)
        journal = self.staging / f"{staged.job_id}.json"
        payload = {"media_id": media_id, "version": version, "rel_path": rel_path,
                   "sha256": staged.sha256, "bytes": staged.bytes, "staged": str(staged.path)}
        fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        promoted = False
        try:
            version_dir.mkdir(mode=0o700)
            manifest_path = version_dir / _MANIFEST_NAME
            mfd = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                          | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(mfd, "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(manifest_path, 0o400)
            target = version_dir / staged.storage_name
            os.replace(staged.path, target)
            os.chmod(target, 0o400)
            if poster is not None:
                poster_target = version_dir / poster.storage_name
                os.replace(poster.path, poster_target)
                os.chmod(poster_target, 0o400)
            promoted = True
            _fsync_dir(version_dir)
            _fsync_dir(media_dir)
            insert_row()
        except BaseException:
            if promoted:
                shutil.rmtree(version_dir, ignore_errors=True)
                _fsync_dir(media_dir)
            journal.unlink(missing_ok=True)
            raise
        journal.unlink(missing_ok=True)
        self._try_rmdir_staging(staged.job_id)
        return rel_path

    def _try_rmdir_staging(self, job_id: str) -> None:
        job_dir = self.staging / job_id
        try:
            job_dir.rmdir()
        except OSError:
            pass

    # ------------------------------------------------------------- serving

    def _walk_open(self, rel_parts: tuple[str, ...]) -> int:
        """Open ``rel_parts`` under the root without following symlinks; returns an fd."""
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        dir_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
        try:
            for part in rel_parts[:-1]:
                next_fd = os.open(part, flags | getattr(os, "O_DIRECTORY", 0), dir_fd=dir_fd)
                os.close(dir_fd)
                dir_fd = next_fd
            return os.open(rel_parts[-1], flags, dir_fd=dir_fd)
        finally:
            os.close(dir_fd)

    def _read_fd_bounded(self, fd: int, limit: int = MAX_MEDIA_BYTES) -> bytes:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise MediaStorageError("this media entry is not a regular file")
        if info.st_size > limit:
            raise MediaIntegrityError("media file exceeds the storage limit")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def locate(self, media_id: str, version: int) -> tuple[str, dict[str, Any]]:
        """Find the promoted version directory for ``(media_id, version)`` without
        following symlinks, and return ``(version dir name, manifest)``.

        Schema v54 has no media-versions table; the manifest written atomically at
        commit time is the version's self-description. A directory whose manifest is
        missing or corrupt is treated as absent (it was never fully promoted).
        """
        if not _MEDIA_ID_RE.fullmatch(media_id):
            raise MediaStorageError("no such media id")
        if not isinstance(version, int) or not 1 <= version <= 999:
            raise MediaStorageError("no such media version")
        prefix = f"v{version:03d}-"
        try:
            media_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                               | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            raise MediaStorageError("the media store is missing") from None
        try:
            dir_fd = os.open(media_id, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                             | getattr(os, "O_NOFOLLOW", 0), dir_fd=media_fd)
        except OSError:
            raise MediaStorageError("no such media id") from None
        try:
            found: Optional[str] = None
            with os.scandir(dir_fd) as entries:
                for entry in entries:
                    if entry.name.startswith(prefix) and _VERSION_DIR_RE.fullmatch(entry.name) \
                            and entry.is_dir(follow_symlinks=False):
                        # Two dirs for one version would mean a crashed double promotion;
                        # the highest sha8 wins deterministically.
                        if found is None or entry.name > found:
                            found = entry.name
            if found is None:
                raise MediaStorageError("no such media version")
        finally:
            os.close(dir_fd)
            os.close(media_fd)
        manifest = self._read_manifest(media_id, found)
        return found, manifest

    def _read_manifest(self, media_id: str, version_dir: str) -> dict[str, Any]:
        try:
            fd = self._walk_open((media_id, version_dir, _MANIFEST_NAME))
        except OSError:
            raise MediaStorageError("this media version was never fully promoted") from None
        try:
            raw = self._read_fd_bounded(fd, limit=_MAX_MANIFEST_CHARS)
        finally:
            os.close(fd)
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise MediaStorageError("this media version's manifest is unreadable") from None
        if not isinstance(manifest, dict) or not _SHA_RE.fullmatch(str(manifest.get("sha256", ""))) \
                or not isinstance(manifest.get("bytes"), int):
            raise MediaStorageError("this media version's manifest is incomplete")
        return manifest

    def read_version(self, media_id: str, version: int) -> tuple[bytes, dict[str, Any]]:
        """Read a version and verify it against its manifest before anyone sees it.

        Raises ``MediaStorageError`` when the version is missing (never promoted, or
        deleted by reconciliation) and ``MediaIntegrityError`` when the stored bytes
        no longer match the recorded size or SHA-256.
        """
        version_dir, manifest = self.locate(media_id, version)
        expected_sha = str(manifest["sha256"])
        expected_bytes = int(manifest["bytes"])
        storage_name = str(manifest.get("storage_name") or "")
        if not _STORAGE_NAME_RE.fullmatch(storage_name):
            raise MediaStorageError("this media version's manifest names no storable file")
        try:
            fd = self._walk_open((media_id, version_dir, storage_name))
        except (OSError, FileNotFoundError):
            raise MediaStorageError("media content file is missing") from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise MediaStorageError("media content is not a regular file")
            if info.st_size != expected_bytes:
                raise MediaIntegrityError("media size no longer matches its recorded version")
            data = self._read_fd_bounded(fd)
        finally:
            os.close(fd)
        if len(data) != expected_bytes:
            raise MediaIntegrityError("media size no longer matches its recorded version")
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha:
            raise MediaIntegrityError("media failed its recorded SHA-256 integrity check")
        return data, manifest

    def read_poster(self, media_id: str, version: int) -> tuple[bytes, dict[str, Any]]:
        """Read the version's poster asset, hash-verified against the manifest.

        Returns ``(bytes, poster manifest entry)``. Raises ``MediaStorageError``
        when this version has no poster.
        """
        version_dir, manifest = self.locate(media_id, version)
        poster = manifest.get("poster")
        if not isinstance(poster, dict):
            raise MediaStorageError("this media version has no poster")
        name = str(poster.get("name") or "")
        expected_sha = str(poster.get("sha256") or "")
        expected_bytes = poster.get("bytes")
        if not _STORAGE_NAME_RE.fullmatch(name) or not _SHA_RE.fullmatch(expected_sha) \
                or not isinstance(expected_bytes, int):
            raise MediaStorageError("this media version's poster record is incomplete")
        try:
            fd = self._walk_open((media_id, version_dir, name))
        except (OSError, FileNotFoundError):
            raise MediaStorageError("poster file is missing") from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise MediaStorageError("poster is not a regular file")
            if info.st_size != expected_bytes:
                raise MediaIntegrityError("poster size no longer matches its recorded version")
            data = self._read_fd_bounded(fd)
        finally:
            os.close(fd)
        if hashlib.sha256(data).hexdigest() != expected_sha:
            raise MediaIntegrityError("poster failed its recorded SHA-256 integrity check")
        return data, poster

    def version_path_for_serve(self, media_id: str, version_dir: str, storage_name: str) -> Path:
        """Resolve a version path AFTER the hash check, for streaming responses."""
        return self.root / media_id / version_dir / storage_name

    # ------------------------------------------------------------- removal

    def remove_version(self, media_id: str, version_dir: str) -> None:
        if not _MEDIA_ID_RE.fullmatch(media_id) or not _VERSION_DIR_RE.fullmatch(version_dir):
            return
        shutil.rmtree(self.root / media_id / version_dir, ignore_errors=True)


def reconcile_media_store(config_or_root: Union[hutchConfig, Path, str],
                          version_exists: Callable[[str, int], bool], *,
                          max_staging_age: float = 24 * 3600) -> dict[str, int]:
    """Crash recovery: delete unreferenced versions and abandoned staging.

    ``version_exists(media_id, version)`` must consult the committed SQLite rows
    (``media_jobs`` results, or whatever ledger the integrator keeps). A promoted
    version without a row was never visible, so deletion loses nothing; staging
    older than ``max_staging_age`` has no live owner.
    """
    storage = MediaStorage(config_or_root)
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
    for media_dir in list(storage.root.iterdir()):
        if not media_dir.is_dir() or media_dir.is_symlink() or media_dir.name == _STAGING_INFIX:
            continue
        if not _MEDIA_ID_RE.fullmatch(media_dir.name):
            continue
        media_id = media_dir.name
        live_versions = 0
        for version_dir in list(media_dir.iterdir()):
            match = _VERSION_DIR_RE.fullmatch(version_dir.name) \
                if version_dir.is_dir() and not version_dir.is_symlink() else None
            if match is None:
                continue
            if version_exists(media_id, int(match.group(1))):
                live_versions += 1
                continue
            shutil.rmtree(version_dir, ignore_errors=True)
            removed_versions += 1
        if live_versions == 0:
            shutil.rmtree(media_dir, ignore_errors=True)
    return {"removed_versions": removed_versions, "removed_staging": removed_staging}
