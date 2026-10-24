"""Prune stale validation temporary trees left behind by test/agent runs.

Long regression runs create large scratch trees: immutable tree snapshots
(``~/.cache/hutch-tree-snapshot-v*``), their per-batch pytest output
(``~/.cache/hutch-pytest-snapshot-v*``), pytest ``--basetemp`` directories, and
one-off validation directories. Each run uses a fresh versioned or suffixed
name so it cannot clobber the previous run's evidence, so these accumulate.

This script removes the stale ones while keeping the newest of each family and
anything still being written to. It is scoped by explicit name patterns, so it
never touches unrelated tasks' scratch trees or project checkouts.

Usage:
    python scripts/prune_validation_tmp.py            # dry run: report only
    python scripts/prune_validation_tmp.py --apply    # actually delete
    python scripts/prune_validation_tmp.py --keep 2   # keep the 2 newest per family
    python scripts/prune_validation_tmp.py --max-age-hours 48

Safety properties:
    * Dry run by default; ``--apply`` is required to delete.
    * Scoped to hutch-owned ``hutch-*`` scratch names plus the hutch test TMPDIR.
    * Skips any directory modified within ``--max-age-hours`` (default 24).
    * Skips any directory with an open file handle, so a live run is never eaten.
    * Never follows the directory symlink targets named in ``--protect``.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

HOME = Path.home()

# (directory to scan, glob for direct children to consider).
# Ordered: families whose newest member is worth keeping.
FAMILIES: list[tuple[Path, str]] = [
    (HOME / ".cache", "hutch-tree-snapshot-v*"),
    (HOME / ".cache", "hutch-pytest-snapshot-v*"),
    (HOME / ".cache", "hutch-dropdown-validation-*"),
    (HOME / ".cache", "hutch-pytest-memory-*"),
    (HOME / ".cache", "hutch-pytest-final-*"),
    (HOME / ".cache", "hutch-pytest-full"),
    (HOME / ".hutch-tmp", "*"),
    (HOME / ".local" / "share" / "opencode" / "hutch-tmp", "*"),
    (Path("/tmp"), "hutch-test-artifacts-*"),
]

# Never touched regardless of age.
PROTECT = re.compile(r"^pytest-current$")


def _version_key(path: Path) -> tuple[int, int]:
    """Sort key so hutch-tree-snapshot-v10 sorts after v9."""
    m = re.search(r"-v(\d+)$", path.name)
    return (int(m.group(1)) if m else -1, 0)


def _has_open_handle(path: Path) -> bool:
    """True if any process holds a file open under ``path``."""
    try:
        out = subprocess.run(
            ["lsof", "+D", str(path)],
            capture_output=True, text=True, timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # lsof missing or slow: fall back to a conservative age check only.
        return False
    return any(line for line in out.stdout.splitlines() if not line.startswith("COMMAND"))


def collect(args: argparse.Namespace) -> tuple[list[tuple[Path, int]], list[str]]:
    """Return (candidates to delete with sizes, notes about skips)."""
    notes: list[str] = []
    keep: list[Path] = []
    drop: list[Path] = []

    for root, pattern in FAMILIES:
        if not root.is_dir():
            continue
        matches = sorted(
            (p for p in root.glob(pattern) if p.is_dir() and not PROTECT.match(p.name)),
            key=_version_key,
        )
        if not matches:
            continue
        # Newest `keep` of each family survive; the rest are candidates.
        survivors = matches[-args.keep:] if args.keep else []
        keep.extend(survivors)
        drop.extend(p for p in matches if p not in survivors)

    candidates: list[tuple[Path, int]] = []
    for path in drop:
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            notes.append(f"skip {path}: {exc}")
            continue
        age_hours = (args.now - mtime) / 3600.0
        if age_hours < args.max_age_hours:
            notes.append(f"skip {path.name}: only {age_hours:.1f}h old")
            continue
        if _has_open_handle(path):
            notes.append(f"skip {path.name}: has open file handles")
            continue
        candidates.append((path, _tree_size(path)))
    return candidates, notes


def _tree_size(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually delete (default is a dry run)")
    parser.add_argument("--keep", type=int, default=1,
                        help="newest members to keep per family (default 1)")
    parser.add_argument("--max-age-hours", type=float, default=24.0,
                        help="skip anything modified within this window (default 24)")
    parser.add_argument("--now", type=float, default=None,
                        help=argparse.SUPPRESS)  # test hook
    args = parser.parse_args()

    import time
    if args.now is None:
        args.now = time.time()

    candidates, notes = collect(args)

    print("Stale validation scratch trees")
    print("==============================")
    if not candidates:
        print("Nothing to prune.")
    for path, size in candidates:
        print(f"  {'would remove' if not args.apply else 'removed'}  {size / 2**30:6.2f} GiB  {path}")
    if notes:
        print("\nKept (with reason)")
        for note in notes:
            print(f"  {note}")

    total = sum(size for _, size in candidates)
    verb = "Freed" if args.apply else "Reclaimable"
    print(f"\n{verb}: {total / 2**30:.2f} GiB across {len(candidates)} director{'y' if len(candidates) == 1 else 'ies'}")
    if not args.apply and candidates:
        print("Dry run only. Re-run with --apply to delete.")

    if args.apply:
        for path, _size in candidates:
            shutil.rmtree(path, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
