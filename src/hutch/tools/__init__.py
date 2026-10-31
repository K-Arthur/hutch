"""Tool registry: maps bot tool allowlists to tool instances.

Tool classes are imported on first use rather than at module import, so cheap callers
(``hutch version``/``status``/``--help``, the dashboard process) do not pay for the full
tool import graph. ``_CATALOG`` remains a read-only mapping of name to tool class.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from importlib import import_module

from .base import Tool, ToolContext, ToolResult

#: name -> (module under hutch.tools, tool class). Tool classes are imported on first use so
#: that importing this registry stays cheap: quick CLI commands (version/status/--help) and the
#: dashboard process do not pay for the whole tool import graph, only a run that grants a tool
#: imports it. Keep this table in catalog order; it defines tool-definition ordering.
_SPECS: dict[str, tuple[str, str]] = {
    "shell": ("shell", "ShellTool"),
    "read_file": ("files", "FilesReadTool"),
    "list_files": ("files", "FilesListTool"),
    "write_file": ("files", "FilesWriteTool"),
    "remember": ("memory", "MemorySaveTool"),
    "recall": ("memory", "MemoryRecallTool"),
    "capture_commitment": ("commitments", "CaptureCommitmentTool"),
    "list_commitments": ("commitments", "ListCommitmentsTool"),
    "report_commitment_done": ("commitments", "ReportCommitmentDoneTool"),
    "web_fetch": ("webfetch", "WebFetchTool"),
    "create_document": ("documents", "CreateDocumentTool"),
    "revise_document": ("documents", "ReviseDocumentTool"),
    "inspect_document": ("documents", "InspectDocumentTool"),
    "create_media": ("media", "CreateMediaTool"),
    "render_diagram": ("media", "RenderDiagramTool"),
    "run_python": ("python_exec", "RunPythonTool"),
    "reset_workspace": ("python_exec", "ResetWorkspaceTool"),
    "delegate_task": ("delegation", "DelegateTaskTool"),
    "live_search": ("live", "LiveSearchTool"),
    "inspect_media": ("live", "InspectMediaTool"),
    "ingest_source": ("synthesis", "IngestSourceTool"),
    "register_manifest": ("synthesis", "RegisterManifestTool"),
    "register_script": ("synthesis", "RegisterScriptTool"),
    "render_audio_overview": ("synthesis", "RenderAudioOverviewTool"),
    "render_infographic": ("synthesis", "RenderInfographicTool"),
    "plan_workspace_action": ("workspace_actions", "PlanWorkspaceActionTool"),
    "run_workspace_plan": ("workspace_actions", "RunWorkspacePlanTool"),
    "draft_workflow": ("workflow_draft", "DraftWorkflowTool"),
}

_RESOLVED: dict[str, type[Tool]] = {}


def _tool_class(name: str) -> type[Tool]:
    """Import and memoize the tool class for one catalog name."""
    try:
        return _RESOLVED[name]
    except KeyError:
        module_name, class_name = _SPECS[name]
        cls = getattr(import_module(f"{__name__}.{module_name}"), class_name)
        _RESOLVED[name] = cls
        return cls


class _LazyCatalog(Mapping[str, type[Tool]]):
    """Read-only name -> tool-class mapping that imports a class only when it is looked up."""

    def __getitem__(self, name: str) -> type[Tool]:
        return _tool_class(name)

    def __iter__(self) -> Iterator[str]:
        return iter(_SPECS)

    def __len__(self) -> int:
        return len(_SPECS)


#: name -> tool class (browser/computer stay lazy too: their dependencies are optional).
_CATALOG: Mapping[str, type[Tool]] = _LazyCatalog()

#: Tool submodules, kept reachable as package attributes (the old eager imports bound them).
_MODULES = frozenset(module_name for module_name, _ in _SPECS.values()) | {"browser", "computer"}


def __getattr__(name: str):
    """Import a tool submodule on attribute access, matching the eager-import surface."""
    if name in _MODULES:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

#: bot-level tool groups that expand to concrete tool names
GROUPS: dict[str, list[str]] = {
    "files": ["read_file", "list_files", "write_file"],
    "documents": ["create_document", "revise_document", "inspect_document"],
    "media": ["create_media", "render_diagram"],
    "workspace": ["run_python", "reset_workspace"],
    # Keep account-backed workspace actions opt-in. The existing ``workspace`` group
    # predates these tools and is used by Bots that should only get local scratch access.
    "workspace_actions": ["plan_workspace_action", "run_workspace_plan"],
    "memory": ["remember", "recall"],
    "commitments": ["capture_commitment", "list_commitments", "report_commitment_done"],
    "browser": ["browser"],
    "computer": ["computer"],
    "grounding": ["live_search", "inspect_media"],
    "synthesis": ["ingest_source", "register_manifest", "register_script",
                  "render_audio_overview", "render_infographic"],
}

ALL_TOOL_NAMES = sorted(_SPECS) + ["browser", "computer"]


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
        # The computer tool launches applications that can make their own network requests, and strict-offline behavior for
        # an isolated desktop has not been verified: withheld rather than implied.
        from ..integrations.catalog import OFFLINE_WITHHELD_TOOLS
        expanded = [name for name in expanded if name not in OFFLINE_WITHHELD_TOOLS]
    for name in expanded:
        if name == "delegate_task" and (ctx is None or ctx.delegation_submit is None):
            continue
        if name in {'remember', 'recall'} and not enabled:
            continue
        if name == "browser":
            from .browser import BrowserTool
            tools[name] = BrowserTool()
        elif name == "computer":
            from .computer import ComputerTool
            tools[name] = ComputerTool()
        elif name in _SPECS:
            tools[name] = _tool_class(name)()
    # Skills are instruction packages resolved for this run, not bot-granted action tools. The
    # activation tool exists only when the run has a non-empty trusted catalog, and its results
    # are untrusted instruction text routed through the same tool pipeline as everything else.
    resolved_skills = getattr(ctx, "skills", None) if ctx is not None else None
    if resolved_skills is not None and getattr(resolved_skills, "catalog", None):
        from .skill import UseSkillTool
        tools["use_skill"] = UseSkillTool(resolved_skills)
    # A clarification is an ordinary conversation primitive, not a Bot-granted
    # action capability. It is never offered to scheduled or CLI-only runs, and a
    # delegated child cannot ask the owner directly: it shares the parent's
    # conversation while the parent blocks waiting for its result, so an answer
    # could not reach it. A child that needs input reports it in its result text.
    if (ctx is not None and getattr(getattr(ctx, "run", None), "conversation_id", "")
            and not getattr(getattr(ctx, "run", None), "parent_run_id", None)):
        from .choice import AskUserChoiceTool
        tools["ask_user_choice"] = AskUserChoiceTool()
    if ctx is not None and getattr(getattr(ctx.bot, "inference_mode", None), "value", "") != "offline":
        local_gmail_ok = False
        if getattr(getattr(ctx.bot, "inference_mode", None), "value", "") == "local":
            # Gmail's restricted data stays with a loopback-routed Bot and is rechecked
            # whenever the run constructs its tool set.
            from ..google_mail import validate_local_gmail_bot
            from ..google_calendar import GoogleCalendarError
            try:
                validate_local_gmail_bot(ctx.bot)
                local_gmail_ok = True
            except GoogleCalendarError:
                pass
        from ..integrations.catalog import construct_connection_tools
        tools.update(construct_connection_tools(ctx.store, ctx.bot, local_gmail_ok=local_gmail_ok))
        from .notion import construct_notion_tools
        tools.update(construct_notion_tools(ctx.store, ctx.bot, getattr(ctx, "run", None)))
        from .kdeconnect import construct_kdeconnect_tools
        tools.update(construct_kdeconnect_tools(ctx.store, ctx.bot, getattr(ctx, "run", None)))
    return tools


__all__ = [
    "Tool", "ToolContext", "ToolResult",
    "build_tools", "expand_tools", "GROUPS", "ALL_TOOL_NAMES",
]
