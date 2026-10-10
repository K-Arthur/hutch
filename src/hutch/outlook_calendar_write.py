"""Separately consented, single-event Outlook Calendar writes.

Microsoft's delegated Calendars.ReadWrite grant can create, change, and delete
events across the signed-in user's calendars. Hutch keeps that credential in a
separate Secret Service namespace, only gives a Bot a selected-calendar create
capability, requires exact approval for every event, and exposes no edit/delete
operation.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote

import httpx

from .outlook_calendar import OutlookCalendarBook, OutlookCalendarError, SecretToolStore

CALENDAR_WRITE_SCOPE = "Calendars.ReadWrite"
CALENDAR_WRITE_CALLBACK_PATH = "/api/v1/connections/outlook-calendar-write/callback"
CALENDAR_WRITE_ACCOUNT_RE = re.compile(r"^mscalw_[0-9a-f]{24}$")


class OutlookCalendarWriteSecretToolStore(SecretToolStore):
    service = "hutch.outlook-calendar-write"
    feature = "Outlook Calendar event creation"
    account_pattern = CALENDAR_WRITE_ACCOUNT_RE
    probe_account = "mscalw_000000000000000000000000"


class OutlookCalendarWriteOutcomeUnknown(OutlookCalendarError):
    """Microsoft may have created an event, but Hutch could not verify it."""


class OutlookCalendarWriteBook(OutlookCalendarBook):
    """Independent OAuth identity and exact, one-shot event creation client."""

    feature = "Outlook Calendar event creation"
    storage_name = "outlook-calendar-write"
    account_prefix = "mscalw_"
    account_pattern = CALENDAR_WRITE_ACCOUNT_RE
    callback_path = CALENDAR_WRITE_CALLBACK_PATH
    oauth_scopes = (CALENDAR_WRITE_SCOPE, "offline_access")
    required_scopes = (CALENDAR_WRITE_SCOPE,)
    secret_store_type = OutlookCalendarWriteSecretToolStore
    error_type = OutlookCalendarError

    @classmethod
    def prepare_event(cls, *, summary: str, start: str, end: str,
                      description: str = "", location: str = "") -> dict[str, str]:
        if (not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 180 or
                any(ord(char) < 32 or ord(char) == 127 for char in summary)):
            raise OutlookCalendarError("Event title must be 1–180 plain-text characters")
        if not isinstance(description, str) or len(description) > 2000:
            raise OutlookCalendarError("Event description must be at most 2,000 characters")
        if any((ord(char) < 32 and char not in "\r\n\t") or ord(char) == 127 for char in description):
            raise OutlookCalendarError("Event description contains unsupported control characters")
        if not isinstance(location, str) or len(location) > 300:
            raise OutlookCalendarError("Event location must be at most 300 characters")
        if any(ord(char) < 32 or ord(char) == 127 for char in location):
            raise OutlookCalendarError("Event location contains unsupported control characters")
        start_dt, end_dt = cls._time(start, "start"), cls._time(end, "end")
        if start_dt >= end_dt:
            raise OutlookCalendarError("Calendar event end after start is required")
        if (end_dt - start_dt).total_seconds() > 366 * 24 * 3600:
            raise OutlookCalendarError("Calendar events cannot be longer than 366 days")
        return {
            "summary": summary.strip(),
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "description": description,
            "location": location,
        }

    @staticmethod
    def _verified_utc(value: Any, label: str) -> datetime:
        if not isinstance(value, dict):
            raise OutlookCalendarError(f"Microsoft returned no verifiable event {label}")
        raw, zone = value.get("dateTime"), value.get("timeZone")
        if not isinstance(raw, str) or len(raw) > 80:
            raise OutlookCalendarError(f"Microsoft returned an invalid event {label}")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                if str(zone or "").casefold() != "utc":
                    raise ValueError
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            raise OutlookCalendarError(f"Microsoft returned an invalid event {label}") from None

    def create_event(self, account_id: str, calendar_id: str, *, summary: str, start: str, end: str,
                     description: str = "", location: str = "",
                     before_write: Callable[[], str | None] | None = None) -> dict[str, str]:
        """Create once, then read back and verify exact event values; never retry an uncertain write."""
        self._require_client_id()
        account = self._account(account_id)
        if CALENDAR_WRITE_SCOPE not in account.get("scopes", []):
            raise OutlookCalendarError(
                "This Outlook account has no Calendars.ReadWrite grant; connect a separate event-creation account")
        if (not isinstance(calendar_id, str) or not 1 <= len(calendar_id) <= 1024 or
                any(ord(char) < 32 for char in calendar_id)):
            raise OutlookCalendarError("Choose a valid calendar from the connected Microsoft account")
        event = self.prepare_event(summary=summary, start=start, end=end,
                                   description=description, location=location)
        start_dt = self._time(event["start"], "start")
        end_dt = self._time(event["end"], "end")
        selected = next((row for row in self.list_calendars(account_id) if row["id"] == calendar_id), None)
        if selected is None:
            raise OutlookCalendarError("The selected Outlook calendar is no longer available; review this Bot's grant")

        # Refresh the token and validate destination before recording the effect
        # intent. After it is recorded, transport ambiguity must remain unknown.
        token = self.access_token(account_id)
        path = f"/v1.0/me/calendars/{quote(calendar_id, safe='')}/events"
        url = f"https://graph.microsoft.com{path}"
        payload: dict[str, Any] = {
            "subject": event["summary"],
            "start": {"dateTime": start_dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
                      "timeZone": "UTC"},
            "end": {"dateTime": end_dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
                    "timeZone": "UTC"},
            "attendees": [],
        }
        if event["description"]:
            payload["body"] = {"contentType": "Text", "content": event["description"]}
        if event["location"]:
            payload["location"] = {"displayName": event["location"]}
        if before_write is not None:
            refusal = before_write()
            if refusal:
                raise OutlookCalendarError(f"{refusal}; the event was not sent")

        try:
            with self._http() as client:
                response = client.post(url, json=payload, headers={
                    "Authorization": f"Bearer {token}", "Accept": "application/json",
                })
        except httpx.HTTPError:
            raise OutlookCalendarWriteOutcomeUnknown(
                "Microsoft may have created this event, but Hutch did not receive a response. Check the calendar before retrying.") from None
        if response.request.url.host != "graph.microsoft.com" or response.request.url.scheme != "https":
            raise OutlookCalendarWriteOutcomeUnknown(
                "Microsoft may have created this event, but the response came from an unexpected destination. Check the calendar.")
        if response.status_code >= 500 or 300 <= response.status_code < 400 or 200 <= response.status_code < 300:
            if response.status_code < 400:
                try:
                    created = response.json()
                except ValueError:
                    created = None
                event_id = created.get("id") if isinstance(created, dict) else None
                if isinstance(event_id, str) and 1 <= len(event_id) <= 1024:
                    pass
                else:
                    raise OutlookCalendarWriteOutcomeUnknown(
                        "Microsoft may have created the event but returned no verifiable ID; check the calendar before retrying")
            else:
                raise OutlookCalendarWriteOutcomeUnknown(
                    f"Microsoft may have created the event (HTTP {response.status_code}); check the calendar before retrying")
        else:
            self._json(response, "event creation")
            raise OutlookCalendarError("Microsoft did not accept the event; review the selected calendar and try again")

        verify_url = f"https://graph.microsoft.com{path}/{quote(event_id, safe='')}"
        try:
            verified = self._get(verify_url, account_id,
                {"$select": "id,subject,start,end,location,attendees,body"}, "created event verification")
            actual_start = self._verified_utc(verified.get("start"), "start")
            actual_end = self._verified_utc(verified.get("end"), "end")
            actual_location = verified.get("location") if isinstance(verified.get("location"), dict) else {}
            attendees = verified.get("attendees", [])
            body = verified.get("body")
            actual_description = body.get("content") if isinstance(body, dict) else None
            description_matches = (
                isinstance(body, dict) and str(body.get("contentType") or "").casefold() == "text" and
                actual_description == event["description"]
            ) if event["description"] else (
                body is None or isinstance(body, dict) and actual_description in (None, "")
            )
            if (verified.get("id") != event_id or verified.get("subject") != event["summary"] or
                    actual_start != start_dt or actual_end != end_dt or
                    str(actual_location.get("displayName") or "") != event["location"] or
                    not isinstance(attendees, list) or attendees or not description_matches):
                raise OutlookCalendarWriteOutcomeUnknown(
                    "Microsoft accepted the request but Hutch could not verify the exact guest-free event; check the calendar before retrying")
        except OutlookCalendarWriteOutcomeUnknown:
            raise
        except OutlookCalendarError:
            raise OutlookCalendarWriteOutcomeUnknown(
                "Microsoft may have created the event, but Hutch could not verify it. Check the calendar before retrying") from None
        return {"id": event_id, "summary": event["summary"], "start": event["start"],
                "end": event["end"], "location": event["location"]}


__all__ = ["OutlookCalendarWriteBook", "OutlookCalendarWriteOutcomeUnknown",
           "OutlookCalendarWriteSecretToolStore", "CALENDAR_WRITE_SCOPE", "CALENDAR_WRITE_CALLBACK_PATH"]
