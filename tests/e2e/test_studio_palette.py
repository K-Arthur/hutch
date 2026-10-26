"""The ⌘K / Ctrl+K command palette: an ARIA combobox over a listbox in a native modal dialog."""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")
expect = pw.expect

from hutch.models import Bot  # noqa: E402
from tests.e2e.test_design_system import app_server, browser  # noqa: E402,F401


@pytest.fixture()
def page(browser, app_server):
    base, app = app_server
    store = app.state.store
    store.create_bot(Bot(name="research-desk", display_name="Research Desk", description="Reads sources and writes briefings",
                         model="mock/demo", tools=[]))
    context = browser.new_context(viewport={"width": 1280, "height": 800}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/#/chat/design-system-review", wait_until="domcontentloaded")
    page.locator("#chat-prompt").wait_for()
    yield page, base
    assert not errors, errors
    context.close()


def test_palette_opens_with_a_shortcut_and_is_a_labelled_combobox(page):
    page, _ = page
    page.locator("#chat-prompt").focus()
    page.keyboard.press("Control+k")
    dialog = page.locator("dialog.palette")
    expect(dialog).to_be_visible()
    box = page.get_by_role("combobox", name="Search assistants, conversations and pages")
    expect(box).to_be_focused()
    assert box.get_attribute("aria-expanded") == "true"
    listbox = page.get_by_role("listbox", name="Results")
    expect(listbox).to_be_visible()
    # assistants, pages and actions are all reachable options
    names = [text.strip() for text in page.locator("dialog.palette").get_by_role("option").all_inner_texts()]
    assert any("Research Desk" in name for name in names), names
    assert any(name.startswith("Settings") for name in names), names
    assert any(name.startswith("New conversation") for name in names), names
    # the active descendant always points at an option that exists
    active = box.get_attribute("aria-activedescendant")
    assert active and page.locator(f"#{active}").get_attribute("role") == "option"


def test_palette_filters_navigates_by_keyboard_and_restores_focus(page):
    page, base = page
    page.locator("#chat-prompt").focus()
    page.keyboard.press("Control+k")
    page.keyboard.type("research")
    options = page.locator("dialog.palette").get_by_role("option")
    # Assistants are listed first, so the best match is the assistant itself.
    expect(options.first).to_contain_text("Research Desk")
    assert page.locator("#palette-status").inner_text().endswith(("result", "results"))
    page.keyboard.press("Enter")
    expect(page.locator("dialog.palette")).not_to_be_visible()
    page.wait_for_url("**/#/chat/research-desk")
    # Escape closes without navigating and returns focus to where the person was. Wait for the
    # destination view to finish rendering first: its data loads before it replaces the old view.
    expect(page.get_by_role("heading", name="Research Desk", level=1)).to_be_visible()
    page.locator("#chat-prompt").wait_for()
    page.locator("#chat-prompt").focus()
    page.keyboard.press("Control+k")
    page.keyboard.press("Escape")
    expect(page.locator("dialog.palette")).not_to_be_visible()
    info = page.evaluate("() => { const e = document.activeElement; return [e.tagName, e.id, e.className]; }")
    assert info[1] == "chat-prompt", info
    assert page.url.endswith("#/chat/research-desk")


def test_palette_arrow_keys_wrap_and_empty_state_is_announced(page):
    page, _ = page
    page.keyboard.press("Control+k")
    first = page.locator('dialog.palette [role="option"][aria-selected="true"]')
    expect(first).to_have_count(1)
    page.keyboard.press("ArrowUp")           # wraps to the last entry
    last_id = page.locator("#palette-input").get_attribute("aria-activedescendant")
    assert last_id and last_id != "palette-opt-0"
    page.keyboard.type("zzzz-no-such-thing")
    assert page.locator("#palette-status").inner_text() == "No results"
    expect(page.locator(".palette-empty")).to_contain_text("No match")
    page.keyboard.press("Control+k")         # the same shortcut toggles it closed
    expect(page.locator("dialog.palette")).not_to_be_visible()
