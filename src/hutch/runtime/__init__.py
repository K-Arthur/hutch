"""Runtime factory."""

from __future__ import annotations

from ..models import Bot, RuntimeKind
from .base import AgentRuntime, RunAborted
from .builtin import BuiltinRuntime
from .opencode import OpenCodeRuntime
from .pi import PiRuntime


class RuntimeUnavailable(RuntimeError):
    """The selected persisted runtime or model route cannot execute real work."""


def get_runtime(bot: Bot) -> AgentRuntime:
    provider = bot.model.partition("/")[0].strip().lower()
    if bot.runtime is RuntimeKind.pi:
        return PiRuntime()
    if bot.runtime is RuntimeKind.opencode:
        return OpenCodeRuntime()
    if bot.runtime is RuntimeKind.mock or provider == "mock":
        raise RuntimeUnavailable("The mock runtime was removed. Select a configured Ollama, OpenAI, Anthropic, or compatible model route.")
    if not bot.model.strip():
        raise RuntimeUnavailable("No model route is configured. Choose a real model before starting this bot.")
    return BuiltinRuntime()


__all__ = ["AgentRuntime", "RunAborted", "BuiltinRuntime", "PiRuntime", "OpenCodeRuntime", "RuntimeUnavailable", "get_runtime"]
