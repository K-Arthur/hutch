"""Local, read-only Microsoft Outlook Mail connection.

Mail uses a separate OAuth store and callback from Outlook Calendar. The only
provider permission requested is delegated ``Mail.Read``; Hutch never sends,
changes, deletes, forwards, or downloads attachments. Results are bounded and
must be treated as untrusted user content by the calling Bot.
"""

from __future__ import annotations

import re
from typing import Any

from .outlook_calendar import (
    GRAPH_API,
    OutlookCalendarBook,
    OutlookCalendarError,
    SecretToolStore,
)

MAIL_SCOPE = "Mail.Read"
MAIL_CALLBACK_PATH = "/api/v1/connections/outlook-mail/callback"
MAIL_ACCOUNT_RE = re.compile(r"^msmail_[0-9a-f]{24}$")
MAIL_SEND_SCOPE = "Mail.Send"
MAIL_SEND_CALLBACK_PATH = "/api/v1/connections/outlook-mail-send/callback"
MAIL_SEND_ACCOUNT_RE = re.compile(r"^mssend_[0-9a-f]{24}$")
MAIL_ADDRESS_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


class OutlookMailSecretToolStore(SecretToolStore):
    service = "hutch.outlook-mail"
    feature = "Outlook Mail"
    account_pattern = MAIL_ACCOUNT_RE
    probe_account = "msmail_000000000000000000000000"


class OutlookMailBook(OutlookCalendarBook):
    """Microsoft delegated OAuth and bounded message lookup for one local state directory."""

    feature = "Outlook Mail"
    storage_name = "outlook-mail"
    account_prefix = "msmail_"
    account_pattern = MAIL_ACCOUNT_RE
    callback_path = MAIL_CALLBACK_PATH
    oauth_scopes = (MAIL_SCOPE, "offline_access")
    required_scopes = (MAIL_SCOPE,)
    secret_store_type = OutlookMailSecretToolStore

    def list_messages(self, account_id: str, query: str, *, limit: int = 10) -> list[dict[str, str]]:
        """Search messages using Microsoft Graph's bounded, plain-text preview response."""
        self._require_client_id()
        account = self._account(account_id)
        if MAIL_SCOPE not in account.get("scopes", []):
            raise OutlookCalendarError("This Outlook Mail account has no Mail.Read grant; reconnect it from Connections")
        if not isinstance(query, str):
            raise OutlookCalendarError("Outlook Mail search must be plain text")
        query = " ".join(query.split())
        if not 2 <= len(query) <= 160 or any(ord(char) < 32 or ord(char) == 127 for char in query):
            raise OutlookCalendarError("Enter an Outlook Mail search from 2 to 160 plain-text characters")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
            raise OutlookCalendarError("Outlook Mail result limit must be between 1 and 10")

        # Keep the search term inside one quoted AQS expression. The request is
        # sent via httpx query parameters and cannot change the Graph host/path.
        escaped = query.replace("\\", "\\\\").replace('"', '\\"')
        url = f"{GRAPH_API}/me/messages"
        self._validate_graph_url(url, "/v1.0/me/messages")
        payload = self._get(url, account_id, {
            "$search": f'"{escaped}"',
            "$top": str(limit),
            "$select": "subject,from,receivedDateTime,bodyPreview",
        }, "mail search", prefer='outlook.body-content-type="text"')
        values = payload.get("value", [])
        if not isinstance(values, list):
            raise OutlookCalendarError("Microsoft returned an invalid Outlook Mail result list")

        messages: list[dict[str, str]] = []
        for item in values[:limit]:
            if not isinstance(item, dict):
                continue
            sender = item.get("from") if isinstance(item.get("from"), dict) else {}
            email = sender.get("emailAddress") if isinstance(sender.get("emailAddress"), dict) else {}
            messages.append({
                "subject": str(item.get("subject") or "(no subject)")[:300],
                "from": str(email.get("name") or email.get("address") or "(unknown sender)")[:200],
                "received_at": str(item.get("receivedDateTime") or "")[:64],
                "preview": str(item.get("bodyPreview") or "")[:1200],
            })
        return messages


class OutlookMailSendOutcomeUnknown(OutlookCalendarError):
    """Graph may have accepted a send, but Hutch did not receive a definitive response."""


class OutlookMailSendSecretToolStore(OutlookMailSecretToolStore):
    service = "hutch.outlook-mail-send"
    feature = "Outlook Mail sending"
    account_pattern = MAIL_SEND_ACCOUNT_RE
    probe_account = "mssend_000000000000000000000000"


class OutlookMailSendBook(OutlookCalendarBook):
    """Separate, send-only Mail.Send account with exact, single-attempt Graph writes."""

    feature = "Outlook Mail sending"
    storage_name = "outlook-mail-send"
    account_prefix = "mssend_"
    account_pattern = MAIL_SEND_ACCOUNT_RE
    callback_path = MAIL_SEND_CALLBACK_PATH
    oauth_scopes = (MAIL_SEND_SCOPE, "offline_access")
    required_scopes = (MAIL_SEND_SCOPE,)
    secret_store_type = OutlookMailSendSecretToolStore
    error_type = OutlookCalendarError

    @staticmethod
    def prepare_message(recipients: list[str], subject: str, body: str) -> dict[str, Any]:
        if not isinstance(recipients, list) or not 1 <= len(recipients) <= 5:
            raise OutlookCalendarError("Choose between 1 and 5 email recipients")
        addresses: list[str] = []
        for address in recipients:
            if (not isinstance(address, str) or len(address) > 254 or
                    not MAIL_ADDRESS_RE.fullmatch(address)):
                raise OutlookCalendarError("Enter each recipient as one plain email address")
            local, _domain = address.rsplit("@", 1)
            if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
                raise OutlookCalendarError("Enter each recipient as one plain email address")
            if address.casefold() in {item.casefold() for item in addresses}:
                raise OutlookCalendarError("Remove duplicate email recipients")
            addresses.append(address)
        if (not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 180 or
                any(ord(char) < 32 or ord(char) == 127 for char in subject)):
            raise OutlookCalendarError("Email subject must be 1–180 plain-text characters")
        subject = subject.strip()
        if not isinstance(body, str) or not 1 <= len(body) <= 12000:
            raise OutlookCalendarError("Email body must be 1–12,000 plain-text characters")
        if any((ord(char) < 32 and char not in "\r\n\t") or ord(char) == 127 for char in body):
            raise OutlookCalendarError("Email body contains unsupported control characters")
        try:
            body.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise OutlookCalendarError("Email body must contain valid Unicode text") from None
        return {"to": addresses, "subject": subject, "body": body}

    def send_message(self, account_id: str, recipients: list[str], subject: str, body: str,
                     *, before_write) -> dict[str, bool]:
        """Send once. A timeout or server error is outcome-unknown and is never retried."""
        self._require_client_id()
        account = self._account(account_id)
        if MAIL_SEND_SCOPE not in account.get("scopes", []):
            raise OutlookCalendarError("This Outlook account has no Mail.Send grant; connect a separate sending account")
        message = self.prepare_message(recipients, subject, body)
        url = f"{GRAPH_API}/me/sendMail"
        self._validate_graph_url(url, "/v1.0/me/sendMail")

        # Resolve/refresh the delegated credential before the durable effect
        # intent. After begin_effect runs, every ambiguous response is held for
        # human reconciliation rather than automatically sent again.
        token = self.access_token(account_id)
        if before_write is not None:
            blocked = before_write()
            if blocked:
                raise OutlookCalendarError(str(blocked))
        payload = {
            "message": {
                "subject": message["subject"],
                "body": {"contentType": "Text", "content": message["body"]},
                "toRecipients": [{"emailAddress": {"address": address}} for address in message["to"]],
            },
            "saveToSentItems": True,
        }
        try:
            with self._http() as client:
                response = client.post(url, json=payload, headers={
                    "Authorization": f"Bearer {token}", "Accept": "application/json",
                })
        except httpx.HTTPError:
            raise OutlookMailSendOutcomeUnknown(
                "Microsoft may have accepted this email, but Hutch did not receive a response. Check Sent Items before retrying.") from None

        if response.request.url.host != "graph.microsoft.com" or response.request.url.scheme != "https":
            raise OutlookMailSendOutcomeUnknown(
                "Microsoft may have accepted this email, but the response came from an unexpected destination. Check Sent Items.")
        if response.status_code == 202:
            return {"accepted": True, "delivery_verified": False}
        if response.status_code >= 500 or 300 <= response.status_code < 400 or 200 <= response.status_code < 300:
            raise OutlookMailSendOutcomeUnknown(
                f"Microsoft may have accepted this email (HTTP {response.status_code}); check Sent Items before retrying.")
        self._json(response, "email send")
        raise OutlookCalendarError("Microsoft did not accept this email; review the address and account permission before trying again")


__all__ = ["OutlookMailBook", "OutlookMailSendBook", "OutlookMailSendOutcomeUnknown",
           "OutlookMailSecretToolStore", "OutlookMailSendSecretToolStore", "MAIL_SCOPE", "MAIL_CALLBACK_PATH",
           "MAIL_SEND_SCOPE", "MAIL_SEND_CALLBACK_PATH"]
