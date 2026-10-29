"""Live-browser check of the two-step fact-purge control in the SPA saved-notes pane."""
from __future__ import annotations

import json
import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.e2e.settings_pane import open_assistant_customization  # noqa: E402
from tests.support.artifacts import artifact_path  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402

SENTINEL = 'PRIVATEPURGEUISENTINEL'


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        instance = launch_browser(p)
        yield instance
        instance.close()


@pytest.fixture()
def live(tmp_path, monkeypatch, browser):
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


@pytest.mark.parametrize('label,width,height', [('desktop', 1440, 960), ('phone', 390, 844)])
def test_purge_needs_the_exact_key_then_erases_and_refreshes_saved_notes(browser, live, label, width, height):
    base, app = live
    store = app.state.store
    bot = store.create_bot(Bot(name=f"purge-ui-{label}", display_name="Purge UI"))
    conversation, _ = store.create_conversation(bot.id, "purge-ui-chat", idem_key="purge-ui-chat",
                                                request_hash="purge-ui-chat")
    fact = store.remember(bot.id, "favourite-colour", SENTINEL, conversation_id=conversation["id"])
    store.review_fact(bot.id, fact.id, content_hash=fact.content_hash, action="approve", actor="fixture")
    context = browser.new_context(viewport={"width": width, "height": height},
                                  is_mobile=width <= 640, has_touch=width <= 640,
                                  reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{base}/#/bot/{bot.name}")
        open_assistant_customization(page, "limits")
        page.locator("#fact-purge-root [data-fact-purge-step='1']").wait_for(state="visible", timeout=15_000)
        page.select_option("[data-fact-purge-key]", "favourite-colour")
        preview_box = page.locator("[data-fact-purge-preview]").bounding_box()
        page.click("[data-fact-purge-preview]")
        step_two = page.locator("[data-fact-purge-step='2']")
        step_two.wait_for(state="visible", timeout=15_000)
        assert page.evaluate("document.activeElement && document.activeElement.hasAttribute('data-fact-purge-confirmation')")
        assert step_two.locator("[data-fact-purge-count='fact_revisions']").inner_text().strip() == "1"
        assert step_two.locator("[data-fact-purge-count='total']").inner_text().strip() == "1"
        remaining = step_two.locator("[data-fact-purge-remaining] li").all_inner_texts()
        assert any("transcripts" in item for item in remaining)
        assert any("backups" in item for item in remaining)
        metrics = page.evaluate("""() => {
          const root = document.querySelector('#fact-purge-root').getBoundingClientRect();
          const confirm = document.querySelector('[data-fact-purge-confirm]').getBoundingClientRect();
          return {viewport: [innerWidth, innerHeight],
                  document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
                  root: {left: root.left, right: root.right, width: root.width},
                  confirm: {top: confirm.top, bottom: confirm.bottom, height: confirm.height}};
        }""")
        assert metrics['root']['left'] >= -1 and metrics['root']['right'] <= width + 1, (label, metrics)
        if width <= 640:
            # The SPA shell's base .btn target is 40px; the 44px coarse-pointer rule lives in the
            # server-page hutch.css that the parked dashboard session is still migrating in.
            assert preview_box["height"] >= 40, (label, preview_box)
            assert metrics["confirm"]["height"] >= 40, (label, metrics)
        out = artifact_path("fact-purge-control")
        out.mkdir(parents=True, exist_ok=True)
        screenshot = out / f"{label}.png"
        page.screenshot(path=str(screenshot), animations="disabled")
        (out / f"{label}.json").write_text(json.dumps({
            'test': 'tests/e2e/test_fact_purge_ui.py',
            'browser': browser.browser_type.name, 'browser_version': browser.version,
            'viewport': [width, height], 'page_errors': errors,
            'control_within_viewport': metrics['root']['left'] >= -1 and metrics['root']['right'] <= width + 1,
            'preview_height_px': round(preview_box['height']),
            'confirm_height_px': round(metrics['confirm']['height']),
            'remaining_items': len(remaining),
            'screenshot': screenshot.name,
        }, indent=2) + '\n', encoding='utf-8')
        confirm = page.locator("[data-fact-purge-confirm]")
        assert confirm.is_disabled()
        page.fill("[data-fact-purge-confirmation]", "wrong-key")
        assert confirm.is_disabled()
        page.fill("[data-fact-purge-confirmation]", "favourite-colour")
        assert not confirm.is_disabled()
        confirm.click()
        success = page.locator("[data-fact-purge-success]")
        success.wait_for(state="visible", timeout=15_000)
        assert "Erased 1 saved copy." in success.inner_text()
        assert page.evaluate("document.activeElement && document.activeElement.hasAttribute('data-fact-purge-success')")
        assert any("transcripts" in item
                   for item in success.locator("[data-fact-purge-remaining] li").all_inner_texts())
        # Showing the outcome delays the saved-notes refresh, which re-renders this panel.
        success.wait_for(state="detached", timeout=15_000)
        page.locator("#fact-purge-root [data-fact-purge-step='1']").wait_for(state="visible", timeout=15_000)
        assert store.recall_all(bot.id) == []
        assert errors == []
    finally:
        context.close()
