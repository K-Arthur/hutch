"""Read-only schedule history routes.

The route module is separate from ``app.py`` so the frozen app factory gains one
registration line instead of a new route body. Policy and roll-call routes live
here too; each group has its own small registration helper.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query

from ..schedule_history import list_revisions, schedule_identity_exists


def _schedule_for(bot, schedule_id: str):
    for scheduled in bot.schedules or ([bot.schedule] if bot.schedule else []):
        if scheduled.id == schedule_id:
            return scheduled
    return None


def _register_revision_routes(app, store, bot_or_404) -> None:
    @app.get("/api/v1/bots/{ref}/schedules/{schedule_id}/revisions")
    def schedule_revisions(ref: str, schedule_id: str, limit: int = Query(50, ge=1, le=100),
                           offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
        bot = bot_or_404(ref)
        if _schedule_for(bot, schedule_id) is None and not schedule_identity_exists(
                store, bot.id, schedule_id):
            raise HTTPException(404, f"no such scheduled task: {schedule_id}")
        return list_revisions(store, bot.id, schedule_id, limit=limit, offset=offset)


def register_schedule_routes(app, store, bot_or_404) -> None:
    """Register every Phase 2 schedule route from one app-factory call."""
    _register_revision_routes(app, store, bot_or_404)
