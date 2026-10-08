"""OpenCode adapter capability boundary.

Execution is deliberately unavailable until Hutch can own the OpenCode
process, broker every permission request, and reserve a provider budget. The
previous adapter used ``--auto`` and could escape Hutch's approval and spend
controls. Keeping a loud fail-closed adapter is safer than silently pretending
that workspace cwd is a security boundary.
"""

from __future__ import annotations

from typing import Callable

from ..models import Run
from ..tools import Tool, ToolContext
from .base import RunAborted

class OpenCodeRuntime:
    kind = "opencode"

    def __init__(self, binary: str = "opencode"):
        self.binary = binary

    def execute(
        self,
        run: Run,
        ctx: ToolContext,
        tools: dict[str, Tool],
        stop: Callable[[], bool],
    ) -> str:
        del run, ctx, tools, stop
        raise RunAborted(
            "unsupported",
            "OpenCode execution is disabled until Hutch can broker its tool permissions, "
            "contain its process and enforce a provider budget. Use the builtin runtime instead.",
        )
