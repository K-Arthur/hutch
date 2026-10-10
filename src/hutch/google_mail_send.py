"""Separate, send-only Gmail authorization and one-shot plain-text delivery."""

from __future__ import annotations

import base64
import json
import re
from email import policy
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlsplit

import httpx

from .google_calendar import (
    GoogleCalendarBook,
    GoogleCalendarError,
    GoogleCalendarOutcomeUnknown,
    SecretToolStore,
    _atomic_private_json,
)

GOOGLE_MAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_MAIL_SEND_CALLBACK_PATH = "/api/v1/connections/google-mail-send/callback"
GOOGLE_MAIL_SEND_API = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_MAIL_SEND_ACCOUNT_RE = re.compile(r"^gmail_send_[0-9a-f]{24}$")
GOOGLE_MAIL_ADDRESS_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


class GoogleMailSendOutcomeUnknown(GoogleCalendarOutcomeUnknown):
    """Google may have accepted a message without returning a verifiable receipt."""


class GoogleMailSendSecretToolStore(SecretToolStore):
    service = "hutch.google-mail-send"
    feature_name = "Gmail sending"
    account_pattern = GOOGLE_MAIL_SEND_ACCOUNT_RE
    probe_account = "gmail_send_000000000000000000000000"


class GoogleMailSendBook(GoogleCalendarBook):
    """Google OAuth account with only ``gmail.send`` and no mailbox-read access."""

    feature_name = "Gmail sending"
    client_id_env = "HUTCH_GOOGLE_OAUTH_CLIENT_ID"
    storage_name = "google-mail-send"
    account_prefix = "gmail_send_"
    account_pattern = GOOGLE_MAIL_SEND_ACCOUNT_RE
    callback_path = GOOGLE_MAIL_SEND_CALLBACK_PATH
    oauth_scopes = (GOOGLE_MAIL_SEND_SCOPE,)
    required_scopes = (GOOGLE_MAIL_SEND_SCOPE,)
    api_host = "gmail.googleapis.com"
    api_base = GOOGLE_MAIL_SEND_API
    secret_store_type = GoogleMailSendSecretToolStore

    @staticmethod
    def _clean_address(address: str) -> str:
        if not isinstance(address, str):
            raise GoogleCalendarError("Enter the email address to send from")
        address = address.strip()
        if (len(address) > 254 or not GOOGLE_MAIL_ADDRESS_RE.fullmatch(address) or
                any(ord(char) < 33 or ord(char) > 126 for char in address)):
            raise GoogleCalendarError("Enter one valid sender email address")
        local, _domain = address.rsplit("@", 1)
        if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
            raise GoogleCalendarError("Enter one valid sender email address")
        return address

    def start(self, label: str, redirect_uri: str, from_address: str):
        sender = self._clean_address(from_address)
        started = super().start(label, redirect_uri)
        try:
            path = self.pending_dir / f"{started.state}.json"
            with self._lock_context():
                try:
                    pending = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raise GoogleCalendarError("This Gmail sending sign-in request could not be prepared; start again") from None
                if not isinstance(pending, dict):
                    raise GoogleCalendarError("This Gmail sending sign-in request could not be prepared; start again")
                pending["from_address"] = sender
                _atomic_private_json(path, pending)
        except Exception as exc:
            try:
                self.cancel(started.state)
            except GoogleCalendarError:
                pass
            if isinstance(exc, GoogleCalendarError):
                raise
            raise GoogleCalendarError(
                "This Gmail sending sign-in request could not be prepared; start again") from None
        return started

    def _account_metadata(self, pending: dict[str, Any]) -> dict[str, str]:
        return {"from_address": self._clean_address(pending.get("from_address"))}

    def _granted_scopes_allowed(self, requested: set[str], granted: set[str]) -> bool:
        if not super()._granted_scopes_allowed(requested, granted):
            return False
        gmail_scopes = {scope for scope in granted
                        if scope.startswith("https://www.googleapis.com/auth/gmail")}
        return gmail_scopes == {GOOGLE_MAIL_SEND_SCOPE}

    @staticmethod
    def prepare_message(from_address: str, recipients: list[str], subject: str, body: str) -> dict[str, Any]:
        sender = GoogleMailSendBook._clean_address(from_address)
        if not isinstance(recipients, list) or not 1 <= len(recipients) <= 5:
            raise GoogleCalendarError("Choose between 1 and 5 email recipients")
        addresses: list[str] = []
        for address in recipients:
            clean = GoogleMailSendBook._clean_address(address)
            if clean.casefold() in {item.casefold() for item in addresses}:
                raise GoogleCalendarError("Remove duplicate email recipients")
            addresses.append(clean)
        if (not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 180 or
                any(ord(char) < 32 or ord(char) == 127 for char in subject)):
            raise GoogleCalendarError("Email subject must be 1–180 plain-text characters")
        subject = subject.strip()
        try:
            subject.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise GoogleCalendarError("Email subject must contain valid Unicode text") from None
        if not isinstance(body, str) or not 1 <= len(body) <= 12000:
            raise GoogleCalendarError("Email body must be 1–12,000 plain-text characters")
        if any((ord(char) < 32 and char not in "\r\n\t") or ord(char) == 127 for char in body):
            raise GoogleCalendarError("Email body contains unsupported control characters")
        try:
            body.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise GoogleCalendarError("Email body must contain valid Unicode text") from None
        return {"from": sender, "to": addresses, "subject": subject, "body": body}

    def send_message(self, account_id: str, recipients: list[str], subject: str, body: str,
                     *, before_write) -> dict[str, Any]:
        """Send one plain-text message; ambiguous outcomes are never retried."""
        self._require_client_id()
        account = self._account(account_id)
        account_scopes = account.get("scopes", [])
        gmail_scopes = ({scope for scope in account_scopes if isinstance(scope, str) and
                         scope.startswith("https://www.googleapis.com/auth/gmail")}
                        if isinstance(account_scopes, list) else set())
        if gmail_scopes != {GOOGLE_MAIL_SEND_SCOPE}:
            raise GoogleCalendarError("This Gmail account has no gmail.send grant; connect a separate sending account")
        message = self.prepare_message(account.get("from_address"), recipients, subject, body)

        # Refresh credentials before the durable intent. Once before_write runs,
        # all transport and malformed-success outcomes are held for owner review.
        token = self.access_token(account_id)
        if before_write is not None:
            blocked = before_write()
            if blocked:
                raise GoogleCalendarError(str(blocked))

        mime = EmailMessage(policy=policy.SMTP)
        mime["From"] = message["from"]
        mime["To"] = ", ".join(message["to"])
        mime["Subject"] = message["subject"]
        mime.set_content(message["body"])
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii").rstrip("=")
        url = f"{GOOGLE_MAIL_SEND_API}/users/me/messages/send"
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != self.api_host or parts.username or parts.password:
            raise GoogleCalendarError("Refusing a Gmail send destination outside Google's verified API host")
        try:
            with self._http() as client:
                response = client.post(url, params={"fields": "id,threadId"}, json={"raw": raw}, headers={
                    "Authorization": f"Bearer {token}", "Accept": "application/json",
                })
        except httpx.HTTPError:
            raise GoogleMailSendOutcomeUnknown(
                "Google may have accepted this email, but Hutch did not receive a response. Check Gmail Sent before retrying.") from None

        if response.request.url.scheme != "https" or response.request.url.host != self.api_host:
            raise GoogleMailSendOutcomeUnknown(
                "Google may have accepted this email, but the response destination changed. Check Gmail Sent before retrying.")
        if (300 <= response.status_code < 400 or response.status_code == 408 or
                response.status_code >= 500):
            raise GoogleMailSendOutcomeUnknown(
                f"Google may have accepted this email (HTTP {response.status_code}). Check Gmail Sent before retrying.")
        if not 200 <= response.status_code < 300:
            if response.status_code in (401, 403):
                raise GoogleCalendarError("Google rejected the Gmail send; reconnect the sending account and check its permissions")
            if response.status_code == 429:
                raise GoogleCalendarError("Google rate-limited the Gmail send; nothing was accepted, wait and try again")
            raise GoogleCalendarError(f"Google did not accept the Gmail send (HTTP {response.status_code})")
        try:
            payload = response.json()
        except ValueError:
            raise GoogleMailSendOutcomeUnknown(
                "Google may have accepted this email but returned no receipt. Check Gmail Sent before retrying.") from None
        message_id = payload.get("id") if isinstance(payload, dict) else None
        thread_id = payload.get("threadId") if isinstance(payload, dict) else None
        if (not isinstance(message_id, str) or not 1 <= len(message_id) <= 256 or
                (thread_id is not None and (not isinstance(thread_id, str) or len(thread_id) > 256))):
            raise GoogleMailSendOutcomeUnknown(
                "Google may have accepted this email but returned no verifiable receipt. Check Gmail Sent before retrying.")
        return {"accepted": True, "delivery_verified": False, "message_id": message_id,
                "thread_id": thread_id or ""}


__all__ = ["GoogleMailSendBook", "GoogleMailSendOutcomeUnknown", "GoogleMailSendSecretToolStore",
           "GOOGLE_MAIL_SEND_SCOPE", "GOOGLE_MAIL_SEND_CALLBACK_PATH"]
