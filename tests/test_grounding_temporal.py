"""Temporal semantics: roles, precision, anchoring, as-of modes, DST honesty."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hutch.grounding.clock import FrozenClock, civil, fold_note, utc_iso
from hutch.grounding.temporal import (
    EvidenceCutoff, Precision, TimestampRole, TimestampValue, find_relative_phrases, newest_first,
    parse_any, parse_epoch, parse_gdelt, parse_iso, parse_month_day, parse_relative, parse_rfc822,
    parse_slash_date,
)

CLOCK = FrozenClock.at("2026-10-11T12:00:00+00:00")


def test_offset_iso_is_exact_and_keeps_literal_offset_note():
    value = parse_iso("2026-10-08T05:30:00+02:00", role=TimestampRole.publication.value, clock=CLOCK)
    assert value.instant == "2026-10-08T03:30:00+00:00"
    assert value.precision == Precision.second.value
    assert not value.uncertain
    assert "literal UTC offset" in value.note


def test_offsetless_time_is_uncertain_not_utc_and_not_now():
    value = parse_iso("2026-10-08T05:30", role=TimestampRole.publication.value, clock=CLOCK)
    assert value.uncertain and value.instant.endswith("+00:00")
    assert "unresolved" in value.note
    # with an explicit zone the civil time is resolved deliberately
    zoned = parse_iso("2026-10-08T05:30", role=TimestampRole.publication.value, default_tz="Europe/Berlin",
                      clock=CLOCK)
    assert zoned.instant == "2026-10-08T03:30:00+00:00" and not zoned.uncertain


def test_date_only_is_a_civil_day_interval_never_seconds():
    value = parse_iso("2026-10-08", role=TimestampRole.publication.value, clock=CLOCK)
    assert value.precision == Precision.day.value
    assert value.instant == "2026-10-08T00:00:00+00:00"
    assert value.end_instant == "2026-10-09T00:00:00+00:00"


def test_relative_phrase_anchors_to_speaker_not_reader():
    speaker = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)   # a three-month-old quote
    value = parse_relative("ten minutes ago", reference=speaker)
    assert value.instant == "2026-07-01T08:50:00+00:00"
    assert "2026-07-01" in value.note and "not to now" in value.note
    # the same text in the user's request anchors to the request clock
    now_value = parse_relative("ten minutes ago", reference=CLOCK.now())
    assert now_value.instant == "2026-10-11T11:50:00+00:00"


def test_find_relative_phrases_returns_all_anchored_spans():
    text = "Two hours ago it rained; five minutes ago it stopped."
    found = find_relative_phrases(text, reference=CLOCK.now())
    assert [v.instant for v in found] == ["2026-10-11T10:00:00+00:00", "2026-10-11T11:55:00+00:00"]


def test_rfc822_unknown_offset_stays_uncertain():
    value = parse_rfc822("Tue, 08 Oct 2026 05:30:00 -0000", clock=CLOCK)
    assert value.uncertain and "-0000" in value.note
    known = parse_rfc822("Tue, 08 Oct 2026 05:30:00 GMT", clock=CLOCK)
    assert not known.uncertain


def test_gdelt_seendate_is_index_observation_not_publication():
    value = parse_gdelt("20261008T053000Z", clock=CLOCK)
    assert value.role == TimestampRole.index.value
    assert "crawl/seen" in value.note


def test_ambiguous_slash_date_is_not_silently_resolved():
    value = parse_slash_date("03/04/2026", role=TimestampRole.publication.value)
    assert value.uncertain and value.instant is None
    assert "MDY" in value.note and "DMY" in value.note
    resolved = parse_slash_date("13/04/2026", role=TimestampRole.publication.value)
    assert resolved.instant.startswith("2026-04-13") and not resolved.uncertain


def test_month_day_missing_year_rolls_back_when_it_would_be_future():
    value = parse_month_day("Oct 8", reference=datetime(2027, 1, 5, tzinfo=timezone.utc))
    assert value.instant.startswith("2026-10-08") and value.uncertain
    assert "anchored to 2026" in value.note


def test_epoch_units_must_be_stated_not_guessed():
    assert parse_epoch(1789920855, unit="seconds").instant == "2026-09-20T16:14:15+00:00"
    assert parse_epoch(1789920855962, unit="milliseconds").instant == "2026-09-20T16:14:15.962000+00:00"
    with pytest.raises(ValueError):
        parse_epoch(5, unit="furlongs")


def test_future_dated_value_is_flagged_against_the_clock():
    value = parse_iso("2027-01-01T00:00:00Z", clock=CLOCK)
    assert value.future


def test_unknown_time_sorts_last_never_as_now():
    unknown = TimestampValue(raw="sometime", role=TimestampRole.publication.value)
    known = parse_iso("2026-01-01T00:00:00Z")
    order = newest_first([unknown, known])
    assert order[0] is known and order[-1] is unknown


def test_as_of_modes_stay_distinct():
    cutoff = EvidenceCutoff.from_clock(CLOCK, as_of="2026-10-01T00:00:00Z")
    # evidence observed on Oct 5 is unavailable "as known at Oct 1", but it can still be about
    # an event that occurred before Oct 1
    retrieved = TimestampValue(raw="2026-10-05", role=TimestampRole.retrieval.value,
                               instant="2026-10-05T00:00:00+00:00")
    occurred = TimestampValue(raw="2026-09-20", role=TimestampRole.occurrence.value,
                              instant="2026-09-20T00:00:00+00:00")
    assert cutoff.available_by(occurred) is True
    assert cutoff.available_by(retrieved) is False
    assert cutoff.events_before(occurred) is True
    assert cutoff.events_before(retrieved) is False
    assert "evidence available by that instant" in cutoff.describe()


def test_cutoff_contains_respects_horizon_and_unknowns():
    cutoff = EvidenceCutoff.from_clock(CLOCK, horizon_hours=24)
    recent = parse_iso("2026-10-11T06:00:00Z", clock=CLOCK)
    old = parse_iso("2026-10-01T06:00:00Z", clock=CLOCK)
    unknown = TimestampValue(raw="no date")
    assert cutoff.contains(recent) and not cutoff.contains(old) and not cutoff.contains(unknown)


def test_dst_fold_and_gap_are_reported_not_guessed():
    # 2026-11-01 01:30 in New York happens twice; civil() resolves via the fold offset
    fold_instant = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)   # 01:30 EDT (first pass)
    assert "fold" in fold_note(fold_instant, "America/New_York")
    display = civil(fold_instant, "America/New_York")
    assert "-04:00" in display
    assert utc_iso(fold_instant.astimezone(timezone.utc)) == "2026-11-01T05:30:00+00:00"
    with pytest.raises(Exception):
        civil(fold_instant, "Mars/Olympus_Mons")


def test_parse_any_dispatches_without_losing_the_method():
    assert parse_any("20261008T053000Z", clock=CLOCK).method == "gdelt_seendate"
    assert parse_any("Tue, 08 Oct 2026 05:30:00 GMT", clock=CLOCK).method == "rfc822"
    assert parse_any("2026-10-08T05:30:00Z", clock=CLOCK).method == "iso8601"
