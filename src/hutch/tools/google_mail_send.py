"""Owner-approved, one-shot Gmail sending using a separate send-only grant."""

from __future__ import annotations

import os
from typing import Any

from ..approvals import DeniedError
from ..google_calendar import GoogleCalendarError
from ..google_mail_send import GoogleMailSendBook, GoogleMailSendOutcomeUnknown
from .base import Tool, ToolContext, ToolResult, _schema


class GoogleMailSendTool(Tool):
    name = "google_mail_send"
    parameters = _schema(["to", "subject", "body"], {
        "to": {"type": "array", "minItems": 1, "maxItems": 5,
               "items": {"type": "string", "maxLength": 254},
               "description": "One to five plain email addresses shown exactly in the approval."},
        "subject": {"type": "string", "minLength": 1, "maxLength": 180,
                    "description": "Plain-text subject shown exactly in the approval."},
        "body": {"type": "string", "minLength": 1, "maxLength": 12000,
                 "description": "Plain-text message body shown exactly in the approval."},
    })

    def __init__(self, grant: dict[str, Any]):
        self.grant = dict(grant)
        label = self.grant.get("account_label") or "the selected Gmail account"
        self.description = (
            f"Prepare one new plain-text email from {label} to 1–5 recipients. "
            "Hutch displays the exact sender, account, recipients, subject and body for fresh owner approval before sending, "
            "including in automatic mode. No attachments, CC, BCC, replies or forwards. "
            "An uncertain result must be checked in Gmail Sent and is never retried automatically."
        )

    def effect(self, args: dict, ctx: ToolContext) -> str:
        return "web"

    def recorded_arguments(self, args: dict, ctx: ToolContext) -> dict:
        book = GoogleMailSendBook(ctx.config.state_dir,
                                  os.environ.get("HUTCH_GOOGLE_OAUTH_CLIENT_ID", ""))
        account = book._account(self.grant["account_id"])
        return {**args, "account_id": self.grant["account_id"],
                "account_label": self.grant.get("account_label", ""),
                "from_address": account.get("from_address", "")}

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.dry_run:
            return ToolResult(True,
                              "[rehearsal] would show the exact Gmail message for approval and submit at most one send request. Nothing was changed.",
                              {"simulated": True})
        grant_reader = getattr(ctx.store, "google_mail_send_grant", None)
        current = grant_reader(ctx.bot.id) if callable(grant_reader) else None
        if not current or current.get("account_id") != self.grant.get("account_id"):
            return ToolResult(False, "Gmail sending access was removed or changed; ask the owner to review this Bot's Connections grant.")

        try:
            book = GoogleMailSendBook(ctx.config.state_dir,
                                      os.environ.get("HUTCH_GOOGLE_OAUTH_CLIENT_ID", ""))
            account = book._account(current["account_id"])
            if account.get("status") != "connected":
                raise GoogleCalendarError("This Gmail sending account is not connected; reconnect it from Connections")
            message = book.prepare_message(account.get("from_address"), args.get("to"),
                                           args.get("subject"), args.get("body"))
        except GoogleCalendarError as exc:
            return ToolResult(False, str(exc))

        label = current.get("account_label") or "the selected Gmail account"
        grant_snapshot = dict(current)
        detail = {
            "account_id": current["account_id"],
            "account": label,
            "from": message["from"],
            "recipients": list(message["to"]),
            "subject": message["subject"],
            "body": message["body"],
            "effect": "send one plain-text email; no attachments, CC, BCC, reply, or forward",
            "delivery": "Google acceptance is not proof of delivery; Hutch will not retry an uncertain result",
        }
        try:
            ctx.gate.decide(self.name, f"Send email to {', '.join(message['to'])[:300]}",
                            detail, outward=True, ask_in_auto=True)
        except DeniedError as exc:
            return ToolResult(False, f"email was not approved; nothing was sent ({exc})")

        # The owner can revoke while the exact request is open for approval.
        current = grant_reader(ctx.bot.id) if callable(grant_reader) else None
        if not current or any(current.get(key) != grant_snapshot.get(key)
                              for key in ("account_id", "granted_at", "account_label")):
            return ToolResult(False, "Gmail sending access changed while approval was pending; no email was sent.")
        try:
            def before_write():
                latest = grant_reader(ctx.bot.id) if callable(grant_reader) else None
                if not latest or any(latest.get(key) != grant_snapshot.get(key)
                                     for key in ("account_id", "granted_at", "account_label")):
                    return "Gmail sending access changed before the send request; nothing was sent"
                current_account = book._account(latest["account_id"])
                if current_account.get("from_address") != message["from"]:
                    return "The Gmail sender address changed after approval; nothing was sent"
                return ctx.begin_effect()

            result = book.send_message(current["account_id"], message["to"], message["subject"], message["body"],
                                       before_write=before_write)
        except GoogleMailSendOutcomeUnknown as exc:
            from ..runtime.base import RunAborted
            raise RunAborted("outcome_unknown", str(exc)) from exc
        except GoogleCalendarError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True,
                          "Google accepted one email request. Delivery is not confirmed; check Gmail Sent before considering any retry.",
                          {**result, "account_id": current["account_id"], "requires_reconciliation": True})
