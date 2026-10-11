"""Capture the typed-output widgets on a real run: seed real tool results, screenshot.

Usage (root venv has Playwright; PYTHONPATH points at this worktree's src)::

    PYTHONPATH=$PWD/src python docs/realignment/capture_outputs_widgets.py \
        --state /tmp/hutch-outputs-visual --port 18899 \
        --out docs/realignment/artifacts/outputs-widgets

Seeds one conversation/run whose tool events come from the REAL tools (contained
run_python with emit_block, render_diagram, create_media animation), then drives a
real Chromium through the run page at 1440/900/390 CSS pixels, exercising chart
hover, the data table toggle, timeline filters, comparison sort, flowchart
selection/zoom, and the code-receipt copy button. Console errors, page errors and
horizontal overflow are recorded per viewport.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

VIEWPORTS = {"desktop": (1440, 1000), "tablet": (900, 1024), "phone": (390, 844)}

CHART_CELL = """
import math
hours = list(range(24))
grid = [120 + 60 * math.sin(h / 3.4) + 8 * (h % 5) for h in hours]
solar = [max(0.0, 260 * math.sin((h - 5) / 14 * math.pi)) for h in hours]
emit_block("chart", {
    "kind": "line",
    "series": [{"label": "grid draw", "points": [[h, round(v, 1)] for h, v in zip(hours, grid)]},
               {"label": "solar", "points": [[h, round(v, 1)] for h, v in zip(hours, solar)]}],
    "x": {"label": "hour of day", "unit": "h", "scale": "linear"},
    "y": {"label": "kilowatts", "scale": "linear"},
    "source": "executed",
    "notes": "One day of a deterministic simulation; values are computed, not estimated.",
}, "Line chart: hourly grid draw and solar output over one simulated day.")
emit_block("table", {
    "columns": [{"name": "hour", "dtype": "number"}, {"name": "grid_kw", "dtype": "number"},
                {"name": "solar_kw", "dtype": "number"}],
    "rows": [[h, round(g, 1), round(s, 1)] for h, g, s in list(zip(hours, grid, solar))[:8]],
    "row_total": 24,
    "truncation": {"omitted_rows": 16, "reason": "preview shows the first 8 of 24 hours"},
    "notes": "Computed by the workspace kernel; the full 24 rows stay in the kernel namespace.",
}, "Table preview: hour, grid kilowatts, solar kilowatts.")
emit_block("timeline", {
    "events": [
        {"id": "e1", "label": "Load test requested", "when": {"iso8601": "2026-10-10T09:00:00+00:00",
         "precision": "second", "timezone": "UTC"}, "state": "confirmed", "source": "chat"},
        {"id": "e2", "label": "Fixture data prepared", "when": {"iso8601": "2026-10-10T09:12:00+00:00",
         "precision": "minute"}, "state": "confirmed"},
        {"id": "e3", "label": "Analysis run (corrected start)", "when": {"iso8601": "2026-10-10T09:20:00+00:00",
         "precision": "minute"}, "state": "corrected", "corrected_from": "e2"},
        {"id": "e4", "label": "Publish report", "when": {"iso8601": "2026-10-11", "precision": "day"},
         "state": "planned"},
        {"id": "e5", "label": "Owner reported a discrepancy", "when": {"iso8601": "2026-10-10T10:02:00+00:00",
         "precision": "minute"}, "state": "reported"},
    ]}, "Timeline: load test requested, data prepared, analysis run, report planned, discrepancy reported.")
emit_block("comparison", {
    "items": [{"id": "local", "label": "Local contained kernel"},
              {"id": "cloud", "label": "Hosted notebook service"}],
    "criteria": [{"id": "cost", "label": "Monthly cost", "unit": "USD"},
                 {"id": "offline", "label": "Works offline"},
                 {"id": "data", "label": "Data leaves the machine"}],
    "cells": [
        {"item": "local", "criterion": "cost", "value": "0", "citations": "this machine"},
        {"item": "cloud", "criterion": "cost", "value": "24"},
        {"item": "local", "criterion": "offline", "value": "yes"},
        {"item": "cloud", "criterion": "offline", "state": "unsupported"},
        {"item": "local", "criterion": "data", "value": "never"},
        {"item": "cloud", "criterion": "data", "value": "sent to the provider"},
    ],
    "ranking_note": "Unknown values are shown as unknown; no guess is filled in.",
}, "Comparison of a local kernel and a hosted notebook across cost, offline use, and data movement.")
print("emitted chart, table, timeline, comparison")
"""

RECEIPT_CELL = """
import csv
with open("out/energy.csv", "w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["hour", "kilowatts"])
    writer.writerows([[h, round(120 + 60 * __import__("math").sin(h / 3.4), 1)] for h in range(24)])
print("wrote out/energy.csv")
"""


def seed(state_dir: Path) -> tuple[str, str]:
    from hutch.config import get_config
    from hutch.store import Store
    from hutch.models import ApprovalMode, Bot, Run, RunStatus
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine
    from hutch.tools import build_tools
    from hutch.tools.base import ToolContext
    from hutch.runtime.steps import call_tool

    os.environ["HUTCH_STATE_DIR"] = str(state_dir)
    os.environ["HUTCH_SANDBOX"] = "strict"
    from hutch import sandbox
    sandbox.reset_cache()
    config = get_config()
    store = Store(config)
    bot = store.create_bot(Bot(name="visual-outputs", display_name="Outputs review",
                               model="mock/demo", tools=["media", "workspace"],
                               approval_mode=ApprovalMode.auto, sandbox="strict"))
    conversation, _ = store.create_conversation(bot.id, "Typed outputs", idem_key="visual-1",
                                                request_hash="h")
    run = store.create_run(Run(bot_id=bot.id, prompt="Show the typed outputs",
                               status=RunStatus.running, conversation_id=conversation["id"]))
    workspace = config.run_dir(bot.name, run.id) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    emit = lambda ev: store.append_event(ev)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=config, workspace=workspace, emit=emit)
    tools = build_tools(["run_python", "render_diagram", "create_media"], ctx)
    call_tool(run, ctx, tools, "run_python", {"code": CHART_CELL, "timeout_seconds": 60})
    call_tool(run, ctx, tools, "run_python", {"code": RECEIPT_CELL, "timeout_seconds": 60})
    call_tool(run, ctx, tools, "render_diagram", {
        "title": "Nightly analysis pipeline with a retry loop",
        "nodes": [
            {"id": "collect", "label": "Collect authorized inputs", "group": "ingest"},
            {"id": "validate", "label": "Validate schema and quoting", "group": "ingest",
             "detail": "Rejects ragged rows with their line numbers instead of repairing them."},
            {"id": "analyze", "label": "Execute analysis in the contained kernel", "group": "compute"},
            {"id": "render", "label": "Render chart and table blocks", "group": "publish"},
            {"id": "publish", "label": "Publish verified report", "group": "publish"},
        ],
        "edges": [
            {"from": "collect", "to": "validate"},
            {"from": "validate", "to": "analyze", "label": "schema ok"},
            {"from": "analyze", "to": "render"},
            {"from": "render", "to": "publish"},
            {"from": "validate", "to": "collect", "label": "needs more data"},
            {"from": "publish", "to": "analyze", "label": "revise aggregation"},
        ],
        "direction": "LR",
        "assumptions_note": "The retry loop assumes the owner approves re-running the analysis.",
    })
    call_tool(run, ctx, tools, "create_media", {
        "kind": "animation", "prompt": "Power draw through the day",
        "seconds": 2.0, "width": 480, "height": 270,
        "frames": [{"label": "00:00", "duration_seconds": 0.5, "detail": "baseline"},
                   {"label": "06:00", "duration_seconds": 0.5, "detail": "morning ramp"},
                   {"label": "12:00", "duration_seconds": 0.5, "detail": "peak"},
                   {"label": "18:00", "duration_seconds": 0.5, "detail": "evening fall"}],
    })
    store.set_status(run, RunStatus.succeeded, event={"reason": "complete"})
    store.close()
    return conversation["id"], run.id


def capture(app_url: str, out_dir: Path, run_id: str) -> dict:
    from playwright.sync_api import sync_playwright

    results: dict = {"viewports": {}, "console_errors": [], "page_errors": []}
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (width, height) in VIEWPORTS.items():
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("console", lambda msg: results["console_errors"].append(f"{name}: {msg.text}")
                    if msg.type == "error" else None)
            page.on("pageerror", lambda exc: results["page_errors"].append(f"{name}: {exc}"))
            page.goto(f"{app_url}/#/run/{run_id}", wait_until="networkidle")
            page.wait_for_selector("[data-widget-card]", state="attached", timeout=20000)
            # Finished runs with 4+ steps collapse the tool stream behind a summary.
            stream = page.query_selector("details.tool-stream")
            if stream and not stream.get_attribute("open"):
                stream.evaluate("el => el.open = true")
            # 4+ consecutive tool calls also collapse into a group row.
            group = page.query_selector("[data-group-toggle]")
            if group and group.get_attribute("aria-expanded") == "false":
                group.evaluate("el => el.click()")
            # Expand the tool lines so every card is on screen, then let the feed settle.
            for toggle in page.query_selector_all("[data-tool-toggle]"):
                if toggle.get_attribute("aria-expanded") == "false":
                    toggle.evaluate("el => el.click()")
            page.wait_for_timeout(900)
            debug = page.evaluate("""() => {
                const card = document.querySelector('[data-widget-card]');
                const style = card ? getComputedStyle(card) : null;
                return {cards: document.querySelectorAll('[data-widget-card]').length,
                        display: style && style.display, visibility: style && style.visibility,
                        rect: card ? JSON.parse(JSON.stringify(card.getBoundingClientRect())) : null};
            }""")
            page.screenshot(path=str(out_dir / f"run-{name}.png"), full_page=True)
            overflow = page.evaluate(
                "() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
            cards = page.eval_on_selector_all("[data-widget-card]",
                                              "els => els.map(e => e.dataset.blockKind)")
            results["viewports"][name] = {"width": width, "height": height,
                                          "scroll_width": overflow["sw"], "client_width": overflow["cw"],
                                          "block_kinds": cards, "debug": debug}
            if name == "desktop":
                chart = page.locator("[data-widget-chart]").first
                if chart.count():
                    chart.hover()
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(out_dir / "chart-hover.png"))
                    page.locator("[data-widget-datatable] summary").first.click()
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(out_dir / "chart-data-table.png"))
                timeline = page.locator("[data-widget-tl-q]").first
                if timeline.count():
                    timeline.fill("analysis")
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(out_dir / "timeline-filter.png"))
                node = page.locator("[data-widget-fc-node]").first
                if node.count():
                    node.click()
                    page.wait_for_timeout(200)
                    page.screenshot(path=str(out_dir / "flowchart-selected.png"))
                receipt = page.locator("[data-widget-code]").first
                if receipt.count():
                    receipt.scroll_into_view_if_needed()
                    page.screenshot(path=str(out_dir / "code-receipt.png"))
            page.close()
        browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--port", type=int, default=18899)
    parser.add_argument("--out", required=True)
    parser.add_argument("--keep-state", action="store_true")
    args = parser.parse_args()
    state = Path(args.state)
    if state.exists() and not args.keep_state:
        shutil.rmtree(state)
    state.mkdir(parents=True, exist_ok=True)
    conversation_id, run_id = seed(state)
    print(f"seeded conversation {conversation_id} run {run_id} in {state}")
    env = dict(os.environ, HUTCH_STATE_DIR=str(state))
    server = subprocess.Popen(
        [sys.executable, "-m", "hutch.cli", "serve", "--host", "127.0.0.1", "--port", str(args.port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 30
        import urllib.request
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        else:
            raise SystemExit("server did not become healthy")
        results = capture(f"http://127.0.0.1:{args.port}", Path(args.out), run_id)
        (Path(args.out) / "capture-results.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2)[:2000])
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
