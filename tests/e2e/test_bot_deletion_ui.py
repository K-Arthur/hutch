"""Live-browser journey for the dashboard whole-Bot permanent-deletion pages.

Covers the server-rendered picker, the danger-zone two-step control, the typed address guard,
the injected-API-error retry and the responsive layout, then writes PNG evidence plus capture.json
with the exact Chromium build to the isolated test-artifact root (set HUTCH_DELETION_EVIDENCE_DIR to
refresh docs/realignment/artifacts/completion-2026-10-29/deletion/ deliberately). The focused command is
COMMAND below.
"""
from __future__ import annotations

import json
import os
import platform
import re
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.artifacts import artifact_path  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(os.environ.get("HUTCH_DELETION_EVIDENCE_DIR", str(artifact_path("deletion-ui"))))
COMMAND = ".venv/bin/python -m pytest -q --no-header --tb=line tests/e2e/test_bot_deletion_ui.py"
VIEWPORTS = (("desktop", 1440, 900), ("tablet", 900, 900), ("phone", 360, 800))
CLEANUP_TEXT = {"none": "No post-commit cleanup was requested.", "pending": "has not started yet",
                "cleaning": "is still running", "cleaned": "Every managed file was removed.",
                "needs_attention": "needs attention"}


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        instance = launch_browser(p)
        yield instance
        instance.close()


@pytest.fixture()
def live(tmp_path, monkeypatch, browser):
    """Isolated state directory, app and uvicorn thread on an ephemeral port."""
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "4")
    existing_contexts = set(browser.contexts)
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", app
    finally:
        for context in set(browser.contexts) - existing_contexts:
            context.close()
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def _process_tree_children() -> dict[int, list[int]]:
    """Map parent process ids to their direct children via /proc."""
    children: dict[int, list[int]] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            stat = Path("/proc", name, "stat").read_text()
        except OSError:
            continue
        fields = stat.rsplit(")", 1)[-1].split()
        if fields:
            children.setdefault(int(fields[1]), []).append(int(name))
    return children


def _launched_browser_executable() -> str:
    """Return the executable path of the Playwright browser this process launched."""
    children = _process_tree_children()
    pending, seen = list(children.get(os.getpid(), [])), set()
    while pending:
        pid = pending.pop()
        pending.extend(children.get(pid, []))
        try:
            executable = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            continue
        if "ms-playwright" in executable and Path(executable).name in {"chrome", "chrome-headless-shell"}:
            seen.add(executable)
    assert seen, "could not identify the launched Playwright Chromium executable"
    return sorted(seen)[0]


def _chromium_build(executable: str) -> tuple[str, str]:
    """Split an installed Chromium path into its build directory and revision."""
    match = re.search(r"(chromium(?:_headless_shell)?)-(\d+)", executable)
    assert match is not None, executable
    return match.group(0), match.group(2)


@pytest.fixture(scope="module")
def evidence(browser):
    """Collect capture entries; always write capture.json, even when a case fails."""
    assert browser.browser_type.name == "chromium", "browser evidence requires the Playwright Chromium build"
    executable = _launched_browser_executable()
    build_directory, revision = _chromium_build(executable)
    state = {
        "captures": [], "pages": {},
        "browser": {"engine": "chromium", "name": "Chrome for Testing", "version": browser.version,
                    "headless": True, "executable_path": executable,
                    "build_directory": build_directory, "revision": revision},
    }
    yield state
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    record = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "command": COMMAND,
        "test_file": "tests/e2e/test_bot_deletion_ui.py",
        "page": "GET /bots/delete and GET /bots/{name}/delete",
        "browser": state["browser"],
        "playwright_version": package_version("playwright"),
        "python_version": platform.python_version(),
        "note": "Chromium revision/build derived from the launched Playwright executable, as in "
                "docs/realignment/capture_marketing_head.py.",
        "honest_limits": [
            "Deletion is a settings action: the assistant danger zone links to the picker; the shared "
            "sidebar deliberately has no destructive primary-navigation row.",
            "Discovery is verified at 1440px; the shared sidebar collapses behind #nav-toggle on narrow views.",
            "History is not reloaded after deletion (GET history 404s once the Bot is gone); the panel "
            "says the content-free evidence remains rather than inventing a list.",
        ],
        "captures": state["captures"],
    }
    (ARTIFACTS / "capture.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def open_page(browser, evidence, width: int, height: int):
    """Open a fresh context/page and start a page-error and API-request ledger."""
    coarse = width <= 640
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce",
                                  is_mobile=coarse, has_touch=coarse)
    page = context.new_page()
    log = {"page_errors": [], "console_errors": [], "api_requests": []}
    page.on("pageerror", lambda error, sink=log: sink["page_errors"].append(str(error)))
    page.on("console", lambda message, sink=log: sink["console_errors"].append(message.text)
            if message.type == "error" else None)
    page.on("request", lambda request, sink=log: sink["api_requests"].append(
        {"method": request.method, "url": request.url}) if "/deletion-requests" in request.url else None)
    evidence["pages"][id(page)] = log
    return context, page, log


def capture(evidence, name: str, page, *, extra: dict | None = None) -> dict:
    """Screenshot the current page state and record the measured evidence."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    viewport = page.viewport_size or {"width": 0, "height": 0}
    path = ARTIFACTS / f"{name}-{viewport['width']}x{viewport['height']}.png"
    page.screenshot(path=str(path), animations="disabled")
    assert path.stat().st_size > 5_000, path
    log = evidence["pages"][id(page)]
    entry = {
        "case": name,
        "route_url": page.url,
        "viewport": [viewport["width"], viewport["height"]],
        "path": (path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.relative_to(ARTIFACTS)).as_posix(),
        "path_bytes": path.stat().st_size,
        "horizontal_overflow": page.evaluate("() => document.documentElement.scrollWidth - innerWidth"),
        "page_error_count": len(log["page_errors"]),
        "page_errors": list(log["page_errors"]),
        "console_error_count": len(log["console_errors"]),
        "console_errors": list(log["console_errors"]),
    }
    entry.update(extra or {})
    evidence["captures"].append(entry)
    return entry


def wait_preview(page):
    """Wait for the preview step, including its counts and typed-address field."""
    page.locator("[data-bot-delete-step='preview']").wait_for(state="visible", timeout=15_000)


def test_picker_empty_state_when_no_bots(browser, live, evidence):
    base, _app = live
    context, page, log = open_page(browser, evidence, 1440, 900)
    try:
        response = page.goto(base + "/bots/delete", wait_until="networkidle")
        assert response is not None and response.status == 200
        page.get_by_role("heading", name="No bots yet").wait_for(timeout=10_000)
        assert page.locator("[data-bot-delete-choice]").count() == 0
        assert page.get_by_role("link", name="New bot").get_attribute("href") == "/bots/new"
        capture(evidence, "picker-empty", page)
        assert log["page_errors"] == []
    finally:
        context.close()


def test_picker_lists_bots_and_each_link_opens_its_danger_zone(browser, live, evidence):
    base, app = live
    store = app.state.store
    store.create_bot(Bot(name="browser-alpha", display_name="Browser Alpha", description="first bot"))
    store.create_bot(Bot(name="browser-beta", display_name="Browser Beta"))
    context, page, log = open_page(browser, evidence, 1440, 900)
    try:
        response = page.goto(base + "/bots/delete", wait_until="networkidle")
        assert response is not None and response.status == 200
        rows = page.locator("[data-bot-delete-choice]")
        assert rows.count() == 2
        assert "browser-alpha" in rows.nth(0).inner_text()
        assert "browser-beta" in rows.nth(1).inner_text()
        assert page.locator('[data-bot-delete-link="browser-alpha"]').get_attribute(
            "href") == "/bots/browser-alpha/delete"
        capture(evidence, "picker-two-bots", page)
        page.click('[data-bot-delete-link="browser-beta"]')
        page.wait_for_url("**/bots/browser-beta/delete", timeout=10_000)
        assert page.locator("[data-bot-deletion]").get_attribute("data-bot-name") == "browser-beta"
        page.get_by_role("heading", name="Permanently delete Browser Beta").wait_for(timeout=10_000)
        capture(evidence, "picker-link-danger", page)
        assert log["page_errors"] == []
    finally:
        context.close()


def test_assistant_danger_zone_links_to_the_deletion_picker(browser, live, evidence):
    """Deletion is a settings action: it lives in the assistant's danger zone,
    not in the primary navigation (the shared sidebar has no destructive row)."""
    base, app = live
    app.state.store.create_bot(Bot(name="nav-bot", display_name="Nav Bot"))
    context, page, log = open_page(browser, evidence, 1440, 900)
    try:
        response = page.goto(base + "/bots/nav-bot", wait_until="networkidle")
        assert response is not None and response.status == 200
        assert page.locator('nav.nav a[href="/bots/delete"]').count() == 0
        page.locator("details.danger-zone > summary").click()
        link = page.locator('a[href="/bots/delete"]').first
        link.wait_for(state="visible", timeout=10_000)
        assert "deletion picker" in link.inner_text()
        capture(evidence, "danger-zone-picker-link", page)
        link.click()
        page.wait_for_url("**/bots/delete", timeout=10_000)
        page.get_by_role("heading", name="Permanently delete a bot").wait_for(timeout=10_000)
        rows = page.locator("[data-bot-delete-choice]")
        assert rows.count() == 1 and "nav-bot" in rows.nth(0).inner_text()
        assert log["page_errors"] == []
    finally:
        context.close()


def test_wrong_typed_address_shows_an_error_and_erases_nothing(browser, live, evidence):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name="typed-wrong", display_name="Typed Wrong"))
    context, page, log = open_page(browser, evidence, 1440, 900)
    try:
        page.goto(base + "/bots/typed-wrong/delete", wait_until="networkidle")
        page.click("[data-bot-delete-preview]")
        wait_preview(page)
        page.fill("[data-bot-delete-confirmation]", "typed-wrong-extra")
        confirm = page.locator("[data-bot-delete-confirm]")
        assert confirm.is_disabled()
        page.press("[data-bot-delete-confirmation]", "Enter")
        error = page.locator("#bot-deletion-error")
        error.wait_for(state="visible", timeout=5_000)
        assert error.get_attribute("aria-live") == "assertive"
        assert "does not match the bot address" in error.inner_text()
        assert page.evaluate("document.activeElement && document.activeElement.id === 'bot-deletion-error'")
        assert not any(entry["url"].endswith("/confirm") for entry in log["api_requests"])
        assert store.get_bot("typed-wrong") is not None and store.get_bot(bot.id) is not None
        capture(evidence, "wrong-typed-address", page, extra={"bot_still_present": True})
        assert log["page_errors"] == [] and log["console_errors"] == []
    finally:
        context.close()


def test_successful_deletion_shows_cleanup_state_and_removes_only_that_bot(browser, live, evidence):
    base, app = live
    store = app.state.store
    store.create_bot(Bot(name="delete-me", display_name="Delete Me", description="about to go"))
    store.create_bot(Bot(name="keep-me", display_name="Keep Me"))
    context, page, log = open_page(browser, evidence, 1440, 900)
    try:
        page.goto(base + "/bots/delete-me/delete", wait_until="networkidle")
        assert page.locator("#bot-deletion-history").inner_text().strip() == "No deletion requests yet"
        with page.expect_response(lambda response: response.request.method == "POST"
                                  and response.url.endswith("/deletion-requests")) as preview_info:
            page.click("[data-bot-delete-preview]")
        wait_preview(page)
        preview = preview_info.value.json()
        assert preview["bot_name"] == "delete-me"
        counts = page.locator("[data-bot-delete-counts] li").all_inner_texts()
        non_zero = [key for key, value in preview["counts"].items() if key != "total" and value > 0]
        assert len(counts) == len(non_zero), (counts, preview["counts"])
        assert page.locator("[data-bot-delete-total]").inner_text() == str(preview["counts"]["total"])
        remaining = page.locator("[data-bot-delete-remaining] li").all_inner_texts()
        assert remaining == preview["remaining"]
        assert page.locator("[data-bot-delete-confirm]").is_disabled()
        page.fill("[data-bot-delete-confirmation]", "delete-me")
        assert not page.locator("[data-bot-delete-confirm]").is_disabled()
        with page.expect_response(lambda response: response.url.endswith("/confirm")) as confirm_info:
            page.click("[data-bot-delete-confirm]")
        result = confirm_info.value.json()
        assert result["status"] == "confirmed"
        assert confirm_info.value.request.headers.get("idempotency-key")
        page.locator("[data-bot-delete-success]").wait_for(state="visible", timeout=15_000)
        outcome = page.locator("[data-bot-delete-outcome]").inner_text()
        assert CLEANUP_TEXT[result["cleanup_state"]] in outcome
        assert page.locator("[data-bot-delete-cleanup-state]").inner_text() == result["cleanup_state"]
        assert page.evaluate("document.activeElement && document.activeElement.hasAttribute("
                             "'data-bot-delete-success')")
        assert store.get_bot("delete-me") is None
        assert store.get_bot("keep-me") is not None
        capture(evidence, "deleted-success", page, extra={"cleanup_state": result["cleanup_state"],
                                                   "erased_total": result["counts"]["total"]})
        page.goto(base + "/bots/delete", wait_until="networkidle")
        rows = page.locator("[data-bot-delete-choice]")
        assert rows.count() == 1 and "keep-me" in rows.nth(0).inner_text()
        capture(evidence, "picker-after-deletion", page, extra={"remaining_bot": "keep-me"})
        assert log["page_errors"] == []
    finally:
        context.close()


def test_injected_api_error_shows_banner_and_retry_recovers_the_control(browser, live, evidence):
    base, app = live
    app.state.store.create_bot(Bot(name="error-bot", display_name="Error Bot"))
    context, page, log = open_page(browser, evidence, 1440, 900)
    calls = {"post": 0}

    def inject_failure(route):
        if route.request.method == "POST":
            calls["post"] += 1
            if calls["post"] == 1:
                route.fulfill(status=503, content_type="application/json",
                              body=json.dumps({"detail": "Injected preview failure for the browser journey."}))
                return
        route.continue_()

    page.route("**/api/v1/bots/error-bot/deletion-requests", inject_failure)
    try:
        page.goto(base + "/bots/error-bot/delete", wait_until="networkidle")
        page.click("[data-bot-delete-preview]")
        error = page.locator("#bot-deletion-error")
        error.wait_for(state="visible", timeout=10_000)
        assert "Injected preview failure" in error.inner_text()
        assert page.evaluate("document.activeElement && document.activeElement.id === 'bot-deletion-error'")
        assert page.locator("[data-bot-delete-preview]").is_enabled(), "a failed preview must unfreeze the control"
        capture(evidence, "injected-error", page, extra={"injected_status": 503})
        page.click("[data-bot-delete-retry]")
        wait_preview(page)
        assert error.is_hidden()
        page.fill("[data-bot-delete-confirmation]", "error-bot")
        assert not page.locator("[data-bot-delete-confirm]").is_disabled()
        capture(evidence, "retry-recovered", page, extra={"retry_preview_calls": calls["post"]})
        assert log["page_errors"] == []
        assert len(log["console_errors"]) == 1 and "503" in log["console_errors"][0], log["console_errors"]
    finally:
        context.close()


@pytest.mark.parametrize("label,width,height", VIEWPORTS)
def test_no_horizontal_overflow_at_three_viewports(browser, live, evidence, label, width, height):
    base, app = live
    app.state.store.create_bot(Bot(name=f"overflow-{label}", display_name="Overflow View"))
    context, page, log = open_page(browser, evidence, width, height)
    try:
        response = page.goto(base + f"/bots/overflow-{label}/delete", wait_until="networkidle")
        assert response is not None and response.status == 200
        overflow = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 2, (label, overflow)
        page.click("[data-bot-delete-preview]")
        wait_preview(page)
        overflow = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 2, (label, overflow)
        geometry = page.evaluate("""() => {
          const measure = (selector) => {
            const box = document.querySelector(selector).getBoundingClientRect();
            return {height: Math.round(box.height), width: Math.round(box.width)};
          };
          return {preview: measure('[data-bot-delete-preview]'),
                  confirm: measure('[data-bot-delete-confirm]'),
                  input: measure('[data-bot-delete-confirmation]')};
        }""")
        if width <= 640:
            for control in ("preview", "confirm", "input"):
                assert geometry[control]["height"] >= 44, (label, control, geometry)
        capture(evidence, f"overflow-{label}", page, extra={"control_geometry": geometry})
        assert log["page_errors"] == []
    finally:
        context.close()
