"""Browser journey: spending bands round-trip, the preflight review sheet, and honest run context (SR-2/LM-3)."""

from __future__ import annotations

from tests.support.browser import wait_for_page, wait_for_page_value

import hashlib
import json
import time
from pathlib import Path

import pytest

from hutch.models import Bot

from tests.e2e.test_browser import browser, live, open_assistant_customization  # noqa: F401
from tests.support.artifacts import artifact_path

pytest.importorskip("playwright.sync_api")

ARTIFACTS = artifact_path("cost-guardrails-2026-10-11")
VIEWPORTS = (("desktop", {"width": 1440, "height": 900}),
             ("tablet", {"width": 768, "height": 1024}),
             ("phone", {"width": 360, "height": 780}))


def test_budget_bands_preflight_and_context_are_usable_at_every_width(browser, live):  # noqa: F811
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="budget-widgets", display_name="Budget Widgets", model="mock/demo",
                               description="shows spending bands"))
    conversation, _ = store.create_conversation(bot.id, "budget chat", idem_key="budget-seed", request_hash="seed")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, dict] = {}

    for label, viewport in VIEWPORTS:
        page = browser.new_page(viewport=viewport)
        errors: list[str] = []
        estimate_requests: list[dict[str, str]] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("request", lambda request: estimate_requests.append({"url": request.url, "body": request.post_data or ""})
                if request.method == "POST" and "/estimate" in request.url else None)
        try:
            page.goto(f"{base}/#/bot/{bot.name}")
            open_assistant_customization(page, "model")
            if label == "desktop":
                page.fill('[data-task-route="code_analysis"]', "mock/demo")
                page.click("#form-model button[type=submit]")
                deadline = time.time() + 8
                saved_routes = {}
                while time.time() < deadline:
                    saved_routes = store.get_bot(bot.id).task_routes
                    if saved_routes.get("code_analysis") == "mock/demo":
                        break
                    page.wait_for_timeout(100)
                assert saved_routes == {"code_analysis": "mock/demo"}, "the task route did not save through Bot settings"
                open_assistant_customization(page, "model")
            route_input = page.locator('[data-task-route="code_analysis"]')
            route_input.wait_for(state="visible")
            route_geometry = wait_for_page_value(page, """() => {
              const input = document.querySelector('[data-task-route="code_analysis"]');
              if (!input || !input.isConnected) return null;
              input.scrollIntoView({block: 'center', inline: 'nearest'});
              const rect = input.getBoundingClientRect();
              return rect.width > 0 && rect.height > 0
                ? {value: input.value, width: rect.width, height: rect.height} : null;
            }""")
            assert route_geometry["width"] > 0 and route_geometry["height"] > 0
            page.screenshot(path=str(ARTIFACTS / f"route-settings-{label}.png"), full_page=False,
                            animations="disabled")
            open_assistant_customization(page, "limits")
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
            open_assistant_customization(page, "limits")
            disclosure = page.locator("#assistant-usage-limits")
            disclosure.wait_for(state="attached")
            if not disclosure.evaluate("element => element.open"):
                disclosure.locator(":scope > summary").click()
            wait_for_page(page, "document.querySelector('#band-ceiling')?.value === '0.15'", timeout=6000)
            assert page.input_value("#band-warn") == "0.05"

            page.goto(f"{base}/#/chat")
            page.wait_for_selector("#composer-menu-btn")
            page.click("#composer-menu-btn")
            page.select_option("#chat-task-role", "code_analysis")
            page.fill("#chat-prompt", "Review the current diff and preserve the public API.")
            page.click("#composer-menu-btn")
            page.wait_for_selector("#preflight-open")
            page.click("#preflight-open")
            page.wait_for_selector(".modal-card .preflight-grid")
            assert page.locator("#composer-menu").evaluate("el => el.hidden")
            body_text = page.inner_text(".modal-card")
            assert "Price basis" in body_text and "Next call reserve" in body_text and "Context" in body_text
            assert "Task role" in body_text and "Code analysis" in body_text
            assert "selected skills, recent conversation and this draft" in body_text
            request = next((item for item in estimate_requests if "/estimate" in item["url"]), None)
            assert request is not None
            assert "Review the current diff" not in request["url"]
            estimate_body = json.loads(request["body"])
            assert estimate_body["prompt"] == "Review the current diff and preserve the public API."
            assert estimate_body["task_role"] == "code_analysis"
            assert estimate_body["conversation_id"] == conversation["id"]
            page.screenshot(path=str(ARTIFACTS / f"budget-{label}.png"), full_page=False, animations="disabled")
            page.click("#modal-close")

            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert overflow <= 1, f"horizontal overflow at {label}: {overflow}px"
            assert not errors, f"page errors at {label}: {errors}"
            evidence[label] = {"size": [viewport["width"], viewport["height"]],
                               "overflow_px": overflow, "page_errors": errors}
        finally:
            page.close()

    repo_root = Path(__file__).resolve().parents[2]
    (ARTIFACTS / "validation.json").write_text(json.dumps({
        "test": "tests/e2e/test_browser_budget_controls.py::test_budget_bands_preflight_and_context_are_usable_at_every_width",
        "journey": "task-role route configured through Bot settings; spending bands save + reload round-trip; one-message role selection and draft/context-aware cost preflight; mock route only",
        "browser": browser.browser_type.name,
        "browser_version": browser.version,
        "provider_calls": 0,
        "viewports": evidence,
        "source_sha256": {
            "app.js": hashlib.sha256((repo_root / "src/hutch/server/static/app.js").read_bytes()).hexdigest(),
            "style.css": hashlib.sha256((repo_root / "src/hutch/server/static/style.css").read_bytes()).hexdigest(),
            "website/index.html": hashlib.sha256((repo_root / "website/index.html").read_bytes()).hexdigest(),
        },
        "note": "Screenshots are the visual evidence; provider billing was not exercised (mock route).",
    }, indent=2) + "\n")
