"""Tool registry — maps bot tool allowlists to tool instances."""

from __future__ import annotations

from .base import Tool, ToolContext, ToolResult
from .files import FilesListTool, FilesReadTool, FilesWriteTool
from .memory import MemoryRecallTool, MemorySaveTool
from .shell import ShellTool
from .webfetch import WebFetchTool

#: name -> factory (browser is imported lazily so the dependency stays optional)
_CATALOG: dict[str, type[Tool]] = {
    "shell": ShellTool,
    "read_file": FilesReadTool,
    "list_files": FilesListTool,
    "write_file": FilesWriteTool,
    "remember": MemorySaveTool,
    "recall": MemoryRecallTool,
    "web_fetch": WebFetchTool,
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


def build_tools(names: list[str], ctx: ToolContext) -> dict[str, Tool]:
    tools: dict[str, Tool] = {}
    for name in expand_tools(names):
        if name == "browser":
            from .browser import BrowserTool
            tools[name] = BrowserTool()
        elif name in _CATALOG:
            tools[name] = _CATALOG[name]()
    return tools


__all__ = [
    "Tool", "ToolContext", "ToolResult",
    "build_tools", "expand_tools", "GROUPS", "ALL_TOOL_NAMES",
]
