"""Queue wrapper: explicit configuration and exact argument forwarding.

The wrapper must never assume a sibling Varve checkout. It forwards every token
after its own `--queue-cli` option unchanged, runs from the caller's cwd, and
propagates the queue CLI's exit code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "validation_queue.py"


def run_wrapper(args: list[str], queue_cli: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("VARVE_QUEUE_CLI", None)
    if queue_cli is not None:
        env["VARVE_QUEUE_CLI"] = queue_cli
    return subprocess.run(
        [sys.executable, str(WRAPPER), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def fake_queue(tmp_path: Path, body: str = "console.log(JSON.stringify(process.argv.slice(2)));") -> Path:
    path = tmp_path / "queue.mjs"
    path.write_text(body, encoding="utf-8")
    return path


def test_status_forwards_through_env(tmp_path: Path):
    fake = fake_queue(tmp_path)
    result = run_wrapper(["status"], queue_cli=str(fake))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["status"]


def test_queue_cli_option_overrides_env_and_is_not_forwarded(tmp_path: Path):
    fake = fake_queue(tmp_path)
    result = run_wrapper(
        ["--queue-cli", str(fake), "run", "--label", "x", "--", "echo", "hi"],
        queue_cli=str(tmp_path / "missing.mjs"),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["run", "--label", "x", "--", "echo", "hi"]


def test_missing_configuration_fails_clearly():
    result = run_wrapper(["status"])
    assert result.returncode == 2
    assert "VARVE_QUEUE_CLI" in result.stderr
    assert "explicit opt-in" in result.stderr


def test_missing_queue_cli_fails_clearly(tmp_path: Path):
    result = run_wrapper(["status"], queue_cli=str(tmp_path / "missing.mjs"))
    assert result.returncode == 2
    assert "not found" in result.stderr


def test_child_exit_code_is_propagated(tmp_path: Path):
    fake = fake_queue(tmp_path, "process.exit(7);")
    result = run_wrapper(["status"], queue_cli=str(fake))
    assert result.returncode == 7


def test_no_arguments_prints_usage():
    result = run_wrapper([])
    assert result.returncode == 2
    assert "usage:" in result.stderr.lower()
