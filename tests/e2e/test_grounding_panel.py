"""Real-browser journey for the grounded-evidence panel: entry link, scoped label,
source independence, frame delivery from the API, and revisions — the parts unit tests
cannot see. Skipped automatically when no Playwright browser is installed.
"""

from __future__ import annotations

from tests.e2e.grounding_fixtures import (  # noqa: F401 - the fixtures are the point
    browser, live, open_panel, seed_grounded_run,
)


def test_evidence_panel_shows_scoped_findings_sources_and_frames(browser, live):
    base, _app, state_dir = live
    run_id = seed_grounded_run(state_dir)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    try:
        problems = open_panel(page, base, run_id)
        panel = page.locator("[data-evidence-panel]")
        assert "Evidence" in panel.inner_text()
        # the scoped label, never a universal verdict
        assert "Insufficient evidence" in panel.locator(".evidence-claim-meta").inner_text()
        assert "not a universal verdict" in panel.inner_text()
        # sources carry independence chips as text, not color alone (newest first, so assert on both)
        sources = panel.locator(".evidence-source")
        assert sources.count() == 2
        source_text = panel.inner_text()
        assert "independent origin" in source_text and "same origin" in source_text
        # acquisition outcomes keep the blocked state visible
        assert "blocked" in panel.inner_text()
        # the entry link in the thread points back at this panel
        entry = page.locator(".grounding-entry")
        assert entry.count() == 1 and "focus=evidence" in entry.first.get_attribute("href")
        # the inspected frame is served by the API and actually decodes
        page.evaluate("() => document.querySelectorAll('[data-evidence-panel] details').forEach(d => d.open = true)")
        page.wait_for_timeout(800)
        frame_ok = page.evaluate(
            "() => Array.from(document.querySelectorAll('.evidence-frame img')).every(i => i.complete && i.naturalWidth > 0)")
        assert frame_ok, "the frame image must load from the authenticated API route"
        assert not problems, problems
        assert not page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
    finally:
        page.close()


def test_evidence_panel_refresh_appends_a_revision(browser, live, monkeypatch):
    from hutch.grounding import acquire as acquire_mod

    def fake_feeds(query, cutoff, budget, clock, cfg, stop):
        outcome = acquire_mod.AdapterOutcome(adapter="feeds", lane="feeds", query=query, state="ok",
                                             retained=1, returned=1, freshness="polled")
        source = acquire_mod.FoundSource(adapter="feeds", lane="feeds", platform="web", kind="feed_item",
                                         url="https://news.example/refresh", origin="news.example",
                                         origin_id="https://news.example/refresh", title="Refresh follow-up",
                                         excerpt="New window.", retrieved_at="2026-10-11T20:05:00+00:00")
        return [source], outcome

    monkeypatch.setitem(acquire_mod.ADAPTERS, "feeds", fake_feeds)
    for name in ("gdelt", "hn", "bluesky", "searxng", "jetstream"):
        monkeypatch.setitem(acquire_mod.ADAPTERS, name, lambda q, c, b, cl, cf, s, name=name: (
            [], acquire_mod.AdapterOutcome(adapter=name, lane="?", query=q, state="unavailable")))
    base, _app, state_dir = live
    run_id = seed_grounded_run(state_dir)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    try:
        problems = open_panel(page, base, run_id)
        page.click("[data-evidence-refresh]")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('[data-evidence-panel] summary'))"
            ".some(s => /Answer revisions \\(2\\)/.test(s.textContent))", timeout=20_000)
        panel_text = page.locator("[data-evidence-panel]").inner_text()
        assert "Answer revisions (2)" in panel_text
        assert "Refresh follow-up" in panel_text or "follow-up" in panel_text.lower()
        assert not problems, problems
    finally:
        page.close()


def test_evidence_panel_phone_width_has_no_overflow(browser, live):
    base, _app, state_dir = live
    run_id = seed_grounded_run(state_dir)
    page = browser.new_page(viewport={"width": 360, "height": 800})
    try:
        problems = open_panel(page, base, run_id)
        page.evaluate("() => document.querySelectorAll('[data-evidence-panel] details').forEach(d => d.open = true)")
        page.wait_for_timeout(600)
        assert not page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        assert page.locator("[data-evidence-panel] .evidence-source").count() == 2
        assert not problems, problems
    finally:
        page.close()
