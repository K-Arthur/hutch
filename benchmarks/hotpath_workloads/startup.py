"""Cold CLI startup: subprocess wall time for hutch version / hutch status.

Each sample is a fresh process with an isolated HUTCH_STATE_DIR, matching how a shell invocation
starts. The interpreter runs with the caller's PYTHONPATH, so the measured source tree is the
worktree this harness lives in (recorded in detail.module_file).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

SAMPLES_FULL = 11
SAMPLES_QUICK = 5


def _command() -> list[str]:
    entry = Path(sys.executable).parent / "hutch"
    return [str(entry)] if entry.exists() else [sys.executable, "-m", "hutch.cli"]


def _module_file(env: dict[str, str]) -> str:
    try:
        out = subprocess.run([sys.executable, "-c", "import hutch; print(hutch.__file__)"],
                             env=env, capture_output=True, text=True, check=True, timeout=60)
        return out.stdout.strip().splitlines()[-1]
    except (OSError, subprocess.CalledProcessError, IndexError):
        return "unknown"


def run(quick: bool, state) -> list[dict]:
    n = SAMPLES_QUICK if quick else SAMPLES_FULL
    cli_state = state / "cli-state"
    env = dict(os.environ, HUTCH_STATE_DIR=str(cli_state))
    env.pop("HUTCH_TESTING", None)
    command = _command()
    subprocess.run(command + ["init"], env=env, capture_output=True, check=True, timeout=180)
    cases: list[dict] = []
    for name, args in (("startup.cli_version_ms", ["version"]), ("startup.cli_status_ms", ["status"])):
        subprocess.run(command + args, env=env, capture_output=True, check=True, timeout=120)
        samples = []
        for _ in range(n):
            started = time.perf_counter()
            subprocess.run(command + args, env=env, capture_output=True, check=True, timeout=120)
            samples.append((time.perf_counter() - started) * 1000.0)
        cases.append({"name": name, "unit": "ms", "samples": samples, "better": "lower",
                      "note": "fresh process, cold interpreter + imports, isolated state dir",
                      "detail": {"runs": n, "module_file": _module_file(env),
                                 "command": Path(command[0]).name}})
    return cases
