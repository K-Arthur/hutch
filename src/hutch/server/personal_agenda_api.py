"""Read-only agenda routes for Today.

The owner chooses one calendar grant and one mailbox grant; the server reads them
through the same reviewed grants the assistant tools use, and never writes a row.
An unknown assistant is a 404; a missing, expired or unusable grant is an explicit
unavailable reason in the response, never an empty "nothing scheduled" answer.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException

from ..models import utcnow
from ..personal import agenda_sources
from ..personal.agenda import build_agenda, resolve_zone
from ..personal.today import InvalidTimezone


def install_personal_agenda_routes(app: FastAPI, store, config) -> None:
    cache: dict[str, dict[str, Any]] = {}

    @app.get("/api/v1/personal/agenda/sources")
    def agenda_source_list() -> dict:
        return agenda_sources.list_sources(store)

    @app.get("/api/v1/personal/agenda")
    def agenda(timezone: Optional[str] = None, calendar: Optional[str] = None,
               mail: Optional[str] = None) -> dict:
        now = utcnow()
        try:
            resolve_zone(timezone, now)
        except InvalidTimezone as exc:
            raise HTTPException(422, str(exc)) from None
        selected_calendar = _select(calendar, "calendar", store, config)
        selected_mail = _select(mail, "mail", store, config)
        try:
            return build_agenda(now=now, timezone_name=timezone, calendar=selected_calendar,
                                mail=selected_mail, cache=cache)
        except InvalidTimezone as exc:
            raise HTTPException(422, str(exc)) from None


def _select(bot_id: Optional[str], kind: str, store, config):
    """Resolve one selection; an unknown assistant is not a grant state."""
    value = (bot_id or "").strip()
    if not value:
        return None
    if len(value) > 64 or any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise HTTPException(422, f"{kind} selection must be an assistant id")
    if store.get_bot(value) is None:
        raise HTTPException(404, f"No such assistant for the {kind} selection")
    resolver = agenda_sources.calendar_source if kind == "calendar" else agenda_sources.mail_source
    return resolver(store, config, value)
