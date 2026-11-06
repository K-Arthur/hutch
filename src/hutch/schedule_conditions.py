"""Bounded declarative conditions for schedule and source runs.

This is deliberately not an expression language. A condition is one literal
comparison over an allowlisted field. Values are scalars or a short list of
scalars; nested objects, regular expressions, attribute access and code are all
rejected before the policy is saved. All conditions must pass.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

MAX_CONDITIONS = 8
MAX_LIST_VALUES = 20
MAX_STRING_CHARS = 200

FIELD_KINDS = {
    "schedule_name": "string",
    "schedule_timezone": "string",
    "schedule_trigger": "string",
    "schedule_enabled": "boolean",
    "bot_name": "string",
    "bot_paused": "boolean",
    "occurrence_weekday": "integer",
    "occurrence_hour": "integer",
    "missed_windows": "integer",
}
OPERATORS = frozenset({"eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "contains"})


class ConditionError(ValueError):
    """A condition list is outside the closed schema."""


def _matches_kind(value: Any, kind: str) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return False


def _validate_value(kind: str, op: str, value: Any) -> None:
    if op in ("in", "not_in"):
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_LIST_VALUES:
            raise ValueError(f"{op} requires a list of 1 to {MAX_LIST_VALUES} values")
        for item in value:
            if not _matches_kind(item, kind):
                raise ValueError(f"{op} values must be {kind}")
            if isinstance(item, str) and len(item) > MAX_STRING_CHARS:
                raise ValueError(f"condition strings are capped at {MAX_STRING_CHARS} characters")
        return
    if op == "contains":
        if kind != "string" or not isinstance(value, str):
            raise ValueError("contains requires a string field and a string value")
        if len(value) > MAX_STRING_CHARS:
            raise ValueError(f"condition strings are capped at {MAX_STRING_CHARS} characters")
        return
    if not _matches_kind(value, kind):
        raise ValueError(f"{op} value must be {kind}")
    if op in ("lt", "lte", "gt", "gte") and kind != "integer":
        raise ValueError(f"{op} is only valid for integer fields")
    if isinstance(value, str) and len(value) > MAX_STRING_CHARS:
        raise ValueError(f"condition strings are capped at {MAX_STRING_CHARS} characters")


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    op: str
    value: Any

    @model_validator(mode="after")
    def _closed_schema(self) -> "Condition":
        kind = FIELD_KINDS.get(self.field)
        if kind is None:
            raise ValueError(f"unknown condition field: {self.field[:40]}")
        if self.op not in OPERATORS:
            raise ValueError(f"unknown condition operator: {self.op[:40]}")
        _validate_value(kind, self.op, self.value)
        return self


def validate_conditions(raw: Any) -> list[dict[str, Any]]:
    """Return a normalized condition list or raise ``ConditionError``."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConditionError("conditions must be a list")
    if len(raw) > MAX_CONDITIONS:
        raise ConditionError(f"at most {MAX_CONDITIONS} conditions are allowed")
    parsed: list[dict[str, Any]] = []
    for item in raw:
        try:
            condition = Condition.model_validate(item)
        except ValidationError as exc:
            message = str(exc.errors()[0].get("msg") or "invalid condition")
            raise ConditionError(message.removeprefix("Value error, ")[:200]) from None
        parsed.append(condition.model_dump())
    return parsed


def schedule_context(bot, schedule, occurrence: datetime, missed: int) -> dict[str, Any]:
    """Facts a condition may read. An invalid zone already blocks the schedule upstream."""
    try:
        zone = ZoneInfo(schedule.timezone)
    except Exception:
        zone = timezone.utc
    aware = occurrence if occurrence.tzinfo is not None else occurrence.replace(tzinfo=timezone.utc)
    local = aware.astimezone(zone)
    return {
        "schedule_name": schedule.name,
        "schedule_timezone": schedule.timezone,
        "schedule_trigger": schedule.trigger.value,
        "schedule_enabled": bool(schedule.enabled),
        "bot_name": bot.name,
        "bot_paused": bool(bot.paused),
        "occurrence_weekday": local.weekday(),
        "occurrence_hour": local.hour,
        "missed_windows": int(missed),
    }


def _same(actual: Any, expected: Any, kind: str) -> bool:
    if kind == "boolean":
        return isinstance(actual, bool) and actual == expected
    if kind == "integer":
        return isinstance(actual, int) and not isinstance(actual, bool) and actual == expected
    return isinstance(actual, str) and actual == expected


def _compare(op: str, actual: Any, expected: Any, kind: str) -> bool:
    if op == "eq":
        return _same(actual, expected, kind)
    if op == "ne":
        return not _same(actual, expected, kind)
    if op == "in":
        return any(_same(actual, item, kind) for item in expected)
    if op == "not_in":
        return not any(_same(actual, item, kind) for item in expected)
    if op == "contains":
        return isinstance(actual, str) and expected in actual
    if op == "lt":
        return actual < expected
    if op == "lte":
        return actual <= expected
    if op == "gt":
        return actual > expected
    return actual >= expected


def evaluate_conditions(conditions: list[dict[str, Any]], context: dict[str, Any]) -> tuple[bool, str]:
    """All conditions must pass. The reason names the field and operator only."""
    for condition in conditions:
        field = condition["field"]
        if field not in context:
            return False, f"{field}:unavailable"
        kind = FIELD_KINDS[field]
        if not _compare(condition["op"], context[field], condition["value"], kind):
            return False, f"{field}:{condition['op']}"
    return True, ""
