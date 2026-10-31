"""Why a parked workflow is not being continued.

The supervisor revisits workflows whose attempt ended while the instance is still live. Two facts
stop it from admitting a fresh attempt, and each needs a different record:

- the assistant is **archived**: the work is held, not lost, so restoring the assistant continues it;
- the Bot is gone: nothing can continue it, so the instance is closed with a reason.

Recording the reason matters. Skipping silently leaves a workflow looking pending forever with no
explanation on the owner's screen.
"""
from __future__ import annotations

from typing import Any

from .persistence import update_workflow_run


def hold_parked_workflow(store: Any, wf_id: str, *, archived: bool) -> None:
    """Hold a parked workflow for a retired assistant, or close it for a missing one."""
    update_workflow_run(
        store, wf_id, status="waiting" if archived else "failed", finished=not archived,
        reason="the assistant is archived; restore it to continue" if archived else "the Bot no longer exists")
