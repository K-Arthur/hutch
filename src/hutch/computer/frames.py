"""Observation frames: bounded, private, hash-verified image artifacts for computer use.

A frame is *evidence and model input*, not a durable record. Frames live in ``<run dir>/frames`` with owner-only permissions,
are verified by size and SHA-256 on every read, and the store evicts the oldest ones to stay inside a per-run budget so that a
long browsing session cannot grow without bound. Nothing here ever returns a path to a model or to the web: callers hand out
the opaque ``frame_id`` and fetch bytes through an authorized, verified read.
"""

from __future__ import annotations

import hashlib
import contextlib
try:
    import fcntl
except ImportError:  # package import stays usable; this storage boundary is Linux/POSIX only
    fcntl = None
import os
import re
import stat
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

MAX_FRAME_BYTES = 900_000            # one image; a 1280x800 UI screenshot is typically 100-400 KB as PNG
MAX_FRAME_EDGE = 2000                # long edge in pixels; provider limits are higher, this bounds image tokens
MAX_RUN_FRAME_BYTES = 8 * 1024 * 1024
MAX_RUN_FRAMES = 64

MEDIA_TYPES = {"image/png": "png", "image/jpeg": "jpg"}
_NAME_RE = re.compile(r"^f(\d{6})\.(png|jpg)$")
_FRAME_ID_RE = re.compile(r"^f\d{6}$")


class FrameError(Exception):
    """A frame could not be stored or verified; the message is safe to show to a person."""


@dataclass(frozen=True)
class ImageRef:
    """A stored frame. ``path`` is run-relative and internal; use ``public()`` for anything that leaves the process."""

    frame_id: str
    path: str
    sha256: str
    bytes: int
    media_type: str
    width: int
    height: int

    def public(self) -> dict[str, Any]:
        return {"frame_id": self.frame_id, "sha256": self.sha256, "bytes": self.bytes,
                "media_type": self.media_type, "width": self.width, "height": self.height}

    def internal(self) -> dict[str, Any]:
        return {**self.public(), "path": self.path}

    @classmethod
    def from_internal(cls, data: dict[str, Any]) -> "ImageRef":
        try:
            return cls(frame_id=str(data["frame_id"]), path=str(data["path"]), sha256=str(data["sha256"]),
                       bytes=int(data["bytes"]), media_type=str(data["media_type"]),
                       width=int(data["width"]), height=int(data["height"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise FrameError("the frame reference is incomplete") from exc


def image_size(data: bytes, media_type: str) -> tuple[int, int]:
    """Read pixel dimensions from the image header without decoding it (no imaging dependency)."""
    if media_type == "image/png":
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise FrameError("the image is not a valid PNG")
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    if media_type == "image/jpeg":
        if len(data) < 4 or data[:2] != b"\xff\xd8":
            raise FrameError("the image is not a valid JPEG")
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            if marker == 0xFF:
                index += 1
                continue
            length = struct.unpack(">H", data[index + 2:index + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[index + 5:index + 9])
                return width, height
            index += 2 + length
        raise FrameError("the JPEG has no frame header")
    raise FrameError(f"unsupported image type {media_type!r}")


class FrameStore:
    """Per-run frame directory with a byte/count budget and verified reads."""

    def __init__(self, run_dir: Path, *, max_bytes: int = MAX_RUN_FRAME_BYTES, max_frames: int = MAX_RUN_FRAMES):
        self._run_dir = Path(run_dir)
        self._dir = self._run_dir / "frames"
        self._max_bytes = max_bytes
        self._max_frames = max_frames
        self._lock = threading.Lock()

    # ------------------------------------------------------------ internals

    @contextlib.contextmanager
    def _serialized(self):
        if fcntl is None:
            raise FrameError("frame storage requires POSIX directory leases on this platform")
        with self._lock:
            self._ensure_dir()
            fd = os.open(self._dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                # Browser/native stores are separate objects; their quota and frame IDs share one run directory.
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self._dir.is_symlink() or not self._dir.is_dir():
            raise FrameError("the frame directory is not a private directory")

    def _entries(self) -> list[tuple[int, Path, int]]:
        found: list[tuple[int, Path, int]] = []
        with os.scandir(self._dir) as it:
            for entry in it:
                match = _NAME_RE.match(entry.name)
                if not match:
                    continue
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise FrameError("the frame directory contains a non-regular entry")
                found.append((int(match.group(1)), Path(entry.path), info.st_size))
        return sorted(found)

    # ------------------------------------------------------------- public

    def save(self, data: bytes, media_type: str) -> ImageRef:
        if media_type not in MEDIA_TYPES:
            raise FrameError(f"unsupported frame type {media_type!r}")
        if not data:
            raise FrameError("the capture returned no image data")
        if len(data) > MAX_FRAME_BYTES:
            raise FrameError(f"the frame is {len(data):,} bytes; the limit is {MAX_FRAME_BYTES:,}")
        width, height = image_size(data, media_type)
        if width <= 0 or height <= 0 or max(width, height) > MAX_FRAME_EDGE:
            raise FrameError(f"the frame is {width}x{height}; the long edge limit is {MAX_FRAME_EDGE}px")
        digest = hashlib.sha256(data).hexdigest()
        with self._serialized():
            entries = self._entries()
            seq = (entries[-1][0] + 1) if entries else 1
            name = f"f{seq:06d}.{MEDIA_TYPES[media_type]}"
            path = self._dir / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fchmod(stream.fileno(), 0o400)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            entries.append((seq, path, len(data)))
            total = sum(size for _, _, size in entries)
            while len(entries) > 1 and (total > self._max_bytes or len(entries) > self._max_frames):
                _, oldest, size = entries.pop(0)
                try:
                    oldest.unlink()
                except OSError:
                    pass
                total -= size
        return ImageRef(frame_id=f"f{seq:06d}", path=str(path.relative_to(self._run_dir)), sha256=digest,
                        bytes=len(data), media_type=media_type, width=width, height=height)

    def load(self, ref: ImageRef) -> bytes:
        """Return the frame bytes after verifying that the file is the one that was stored. Raises ``FrameError``."""
        if not _FRAME_ID_RE.match(ref.frame_id) or ref.media_type not in MEDIA_TYPES:
            raise FrameError("the frame reference is not valid")
        expected = f"frames/{ref.frame_id}.{MEDIA_TYPES[ref.media_type]}"
        if ref.path != expected:
            raise FrameError("the frame reference does not point into this run's frame directory")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            dir_fd = os.open(self._dir, dir_flags)
        except OSError as exc:
            raise FrameError("the frame is no longer available") from exc
        try:
            try:
                fd = os.open(f"{ref.frame_id}.{MEDIA_TYPES[ref.media_type]}", flags, dir_fd=dir_fd)
            except OSError as exc:
                raise FrameError("the frame is no longer available (it may have been superseded)") from exc
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != ref.bytes or ref.bytes > MAX_FRAME_BYTES:
                    raise FrameError("the frame does not match its recorded size")
                data = stream.read(MAX_FRAME_BYTES + 1)
        finally:
            os.close(dir_fd)
        if len(data) != ref.bytes or hashlib.sha256(data).hexdigest() != ref.sha256:
            raise FrameError("the frame failed its integrity check")
        return data

    def usage(self) -> dict[str, int]:
        with self._lock:
            if not self._dir.is_dir():
                return {"frames": 0, "bytes": 0}
            entries = self._entries()
        return {"frames": len(entries), "bytes": sum(size for _, _, size in entries)}


def new_frame_store(config: Any, bot_name: str, run_id: str) -> FrameStore:
    """The frame store for a run, rooted at the same private run directory as its artifacts."""
    return FrameStore(config.run_dir(bot_name, run_id))


def validate_frame_id(value: Optional[str]) -> str:
    if not isinstance(value, str) or not _FRAME_ID_RE.match(value):
        raise FrameError("frame ids look like f000012")
    return value
