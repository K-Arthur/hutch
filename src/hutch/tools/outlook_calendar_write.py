"""Exact-approval, create-only Outlook Calendar action."""

from __future__ import annotations

import os
from typing import Any

from ..approvals import DeniedError
from ..outlook_calendar import OutlookCalendarError
from ..outlook_calendar_write import OutlookCalendarWriteBook, OutlookCalendarWriteOutcomeUnknown
from .base import Tool, ToolContext, ToolResult, _schema


class OutlookCalendarCreateEventTool(Tool):
    name = "outlook_calendar_create_event"
    parameters = _schema(["summary", "start", "end"], {
        "summary": {"type": "string", "minLength": 1, "maxLength": 180,
                     "description": "Event title shown exactly in the approval."},
        "start": {"type": "string", "minLength": 20, "maxLength": 64,
                  "description": "ISO 8601 start date-time with an explicit time zone offset."},
        "end": {"type": "string", "minLength": 20, "maxLength": 64,
                "description": "ISO 8601 end date-time with an explicit time zone offset, after start and within 366 days."},
        "description": {"type": "string", "maxLength": 2000, "description": "Optional plain-text event description."},
        "location": {"type": "string", "maxLength": 300, "description": "Optional event location."},
    })

    def __init__(self, grant: dict[str, Any]):
        self.grant = dict(grant)
        self.description = (
            "Create one guest-free event on the one Outlook calendar explicitly granted to this Bot: "
            f"{self.grant.get('calendar_name') or 'selected calendar'} "
            f"({self.grant.get('account_label') or 'selected account'}). Each event requires exact owner approval, "
            "including in automatic mode. The approval shows the title, time, description, location, account and calendar. "
            "This action cannot edit or delete events, and an uncertain result is never retried automatically.")

    def effect(self, args: dict, ctx: ToolContext) -> str:
        return "web"

    def recorded_arguments(self, args: dict, ctx: ToolContext) -> dict:
        prepared = OutlookCalendarWriteBook.prepare_event(summary=args.get("summary", ""),
            start=args.get("start", ""), end=args.get("end", ""), description=args.get("description", ""),
            location=args.get("location", ""))
        return {**prepared, "account_id": self.grant["account_id"], "account_label": self.grant["account_label"],
                "calendar_id": self.grant["calendar_id"], "calendar_name": self.grant["calendar_name"]}

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.dry_run:
            return ToolResult(True,
                "[rehearsal] would request exact approval, then create one guest-free Outlook event. Nothing was changed.",
                {"simulated": True})
        grant_reader = getattr(ctx.store, "outlook_calendar_write_grant", None)
        current = grant_reader(ctx.bot.id) if callable(grant_reader) else None
        grant_fields = ("account_id", "account_label", "calendar_id", "calendar_name")
        if not current or any(current.get(field) != self.grant.get(field) for field in grant_fields):
            return ToolResult(False,
                "Outlook Calendar event creation was removed or changed; review this Bot's Connections grant.")
        try:
            event = OutlookCalendarWriteBook.prepare_event(summary=args.get("summary", ""),
                start=args.get("start", ""), end=args.get("end", ""), description=args.get("description", ""),
                location=args.get("location", ""))
        except OutlookCalendarError as exc:
            return ToolResult(False, str(exc))
        detail = {
            "account_id": current["account_id"], "account": current["account_label"],
            "calendar_id": current["calendar_id"], "calendar": current["calendar_name"],
            "event": event,
            "effect": "create one guest-free event; this Bot cannot edit or delete events",
            "permission": "Microsoft's separate Calendars.ReadWrite consent covers the signed-in user's calendars; Hutch exposes create only on this selected calendar to this Bot",
            "uncertain_result": "check the selected calendar before retrying",
        }
        try:
            ctx.gate.decide(self.name, f"Create event in {current['calendar_name']}: {event['summary'][:120]}",
                            detail, outward=True, ask_in_auto=True)
        except DeniedError as exc:
            return ToolResult(False, f"event creation was not approved; nothing was changed ({exc})")

        current = grant_reader(ctx.bot.id) if callable(grant_reader) else None
        if not current or any(current.get(field) != self.grant.get(field) for field in grant_fields):
            return ToolResult(False,
                "Outlook Calendar event-creation access changed while approval was pending; no event was created.")
        try:
            book = OutlookCalendarWriteBook(ctx.config.state_dir,
                os.environ.get("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", ""))
            created = book.create_event(current["account_id"], current["calendar_id"],
                summary=event["summary"], start=event["start"], end=event["end"],
                description=event["description"], location=event["location"], before_write=ctx.begin_effect)
        except OutlookCalendarWriteOutcomeUnknown as exc:
            from ..runtime.base import RunAborted
            raise RunAborted("outcome_unknown", str(exc)) from exc
        except OutlookCalendarError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True,
            f"Created {created['summary']} on {current['calendar_name']} ({created['start']} to {created['end']}).",
            {"created": True, "event_id": created["id"], "calendar_id": current["calendar_id"],
             "verified": True, "read_only": False})


__all__ = ["OutlookCalendarCreateEventTool"]
