"""Tool registry — maps bot tool allowlists to tool instances."""

from __future__ import annotations

from .base import Tool, ToolContext, ToolResult
from .files import FilesListTool, FilesReadTool, FilesWriteTool
from .memory import MemoryRecallTool, MemorySaveTool
from .shell import ShellTool
from .webfetch import WebFetchTool
from .delegation import DelegateTaskTool
from .choice import AskUserChoiceTool
from .documents import CreateDocumentTool, InspectDocumentTool, ReviseDocumentTool
from .skill import UseSkillTool
from .live import InspectMediaTool, LiveSearchTool
from .google_calendar import GoogleCalendarCreateEventTool, GoogleCalendarEventsTool
from .outlook_calendar import OutlookCalendarEventsTool
from .outlook_calendar_write import OutlookCalendarCreateEventTool
from .outlook_mail import OutlookMailSearchTool
from .google_mail import GoogleMailSearchTool
from .synthesis import (
    IngestSourceTool,
    RegisterManifestTool,
    RegisterScriptTool,
    RenderAudioOverviewTool,
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
    "delegate_task": DelegateTaskTool,
    "live_search": LiveSearchTool,
    "inspect_media": InspectMediaTool,
    "ingest_source": IngestSourceTool,
    "register_manifest": RegisterManifestTool,
    "register_script": RegisterScriptTool,
    "render_audio_overview": RenderAudioOverviewTool,
    "plan_workspace_action": PlanWorkspaceActionTool,
    "run_workspace_plan": RunWorkspacePlanTool,
}

#: bot-level tool groups that expand to concrete tool names
GROUPS: dict[str, list[str]] = {
    "files": ["read_file", "list_files", "write_file"],
    "documents": ["create_document", "revise_document", "inspect_document"],
    "memory": ["remember", "recall"],
    "browser": ["browser"],
    "grounding": ["live_search", "inspect_media"],
    "synthesis": ["ingest_source", "register_manifest", "register_script", "render_audio_overview"],
    "workspace": ["plan_workspace_action", "run_workspace_plan"],
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
            "web_fetch", "browser", "live_search", "google_calendar_events", "google_calendar_create_event",
            "outlook_calendar_events", "outlook_calendar_create_event", "outlook_mail_search",
            "render_audio_overview", "run_workspace_plan"}]
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
    # Skills are instruction packages resolved for this run, not bot-granted action tools. The
    # activation tool exists only when the run has a non-empty trusted catalog, and its results
    # are untrusted instruction text routed through the same tool pipeline as everything else.
    resolved_skills = getattr(ctx, "skills", None) if ctx is not None else None
    if resolved_skills is not None and getattr(resolved_skills, "catalog", None):
        tools["use_skill"] = UseSkillTool(resolved_skills)
    # A clarification is an ordinary conversation primitive, not a Bot-granted
    # action capability. It is never offered to scheduled or CLI-only runs.
    if ctx is not None and getattr(getattr(ctx, "run", None), "conversation_id", ""):
        tools["ask_user_choice"] = AskUserChoiceTool()
    if ctx is not None and getattr(getattr(ctx.bot, "inference_mode", None), "value", "") != "offline":
        grant_reader = getattr(ctx.store, "google_calendar_grant", None)
        grant = grant_reader(ctx.bot.id) if callable(grant_reader) else None
        if grant:
            tools["google_calendar_events"] = GoogleCalendarEventsTool(grant)
            if grant.get("allow_event_creation"):
                tools["google_calendar_create_event"] = GoogleCalendarCreateEventTool(grant)
        outlook_grant_reader = getattr(ctx.store, "outlook_calendar_grant", None)
        outlook_grant = outlook_grant_reader(ctx.bot.id) if callable(outlook_grant_reader) else None
        if outlook_grant:
            tools["outlook_calendar_events"] = OutlookCalendarEventsTool(outlook_grant)
        outlook_write_grant_reader = getattr(ctx.store, "outlook_calendar_write_grant", None)
        outlook_write_grant = (outlook_write_grant_reader(ctx.bot.id)
                               if callable(outlook_write_grant_reader) else None)
        if outlook_write_grant:
            tools["outlook_calendar_create_event"] = OutlookCalendarCreateEventTool(outlook_write_grant)
        outlook_mail_grant_reader = getattr(ctx.store, "outlook_mail_grant", None)
        outlook_mail_grant = outlook_mail_grant_reader(ctx.bot.id) if callable(outlook_mail_grant_reader) else None
        if outlook_mail_grant:
            tools["outlook_mail_search"] = OutlookMailSearchTool(outlook_mail_grant)
        outlook_mail_send_grant_reader = getattr(ctx.store, "outlook_mail_send_grant", None)
        outlook_mail_send_grant = (outlook_mail_send_grant_reader(ctx.bot.id)
                                   if callable(outlook_mail_send_grant_reader) else None)
        if outlook_mail_send_grant:
            from .outlook_mail_send import OutlookMailSendTool
            tools["outlook_mail_send"] = OutlookMailSendTool(outlook_mail_send_grant)
        google_mail_send_grant_reader = getattr(ctx.store, "google_mail_send_grant", None)
        google_mail_send_grant = (google_mail_send_grant_reader(ctx.bot.id)
                                  if callable(google_mail_send_grant_reader) else None)
        if google_mail_send_grant:
            from .google_mail_send import GoogleMailSendTool
            tools["google_mail_send"] = GoogleMailSendTool(google_mail_send_grant)
    if ctx is not None and getattr(getattr(ctx.bot, "inference_mode", None), "value", "") == "local":
        # Gmail's restricted data stays with an explicitly loopback-routed
        # built-in Bot. Also omit the tool if later Bot edits add remote
        # fallbacks or move its primary endpoint off this machine.
        from ..google_mail import validate_local_gmail_bot
        from ..google_calendar import GoogleCalendarError
        google_mail_grant_reader = getattr(ctx.store, "google_mail_grant", None)
        google_mail_grant = google_mail_grant_reader(ctx.bot.id) if callable(google_mail_grant_reader) else None
        try:
            validate_local_gmail_bot(ctx.bot)
            gmail_route_is_local = True
        except GoogleCalendarError:
            gmail_route_is_local = False
        if google_mail_grant and gmail_route_is_local:
            tools["google_mail_search"] = GoogleMailSearchTool(google_mail_grant)
    return tools


__all__ = [
    "Tool", "ToolContext", "ToolResult",
    "build_tools", "expand_tools", "GROUPS", "ALL_TOOL_NAMES",
]
