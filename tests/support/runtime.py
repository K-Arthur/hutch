"""Deterministic execution fixture used only by the test suite.

Runs a canned but realistic script against the REAL tool layer (so policy,
approvals, transcripts and the dashboard behave exactly as in production):
saves a memory, writes a report into the workspace, maybe runs a shell
command, then replies with a summary.
"""

from __future__ import annotations

import os
from typing import Callable

from hutch.models import Event, EventType, Run
from hutch.tools import Tool, ToolContext
from hutch.runtime.base import RunAborted
from hutch.runtime.steps import StepTimer, call_tool, finish_step


class TestScenarioRuntime:
    kind = "test-scenario"

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
            timer = StepTimer()
            result = call_tool(run, ctx, tools, name, args, timer)
            run.steps += 1
            run.tokens += 350  # plausible per-step usage for the dashboard meter
            finish_step(run, ctx, timer, model=ctx.bot.model or "test/scenario", prompt_tokens=250, completion_tokens=100)
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
                    "## Findings (test fixture)\n"
                    "1. Deterministic scenario output — no model was contacted.\n"
                    "2. The tool/policy/approval pipeline was exercised by the test fixture.\n"
                ),
            })

        if "recall" in tools:
            call("recall", {"query": "last-run"})

        final = (f"Test scenario finished for “{run.prompt[:100]}”. "
                 f"The fixture exercised {run.steps} tool steps and {run.tokens} synthetic tokens. "
                 "Reference-fact proposals need human review.")
        ctx.emit(Event(run_id=run.id, type=EventType.message,
                       data={"role": "assistant", "content": final}))
        return final


def test_runtime_for(bot, production_factory):
    """Inject scenarios only inside the test harness, never from product runtime selection."""
    from hutch.models import RuntimeKind

    provider = bot.model.partition("/")[0].strip().lower()
    if os.environ.get("HUTCH_TESTING") == "1" and (
        not bot.model or provider == "mock" or bot.runtime is RuntimeKind.mock
    ):
        return TestScenarioRuntime()
    return production_factory(bot)


def test_model_choices_for(bot, args, kwargs, production_factory):
    """Keep retired mock routes visibly unavailable even in test-driven UI fixtures."""
    choices = production_factory(*args, **kwargs)
    if os.environ.get("HUTCH_TESTING") == "1" and bot.model.startswith("mock/"):
        own = next((choice for choice in choices if choice.spec == bot.model), None)
        if own is not None:
            own.state = "setup"
            own.note = "legacy test route; choose a real model"
            own.fix = "Choose a configured Ollama, OpenAI, Anthropic, or compatible route"
    return choices


def test_validate_override_for(bot, spec, args, kwargs, production_factory):
    """Allow fixture-only mock routes through test entrypoints, not product code."""
    candidate = (spec or bot.model or "").strip()
    provider, separator, model = candidate.partition("/")
    if os.environ.get("HUTCH_TESTING") == "1" and separator and provider.strip().lower() == "mock" and model.strip():
        return candidate
    return production_factory(*args, **kwargs)
