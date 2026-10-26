"""Tool registry — maps bot tool allowlists to tool instances."""

from __future__ import annotations

from .base import Tool, ToolContext, ToolResult
from .files import FilesListTool, FilesReadTool, FilesWriteTool
from .memory import MemoryRecallTool, MemorySaveTool
from .shell import ShellTool
from .webfetch import WebFetchTool
from .delegation import DelegateTaskTool
from .choice import AskUserChoiceTool
from .skill import UseSkillTool
from .documents import CreateDocumentTool, InspectDocumentTool, ReviseDocumentTool
from .media import CreateMediaTool, RenderDiagramTool
from .python_exec import ResetWorkspaceTool, RunPythonTool
from .live import InspectMediaTool, LiveSearchTool

from .workflow_draft import DraftWorkflowTool
from .synthesis import (
    IngestSourceTool,
    RegisterManifestTool,
    RegisterScriptTool,
    RenderAudioOverviewTool,
    RenderInfographicTool,
)
from .workspace_actions import PlanWorkspaceActionTool, RunWorkspacePlanTool

#: name -> factory (browser is imported lazily so the dependency stays optional)
_CATALOG: dict[str, type[Tool]] = {
    "shell": ShellTool,
    "read_file": FilesReadTool,
    "list_files": FilesListTool,
    "write_file": FilesWriteTool,
    "remember": MemorySaveTool,
    "recall": MemoryRecallTool,
    "web_fetch": WebFetchTool,
    "create_document": CreateDocumentTool,
    "revise_document": ReviseDocumentTool,
    "inspect_document": InspectDocumentTool,
    "create_media": CreateMediaTool,
    "render_diagram": RenderDiagramTool,
    "run_python": RunPythonTool,
    "reset_workspace": ResetWorkspaceTool,
    "delegate_task": DelegateTaskTool,
    "live_search": LiveSearchTool,
    "inspect_media": InspectMediaTool,
    "ingest_source": IngestSourceTool,
    "register_manifest": RegisterManifestTool,
    "register_script": RegisterScriptTool,
    "render_audio_overview": RenderAudioOverviewTool,
    "render_infographic": RenderInfographicTool,
    "plan_workspace_action": PlanWorkspaceActionTool,
    "run_workspace_plan": RunWorkspacePlanTool,

"draft_workflow": DraftWorkflowTool,
}

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
    "browser": ["browser"],
    "computer": ["computer"],
    "grounding": ["live_search", "inspect_media"],
    "synthesis": ["ingest_source", "register_manifest", "register_script",
                  "render_audio_overview", "render_infographic"],
}

ALL_TOOL_NAMES = sorted(_CATALOG) + ["browser", "computer"]


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
        elif name in _CATALOG:
            tools[name] = _CATALOG[name]()
    # Skills are instruction packages resolved for this run, not bot-granted action tools. The
    # activation tool exists only when the run has a non-empty trusted catalog, and its results
    # are untrusted instruction text routed through the same tool pipeline as everything else.
    resolved_skills = getattr(ctx, "skills", None) if ctx is not None else None
    if resolved_skills is not None and getattr(resolved_skills, "catalog", None):
        tools["use_skill"] = UseSkillTool(resolved_skills)
    # A clarification is an ordinary conversation primitive, not a Bot-granted
    # action capability. It is never offered to scheduled or CLI-only runs, and a
    # delegated child cannot ask the owner directly: it shares the parent's
    # conversation while the parent blocks waiting for its result, so an answer
    # could not reach it. A child that needs input reports it in its result text.
    if (ctx is not None and getattr(getattr(ctx, "run", None), "conversation_id", "")
            and not getattr(getattr(ctx, "run", None), "parent_run_id", None)):
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
    return tools


__all__ = [
    "Tool", "ToolContext", "ToolResult",
    "build_tools", "expand_tools", "GROUPS", "ALL_TOOL_NAMES",
]
