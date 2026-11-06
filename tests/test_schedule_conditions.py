"""Bounded schedule conditions: closed schema, strict types and AND evaluation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hutch.models import Bot, Schedule
from hutch.schedule_conditions import (
    MAX_CONDITIONS,
    ConditionError,
    evaluate_conditions,
    schedule_context,
    validate_conditions,
)


def _condition(field: str, op: str, value):
    return {"field": field, "op": op, "value": value}


def test_valid_conditions_normalize_and_null_is_empty():
    assert validate_conditions(None) == []
    parsed = validate_conditions([
        _condition("schedule_timezone", "eq", "UTC"),
        _condition("occurrence_weekday", "in", [0, 1, 2, 3, 4]),
        _condition("missed_windows", "gte", 0),
        _condition("schedule_name", "contains", "release"),
    ])
    assert parsed[0] == _condition("schedule_timezone", "eq", "UTC")
    assert parsed[1]["value"] == [0, 1, 2, 3, 4]


@pytest.mark.parametrize("value, message", [
    (_condition("prompt", "eq", "secret"), "unknown condition field"),
    (_condition("schedule_timezone", "regex", ".*"), "unknown condition operator"),
    (_condition("schedule_timezone", "eq", {"nested": True}), "must be string"),
    (_condition("occurrence_weekday", "eq", True), "must be integer"),
    (_condition("occurrence_weekday", "contains", "1"), "contains requires a string field"),
    (_condition("schedule_name", "lt", "z"), "only valid for integer fields"),
    (_condition("schedule_timezone", "in", "UTC"), "requires a list"),
    (_condition("schedule_timezone", "in", ["UTC"] * 21), "1 to 20"),
    (_condition("schedule_timezone", "eq", "x" * 201), "capped at 200"),
])
def test_invalid_conditions_are_rejected_before_save(value, message):
    with pytest.raises(ConditionError, match=message):
        validate_conditions([value])


def test_condition_count_and_nesting_are_bounded():
    with pytest.raises(ConditionError, match="at most"):
        validate_conditions([_condition("schedule_timezone", "eq", "UTC")] * (MAX_CONDITIONS + 1))
    with pytest.raises(ConditionError):
        validate_conditions([{"field": "schedule_name", "op": "eq", "value": "x", "extra": 1}])


def _context():
    bot = Bot(name="release-watch", tools=[])
    schedule = Schedule(name="Nightly release check", cron="0 3 * * *", timezone="America/New_York")
    occurrence = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)   # 07:00 EST, Friday
    return schedule_context(bot, schedule, occurrence, 2)


def test_context_uses_the_schedule_zone_and_occurrence_facts():
    context = _context()
    assert context["occurrence_weekday"] == 4
    assert context["occurrence_hour"] == 7
    assert context["missed_windows"] == 2
    assert context["bot_paused"] is False


def test_all_conditions_must_pass_and_failures_name_only_field_and_operator():
    context = _context()
    assert evaluate_conditions([], context) == (True, "")
    assert evaluate_conditions([
        _condition("schedule_timezone", "eq", "America/New_York"),
        _condition("occurrence_weekday", "in", [0, 1, 2, 3, 4]),
        _condition("missed_windows", "lte", 2),
    ], context) == (True, "")
    assert evaluate_conditions([_condition("occurrence_weekday", "eq", 0)], context) == (
        False, "occurrence_weekday:eq")
    assert evaluate_conditions([_condition("schedule_name", "contains", "release")], context) == (True, "")
    assert evaluate_conditions([_condition("schedule_name", "contains", "secret")], context) == (
        False, "schedule_name:contains")


def test_boolean_and_integer_values_are_not_conflated():
    context = _context()
    with pytest.raises(ConditionError):
        validate_conditions([_condition("bot_paused", "eq", 1)])
    with pytest.raises(ConditionError):
        validate_conditions([_condition("occurrence_hour", "eq", False)])
