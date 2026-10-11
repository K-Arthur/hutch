"""Jetstream live reader: bounded reads, at-least-once dedup, explicit cursor recovery.

A real local websocket server (the same ``websockets`` dependency the reader wants) plays
documented frames, a duplicate, and a ``CursorTooOld`` handshake rejection — no network.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from hutch.grounding import acquire as acquire_mod
from hutch.grounding import streams as stream_mod
from hutch.grounding.clock import FrozenClock
from hutch.grounding.streams import (
    CursorKind, StreamCursor, StreamPump, read_jetstream_stream,
)
from hutch.grounding.temporal import EvidenceCutoff

ws_server = pytest.importorskip("websockets.sync.server")

CLOCK = FrozenClock.at("2026-10-11T12:00:00+00:00")
CUTOFF = EvidenceCutoff.from_clock(CLOCK, horizon_hours=24)


def frame(seq: int, text: str = "event") -> str:
    return json.dumps({"did": "did:plc:fixture", "seq": seq, "time_us": 1789920855000000 + seq,
                       "kind": "commit",
                       "commit": {"operation": "create", "collection": "app.bsky.feed.post",
                                  "rkey": f"r{seq}", "record": {"text": text, "langs": ["en"]}}})


class LocalJetstream:
    """A documented-shape local instance: fixed frames, then keep the socket open briefly."""

    def __init__(self, frames, *, reject_with: bytes | None = None):
        self.frames = frames
        self.reject_with = reject_with
        self.server = ws_server.serve(self._handler, "127.0.0.1", 0,
                                      **self._reject_kwargs())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.socket.getsockname()[1]

    def _reject_kwargs(self):
        if self.reject_with is None:
            return {}
        from websockets.datastructures import Headers
        from websockets.http11 import Response

        def process_request(connection, request):
            return Response(400, "Bad Request", Headers([("Content-Type", "application/json")]),
                            self.reject_with)
        return {"process_request": process_request}

    def _handler(self, connection):
        for item in self.frames:
            connection.send(item)
        time.sleep(1.5)

    @property
    def url_host(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)


def test_bounded_read_dedupes_overlap_and_advances_the_seq_cursor():
    instance = LocalJetstream([frame(5, "aurora tonight"), frame(5, "aurora tonight"), frame(6, "aurora again")])
    try:
        pump = StreamPump(key_fn=lambda e: e.get("id", ""), clock=CLOCK)
        report = read_jetstream_stream(pump=pump, host=instance.url_host, max_events=2, max_seconds=5.0,
                                       clock=CLOCK)
        assert report["connected"] is True
        assert pump.liveness.events == 2 and pump.liveness.duplicates == 1
        assert report["scanned"] == 3
        assert pump.cursor.kind == CursorKind.seq.value and pump.cursor.value == 6
        assert "sample" in report["scanned_note"]
    finally:
        instance.close()


def test_cursor_too_old_is_an_explicit_gap_not_a_silent_skip():
    instance = LocalJetstream([], reject_with=b'{"error":"CursorTooOld","message":"below lookback floor"}')
    try:
        pump = StreamPump(key_fn=lambda e: e.get("id", ""), clock=CLOCK)
        report = read_jetstream_stream(pump=pump, host=instance.url_host, max_events=5, max_seconds=3.0,
                                       clock=CLOCK)
        assert report["state"] == "gap"
        assert "CursorTooOld" in report["gap_note"] and "silently" in report["gap_note"]
        assert pump.liveness.events == 0
    finally:
        instance.close()


def test_term_filter_keeps_only_matching_frames_but_counts_traffic():
    instance = LocalJetstream([frame(1, "buy my token now"), frame(2, "aurora visible over the city"),
                               frame(3, "unrelated chatter")])
    try:
        pump = StreamPump(key_fn=lambda e: e.get("id", ""), clock=CLOCK)
        seen: list[int] = []
        report = read_jetstream_stream(pump=pump, host=instance.url_host, max_events=10, max_seconds=2.0,
                                       filter_fn=lambda e: "aurora" in str((e.payload.get("commit") or {})
                                                                           .get("record", {}).get("text", "")),
                                       sink=lambda e: seen.append(e.seq), clock=CLOCK)
        assert pump.liveness.events == 1 and seen == [2]
        assert report["scanned"] == 3, "traffic is counted even when filtered out"
        # the read position advances even when nothing matched — resume must not restart blind
        assert pump.cursor is not None and pump.cursor.value == 3
    finally:
        instance.close()


def test_unreachable_host_is_blocked_with_a_note():
    pump = StreamPump(key_fn=lambda e: e.get("id", ""), clock=CLOCK)
    report = read_jetstream_stream(pump=pump, host="ws://127.0.0.1:1", max_events=1, max_seconds=2.0, clock=CLOCK)
    assert report["state"] == "blocked" and report["gap_note"]


# ------------------------------------------------------------------ adapter

def _fake_reader_factory(frames, report_state="live"):
    def fake_reader(*, pump, host, cursor=None, kinds=(), collections=(), max_events=10, max_seconds=5.0,
                    filter_fn=None, sink=None, stop=None, clock):
        scanned = 0
        for text in frames:
            event = stream_mod.parse_jetstream_event(text)
            scanned += 1
            if event is None or (filter_fn is not None and not filter_fn(event)):
                continue
            pump.observe({"seq": event.seq}, event_key=event.dedup_key(),
                         cursor=StreamCursor(adapter="jetstream", instance=host, kind="seq", value=event.seq))
            if sink:
                sink(event)
        report = pump.liveness.report(clock.now())
        report["state"] = report_state
        report["scanned"] = scanned
        report["scanned_note"] = f"bounded live window: scanned {scanned} event(s), kept {pump.liveness.events} after the filter"
        return report
    return fake_reader


def test_stream_adapter_builds_sources_and_returns_a_resumable_cursor(monkeypatch):
    monkeypatch.setattr(stream_mod, "read_jetstream_stream",
                        _fake_reader_factory([frame(11, "the kestrel bridge reopened at noon"),
                                              frame(12, "totally unrelated post")]))
    cfg = acquire_mod.GroundingConfig(jetstream_host="ws://instance")
    sources, outcome = acquire_mod.search_jetstream_stream(
        "kestrel bridge", CUTOFF, acquire_mod.AcquireBudget(max_results_per_adapter=5), CLOCK, cfg, lambda: False)
    assert outcome.state == "ok" and outcome.freshness == "stream"
    assert outcome.returned == 2 and outcome.retained == 1
    assert sources[0].platform == "bluesky" and "kestrel" in sources[0].excerpt
    assert "bounded live window" in sources[0].note
    assert outcome.cursor_json["kind"] == "seq" and outcome.cursor_json["value"] == 11


def test_stream_adapter_zero_matches_is_not_nothing_happened(monkeypatch):
    monkeypatch.setattr(stream_mod, "read_jetstream_stream",
                        _fake_reader_factory([frame(21, "unrelated"), frame(22, "also unrelated")]))
    cfg = acquire_mod.GroundingConfig(jetstream_host="ws://instance")
    sources, outcome = acquire_mod.search_jetstream_stream(
        "kestrel bridge", CUTOFF, acquire_mod.AcquireBudget(), CLOCK, cfg, lambda: False)
    assert sources == [] and outcome.state == "zero_results"
    assert "scanned 2" in outcome.detail


def test_stream_adapter_reports_unsupported_without_the_dependency(monkeypatch):
    monkeypatch.setattr(stream_mod, "jetstream_readiness", lambda: ("unsupported", "no websockets here"))
    cfg = acquire_mod.GroundingConfig()
    sources, outcome = acquire_mod.search_jetstream_stream(
        "x", CUTOFF, acquire_mod.AcquireBudget(), CLOCK, cfg, lambda: False)
    assert sources == [] and outcome.state == "unsupported" and "no websockets here" in outcome.detail


def test_stream_cursor_resume_uses_the_stored_instance_and_rewinds_on_a_switch(monkeypatch):
    captured = {}

    def fake_reader(*, pump, host, cursor=None, **kwargs):
        captured["host"], captured["cursor"] = host, cursor
        report = pump.liveness.report(CLOCK.now())
        report.update({"state": "quiet", "scanned": 0, "scanned_note": "no traffic"})
        return report

    monkeypatch.setattr(stream_mod, "read_jetstream_stream", fake_reader)
    stored = StreamCursor(adapter="jetstream", instance="old.example", kind=CursorKind.seq.value,
                          value=5000, schema_version=2).to_json()
    cfg = acquire_mod.GroundingConfig(jetstream_host="new.example",
                                      stream_cursors={"jetstream": stored})
    _sources, outcome = acquire_mod.search_jetstream_stream(
        "x", CUTOFF, acquire_mod.AcquireBudget(), CLOCK, cfg, lambda: False)
    assert captured["host"] == "new.example"
    assert captured["cursor"].instance == "new.example" and captured["cursor"].value == 5000 - 500
    assert "rewound" in outcome.gap_note
