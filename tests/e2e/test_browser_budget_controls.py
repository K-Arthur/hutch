"""Browser journey: spending bands round-trip, the preflight review sheet, and honest run context (SR-2/LM-3)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from hutch.models import Bot

from tests.e2e.test_browser import browser, live, open_assistant_customization  # noqa: F401

pytest.importorskip("playwright.sync_api")

ARTIFACTS = Path(__file__).resolve().parents[2] / "docs" / "realignment" / "artifacts" / "budget-guardrails-2026-10-11"
VIEWPORTS = (("desktop", {"width": 1440, "height": 900}),
             ("tablet", {"width": 768, "height": 1024}),
             ("phone", {"width": 360, "height": 780}))


def test_budget_bands_preflight_and_context_are_usable_at_every_width(browser, live):  # noqa: F811
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="budget-widgets", display_name="Budget Widgets", model="mock/demo",
                               description="shows spending bands"))
    store.create_conversation(bot.id, "budget chat", idem_key="budget-seed", request_hash="seed")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, dict] = {}

    for label, viewport in VIEWPORTS:
        page = browser.new_page(viewport=viewport)
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.goto(f"{base}/#/bot/{bot.name}")
            open_assistant_customization(page)
            disclosure = page.locator("#assistant-usage-limits")
            disclosure.wait_for(state="attached")
            if not disclosure.evaluate("element => element.open"):
                disclosure.locator(":scope > summary").click()
            page.wait_for_selector("#band-warn", state="visible")
            page.fill("#band-warn", "0.05")
            page.fill("#band-pause", "0.10")
            page.fill("#band-ceiling", "0.15")
            page.click("#form-limits button[type=submit]")
            deadline = time.time() + 8
            policy = None
            while time.time() < deadline:
                policy = store.get_budget_policy("bot", bot.id)
                if policy is not None:
                    break
                page.wait_for_timeout(100)
            assert policy is not None, "the bands were not saved through the UI"
            assert (policy.warn_usd, policy.pause_usd, policy.ceiling_usd) == (0.05, 0.10, 0.15)

            page.reload()
            open_assistant_customization(page)
            disclosure = page.locator("#assistant-usage-limits")
            disclosure.wait_for(state="attached")
            if not disclosure.evaluate("element => element.open"):
                disclosure.locator(":scope > summary").click()
            page.wait_for_function("document.querySelector('#band-ceiling')?.value === '0.15'", timeout=6000)
            assert page.input_value("#band-warn") == "0.05"

            page.goto(f"{base}/#/chat")
            page.wait_for_selector("#composer-menu-btn")
            page.click("#composer-menu-btn")
            page.wait_for_selector("#preflight-open")
            page.click("#preflight-open")
            page.wait_for_selector(".modal-card .preflight-grid")
            body_text = page.inner_text(".modal-card")
            assert "Price basis" in body_text and "Next call reserve" in body_text and "Context" in body_text
            page.screenshot(path=str(ARTIFACTS / f"budget-{label}.png"), full_page=False)
            page.click("#modal-close")

            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert overflow <= 1, f"horizontal overflow at {label}: {overflow}px"
            assert not errors, f"page errors at {label}: {errors}"
            evidence[label] = {"overflow_px": overflow, "page_errors": errors}
        finally:
            page.close()

    (ARTIFACTS / "validation.json").write_text(json.dumps({
        "journey": "assistant settings bands save + reload round-trip; composer preflight review sheet; mock route only",
        "viewports": evidence,
        "note": "Screenshots are the visual evidence; provider billing was not exercised (mock route).",
    }, indent=2) + "\n")
