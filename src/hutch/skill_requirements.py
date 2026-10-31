"""Which tools a skill's declared requirements are checked against.

A skill declares ``hutch.requires-tools`` and Hutch has to decide whether the Bot can actually
reach them. Two kinds of tool exist and they behave differently:

* native tools live in the Bot's own allowlist, so the owner can add one by editing the Bot;
* connector tools are reviewed store grants on an MCP server, so the owner adds one in Connectors
  and it never appears in the allowlist at all.

Checking only the allowlist made every skill that required a connector tool look permanently
unsatisfiable, and told the owner to enable a tool that could not be enabled. The classification
below exists so the reason a skill cannot load names the place where it can be fixed.

Kept outside ``skills.py`` because that module is frozen over its size cap and shrinks only.
"""

from __future__ import annotations

from typing import Iterable, Optional

#: Tools a Strict Offline run withholds because the worker has no host network.
OFFLINE_WITHHELD = frozenset({
    "web_fetch", "browser", "google_calendar_events", "google_calendar_create_event",
    "outlook_calendar_events", "outlook_calendar_create_event", "outlook_mail_search",
    "google_mail_search",
})

#: The namespace every connector tool shares (``mcp__<integration>__<tool>``).
CONNECTOR_PREFIX = "mcp__"


def is_connector_tool(name: str) -> bool:
    return name.startswith(CONNECTOR_PREFIX)


def available_tools_for(bot, connector_tools: Optional[Iterable[str]] = None) -> set[str]:
    """Every tool name this Bot can reach at run time, from both authorities.

    ``connector_tools`` are the Bot's granted MCP tool names, read from the same store grant the
    runtime uses. Omitting them is a statement that the Bot has none, not a way to skip the check.
    """
    from .tools import expand_tools
    available = set(expand_tools(list(getattr(bot, "tools", []) or [])))
    available |= set(connector_tools or ())
    if getattr(getattr(bot, "inference_mode", None), "value", "") == "offline":
        available -= OFFLINE_WITHHELD
        # Strict Offline runs have no host network, so ``build_tools`` withholds connector tools
        # as well; counting a grant as reachable there would promise a tool that cannot run.
        available -= {name for name in available if is_connector_tool(name)}
    if not getattr(bot, "memory_enabled", True):
        available -= {"remember", "recall"}
    return available


def missing_tool_reason(skill_name: str, missing: list[str]) -> tuple[str, str]:
    """The owner-facing reason a skill cannot load, and the code that classifies it.

    A connector tool is not something the owner can enable on the Bot, so the message names
    Connectors instead of the Bot's tool list. Mixed cases stay generic on purpose: listing two
    different remedies in one sentence is how the original dead end was produced.
    """
    connectors = [tool for tool in missing if is_connector_tool(tool)]
    if connectors and len(connectors) == len(missing):
        names = ", ".join(connectors)
        return (f"skill '{skill_name}' requires the {names} connector tool(s), which is not "
                "granted to this Bot in Connectors"), "requires_connector_tools"
    return (f"skill '{skill_name}' requires the {', '.join(missing)} tool(s) this Bot does not enable",
            "requires_tools")


__all__ = ["CONNECTOR_PREFIX", "OFFLINE_WITHHELD", "available_tools_for", "is_connector_tool",
           "missing_tool_reason"]
