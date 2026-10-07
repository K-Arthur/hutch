"""Per-step accounting shared by every runtime (SR-2, PF-11).

A *step* is one model turn plus the tools it triggered. Wall time is split three ways:

* ``model_ms``    waiting on the model (network + inference)
* ``tool_ms``     inside tools (subprocess, file IO, network)
* ``overhead_ms`` everything else: Hutch's own cost — policy checks, approval bookkeeping,
                  event emission, accounting. The draft targets < 50 ms per step.

Each step lands in the transcript as a ``step`` event, so the numbers are inspectable per run
and the dashboard can sum them without a separate metrics store.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import Event, EventType, Run
from ..tools import Tool, ToolContext
from ..tools.base import ToolResult


@dataclass
class StepTimer:
    t0: float = field(default_factory=time.perf_counter)
    model_ms: float = 0.0
    tool_ms: float = 0.0

    def model(self, seconds: float) -> None:
        self.model_ms += seconds * 1000.0


def call_tool(run: Run, ctx: ToolContext, tools: dict[str, Tool], name: str, args: dict[str, Any],
              timer: Optional[StepTimer] = None, output_chars: int = 2_000) -> ToolResult:
    """Emit the call, run the tool (timed), emit the result. Used by the mock and builtin runtimes."""
    ctx.emit(Event(run_id=run.id, type=EventType.tool_call, data={"tool": name, "args": args}))
    tool = tools.get(name)
    t1 = time.perf_counter()
    if tool is None:
        result = ToolResult(ok=False, output=f"error: unknown tool '{name}' — available: {sorted(tools)}")
    else:
        result = tool.run(args, ctx)
    if timer is not None:
        timer.tool_ms += (time.perf_counter() - t1) * 1000.0
    ctx.emit(Event(run_id=run.id, type=EventType.tool_result,
                   data={"tool": name, "ok": result.ok, "output": result.output[:output_chars]}))
    return result


def finish_step(run: Run, ctx: ToolContext, timer: StepTimer, *, model: str = "",
                prompt_tokens: int = 0, completion_tokens: int = 0, cached_tokens: int = 0,
                cost_usd: float = 0.0, **extra: Any) -> None:
    """Fold a step into the run's totals and append its ``step`` event."""
    total_ms = (time.perf_counter() - timer.t0) * 1000.0
    overhead_ms = max(0.0, total_ms - timer.model_ms - timer.tool_ms)
    run.prompt_tokens += prompt_tokens
    run.completion_tokens += completion_tokens
    run.cached_tokens += cached_tokens
    run.cost_usd = round(run.cost_usd + cost_usd, 8)
    run.model_ms += timer.model_ms
    run.tool_ms += timer.tool_ms
    run.overhead_ms += overhead_ms
    if model:
        run.model_used = model
    ctx.emit(Event(run_id=run.id, type=EventType.step, data={
        "n": run.steps, "model": model or run.model_used,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens, "cost_usd": round(cost_usd, 8),
        "model_ms": round(timer.model_ms, 2), "tool_ms": round(timer.tool_ms, 2),
        "overhead_ms": round(overhead_ms, 3), **extra,
    }))
