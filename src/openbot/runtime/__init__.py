"""Runtime factory."""

from __future__ import annotations

from ..models import Bot, RuntimeKind
from .base import AgentRuntime, RunAborted
from .builtin import BuiltinRuntime
from .mock import MockRuntime
from .opencode import OpenCodeRuntime
from .pi import PiRuntime


def get_runtime(bot: Bot) -> AgentRuntime:
    if bot.runtime is RuntimeKind.pi:
        return PiRuntime()
    if bot.runtime is RuntimeKind.opencode:
        return OpenCodeRuntime()
    if bot.runtime is RuntimeKind.mock or bot.model.startswith("mock/"):
        return MockRuntime()
    return BuiltinRuntime()


__all__ = ["AgentRuntime", "RunAborted", "BuiltinRuntime", "MockRuntime", "PiRuntime", "OpenCodeRuntime", "get_runtime"]
