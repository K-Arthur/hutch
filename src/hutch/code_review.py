"""Owner-run verification and pruning for retained coding handoff worktrees.

A handoff ends with changes in an isolated worktree. "Changes ready" only means
the coding CLI exited and Git saw files; it says nothing about whether the work
passes a check. This module runs one explicit owner-supplied command in that
worktree and records a content-free receipt. Deleting the worktree lives in
``code_prune`` and is a separate, confirmed step.

Nothing here accepts a command inferred from repository content, and no output
is persisted: the receipt holds a digest of the argv, the exit code, the
duration, a fingerprint of the changed tree and the time.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

from . import procguard
from .models import iso, utcnow

DEFAULT_TIMEOUT_SECONDS = 900
MAX_TIMEOUT_SECONDS = 3600
MAX_CAPTURED_BYTES = 64 * 1024
MAX_FINGERPRINT_BYTES = 8 * 1024 * 1024
VERIFIABLE_STATUSES = frozenset(
    {"changes_ready", "complete_no_changes", "stopped", "interrupted", "failed"}
)
ACTIVE_STATUSES = frozenset({"launching", "running", "stopping", "cleanup_incomplete"})


class CodeReviewError(ValueError):
    """A coding handoff cannot be verified or pruned safely."""


def argv_digest(argv: Iterable[str]) -> str:
    """Digest the exact command vector without retaining arguments that may be secret."""
    parts = [str(part) for part in argv]
    payload = b"\0".join(part.encode("utf-8", "surrogateescape") for part in parts)
    return hashlib.sha256(payload).hexdigest()


def _bounded_timeout(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodeReviewError("Verification timeout must be a whole number of seconds")
    return max(1, min(value, MAX_TIMEOUT_SECONDS))


def runner_state(task: dict[str, Any]) -> str:
    """Classify the recorded OpenCode runner as active, gone, or impossible to prove.

    ``active`` means the exact recorded process group (or a member of it) is
    still present. ``unknown`` means no complete identity was saved, the host
    rebooted, or the process table cannot be read safely: neither state permits
    verification or pruning, because both would race an agent that may still edit.
    """
    if task.get("status") not in ACTIVE_STATUSES:
        return "gone"
    runner_pid = task.get("runner_pid")
    runner_start = task.get("runner_starttime")
    runner_session = task.get("runner_session")
    if task.get("status") == "launching" or not runner_pid or not runner_start or not runner_session:
        return "unknown"
    if procguard.boot_id() != task.get("runner_boot_id"):
        return "unknown"
    current = procguard.identity(int(runner_pid))
    exact_leader = (current is not None and current.starttime == int(runner_start)
                    and current.pgrp == int(runner_pid) and current.session == int(runner_session))
    members = procguard.unverified_group(int(runner_pid), session_id=int(runner_session))
    return "active" if exact_leader or members else "gone"


def _git() -> str:
    executable = shutil.which("git")
    if not executable:
        raise CodeReviewError("Git is required to verify or prune a coding task")
    return executable


def git_run(args: list[str], *, cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [_git(), "-C", str(cwd), "-c", "core.hooksPath=/dev/null", *args],
            capture_output=True, text=True, timeout=timeout, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeReviewError("Git could not inspect the retained coding worktree") from exc


def _git_bytes(args: list[str], *, cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    """Read NUL-separated Git output without assuming file names are valid UTF-8."""
    try:
        return subprocess.run(
            [_git(), "-C", str(cwd), "-c", "core.hooksPath=/dev/null", *args],
            capture_output=True, timeout=timeout, check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeReviewError("Git could not inspect the retained coding worktree") from exc


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _file_digest(path: Path) -> bytes:
    """Hash a bounded prefix of one changed file; the content is never retained."""
    digest = hashlib.sha256()
    try:
        if path.is_symlink():
            digest.update(b"symlink\0" + os.fsencode(os.readlink(path)))
            return digest.digest()
        with path.open("rb") as stream:
            remaining = MAX_FINGERPRINT_BYTES
            while remaining > 0:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
    except OSError:
        digest.update(b"unreadable")
    return digest.digest()


def worktree_fingerprint(worktree: Path, base_commit: str) -> tuple[int, str]:
    """Return the changed-file count and a content-free digest of the worktree.

    The digest covers Git's porcelain status, the pinned base and a bounded
    hash of each changed file's content, so re-touching a file does not look
    like a new change while an edit does. No path, diff or file body is stored
    in the receipt.
    """
    status_text = git_run(["status", "--porcelain=v1", "--untracked-files=all"], cwd=worktree)
    if status_text.returncode != 0:
        raise CodeReviewError("Git could not read the retained coding worktree")
    status_zero = _git_bytes(["status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=worktree)
    if status_zero.returncode != 0:
        raise CodeReviewError("Git could not fingerprint the retained coding worktree")

    digest = hashlib.sha256()
    raw = status_zero.stdout
    digest.update(b"base\0" + base_commit.encode("ascii", "ignore") + b"\0status\0" + raw)
    tokens = raw.split(b"\0")
    changed = 0
    index = 0
    root = worktree.resolve()
    while index < len(tokens):
        token = tokens[index]
        if not token:
            index += 1
            continue
        changed += 1
        relative = token[3:]
        index += 1
        if b"R" in token[:2] or b"C" in token[:2]:
            index += 1  # the second NUL token is the rename/copy source path
        candidate = worktree / os.fsdecode(relative)
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if _within(root, resolved):
            digest.update(b"path\0" + relative + b"\0" + _file_digest(candidate))
    return changed, digest.hexdigest()


def _bounded_command(argv: list[str], *, cwd: Path, timeout: int) -> tuple[int, str, bool, bool]:
    """Run one explicit command, capping captured output and killing only its own group.

    Returns (exit_code, output, timed_out, output_truncated). The command gets a
    new session so a timeout kills its descendants rather than only the leader.
    """
    try:
        process = subprocess.Popen(
            argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, start_new_session=True, bufsize=0,
        )
    except OSError as exc:
        raise CodeReviewError("The verification command could not be started") from exc

    chunks: list[bytes] = []
    kept = 0
    truncated = False
    reader_done = threading.Event()

    def drain() -> None:
        nonlocal kept, truncated
        assert process.stdout is not None
        try:
            while True:
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                if kept < MAX_CAPTURED_BYTES:
                    piece = chunk[:MAX_CAPTURED_BYTES - kept]
                    chunks.append(piece)
                    kept += len(piece)
                if kept >= MAX_CAPTURED_BYTES:
                    truncated = True
        except OSError:
            pass
        finally:
            reader_done.set()

    reader = threading.Thread(target=drain, name="hutch-code-verify-output", daemon=True)
    reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _end_group(process)
    except KeyboardInterrupt:
        _end_group(process)
        raise
    reader_done.wait(timeout=5)
    try:
        process.stdout.close()  # type: ignore[union-attr]
    except OSError:
        pass
    output = b"".join(chunks).decode("utf-8", "replace")
    return int(process.returncode if process.returncode is not None else -1), output, timed_out, truncated


def _end_group(process: subprocess.Popen) -> None:
    for sig, grace in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 3.0)):
        try:
            os.killpg(process.pid, sig)
        except (OSError, ProcessLookupError):
            pass
        try:
            process.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


def worktree_path(task: dict[str, Any], state_dir: Path) -> Path:
    raw = task.get("worktree_path")
    if not raw:
        raise CodeReviewError("This coding task has no retained worktree to verify")
    actual = Path(str(raw))
    expected = (Path(state_dir) / "code-worktrees" / str(task["id"]))
    if actual != expected:
        raise CodeReviewError("The recorded worktree is not the one this task created")
    if actual.is_symlink() or not actual.is_dir():
        raise CodeReviewError("The retained worktree is missing or is not a safe directory")
    root = git_run(["rev-parse", "--show-toplevel"], cwd=actual)
    if root.returncode != 0 or Path(root.stdout.strip()).resolve() != actual.resolve():
        raise CodeReviewError("The retained folder is no longer the task's Git worktree")
    return actual


def assert_runner_stopped(task: dict[str, Any]) -> None:
    state = runner_state(task)
    if state == "active":
        raise CodeReviewError("The recorded OpenCode process group is still present; stop or reconcile it first")
    if state == "unknown":
        raise CodeReviewError(
            "Hutch cannot prove the recorded OpenCode process is gone; run `hutch code reconcile` first"
        )


def latest_receipt(store: Any, handoff_id: str, kind: str) -> Optional[dict[str, Any]]:
    with store._lock:
        row = store._db.execute(
            "SELECT * FROM code_handoff_receipts WHERE handoff_id = ? AND kind = ? ORDER BY rowid DESC LIMIT 1",
            (handoff_id, kind),
        ).fetchone()
    return dict(row) if row else None


def append_receipt(store: Any, handoff_id: str, *, kind: str, argv_digest_value: str = "",
                    exit_code: Optional[int], duration_ms: int, changed_files: int,
                    worktree_digest: str, timed_out: bool, output_truncated: bool,
                    detail: str) -> dict[str, Any]:
    receipt = {
        "id": "vfy_" + uuid.uuid4().hex[:24],
        "handoff_id": handoff_id, "kind": kind, "argv_digest": argv_digest_value,
        "exit_code": exit_code, "duration_ms": max(0, int(duration_ms)),
        "changed_files": max(0, int(changed_files)), "worktree_digest": worktree_digest,
        "timed_out": int(bool(timed_out)), "output_truncated": int(bool(output_truncated)),
        "detail": detail[:500], "created_at": iso(utcnow()),
    }
    with store._tx() as db:
        db.execute("""INSERT INTO code_handoff_receipts(
                id, handoff_id, kind, argv_digest, exit_code, duration_ms, changed_files,
                worktree_digest, timed_out, output_truncated, detail, created_at)
            VALUES (:id, :handoff_id, :kind, :argv_digest, :exit_code, :duration_ms, :changed_files,
                    :worktree_digest, :timed_out, :output_truncated, :detail, :created_at)""", receipt)
    return receipt


def verification_state(receipt: Optional[dict[str, Any]]) -> str:
    if receipt is None:
        return "unverified"
    return "verified" if int(receipt.get("exit_code") or 0) == 0 and not receipt.get("timed_out") else "verification_failed"


def verify_handoff(store: Any, handoff_id: str, argv: list[str], *, state_dir: Path,
                   timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
                   rerun: bool = False) -> dict[str, Any]:
    """Run one explicit command in the retained worktree and append a receipt."""
    task = store.code_handoff(handoff_id)
    if task is None:
        raise CodeReviewError(f"No coding task named {handoff_id}")
    assert_runner_stopped(task)
    if task["status"] not in VERIFIABLE_STATUSES:
        raise CodeReviewError(f"This coding task is {task['status']} and cannot be verified yet")
    worktree = worktree_path(task, Path(state_dir))
    command = [str(part) for part in argv]
    if not command:
        raise CodeReviewError("Pass the check command after `--`, for example: hutch code verify ID -- pytest -q")
    if any("\0" in part for part in command):
        raise CodeReviewError("The verification command contains an invalid NUL character")
    timeout = _bounded_timeout(timeout_seconds)

    digest = argv_digest(command)
    _, fingerprint_before = worktree_fingerprint(worktree, str(task["base_commit"]))
    latest = latest_receipt(store, handoff_id, "verify")
    if (not rerun and latest is not None and latest["argv_digest"] == digest
            and latest["worktree_digest"] == fingerprint_before
            and verification_state(latest) == "verified"):
        return {**latest, "output": "", "reused": True}

    started = time.monotonic()
    exit_code, output, timed_out, truncated = _bounded_command(command, cwd=worktree, timeout=timeout)
    duration_ms = int((time.monotonic() - started) * 1000)
    changed_files, fingerprint = worktree_fingerprint(worktree, str(task["base_commit"]))
    if timed_out:
        detail = "timed_out"
    elif exit_code == 0:
        detail = "verified"
    else:
        detail = "exit_nonzero"
    receipt = append_receipt(
        store, handoff_id, kind="verify", argv_digest_value=digest, exit_code=exit_code,
        duration_ms=duration_ms, changed_files=changed_files,
        worktree_digest=fingerprint, timed_out=timed_out, output_truncated=truncated, detail=detail,
    )
    return {**receipt, "output": output, "reused": False}


def receipt_map(store: Any, handoff_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Latest verification and prune receipt per task for the API projection."""
    ids = [str(value) for value in handoff_ids]
    result: dict[str, dict[str, Any]] = {}
    if not ids:
        return result
    placeholders = ",".join("?" for _ in ids)
    with store._lock:
        rows = store._db.execute(
            f"SELECT * FROM code_handoff_receipts WHERE handoff_id IN ({placeholders}) ORDER BY rowid",
            ids,
        ).fetchall()
    for row in rows:
        item = result.setdefault(str(row["handoff_id"]), {"verification": None, "pruned_at": None})
        if row["kind"] == "verify":
            item["verification"] = dict(row)
        elif row["kind"] == "prune":
            item["pruned_at"] = row["created_at"]
    return result
