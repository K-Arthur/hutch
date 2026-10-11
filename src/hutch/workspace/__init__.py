"""Conversation-scoped persistent Python workspaces (the ``run_python`` lane).

A workspace is one contained kernel process per conversation: bubblewrap
strict containment (workspace-only writable dir, read-only venv, no network,
cgroup caps), a JSON-line protocol, durable environment generations in the
``workspace_sessions`` table, and typed output blocks as receipts. It fails
closed: when strict containment is unavailable there is no execution at all,
never an unsandboxed fallback.
"""

from .manager import (
    ContainmentUnavailable,
    WorkspaceManager,
    kernel_argv,
    kernel_env,
    manager_for_conversation,
    workspace_dir_for,
)

__all__ = [
    "ContainmentUnavailable",
    "WorkspaceManager",
    "kernel_argv",
    "kernel_env",
    "manager_for_conversation",
    "workspace_dir_for",
]
