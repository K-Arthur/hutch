"""Acquisition: distinct outcomes, local date validation, bounded fan-out failure modes."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from hutch.grounding import acquire as acquire_mod
from hutch.grounding.clock import FrozenClock
from hutch.grounding.temporal import EvidenceCutoff

CLOCK = FrozenClock.at("2026-10-11T12:00:00+00:00")
CUTOFF = EvidenceCutoff.from_clock(CLOCK, horizon_hours=72)


class FetchStub:
    """Queue of canned responses; records every URL requested."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        status, text, headers = self.responses.pop(0)
        return SimpleNamespace(status=status, text=text, headers=headers or {}, url=url,
                               body=text.encode() if isinstance(text, str) else text, redirects=[], truncated=False)


@pytest.fixture()
def budget():
    return acquire_mod.AcquireBudget(max_results_per_adapter=6)


def test_gdelt_validates_dates_locally_and_tags_seendate(monkeypatch, budget):
    payload = {"articles": [
        {"url": "https://a.example/1", "title": "In frame", "seendate": "20261011T060000Z",
         "domain": "a.example", "language": "English"},
        {"url": "https://b.example/2", "title": "Too old", "seendate": "20250101T000000Z",
         "domain": "b.example", "language": "English"},
    ]}
    stub = FetchStub([(200, json.dumps(payload), {"content-type": "application/json"})])
    monkeypatch.setattr(acquire_mod, "_fetch", stub)
    monkeypatch.setattr(acquire_mod.HostGate, "wait", classmethod(lambda cls, url, minimum, stop: None))
    sources, outcome = acquire_mod.search_gdelt("bridge", CUTOFF, budget, CLOCK,
                                                acquire_mod.GroundingConfig(), lambda: False)
    assert outcome.state == "ok" and outcome.returned == 2 and outcome.retained == 1
    assert outcome.dropped_out_of_range == 1
    assert sources[0].published.method == "gdelt_seendate"
    assert sources[0].published.role == "index"
    assert "crawl/seen" in sources[0].published.note


def test_gdelt_rate_limit_is_its_own_outcome(monkeypatch, budget):
    stub = FetchStub([(429, "slow down", {})])
    monkeypatch.setattr(acquire_mod, "_fetch", stub)
    monkeypatch.setattr(acquire_mod.HostGate, "wait", classmethod(lambda cls, url, minimum, stop: None))
    sources, outcome = acquire_mod.search_gdelt("x", CUTOFF, budget, CLOCK, acquire_mod.GroundingConfig(),
                                                lambda: False)
    assert sources == [] and outcome.state == "rate_limited"
    assert "rate limit" in outcome.detail.lower() or "5 s" in outcome.detail


def test_gdelt_html_block_page_is_not_parsed_as_empty_results(monkeypatch, budget):
    stub = FetchStub([(200, "<html>are you a robot?</html>", {"content-type": "text/html"})])
    monkeypatch.setattr(acquire_mod, "_fetch", stub)
    monkeypatch.setattr(acquire_mod.HostGate, "wait", classmethod(lambda cls, url, minimum, stop: None))
    sources, outcome = acquire_mod.search_gdelt("x", CUTOFF, budget, CLOCK, acquire_mod.GroundingConfig(),
                                                lambda: False)
    assert sources == [] and outcome.state == "error" and "not JSON" in outcome.detail


RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>F</title>
<item><title>Bridge reopened</title><link>https://feed.example/a</link>
<description>Officials said the bridge reopened at noon.</description>
<pubDate>Sat, 11 Oct 2026 06:00:00 GMT</pubDate><guid>fa-1</guid></item>
<item><title>Old story</title><link>https://feed.example/b</link>
<description>From last year.</description>
<pubDate>Wed, 01 Jan 2025 06:00:00 GMT</pubDate><guid>fb-2</guid></item>
</channel></rss>"""


def test_feed_updated_only_is_kept_as_modification_time(monkeypatch, budget):
    atom = '''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Updated bridge report</title><id>entry-1</id>
        <link href="https://feed.example/a"/><updated>2026-10-11T06:00:00Z</updated>
        <summary>bridge reopened update</summary></entry></feed>'''
    monkeypatch.setattr(acquire_mod, "_fetch", FetchStub([(200, atom, {"content-type": "application/atom+xml"})]))
    sources, outcome = acquire_mod.search_feeds("bridge reopened", CUTOFF, budget, CLOCK,
                                                acquire_mod.GroundingConfig(feeds=("https://feed.example/rss",)),
                                                lambda: False)
    assert outcome.state == "ok" and len(sources) == 1
    assert sources[0].published is None
    assert sources[0].updated is not None
    assert sources[0].updated.role == "modification"


def test_feeds_parse_rfc822_dates_and_count_out_of_range(monkeypatch, budget):
    stub = FetchStub([(200, RSS, {"content-type": "application/xml"})])
    monkeypatch.setattr(acquire_mod, "_fetch", stub)
    sources, outcome = acquire_mod.search_feeds("bridge", CUTOFF, budget, CLOCK, acquire_mod.GroundingConfig(),
                                                lambda: False, feed_urls=["https://feed.example/rss"])
    assert outcome.state == "ok" and outcome.retained == 1 and outcome.dropped_out_of_range == 1
    assert sources[0].published.role == "publication"
    assert sources[0].published.instant == "2026-10-11T06:00:00+00:00"


def test_feeds_partial_when_one_feed_fails(monkeypatch, budget):
    stub = FetchStub([(200, RSS, {}), (500, "boom", {})])
    monkeypatch.setattr(acquire_mod, "_fetch", stub)
    sources, outcome = acquire_mod.search_feeds("bridge", CUTOFF, budget, CLOCK, acquire_mod.GroundingConfig(),
                                                lambda: False,
                                                feed_urls=["https://feed.example/rss", "https://other.example/rss"])
    assert outcome.state == "partial" and outcome.retained == 1
    assert "other.example: HTTP 500" in outcome.detail


def test_feeds_unavailable_is_not_zero_results(monkeypatch, budget):
    stub = FetchStub([(500, "boom", {}), (500, "boom", {})])
    monkeypatch.setattr(acquire_mod, "_fetch", stub)
    sources, outcome = acquire_mod.search_feeds("bridge", CUTOFF, budget, CLOCK, acquire_mod.GroundingConfig(),
                                                lambda: False,
                                                feed_urls=["https://feed.example/rss", "https://other.example/rss"])
    assert sources == [] and outcome.state == "unavailable"


SEARX_FILTERED = json.dumps({"results": [], "unresponsive_engines": [["bing news", "time range not supported"]]})
SEARX_PLAIN = json.dumps({"results": [
    {"url": "https://news.example/in", "title": "In range", "publishedDate": "2026-10-11T09:00:00+00:00",
     "content": "detail"},
    {"url": "https://news.example/old", "title": "Out of range", "publishedDate": "2024-01-01T00:00:00+00:00",
     "content": "ancient"},
    {"url": "https://news.example/undated", "title": "No date", "content": "undated snippet"},
], "unresponsive_engines": []})


def test_searxng_disabled_engines_and_filterless_retry(monkeypatch, budget):
    stub = FetchStub([(200, SEARX_FILTERED, {"content-type": "application/json"}),
                      (200, SEARX_PLAIN, {"content-type": "application/json"})])
    monkeypatch.setattr(acquire_mod, "_fetch", stub)
    cfg = acquire_mod.GroundingConfig(searxng_base="http://127.0.0.1:8080", searxng_accepts_json=True)
    sources, outcome = acquire_mod.search_searxng("bridge", CUTOFF, budget, CLOCK, cfg, lambda: False)
    urls = [s.url for s in sources]
    assert outcome.attempts == 2 and outcome.state == "ok"
    assert outcome.dropped_out_of_range == 1
    assert "bing news" in outcome.disabled_engines
    assert "https://news.example/in" in urls and "https://news.example/old" not in urls
    note = next(s.note for s in sources if s.url.endswith("undated"))
    assert "date-unvalidated" in note
    assert "time_range" in stub.urls[0] and "time_range" not in stub.urls[1]


def test_searxng_without_a_configured_instance_says_so(monkeypatch, budget):
    sources, outcome = acquire_mod.search_searxng("x", CUTOFF, budget, CLOCK, acquire_mod.GroundingConfig(),
                                                  lambda: False)
    assert sources == [] and outcome.state == "disabled"
    assert "grounding.json" in outcome.detail


def test_bluesky_403_is_blocked_not_zero_results(monkeypatch, budget):
    stub = FetchStub([(403, "<html>nope</html>", {"content-type": "text/html"})])
    monkeypatch.setattr(acquire_mod, "_fetch", stub)
    sources, outcome = acquire_mod.search_bluesky("x", CUTOFF, budget, CLOCK, acquire_mod.GroundingConfig(),
                                                  lambda: False)
    assert sources == [] and outcome.state == "blocked"
    assert "not 'no posts exist'" in outcome.detail


def _fake(kind, sources=None, state=None, delay=0.0):
    def fn(query, cutoff, budget, clock, cfg, stop):
        if delay:
            time.sleep(delay)
        rows = []
        for i, url in enumerate(sources or []):
            rows.append(acquire_mod.FoundSource(adapter=kind, lane="news", platform="web", kind="article",
                                                url=url, canonical_url=url, title=f"{kind} {i}",
                                                origin="example.com", origin_id=f"{kind}-{i}",
                                                retrieved_at=clock.now().isoformat()))
        outcome = acquire_mod.AdapterOutcome(adapter=kind, lane="news", query=query,
                                             state=state or ("ok" if rows else "zero_results"),
                                             retained=len(rows), returned=len(rows))
        return rows, outcome
    return fn


def test_fan_out_mixes_unavailable_adapters_with_useful_results(monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("provider exploded")

    monkeypatch.setitem(acquire_mod.ADAPTERS, "gdelt", _fake("gdelt", ["https://n.example/1", "https://n.example/2"]))
    monkeypatch.setitem(acquire_mod.ADAPTERS, "hn", broken)
    monkeypatch.setitem(acquire_mod.ADAPTERS, "bluesky",
                        _fake("bluesky", state="blocked"))
    monkeypatch.setitem(acquire_mod.ADAPTERS, "feeds", _fake("feeds", []))
    monkeypatch.setitem(acquire_mod.ADAPTERS, "searxng", _fake("searxng", [], state="disabled"))
    result = acquire_mod.run_search("what happened", cutoff=CUTOFF, budget=acquire_mod.AcquireBudget(),
                                    clock=CLOCK, cfg=acquire_mod.GroundingConfig(),
                                    lanes=("news", "feeds", "discussion", "social", "search"))
    states = {o.adapter: o.state for o in result.outcomes}
    assert states["gdelt"] == "ok" and len(result.sources) == 2
    assert states["hn"] == "error" and "exploded" in next(o.detail for o in result.outcomes if o.adapter == "hn")
    assert states["bluesky"] == "blocked" and states["feeds"] == "zero_results"
    ledger = {row["adapter"]: row["state"] for row in result.missing_ledger()}
    assert ledger == {"hn": "error", "bluesky": "blocked", "searxng": "disabled"}
    assert states["searxng"] == "disabled"


def test_fan_out_wall_deadline_returns_partial_findings(monkeypatch):
    monkeypatch.setitem(acquire_mod.ADAPTERS, "gdelt", _fake("gdelt", ["https://n.example/1"]))
    monkeypatch.setitem(acquire_mod.ADAPTERS, "hn", _fake("hn", ["https://n.example/2"], delay=1.5))
    started = time.monotonic()
    result = acquire_mod.run_search("x", cutoff=CUTOFF, budget=acquire_mod.AcquireBudget(wall_seconds=0.4,
                                                                                         max_adapters=2),
                                    clock=CLOCK, cfg=acquire_mod.GroundingConfig(), lanes=("news", "discussion"))
    elapsed = time.monotonic() - started
    assert result.deadline_hit and any(s.url.endswith("/1") for s in result.sources)
    assert not any(s.url.endswith("/2") for s in result.sources)
    # the wall budget bounds THIS call: the still-running 1.5 s adapter must not hold it open
    assert elapsed < 1.2, f"wall deadline was not a hard bound ({elapsed:.2f}s)"
    discarded = [o for o in result.outcomes if o.state == "partial" and "discarded" in o.detail]
    assert discarded and discarded[0].adapter == "hn"


def test_fan_out_respects_the_total_source_budget(monkeypatch):
    many = [f"https://n.example/{i}" for i in range(10)]
    monkeypatch.setitem(acquire_mod.ADAPTERS, "gdelt", _fake("gdelt", many))
    result = acquire_mod.run_search("x", cutoff=CUTOFF, budget=acquire_mod.AcquireBudget(max_total_sources=4,
                                                                                         max_adapters=1),
                                    clock=CLOCK, cfg=acquire_mod.GroundingConfig(), lanes=("news",))
    assert len(result.sources) == 4 and result.truncated


def test_host_gate_spaces_requests(monkeypatch):
    started = time.monotonic()
    acquire_mod.HostGate.wait("https://gdelt.example/x", 0.08, lambda: False)
    acquire_mod.HostGate.wait("https://gdelt.example/y", 0.08, lambda: False)
    assert time.monotonic() - started >= 0.05
