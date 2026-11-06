"""Durable spool for results a provider has already been paid to produce.

A synchronous media API (image generation, speech synthesis) returns the finished bytes inside the
same request that bills for them. If the process dies after the provider answered and before the
media store committed, the money is spent and the bytes are gone. The spool closes that window: the
validated-by-size bytes are written to disk, atomically, *before* ``submit`` returns, and the job
ledger can later finalize from the spool instead of paying again.

Rules:

* the spool lives under the media root (``<state>/media/spool``), owner-only, and a handle is
  ``spool_<hex>`` only; anything else is refused so a handle can never name another path;
* a write is a temporary file, ``fsync``, then ``rename``, so a reader never sees a partial entry;
* each entry carries its size and SHA-256 and is re-verified on read; a mismatch is reported as
  corruption, never returned as bytes;
* an entry is removed only after the media store committed the bytes (``discard``), or by
  ``sweep`` once it is older than a bound and no live job references it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Optional

from .storage import MAX_MEDIA_BYTES

_HANDLE_RE = re.compile(r"^spool_[0-9a-f]{24}$")
SPOOL_DIRNAME = "spool"


class SpoolError(RuntimeError):
    """The spool could not store or return an entry honestly."""


def new_handle() -> str:
    return f"spool_{secrets.token_hex(12)}"


class MediaSpool:
    def __init__(self, media_root: Path | str):
        self.root = Path(media_root) / SPOOL_DIRNAME
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise SpoolError("the media spool path is not a real directory")
        os.chmod(self.root, 0o700)

    def _paths(self, handle: str) -> tuple[Path, Path]:
        if not _HANDLE_RE.fullmatch(handle or ""):
            raise SpoolError("not a spool handle")
        return self.root / f"{handle}.bin", self.root / f"{handle}.json"

    def put(self, data: bytes, *, meta: Optional[dict] = None, handle: Optional[str] = None) -> str:
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise SpoolError("the spool stores non-empty bytes only")
        if len(data) > MAX_MEDIA_BYTES:
            raise SpoolError(f"result exceeds the {MAX_MEDIA_BYTES // 1_000_000} MB media limit")
        handle = handle or new_handle()
        body, manifest = self._paths(handle)
        record = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "written": time.time(), "meta": dict(meta or {})}
        self._atomic(body, bytes(data))
        self._atomic(manifest, json.dumps(record, sort_keys=True).encode("utf-8"))
        return handle

    def _atomic(self, target: Path, payload: bytes) -> None:
        tmp = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def has(self, handle: str) -> bool:
        try:
            body, manifest = self._paths(handle)
        except SpoolError:
            return False
        return body.is_file() and manifest.is_file()

    def get(self, handle: str) -> bytes:
        body, manifest = self._paths(handle)
        try:
            record = json.loads(manifest.read_text(encoding="utf-8"))
            data = body.read_bytes()
        except (OSError, ValueError) as exc:
            raise SpoolError("the spooled result is missing or unreadable") from exc
        if len(data) != record.get("size") or hashlib.sha256(data).hexdigest() != record.get("sha256"):
            raise SpoolError("the spooled result no longer matches its recorded digest")
        return data

    def meta(self, handle: str) -> dict:
        _, manifest = self._paths(handle)
        try:
            return dict(json.loads(manifest.read_text(encoding="utf-8")).get("meta") or {})
        except (OSError, ValueError):
            return {}

    def discard(self, handle: str) -> None:
        for path in self._paths(handle):
            path.unlink(missing_ok=True)

    def sweep(self, *, keep: set[str], older_than_seconds: float = 7 * 86400.0) -> int:
        """Remove entries nothing references and that are older than the bound."""
        removed, cutoff = 0, time.time() - older_than_seconds
        for manifest in self.root.glob("spool_*.json"):
            handle = manifest.stem
            if handle in keep:
                continue
            try:
                if manifest.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            self.discard(handle)
            removed += 1
        return removed


class ResultHold:
    """Holds one synchronous result between ``submit`` and ``fetch``.

    With a :class:`MediaSpool` the bytes survive a crash and a restart. Without one (unit tests,
    or a caller that has no state directory) they live in memory and :attr:`durable` is False, so
    ``can_recover`` is honest about it."""

    def __init__(self, spool: Optional[MediaSpool] = None):
        self._spool = spool
        self._memory: dict[str, tuple[bytes, dict]] = {}

    @property
    def durable(self) -> bool:
        return self._spool is not None

    def put(self, data: bytes, meta: Optional[dict] = None) -> str:
        if self._spool is not None:
            return self._spool.put(data, meta=meta)
        if not data:
            raise SpoolError("the hold stores non-empty bytes only")
        handle = new_handle()
        self._memory[handle] = (bytes(data), dict(meta or {}))
        return handle

    def has(self, handle: str) -> bool:
        if self._spool is not None:
            return self._spool.has(handle)
        return handle in self._memory

    def get(self, handle: str) -> bytes:
        if self._spool is not None:
            return self._spool.get(handle)
        try:
            return self._memory[handle][0]
        except KeyError as exc:
            raise SpoolError("no held result for this handle") from exc

    def meta(self, handle: str) -> dict:
        if self._spool is not None:
            return self._spool.meta(handle)
        return dict(self._memory.get(handle, (b"", {}))[1])

    def discard(self, handle: str) -> None:
        if self._spool is not None:
            self._spool.discard(handle)
        self._memory.pop(handle, None)
