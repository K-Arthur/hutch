#!/usr/bin/env python3
"""Generate and verify the stable Hutch agent map (.ai/repo-map.generated.md).

Why this exists
---------------
Agents need a compact, trustworthy map of the repository before searching it.
The map is generated from names in the committed/staged tree
(`git ls-files --cached`), never from working-tree content, so ordinary source
edits do not churn it; adding, removing or moving a tracked file does. No
timestamps and no source line counts: two checkouts at the same commit produce
the same bytes.

What it contains
----------------
* top-level layout with tracked-file counts;
* Python package layout under `src/hutch/`;
* `tests/` layout, plus `desktop/`, `app/src/` and `website/` source layout;
* Rust crates discovered from `desktop/*/Cargo.toml`;
* entry-point table for always-loaded and on-demand agent docs;
* the largest frozen files from `.file-size-baseline.json` (top 10).

Ignored/derived trees (installed environments, worktrees, `node_modules`,
`docs/**/artifacts`, root build output) never enter the counts. Output is capped
at MAX_LINES lines.

Usage
-----
    uv run --frozen --no-sync python scripts/generate_agent_map.py --write
        Regenerate the map (run after staging file additions or removals).
    ... --check
        Default: exit 1 when the map is missing or stale; writes nothing.
    ... --write / --check with --json? no: text only.

Exit codes: 0 ok, 1 missing/stale map on --check, 2 the tree cannot be read.
Tests: tests/test_agent_map.py.
Policy narrative: docs/agent-workflow.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ".ai/repo-map.generated.md"
BASELINE_PATH = ".file-size-baseline.json"
MAX_LINES = 120
FROZEN_ROWS = 10

#: Directory names that are never project structure (installed, cached, derived).
EXCLUDED_DIR_NAMES = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".worktrees",
    ".hypothesis", ".pytest_cache", ".validation", "playwright-report",
    "test-results", ".venv-build",
})

#: Root-level output/report trees that are not source, plus ``.ai`` (agent guidance, which the fixed
#: ENTRY_POINTS table below lists instead of a file count for the directory), ``.pipeline`` (dated
#: program records) and ``research_notes`` (research write-ups). None of them is project structure.
EXCLUDED_ROOT_DIRS = frozenset({"build", "dist", "var", "reports", "coverage", "htmlcov", ".ai",
                                ".pipeline", "research_notes"})

#: (path, what it is for) - fixed, so adding a doc does not require map churn.
ENTRY_POINTS = (
    ("AGENTS.md", "always-loaded index and hard rules (<=150 lines)"),
    (".ai/skills/README.md", "reusable task playbooks"),
    (".ai/roles/README.md", "on-demand role files"),
    ("docs/agent-workflow.md", "context economy, guard commands, quiet validation"),
    ("docs/architecture.md", "architecture overview"),
    ("docs/repository-hygiene.md", "ignore, commit and packaging policy"),
    ("docs/realignment/tool-calling.md", "canonical tool contract and evidence"),
)

CARGO_PATTERN = re.compile(r"desktop/([^/]+)/Cargo\.toml")


class AgentMapError(RuntimeError):
    """The tracked tree cannot be read or the rendered map is unusable."""


def _excluded(relative: str) -> bool:
    parts = relative.split("/")
    if parts[0] in EXCLUDED_ROOT_DIRS:
        return True
    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return True
    if parts[0] == "docs" and "artifacts" in parts:
        return True
    return False


def tracked_paths(root: Path = ROOT) -> list[str]:
    """Sorted paths in the git index (committed or staged), excluded trees removed."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "-z"],
            check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise AgentMapError("git is not available") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise AgentMapError(f"git ls-files failed: {detail}") from exc
    names = [name for name in completed.stdout.split("\0") if name]
    return sorted(name for name in names if not _excluded(name))


def _group_counts(paths: Iterable[str], prefix: str = "") -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in paths:
        if prefix and not path.startswith(prefix):
            continue
        rest = path[len(prefix):]
        if not rest:
            continue
        pieces = rest.split("/")
        label = pieces[0] + "/" if len(pieces) > 1 else "(root files)"
        counts[label] += 1
    return counts


def _sorted_groups(counts: Counter[str], leaf_label: str) -> list[tuple[str, int]]:
    return sorted(
        ((label, count) for label, count in counts.items()),
        key=lambda item: (item[0] != leaf_label, item[0]))


def _table(labels: tuple[str, str], rows: list[tuple[str, int]], second: str = "Tracked files") -> list[str]:
    lines = [f"| {labels[0]} | {second} |", "| --- | ---: |"]
    lines.extend(f"| `{name}` | {count} |" for name, count in rows)
    return lines


def frozen_files(root: Path = ROOT) -> list[tuple[str, int]] | None:
    """Top frozen files from the baseline, largest first; None when unreadable."""
    try:
        raw = json.loads((Path(root) / BASELINE_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    files = raw.get("files") if isinstance(raw, dict) else None
    if not isinstance(files, dict):
        return None
    ranked = sorted(
        ((str(path), lines) for path, lines in files.items()
         if isinstance(path, str) and isinstance(lines, int) and not isinstance(lines, bool)),
        key=lambda item: (-item[1], item[0]))
    return ranked[:FROZEN_ROWS]


def _prefixed_groups(paths: list[str], prefix: str, label_prefix: str) -> list[tuple[str, int]]:
    counts = _group_counts(paths, prefix)
    return [(f"{label_prefix}{name}", count) for name, count in sorted(counts.items())]


def render(root: Path = ROOT) -> str:
    """Render the deterministic map for the index at root."""
    paths = tracked_paths(root)
    if not paths:
        raise AgentMapError(f"no tracked files found under {root}")

    lines: list[str] = [
        "# Hutch agent map (generated)",
        "",
        "Generated from the committed/staged tree (`git ls-files --cached`) by",
        "`python scripts/generate_agent_map.py --write`. Deterministic: no timestamps,",
        "no source line counts, no unstaged or ignored files. Ordinary source edits do",
        "not change it; stage file additions or removals, then regenerate. Do not edit",
        "this file by hand.",
        "",
        f"Tracked files in scope: {len(paths)}.",
        "",
        "## Top-level layout",
        "",
    ]
    top_rows = _sorted_groups(_group_counts(paths), "(root files)")
    lines.extend(_table(("Top-level entry", "Tracked files"), top_rows))
    lines.extend(["", "## Python package: src/hutch/", ""])
    python_rows = _sorted_groups(_group_counts(paths, "src/hutch/"), "(root files)")
    lines.extend(_table(("Path", "Files in src/hutch/"), python_rows))
    lines.extend(["", "## Tests: tests/", ""])
    test_rows = _sorted_groups(_group_counts(paths, "tests/"), "(root files)")
    lines.extend(_table(("Path", "Files in tests/"), test_rows))

    lines.extend(["", "## Desktop, dashboard sources and website", ""])
    source_rows = (
        _prefixed_groups(paths, "desktop/", "desktop/")
        + _prefixed_groups(paths, "app/src/", "app/src/")
        + _prefixed_groups(paths, "website/", "website/")
    )
    lines.extend(_table(("Path", "Tracked files"), source_rows))

    lines.extend(["", "## Rust crates", ""])
    crates: list[tuple[str, str, int]] = []
    for path in paths:
        match = CARGO_PATTERN.fullmatch(path)
        if not match:
            continue
        crate = match.group(1)
        count = sum(1 for candidate in paths
                    if candidate.startswith(f"desktop/{crate}/"))
        crates.append((f"desktop/{crate}", path, count))
    if crates:
        lines.extend(["| Crate | Manifest | Tracked files |", "| --- | --- | ---: |"])
        lines.extend(f"| `{crate}` | `{manifest}` | {count} |"
                     for crate, manifest, count in sorted(crates))
    else:
        lines.append("No Rust crates found under `desktop/*/Cargo.toml`.")

    lines.extend(["", "## Entry points", "", "| Entry point | Load it for |",
                  "| --- | --- |"])
    lines.extend(f"| `{path}` | {purpose} |" for path, purpose in ENTRY_POINTS)

    lines.extend(["", "## Largest frozen files", ""])
    frozen = frozen_files(root)
    if frozen:
        lines.extend(["| File (frozen in .file-size-baseline.json) | Lines |", "| --- | ---: |"])
        lines.extend(f"| `{path}` | {count} |" for path, count in frozen)
    else:
        lines.append("No readable `.file-size-baseline.json` in this checkout.")

    lines.extend([
        "",
        "## Regenerate",
        "",
        "Regenerate with python scripts/generate_agent_map.py --write after staging additions or removals; "
        "--check (also npm run audit:agent-map) detects drift.",
    ])
    if len(lines) > MAX_LINES:
        raise AgentMapError(
            f"agent map would be {len(lines)} lines, over the {MAX_LINES}-line cap")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify the stable Hutch agent map.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true",
                      help="write .ai/repo-map.generated.md")
    mode.add_argument("--check", action="store_true",
                      help="exit 1 when the map is missing or stale (default)")
    parser.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = (args.root or ROOT).resolve()
    try:
        content = render(root)
    except AgentMapError as exc:
        print(f"Agent map generation failed: {exc}", file=sys.stderr)
        return 2
    map_path = root / MAP_PATH
    if args.write:
        try:
            map_path.parent.mkdir(parents=True, exist_ok=True)
            map_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            print(f"Agent map write failed: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote {MAP_PATH} ({len(content.splitlines())} lines).")
        return 0
    try:
        current = map_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Agent map check failed: missing {MAP_PATH}; "
              "run python scripts/generate_agent_map.py --write", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Agent map check failed to read {MAP_PATH}: {exc}", file=sys.stderr)
        return 2
    if current != content:
        print(f"Agent map check failed: {MAP_PATH} is stale; "
              "run python scripts/generate_agent_map.py --write", file=sys.stderr)
        return 1
    print(f"Agent map check passed ({len(content.splitlines())} lines; "
          f"{len(tracked_paths(root))} tracked files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
