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


__all__ = ["OutlookMailBook", "OutlookMailSecretToolStore", "MAIL_SCOPE", "MAIL_CALLBACK_PATH"]
