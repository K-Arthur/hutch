"""Built-in agent loop — OpenBot's own runtime.

A deliberately thin loop (the differentiating machinery — policy, approvals,
caps, transcripts — lives in the engine, not here). Works with any
OpenAI-compatible endpoint: OpenAI, Ollama (http://localhost:11434/v1),
llama.cpp/LM Studio servers, or any custom base URL.

Model spec format:  provider/model-id
  openai/gpt-4o-mini            -> api.openai.com (OPENAI_API_KEY)
  ollama/llama3.2               -> localhost:11434/v1
  lmstudio/qwen2.5-7b           -> localhost:1234/v1
  openai-compatible/<name>      -> OPENBOT_BASE_URL (or bot.base_url)
"""

from __future__ import annotations

import os
from typing import Callable

from openai import OpenAI

from ..models import Event, EventType, Run
from ..tools import Tool, ToolContext
from .base import RunAborted

PROVIDER_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}

SYSTEM_TEMPLATE = """You are {name}, a bot running on OpenBot — a local, human-supervised agent platform.

Your purpose: {description}

Operator instructions:
{instructions}

Rules of engagement:
- Your entire world is your workspace directory: {workspace}. File reads/writes stay inside it.
- Tool calls that mutate anything may require human approval; the run pauses until a human answers. If an action is denied, do not retry it — adapt or report.
- Prefer the fewest tool calls that accomplish the task. Never loop over the same failing action.
- When you are done, reply with a concise summary of what you did, created, or found. If you could not finish, say exactly what blocked you.

Current date: {date} (UTC)
{memory_block}"""


class BuiltinRuntime:
    kind = "builtin"

    def __init__(self, api_key_env: str = "OPENAI_API_KEY"):
        self.api_key_env = api_key_env

    # ------------------------------------------------------------- provider

    def _client_config(self, ctx: ToolContext) -> tuple[str, str]:
        spec = ctx.bot.model
        provider, _, model = spec.partition("/")
        model = model or spec
        base_url = ctx.bot.base_url or os.environ.get("OPENBOT_BASE_URL")
        api_key = os.environ.get(self.api_key_env, "local")

        if provider == "openai" and not base_url:
            base_url = None  # SDK default
        elif provider in PROVIDER_BASE_URLS and not base_url:
            base_url = PROVIDER_BASE_URLS[provider]
            api_key = api_key if provider == "openai" else "local"
        elif provider == "openai-compatible":
            if not base_url:
                raise RunAborted("error", "openai-compatible provider needs bot.base_url or OPENBOT_BASE_URL")
        elif provider == "mock":
            raise RunAborted("error", "use MockRuntime for mock/* models")
        return model, base_url or ""

    def _client(self, ctx: ToolContext):
        model, base_url = self._client_config(ctx)
        kwargs = {"base_url": base_url} if base_url else {}
        return OpenAI(api_key=os.environ.get(self.api_key_env, "local"), **kwargs), model

    # ---------------------------------------------------------------- prompt

    def _system_prompt(self, ctx: ToolContext) -> str:
        import datetime as dt
        facts = ctx.store.recall_all(ctx.bot.id) if ctx.bot.memory_enabled else []
        memory_block = ""
        if facts:
            joined = "\n".join(f"- {m.key}: {m.value}" for m in facts[:40])
            memory_block = "What you remember from previous runs:\n" + joined
        return SYSTEM_TEMPLATE.format(
            name=ctx.bot.name,
            description=ctx.bot.description or "(none given)",
            instructions=ctx.bot.instructions or "(none given)",
            workspace=ctx.workspace,
            date=dt.datetime.now(dt.timezone.utc).date().isoformat(),
            memory_block=memory_block,
        )

    # ------------------------------------------------------------------ loop

    def execute(
        self,
        run: Run,
        ctx: ToolContext,
        tools: dict[str, Tool],
        stop: Callable[[], bool],
    ) -> str:
        client, model = self._client(ctx)
        system = self._system_prompt(ctx)

        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": run.prompt},
        ]

        while run.steps < ctx.bot.limits.max_steps:
            if stop():
                raise RunAborted("stopped", "user requested stop")

            # Daily token cap: measured usage when the API reports it, estimate otherwise
            used_today = ctx.store.tokens_today(ctx.bot.id)
            if used_today > ctx.bot.limits.daily_token_cap:
                raise RunAborted("token_cap", f"daily cap {ctx.bot.limits.daily_token_cap} exceeded")

            try:
                params: dict = {"model": model, "messages": messages}
                if tools:
                    params["tools"] = [t.spec() for t in tools.values()]
                response = client.chat.completions.create(**params)
            except Exception as exc:  # provider/network errors surface as run failures
                raise RunAborted("error", f"model call failed: {exc}") from exc

            choice = response.choices[0]
            msg = choice.message
            if getattr(response, "usage", None) and response.usage.total_tokens:
                run.tokens += response.usage.total_tokens
            else:
                run.tokens += (len(str(messages)) + len(msg.content or "")) // 8

            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                final_text = msg.content or ""
                ctx.emit(Event(run_id=run.id, type=EventType.message,
                               data={"role": "assistant", "content": final_text}))
                return final_text

            run.steps += 1
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [
                                 {"id": tc.id, "type": "function",
                                  "function": {"name": tc.function.name,
                                               "arguments": tc.function.arguments}}
                                 for tc in tool_calls
                             ]})
            for tc in tool_calls:
                result = self._run_one_tool(tc.function.name, tc.function.arguments, ctx, tools)
                messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": (result.output or "(empty)")[:12_000],
                })

        raise RunAborted("steps_exceeded", f"hit max_steps={ctx.bot.limits.max_steps}")

    def _run_one_tool(self, name: str, raw_args: str, ctx: ToolContext, tools: dict[str, Tool]) -> object:
        import json
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {}
        ctx.emit(Event(run_id=ctx.run.id, type=EventType.tool_call, data={"tool": name, "args": args}))
        tool = tools.get(name)
        if tool is None:
            from ..tools.base import ToolResult
            result = ToolResult(ok=False, output=f"error: unknown tool '{name}' — available: {sorted(tools)}")
        else:
            result = tool.run(args, ctx)
        ctx.emit(Event(run_id=ctx.run.id, type=EventType.tool_result,
                       data={"tool": name, "ok": result.ok, "output": result.output[:2_000]}))
        return result
