"""ONE derived source for the tool enumerations that shape a run (ADR-0017 §3.1, §5 S1, §8).

Four call sites enumerated tools by hand before S1 and had already drifted once (the offline
withheld list existed in two shapes). This module is the single source for all of them:

* the offline-withheld list            (was: tools/__init__.py and readiness.py, two copies)
* the browser special case             (was: ALL_TOOL_NAMES' tail, the lazy import, readiness's
                                       triple "unknown tool" check)
* the grant-gated connection tools     (was: build_tools' inline reader chain and readiness's
                                       _CONNECTION_TOOLS/_CONNECTION_READERS tables)
* the capability-snapshot enumeration  (was: engine.capability_snapshot's inline expand/filter/sort)

Two rules keep this honest. First, the registry itself (name → class, groups, expansion) stays
in ``hutch.tools``: the catalog derives FROM it and never redefines it, so there is no second
registry and no second enforcement path (binding constraint 2). Second, every consumer
(build_tools, readiness, the engine snapshot) reads its enumeration from here, so a new native
tool or a changed withholding rule is written once. (The fourth UI enumeration, ``TOOL_SETTINGS``
in app.js, is display-only and is frontend work, slice S9, not this one.)

The module imports nothing from ``hutch.tools`` at import time (function-level imports only), so
``hutch.tools`` may import this module freely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from ..models import Bot
    from ..tools.base import Tool

#: The browser is a real tool but a lazy import (its dependency is optional), so it is catalog
#: data everywhere a name list is needed and a class only inside build_tools.
BROWSER_TOOL_NAME = "browser"

#: Tools ``build_tools`` withholds in Strict Offline mode: model requests use the run-scoped
#: local broker, so web, browser and external-account tools cannot create additional host-network
#: requests from that worker. Document tools are local and correctly not withheld.
OFFLINE_WITHHELD_TOOLS = frozenset({
    "web_fetch", BROWSER_TOOL_NAME,
    "computer", "live_search", "render_audio_overview", "run_workspace_plan",
    "google_calendar_events", "google_calendar_create_event",
    "outlook_calendar_events", "outlook_calendar_create_event",
    "outlook_mail_search", "outlook_mail_send", "google_mail_send", "google_mail_search",
})

#: The narrower set the capability snapshot withholds for offline Bots. This is deliberately NOT
#: ``OFFLINE_WITHHELD_TOOLS``: the snapshot records declared routing policy (and delegation
#: narrows further at ``_delegated_bot``), while ``build_tools`` enforces the full list. Changing
#: this set would change persisted snapshots, it is pinned byte-stable under snapshot_version 1.
SNAPSHOT_OFFLINE_WITHHELD_TOOLS = frozenset({"web_fetch", BROWSER_TOOL_NAME})


@dataclass(frozen=True)
class ConnectionToolSpec:
    """One grant-gated external-account tool (the calendar/mail family).

    A grant is a reviewed store row bound to one Bot, never an allowlist string. The grant binds
    the account at construction, so model arguments can never choose a credential (§4.4).
    """

    name: str                # canonical tool name, also the ``build_tools`` result key
    service: str             # connections service id (readiness + CONNECTION_SERVICE_LABELS)
    grant_reader: str        # the Store method whose truthy result proves the grant
    description: str         # what readiness says is missing when the grant is absent
    consent_field: str = ""  # grant key that must additionally be truthy (explicit consent)
    requires_tool: str = ""  # another granted tool that must be present first
    local_only: bool = False # only for explicitly loopback-routed local Bots


#: Construction order is the historical ``build_tools`` order; keep it stable.
CONNECTION_TOOL_SPECS: tuple[ConnectionToolSpec, ...] = (
    ConnectionToolSpec(
        name="google_calendar_events", service="google-calendar", grant_reader="google_calendar_grant",
        description="a Google Calendar connection granted to this Bot"),
    ConnectionToolSpec(
        name="google_calendar_create_event", service="google-calendar-write",
        grant_reader="google_calendar_grant", description="a Google Calendar connection with event-creation consent",
        consent_field="allow_event_creation", requires_tool="google_calendar_events"),
    ConnectionToolSpec(
        name="outlook_calendar_events", service="outlook-calendar", grant_reader="outlook_calendar_grant",
        description="an Outlook Calendar connection granted to this Bot"),
    ConnectionToolSpec(
        name="outlook_calendar_create_event", service="outlook-calendar-write",
        grant_reader="outlook_calendar_write_grant",
        description="an Outlook Calendar write connection granted to this Bot"),
    ConnectionToolSpec(
        name="outlook_mail_search", service="outlook-mail", grant_reader="outlook_mail_grant",
        description="an Outlook Mail connection granted to this Bot"),
    ConnectionToolSpec(
        name="outlook_mail_send", service="outlook-mail-send", grant_reader="outlook_mail_send_grant",
        description="an Outlook Mail send connection granted to this Bot"),
    ConnectionToolSpec(
        name="google_mail_send", service="google-mail-send", grant_reader="google_mail_send_grant",
        description="a Gmail send connection granted to this Bot"),
    ConnectionToolSpec(
        name="google_mail_search", service="google-mail", grant_reader="google_mail_grant",
        description="a Gmail search connection (private preview)", local_only=True),
)

#: canonical tool name -> its spec.
CONNECTION_TOOLS: dict[str, ConnectionToolSpec] = {spec.name: spec for spec in CONNECTION_TOOL_SPECS}

#: service id -> the Store grant reader that proves it (one derivation for readiness and skills).
CONNECTION_SERVICE_READERS: dict[str, str] = {
    spec.service: spec.grant_reader for spec in CONNECTION_TOOL_SPECS
}


def connection_service_granted(store: Any, bot: "Bot", service: str) -> bool:
    """True if the reviewed grant row (and any explicit consent field) exists for this Bot."""
    reader_name = CONNECTION_SERVICE_READERS.get(service)
    reader = getattr(store, reader_name, None) if reader_name else None
    if not callable(reader):
        return False
    try:
        grant = reader(bot.id)
    except Exception:  # noqa: BLE001 - a store read must not break the readiness report
        return False
    if not grant:
        return False
    consent = next((spec.consent_field for spec in CONNECTION_TOOL_SPECS if spec.service == service
                    and spec.consent_field), "")
    spec = next((spec for spec in CONNECTION_TOOL_SPECS if spec.service == service), None)
    if spec and spec.local_only:
        if getattr(getattr(bot, "inference_mode", None), "value", "") != "local":
            return False
        try:
            from ..google_mail import validate_local_gmail_bot
            validate_local_gmail_bot(bot)
        except Exception:  # noqa: BLE001 - invalid routes fail closed in readiness too
            return False
    if consent:
        return bool(grant.get(consent)) if isinstance(grant, dict) else bool(grant)
    return True


def available_connection_services(store: Any, bot: "Bot") -> set[str]:
    """The external-account prerequisites this Bot currently satisfies (used by runs and readiness)."""
    return {spec.service for spec in CONNECTION_TOOL_SPECS
            if connection_service_granted(store, bot, spec.service)}


def construct_connection_tools(store: Any, bot: "Bot", *, local_gmail_ok: bool = False) -> dict[str, "Tool"]:
    """Construct the grant-gated calendar/mail tools this Bot's store grants prove.

    One grant-resolution implementation for every consumer: ``build_tools`` calls this for the run,
    and the context-free estimator (S5) calls it for the same bot with the same store readers, so
    inclusion decisions cannot diverge between admission and execution.
    """
    from ..tools.google_calendar import GoogleCalendarCreateEventTool, GoogleCalendarEventsTool
    from ..tools.google_mail import GoogleMailSearchTool
    from ..tools.google_mail_send import GoogleMailSendTool
    from ..tools.outlook_calendar import OutlookCalendarEventsTool
    from ..tools.outlook_calendar_write import OutlookCalendarCreateEventTool
    from ..tools.outlook_mail import OutlookMailSearchTool
    from ..tools.outlook_mail_send import OutlookMailSendTool

    classes: dict[str, Any] = {
        "google_calendar_events": GoogleCalendarEventsTool,
        "google_calendar_create_event": GoogleCalendarCreateEventTool,
        "outlook_calendar_events": OutlookCalendarEventsTool,
        "outlook_calendar_create_event": OutlookCalendarCreateEventTool,
        "outlook_mail_search": OutlookMailSearchTool,
        "outlook_mail_send": OutlookMailSendTool,
        "google_mail_send": GoogleMailSendTool,
        "google_mail_search": GoogleMailSearchTool,
    }
    tools: dict[str, "Tool"] = {}
    for spec in CONNECTION_TOOL_SPECS:
        if spec.local_only and not local_gmail_ok:
            continue
        reader = getattr(store, spec.grant_reader, None)
        grant = reader(bot.id) if callable(reader) else None
        if not grant:
            continue
        if spec.requires_tool and spec.requires_tool not in tools:
            continue
        if spec.consent_field and not grant.get(spec.consent_field):
            continue
        tools[spec.name] = classes[spec.name](grant)
    return tools


def known_tool_names() -> set[str]:
    """Every tool name a Bot's allowlist may legally contain: the native catalog, the browser, and
    every group member. One derivation for build_tools, readiness and validation."""
    from ..tools import ALL_TOOL_NAMES, GROUPS
    names = set(ALL_TOOL_NAMES)
    for group in GROUPS.values():
        names.update(group)
    names.update(CONNECTION_TOOLS)
    return names


def is_known_tool_name(name: str) -> bool:
    return name in known_tool_names()


def offline_withheld(enabled: list[str]) -> list[str]:
    """The enabled tool names Strict Offline withholds, in the caller's order."""
    return [name for name in enabled if name in OFFLINE_WITHHELD_TOOLS]


def snapshot_tool_names(bot_tools: list[str], *, offline: bool, tool_access: str = "bot") -> list[str]:
    """The tool-name list a capability snapshot records (the engine's enumeration, derived once).

    Reproduces the v1 behavior exactly, group expansion, the narrower offline withholding set,
    sorted output, because persisted snapshots are pinned byte-stable under ``snapshot_version: 1``
    and the delegation admission gate hard-rejects any other version (engine._delegated_bot).
    """
    from ..tools import expand_tools
    tools = [] if tool_access == "none" else expand_tools(list(bot_tools))
    if offline:
        tools = [name for name in tools if name not in SNAPSHOT_OFFLINE_WITHHELD_TOOLS]
    return sorted(tools)


__all__ = [
    "BROWSER_TOOL_NAME", "OFFLINE_WITHHELD_TOOLS", "SNAPSHOT_OFFLINE_WITHHELD_TOOLS",
    "CONNECTION_TOOL_SPECS", "CONNECTION_TOOLS", "CONNECTION_SERVICE_READERS",
    "ConnectionToolSpec", "available_connection_services", "connection_service_granted",
    "construct_connection_tools", "known_tool_names", "is_known_tool_name",
    "offline_withheld", "snapshot_tool_names",
]
