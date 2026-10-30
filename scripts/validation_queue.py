#!/usr/bin/env python3
"""Run Hutch validation through the machine-wide Varve queue.

The queue is a machine-wide admission and receipt service that lives in a
separate checkout. Hutch deliberately does not import Varve code and does not
assume a sibling-checkout path. Adoption is explicit:

    export VARVE_QUEUE_CLI=/absolute/path/to/varve/scripts/quality/validation-queue.mjs
    npm run queue -- status
    npm run queue -- run --label "pytest: focused" --class shared -- \
        uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_x.py

`--queue-cli` overrides the environment variable for one invocation. With
neither set, the wrapper exits 2 and explains the opt-in; there is no implicit
cross-repository default.

The queue keeps its own state and receipts machine-wide. Receipt identity
includes the repository common directory and HEAD, so Hutch never reuses a
Varve receipt and Varve never reuses a Hutch receipt. Receipts are local cache
evidence only, never CI evidence.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV_VAR = "VARVE_QUEUE_CLI"
USAGE = """usage: validation_queue.py [--queue-cli <path>] <queue args...>

Examples:
  validation_queue.py status
  validation_queue.py history --limit 10
  validation_queue.py run --label "pytest: focused" --class shared -- pytest -q tests/test_x.py

The queue CLI must be configured with --queue-cli or VARVE_QUEUE_CLI. There is
no implicit sibling-checkout default.
"""


def _extract_queue_cli(argv: list[str]) -> tuple[str | None, list[str]]:
    """Remove one --queue-cli option from argv, preserving every other token."""
    remaining: list[str] = []
    queue_cli: str | None = None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--queue-cli":
            if index + 1 >= len(argv):
                raise ValueError("--queue-cli requires a path")
            queue_cli = argv[index + 1]
            index += 2
            continue
        if argument.startswith("--queue-cli="):
            queue_cli = argument.split("=", 1)[1]
            index += 1
            continue
        remaining.append(argument)
        index += 1
    return queue_cli, remaining


def _resolve_queue_cli(explicit: str | None) -> Path:
    configured = explicit or os.environ.get(ENV_VAR)
    if not configured:
        raise ValueError(
            f"no queue CLI configured; set {ENV_VAR}=/path/to/varve/"
            "scripts/quality/validation-queue.mjs or pass --queue-cli "
            "(explicit opt-in; no cross-repository default)",
        )
    path = Path(configured).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"queue CLI not found: {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print(USAGE, end="", file=sys.stderr)
        return 2
    if arguments in (["-h"], ["--help"]):
        print(USAGE, end="")
        return 0

    try:
        explicit, forwarded = _extract_queue_cli(arguments)
        queue_cli = _resolve_queue_cli(explicit)
    except ValueError as error:
        print(f"validation-queue: {error}", file=sys.stderr)
        return 2

    if not forwarded:
        print(USAGE, end="", file=sys.stderr)
        return 2

    node = shutil.which("node")
    if node is None:
        print("validation-queue: node is required to run the queue CLI", file=sys.stderr)
        return 2

    completed = subprocess.run(
        [node, str(queue_cli), *forwarded],
        cwd=Path.cwd(),
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
