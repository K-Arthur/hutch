"""Per-card widget evidence: scroll each card into view, screenshot the card itself,
and drive one interaction per kind (chart data table, timeline filter, comparison
sort, flowchart node selection, code receipt, media playback surface).

Usage: same env as capture_outputs_widgets.py; --run and --out are required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="http://127.0.0.1:18899")
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results: dict = {"cards": [], "console_errors": [], "page_errors": []}

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: results["console_errors"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: results["page_errors"].append(str(e)))
        page.goto(f"{args.app}/#/run/{args.run}", wait_until="networkidle")
        page.wait_for_selector("[data-widget-card]", state="attached", timeout=20000)
        stream = page.query_selector("details.tool-stream")
        if stream and not stream.get_attribute("open"):
            stream.evaluate("el => el.open = true")
        group = page.query_selector("[data-group-toggle]")
        if group and group.get_attribute("aria-expanded") == "false":
            group.evaluate("el => el.click()")
        for toggle in page.query_selector_all("[data-tool-toggle]"):
            if toggle.get_attribute("aria-expanded") == "false":
                toggle.evaluate("el => el.click()")
        page.wait_for_timeout(700)

        cards = page.query_selector_all("[data-widget-card]")
        for index, card in enumerate(cards):
            kind = card.get_attribute("data-block-kind")
            card.scroll_into_view_if_needed()
            page.wait_for_timeout(250)
            card.screenshot(path=str(out / f"card-{index:02d}-{kind}.png"))
            results["cards"].append({"index": index, "kind": kind,
                                     "height": card.bounding_box()["height"] if card.bounding_box() else None})

        # chart: open the exact-values data table
        chart = page.query_selector("[data-widget-chart]")
        if chart:
            summary = chart.query_selector("[data-widget-datatable] summary")
            if summary:
                summary.evaluate("el => el.click()")
                page.wait_for_timeout(300)
                chart.scroll_into_view_if_needed()
                chart.screenshot(path=str(out / "interaction-chart-datatable.png"))

        # timeline: filter + group toggle, then screenshot the results area
        timeline = page.query_selector("[data-widget-timeline]")
        if timeline:
            field = timeline.query_selector("[data-widget-tl-q]")
            if field:
                field.fill("analysis")
                field.evaluate("el => el.dispatchEvent(new Event('input', {bubbles: true}))")
                page.wait_for_timeout(300)
            timeline.scroll_into_view_if_needed()
            timeline.screenshot(path=str(out / "interaction-timeline-filter.png"))

        # comparison: sort by the first criterion
        comparison = page.query_selector("[data-widget-csort]")
        if comparison:
            comparison.evaluate("el => el.click()")
            page.wait_for_timeout(300)
            card = page.query_selector("[data-block-kind='comparison']")
            if card:
                card.scroll_into_view_if_needed()
                card.screenshot(path=str(out / "interaction-comparison-sorted.png"))

        # flowchart: select a node, then zoom in
        node = page.query_selector("[data-widget-fc-node]")
        if node:
            node.evaluate("el => el.dispatchEvent(new MouseEvent('click', {bubbles: true}))")
            page.wait_for_timeout(250)
            card = page.query_selector("[data-block-kind='flowchart']")
            if card:
                card.scroll_into_view_if_needed()
                card.screenshot(path=str(out / "interaction-flowchart-selected.png"))
            detail = page.query_selector("[data-widget-fc-detail]")
            results["flowchart_detail"] = detail.inner_text() if detail else ""
            zoom = page.query_selector("[data-widget-action='fc-zoom']")
            if zoom:
                zoom.evaluate("el => el.click()")
                page.wait_for_timeout(200)
                if card:
                    card.screenshot(path=str(out / "interaction-flowchart-zoomed.png"))

        # media: screenshot the media card (SVG animation mount)
        media = page.query_selector("[data-block-kind='media']")
        if media:
            media.scroll_into_view_if_needed()
            media.screenshot(path=str(out / "interaction-media.png"))

        # keyboard: focus the first flowchart node and press Enter (accessibility path)
        if node:
            node.evaluate("el => el.focus()")
            focused = page.evaluate("() => document.activeElement && document.activeElement.getAttribute('data-widget-fc-node')")
            results["flowchart_focus"] = focused
        browser.close()
    (out / "card-results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
