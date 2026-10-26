"""Shared-control behavior against the running Hutch application, not a demo page."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
from hutch.models import Bot
from hutch.connections import ConnectionBook
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


def assert_uses_token(page, locator, border_token="--color-semantic-border-strong",
                      bg_token="--color-semantic-panel"):
    """The popup/field edge and surface must resolve to the same design-system
    tokens the rest of the UI uses — not a one-off grey. Both expected and actual
    go through the browser's colour normalisation, so no hex values are hardcoded."""
    result = locator.evaluate("""(el, tok) => {
      const cs = getComputedStyle(el);
      const root = getComputedStyle(document.documentElement);
      const norm = c => {
        const p = document.createElement('span');
        p.style.color = c; document.body.append(p);
        const v = getComputedStyle(p).color; p.remove(); return v;
      };
      return {
        border: cs.borderTopColor,
        expectedBorder: norm(root.getPropertyValue(tok.border)),
        bg: cs.backgroundColor,
        expectedBg: norm(root.getPropertyValue(tok.bg)),
      };
    }""", {"border": border_token, "bg": bg_token})
    assert result["border"] == result["expectedBorder"], result
    assert result["bg"] == result["expectedBg"], result


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
        page.evaluate("""() => {
          const list=document.querySelector('#setup-model-routes');list.replaceChildren();
          for(let i=0;i<160;i++){const item=document.createElement('option');item.value='ollama/catalog-'+i;list.append(item);}
        }""")
        field.fill("catalog")
        assert page.locator(".hc-suggestions").get_by_role("option").count() == 100
        assert "Showing 100 of 160" in page.locator(".hc-suggestions [role=status]").inner_text()
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


def test_late_model_catalog_does_not_open_a_dialog_after_navigation(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="late-catalog", model="mock/demo", tools=[]))
    page = browser.new_page()
    pending = []
    try:
        def delay_discovery(route):
            if "discover=1" in route.request.url:
                pending.append(route)
            else:
                route.continue_()
        page.route("**/api/bots/late-catalog/models*", delay_discovery)
        page.goto(base + "/#/chat/late-catalog")
        page.locator(".ms-btn").click()
        page.locator(".ms-more").click()
        page.locator('.ws-foot a[href="#/settings"]').click()
        page.locator("#workspace-settings-mode").wait_for()
        assert pending
        for route in pending:
            route.fulfill(json={"default": "mock/demo", "models": []})
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        assert page.locator("#modal-root [role=dialog]").count() == 0
    finally:
        page.close()


def test_action_menu_has_a_non_popover_api_fallback(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="fallback-control", model="mock/demo", tools=[]))
    context = browser.new_context(viewport={"width": 390, "height": 844})
    context.add_init_script("HTMLElement.prototype.showPopover = undefined")
    page = context.new_page()
    try:
        page.goto(base + "/#/bot/fallback-control")
        trigger = page.get_by_label("Assistant options", exact=True).first
        trigger.click()
        menu = page.get_by_role("menu", name="Assistant options")
        menu.wait_for(state="visible")
        assert_fits(page, menu)
        page.keyboard.press("End")
        assert page.get_by_role("menuitem", name="Delete assistant").evaluate("el => el === document.activeElement")
        page.keyboard.press("Escape")
        assert menu.is_hidden()
    finally:
        context.close()


def test_server_select_form_remains_usable_without_javascript(browser, live):
    base, app = live
    ConnectionBook(app.state.config.state_dir).add("openai-api")
    context = browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=False)
    page = context.new_page()
    try:
        page.goto(base + "/legacy/connections")
        window = page.get_by_label("Window", exact=True).first
        window.select_option("week")
        form = window.locator("xpath=..")
        data = form.evaluate("form => Object.fromEntries(new FormData(form))")
        assert data["window"] == "week" and "csrf" in data
        assert window.evaluate("el => getComputedStyle(el).fontSize") == "16px"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        out = artifact_path("dropdowns/server")
        out.mkdir(parents=True, exist_ok=True)
        window.click()
        page.screenshot(path=str(out / "no-javascript-phone.png"))
    finally:
        context.close()


def test_popup_edges_and_surfaces_match_design_tokens(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="token-match", model="mock/demo", tools=[]))
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        # App popover surface + edge.
        page.goto(base + "/#/chat/token-match")
        page.locator(".ms-btn").click()
        page.locator(".ms-menu").wait_for(state="visible")
        assert_uses_token(page, page.locator(".ms-menu"),
                          bg_token="--color-semantic-panel")
        page.keyboard.press("Escape")
        # Composer sheet surface + edge.
        page.locator("#composer-menu-btn").click()
        page.locator("#composer-menu").wait_for(state="visible")
        assert_uses_token(page, page.locator("#composer-menu"),
                          bg_token="--color-semantic-panel")
        page.keyboard.press("Escape")
        # Server-rendered native select field uses the same edge token.
        ConnectionBook(app.state.config.state_dir).add("openai-api")
        page.goto(base + "/legacy/connections")
        window = page.get_by_label("Window", exact=True).first
        window.wait_for()
        # Form fields use the 3:1 control edge (WCAG 1.4.11); popups keep the quieter strong border.
        assert_uses_token(page, window, bg_token="--color-semantic-bg", border_token="--color-semantic-border-edge")
        assert window.evaluate("el => getComputedStyle(el).minHeight") == "44px"
    finally:
        context.close()


def test_native_select_escape_closes_only_its_own_picker(browser, live):
    base, app = live
    app.state.store.create_bot(Bot(name="nested-selection", model="mock/demo", tools=[]))
    page = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        page.goto(base + "/#/chat/nested-selection")
        page.locator("#studio-conversation-options").click()
        picker = page.locator("#chat-workflow-mode")
        picker.click()
        assert picker.evaluate("el => el.matches(':open')")
        page.keyboard.press("Escape")
        assert not picker.evaluate("el => el.matches(':open')")
        assert page.locator(".conversation-actions-panel").is_visible()
        page.keyboard.press("Escape")
        assert page.locator(".conversation-actions-panel").is_hidden()
    finally:
        page.close()


@pytest.mark.parametrize("forced", [False, True])
def test_popup_reflow_spacing_and_focus_survive_accessibility_preferences(browser, live, forced):
    base, app = live
    app.state.store.create_bot(Bot(name="resilient-controls", model="mock/demo", tools=[]))
    context = browser.new_context(viewport={"width": 320, "height": 740}, reduced_motion="reduce",
                                  forced_colors="active" if forced else "none")
    page = context.new_page()
    try:
        page.goto(base + "/#/chat/resilient-controls")
        page.locator("#composer-menu-btn").wait_for()
        page.add_style_tag(content="""
          * { line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important; }
          p { margin-block-end: 2em !important; }
        """)
        page.locator("#composer-menu-btn").click()
        popup = page.locator("#composer-menu")
        assert_fits(page, popup)
        page.get_by_role("button", name="Review cost and context before sending").scroll_into_view_if_needed()
        assert_fits(page, page.get_by_role("button", name="Review cost and context before sending"))
        assert popup.locator(".hc-popup-close").is_visible(), "sticky dismiss remains reachable after scrolling"
        page.keyboard.press("Escape")
        assert page.locator("#composer-menu-btn").evaluate("el => el === document.activeElement")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        if not forced:
            # Canvas converts CSS color-mix output to sRGB for measured contrast.
            ratios = page.evaluate("""() => {
              const el=document.querySelector('#chat-workflow-mode');
              const s=getComputedStyle(el), canvas=document.createElement('canvas'); canvas.width=canvas.height=1;
              const ctx=canvas.getContext('2d');
              const rgb=c=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=c;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data].slice(0,3);};
              const l=c=>rgb(c).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((v,x,i)=>v+x*[.2126,.7152,.0722][i],0);
              const ratio=(a,b)=>{a=l(a);b=l(b);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);};
              return {text:ratio(s.color,s.backgroundColor),border:ratio(s.borderTopColor,s.backgroundColor)};
            }""")
            assert ratios["text"] >= 4.5 and ratios["border"] >= 3, ratios
        out = artifact_path("dropdowns/resilience")
        out.mkdir(parents=True, exist_ok=True)
        page.locator("#composer-menu-btn").click()
        page.screenshot(path=str(out / f"spacing-forced-{forced}.png"))
    finally:
        context.close()
