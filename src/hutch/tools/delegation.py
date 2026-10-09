"""Explicitly approved, bounded child work for the supervised offline runtime."""

from __future__ import annotations

import hashlib
import json

from ..approvals import DeniedError
from ..models import InferenceMode
from ..safety import Decision, Verdict
from .base import Tool, ToolContext, ToolResult, _schema, clip, rehearsed

MAX_DELEGATED_TASK_CHARS = 4_000
MAX_DELEGATED_RESULT_CHARS = 8_000


class DelegateTaskTool(Tool):
    name = "delegate_task"
    description = (
        "Ask a separate Hutch worker to complete one bounded subtask using the same bot's captured "
        "Strict Offline permissions and a private workspace. Only the task text is shared; the child "
        "does not receive this conversation's prior messages. Always describe a concrete result to return."
    )
    parameters = _schema(
        ["task"],
        {"task": {"type": "string", "description": "One specific subtask, at most 4,000 characters"}},
    )

    def effect(self, args, ctx):
        return "process"

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        task = args.get("task")
        if not isinstance(task, str):
            return ToolResult(ok=False, output="error: delegated task must be text")
        task = task.strip()
        if not task:
            return ToolResult(ok=False, output="error: delegated task cannot be empty")
        if len(task) > MAX_DELEGATED_TASK_CHARS:
            return ToolResult(ok=False, output=f"error: delegated task exceeds {MAX_DELEGATED_TASK_CHARS:,} characters")
        if (ctx.bot.inference_mode is not InferenceMode.offline or ctx.bot.runtime.value != "builtin"
                or ctx.delegation_submit is None):
            return ToolResult(ok=False, output=("error: delegation is available only through a supervised "
                                                "Strict Offline built-in run") )
        if ctx.dry_run:
            return rehearsed(f"request approval for a separate local child run: {task[:160]}")

        depth = ctx.store.delegation_depth(ctx.run.id)
        if depth >= 2:
            return ToolResult(ok=False, output="error: delegation depth limit is two")
        if ctx.run.cancel_requested or ctx.closed:
            return ToolResult(ok=False, output="error: this run is stopping; no child was started")

        detail = {
            "task": task,
            "bot_id": ctx.bot.id,
            "model": ctx.bot.model,
            "inference_mode": "offline",
            "depth": depth + 1,
            "workspace": "private child workspace",
            "context": "task text only; no parent conversation history",
            "limits": {"steps": min(ctx.bot.limits.max_steps, 8),
                       "timeout_seconds": min(ctx.bot.limits.timeout_seconds, 600)},
        }
        decision = Decision(Verdict.ask, "start separate local model work", rule="delegation:always-review",
                            risk="high", outward=True)
        try:
            ctx.gate.decide("delegate_task", "delegate bounded offline work", detail,
                            decision=decision, outward=True, ask_in_auto=True)
        except DeniedError as exc:
            return ToolResult(ok=False, output=f"error: {exc}; no child was started")
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: approval could not be recorded ({exc}); no child was started")

        refusal = ctx.begin_effect()
        if refusal:
            return ToolResult(ok=False, output=f"error: {refusal}")

        # The model call ID is not reliably stable across providers, so the call position and
        # task digest form a compact key. Exact retry of this step reuses its original child;
        # the same task requested on a later model step creates new work.
        digest = hashlib.sha256(task.encode("utf-8")).hexdigest()
        idem_key = f"step-{ctx.run.steps}-{digest[:24]}"
        request_hash = hashlib.sha256(json.dumps(detail, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            result = ctx.delegation_submit(task, idem_key, request_hash)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: child admission failed safely ({type(exc).__name__}: {exc})")
        if not result.ok:
            return result
        return ToolResult(ok=True, output=clip(result.output, MAX_DELEGATED_RESULT_CHARS), data=result.data)
