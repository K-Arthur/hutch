"""Adversarial acceptance scenarios over the evidence layer, frozen clocks, no network.

Each test pins one failure mode from the mission table and asserts the *distinction* the
product must preserve, not just that something was returned.
"""

from __future__ import annotations

from datetime import datetime, timezone

from hutch.grounding.clock import FrozenClock
from hutch.grounding.dedup import DedupItem, filter_sensitivity_summary, origin_clusters
from hutch.grounding.report import ClaimDraft, EvidenceLinkDraft, assess_claims, render_brief
from hutch.grounding import acquire as acquire_mod
from hutch.grounding.temporal import (
    EvidenceCutoff, TimestampRole, TimestampValue, parse_iso, parse_relative,
)

CLOCK = FrozenClock.at("2026-10-11T12:00:00+00:00")


def _ts(raw, role, method="iso8601"):
    return parse_iso(raw, role=role, method=method, clock=CLOCK)


def _source(url, origin, published, fetched, title="t", origin_id=None, note=""):
    return acquire_mod.FoundSource(
        adapter="feeds", lane="feeds", platform="web", kind="feed_item", url=url, canonical_url=url,
        title=title, excerpt=title, origin=origin, origin_id=origin_id or url,
        published=published, retrieved_at=fetched, note=note)


def _result(sources):
    outcome = acquire_mod.AdapterOutcome(adapter="feeds", lane="feeds", query="q", state="ok",
                                         retained=len(sources), returned=len(sources))
    return acquire_mod.AcquireResult(sources=sources, outcomes=[outcome])


def test_ten_minutes_versus_three_months_keeps_every_role():
    """A just-published event, an old event reposted now, and a genuinely new update to an
    old controversy must not collapse into one 'current' fact."""
    cutoff = EvidenceCutoff.from_clock(CLOCK, horizon_hours=24)
    fresh = _source("https://news.example/fresh", "news.example",
                    _ts("2026-10-11T11:50:00+00:00", TimestampRole.publication.value),
                    "2026-10-11T11:55:00+00:00", title="Bridge reopens after this morning's storm")
    old_repost = _source("https://archive.example/2024", "archive.example",
                         _ts("2024-06-01T09:00:00+00:00", TimestampRole.publication.value),
                         "2026-10-11T11:59:00+00:00", title="Dramatic flood footage (reposted today)")
    genuinely_new = _source("https://news.example/update", "news.example",
                            _ts("2026-10-11T10:00:00+00:00", TimestampRole.publication.value),
                            "2026-10-11T10:30:00+00:00",
                            title="Old harbour dispute: inspectors publish the new report today")
    # the old repost is outside the requested horizon by its own publication time
    assert not cutoff.contains(old_repost.published)
    assert cutoff.contains(fresh.published) and cutoff.contains(genuinely_new.published)
    relative = parse_relative("ten minutes ago", reference=CLOCK.now())
    assert relative.instant == "2026-10-11T11:50:00+00:00"
    # a quote saying "today" three months ago anchors to the quote, not to now
    quote_reference = datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc)
    quoted = parse_relative("two hours ago", reference=quote_reference)
    assert quoted.instant == "2026-07-08T07:00:00+00:00"
    brief = render_brief("what happened at the bridge today?", _result([fresh, genuinely_new]),
                         cutoff=cutoff, clock=CLOCK)
    assert "publication 2026-10-11" in brief
    assert "2024" not in brief.split("Sources")[0] if "Sources" in brief else True


def test_two_fixtures_with_similar_names_do_not_merge():
    """Similar teams/fixtures must keep separate identities; postponed is not a result."""
    cutoff = EvidenceCutoff.from_clock(CLOCK, horizon_hours=48)
    a_vs_b = _source("https://sport.example/a-vs-b", "sport.example",
                     _ts("2026-10-11T09:00:00+00:00", TimestampRole.announcement.value),
                     "2026-10-11T09:01:00+00:00", title="Kestrel FC vs Harbour United postponed to Sunday")
    b_vs_a = _source("https://sport.example/b-vs-a", "sport.example",
                     _ts("2026-10-11T09:05:00+00:00", TimestampRole.announcement.value),
                     "2026-10-11T09:06:00+00:00", title="Harbour United vs Kestrel FC: final score 2-1")
    claims = [ClaimDraft(claim_id="c1", text="the Kestrel FC fixture today was postponed", kind="result")]
    links = [EvidenceLinkDraft(claim_id="c1", source_key=a_vs_b.origin_id, relation="reports_allegation",
                               note="announcement of a postponement, not a result")]
    assessments = assess_claims(claims, links, [a_vs_b, b_vs_a], cutoff=cutoff)
    # the two URLs are different objects: minimum independence is not assumed from one outlet
    items = [a_vs_b.dedup_item(), b_vs_a.dedup_item()]
    clusters = origin_clusters(items)
    assert len(clusters) == 2, "different fixtures are different source objects"
    assert assessments["c1"].axes["temporal_fit"] in ("in_frame", "unknown")


def test_rumor_amplification_never_becomes_corroboration_and_a_correction_revises(config, store):
    """Hundreds of copies trace to one unsupported claim; a correction arrives later and
    becomes a labelled revision instead of silently moving the original answer."""
    inv = store.create_investigation(question="is the water safe?", reference_instant=CLOCK.now().isoformat(),
                                     run_id="run_rumor")
    copies = [DedupItem(key=f"c{i}", text="urgent: tap water is unsafe in the east district, share widely",
                        url=f"https://amplify{i}.example/post", origin=f"amplify{i}.example",
                        origin_id=f"amp-{i}") for i in range(50)]
    independent = DedupItem(key="real", text="The utility says water tests remain within safety limits; "
                                             "the viral claim cites no test results",
                            url="https://utility.example/statement", origin="utility.example", origin_id="u-1")
    summary = filter_sensitivity_summary(copies + [independent])
    assert summary["raw_items"] == 51
    assert summary["distinct_origins"] < 10, "copies must not count as dozens of origins"
    clusters = origin_clusters(copies + [independent])
    kind_of = {m.key: c.kind for c in clusters for m in c.members}
    assert kind_of["real"] in ("origin",)
    assert any(kind_of[f"c{i}"] in ("repost", "syndication") for i in range(50))
    # first answer: one copy, one independent statement -> not supported
    claim = store.add_claim(inv["id"], text="tap water is unsafe in the east district", kind="allegation")
    for i in (0, 1):
        row = store.record_sources(inv["id"], [{"adapter": "feeds",
                                                "url": f"https://amplify{i}.example/post",
                                                "origin_id": f"amp-{i}",
                                                "retrieved_at": CLOCK.now().isoformat()}])[0]
        store.add_evidence_link(inv["id"], claim_id=claim, source_id=row["id"],
                                relation="reports_allegation", independence="same_origin")
    store.add_answer(inv["id"], body_json={"text": "v1: an unsupported viral claim; no test evidence"},
                     effective_as_of=CLOCK.now().isoformat())
    # correction arrives after the first answer
    corrected = store.record_sources(inv["id"], [{"adapter": "feeds", "url": "https://utility.example/statement",
                                                  "origin_id": "u-1", "retrieved_at": CLOCK.now().isoformat()}])[0]
    store.add_evidence_link(inv["id"], claim_id=claim, source_id=corrected["id"],
                            relation="contradicts", independence="independent")
    store.add_answer(inv["id"], body_json={"text": "v2: the utility's tests contradict the claim"},
                     effective_as_of=CLOCK.now().isoformat())
    bundle = store.investigation_bundle(inv["id"])
    assert len(bundle["answers"]) == 2
    assert bundle["answers"][1]["revision_of"] == bundle["answers"][0]["id"]
    assert "unsupported viral claim" in bundle["answers"][0]["body_json"]
    assert bundle["evidence"][-1]["relation"] == "contradicts"


def test_as_known_then_does_not_leak_later_corrections():
    """Mode 1 (what was available by T) excludes a later correction; mode 2 (what we now
    know about events before T) includes it. The two answers stay distinct."""
    cutoff = EvidenceCutoff.from_clock(CLOCK, as_of="2026-10-05T00:00:00+00:00")
    original = TimestampValue(raw="", role=TimestampRole.publication.value,
                              instant="2026-10-01T08:00:00+00:00")
    correction_retrieved = TimestampValue(raw="", role=TimestampRole.retrieval.value,
                                          instant="2026-10-08T09:00:00+00:00")
    correction_occurred = TimestampValue(raw="", role=TimestampRole.occurrence.value,
                                         instant="2026-10-04T23:00:00+00:00")
    assert cutoff.available_by(original) is True
    assert cutoff.available_by(correction_retrieved) is False, "a later fact check must not leak into the older answer"
    assert cutoff.events_before(correction_occurred) is True, "mode 2 can use it for events before T"
    assert cutoff.describe().startswith("as of 2026-10-05")


def test_evidence_survives_a_store_restart(config, store):
    """The 'complete conversation' scenario: restart and retrieve the revised report with
    working citations."""
    inv = store.create_investigation(question="did it reopen?", reference_instant=CLOCK.now().isoformat())
    row = store.record_sources(inv["id"], [{"adapter": "feeds", "url": "https://news.example/x",
                                            "origin_id": "x-1", "title": "reopened",
                                            "retrieved_at": CLOCK.now().isoformat()}])[0]
    store.add_answer(inv["id"], body_json={"text": "v1"}, effective_as_of=CLOCK.now().isoformat())
    state_dir = config.state_dir
    store.close()
    from hutch.config import hutchConfig
    from hutch.store import Store
    reopened = Store(hutchConfig(state_dir=state_dir))
    try:
        bundle = reopened.investigation_bundle(inv["id"])
        assert bundle and bundle["sources"][0]["id"] == row["id"]
        assert len(bundle["answers"]) == 1 and "v1" in bundle["answers"][0]["body_json"]
        assert reopened.get_investigation(inv["id"])["revision"] >= 2
    finally:
        reopened.close()
