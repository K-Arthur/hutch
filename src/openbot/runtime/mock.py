"""Deterministic mock runtime — offline tests, demos, and marketing screenshots.

Runs a canned but realistic script against the REAL tool layer (so policy,
approvals, transcripts and the dashboard behave exactly as in production):
saves a memory, writes a report into the workspace, maybe runs a shell
command, then replies with a summary.
"""

from __future__ import annotations

from typing import Callable

from ..models import Event, EventType, Run
from ..tools import Tool, ToolContext
from .base import RunAborted


class MockRuntime:
    kind = "mock"

    def execute(
        self,
        run: Run,
        ctx: ToolContext,
        tools: dict[str, Tool],
        stop: Callable[[], bool],
    ) -> str:
        prompt = run.prompt.lower()

        def call(name: str, args: dict) -> str:
            if stop():
                raise RunAborted("stopped", "user requested stop")
            ctx.emit(Event(run_id=run.id, type=EventType.tool_call, data={"tool": name, "args": args}))
            tool = tools.get(name)
            from ..tools.base import ToolResult
            result = tool.run(args, ctx) if tool else ToolResult(
                ok=False, output=f"error: tool '{name}' not enabled for this bot")
            ctx.emit(Event(run_id=run.id, type=EventType.tool_result,
                           data={"tool": name, "ok": result.ok, "output": result.output[:2_000]}))
            run.steps += 1
            run.tokens += 350  # plausible per-step usage for the dashboard meter
            return result.output

        topic = ctx.bot.description or ctx.bot.name
        if "research" in prompt or "summar" in prompt or "news" in prompt or "report" in prompt:
            flavor = "research briefing"
        elif "todo" in prompt or "code" in prompt or "repo" in prompt:
            flavor = "code review notes"
        else:
            flavor = "task notes"

        if "remember" in tools:
            call("remember", {"key": "last-run", "value": f"{flavor} for: {run.prompt[:120]}"})

        if "list_files" in tools:
            call("list_files", {})

        if "shell" in tools:
            call("shell", {"command": "date -u"})

        if "write_file" in tools:
            call("write_file", {
                "path": "report.md",
                "content": (
                    f"# {flavor.title()}\n\n"
                    f"- bot: {ctx.bot.name}\n- asked: {run.prompt}\n\n"
                    "## Findings (mock)\n"
                    "1. Deterministic mock run — no model was contacted.\n"
                    "2. The full tool/policy/approval pipeline executed normally.\n"
                    "3. Swap the bot's model to openai/* or ollama/* for real runs.\n"
                ),
            })

        if "recall" in tools:
            call("recall", {"query": "last-run"})

        final = (
            f"Done — {flavor} for “{run.prompt[:100]}”. "
            f"Wrote report.md, updated memory ({run.steps} tool steps, ~{run.tokens} tokens). "
            "This was a mock run; point the bot at a real model for live results."
        )
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": final}))
        return final
