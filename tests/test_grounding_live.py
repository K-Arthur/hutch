"""Live, read-only smoke checks against real public endpoints.

Skipped unless ``HUTCH_LIVE_TEST=1``: the offline suite must remain deterministic. These
checks prove the shipped acquisition paths work against the actual services — GDELT,
a public RSS feed, Hacker News Algolia, and the Wikimedia SSE stream — and they assert
structural honesty (state vocabulary, parsed timestamps in frame, cursor shape), never
that today's news is non-empty.
"""

from __future__ import annotations

import os

import pytest

from hutch.grounding import acquire as acquire_mod
from hutch.grounding.clock import SYSTEM_CLOCK
from hutch.grounding.streams import StreamPump, read_wikimedia_stream
from hutch.grounding.temporal import EvidenceCutoff

pytestmark = pytest.mark.skipif(os.environ.get("HUTCH_LIVE_TEST") != "1",
                                reason="live network checks run only with HUTCH_LIVE_TEST=1")

CFG = acquire_mod.GroundingConfig(feeds=("https://feeds.bbci.co.uk/news/world/rss.xml",))
BUDGET = acquire_mod.AcquireBudget(max_results_per_adapter=5, per_adapter_timeout=30.0)


def _cutoff(hours=48):
    return EvidenceCutoff.from_clock(SYSTEM_CLOCK, horizon_hours=hours)


def test_live_gdelt_returns_articles_with_validated_dates():
    sources, outcome = acquire_mod.search_gdelt("storm", _cutoff(72), BUDGET, SYSTEM_CLOCK, CFG, lambda: False)
    assert outcome.state in ("ok", "zero_results", "rate_limited"), outcome.to_json()
    if outcome.state == "ok":
        assert sources and all(s.published and s.published.instant for s in sources)
        assert outcome.retained <= 5
    print(f"[live] gdelt: {outcome.state} retained={outcome.retained} "
          f"dropped_out_of_range={outcome.dropped_out_of_range} latency={outcome.latency_ms}ms")


def test_live_feed_preserves_declared_publication_dates():
    sources, outcome = acquire_mod.search_feeds("news", _cutoff(168), BUDGET, SYSTEM_CLOCK, CFG, lambda: False)
    assert outcome.retained > 0, outcome.to_json()
    assert all(s.published is not None for s in sources)
    print(f"[live] bbc feed: retained={outcome.retained} newest={sources[0].published.instant}")


def test_live_hn_search_parses_story_times():
    sources, outcome = acquire_mod.search_hn("python", _cutoff(72), BUDGET, SYSTEM_CLOCK, CFG, lambda: False)
    assert outcome.state in ("ok", "zero_results")
    if sources:
        assert all(s.published and s.published.instant for s in sources)
    print(f"[live] hn: {outcome.state} retained={outcome.retained}")


def test_live_wikimedia_stream_reads_events_with_a_structured_cursor():
    pump = StreamPump(key_fn=lambda e: str(e.get("id", "")), clock=SYSTEM_CLOCK)
    report = read_wikimedia_stream(pump=pump, stream_key="recentchange", clock=SYSTEM_CLOCK,
                                   max_events=40, max_seconds=20.0)
    assert report["connected"], report
    assert report["events"] > 0 or report["state"] == "quiet"
    if pump.cursor is not None:
        assert pump.cursor.kind == "structured_json"
        assert isinstance(pump.cursor.value, list)
    print(f"[live] wikimedia stream: state={report['state']} events={report['events']} "
          f"duplicates={report['duplicates']} canary_age={report['canary_age_seconds']}")


def test_live_jetstream_bounded_window_with_a_seq_cursor():
    from hutch.grounding.streams import read_jetstream_stream
    pump = StreamPump(key_fn=lambda e: str(e.get("seq", "")), clock=SYSTEM_CLOCK)
    report = read_jetstream_stream(pump=pump, max_events=30, max_seconds=15.0, clock=SYSTEM_CLOCK)
    assert report["state"] in ("live", "quiet", "gap"), report
    assert report.get("scanned", 0) > 0, report
    if report["state"] != "gap":
        assert pump.cursor is not None and pump.cursor.kind == "seq"
    print(f"[live] jetstream: state={report['state']} scanned={report.get('scanned')} "
          f"kept={report['events']} duplicates={report['duplicates']} cursor={pump.cursor.value if pump.cursor else None}")
