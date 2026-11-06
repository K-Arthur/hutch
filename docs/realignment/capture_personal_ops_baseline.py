"""Capture baseline screenshots for personal ops, shared spaces, schedules, tasks, and catalog.

Runs against a live local Hutch server on an isolated temporary state directory.
Captures viewports: 360x800, 768x1024, 1280x800, 1920x1080 in both dark and light schemes.
Outputs screenshots and a report.json into docs/research/2026-11-personal-ops-workflows/artifacts/phase0/.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

PAGES = (
    ("today", "/#/today"),
    ("shared", "/#/shared"),
    ("schedules", "/#/schedules"),
    ("tasks", "/#/tasks"),
    ("catalog", "/#/catalog"),
)
WIDTHS = (
    (360, 800),
    (768, 1024),
    (1280, 800),
    (1920, 1080),
)
SCHEMES = ("dark", "light")


def seed_test_store(store: Any) -> None:
    """Populate realistic commitments and spaces so Today and Shared render fully."""
    from hutch.personal import Commitment, CompletionKind, Space, SpaceMember, SpaceRole
    from hutch.personal.store import PersonalStore

    personal = PersonalStore(store)
    personal.commitments.create(Commitment(
        title="Pay the water bill",
        detail="Account ending 4417",
        due_at="2026-11-06T17:00:00-07:00",
        due_timezone="America/Vancouver",
        priority="high",
    ))
    reported, _ = personal.commitments.create(Commitment(title="Return the parcel"))
    personal.commitments.complete(
        reported.id,
        evidence="Left at the counter, receipt 2291",
        kind=CompletionKind.unverified,
        actor="assistant",
    )
    personal.commitments.create(Commitment(
        title="Schedule the boiler service",
        created_by="assistant",
        confirmation="proposed",
        source="assistant",
        source_detail="capture_commitment",
    ))
    space = personal.spaces.create(Space(name="Our household", kind="household"))
    personal.spaces.add_member(space.id, SpaceMember(display_name="Kevin", role=SpaceRole.owner))
    personal.spaces.add_member(space.id, SpaceMember(display_name="Sam", role=SpaceRole.adult))
    bots = store.list_bots()
    if bots:
        personal.spaces.grant(space.id, bots[0].id)
    personal.commitments.create(
        Commitment(title="Buy groceries", space_id=space.id, detail="Milk and eggs")
    )


async def measure(page: Page) -> dict[str, Any]:
    """Capture critical accessibility, layout, and rendering facts."""
    return await page.evaluate("""() => ({
        title: document.title,
        heading: (document.querySelector('h1') || document.querySelector('h2') || {}).textContent?.trim() || '',
        overflow_x: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
        focusable: document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]').length,
    })""")


async def capture_one(browser: Any, origin: str, out: Path, name: str, path: str,
                      size: tuple[int, int], scheme: str) -> dict[str, Any]:
    context = await browser.new_context(
        viewport={"width": size[0], "height": size[1]},
        color_scheme=scheme,
        device_scale_factor=1,
    )
    page = await context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(f"pageerror: {err}"))
    page.on("console", lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None)

    await page.goto(origin + path, wait_until="networkidle")
    await page.wait_for_timeout(800)

    filename = f"{name}-{size[0]}-{scheme}.png"
    await page.screenshot(path=str(out / filename), full_page=False)
    metrics = await measure(page)
    record = {
        "page": name,
        "path": path,
        "width": size[0],
        "height": size[1],
        "scheme": scheme,
        "screenshot": filename,
        "console_errors": errors,
        **metrics,
    }
    await context.close()
    return record


async def capture_all(origin: str, out: Path) -> list[dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        for name, path in PAGES:
            for size in WIDTHS:
                for scheme in SCHEMES:
                    record = await capture_one(browser, origin, out, name, path, size, scheme)
                    records.append(record)
        await browser.close()
    return records


def head_commit() -> str:
    res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False)
    return res.stdout.strip()


def run_capture(origin: str, out: Path) -> None:
    records = asyncio.run(capture_all(origin, out))
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": head_commit(),
        "records": records,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    bad = [r for r in records if r["console_errors"] or r["overflow_x"] > 0]
    print(f"Captured {len(records)} views; {len(bad)} with console errors or horizontal overflow")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture baseline visual screenshots.")
    parser.add_argument("--origin", default="", help="Origin of running server, or empty to launch one")
    parser.add_argument("--out", type=Path, default=Path("docs/research/2026-11-personal-ops-workflows/artifacts/phase0"))
    args = parser.parse_args()

    if args.origin:
        run_capture(args.origin.rstrip("/"), args.out)
        return

    tmp_dir = tempfile.mkdtemp(prefix="hutch-baseline-")
    prev_state = os.environ.get("HUTCH_STATE_DIR")
    os.environ["HUTCH_STATE_DIR"] = tmp_dir
    try:
        from hutch.server.app import create_app
        from tests.support.live_app import serve

        app = create_app()
        seed_test_store(app.state.store)
        with serve(app) as origin:
            run_capture(origin, args.out)
    finally:
        if prev_state is not None:
            os.environ["HUTCH_STATE_DIR"] = prev_state
        else:
            os.environ.pop("HUTCH_STATE_DIR", None)
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

