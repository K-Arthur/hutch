"""Pi adapter capability boundary.

Execution is unavailable until Hutch can put Pi inside an owned OS sandbox,
provide an explicitly restricted capability set, and reserve provider usage.
Pi RPC does not document an approval broker, so accepting tool calls here would
bypass Hutch's human-control contract.
"""

from __future__ import annotations

from typing import Callable

from ..models import Run
from ..tools import Tool, ToolContext
from .base import RunAborted

RPC_TIMEOUT = 600


class PiRuntime:
    kind = "pi"

    def __init__(self, binary: str = "pi"):
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
            "Pi execution is disabled until Hutch can contain its process and provide a restricted "
            "capability set with provider budget enforcement. Use the builtin runtime instead.",
        )
