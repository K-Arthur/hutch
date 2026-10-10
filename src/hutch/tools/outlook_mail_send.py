"""Owner-approved, one-shot Outlook Mail sending."""

from __future__ import annotations

import os
from typing import Any

from ..approvals import DeniedError
from ..outlook_calendar import OutlookCalendarError
from ..outlook_mail import (OutlookMailSendBook, OutlookMailSendOutcomeUnknown)
from .base import Tool, ToolContext, ToolResult, _schema


class OutlookMailSendTool(Tool):
    name = "outlook_mail_send"
    parameters = _schema(["to", "subject", "body"], {
        "to": {"type": "array", "minItems": 1, "maxItems": 5, "items": {"type": "string", "maxLength": 254},
               "description": "One to five email addresses. Each address is shown in the approval."},
        "subject": {"type": "string", "minLength": 1, "maxLength": 180,
                    "description": "Plain-text subject shown exactly in the approval."},
        "body": {"type": "string", "minLength": 1, "maxLength": 12000,
                 "description": "Plain-text message body shown exactly in the approval."},
    })

    def __init__(self, grant: dict[str, Any]):
        self.grant = dict(grant)
        label = self.grant.get("account_label") or "the selected Outlook account"
        self.description = (
            f"Prepare one new plain-text email from {label} to 1–5 recipients. "
            "Hutch displays the exact account, recipients, subject, and body for a fresh owner approval before sending, "
            "including in automatic mode. This cannot reply, forward, attach files, use CC/BCC, or send without approval. "
            "Microsoft acceptance does not prove delivery; an uncertain result must be checked in Sent Items and is never retried automatically."
        )

    def effect(self, args: dict, ctx: ToolContext) -> str:
        return "web"

    def recorded_arguments(self, args: dict, ctx: ToolContext) -> dict:
        return {**args, "account_id": self.grant["account_id"],
                "account_label": self.grant.get("account_label", "")}

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.dry_run:
            return ToolResult(True,
                              "[rehearsal] would show the exact email for approval and submit at most one send request. Nothing was changed.",
                              {"simulated": True})
        grant_reader = getattr(ctx.store, "outlook_mail_send_grant", None)
        current = grant_reader(ctx.bot.id) if callable(grant_reader) else None
        if not current or current.get("account_id") != self.grant.get("account_id"):
            return ToolResult(False, "Outlook email-sending access was removed or changed; ask the owner to review this Bot's Connections grant.")

        try:
            message = OutlookMailSendBook.prepare_message(args.get("to"), args.get("subject"), args.get("body"))
        except OutlookCalendarError as exc:
            return ToolResult(False, str(exc))
        label = self.grant.get("account_label") or "the selected Outlook account"
        detail = {
            "account_id": current["account_id"],
            "account": label,
            "recipients": list(message["to"]),
            "subject": message["subject"],
            "body": message["body"],
            "effect": "send one plain-text email; no attachments, CC, BCC, reply, or forward",
            "delivery": "Microsoft acceptance is not proof of delivery; Hutch will not retry an uncertain result",
        }
        try:
            ctx.gate.decide(self.name, f"Send email to {', '.join(message['to'])[:300]}",
                            detail, outward=True, ask_in_auto=True)
        except DeniedError as exc:
            return ToolResult(False, f"email was not approved; nothing was sent ({exc})")

        # An owner may revoke the Bot grant while the approval card is open.
        current = grant_reader(ctx.bot.id) if callable(grant_reader) else None
        if not current or current.get("account_id") != self.grant.get("account_id"):
            return ToolResult(False, "Outlook email-sending access changed while approval was pending; no email was sent.")
        try:
            book = OutlookMailSendBook(ctx.config.state_dir,
                                       os.environ.get("HUTCH_OUTLOOK_OAUTH_CLIENT_ID", ""))
            result = book.send_message(current["account_id"], message["to"], message["subject"], message["body"],
                                       before_write=ctx.begin_effect)
        except OutlookMailSendOutcomeUnknown as exc:
            from ..runtime.base import RunAborted
            raise RunAborted("outcome_unknown", str(exc)) from exc
        except OutlookCalendarError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True,
                          "Microsoft accepted one email request. Delivery is not confirmed; check Outlook Sent Items before considering any retry.",
                          {**result, "account_id": current["account_id"], "requires_reconciliation": True})
