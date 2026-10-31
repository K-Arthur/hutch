"""Owner-confirmed removal of a retained coding worktree and its branch.

Separate from verification so each module owns one lifecycle step: verification
observes, pruning deletes. Pruning requires a passing receipt unless the owner
explicitly discards the work, a recorded runner group that is provably gone, and
explicit confirmation. The configured project folder is never modified.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .code_review import (CodeReviewError, append_receipt, assert_runner_stopped, git_run,
                          latest_receipt, verification_state, worktree_fingerprint,
                          worktree_path)


def prune_handoff(store: Any, handoff_id: str, *, state_dir: Path, confirmed: bool,
                  discard: bool = False) -> dict[str, Any]:
    """Remove a retained worktree and branch only after a verified receipt.

    ``discard`` is the explicit escape hatch for an unverified or failed check;
    it still requires confirmation and never touches a live runner.
    """
    if not confirmed:
        raise CodeReviewError("Pruning deletes uncommitted work; confirm explicitly with --yes")
    task = store.code_handoff(handoff_id)
    if task is None:
        raise CodeReviewError(f"No coding task named {handoff_id}")
    assert_runner_stopped(task)
    latest = latest_receipt(store, handoff_id, "verify")
    if latest is None and not discard:
        raise CodeReviewError("Run `hutch code verify` first, or pass --discard to remove unverified work")
    if latest is not None and verification_state(latest) != "verified" and not discard:
        raise CodeReviewError("The last verification failed; review it or pass --discard to remove the worktree")
    if latest_receipt(store, handoff_id, "prune") is not None:
        raise CodeReviewError("This coding task's worktree was already pruned")

    raw = task.get("worktree_path")
    if not raw:
        raise CodeReviewError("This coding task has no retained worktree to prune")
    expected = (Path(state_dir) / "code-worktrees" / str(task["id"]))
    if Path(str(raw)) != expected:
        raise CodeReviewError("The recorded worktree is not the one this task created")
    worktree = Path(str(raw))
    if worktree.is_symlink():
        raise CodeReviewError("The retained worktree is unsafe and will not be removed")
    if worktree.is_dir():
        worktree = worktree_path(task, Path(state_dir))
        changed_files, fingerprint = worktree_fingerprint(worktree, str(task["base_commit"]))
    else:
        changed_files, fingerprint = 0, hashlib.sha256(b"worktree_missing").hexdigest()
    project_root = Path(str(task["project_root"]))
    if not project_root.is_dir():
        raise CodeReviewError("The configured project folder is no longer available; the worktree was kept")
    branch = str(task.get("branch_name") or "")

    if worktree.is_dir():
        removed = git_run(["worktree", "remove", "--force", str(worktree)], cwd=project_root, timeout=60)
        if removed.returncode != 0:
            detail = (removed.stderr or removed.stdout).strip().splitlines()
            raise CodeReviewError("Git could not remove the retained worktree"
                                  + (f": {detail[-1][:300]}" if detail else ""))
    branch_removed = False
    warning = ""
    if branch:
        exists = git_run(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=project_root)
        if exists.returncode == 0:
            deleted = git_run(["branch", "-D", branch], cwd=project_root)
            branch_removed = deleted.returncode == 0
            if not branch_removed:
                warning = (deleted.stderr or deleted.stdout).strip().splitlines()[-1][:300]
        else:
            branch_removed = True
    git_run(["worktree", "prune"], cwd=project_root)

    detail = ("worktree_removed;" + ("branch_removed" if branch_removed else "branch_kept"))
    receipt = append_receipt(
        store, handoff_id, kind="prune", exit_code=None, duration_ms=0,
        changed_files=changed_files, worktree_digest=fingerprint,
        timed_out=False, output_truncated=False, detail=detail,
    )
    return {**receipt, "worktree_removed": True, "branch_removed": branch_removed, "warning": warning}
