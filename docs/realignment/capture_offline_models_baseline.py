"""Phase 0 visual baseline for offline and local models.

Runs the real FastAPI app on a real port against a fresh HUTCH_STATE_DIR, creates one
assistant on a real local model, then captures /models, the model switcher, /connections
and the onboarding local-service step with Playwright Chromium at four widths and both
themes. Also drives the onboarding wizard once so the local-service page exists.

Usage:
  uv run --frozen --no-sync python docs/realignment/capture_offline_models_baseline.py \
    --label up --out docs/realignment/artifacts/offline-models-2026-11/baseline-up
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

from hutch.models import Bot
from hutch.server.app import create_app

WIDTHS = (360, 768, 1280, 1920)
HEIGHT = 900
# The dashboard is a fixed dark workspace: its linked stylesheets never read
# data-hutch-theme (only the unlinked generated ui.css and overlay tokens do), and
# Settings says so in words. Capture the product's real state instead of a fiction.
THEMES = ("dark",)


def start_app(state_dir: str) -> tuple[object, str, threading.Thread, uvicorn.Server]:
    os.environ["HUTCH_STATE_DIR"] = state_dir
    os.environ["HUTCH_MAX_CONCURRENT"] = "2"
    app = create_app()
    app.state.store.create_bot(Bot(name="baseline", display_name="Baseline", model="ollama/qwen3:0.6b", tools=[]))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("local Hutch server did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    return app, f"http://127.0.0.1:{port}", thread, server


def apply_theme(page, theme: str) -> None:
    page.evaluate("theme => document.documentElement.setAttribute('data-hutch-theme', theme)", theme)


def shoot(page, out: Path, name: str, theme: str, errors: dict) -> dict:
    apply_theme(page, theme)
    page.wait_for_timeout(150)
    path = out / f"{name}-{theme}.png"
    page.screenshot(path=str(path), full_page=True, animations="disabled")
    metrics = page.evaluate("""() => ({
        title: document.title,
        viewportWidth: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        overflow: document.documentElement.scrollWidth > innerWidth,
        theme: document.documentElement.getAttribute('data-hutch-theme')
    })""")
    metrics.update(name=name, theme=theme, screenshot=str(path),
                   pageErrors=list(errors["page"]), consoleErrors=list(errors["console"]))
    errors["page"].clear()
    errors["console"].clear()
    return metrics


def capture_surface(browser, base: str, path: str, out: Path, label: str, *, open_switcher: bool = False) -> list[dict]:
    records = []
    for width in WIDTHS:
        for theme in THEMES:
            context = browser.new_context(viewport={"width": width, "height": HEIGHT}, reduced_motion="reduce")
            page = context.new_page()
            errors = {"page": [], "console": []}
            page.on("pageerror", lambda exc: errors["page"].append(str(exc)))
            page.on("console", lambda msg: errors["console"].append(msg.text) if msg.type == "error" else None)
            response = page.goto(base + path, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(700)
            if open_switcher:
                try:
                    page.locator(".ms-btn").click(timeout=5_000)
                    page.wait_for_timeout(300)
                except Exception:
                    errors["page"].append("model switcher did not open")
            record = shoot(page, out, f"{label}-{width}", theme, errors)
            record.update(path=path, httpStatus=response.status if response else None, width=width)
            records.append(record)
            context.close()
    return records


def drive_onboarding(browser, base: str) -> None:
    """Walk the real wizard to the local-service step; it refuses direct entry without setup state."""
    context = browser.new_context(viewport={"width": 1280, "height": HEIGHT}, reduced_motion="reduce")
    page = context.new_page()
    page.goto(base + "/onboarding", wait_until="domcontentloaded", timeout=30_000)
    page.fill("textarea[name=request]", "Check the local model setup on this machine.")
    page.click("button[type=submit]")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(500)
    if "/onboarding/ai-service" not in page.url:
        page.goto(base + "/onboarding/ai-service", wait_until="domcontentloaded")
    page.check('input[name="route_kind"][value="local_service"]')
    page.click("button[type=submit]")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(500)
    context.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="up or down: the state of the real Ollama server")
    parser.add_argument("--out", required=True)
    parser.add_argument("--state", default="")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    state_dir = args.state or tempfile.mkdtemp(prefix="hutch-offline-baseline-")
    app, base, thread, server = start_app(state_dir)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            records: list[dict] = []
            records += capture_surface(browser, base, "/onboarding", out, f"{args.label}-onboarding")
            records += capture_surface(browser, base, "/models", out, f"{args.label}-models")
            records += capture_surface(browser, base, "/#/chat/baseline", out, f"{args.label}-switcher",
                                       open_switcher=True)
            records += capture_surface(browser, base, "/#/connections", out, f"{args.label}-connections")
            drive_onboarding(browser, base)
            records += capture_surface(browser, base, "/onboarding/local-service", out,
                                       f"{args.label}-local-service")
            browser_version = browser.version
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    report = {"label": args.label, "base": base, "stateDir": state_dir, "browser": "Chromium",
              "browserVersion": browser_version, "screenshots": records,
              "overflow": [r["screenshot"] for r in records if r["overflow"]],
              "errors": [r["screenshot"] for r in records if r["pageErrors"] or r["consoleErrors"]]}
    (out / "capture-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"label": args.label, "captured": len(records),
                      "overflow": report["overflow"], "errors": report["errors"]}, indent=2))


if __name__ == "__main__":
    main()
