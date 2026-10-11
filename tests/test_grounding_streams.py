"""Stream continuity: cursor namespaces, verbatim resume, dedup, canary-aware liveness."""

from __future__ import annotations

import json

import pytest

from hutch.grounding.clock import FrozenClock
from hutch.grounding.streams import (
    CursorKind, CursorMismatch, LivenessState, StreamCursor, StreamPump, jetstream_readiness,
    migrate_jetstream_cursor, parse_jetstream_cursor, parse_jetstream_event, parse_sse,
    read_wikimedia_stream, wikimedia_cursor,
)

CLOCK = FrozenClock.at("2026-10-11T12:00:00+00:00")


def test_jetstream_cursor_kind_is_decided_by_the_documented_magnitude_rule():
    seq = parse_jetstream_cursor(123_456_789, instance="js-1")
    assert seq.kind == CursorKind.seq.value and seq.value == 123_456_789
    ts = parse_jetstream_cursor(1_789_920_855_962_065, instance="js-1")
    assert ts.kind == CursorKind.timestamp_micros.value
    with pytest.raises(CursorMismatch):
        parse_jetstream_cursor("not-a-number", instance="js-1")


def test_mixed_namespace_comparison_is_impossible_and_migration_is_explicit():
    """The #349 failure class: a v1 timestamp compared against v2 seqs silently dropped
    everything. Kinds differ, lineages differ, and a migration rewinds with a reason."""
    seq = parse_jetstream_cursor(1000, instance="js-1")
    ts = parse_jetstream_cursor(1_789_920_855_962_065, instance="js-1")
    assert not seq.same_lineage(ts)
    with pytest.raises(CursorMismatch):
        migrate_jetstream_cursor(ts, new_instance="js-2")     # timestamps cannot be rewound like seqs
    moved, note = migrate_jetstream_cursor(seq, new_instance="js-2", rewind=500)
    assert moved.value == 500 and moved.instance == "js-2"
    assert "rewound" in note and "at-least-once" in note


def test_wikimedia_cursor_is_a_structured_array_not_an_integer():
    ids = [{"topic": "eqiad.mediawiki.recentchange", "partition": 0, "timestamp": 1532031066001},
           {"topic": "codfw.mediawiki.recentchange", "partition": 0, "offset": -1}]
    cursor = wikimedia_cursor(ids)
    assert cursor.kind == CursorKind.structured_json.value
    assert cursor.value == ids
    assert "multi-DC-stable" in cursor.note


def test_sse_framing_tolerates_comments_and_multi_data_lines():
    lines = [": heartbeat", "event: message", "id: [{\"a\":1}]", 'data: {"x": 1,', "data:  \"y\": 2}", "", ""]
    events = list(parse_sse(lines))
    assert len(events) == 1
    event = events[0]
    assert event.id == '[{"a":1}]'
    assert json.loads(event.data) == {"x": 1, "y": 2}


def _pump():
    return StreamPump(key_fn=lambda e: e.get("id", ""), clock=CLOCK)


def test_stream_pump_deduplicates_overlap_and_counts_late_events():
    pump = _pump()
    first = {"id": "a", "published_instant": "2026-10-11T11:00:00+00:00"}
    assert pump.observe(first, event_key="a") is True
    assert pump.observe(first, event_key="a") is False           # reconnect overlap
    assert pump.liveness.events == 1 and pump.liveness.duplicates == 1
    late = {"id": "b"}
    pump.observe(late, event_key="b", event_time=CLOCK.now() - __import__("datetime").timedelta(hours=2))
    assert pump.liveness.late == 1


def test_stream_pump_refuses_mixed_cursor_lineages_mid_stream():
    pump = _pump()
    pump.observe({"id": "a"}, event_key="a", cursor=parse_jetstream_cursor(10, instance="js-1"))
    with pytest.raises(CursorMismatch):
        pump.observe({"id": "b"}, event_key="b", cursor=parse_jetstream_cursor(11, instance="js-2"))


def test_jetstream_event_parsing_keeps_seq_and_time_separate():
    raw = json.dumps({"did": "did:plc:x", "seq": 42, "time_us": 1789920855962065, "kind": "commit",
                      "commit": {"operation": "create", "collection": "app.bsky.feed.post", "rkey": "abc"}})
    event = parse_jetstream_event(raw)
    assert event.seq == 42 and event.time_us == 1789920855962065
    assert event.dedup_key() == "seq:42"
    assert parse_jetstream_event("garbage") is None


def test_jetstream_readiness_is_honest_about_the_missing_dependency():
    state, detail = jetstream_readiness()
    assert state in ("unsupported", "ready")
    if state == "unsupported":
        assert "websockets" in detail


class _FakeStream:
    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self):
        yield from self._lines


class _FakeResponse:
    def __init__(self, status, lines):
        self.status_code = status
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_lines(self):
        yield from self._lines


def test_wikimedia_read_filters_client_side_and_survives_canaries(monkeypatch):
    events = [
        "event: message",
        'id: [{"topic":"eqiad.mediawiki.recentchange","partition":0,"timestamp":1791701009229}]',
        "data: " + json.dumps({"meta": {"id": "e1", "dt": "2026-10-11T11:59:00Z",
                                        "domain": "canary"}, "type": "canary"}),
        "",
        "event: message",
        'id: [{"topic":"eqiad.mediawiki.recentchange","partition":0,"timestamp":1791701009230}]',
        "data: " + json.dumps({"meta": {"id": "e2", "dt": "2026-10-11T11:59:01Z",
                                        "domain": "en.wikipedia.org"}, "title": "Solar storm", "wiki": "enwiki"}),
        "",
        "event: message",
        'id: [{"topic":"eqiad.mediawiki.recentchange","partition":0,"timestamp":1791701009231}]',
        "data: " + json.dumps({"meta": {"id": "e3", "dt": "2026-10-11T11:59:02Z",
                                        "domain": "de.wikipedia.org"}, "title": "Sonnensturm", "wiki": "dewiki"}),
        "",
    ]

    def fake_open(url, timeout, headers):
        class _Manager:
            def __exit__(self, *exc):
                return False
        return (_FakeResponse(200, events), type("C", (), {"close": lambda self: None})(), _Manager())

    monkeypatch.setattr("hutch.grounding.streams._open_pinned_stream", fake_open)
    pump = _pump()
    seen: list[str] = []
    report = read_wikimedia_stream(pump=pump, stream_key="recentchange", clock=CLOCK,
                                   filter_fn=lambda e: e.get("wiki") == "enwiki",
                                   max_events=10, max_seconds=5.0)
    assert pump.liveness.events == 2 and pump.liveness.last_canary_at is not None
    assert report["state"] in ("live", "quiet")
    assert report["note"]  # honest note about what liveness does NOT prove
    assert pump.cursor.kind == CursorKind.structured_json.value


def test_wikimedia_blocked_connect_reports_blocked_not_quiet(monkeypatch):
    def refuse(url, timeout, headers):
        from hutch.netguard import NetGuardError
        raise NetGuardError("non-public address for stream.example")

    monkeypatch.setattr("hutch.grounding.streams._open_pinned_stream", refuse)
    pump = _pump()
    report = read_wikimedia_stream(pump=pump, clock=CLOCK, max_events=1, max_seconds=1.0)
    assert report["state"] == "blocked" and "non-public address" in report["gap_note"]


def test_liveness_report_separates_connected_from_coverage():
    state = LivenessState(connected=True, connected_at=CLOCK.now())
    report = state.report(CLOCK.now())
    assert report["connected"] is True and report["state"] == "unknown"
    assert "does not prove filtering or coverage" in report["note"]
    assert report["canary_age_seconds"] is None
