"""What a staged skill update would change, in terms the owner can act on (ADR-0017 §4.4).

An update is a write path. The registry already stages new bytes, re-hashes them before applying,
and refuses a staged directory that changed after review. What it could not say is *what is
different*: an operator had to read two versions of the instructions and diff the frontmatter by
eye to notice that the new version needs a tool the Bot does not have, or that a declared
connection went from optional to required.

This module answers that question and nothing else. It is pure comparison over two directories:
no registry state, no locks, no writes. The caller decides whether a difference blocks an apply;
here every difference is reported, and the ones that change what an assistant may do or needs are
marked material so an interface can put them first.

Two honesty rules:

* A file is reported as changed only when its bytes differ, by sha256. A same-size edit with a
  restored mtime is still a change.
* The comparison is bounded. A package with more files than the registry accepts is refused
  elsewhere; here a truncated listing is reported as truncated rather than silently short.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

#: How many paths a single list may name before it is summarised.
MAX_LISTED_PATHS = 40
#: Files larger than this are hashed but not read twice for a body comparison.
MAX_COMPARED_FILE_BYTES = 4 * 1024 * 1024

_TOOL_KEY = "hutch.requires-tools"
_CONNECTION_KEY = "hutch.requires-connections"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _index(directory: Path) -> tuple[dict[str, str], int, bool]:
    """Map package-relative path to sha256, plus total bytes and whether the listing was cut short."""
    files: dict[str, str] = {}
    total = 0
    truncated = False
    skipped = 0
    for path in sorted(directory.rglob("*")):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(directory).as_posix()
            size = path.stat().st_size
        except OSError:
            skipped += 1
            continue
        total += size
        if len(files) >= 2_000:
            truncated = True
            break
        files[relative] = _hash_file(path)
    if skipped:
        truncated = True
    return files, total, truncated


def _split(value: str) -> list[str]:
    import re
    return [part for part in re.split(r"[,\s]+", value or "") if part]


def _requirement_diff(before: list[str], after: list[str]) -> dict[str, list[str]]:
    return {"added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after))}


def _listing(paths: list[str]) -> dict[str, Any]:
    listed = sorted(paths)[:MAX_LISTED_PATHS]
    return {"paths": listed, "count": len(paths), "truncated": len(paths) > len(listed)}


def _frontmatter(directory: Path) -> Optional[dict[str, Any]]:
    """Parse just enough to compare declared capabilities; malformed packages are not compared."""
    from .skills import SKILL_FILENAME, inspect_package
    try:
        parsed, _diagnostics, _hash = inspect_package(directory, enforce_bounds=False)
    except OSError:
        return None
    if parsed is None:
        return None
    return {
        "name": parsed.name,
        "description": " ".join((parsed.description or "").split()),
        "license": parsed.license or "",
        "compatibility": parsed.compatibility or "",
        "version": parsed.version or "",
        "requires_tools": list(parsed.requires_tools),
        "requires_connections": list(parsed.requires_connections),
        "allowed_tools": " ".join(_split(parsed.allowed_tools)),
        "body_bytes": len((parsed.body or "").encode("utf-8")),
        "body_sha256": hashlib.sha256((parsed.body or "").encode("utf-8")).hexdigest(),
    }


def _material_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Plain sentences for the differences that change what an assistant may do or needs."""
    notes: list[str] = []
    tools = _requirement_diff(before["requires_tools"], after["requires_tools"])
    if tools["added"]:
        notes.append("now requires the " + ", ".join(tools["added"]) + " tool(s)")
    if tools["removed"]:
        notes.append("no longer requires the " + ", ".join(tools["removed"]) + " tool(s)")
    connections = _requirement_diff(before["requires_connections"], after["requires_connections"])
    if connections["added"]:
        notes.append("now requires the " + ", ".join(connections["added"]) + " connection(s)")
    if connections["removed"]:
        notes.append("no longer requires the " + ", ".join(connections["removed"]) + " connection(s)")
    if before["allowed_tools"] != after["allowed_tools"]:
        before_set, after_set = set(_split(before["allowed_tools"])), set(_split(after["allowed_tools"]))
        widened = sorted(after_set - before_set)
        narrowed = sorted(before_set - after_set)
        if widened:
            notes.append("declares the additional allowed-tools " + ", ".join(widened))
        if narrowed:
            notes.append("drops the allowed-tools " + ", ".join(narrowed))
    if before["name"] != after["name"]:
        notes.append(f"changes the skill name from {before['name']} to {after['name']}")
    return notes


def compare_packages(installed: str | Path, staged: str | Path) -> dict[str, Any]:
    """Compare an installed package with a staged replacement.

    Returns ``{"comparable": False, "reason": ...}`` when either side cannot be read, so a caller
    shows "could not compare" instead of an empty diff that reads as "nothing changed".
    """
    installed_dir, staged_dir = Path(installed), Path(staged)
    if not installed_dir.is_dir():
        return {"comparable": False, "reason": "the installed package is not on disk"}
    if not staged_dir.is_dir():
        return {"comparable": False, "reason": "the staged update is no longer on disk"}
    before, after = _frontmatter(installed_dir), _frontmatter(staged_dir)
    if before is None or after is None:
        return {"comparable": False, "reason": "one of the packages could not be read for comparison"}

    before_files, before_bytes, before_cut = _index(installed_dir)
    after_files, after_bytes, after_cut = _index(staged_dir)
    added = [path for path in after_files if path not in before_files]
    removed = [path for path in before_files if path not in after_files]
    changed = [path for path, digest in after_files.items()
               if path in before_files and before_files[path] != digest]

    changes = {
        "comparable": True,
        "version": {"from": before["version"], "to": after["version"]},
        "description": {"from": before["description"], "to": after["description"]},
        "license": {"from": before["license"], "to": after["license"]},
        "compatibility": {"from": before["compatibility"], "to": after["compatibility"]},
        "capabilities": {
            "requires_tools": _requirement_diff(before["requires_tools"], after["requires_tools"]),
            "requires_connections": _requirement_diff(before["requires_connections"],
                                                      after["requires_connections"]),
            "allowed_tools": {"from": before["allowed_tools"], "to": after["allowed_tools"]},
        },
        "instructions": {
            "changed": before["body_sha256"] != after["body_sha256"],
            "bytes_from": before["body_bytes"],
            "bytes_to": after["body_bytes"],
        },
        "files": {
            "added": _listing(added),
            "removed": _listing(removed),
            "changed": _listing(changed),
            "count_from": len(before_files),
            "count_to": len(after_files),
            "bytes_from": before_bytes,
            "bytes_to": after_bytes,
            "incomplete": before_cut or after_cut,
        },
        "material": _material_changes(before, after),
    }
    changed_anything = bool(added or removed or changed) or changes["instructions"]["changed"]
    changes["identical"] = not changed_anything and not changes["material"]
    changes["summary"] = _summary(changes)
    return changes


def _summary(changes: dict[str, Any]) -> str:
    if changes["identical"]:
        return "the staged package is byte-identical to the installed one"
    parts: list[str] = []
    if changes["material"]:
        parts.append("; ".join(changes["material"]))
    if changes["instructions"]["changed"]:
        from_bytes = changes["instructions"]["bytes_from"]
        to_bytes = changes["instructions"]["bytes_to"]
        parts.append(f"instructions changed ({from_bytes} to {to_bytes} bytes)")
    files = changes["files"]
    for label in ("added", "removed", "changed"):
        if files[label]["count"]:
            parts.append(f"{files[label]['count']} file(s) {label}")
    return ", ".join(parts) or "metadata changed"


__all__ = ["MAX_LISTED_PATHS", "compare_packages"]
