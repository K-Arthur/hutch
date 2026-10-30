"""Whole-Bot deletion file cleanup: the private fsynced manifest and managed-path removal."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from .bot_deletion_plan import _MANIFEST_NAME, _MANIFEST_ROOT, _ManifestError, _canonical, _managed_path_ok, _now_iso, _safe_component


def _sha256_bytes(data: bytes) -> str:
    """SHA-256 hex of one byte string."""
    return hashlib.sha256(data).hexdigest()


def _chmod_private(path: Path) -> None:
    """Best-effort private permissions on a directory we own."""
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _fsync_dir(path: Path) -> None:
    """Best-effort directory fsync so a recorded path list survives a crash."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _manifest_dir(state_dir: Path, request_id: str) -> Path:
    """The private per-request directory holding the only managed-path record."""
    return Path(state_dir) / _MANIFEST_ROOT / request_id


def _write_manifest(state_dir: Path, request_id: str, bot_id: str, paths: list[str]) -> tuple[str, Path]:
    """Write a 0700, fsynced manifest of managed paths and return its SHA-256."""
    if not _safe_component(request_id):
        raise _ManifestError('the deletion request cannot name a manifest directory')
    for relative in paths:
        if not _managed_path_ok(relative):
            raise _ManifestError('a cleanup path is outside the managed state shapes')
    root = Path(state_dir) / _MANIFEST_ROOT
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _chmod_private(root)
    target = root / request_id
    target.mkdir(mode=0o700, exist_ok=True)
    _chmod_private(target)
    body = _canonical({'request_id': request_id, 'bot_id': bot_id, 'created_at': _now_iso(),
                       'paths': paths}).encode('utf-8')
    temporary = target / (_MANIFEST_NAME + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, target / _MANIFEST_NAME)
    _fsync_dir(target)
    _fsync_dir(root)
    return _sha256_bytes(body), target


def _remove_manifest_dir(state_dir: Path, request_id: str) -> None:
    """Remove the manifest record after its managed paths are gone; tolerate a missing one."""
    target = _manifest_dir(state_dir, request_id)
    try:
        (target / _MANIFEST_NAME).unlink(missing_ok=True)
        (target / (_MANIFEST_NAME + '.tmp')).unlink(missing_ok=True)
        os.rmdir(target)
    except FileNotFoundError:
        pass


def _read_manifest(state_dir: Path, request_id: str, expected_hash: str) -> dict[str, Any]:
    """Read and verify one cleanup manifest; any doubt is an honest cleanup error."""
    path = _manifest_dir(state_dir, request_id) / _MANIFEST_NAME
    try:
        data = path.read_bytes()
    except OSError:
        raise _ManifestError('the cleanup manifest is missing; the erased rows are gone and '
                             'the managed files may remain') from None
    if _sha256_bytes(data) != expected_hash:
        raise _ManifestError('the cleanup manifest does not match its recorded hash; managed files may remain')
    try:
        body = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise _ManifestError('the cleanup manifest is unreadable; managed files may remain') from None
    if not isinstance(body, dict) or body.get('request_id') != request_id:
        raise _ManifestError('the cleanup manifest does not describe this request; managed files may remain')
    paths = body.get('paths')
    if not isinstance(paths, list) or any(not isinstance(item, str) or not _managed_path_ok(item)
                                          for item in paths):
        raise _ManifestError('the cleanup manifest lists paths outside the managed shapes; nothing was deleted')
    return body


def _delete_tree(path: Path) -> None:
    """Depth-first deletion without following symlinks; missing entries are tolerated."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise _ManifestError('a recorded cleanup path is a symbolic link; nothing was deleted')
    if not stat.S_ISDIR(info.st_mode):
        os.unlink(path)
        return
    with os.scandir(path) as entries:
        names = [entry.name for entry in entries]
    for name in names:
        child = path / name
        try:
            child_info = os.lstat(child)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(child_info.st_mode):
            _delete_tree(child)
        else:
            os.unlink(child)
    os.rmdir(path)


def _remove_managed_path(state_dir: Path, relative: str) -> None:
    """Delete one recorded managed path, refusing symlinks or escapes; missing entries are fine."""
    if not _managed_path_ok(relative):
        raise _ManifestError('a recorded cleanup path is outside the managed shapes; nothing was deleted')
    current = Path(state_dir)
    for part in Path(relative).parts:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode):
            raise _ManifestError('a recorded cleanup path crosses a symbolic link; nothing was deleted')
    _delete_tree(current)


# ----------------------------------------------------------- cleanup state
