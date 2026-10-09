"""Capture the dashboard tool-row and meter styles at three viewports.

Run against a loopback Hutch server. The page content is an explicitly synthetic
style fixture; the stylesheet itself is served by Hutch. No bot, provider, or
personal workspace state is required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


DEFAULT_OUT = Path(__file__).parent / "artifacts" / "ui-style-review"
VIEWPORTS = {
    "desktop": (1440, 1000),
    "tablet": (900, 1024),
    "phone": (390, 844),
}


def fixture(css_url: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="{css_url}">
<title>Hutch dashboard style review</title></head><body>
<main class="container">
  <header class="page-head">
    <div><span class="crumb">Studio / run</span><h1>Review the run</h1>
      <p class="sub">Synthetic visual fixture using the dashboard stylesheet.</p></div>
    <span class="chip st-running">working</span>
  </header>
  <section class="meters">
    <article class="meter"><div class="meter-top"><span class="meter-label">Budget used</span>
      <strong class="meter-val">72%</strong></div>
      <div class="bar" role="progressbar" aria-label="Budget used" aria-valuemin="0"
        aria-valuemax="100" aria-valuenow="72"><i style="width:72%"></i></div>
      <p class="meter-note">Measured and reserved usage</p>
    </article>
  </section>
  <section class="transcript"><div class="tx-head"><strong class="tx-title">Tool activity</strong>
    <span class="muted">3 steps</span></div>
    <ul class="tx-list">
      <li class="tx"><details class="toolline call"><summary><strong>read_file</strong>
        <span class="argsum">/workspace/brief.md</span><time>just now</time></summary>
        <pre>Read a brief</pre></details></li>
      <li class="tx"><details class="toolline result ok"><summary><strong>result</strong>
        <span class="argsum">Read complete</span><time>verified</time></summary>
        <pre>Read complete</pre></details></li>
      <li class="tx"><details class="toolline result bad"><summary><strong>result</strong>
        <span class="argsum">Permission denied</span><time>blocked</time></summary>
        <pre>Blocked by policy</pre></details></li>
    </ul>
  </section>
</main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="http://127.0.0.1:18803/")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    css_url = args.app.rstrip("/") + "/static/hutch.css"
    html = fixture(css_url)
    records = []
    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(headless=True)
        for name, (width, height) in VIEWPORTS.items():
            context = browser.new_context(
                viewport={"width": width, "height": height},
                reduced_motion="reduce",
            )
            if name == "desktop":
                context.tracing.start(screenshots=True, snapshots=True, sources=False)
            page = context.new_page()
            errors: list[str] = []
            stylesheet_status: list[int] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "response",
                lambda response: stylesheet_status.append(response.status)
                if response.url == css_url
                else None,
            )
            page.set_content(html, wait_until="networkidle")
            page.locator(".transcript").wait_for()
            page.screenshot(
                path=str(args.output / f"{name}.png"),
                full_page=True,
                animations="disabled",
            )
            metrics = page.locator(".transcript").evaluate(
                """el => {
                  const tool = el.querySelector('.toolline');
                  const fill = document.querySelector('.bar i');
                  const bar = fill.parentElement;
                  const fillStyle = getComputedStyle(fill);
                  return {
                    viewportWidth: innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    transcriptBorder: getComputedStyle(el).borderWidth,
                    toollineLeftBorder: getComputedStyle(tool).borderLeftWidth,
                    toollineIndent: getComputedStyle(tool).paddingLeft,
                    barTransition: fillStyle.transition,
                    barFillRatio: Math.round(fill.getBoundingClientRect().width / bar.getBoundingClientRect().width * 100),
                  };
                }"""
            )
            record = {
                "viewport": name,
                "pageErrors": errors,
                "stylesheetStatus": stylesheet_status,
                **metrics,
            }
            records.append(record)
            if (
                stylesheet_status != [200]
                or errors
                or metrics["documentWidth"] != width
                or metrics["toollineLeftBorder"] != "0px"
                or metrics["toollineIndent"] != "10px"
                or metrics["barTransition"] != "none"
                or metrics["barFillRatio"] != 72
            ):
                raise RuntimeError(f"Visual check failed at {name}: {record}")
            if name == "desktop":
                context.tracing.stop(path=str(args.output / "desktop-trace.zip"))
            context.close()
        browser_version = browser.version
        browser.close()

    report = {
        "stylesheet": css_url,
        "browser": "Firefox",
        "browserVersion": browser_version,
        "fixture": "Synthetic budget meter and tool rows rendered with the actual dashboard stylesheet. No production state or provider calls.",
        "screenshots": records,
    }
    (args.output / "results.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
