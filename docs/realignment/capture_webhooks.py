"""Capture Phase 3 webhooks evidence against a live local Hutch server.

Seeds a temporary state directory with a bot, a webhook source, and deliveries,
serves the real app on loopback, and captures the webhooks surface at
360/768/1280/1920 px in dark and light, plus the opened deliveries log at
1280 and 1920. Writes screenshots and report.json under the Phase 3 evidence dir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
from playwright.async_api import Page, async_playwright

WIDTHS = ((360, 800), (768, 1024), (1280, 800), (1920, 1080))
DELIVERIES_WIDTHS = ((1280, 800), (1920, 1080))
SCHEMES = ("dark", "light")
DEFAULT_OUT = Path("docs/research/2026-11-personal-ops-workflows/artifacts/phase3")


def seed(store: Any) -> None:
    from hutch.models import Bot
    from hutch.webhook_receiver import admit_webhook
    from hutch.webhook_store import create_webhook_source

    bot = store.create_bot(Bot(name="deploy-agent", display_name="Deploy Agent", tools=[]))
    source, token = create_webhook_source(
        store,
        bot_id=bot.id,
        name="Production Webhook",
        prompt_template="Deploy requested: {payload}",
        cooldown_seconds=0.0,
        max_per_hour=60,
    )
    admit_webhook(
        store,
        token,
        b'{"action": "deploy", "env": "prod"}',
        "application/json",
        idempotency_key="seed_deploy_1",
    )
    # duplicate delivery
    admit_webhook(
        store,
        token,
        b'{"action": "deploy", "env": "prod"}',
        "application/json",
        idempotency_key="seed_deploy_1",
    )


class ServerThread:
    def __init__(self, app: Any, host: str = "127.0.0.1", port: int = 0):
        self.app = app
        self.host = host
        self.port = port
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> str:
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.server.serve())

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        while not self.server.started:
            time.sleep(0.02)
        assert self.server.servers
        for s in self.server.servers:
            for sock in s.sockets:
                self.port = sock.getsockname()[1]
                break
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=5)


async def check_overflow(page: Page) -> int:
    return await page.evaluate(
        "Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth)"
    )


async def capture_all(base_url: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"base_url": base_url, "captures": []}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        # 1. Default views across 4 widths x 2 themes
        for width, height in WIDTHS:
            for scheme in SCHEMES:
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                    color_scheme=scheme,
                    reduced_motion="reduce",
                )
                page = await context.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda err: errors.append(str(err)))

                await page.goto(f"{base_url}/#/schedules", wait_until="domcontentloaded")
                if scheme == "light":
                    await page.evaluate("document.documentElement.dataset.hutchTheme = 'light'")

                await page.locator(".webhook-management-section").wait_for(timeout=20_000)
                await page.locator(".webhook-source-card").first.wait_for(timeout=20_000)
                await asyncio.sleep(0.2)

                overflow = await check_overflow(page)
                shot_name = f"webhooks-default-{width}-{scheme}.png"
                shot_path = out_dir / shot_name
                await page.screenshot(path=str(shot_path), full_page=True)

                report["captures"].append({
                    "view": "default",
                    "width": width,
                    "height": height,
                    "scheme": scheme,
                    "overflow": overflow,
                    "errors": errors,
                    "file": shot_name,
                })
                await context.close()

        # 2. Deliveries opened at 1280 and 1920
        for width, height in DELIVERIES_WIDTHS:
            for scheme in SCHEMES:
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                    color_scheme=scheme,
                    reduced_motion="reduce",
                )
                page = await context.new_page()
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))

                await page.goto(f"{base_url}/#/schedules", wait_until="domcontentloaded")
                if scheme == "light":
                    await page.evaluate("document.documentElement.dataset.hutchTheme = 'light'")

                await page.locator(".webhook-management-section").wait_for(timeout=20_000)
                card = page.locator(".webhook-source-card").first
                await card.wait_for(timeout=20_000)
                await card.locator(".webhook-deliveries-details summary").click()
                await card.locator(".webhook-delivery-item").first.wait_for(timeout=20_000)
                await asyncio.sleep(0.2)

                overflow = await check_overflow(page)
                shot_name = f"webhooks-deliveries-{width}-{scheme}.png"
                shot_path = out_dir / shot_name
                await page.screenshot(path=str(shot_path), full_page=True)

                report["captures"].append({
                    "view": "deliveries",
                    "width": width,
                    "height": height,
                    "scheme": scheme,
                    "overflow": overflow,
                    "errors": errors,
                    "file": shot_name,
                })
                await context.close()

        await browser.close()

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="hutch-capture-webhooks-") as state_dir:
        os.environ["HUTCH_STATE_DIR"] = state_dir
        from hutch.server.app import create_app

        app = create_app()
        seed(app.state.store)
        server = ServerThread(app)
        base_url = server.start()
        try:
            report = asyncio.run(capture_all(base_url, args.out))
            print(f"Captured {len(report['captures'])} views into {args.out}")
        finally:
            server.stop()


if __name__ == "__main__":
    main()
