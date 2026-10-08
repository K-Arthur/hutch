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

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..lifecycle import LeaseLost
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


DEFAULT_TOOL_LIMIT = 12_000   # chars shown to the model per tool call unless the bot overrides it (PF-2)


def save_artifact(ctx: ToolContext, tool: str, text: str) -> str:
    """Write a tool's full output under the run's artifacts/ directory; returns its path relative to the run."""
    run_dir = ctx.config.run_dir(ctx.bot.name, ctx.run.id)
    art = run_dir / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    n = len(list(art.iterdir())) + 1
    path = art / f"{n:03d}-{tool}.txt"
    path.write_text(text, encoding="utf-8", errors="replace")
    return str(path.relative_to(run_dir))


def truncate_for_model(ctx: ToolContext, tool: str, output: str) -> tuple[str, Optional[str]]:
    """PF-2: cap what the model sees to the tool's limit; the full output is kept as an artifact."""
    limit = int(ctx.bot.tool_limits.get(tool, DEFAULT_TOOL_LIMIT))
    if limit <= 0 or len(output) <= limit:
        return output, None
    rel = save_artifact(ctx, tool, output)
    note = f"\n... [{len(output) - limit:,} of {len(output):,} characters omitted; full output saved as artifact {rel}]"
    return output[:limit] + note, rel


def _summary(name: str, args: dict[str, Any]) -> str:
    for key in ("command", "path", "url", "selector", "label", "key", "action"):
        if args.get(key):
            return f"{name}: {str(args[key])[:160]}"
    return name


def _run_with_receipt(tool: Tool, name: str, args: dict[str, Any], ctx: ToolContext, run: Run) -> ToolResult:
    """Run a tool; if the call can have a lasting effect, bracket the EFFECT with an intent and a receipt (ADR-0003).

    The tool calls ``ctx.begin_effect()`` after policy and approval, immediately before it acts; that writes the intent and
    refuses (fail closed) if it cannot be recorded or this worker no longer owns the run. After the tool returns the receipt is
    written. If the process dies between the two, the row stays ``started``: recovery reports an unknown outcome and the action
    is never replayed. Local keys do not make a remote effect exactly-once, and the UI says so."""
    effect = "" if ctx.dry_run else tool.effect(args, ctx)
    if not effect:
        return tool.run(args, ctx)
    key = hashlib.sha256(f"{run.id}|{name}|{json.dumps(args, sort_keys=True, default=str)}".encode()).hexdigest()[:24]
    began: dict[str, str] = {}

    def begin() -> Optional[str]:
        try:
            began["id"] = ctx.store.begin_action(run.id, name, key, effect, _summary(name, args), fence=run.fence)
        except LeaseLost as exc:
            ctx.closed = True          # we no longer own this run: nothing more may start from this worker
            return f"{exc}; the action was not started"
        except Exception as exc:
            return f"the action could not be recorded ({exc}), so it was not run"
        return None

    ctx.receipt = begin
    result = ToolResult(ok=False, output="error: the action did not finish")
    try:
        result = tool.run(args, ctx)
        return result
    finally:
        ctx.receipt = None
        if "id" in began:              # an action that never began (denied, expired, refused) has nothing to receipt
            try:
                ctx.store.finish_action(began["id"], "done" if result.ok else "failed",
                                        hashlib.sha256(result.output.encode(errors="replace")).hexdigest()[:16])
            except Exception:
                pass                   # the row stays 'started': an honest "unknown" is better than a made-up receipt


def call_tool(run: Run, ctx: ToolContext, tools: dict[str, Tool], name: str, args: dict[str, Any],
              timer: Optional[StepTimer] = None, output_chars: int = 2_000) -> ToolResult:
    """Emit the call, run the tool (timed), emit the result. Used by the mock and builtin runtimes."""
    if ctx.closed:                       # fenced: the run already ended (timeout, stop, recovery); nothing new may start
        return ToolResult(ok=False, output="error: this run has ended; the action was not started")
    ctx.emit(Event(run_id=run.id, type=EventType.tool_call, data={"tool": name, "args": args}))
    tool = tools.get(name)
    t1 = time.perf_counter()
    if tool is None:
        result = ToolResult(ok=False, output=f"error: unknown tool '{name}' — available: {sorted(tools)}")
    else:
        result = _run_with_receipt(tool, name, args, ctx, run)
    if timer is not None:
        timer.tool_ms += (time.perf_counter() - t1) * 1000.0
    full_chars = len(result.output)
    result.output, artifact = truncate_for_model(ctx, name, result.output)
    data: dict[str, Any] = {"tool": name, "ok": result.ok, "output": result.output[:output_chars]}
    if artifact:
        data.update(artifact=artifact, chars=full_chars)
    if result.data.get("simulated"):
        data["simulated"] = True                                 # Rehearse mode: nothing actually ran
    ctx.emit(Event(run_id=run.id, type=EventType.tool_result, data=data))
    return result


def finish_step(run: Run, ctx: ToolContext, timer: StepTimer, *, model: str = "",
                prompt_tokens: int = 0, completion_tokens: int = 0, cached_tokens: int = 0,
                cost_usd: float = 0.0, account_id: str = "", reservation_id: Optional[str] = None,
                **extra: Any) -> None:
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
    ctx.store.update_run(run)  # persist running totals so the meters (UI-4) are live, not end-of-run
    if reservation_id and not (prompt_tokens or completion_tokens):
        ctx.store.mark_usage_uncertain(reservation_id, "provider response did not report token usage")
    elif prompt_tokens or completion_tokens:
        provider, _, name = (model or run.model_used or "unknown/unknown").partition("/")
        ctx.store.add_usage(run.id, run.bot_id, provider, name or provider, prompt_tokens, completion_tokens,
                            cached_tokens, cost_usd, account_id=account_id, reservation_id=reservation_id)
    ctx.emit(Event(run_id=run.id, type=EventType.step, data={
        "n": run.steps, "model": model or run.model_used,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens, "cost_usd": round(cost_usd, 8),
        "model_ms": round(timer.model_ms, 2), "tool_ms": round(timer.tool_ms, 2),
        "overhead_ms": round(overhead_ms, 3), **extra,
    }))
