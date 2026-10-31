"""Adapters from the owner's reviewed grants to the agenda builder's readers.

This module is the only place the agenda touches persisted grants, OAuth account
metadata or provider clients. It reads; it never writes a row and never stores
provider text. Every failure becomes an explicit reason code so Today can say why a
source is missing instead of drawing an empty day.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..google_calendar import GoogleCalendarBook, GoogleCalendarError
from ..google_mail import GoogleMailBook, validate_local_gmail_bot
from ..google_oauth_config import resolve_google_oauth_client_id
from ..models import iso
from .agenda import AgendaSource, AgendaUnavailable, clean

MAIL_QUERY = "newer_than:1d"


def calendar_book(config, store) -> GoogleCalendarBook:
    """The real Calendar client; tests replace these factories with fakes."""
    return GoogleCalendarBook(Path(config.state_dir), resolve_google_oauth_client_id(store)[0])


def mail_book(config, store) -> GoogleMailBook:
    """The real Gmail client; tests replace these factories with fakes."""
    return GoogleMailBook(Path(config.state_dir), resolve_google_oauth_client_id(store)[0])


def _label(bot) -> str:
    return bot.display_name or bot.name


def _connected_account(book, account_id: str) -> dict[str, Any]:
    """Read the local account record; an absent or revoked account is an expired grant."""
    try:
        accounts = {row.get("id"): row for row in book.accounts()}
    except GoogleCalendarError as exc:
        raise AgendaUnavailable("grant_expired", str(exc)) from None
    account = accounts.get(account_id)
    if account is None or account.get("status") != "connected":
        raise AgendaUnavailable("grant_expired", "This account is no longer connected in Hutch; reconnect it.")
    return account


def _renew(book, account_id: str) -> None:
    """Obtain an access token *before* reading, so a credential failure is identifiable.

    Classifying by call site beats classifying by message text: a revoked or expired
    refresh token is whatever the provider chooses to answer with (Google's canonical
    answer is HTTP 400 ``invalid_grant``), and matching on Hutch's own error copy would
    silently miss any status that has not been seen yet.
    """
    try:
        book.access_token(account_id)
    except AgendaUnavailable:
        raise
    except Exception:
        raise AgendaUnavailable(
            "grant_expired",
            "This account's saved permission is no longer usable; reconnect it in Connections.") from None


def _read_failure(book, account_id: str, exc: Exception) -> AgendaUnavailable:
    """Decide whether a failed read was really a failed credential.

    The probe asks the client for a token: if the credential no longer works, the owner
    must reconnect, and the reading is not merely delayed by a flaky provider.
    """
    try:
        book.access_token(account_id)
    except Exception:
        return AgendaUnavailable("grant_expired", str(exc))
    return AgendaUnavailable("provider_error", str(exc))


def calendar_source(store, config, bot_id: str) -> Optional[AgendaSource]:
    """One assistant's calendar grant as a read-only source, or an explicit unavailability."""
    bot = store.get_bot(bot_id)
    if bot is None:
        return None
    grant = store.google_calendar_grant(bot.id)
    label = _label(bot)
    if not grant:
        return AgendaSource.missing(
            kind="calendar", source="google_calendar", source_label=f"Google Calendar · {label}",
            reason="grant_missing",
            detail="This assistant has no Google Calendar grant. Grant one calendar in Connections.",
            bot_id=bot.id, bot_label=label)
    # The calendar name comes from the provider, so it is bounded and stripped like any other
    # provider text before it becomes part of a label the owner reads.
    calendar_name = clean(grant.get("calendar_name"), 120) or "Calendar"
    selected = AgendaSource(
        kind="calendar", source="google_calendar",
        source_label=f"Google Calendar · {calendar_name}",
        bot_id=bot.id, bot_label=label, account_id=grant["account_id"],
        calendar_id=grant["calendar_id"], calendar_name=calendar_name)

    def fetch(start: datetime, end: datetime) -> list[dict[str, Any]]:
        book = calendar_book(config, store)
        _connected_account(book, selected.account_id)
        _renew(book, selected.account_id)
        try:
            return book.list_events(selected.account_id, selected.calendar_id, iso(start), iso(end),
                                    limit=25)
        except AgendaUnavailable:
            raise
        except GoogleCalendarError as exc:
            raise _read_failure(book, selected.account_id, exc) from None

    return replace(selected, fetch=fetch)


def mail_source(store, config, bot_id: str) -> Optional[AgendaSource]:
    """One assistant's Gmail grant as a bounded read-only digest, under the tool's local rule."""
    bot = store.get_bot(bot_id)
    if bot is None:
        return None
    label = _label(bot)
    grant = store.google_mail_grant(bot.id)
    if not grant:
        return AgendaSource.missing(
            kind="mail", source="gmail", source_label=f"Gmail · {label}", reason="grant_missing",
            detail="This assistant has no Gmail grant. Grant one mailbox in Connections.",
            bot_id=bot.id, bot_label=label)
    try:
        validate_local_gmail_bot(bot)
    except GoogleCalendarError as exc:
        return AgendaSource.missing(
            kind="mail", source="gmail", source_label=f"Gmail · {label}",
            reason="mail_requires_local", detail=str(exc),
            bot_id=bot.id, bot_label=label, account_id=grant["account_id"])
    selected = AgendaSource(
        kind="mail", source="gmail", source_label=f"Gmail · {label}",
        bot_id=bot.id, bot_label=label, account_id=grant["account_id"])

    def fetch(start: datetime, end: datetime) -> list[dict[str, Any]]:
        book = mail_book(config, store)
        _connected_account(book, selected.account_id)
        _renew(book, selected.account_id)
        try:
            return book.list_messages(selected.account_id, MAIL_QUERY, limit=10)
        except AgendaUnavailable:
            raise
        except GoogleCalendarError as exc:
            raise _read_failure(book, selected.account_id, exc) from None

    return replace(selected, fetch=fetch)


def list_sources(store) -> dict[str, list[dict[str, str]]]:
    """Connections the owner can choose from, without secrets or provider content."""
    calendar: list[dict[str, str]] = []
    for grant in store.list_google_calendar_grants():
        calendar.append({
            "bot_id": grant["bot_id"],
            "bot_label": grant.get("bot_name") or grant["bot_id"],
            "account_id": grant["account_id"],
            "calendar_id": grant["calendar_id"],
            "calendar_name": clean(grant.get("calendar_name"), 120) or "Calendar",
            "granted_at": grant.get("granted_at") or "",
        })
    mail: list[dict[str, str]] = []
    for grant in store.list_google_mail_grants():
        bot = store.get_bot(grant["bot_id"])
        usable, detail = True, ""
        if bot is not None:
            try:
                validate_local_gmail_bot(bot)
            except GoogleCalendarError as exc:
                usable, detail = False, str(exc)
        mail.append({
            "bot_id": grant["bot_id"],
            "bot_label": grant.get("bot_name") or grant["bot_id"],
            "account_id": grant["account_id"],
            "granted_at": grant.get("granted_at") or "",
            "local_inference": usable,
            "detail": detail,
        })
    calendar.sort(key=lambda row: (row["bot_label"].lower(), row["calendar_id"]))
    mail.sort(key=lambda row: row["bot_label"].lower())
    return {
        "calendar": calendar,
        "mail": mail,
        "not_included": [
            "Only connections already granted to an assistant appear here. Connect an account and "
            "grant it on Connections first; the agenda cannot grant itself access.",
            "Mailbox previews require an assistant that uses Local inference, so a hosted assistant "
            "is listed as unavailable rather than quietly read.",
        ],
    }
