"""Linux workspace writes anchored to directory descriptors, with revision checks.

Approval waits do not hold a lock. Hutch writers lock the workspace and compare the
reviewed revision again before atomic replacement. External host processes do not
participate in this lock; this is not protection from a hostile workspace owner.
"""
from __future__ import annotations

from contextlib import contextmanager
from ..platforms import locking as fcntl
import hashlib
import os
from pathlib import Path
import stat
import uuid


def destination(path: str, workspace: Path) -> tuple[Path, tuple[str, ...]]:
    ws = workspace.resolve()
    raw = Path(path)
    relative = raw.relative_to(ws) if raw.is_absolute() else raw
    if not relative.parts or any(part == ".." for part in relative.parts):
        raise ValueError("write destination must be a file inside the workspace")
    return ws, relative.parts


@contextmanager
def parent_fd(workspace: Path, parts: tuple[str, ...], *, create: bool = False):
    fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in parts[:-1]:
            if create:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def revision_at(fd: int, name: str) -> dict:
    try:
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return {"exists": False}
    with os.fdopen(handle, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("write destination must be a regular file, without symlinks")
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("file changed while its revision was being read; review again")
        return {"exists": True, "sha256": digest, "device": after.st_dev, "inode": after.st_ino,
                "size": after.st_size, "modified_ns": after.st_mtime_ns, "changed_ns": after.st_ctime_ns,
                "mode": stat.S_IMODE(after.st_mode)}


def revision(workspace: Path, parts: tuple[str, ...]) -> dict:
    try:
        with parent_fd(workspace, parts) as fd:
            return revision_at(fd, parts[-1])
    except FileNotFoundError:
        return {"exists": False}


def replace_reviewed(workspace: Path, parts: tuple[str, ...], content: str, expected: dict, begin_effect) -> None:
    lock = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if revision(workspace, parts) != expected:
            raise ValueError("file changed after review; request a new approval before writing")
        refusal = begin_effect()
        if refusal:
            raise ValueError(refusal)
        with parent_fd(workspace, parts, create=True) as fd:
            temporary = f".hutch-write-{uuid.uuid4().hex}"
            try:
                handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                    # Keep ordinary permissions; do not copy executable privilege bits.
                    os.fchmod(stream.fileno(), expected.get("mode", 0o600) & 0o777)
                if revision_at(fd, parts[-1]) != expected:
                    raise ValueError("file changed after review; request a new approval before writing")
                os.replace(temporary, parts[-1], src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=fd)
                except FileNotFoundError:
                    pass
    finally:
        os.close(lock)
