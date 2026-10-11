"""Stable identity for one Hutch instance (state directory) and process.

Used by the health endpoint, the service readiness handshake and the Runtime &
Background Work surface so a client can tell *which* engine it is talking to.
The full state-directory path is never sent off-host: remote clients receive a
short opaque digest only; the local runtime endpoint may include the path.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

#: process start time, captured once at import
_STARTED_AT = time.time()


def instance_id(state_dir: str | os.PathLike[str]) -> str:
    """Short, stable, opaque identifier for one state directory."""
    resolved = str(Path(state_dir).expanduser().resolve())
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]


def process_started_at() -> str:
    """ISO-8601 UTC timestamp of this process start (module import)."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(_STARTED_AT, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def uptime_seconds(now: float | None = None) -> int:
    return max(0, int((time.time() if now is None else now) - _STARTED_AT))


def instance_info(state_dir: str | os.PathLike[str]) -> dict:
    """Instance descriptor safe to serve from the public health endpoint."""
    return {
        "id": instance_id(state_dir),
        "pid": os.getpid(),
        "started_at": process_started_at(),
    }
