"""Capture Phase 2 schedules evidence against a live local Hutch server.

Seeds a temporary state directory with three routines (one failed, one waiting for
approval, one healthy), serves the real app on loopback, and captures the schedules
surface at 360/768/1280/1920 px in dark and light, plus the opened history panel at
1280 and 1920. Writes screenshots and report.json under the Phase 2 evidence dir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import uvicorn
from playwright.async_api import Page, async_playwright

WIDTHS = ((360, 800), (768, 1024), (1280, 800), (1920, 1080))
HISTORY_WIDTHS = ((1280, 800), (1920, 1080))
SCHEMES = ("dark", "light")
DEFAULT_OUT = Path("docs/research/2026-11-personal-ops-workflows/artifacts/phase2")


def seed(store: Any) -> None:
    from hutch.engine import Engine
    from hutch.models import Bot, Run, RunStatus, Schedule, iso, utcnow
    from hutch.schedule_policy import put_policy

    now = utcnow()
    failed = store.create_bot(Bot(
        name="release-watch", display_name="Release Watch", tools=[],
        schedule=Schedule(name="Nightly release check", cron="0 3 * * *", timezone="UTC",
                          enabled=False, prompt="Check releases."),
    ))
    store.put_schedule(failed.id, Schedule(
        id=failed.schedule.id, name="Nightly release check", cron="0 4 * * *",
        timezone="UTC", enabled=False, prompt="Check the release feed.",
    ))
    failed_run = store.create_run(Run(
        bot_id=failed.id, prompt="Check releases.", origin="schedule",
        schedule_id=failed.schedule.id, status=RunStatus.failed,
        exit_reason="model_unavailable", missed_windows=1,
        created_at=iso(now - timedelta(hours=1)), finished_at=iso(now - timedelta(hours=1)),
    ))
    with store._tx() as db:
        db.execute(
            "INSERT INTO schedule_occurrences_v20 "
            "(schedule_id, occurrence, bot_id, run_id, claimed_at, claimed_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (failed.schedule.id, iso(now - timedelta(hours=1)), failed.id,
             failed_run.id, iso(now - timedelta(hours=1)), "capture"),
        )

    approval = store.create_bot(Bot(
        name="approval-watch", display_name="Approval Watch", tools=[],
        schedule=Schedule(name="Morning approval check", cron="0 3 * * *", timezone="UTC",
                          prompt="Check the morning queue."),
    ))
    store.kv_set(f"{approval.schedule.id}:last_fire", iso(now - timedelta(days=1)))
    put_policy(store, approval.id, approval.schedule.id, approval_required=True, conditions=[])
    Engine(store.config, store).scheduler_claims()

    healthy = store.create_bot(Bot(
        name="healthy-watch", display_name="Healthy Watch", tools=[],
        schedule=Schedule(name="Healthy routine", cron="0 5 * * *", timezone="UTC",
                          prompt="Check the healthy queue."),
    ))
    store.kv_set(f"{healthy.schedule.id}:last_fire", iso(now))


def serve(app) -> tuple[uvicorn.Server, threading.Thread, str]:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "Hutch server did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, thread, f"http://127.0.0.1:{port}"


async def measure(page: Page) -> dict[str, Any]:
    return await page.evaluate("""() => ({
        title: document.title,
        heading: (document.querySelector('h1') || document.querySelector('h2') || {}).textContent?.trim() || '',
        overflow_x: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
        focusable: document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]').length,
        roll_call: !!document.querySelector('.schedule-roll-call'),
        history_open: !!document.querySelector('.schedule-history-body'),
        theme_attr: document.documentElement.dataset.hutchTheme || '',
        body_background: getComputedStyle(document.body).backgroundColor,
        body_color: getComputedStyle(document.body).color,
    })""")


async def capture_one(browser, origin: str, out: Path, width: int, height: int, scheme: str,
                      *, open_history: bool) -> dict[str, Any]:
    context = await browser.new_context(
        viewport={"width": width, "height": height}, color_scheme=scheme, device_scale_factor=1,
    )
    page = await context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)
    await page.goto(f"{origin}/#/schedules", wait_until="domcontentloaded")
    if scheme == "light":
        # The dashboard ships a fixed dark theme; this exercises the design
        # system's derived light scope so light-surface contrast and layout are
        # still checked. It is not an exposed user toggle.
        await page.evaluate("document.documentElement.dataset.hutchTheme = 'light'")
    await page.locator(".schedule-roll-call").wait_for(timeout=20_000)
    if open_history:
        await page.locator(".schedule-history > summary").first.click()
        await page.locator(".schedule-history-body").first.wait_for(timeout=20_000)
    await page.wait_for_timeout(500)
    suffix = "history" if open_history else "default"
    filename = f"schedules-{suffix}-{width}-{scheme}.png"
    await page.screenshot(path=str(out / filename), full_page=False)
    record = {
        "width": width, "height": height, "scheme": scheme, "state": suffix,
        "screenshot": filename, "console_errors": errors, **await measure(page),
    }
    await context.close()
    return record


async def capture(origin: str, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        browser_version = browser.version
        try:
            for width, height in WIDTHS:
                for scheme in SCHEMES:
                    records.append(await capture_one(browser, origin, out, width, height, scheme,
                                                    open_history=False))
            for width, height in HISTORY_WIDTHS:
                for scheme in SCHEMES:
                    records.append(await capture_one(browser, origin, out, width, height, scheme,
                                                    open_history=True))
        finally:
            await browser.close()
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "browser": browser_version,
        "records": records,
        "bad": [r for r in records if r["console_errors"] or r["overflow_x"] > 0 or not r["roll_call"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Phase 2 schedules evidence.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    os.environ.setdefault("HUTCH_STATE_DIR", tempfile.mkdtemp(prefix="hutch-schedule-capture-"))
    from hutch.server.app import create_app

    app = create_app()
    seed(app.state.store)
    server, thread, origin = serve(app)
    try:
        report = asyncio.run(capture(origin, args.out))
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    report["origin"] = origin
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    bad = report["bad"]
    print(f"Captured {len(report['records'])} views; {len(bad)} with errors, overflow or a missing roll call")
    print(f"Evidence: {args.out / 'report.json'}")


if __name__ == "__main__":
    main()
