"""Tool registry — maps bot tool allowlists to tool instances."""

from __future__ import annotations

from .base import Tool, ToolContext, ToolResult
from .files import FilesListTool, FilesReadTool, FilesWriteTool
from .memory import MemoryRecallTool, MemorySaveTool
from .shell import ShellTool
from .webfetch import WebFetchTool
from .delegation import DelegateTaskTool
from .choice import AskUserChoiceTool
from .google_calendar import GoogleCalendarEventsTool
from .outlook_calendar import OutlookCalendarEventsTool

#: name -> factory (browser is imported lazily so the dependency stays optional)
_CATALOG: dict[str, type[Tool]] = {
    "shell": ShellTool,
    "read_file": FilesReadTool,
    "list_files": FilesListTool,
    "write_file": FilesWriteTool,
    "remember": MemorySaveTool,
    "recall": MemoryRecallTool,
    "web_fetch": WebFetchTool,
    "delegate_task": DelegateTaskTool,
}

#: bot-level tool groups that expand to concrete tool names
GROUPS: dict[str, list[str]] = {
    "files": ["read_file", "list_files", "write_file"],
    "memory": ["remember", "recall"],
    "browser": ["browser"],
}

ALL_TOOL_NAMES = sorted(_CATALOG) + ["browser"]


def expand_tools(bot_tools: list[str]) -> list[str]:
    """Expand group names (files/memory/browser) into concrete tool names."""
    out: list[str] = []
    for name in bot_tools:
        if name in GROUPS:
            out.extend(GROUPS[name])
        else:
            out.append(name)
    seen, unique = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def build_tools(names: list[str], ctx: ToolContext, *, memory_enabled: bool | None = None) -> dict[str, Tool]:
    tools: dict[str, Tool] = {}
    enabled = memory_enabled if memory_enabled is not None else (ctx.bot.memory_enabled if ctx is not None else True)
    if enabled and ctx is not None:
        stored_bot = ctx.store.get_bot(ctx.bot.id)
        enabled = bool(stored_bot and stored_bot.memory_enabled)
    expanded = expand_tools(names)
    if ctx is not None and getattr(getattr(ctx.bot, "inference_mode", None), "value", "") == "offline":
        # Model requests use the run-scoped local broker; web and browser tools
        # cannot create additional host-network requests from this worker. A
        # Google Calendar read is an external account request too.
        expanded = [name for name in expanded if name not in {
            "web_fetch", "browser", "google_calendar_events", "outlook_calendar_events"}]
    for name in expanded:
        if name == "delegate_task" and (ctx is None or ctx.delegation_submit is None):
            continue
        if name in {'remember', 'recall'} and not enabled:
            continue
        if name == "browser":
            from .browser import BrowserTool
            tools[name] = BrowserTool()
        elif name in _CATALOG:
            tools[name] = _CATALOG[name]()
    # A clarification is an ordinary conversation primitive, not a Bot-granted
    # action capability. It is never offered to scheduled or CLI-only runs.
    if ctx is not None and getattr(getattr(ctx, "run", None), "conversation_id", ""):
        tools["ask_user_choice"] = AskUserChoiceTool()
    if ctx is not None and getattr(getattr(ctx.bot, "inference_mode", None), "value", "") != "offline":
        grant_reader = getattr(ctx.store, "google_calendar_grant", None)
        grant = grant_reader(ctx.bot.id) if callable(grant_reader) else None
        if grant:
            tools["google_calendar_events"] = GoogleCalendarEventsTool(grant)
        outlook_grant_reader = getattr(ctx.store, "outlook_calendar_grant", None)
        outlook_grant = outlook_grant_reader(ctx.bot.id) if callable(outlook_grant_reader) else None
        if outlook_grant:
            tools["outlook_calendar_events"] = OutlookCalendarEventsTool(outlook_grant)
    return tools


__all__ = [
    "Tool", "ToolContext", "ToolResult",
    "build_tools", "expand_tools", "GROUPS", "ALL_TOOL_NAMES",
]
