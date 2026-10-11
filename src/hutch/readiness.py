"""Execution readiness for one Bot: why a workflow can or cannot run right now.

Readiness is deliberately not one boolean. Each area reports its own state —

* ``runtime``     the selected runtime is supported and installed
* ``model``       a usable, configured model route for this Bot
* ``tools``       every enabled tool exists, is supported by the runtime, and offline mode's removed tools are shown
* ``skills``      each bound skill is installed, reviewed, enabled, compatible, and has the tools and connections it declares
* ``connections`` required accounts are granted for the tools and skills this Bot actually uses

— and the frontend renders the same structure the API returns, so what a person sees is what the
backend enforces. ``missing`` marks something that blocks the configured workflow; ``warning``
marks a visible, explained capability loss that does not block the rest of the Bot. Nothing here
calls a provider or spends money: these are local configuration and local-state checks.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import Bot
from .skills import CONNECTION_SERVICE_LABELS, SkillError, SkillRegistry  # noqa: F401  (re-exported for callers)
from .tools import ALL_TOOL_NAMES, GROUPS, expand_tools

#: Tools whose availability depends on a granted external account, and the store reader that proves it.
_CONNECTION_TOOLS: dict[str, tuple[str, str]] = {
    "google_calendar_events": ("google-calendar", "a Google Calendar connection granted to this Bot"),
    "google_calendar_create_event": ("google-calendar-write", "a Google Calendar connection with event-creation consent"),
    "outlook_calendar_events": ("outlook-calendar", "an Outlook Calendar connection granted to this Bot"),
    "outlook_calendar_create_event": ("outlook-calendar-write", "an Outlook Calendar write connection granted to this Bot"),
    "outlook_mail_search": ("outlook-mail", "an Outlook Mail connection granted to this Bot"),
    "outlook_mail_send": ("outlook-mail-send", "an Outlook Mail send connection granted to this Bot"),
    "google_mail_search": ("google-mail", "a Gmail search connection (private preview)"),
    "google_mail_send": ("google-mail-send", "a Gmail send connection granted to this Bot"),
}

#: service id -> store grant reader. Read-only; absence of the reader means "not granted".
_CONNECTION_READERS: dict[str, str] = {
    "outlook-mail": "outlook_mail_grant",
    "outlook-mail-send": "outlook_mail_send_grant",
    "outlook-calendar": "outlook_calendar_grant",
    "outlook-calendar-write": "outlook_calendar_write_grant",
    "google-calendar": "google_calendar_grant",
    "google-calendar-write": "google_calendar_grant",
    "google-mail": "google_mail_grant",
    "google-mail-send": "google_mail_send_grant",
}


def _grant(store, bot: Bot, service: str) -> bool:
    reader_name = _CONNECTION_READERS.get(service)
    reader = getattr(store, reader_name, None) if reader_name else None
    if not callable(reader):
        return False
    try:
        grant = reader(bot.id)
    except Exception:  # noqa: BLE001 - a store read must not break the report
        return False
    if not grant:
        return False
    if service == "google-calendar-write":
        return bool(grant.get("allow_event_creation")) if isinstance(grant, dict) else bool(grant)
    return True


def available_connection_services(store, bot: Bot) -> set[str]:
    """The external-account prerequisites this Bot currently satisfies (used by runs and readiness)."""
    return {service for service in _CONNECTION_READERS if _grant(store, bot, service)}


def _area(area_id: str, label: str, status: str, items: list[dict], note: str = "") -> dict:
    return {"id": area_id, "label": label, "status": status, "items": items, "note": note}


def _status_of(items: list[dict]) -> str:
    if any(item.get("status") == "missing" for item in items):
        return "missing"
    if any(item.get("status") == "unsupported" for item in items):
        return "unsupported"
    if any(item.get("status") == "warning" for item in items):
        return "warning"
    return "ok"


def bot_readiness(store, config, bot: Bot) -> dict:
    """Resolve the structured readiness report for one Bot. Never raises for user data issues."""
    areas: list[dict] = []
    granted_services = available_connection_services(store, bot)

    # ---------------------------------------------------------------- runtime
    runtime_items: list[dict] = [{
        "name": bot.runtime.value,
        "status": "ok" if bot.runtime.value == "builtin" else "unsupported",
        "detail": "Hutch's built-in supervised runtime" if bot.runtime.value == "builtin"
                  else "external runtimes do not inherit Hutch skills, approvals or budgets",
    }]
    runtime_status = _status_of(runtime_items)
    areas.append(_area("runtime", "Runtime", runtime_status, runtime_items,
                       note="Skills and approvals are enforced by the built-in runtime." if runtime_status != "ok" else ""))

    # ------------------------------------------------------------------ model
    model_items: list[dict] = []
    model_note = ""
    if not (bot.model or "").strip():
        model_items.append({"name": "model route", "status": "missing",
                            "detail": "no model route is configured for this Bot"})
        model_note = "Choose a model in Connections, then set it here or as the workspace default."
    else:
        try:
            from .modelchoices import ModelNotUsable, validate_override
            validate_override(config, store, bot, bot.model)
            model_items.append({"name": bot.model, "status": "ok", "detail": "configured route"})
        except ModelNotUsable as exc:
            model_items.append({"name": bot.model, "status": "missing",
                                "detail": str(exc) + (f" — {exc.fix}" if exc.fix else "")})
        except Exception as exc:  # noqa: BLE001 - readiness must never break the settings page
            model_items.append({"name": bot.model, "status": "warning", "detail": f"could not be checked: {exc}"})
    areas.append(_area("model", "Model", _status_of(model_items), model_items, note=model_note))

    # ------------------------------------------------------------------ tools
    offline = getattr(bot.inference_mode, "value", "") == "offline"
    enabled = expand_tools(list(bot.tools or []))
    tool_items: list[dict] = []
    for name in enabled:
        if name not in ALL_TOOL_NAMES and name != "browser" and not any(name in names for names in GROUPS.values()):
            tool_items.append({"name": name, "status": "missing", "detail": "unknown tool name"})
            continue
        detail = ""
        status = "ok"
        if offline and name in {"web_fetch", "browser", "google_calendar_events", "google_calendar_create_event",
                                "outlook_calendar_events", "outlook_calendar_create_event", "outlook_mail_search"}:
            status, detail = "warning", "withheld in Strict Offline mode"
        if not bot.memory_enabled and name in {"remember", "recall"}:
            status, detail = "warning", "withheld because memory is disabled for this Bot"
        tool_items.append({"name": name, "status": status, "detail": detail})
    if not enabled:
        tool_items.append({"name": "tools", "status": "warning",
                           "detail": "no tools are enabled: this Bot can only talk"})
    tool_status = _status_of(tool_items)
    tool_note = ""
    if bot.runtime.value != "builtin":
        tool_note = "External runtimes decide their own tools; Hutch cannot enforce this tool list there."
    areas.append(_area("tools", "Tools", tool_status, tool_items, note=tool_note))

    # ----------------------------------------------------------------- skills
    skill_items: list[dict] = []
    registry = SkillRegistry(config.state_dir)
    requirement_status: dict[str, str] = {}
    try:
        for name in list(bot.skills or []):
            skill, reason, code = registry.resolve_binding(
                bot, name, available_connections=granted_services)
            if skill is not None:
                skill_items.append({"name": name, "status": "ok", "detail": "reviewed and loadable"})
                requirement_status[name] = "ok"
                continue
            status = {
                "not_installed": "missing",
                "runtime_unsupported": "unsupported",
                "modified": "warning",
                "unreviewed": "warning",
                "disabled": "warning",
                "unreadable": "warning",
                "requires_tools": "warning",
                "requires_connections": "warning",
            }.get(code, "warning")
            requirement_status[name] = code
            skill_items.append({"name": name, "status": status, "detail": reason})
    except Exception as exc:  # noqa: BLE001 - a store read or package inspection must not 500 the settings page
        skill_items.append({"name": "skills", "status": "warning", "detail": f"could not be resolved: {exc}"})
    if not bot.skills:
        skill_items = [{"name": "skills", "status": "ok", "detail": "none assigned"}]
    areas.append(_area("skills", "Skills", _status_of(skill_items), skill_items))

    # ------------------------------------------------------------ connections
    connection_items: list[dict] = []
    for name in enabled:
        requirement = _CONNECTION_TOOLS.get(name)
        if requirement is None:
            continue
        service, description = requirement
        if _grant(store, bot, service):
            connection_items.append({"name": name, "status": "ok", "detail": f"{CONNECTION_SERVICE_LABELS.get(service, service)} granted for this Bot"})
        else:
            connection_items.append({"name": name, "status": "missing", "detail": f"requires {description}"})
    for requirement in registry.binding_requirements(bot):
        for service in requirement["requires_connections"]:
            label = CONNECTION_SERVICE_LABELS.get(service, service)
            if _grant(store, bot, service):
                connection_items.append({"name": service, "status": "ok",
                                         "detail": f"{label} granted for this Bot (skill '{requirement['name']}')"})
            else:
                connection_items.append({"name": service, "status": "missing",
                                         "detail": f"skill '{requirement['name']}' requires {label}, which is not granted to this Bot"})
    if not connection_items:
        connection_items = [{"name": "connections", "status": "ok",
                             "detail": "no external accounts required by the enabled tools or skills"}]
    areas.append(_area("connections", "Connections", _status_of(connection_items), connection_items))

    blocked = [area["id"] for area in areas if area["status"] == "missing"]
    return {
        "bot_id": bot.id,
        "bot_name": bot.name,
        "ready": not blocked,
        "blocked_areas": blocked,
        "areas": areas,
        "mode": {"inference_mode": bot.inference_mode.value, "approval_mode": bot.approval_mode.value,
                 "risk_tier": bot.risk_tier.value, "workspace_mode": "folder" if bot.workdir else bot.workspace_mode},
    }
