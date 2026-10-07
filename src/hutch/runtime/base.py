"""Runtime interface: something that can execute one run of a bot."""

from __future__ import annotations

from typing import Callable, Protocol

from ..models import Run
from ..tools import Tool, ToolContext


class RunAborted(Exception):
    """The run must stop (limit hit, user stop, runtime failure)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


class AgentRuntime(Protocol):
    kind: str

    def execute(
        self,
        run: Run,
        ctx: ToolContext,
        tools: dict[str, Tool],
        stop: Callable[[], bool],
    ) -> str:
        """Run the agent loop to completion, emitting events via ctx.emit.

        Returns the final assistant message. Raises RunAborted to stop early.
        """
        ...  # pragma: no cover
