"""Folder source: bounded, deterministic change detection over a scoped directory.

Polling with a stat signature (size + mtime_ns) and a content hash is
deliberately boring: it cannot miss events when watches overflow, survives
sleep/restart, and costs nothing when nothing changed. Notes:

* atomic-save bursts collapse to one ``changed`` event because the scan sees
  the settled file, not the editor's temp writes;
* ``rename`` is paired from a matching delete + create with the same content
  hash inside one scan;
* a partial scan (file cap, hash budget, event cap) never reports deletions and
  defers unexamined entries to the next check;
* changes under Hutch's own state/workspace paths are recorded as ``excluded``
  so a monitor can see the feedback loop it is deliberately ignoring.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import stat as stat_module
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import CheckOutcome, EventDraft, SourceRuntime, SourceUnavailable

DEFAULT_IGNORE = (
    ".git/**", "**/.git/**", "**/*~", "**/.#*", "**/#*#", "**/.DS_Store",
    "**/*.swp", "**/*.swx", "**/*.tmp", "**/*.part", "**/*.crdownload",
)
_CHUNK = 1024 * 1024


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _matches(rel: str, patterns: tuple[str, ...]) -> bool:
    name = PurePosixPath(rel).name
    for pattern in patterns:
        if pattern in ("**", "**/*"):
            return True
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        try:
            if PurePosixPath(rel).match(pattern):
                return True
        except ValueError:
            continue
    return False


def _hash_file(path: Path, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                return "", total
            digest.update(chunk)
    return digest.hexdigest(), total


def _under(path: str, roots: tuple[str, ...]) -> bool:
    if not roots:
        return False
    resolved = os.path.realpath(path)
    for root in roots:
        root = os.path.realpath(root)
        if resolved == root or resolved.startswith(root.rstrip(os.sep) + os.sep):
            return True
    return False


def _walk(root: Path, *, max_files: int, max_depth: int, ignore: tuple[str, ...]):
    """Bounded breadth-first walk. Yields (rel, stat_result) for regular files only; symlinks are never followed."""
    import collections

    queue: collections.deque[tuple[Path, str, int]] = collections.deque([(root, "", 0)])
    seen = 0
    truncated = False
    while queue:
        directory, rel_dir, depth = queue.popleft()
        if depth > max_depth:
            truncated = True
            continue
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            truncated = True
            continue
        for entry in entries:
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            if _matches(rel, ignore):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.startswith("."):
                        continue
                    queue.append((Path(entry.path), rel, depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                info = entry.stat(follow_symlinks=False)
            except OSError:
                truncated = True
                continue
            if seen >= max_files:
                truncated = True
                return
            seen += 1
            yield rel, info


def check(config: dict, cursor: dict, *, runtime: SourceRuntime, now: datetime) -> CheckOutcome:
    raw_root = str(config.get("path") or "").strip()
    root = Path(raw_root).expanduser()
    if not raw_root or not root.is_absolute():
        raise SourceUnavailable("the watched folder must be an absolute path")
    try:
        if not root.is_dir():
            raise SourceUnavailable(f"the watched folder is not available: {root}")
    except OSError as exc:
        raise SourceUnavailable(f"the watched folder cannot be read: {exc}") from exc

    include = tuple(config.get("include") or ("**/*",))
    ignore = DEFAULT_IGNORE + tuple(config.get("ignore_globs") or ())
    max_files = max(1, min(int(config.get("max_files") or 2000), 20_000))
    max_hashes = max(1, min(int(config.get("max_hashes_per_check") or 200), max_files))
    max_hash_bytes = max(0, min(int(config.get("max_hash_bytes") or 16 * 1024 * 1024), 256 * 1024 * 1024))
    max_depth = max(1, min(int(config.get("max_depth") or 6), 32))
    settle = max(0.0, min(float(config.get("settle_seconds", 2.0)), 300.0))
    now_ts = now.timestamp()

    old: dict = dict(cursor.get("files") or {})
    new: dict[str, dict] = {}
    events: list[EventDraft] = []
    created_candidates: dict[str, dict] = {}
    hashes_used = 0
    event_budget = runtime.max_events
    truncated = False
    complete_scan = True
    seen: set[str] = set()

    def emit(draft: EventDraft) -> bool:
        nonlocal event_budget, truncated
        if len(events) >= event_budget:
            truncated = True
            return False
        events.append(draft.normalized())
        return True

    entries = list(_walk(root, max_files=max_files, max_depth=max_depth, ignore=ignore))
    if len(entries) >= max_files:
        complete_scan = False
    for rel, info in entries:
        if not _matches(rel, include):
            continue
        seen.add(rel)
        if info.st_size > max_hash_bytes:
            new[rel] = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "hash": ""}
            continue
        previous = old.get(rel)
        unchanged = (isinstance(previous, dict) and previous.get("size") == info.st_size
                     and previous.get("mtime_ns") == info.st_mtime_ns and not previous.get("excluded"))
        if unchanged:
            new[rel] = previous
            continue
        if hashes_used >= max_hashes:
            complete_scan = False
            if isinstance(previous, dict):
                new[rel] = previous          # defer: it will be re-examined next check
            continue
        hashes_used += 1
        try:
            digest, _size = _hash_file(Path(root, rel), max_hash_bytes)
        except OSError:
            truncated = True
            if isinstance(previous, dict):
                new[rel] = previous
            continue
        if digest == "":
            new[rel] = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "hash": ""}
            continue
        if _under(str(Path(root, rel)), runtime.exclude_paths):
            new[rel] = {"excluded": True, "size": info.st_size, "mtime_ns": info.st_mtime_ns}
            if not (isinstance(previous, dict) and previous.get("excluded")):
                emit(EventDraft(key=rel, kind="excluded", occurrence=_iso(info.st_mtime), content_hash=digest,
                                summary=f"change under an excluded path was ignored: {rel}", excluded=True))
            continue
        settled = (now_ts - info.st_mtime) >= settle
        if not settled:
            if isinstance(previous, dict):
                new[rel] = previous
            continue
        if isinstance(previous, dict) and not previous.get("excluded"):
            if previous.get("hash") == digest:
                new[rel] = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "hash": digest}
                continue
            if not emit(EventDraft(key=rel, kind="changed", occurrence=_iso(info.st_mtime),
                                   content_hash=digest, summary=f"changed: {rel}")):
                new[rel] = previous
                continue
        else:
            created_candidates[rel] = {"occurrence": _iso(info.st_mtime), "hash": digest}
        new[rel] = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "hash": digest}

    deleted: dict[str, str] = {}
    if complete_scan:
        for rel, entry in old.items():
            if rel in seen or rel in new:
                continue
            if _matches(rel, ignore) or not _matches(rel, include):
                continue
            if _under(str(Path(root, rel)), runtime.exclude_paths):
                continue
            deleted[rel] = entry.get("hash", "") if isinstance(entry, dict) else ""
        for rel, candidate in list(created_candidates.items()):
            if not candidate["hash"]:
                continue
            for gone, gone_digest in list(deleted.items()):
                if gone_digest and gone_digest == candidate["hash"]:
                    if emit(EventDraft(key=rel, kind="renamed", occurrence=_iso(now_ts),
                                       content_hash=candidate["hash"],
                                       summary=f"renamed: {gone} -> {rel}")):
                        deleted.pop(gone, None)
                        created_candidates.pop(rel, None)
                    break

    for rel, candidate in list(created_candidates.items()):
        if not emit(EventDraft(key=rel, kind="created", occurrence=candidate["occurrence"],
                               content_hash=candidate["hash"], summary=f"created: {rel}")):
            new.pop(rel, None)
            truncated = True
    for rel in deleted:
        emit(EventDraft(key=rel, kind="deleted", occurrence=_iso(now_ts), summary=f"deleted: {rel}"))

    material = [e for e in events if not e.excluded]
    if truncated:
        events.append(EventDraft(key=f"__truncated__:{now_ts}", kind="truncated", occurrence=_iso(now_ts),
                                 summary="more changes exist than one bounded check reports; the next check continues"))
    summary = "no change" if not material else f"{len(material)} change(s): " + ", ".join(
        f"{e.kind} {e.key}" for e in material[:3]) + ("…" if len(material) > 3 else "")
    return CheckOutcome(cursor={"files": new}, events=tuple(events), summary=summary, truncated=truncated)
