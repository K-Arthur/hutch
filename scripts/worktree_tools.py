#!/usr/bin/env python3
"""Inspect and safely prune Hutch's concurrent-agent git worktrees.

Why this exists: parallel sessions work in checkouts under .worktrees/. Without
a guard stale trees pile up (the 2026-10-28 audit found 25 registered worktrees
and 6.3 GB under .worktrees/), and a careless cleanup can delete another
session's dirty checkout. This CLI reports every registered worktree with the
facts needed to decide, and prunes only those that are provably safe: clean,
merged, old enough and strictly inside this repository's .worktrees/ directory.
External checkouts and nested parents are reported but never removed.

Usage
-----
    uv run --frozen --no-sync python scripts/worktree_tools.py status [--json]
    uv run --frozen --no-sync python scripts/worktree_tools.py prune [--apply] [--json]

Options: --base REF (default: the main worktree's HEAD), --min-age-days N
(default 14), --root PATH (hidden test hook).

Exit codes: 0 ok (status always; prune dry-run or full success), 1 a selected
worktree could not be removed, 2 not a git repository or git failed.
Tests: tests/test_worktree_tools.py. Policy: docs/concurrent-agents.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIN_AGE_DAYS = 14
WORKTREE_DIR = ".worktrees"
SHORT_HEAD = 7
SECONDS_PER_DAY = 86_400


class WorktreeError(RuntimeError):
    """The repository or its worktree registry cannot be read."""


@dataclass
class Worktree:
    path: Path
    head: str
    branch: str | None
    detached: bool = False
    locked: bool = False
    prunable: bool = False
    main: bool = False
    current: bool = False
    external: bool = False
    nested: bool = False
    nested_parent: bool = False
    age_days: int | None = None
    dirty: int | None = None
    untracked: int | None = None
    merged: bool | None = None
    stale: bool = False

    @property
    def classification(self) -> str:
        if self.main:
            return "main"
        if self.current:
            return "current"
        if self.external:
            return "external"
        if self.nested:
            return "nested"
        return "repo-local"


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], check=False,
                              capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise WorktreeError("git is not available") from exc


def _git_ok(cwd: Path, *args: str) -> str:
    result = _run_git(cwd, *args)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        raise WorktreeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def repo_root(path: Path) -> Path:
    """The top-level worktree containing path; raises when outside git."""
    result = _run_git(Path(path), "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise WorktreeError(f"{path} is not inside a git repository")
    return Path(result.stdout.strip()).resolve()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _parse_porcelain(output: str) -> list[Worktree]:
    worktrees: list[Worktree] = []
    fields: dict[str, str] = {}

    def flush() -> None:
        if "worktree" not in fields:
            return
        branch_ref = fields.get("branch")
        worktrees.append(Worktree(
            path=Path(fields["worktree"]),
            head=fields.get("HEAD", ""),
            branch=branch_ref.removeprefix("refs/heads/") if branch_ref else None,
            detached="detached" in fields,
            locked="locked" in fields,
            prunable="prunable" in fields,
        ))

    for line in output.splitlines():
        if not line.strip():
            flush()
            fields.clear()
            continue
        key, _, value = line.partition(" ")
        fields[key] = value
    flush()
    return worktrees


def _resolve_base(main: Path, base_ref: str | None) -> tuple[str, str]:
    ref = base_ref or "HEAD"
    result = _run_git(main, "rev-parse", "--verify", ref)
    if result.returncode != 0:
        raise WorktreeError(f"cannot resolve base ref {ref!r} in main worktree {main}")
    return ref, result.stdout.strip()


def _commit_time(root: Path, commit: str) -> int | None:
    if not commit:
        return None
    result = _run_git(root, "show", "-s", "--format=%ct", commit)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _dirty_counts(worktree_path: Path) -> tuple[int, int] | None:
    if not worktree_path.is_dir():
        return None
    result = _run_git(worktree_path, "status", "--porcelain")
    if result.returncode != 0:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    untracked = sum(1 for line in lines if line.startswith("??"))
    return len(lines) - untracked, untracked


def _is_merged(root: Path, head: str, base_commit: str) -> bool | None:
    if not head:
        return None
    result = _run_git(root, "merge-base", "--is-ancestor", head, base_commit)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def build_report(root: Path = ROOT, *, base_ref: str | None = None,
                 min_age_days: int = DEFAULT_MIN_AGE_DAYS,
                 now: int | None = None) -> dict[str, Any]:
    """Collect the concurrency report for the repository containing root."""
    repo = repo_root(Path(root))
    worktrees = _parse_porcelain(_git_ok(repo, "worktree", "list", "--porcelain"))
    if not worktrees:
        raise WorktreeError(f"no registered worktrees under {repo}")
    main_path = worktrees[0].path.resolve()
    ref, base_commit = _resolve_base(main_path, base_ref)
    now_ts = int(time.time() if now is None else now)
    worktree_root = (repo / WORKTREE_DIR).resolve()
    current = Path(root).resolve()
    for worktree in worktrees:
        resolved = worktree.path.resolve()
        worktree.main = resolved == main_path
        worktree.current = resolved == current
        worktree.external = not _is_within(resolved, worktree_root)
        worktree.merged = _is_merged(repo, worktree.head, base_commit)
        counts = _dirty_counts(resolved)
        worktree.dirty, worktree.untracked = counts if counts else (None, None)
        commit_ts = _commit_time(repo, worktree.head)
        if commit_ts is not None:
            worktree.age_days = max(0, (now_ts - commit_ts) // SECONDS_PER_DAY)
    nested_scope = [worktree for worktree in worktrees if not worktree.main]
    for worktree in worktrees:
        resolved = worktree.path.resolve()
        worktree.nested = any(
            other is not worktree and _is_within(resolved, other.path.resolve())
            for other in nested_scope)
        worktree.nested_parent = any(
            other is not worktree and _is_within(other.path.resolve(), resolved)
            for other in nested_scope)
        worktree.stale = _is_stale(worktree, worktree_root, min_age_days)
    duplicate_branches = {
        branch: count for branch, count in
        _branch_counts(worktrees).items() if count > 1}
    ordered = sorted(worktrees, key=lambda wt: (not wt.main, str(wt.path)))
    return {
        "repo": str(repo),
        "base": {"ref": ref, "commit": base_commit},
        "min_age_days": min_age_days,
        "current": str(current),
        "worktree_root": str(worktree_root),
        "worktrees": [_worktree_dict(wt) for wt in ordered],
        "duplicate_branches": dict(sorted(duplicate_branches.items())),
        "candidates": [str(wt.path) for wt in ordered if wt.stale],
    }


def _branch_counts(worktrees: list[Worktree]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for worktree in worktrees:
        if worktree.branch:
            counts[worktree.branch] = counts.get(worktree.branch, 0) + 1
    return counts


def _is_stale(worktree: Worktree, worktree_root: Path, min_age_days: int) -> bool:
    resolved = worktree.path.resolve()
    return (
        not worktree.main
        and not worktree.current
        and not worktree.external
        and not worktree.nested_parent
        and not worktree.locked
        and worktree.dirty == 0
        and worktree.untracked == 0
        and worktree.merged is True
        and worktree.age_days is not None
        and worktree.age_days >= min_age_days
        and resolved != worktree_root
        and _is_within(resolved, worktree_root)
        and resolved.is_dir()
    )


def _worktree_dict(worktree: Worktree) -> dict[str, Any]:
    return {
        "path": str(worktree.path),
        "branch": worktree.branch,
        "detached": worktree.detached,
        "head": worktree.head,
        "head_short": worktree.head[:SHORT_HEAD],
        "age_days": worktree.age_days,
        "dirty": worktree.dirty,
        "untracked": worktree.untracked,
        "merged": worktree.merged,
        "locked": worktree.locked,
        "prunable": worktree.prunable,
        "main": worktree.main,
        "current": worktree.current,
        "external": worktree.external,
        "nested": worktree.nested,
        "nested_parent": worktree.nested_parent,
        "classification": worktree.classification,
        "stale": worktree.stale,
    }


def _format_table(report: dict[str, Any]) -> str:
    header = ["STALE", "CLASS", "BRANCH", "HEAD", "AGE", "DIRTY", "MERGED", "PATH"]
    rows: list[list[str]] = []
    for worktree in report["worktrees"]:
        branch = worktree["branch"] or ("detached" if worktree["detached"] else "-")
        age = "-" if worktree["age_days"] is None else f"{worktree['age_days']}d"
        dirty = ("-" if worktree["dirty"] is None
                 else f"{worktree['dirty']}+{worktree['untracked']}")
        merged = "-" if worktree["merged"] is None else (
            "yes" if worktree["merged"] else "no")
        rows.append(["yes" if worktree["stale"] else "", worktree["classification"],
                     branch, worktree["head_short"], age, dirty, merged,
                     worktree["path"]])
    widths = [max(len(str(row[index])) for row in [header] + rows)
              for index in range(len(header))]
    lines = [
        f"Worktrees for {report['repo']}",
        f"  base {report['base']['ref']} @ {report['base']['commit'][:SHORT_HEAD]}"
        f"; stale = clean + merged + at least {report['min_age_days']}d old in"
        f" {report['worktree_root']}",
        "",
        *("  ".join(str(cell).ljust(widths[index])
                    for index, cell in enumerate(row)) for row in [header] + rows),
        "",
        f"{len(rows)} worktree(s): "
        f"{sum(1 for wt in report['worktrees'] if wt['external'])} external; "
        f"{len(report['duplicate_branches'])} duplicate-branch warning(s); "
        f"{len(report['candidates'])} stale candidate(s).",
    ]
    return "\n".join(lines)


def _format_prune(report: dict[str, Any]) -> str:
    lines: list[str] = []
    if report["applied"]:
        lines.append(f"Removed {len(report['removed'])} stale worktree(s).")
        lines.extend(f"  removed {path}" for path in report["removed"])
        lines.extend(f"  error {error}" for error in report["errors"])
    elif report["candidates"]:
        lines.append(f"Prune dry run: {len(report['candidates'])} stale candidate(s), "
                     "nothing removed.")
        lines.extend(f"  candidate {path}" for path in report["candidates"])
        lines.append("Re-run with --apply to remove them.")
    else:
        lines.append("Prune dry run: no stale candidates.")
    return "\n".join(lines)


def _prune(root: Path, *, base_ref: str | None, min_age_days: int,
           apply: bool) -> tuple[dict[str, Any], list[str]]:
    report = build_report(root, base_ref=base_ref, min_age_days=min_age_days)
    candidates = [Path(path) for path in report["candidates"]]
    # Deepest first so a nested child goes before its parent.
    ordered = sorted(candidates, key=lambda path: (-len(path.parts), str(path)))
    removed: list[str] = []
    errors: list[str] = []
    if apply:
        repo = Path(report["repo"])
        for path in ordered:
            result = _run_git(repo, "worktree", "remove", str(path))
            if result.returncode == 0:
                removed.append(str(path))
            else:
                errors.append(f"{path}: {(result.stderr or '').strip()}")
        prune_result = _run_git(repo, "worktree", "prune")
        if prune_result.returncode != 0:
            errors.append(f"worktree prune: {(prune_result.stderr or '').strip()}")
    report.update({"applied": apply, "removed": removed, "errors": errors})
    return report, errors


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base", default=None, help="base ref for merged checks (default: main worktree HEAD)")
    parser.add_argument("--min-age-days", type=int, default=DEFAULT_MIN_AGE_DAYS,
                        help=f"minimum commit age for pruning (default {DEFAULT_MIN_AGE_DAYS})")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect and safely prune Hutch's concurrent-agent worktrees.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="report registered worktrees")
    _add_common_options(status)
    prune = subparsers.add_parser("prune", help="remove safe stale worktrees")
    _add_common_options(prune)
    prune.add_argument("--apply", action="store_true",
                       help="actually remove candidates (default: dry run)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.min_age_days < 0:
        print("--min-age-days must be zero or greater", file=sys.stderr)
        return 2
    root = (args.root or ROOT).resolve()
    try:
        if args.command == "status":
            report = build_report(root, base_ref=args.base,
                                  min_age_days=args.min_age_days)
            if args.json:
                print(json.dumps(report, sort_keys=True))
            else:
                print(_format_table(report))
            return 0
        report, errors = _prune(root, base_ref=args.base,
                                min_age_days=args.min_age_days, apply=args.apply)
    except WorktreeError as exc:
        print(f"Worktree tool failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(_format_prune(report))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
