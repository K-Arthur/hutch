"""Schedule history, policy and roll-call routes.

The route module is separate from ``app.py`` so the frozen app factory gains one
registration line instead of a new route body. Every route is local-owner only
through the existing dashboard middleware.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from ..schedule_conditions import ConditionError
from ..schedule_history import list_occurrences, list_revisions, schedule_identity_exists
from ..schedule_policy import PolicyUnsupported, all_policies, get_policy, put_policy
from ..schedule_roll_call import roll_call
from ..store import RevisionConflict


class SchedulePolicyPut(BaseModel):
    approval_required: bool = False
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    expected_revision: Optional[int] = Field(default=None, ge=0)


def _schedule_for(bot, schedule_id: str):
    for scheduled in bot.schedules or ([bot.schedule] if bot.schedule else []):
        if scheduled.id == schedule_id:
            return scheduled
    return None


def _require_schedule(bot, schedule_id: str, store) -> None:
    if _schedule_for(bot, schedule_id) is None and not schedule_identity_exists(
            store, bot.id, schedule_id):
        raise HTTPException(404, f"no such scheduled task: {schedule_id}")


def _register_revision_routes(app, store, bot_or_404) -> None:
    @app.get("/api/v1/bots/{ref}/schedules/{schedule_id}/revisions")
    def schedule_revisions(ref: str, schedule_id: str, limit: int = Query(50, ge=1, le=100),
                           offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
        bot = bot_or_404(ref)
        _require_schedule(bot, schedule_id, store)
        return list_revisions(store, bot.id, schedule_id, limit=limit, offset=offset)


def _register_policy_routes(app, store, bot_or_404) -> None:
    @app.get("/api/v1/bots/{ref}/schedules/{schedule_id}/policy")
    def schedule_policy(ref: str, schedule_id: str) -> dict[str, Any]:
        bot = bot_or_404(ref)
        _require_schedule(bot, schedule_id, store)
        return get_policy(store, bot.id, schedule_id).as_dict()

    @app.put("/api/v1/bots/{ref}/schedules/{schedule_id}/policy")
    def put_schedule_policy(ref: str, schedule_id: str, body: SchedulePolicyPut) -> dict[str, Any]:
        bot = bot_or_404(ref)
        try:
            policy = put_policy(
                store, bot.id, schedule_id, approval_required=body.approval_required,
                conditions=body.conditions, expected_revision=body.expected_revision,
            )
        except KeyError:
            raise HTTPException(404, f"no such scheduled task: {schedule_id}") from None
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except (ConditionError, PolicyUnsupported) as exc:
            raise HTTPException(422, str(exc)) from None
        return policy.as_dict()

    @app.get("/api/v1/schedule-policies")
    def list_schedule_policies(limit: int = Query(500, ge=1, le=500)) -> list[dict[str, Any]]:
        return all_policies(store, limit=limit)


def _register_history_routes(app, store, bot_or_404) -> None:
    @app.get("/api/v1/bots/{ref}/schedules/{schedule_id}/history")
    def schedule_history(ref: str, schedule_id: str, limit: int = Query(20, ge=1, le=50)) -> dict[str, Any]:
        bot = bot_or_404(ref)
        _require_schedule(bot, schedule_id, store)
        scheduled = _schedule_for(bot, schedule_id)
        return {
            "schedule_id": schedule_id,
            "workflow_linked": bool(scheduled and scheduled.workflow_definition_id),
            "policy": get_policy(store, bot.id, schedule_id).as_dict(),
            "revisions": list_revisions(store, bot.id, schedule_id, limit=limit),
            "occurrences": list_occurrences(store, schedule_id, limit=limit),
        }


def _register_roll_call_routes(app, store, bot_or_404, scheduler) -> None:
    @app.get("/api/v1/schedules/roll-call")
    def schedule_roll_call() -> dict[str, Any]:
        return roll_call(store, scheduler)


def register_schedule_routes(app, store, bot_or_404, scheduler) -> None:
    """Register every Phase 2 schedule route from one app-factory call."""
    _register_revision_routes(app, store, bot_or_404)
    _register_policy_routes(app, store, bot_or_404)
    _register_history_routes(app, store, bot_or_404)
    _register_roll_call_routes(app, store, bot_or_404, scheduler)
