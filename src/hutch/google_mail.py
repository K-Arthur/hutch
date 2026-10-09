"""Local, read-only Gmail search using a separately granted Google OAuth token."""

from __future__ import annotations

import os
import re
from typing import Any

from .google_calendar import GoogleCalendarBook, GoogleCalendarError, SecretToolStore

GOOGLE_MAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_MAIL_CALLBACK_PATH = "/api/v1/connections/google-mail/callback"
GOOGLE_MAIL_API = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_MAIL_ACCOUNT_RE = re.compile(r"^gmail_[0-9a-f]{24}$")


class GoogleMailSecretToolStore(SecretToolStore):
    service = "hutch.google-mail"
    feature_name = "Gmail"
    account_pattern = GOOGLE_MAIL_ACCOUNT_RE
    probe_account = "gmail_000000000000000000000000"


class GoogleMailBook(GoogleCalendarBook):
    """Separate local Gmail credentials and bounded metadata/snippet search."""

    feature_name = "Gmail"
    client_id_env = "HUTCH_GOOGLE_OAUTH_CLIENT_ID"
    storage_name = "google-mail"
    account_prefix = "gmail_"
    account_pattern = GOOGLE_MAIL_ACCOUNT_RE
    callback_path = GOOGLE_MAIL_CALLBACK_PATH
    oauth_scopes = (GOOGLE_MAIL_SCOPE,)
    required_scopes = (GOOGLE_MAIL_SCOPE,)
    api_host = "gmail.googleapis.com"
    api_base = GOOGLE_MAIL_API
    secret_store_type = GoogleMailSecretToolStore

    def list_messages(self, account_id: str, query: str, *, limit: int = 10) -> list[dict[str, str]]:
        """Return bounded sender/subject/date/snippet previews from one connected account."""
        if not isinstance(query, str):
            raise GoogleCalendarError("Gmail search must be plain text")
        if any(ord(char) < 32 or ord(char) == 127 for char in query):
            raise GoogleCalendarError("Enter a Gmail search from 2 to 160 plain-text characters")
        query = " ".join(query.split())
        if not 2 <= len(query) <= 160:
            raise GoogleCalendarError("Enter a Gmail search from 2 to 160 plain-text characters")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
            raise GoogleCalendarError("Gmail result limit must be between 1 and 10")
        self._require_client_id()
        account = self._account(account_id)
        if GOOGLE_MAIL_SCOPE not in account.get("scopes", []):
            raise GoogleCalendarError("This Gmail account has no gmail.readonly grant; reconnect it from Connections")

        list_url = f"{GOOGLE_MAIL_API}/users/me/messages"
        payload = self._get(list_url, account_id,
                            {"q": query, "maxResults": str(limit), "fields": "messages(id),nextPageToken"},
                            "Gmail message search")
        values = payload.get("messages", [])
        if not isinstance(values, list):
            raise GoogleCalendarError("Google returned an invalid Gmail result list")

        messages: list[dict[str, str]] = []
        for item in values[:limit]:
            if not isinstance(item, dict):
                continue
            message_id = item.get("id")
            if not isinstance(message_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", message_id):
                continue
            detail = self._get(f"{list_url}/{message_id}", account_id, {
                "format": "metadata",
                "metadataHeaders": ["From", "Subject", "Date"],
                "fields": "id,snippet,payload/headers(name,value)",
            }, "Gmail message preview")
            body = detail.get("payload") if isinstance(detail.get("payload"), dict) else {}
            headers = body.get("headers", [])
            if not isinstance(headers, list):
                headers = []
            selected: dict[str, str] = {}
            for header in headers:
                if not isinstance(header, dict):
                    continue
                name = str(header.get("name") or "").strip().casefold()
                if name not in {"from", "subject", "date"} or name in selected:
                    continue
                selected[name] = self._clean_text(header.get("value"), 300 if name == "subject" else 200)
            messages.append({
                "from": selected.get("from") or "(unknown sender)",
                "subject": selected.get("subject") or "(no subject)",
                "received_at": selected.get("date", "")[:64],
                "preview": self._clean_text(detail.get("snippet"), 1200),
            })
        return messages

    @staticmethod
    def _clean_text(value: Any, limit: int) -> str:
        text = str(value or "")
        text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)
        return " ".join(text.split())[:limit]


def validate_local_gmail_bot(bot: Any) -> None:
    """Require every route that could receive mailbox text to be a loopback model route."""
    mode = getattr(getattr(bot, "inference_mode", None), "value", "")
    runtime = getattr(getattr(bot, "runtime", None), "value", "")
    if mode != "local":
        raise GoogleCalendarError("Gmail access requires Local inference; Hybrid and hosted routes could send mailbox previews to a provider")
    if runtime != "builtin":
        raise GoogleCalendarError("Gmail access requires Hutch's built-in runtime so the local-only route policy is enforced")

    from .providers.registry import parse_spec, validate_offline_route

    primary_provider = parse_spec(str(getattr(bot, "model", "")))[0]
    routes = [str(getattr(bot, "model", ""))]
    routes.extend(str(route) for route in getattr(bot, "fallbacks", []) or [])
    escalation = getattr(bot, "escalation", None)
    if escalation:
        routes.extend(str(route) for route in escalation.to or [])
    if not routes[0].partition("/")[2]:
        raise GoogleCalendarError("Choose a configured loopback Local model before granting Gmail access")
    for spec in routes:
        provider, _ = parse_spec(spec)
        if provider == "ollama" and provider != primary_provider:
            endpoint = None
        elif provider == primary_provider:
            endpoint = getattr(bot, "base_url", None)
        else:
            endpoint = None
        if provider == "ollama" and not endpoint:
            endpoint = os.environ.get("OLLAMA_HOST") or None
        try:
            validate_offline_route(spec, endpoint)
        except ValueError:
            raise GoogleCalendarError(
                "Gmail previews require loopback-only Local model endpoints with no hosted fallback; "
                "remove the remote route or fallback before granting access"
            ) from None
