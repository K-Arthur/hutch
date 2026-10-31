"""Removing assistants is one list and one confirmation, reachable from where a person looks (owner report).

The report: assistants an earlier demo seeded (and a design fixture) sat in a real workspace, could not run, kept first-run
onboarding from starting, and removing them meant a separate multi-step page per assistant buried in settings. Real server and
browser. Removal is the governed whole-assistant deletion underneath, so each one leaves its evidence record.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402
from tests.support.live_app import horizontal_overflow, serve  # noqa: E402

SEEDED = ("research-briefing", "tidy-downloads", "repo-sweeper")
LEFTOVERS = {*SEEDED, "design-system-review"}      # the fourth is on a route that looks valid, like Design Partner in the report


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        b = launch_browser(playwright)
        yield b
        b.close()


def _seed(store):
    for name in SEEDED:
        store.create_bot(Bot(name=name, display_name=name.replace("-", " ").title(), model="mock/demo", tools=[]))
    store.create_bot(Bot(name="design-system-review", display_name="Design Partner", model="ollama/llama3.2:3b", tools=[]))
    store.create_bot(Bot(name="no-route-yet", display_name="No Route Yet", model="", tools=[]))
    keeper = store.create_bot(Bot(name="real-one", display_name="Real One", model="ollama/llama3.2:3b", tools=[]))
    store.set_workspace_coordinator(keeper.id)


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    app = create_app()
    _seed(app.state.store)
    with serve(app) as url:
        yield url, app.state.store


def _names(store):
    return {bot.name for bot in store.list_bots()}


def _choose_dialog(page):
    return page.locator("dialog[open]").filter(has=page.locator(".removal-list"))


def _confirm_dialog(page):
    return page.locator("dialog[open]").filter(has=page.locator("#removal-phrase"))


def _from_review(page, base):
    page.goto(f"{base}/#/chat/real-one", wait_until="domcontentloaded")
    page.locator("#installation-review").wait_for(timeout=20_000)
    page.locator("#installation-review").click()
    page.locator("[data-remove-assistants]").first.click()
    _choose_dialog(page).wait_for(timeout=15_000)


def test_leftovers_are_preselected_everything_else_is_not_and_a_wrong_phrase_removes_nothing(browser, live):
    base, store = live
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    try:
        _from_review(page, base)
        checked = set(_choose_dialog(page).locator('input[name="remove"]:checked').evaluate_all("els => els.map(e => e.value)"))
        assert checked == LEFTOVERS, checked
        assert "earlier demo" in _choose_dialog(page).inner_text()
        _choose_dialog(page).locator("#modal-confirm").click()
        confirm = _confirm_dialog(page)
        confirm.wait_for(timeout=15_000)
        listed = confirm.inner_text()
        assert "remove 4 assistants" in listed and "Design Partner" in listed and "Real One" not in listed and "No Route Yet" not in listed
        confirm.locator("#removal-phrase").fill("remove them")
        confirm.locator("#modal-confirm").click()
        page.wait_for_timeout(600)
        assert confirm.locator("#removal-phrase").is_visible(), "a wrong phrase keeps the dialog open"
        assert _names(store) == {*LEFTOVERS, "no-route-yet", "real-one"}
    finally:
        page.context.close()


def test_the_right_phrase_removes_each_through_the_governed_deletion_and_keeps_the_rest(browser, live):
    base, store = live
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    try:
        _from_review(page, base)
        _choose_dialog(page).locator("#modal-confirm").click()
        confirm = _confirm_dialog(page)
        confirm.wait_for(timeout=15_000)
        confirm.locator("#removal-phrase").fill("Remove 4 assistants")           # the match ignores case
        confirm.locator("#modal-confirm").click()
        for _ in range(80):
            if _names(store) == {"no-route-yet", "real-one"}:
                break
            page.wait_for_timeout(250)
        assert _names(store) == {"no-route-yet", "real-one"}
        with store._lock:
            confirmed = store._db.execute("SELECT COUNT(*) FROM bot_deletions WHERE status = 'confirmed'").fetchone()[0]
        assert confirmed == 4, "each removal is a recorded governed deletion, not a shortcut"
        page.locator("#roster-list [data-switch-bot]").first.wait_for(timeout=10_000)
        roster = page.locator("#roster-list").inner_text()
        assert "Research Briefing" not in roster and "Design Partner" not in roster and "Real One" in roster
    finally:
        page.context.close()


def test_the_sidebar_menu_removes_one_assistant_and_has_no_way_to_choose_the_main_one(browser, live):
    base, store = live
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/chat/real-one", wait_until="domcontentloaded")
        page.locator('[data-bot-options="no-route-yet"]').wait_for(timeout=20_000)
        page.locator('[data-bot-options="no-route-yet"]').click()
        menu = page.locator("#roster-action-menu")
        menu.wait_for()
        assert "main assistant" not in menu.inner_text().lower(), "the main assistant is named at onboarding, not chosen from a menu"
        page.keyboard.press("Escape")
        page.locator('[data-bot-options="real-one"]').click()
        page.locator("[data-menu-remove]").click()
        _choose_dialog(page).wait_for(timeout=15_000)
        checked = _choose_dialog(page).locator('input[name="remove"]:checked').evaluate_all("els => els.map(e => e.value)")
        assert checked == ["real-one"], "the menu preselects only that assistant"
        _choose_dialog(page).locator("#modal-confirm").click()
        confirm = _confirm_dialog(page)
        confirm.wait_for(timeout=15_000)
        confirm.locator("#removal-phrase").fill("remove 1 assistant")
        confirm.locator("#modal-confirm").click()
        for _ in range(60):
            if "real-one" not in _names(store):
                break
            page.wait_for_timeout(250)
        assert "real-one" not in _names(store) and "no-route-yet" in _names(store)
    finally:
        page.context.close()


def test_the_cant_run_notice_removes_just_that_assistant_or_all_the_leftovers(browser, live):
    base, _ = live
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    try:
        page.goto(f"{base}/#/chat/tidy-downloads", wait_until="domcontentloaded")
        one = page.locator('.welcome-problem [data-remove-name="tidy-downloads"]')
        one.wait_for(timeout=20_000)
        one.click()
        _choose_dialog(page).wait_for(timeout=15_000)
        assert _choose_dialog(page).locator('input[name="remove"]:checked').evaluate_all("els => els.map(e => e.value)") == ["tidy-downloads"]
        _choose_dialog(page).locator("#modal-cancel").click()
        page.locator(".welcome-problem button", has_text="Remove all demo assistants").click()
        _choose_dialog(page).wait_for(timeout=15_000)
        assert len(_choose_dialog(page).locator('input[name="remove"]:checked').all()) == 4
    finally:
        page.context.close()


def test_removing_every_leftover_from_a_demo_only_workspace_hands_it_to_first_run(browser, tmp_path, monkeypatch):
    """Owner report: precreated assistants that cannot run kept first-run onboarding from ever starting."""
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    app = create_app()
    for name in SEEDED:
        app.state.store.create_bot(Bot(name=name, display_name=name.replace("-", " ").title(), model="mock/demo", tools=[]))
    with serve(app) as base:
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        try:
            page.goto(f"{base}/#/chat/tidy-downloads", wait_until="domcontentloaded")
            page.locator(".welcome-problem button", has_text="Remove all demo assistants").click()
            _choose_dialog(page).wait_for(timeout=15_000)
            _choose_dialog(page).locator("#modal-confirm").click()
            confirm = _confirm_dialog(page)
            confirm.wait_for(timeout=15_000)
            confirm.locator("#removal-phrase").fill("remove 3 assistants")
            confirm.locator("#modal-confirm").click()
            page.get_by_role("heading", name="What would you like help with?").wait_for(timeout=20_000)
            assert app.state.store.list_bots() == [] and page.locator("#roster-list [data-switch-bot]").count() == 0
        finally:
            page.context.close()


def test_the_dialogs_fit_a_phone(browser, live):
    base, _ = live
    page = browser.new_context(viewport={"width": 360, "height": 800}).new_page()
    try:
        _from_review(page, base)
        assert horizontal_overflow(page) == 0
        _choose_dialog(page).locator("#modal-confirm").click()
        _confirm_dialog(page).locator("#removal-phrase").wait_for(timeout=15_000)
        assert horizontal_overflow(page) == 0
        box = page.locator("#removal-phrase").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 360.5
    finally:
        page.context.close()
