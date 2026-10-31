"""Immutable per-run tool artifacts and the model-facing output cap (PF-2, ADR-0003).

Split out of ``runtime/steps.py``, which is frozen over its size cap. The behaviour is
unchanged: text artifacts are written with ``O_EXCL|O_NOFOLLOW``, fixed at 0400, fsynced, and
their sha256 recorded so a download can be re-verified. What the model sees is a bounded
prefix; the full text survives as a verifiable artifact rather than being silently lost.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from ..tools import ToolContext

DEFAULT_TOOL_LIMIT = 12_000   # chars shown to the model per tool call unless the bot overrides it (PF-2)

MAX_ARTIFACT_BYTES = 4_000_000  # MAX_TOOL_OUTPUT is one million Unicode characters.
MAX_WORKSPACE_FILE_ARTIFACT_BYTES = 4_000_000
MAX_RUN_ARTIFACT_BYTES = 16_000_000


def run_artifact_bytes(artifact_dir: Path) -> int:
    total = 0
    try:
        entries = os.scandir(artifact_dir)
    except FileNotFoundError:
        return 0
    with entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise OSError("artifact directory contains a non-regular entry")
            total += info.st_size
    return total


def save_artifact(ctx: ToolContext, tool: str, text: str) -> tuple[str, str, int]:
    """Write an immutable tool-output version and return its run-relative path, hash and byte size."""
    run_dir = ctx.config.run_dir(ctx.bot.name, ctx.run.id)
    art = run_dir / "artifacts"
    art.mkdir(parents=True, exist_ok=True, mode=0o700)
    if art.is_symlink():
        raise OSError("artifact directory may not be a symbolic link")
    content = text.encode("utf-8", errors="replace")
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds the 4 MB storage limit")
    if run_artifact_bytes(art) + len(content) > MAX_RUN_ARTIFACT_BYTES:
        raise ValueError("run artifacts exceed the 16 MB storage limit")
    digest = hashlib.sha256(content).hexdigest()
    slug = re.sub(r"[^a-z0-9_-]+", "-", tool.lower()).strip("-")[:40] or "tool"
    for version in range(1, 1_000_000):
        path = art / f"{version:03d}-{slug}.txt"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fchmod(stream.fileno(), 0o400)
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return str(path.relative_to(run_dir)), digest, len(content)
    raise OSError("too many artifact versions in one run")


def snapshot_workspace_file(ctx: ToolContext, path: str, content: str) -> dict[str, Any]:
    """Save the exact text accepted by a successful write_file action as a bounded artifact."""
    if not isinstance(path, str) or not path:
        raise ValueError("the written file path is unavailable")
    if not isinstance(content, str):
        raise ValueError("the written file content is unavailable")
    workspace = ctx.workspace.resolve()
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            relative = Path(os.path.abspath(candidate)).relative_to(workspace)
        except ValueError:
            raise ValueError("the written file is outside this run's workspace") from None
    else:
        relative = candidate
    parts = relative.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("the written file path is not a safe workspace-relative path")
    if len(content.encode("utf-8")) > MAX_WORKSPACE_FILE_ARTIFACT_BYTES:
        raise ValueError("the file exceeds the 4 MB downloadable snapshot limit")
    ref, digest, byte_size = save_artifact(ctx, "workspace_file", content)
    raw_name = PurePosixPath(path.replace("\\", "/")).name
    download_name = re.sub(r"[^A-Za-z0-9._-]+", "-", raw_name).strip("._-")[:120] or "workspace-file.txt"
    return {
        "artifact": ref,
        "sha256": digest,
        "bytes": byte_size,
        "name": download_name,
        "path": "/".join(parts),
    }


def truncate_for_model(ctx: ToolContext, tool: str, output: str) -> tuple[str, Optional[dict[str, Any]]]:
    """PF-2: cap model context while keeping an immutable, verifiable copy of the full tool output."""
    from ..tools.base import MAX_TOOL_OUTPUT
    limit = int(ctx.bot.tool_limits.get(tool, DEFAULT_TOOL_LIMIT))
    if limit <= 0:
        limit = DEFAULT_TOOL_LIMIT
    limit = min(limit, MAX_TOOL_OUTPUT)
    if len(output) <= limit:
        return output, None
    try:
        rel, digest, byte_size = save_artifact(ctx, tool, output)
    except (OSError, ValueError) as exc:
        note = f"\n... [{len(output) - limit:,} of {len(output):,} characters omitted; full output snapshot unavailable: {exc}]"
        return output[:limit] + note, None
    note = f"\n... [{len(output) - limit:,} of {len(output):,} characters omitted; full output saved as artifact {rel}]"
    return output[:limit] + note, {"path": rel, "sha256": digest, "bytes": byte_size}


__all__ = ["DEFAULT_TOOL_LIMIT", "MAX_ARTIFACT_BYTES", "MAX_RUN_ARTIFACT_BYTES",
           "MAX_WORKSPACE_FILE_ARTIFACT_BYTES", "run_artifact_bytes", "save_artifact",
           "snapshot_workspace_file", "truncate_for_model"]
