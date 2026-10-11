"""Deduplication, origin clusters, independence, and explainable noise indicators."""

from __future__ import annotations

from hutch.grounding.dedup import (
    DedupItem, content_hash, filter_sensitivity_summary, group_duplicates, independence_for,
    noise_signals, origin_clusters, simhash64,
)


def item(key, text="", url="", origin="", origin_id="", published=None, labels=()):
    return DedupItem(key=key, text=text, url=url, origin=origin, origin_id=origin_id,
                     published_instant=published, labels=tuple(labels))


def test_exact_and_near_duplicates_group_and_retain_differences():
    shared = "BREAKING: the harbour bridge is closed after a truck incident, avoid the area"
    items = [
        item("a", shared + " #1", origin="acct-a", published="2026-10-11T08:00:00+00:00"),
        item("b", shared + " #2", origin="acct-b", published="2026-10-11T08:01:00+00:00"),
        item("c", "Rumour debunked: the harbour bridge is NOT closed; traffic is normal",
             origin="acct-c", published="2026-10-11T09:00:00+00:00"),
    ]
    groups = group_duplicates(items)
    members = {m for g in groups for m in g.members}
    assert "a" in members and "b" in members
    # a negation is a different statement; near-duplicate hashing on short text must not merge it
    assert not any(set(g.members) == {"a", "b", "c"} for g in groups)
    assert content_hash(items[0].text) != content_hash(items[2].text)
    assert simhash64(shared + " #1") != 0


def test_same_object_retrieved_twice_is_one_mirror_cluster():
    items = [item("a", "same post", url="https://mirror-1.example/post/1", origin="acct", origin_id="post-1"),
             item("b", "same post", url="https://mirror-2.example/copy/9", origin="acct", origin_id="post-1")]
    clusters = origin_clusters(items)
    assert len(clusters) == 1 and clusters[0].kind == "mirror"
    assert clusters[0].distinct_origins == 1
    independence = independence_for(items)
    assert independence == {"a": "same_origin", "b": "same_origin"}


def test_one_origin_posting_near_copies_is_a_repost_cluster_not_corroboration():
    text = "urgent: water is unsafe to drink in the east district until further notice"
    items = [item("p1", text + " please share", url="https://x.example/1", origin="alertfeed", origin_id="1"),
             item("p2", text + " share widely", url="https://x.example/2", origin="alertfeed", origin_id="2"),
             item("p3", text + " retweet", url="https://x.example/3", origin="alertfeed", origin_id="3")]
    clusters = origin_clusters(items)
    assert len(clusters) == 1 and clusters[0].kind == "repost" and len(clusters[0].members) == 3


def test_a_headline_on_many_domains_counts_as_one_syndicated_origin():
    headline = "City council approves the new transit plan"
    items = [item(f"d{i}", headline, url=f"https://outlet{i}.example/story", origin=f"outlet{i}.example",
                  origin_id=f"s{i}") for i in range(4)]
    clusters = origin_clusters(items, headline_share_min=3)
    assert len(clusters) == 1 and clusters[0].kind == "syndication"
    summary = filter_sensitivity_summary(items)
    assert summary["distinct_origins"] == 1 and summary["raw_items"] == 4


def test_distinct_reporting_stays_independent():
    items = [
        item("r1", "The ministry confirmed the bridge reopened at noon after inspections",
             url="https://alpha.example/a", origin="alpha.example", origin_id="a1"),
        item("r2", "Engineers finished a second inspection of the harbour bridge before reopening",
             url="https://beta.example/b", origin="beta.example", origin_id="b1"),
    ]
    clusters = origin_clusters(items)
    assert len(clusters) == 2 and all(c.kind == "origin" for c in clusters)
    assert set(independence_for(items).values()) == {"independent"}


def test_noise_signals_are_explainable_and_never_label_a_person():
    text = "shared alert text about a road closure"
    items = [
        item("x1", text, url="https://s.example/1", origin="roadwatch", origin_id="1",
             published="2026-10-11T08:00:00+00:00", labels=("automated",)),
        item("x2", text, url="https://s.example/2", origin="roadwatch", origin_id="2",
             published="2026-10-11T08:00:20+00:00"),
        item("x3", text, url="https://s.example/3", origin="roadwatch", origin_id="3",
             published="2026-10-11T08:00:40+00:00"),
        item("x4", text, url="https://s.example/4", origin="roadwatch", origin_id="4",
             published="2026-10-11T08:00:50+00:00"),
        item("x5", text, url="https://s.example/5", origin="roadwatch", origin_id="5",
             published="2026-10-11T08:00:55+00:00"),
        item("x6", "https://link.example/only", origin="someone"),
    ]
    signals = noise_signals(items)
    reasons = {s.reason for values in signals.values() for s in values}
    assert "duplicate_text" in reasons
    assert "declared_automation" in reasons       # only because the platform metadata says so
    assert "synchronized_burst" in reasons
    assert any(s.reason == "link_only" for s in signals["x6"])
    assert all(s.action == "downrank" for s in signals["x6"])
    for sig_list in signals.values():
        for sig in sig_list:
            assert sig.evidence, "every signal must carry its evidence"
            assert sig.action in ("group", "downrank")
    # no signal may claim anything about who the account is
    assert not any("bot" in s.reason for lst in signals.values() for s in lst)


def test_bounded_grouping_reports_what_it_did_not_compare():
    items = [item(f"i{i}", f"unique text number {i}") for i in range(8)]
    groups = group_duplicates(items, max_items=4)
    assert any("not compared" in g.note for g in groups if g.representative == "")
