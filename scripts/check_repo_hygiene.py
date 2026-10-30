"""Check staged blobs, without changing the index or reading secret values.

Use with Gitleaks: this checks ignore policy and size, not credential contents.
Existing unchanged evidence is not subject to the 5 MiB limit.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


MAX_BYTES = 5 * 1024 * 1024


def git(root: Path, *args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], input=input,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True).stdout


def check(root: Path) -> list[str]:
    paths = [p for p in git(root, "diff", "--cached", "--name-only", "-z",
                           "--diff-filter=ACMRT").split(b"\0") if p]
    if not paths:
        return []
    # --no-index is essential: ordinary check-ignore skips tracked/staged files.
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "-z", "--stdin"],
        input=b"\0".join(paths) + b"\0", stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    if result.returncode not in (0, 1):
        raise RuntimeError("Git could not evaluate ignore rules")
    ignored = set(result.stdout.split(b"\0"))
    entries = {}
    for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if entry:
            metadata, path = entry.split(b"\t", 1)
            mode, oid, stage = metadata.split()
            if stage == b"0":
                entries[path] = (mode, oid)
    errors = []
    for path in paths:
        label = repr(path.decode("utf-8", errors="backslashreplace"))
        if path in ignored:
            errors.append(f"{label}: matches ignore policy; review before committing")
        mode, oid = entries[path]
        # A submodule's commit need not exist in this repository's object store.
        if mode == b"160000":
            continue
        size = int(git(root, "cat-file", "-s", oid.decode("ascii")))
        if size > MAX_BYTES:
            errors.append(f"{label}: staged blob is {size} bytes (limit {MAX_BYTES}); "
                          "review release storage or a deliberate policy exception")
    return errors


def main() -> int:
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
        errors = check(root)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Repository hygiene check failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    if errors:
        print("Staged repository hygiene findings:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print("Staged repository hygiene check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
