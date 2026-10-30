#!/usr/bin/env python3
"""Guard the context-economy file-size budget for Hutch source files.

Policy
------
* A new source file (Python, JS/MJS, TS, Astro, and hand-maintained CSS) may not
  exceed MAX_LINES (400) lines. Split at 350-400 lines instead of growing it.
* Existing over-cap files are frozen in .file-size-baseline.json and may only
  shrink. The baseline is deterministic and compact:
  {"files":{"path":lines,...},"max_lines":400,"version":1} with sorted keys.
* Generated output is not source: src/hutch/server/static/ui.css and
  model-switcher.css (built from app/src), website/app.css and
  website/styles.min.css (built from the site sources), any *.min.css and the
  vendored static/vendor/ tree are skipped. So are installed environments,
  worktrees, hidden tool state, native build output, root build directories, and
  the 381 MB docs/**/artifacts evidence trees.
* Hand-written dashboard CSS (static/style.css, studio.css, ...) IS source and is
  budgeted. The 2026-10-28 brief called the whole static/*.css directory build
  output, but package.json shows only the two files above are generated; this
  guard stays honest about that.
* Rust is native glue reviewed on its own path and is outside this guard today.

Usage
-----
    uv run --frozen --no-sync python scripts/audit_context_hygiene.py
        Check the tree; exit 1 on a new over-cap file or a frozen file that grew.
    ... --report
        Print the inventory, frozen count and top offenders; never fails.
    ... --update
        Rewrite the baseline after an intentional split. Shrink-only: refuses to
        add a new over-cap file or raise a frozen value. A checkout without a
        baseline bootstraps one on the first update.

Exit codes: 0 pass/report/update, 1 policy violation or refused update,
2 missing or invalid baseline. Tests: tests/test_context_hygiene.py.
Policy narrative: docs/agent-workflow.md. Git commit policy is separate
(.gitignore; see docs/repository-hygiene.md).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterator

MAX_LINES = 400
BASELINE_VERSION = 1
BASELINE_NAME = ".file-size-baseline.json"
ROOT = Path(__file__).resolve().parent.parent
MAX_REPORTED = 40

#: Extensions that count as source for the budget.
SOURCE_SUFFIXES = (".py", ".js", ".mjs", ".ts", ".astro")

#: Generated CSS outputs, relative to the repository root.
GENERATED_CSS = frozenset({
    "src/hutch/server/static/ui.css",              # app/src/input.css
    "src/hutch/server/static/model-switcher.css",  # app/src/model-switcher.css
    "website/app.css",                             # website/src/input.css
    "website/styles.min.css",                      # website/styles.css
})

#: Vendored frontend bundles are not project source.
VENDOR_PREFIX = "src/hutch/server/static/vendor/"

#: Top-level trees that are never project source.
EXCLUDED_ROOT_NAMES = frozenset({
    "build", "dist", "var", "reports", "coverage", "htmlcov",
    "playwright-report", "test-results",
})

#: desktop/ subtrees that are native build output.
DESKTOP_OUTPUT = frozenset({"target", "binaries", "gen"})


class BaselineError(RuntimeError):
    """The baseline is missing, corrupt, or written for a different policy."""


def _excluded_dir(parts: tuple[str, ...]) -> bool:
    """True when a directory (relative path parts) must not be walked."""
    if not parts:
        return False
    if any(part.startswith(".") for part in parts):
        # Hidden directories are tool state: .git, .venv, .worktrees,
        # .hypothesis, .validation, .pytest_cache, .opencode, .agents, ...
        return True
    if any(part in {"node_modules", "__pycache__"} for part in parts):
        return True
    if parts[0] == "docs" and "artifacts" in parts:
        return True
    if parts[0] in EXCLUDED_ROOT_NAMES:
        return True
    if parts[0] == "desktop" and len(parts) > 1 and parts[1] in DESKTOP_OUTPUT:
        return True
    if parts[:2] == ("desktop", "process-guard") and len(parts) > 2 and parts[2] == "target":
        return True
    joined = "/".join(parts)
    if joined == VENDOR_PREFIX.rstrip("/") or joined.startswith(VENDOR_PREFIX):
        return True
    return False


def _has_source_suffix(relative: str) -> bool:
    if relative.endswith(SOURCE_SUFFIXES):
        return True
    if relative.endswith(".css"):
        return not (relative in GENERATED_CSS or relative.endswith(".min.css")
                    or relative.startswith(VENDOR_PREFIX))
    return False


def iter_source_files(root: Path = ROOT) -> Iterator[Path]:
    """Yield budgeted source files under root in deterministic order."""
    base = Path(root)
    for directory, dirnames, filenames in os.walk(base, topdown=True):
        here = Path(directory)
        relative_dir = here.relative_to(base)
        parts = () if relative_dir == Path(".") else relative_dir.parts
        dirnames[:] = sorted(name for name in dirnames if not _excluded_dir(parts + (name,)))
        for name in sorted(filenames):
            relative = "/".join((*parts, name))
            if _has_source_suffix(relative):
                yield here / name


def line_count(path: Path) -> int:
    """Line count using the same convention as wc -l for trailing newlines."""
    data = path.read_bytes()
    return len(data.splitlines()) if data else 0


def collect_inventory(root: Path = ROOT) -> dict[str, int]:
    """Sorted mapping of repository-relative source path to line count."""
    base = Path(root)
    inventory: dict[str, int] = {}
    for path in iter_source_files(base):
        inventory[path.relative_to(base).as_posix()] = line_count(path)
    return dict(sorted(inventory.items()))


def load_baseline(path: Path) -> dict[str, int]:
    """Load and validate a baseline; raise BaselineError when unusable."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BaselineError(
            f"missing file-size baseline {path}; see docs/agent-workflow.md") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot read file-size baseline {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("version") != BASELINE_VERSION:
        raise BaselineError(
            f"{path} is not a version {BASELINE_VERSION} file-size baseline")
    if raw.get("max_lines") != MAX_LINES:
        raise BaselineError(
            f"{path} records max_lines={raw.get('max_lines')!r} but the policy is "
            f"{MAX_LINES}; review the policy change before rewriting the baseline")
    files = raw.get("files")
    if not isinstance(files, dict) or any(
            not isinstance(rel, str) or not isinstance(lines, int) or lines < 0
            for rel, lines in files.items()):
        raise BaselineError(f"{path} has a malformed files map")
    return dict(sorted(files.items()))


def format_baseline(frozen: dict[str, int]) -> str:
    """Render the deterministic, compact baseline document."""
    payload = {"files": dict(sorted(frozen.items())), "max_lines": MAX_LINES,
               "version": BASELINE_VERSION}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"


def write_baseline(path: Path, frozen: dict[str, int]) -> None:
    path.write_text(format_baseline(frozen), encoding="utf-8")


def violations(inventory: dict[str, int], baseline: dict[str, int]) -> list[str]:
    """Policy findings: new over-cap files and frozen files that grew."""
    findings: list[str] = []
    for relative, lines in inventory.items():
        if lines <= MAX_LINES:
            continue
        frozen = baseline.get(relative)
        if frozen is None:
            findings.append(
                f"new source file over {MAX_LINES} lines: {relative} ({lines} lines); split it")
        elif lines > frozen:
            findings.append(
                f"frozen file grew: {relative} ({frozen} -> {lines} lines); "
                "split it instead of extending it")
    return findings


def check(root: Path = ROOT, baseline_path: Path | None = None) -> list[str]:
    """Return policy findings for root; raises BaselineError if unusable."""
    base = Path(root)
    baseline_file = Path(baseline_path) if baseline_path else base / BASELINE_NAME
    return violations(collect_inventory(base), load_baseline(baseline_file))


def update(root: Path = ROOT,
           baseline_path: Path | None = None) -> tuple[dict[str, int], list[str]]:
    """Rewrite the baseline shrink-only. Returns (frozen, refusal reasons)."""
    base = Path(root)
    baseline_file = Path(baseline_path) if baseline_path else base / BASELINE_NAME
    inventory = collect_inventory(base)
    current = {relative: lines for relative, lines in inventory.items()
               if lines > MAX_LINES}
    old = load_baseline(baseline_file) if baseline_file.exists() else None
    errors: list[str] = []
    if old is not None:
        for relative in sorted(current):
            if relative not in old:
                errors.append(
                    f"refuse to add {relative} ({current[relative]} lines) to the "
                    "baseline; split it")
            elif current[relative] > old[relative]:
                errors.append(
                    f"refuse to raise {relative} from {old[relative]} to "
                    f"{current[relative]} lines; split it")
    if errors:
        return {}, errors
    write_baseline(baseline_file, current)
    return current, []


def _top_offenders(inventory: dict[str, int], limit: int = 20) -> list[tuple[int, str]]:
    ranked = sorted(((lines, relative) for relative, lines in inventory.items()
                     if lines > MAX_LINES), reverse=True)
    return ranked[:limit]


def _print_report(inventory: dict[str, int], baseline: dict[str, int],
                  findings: list[str], baseline_name: str) -> None:
    over = sum(1 for lines in inventory.values() if lines > MAX_LINES)
    print(f"Context hygiene report: {len(inventory)} source files scanned; "
          f"{over} over {MAX_LINES} lines; {len(baseline)} frozen in {baseline_name}.")
    if findings:
        print(f"Policy findings ({len(findings)}):")
        for finding in findings[:MAX_REPORTED]:
            print(f"  {finding}")
        if len(findings) > MAX_REPORTED:
            print(f"  ... and {len(findings) - MAX_REPORTED} more")
    else:
        print("Baseline is shrink-only and currently satisfied.")
    top = _top_offenders(inventory)
    if top:
        print("Top offenders:")
        for lines, relative in top:
            print(f"  {lines:6d}  {relative}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Hutch's file-size context budget.")
    parser.add_argument("--report", action="store_true",
                        help="print the inventory and top offenders; never fails")
    parser.add_argument("--update", action="store_true",
                        help="rewrite the shrink-only baseline after an intentional split")
    parser.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = (args.root or ROOT).resolve()
    baseline_path = root / BASELINE_NAME
    try:
        if args.update:
            frozen, errors = update(root, baseline_path)
            if errors:
                print("Refusing to update the file-size baseline:", file=sys.stderr)
                for error in errors:
                    print(f"  {error}", file=sys.stderr)
                return 1
            print(f"Updated {BASELINE_NAME}: {len(frozen)} frozen over-cap source files.")
            return 0
        inventory = collect_inventory(root)
        try:
            baseline = load_baseline(baseline_path)
        except BaselineError:
            if not args.report:
                raise
            print(f"Note: no usable baseline at {baseline_path}; showing the raw inventory.")
            baseline = {}
    except (OSError, BaselineError) as exc:
        print(f"Context hygiene check failed: {exc}", file=sys.stderr)
        return 2
    findings = violations(inventory, baseline)
    if args.report:
        _print_report(inventory, baseline, findings, BASELINE_NAME)
        return 0
    if findings:
        print(f"Context hygiene violations ({len(findings)}):", file=sys.stderr)
        for finding in findings[:MAX_REPORTED]:
            print(f"  {finding}", file=sys.stderr)
        if len(findings) > MAX_REPORTED:
            print(f"  ... and {len(findings) - MAX_REPORTED} more", file=sys.stderr)
        return 1
    print(f"Context hygiene check passed ({len(inventory)} source files; "
          f"{len(baseline)} frozen over-cap files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
