"""Shared-control behavior against the running Hutch application, not a demo page."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
from hutch.models import Bot
from tests.e2e.test_browser import live  # real isolated HTTP app fixture
from tests.e2e.test_skills_browser import seed_skill
from tests.support.artifacts import artifact_path
from tests.support.browser import launch_browser, wait_for_page


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        instance = launch_browser(playwright)
        yield instance
        instance.close()


def assert_fits(page, popup):
    bounds = popup.bounding_box()
    assert bounds and bounds["x"] >= 0 and bounds["y"] >= 0, bounds
    assert bounds["x"] + bounds["width"] <= page.viewport_size["width"] + 1, bounds
    assert bounds["y"] + bounds["height"] <= page.viewport_size["height"] + 1, bounds


@pytest.mark.parametrize("width,height", [(1440, 960), (900, 1024), (390, 844), (320, 740)])
def test_settings_select_retains_native_form_and_shared_picker(browser, live, width, height):
    base, app = live
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = artifact_path("dropdowns/select")
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/settings")
        control = page.locator("#workspace-settings-mode")
        control.wait_for()
        assert control.evaluate("el => el instanceof HTMLSelectElement")
        assert control.get_attribute("name") is None  # existing SPA value contract
        control.click()
        assert control.evaluate("el => el.matches(':open')")
        assert control.evaluate("el => getComputedStyle(el).fontSize") == "16px"
        assert control.locator("option").count() == 3
        page.screenshot(path=str(out / f"open-{width}.png"))
        page.keyboard.press("Escape")
        assert control.input_value() == "hybrid", "exploring must not change the saved routing"
        control.select_option("local")
        with page.expect_response(lambda response: response.url.endswith("/api/v1/preferences/model-defaults")
                                  and response.request.method == "PUT") as saved:
            page.get_by_role("button", name="Save workspace settings").click()
        assert saved.value.ok, saved.value.text()
        page.reload()
        page.locator("#workspace-settings-mode").wait_for()
        assert page.locator("#workspace-settings-mode").input_value() == "local"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors, errors
    finally:
        context.close()


def test_action_menu_keyboard_escape_and_tab_preserve_focus(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="dropdown-helper", display_name="Research and project follow-through", model="ollama/local", tools=[]))
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        page.goto(base + "/#/bot/dropdown-helper")
        trigger = page.get_by_label("Assistant options", exact=True).first
        trigger.wait_for()
        trigger.focus()
        page.keyboard.press("ArrowDown")
        menu = page.locator(".assistant-settings-menu-panel")
        menu.wait_for(state="visible")
        assert menu.get_attribute("role") == "menu"
        assert_fits(page, menu)
        assert page.get_by_role("menuitem", name="Open chat").evaluate("el => el === document.activeElement")
        page.keyboard.press("End")
        assert page.get_by_role("menuitem", name="Delete assistant").evaluate("el => el === document.activeElement")
        page.keyboard.press("Escape")
        assert menu.is_hidden()
        assert trigger.evaluate("el => el === document.activeElement")
        trigger.click()
        menu.wait_for(state="visible")
        page.keyboard.press("Tab")
        assert menu.is_hidden()
        assert not page.evaluate("document.activeElement.closest('.hc-popup') !== null")
    finally:
        context.close()


def test_popup_in_native_dialog_accepts_pointer_and_scrolls_without_closing(browser, live):
    base, _ = live
    context = browser.new_context(viewport={"width": 390, "height": 500})
    page = context.new_page()
    try:
        page.goto(base + "/#/settings")
        page.locator("#workspace-settings-mode").wait_for()
        # Targeted hostile geometry fixture supplements the genuine settings
        # journey above: a native modal, clipped ancestor and 40 menu choices.
        page.evaluate("""() => {
          const dialog = document.createElement('dialog');
          dialog.innerHTML = '<div style="overflow:hidden;height:80px"><button id="nested-trigger">Choose a destination</button><div id="nested-popup" aria-label="Destinations"></div></div>';
          document.body.append(dialog); dialog.showModal();
          const panel = dialog.querySelector('#nested-popup');
          for (let i=0;i<40;i++) { const b=document.createElement('button'); b.type='button'; b.role='menuitem'; b.tabIndex=-1; b.textContent='Destination '+i; panel.append(b); }
          window.__nested = hutchControls.popup({trigger:dialog.querySelector('button'),panel,kind:'menu'});
          dialog.querySelector('button').onclick=()=>__nested.open();
          panel.onclick=e=>{ if(e.target.matches('button')) window.__chosen=e.target.textContent; };
        }""")
        page.locator("#nested-trigger").click()
        menu = page.locator("#nested-popup")
        assert_fits(page, menu)
        menu.hover()
        page.mouse.wheel(0, 500)
        wait_for_page(page, "document.querySelector('#nested-popup').scrollTop > 0")
        assert menu.is_visible()
        page.keyboard.press("End")
        page.get_by_role("menuitem", name="Destination 39", exact=True).click()
        assert page.evaluate("window.__chosen") == "Destination 39"
        page.keyboard.press("Escape")
        assert menu.is_hidden()
        assert page.locator("dialog:has(#nested-trigger)").evaluate("el => el.open"), "first Escape closes only the popup"
    finally:
        context.close()


@pytest.mark.parametrize("width,height", [(1440, 960), (900, 1024), (390, 844), (320, 740)])
def test_skill_checklist_preserves_focus_and_search_selection(browser, live, width, height):
    base, app = live
    seed_skill(app.state.config.state_dir, name="workspace-summary")
    seed_skill(app.state.config.state_dir, name="research-notes", description="Organize research notes and source references without sending them anywhere.")
    app.state.store.create_bot(Bot(name="skill-selection", model="mock/demo", tools=["files"], skills=["workspace-summary", "research-notes"]))
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = artifact_path("dropdowns/chat")
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/chat/skill-selection")
        page.locator("#chat-prompt").fill("Keep these research notes as a draft while I choose the right skills.")
        trigger = page.locator(".skill-picker-btn")
        trigger.wait_for(state="visible")
        trigger.click()
        popup = page.locator(".skill-picker-menu")
        assert popup.get_attribute("role") == "dialog"
        assert_fits(page, popup)
        first = popup.locator('input[value="workspace-summary"]')
        first.focus()
        page.keyboard.press("Space")
        assert first.is_checked()
        assert first.evaluate("el => el === document.activeElement"), "checking a skill must not replace its focused node"
        search = page.get_by_role("searchbox", name="Find a skill")
        search.fill("research")
        assert first.is_hidden()
        second = popup.locator('input[value="research-notes"]')
        second.check()
        search.fill("not-installed")
        assert popup.get_by_role("status").is_visible()
        search.fill("")
        assert first.is_checked() and second.is_checked()
        page.screenshot(path=str(out / f"skills-{width}.png"))
        page.keyboard.press("Escape")
        assert popup.is_hidden()
        assert trigger.evaluate("el => el === document.activeElement")
        assert trigger.inner_text() == "Skills (2)"
        model = page.locator(".ms-btn")
        assert page.locator(".ms-label").is_visible(), "phone must not hide model discovery"
        model.click()
        page.locator(".ms-menu").wait_for(state="visible")
        assert_fits(page, page.locator(".ms-menu"))
        page.screenshot(path=str(out / f"model-{width}.png"))
        page.keyboard.press("Escape")
        page.locator("#composer-menu-btn").click()
        composer = page.locator("#composer-menu")
        assert_fits(page, composer)
        page.screenshot(path=str(out / f"composer-{width}.png"))
        page.keyboard.press("Escape")
        assert "Keep these research notes" in page.locator("#chat-prompt").input_value()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors, errors
    finally:
        context.close()


def test_setup_model_suggestions_keep_typing_focus_and_explicit_values(browser, live):
    base, _ = live
    page = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        page.goto(base + "/#/assistant/new")
        page.locator("#setup-purpose").fill("Review public image credits and prepare a source list.")
        page.locator("#setup-customize").click()
        field = page.get_by_role("combobox", name="Model route", exact=True)
        field.wait_for()
        # Catalog adversary supplements the actual setup flow: matching display
        # names from two providers must retain distinct canonical route values.
        page.evaluate("""() => {
          const list=document.querySelector('#setup-model-routes');
          list.innerHTML='<option value="ollama/shared-model" label="On this machine: Shared model"></option><option value="openrouter/shared-model" label="Hosted: Shared model"></option>';
        }""")
        field.fill("shared")
        options = page.locator(".hc-suggestions").get_by_role("option")
        assert options.count() == 2
        assert field.evaluate("el => el === document.activeElement")
        assert_fits(page, page.locator(".hc-suggestions"))
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        assert field.input_value() == "openrouter/shared-model"
        assert page.locator(".hc-suggestions").is_hidden()
        field.fill("provider/my-explicit-route")
        assert page.get_by_role("status").filter(has_text="No available route matches").is_visible()
        page.keyboard.press("Escape")
        assert field.input_value() == "provider/my-explicit-route"
        assert field.evaluate("el => el === document.activeElement")
        out = artifact_path("dropdowns/setup")
        out.mkdir(parents=True, exist_ok=True)
        field.fill("shared")
        page.screenshot(path=str(out / "provider-identity-phone.png"))
    finally:
        page.close()


def test_public_image_workspace_journey_without_provider_calls(browser, live):
    image_path = os.environ.get("HUTCH_DROPDOWN_PUBLIC_IMAGE")
    if not image_path:
        pytest.skip("opt-in real public image path not supplied; ordinary CI never downloads external content")
    image = Path(image_path)
    payload = image.read_bytes()
    assert payload.startswith(b"\xff\xd8\xff") and len(payload) > 100_000, "use the real photograph, not a generated pixel fixture"
    base, app = live
    app.state.store.create_bot(Bot(name="public-image-review", display_name="Public image source review", model="ollama/llama3.2", tools=[]))
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    requests, errors = [], []
    page.on("request", lambda request: requests.append(request.url))
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = artifact_path("dropdowns/public-image")
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + "/#/chat/public-image-review")
        page.locator("#chat-prompt").fill("Keep the NASA Blue Marble image and its credit for a source review. Do not send or publish anything.")
        page.locator("#composer-menu-btn").click()
        with page.expect_file_chooser() as chooser:
            page.get_by_role("button", name="Attach a data file", exact=True).click()
        with page.expect_response(lambda response: response.url.endswith("/uploads") and response.request.method == "POST") as uploaded:
            chooser.value.set_files(str(image))
        assert uploaded.value.ok, uploaded.value.text()
        result = uploaded.value.json()
        page.get_by_text(f"Uploaded {image.name}", exact=True).wait_for()
        page.keyboard.press("Escape")
        assert image.name in page.locator(".upload-chip-name").inner_text()
        assert_fits(page, page.locator(".upload-chip-remove"))
        assert page.locator(".composer-attachments").evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        page.locator(".ms-btn").click()
        assert_fits(page, page.locator(".ms-menu"))
        page.screenshot(path=str(out / "uploaded-with-model-picker-phone.png"))
        page.keyboard.press("Escape")
        page.reload()
        page.locator(".upload-chip-name").wait_for()
        assert image.name in page.locator(".upload-chip-name").inner_text()
        assert "NASA Blue Marble" in page.locator("#chat-prompt").input_value()
        assert len(app.state.store.list_runs()) == 0, "changing controls and storing a file must not start inference"
        assert not errors, errors
        assert all(url.startswith(base) for url in requests), requests
        (out / "validation.json").write_text(json.dumps({
            "browser": browser.version, "image": image.name, "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "upload": result,
            "source": "https://commons.wikimedia.org/wiki/File:Earth_Western_Hemisphere.jpg",
            "credit": "NASA / Reto Stöckli / Robert Simmon; public domain per source page",
            "scope": "Real public JPEG through actual local upload endpoint and browser file chooser; durable draft reload and model popup. No mocked endpoint, provider inference, vision quality or image-chat support claimed.",
            "external_requests": [], "page_errors": errors,
        }, indent=2) + "\n")
    finally:
        context.close()
