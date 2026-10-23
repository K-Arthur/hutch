"""Navigation and recovery boundaries for the assistant setup task page."""

import json

from playwright.sync_api import expect

from tests.e2e.test_design_system import app_server, browser  # noqa: F401


def _setup_page(browser, app_server):
    base, app = app_server
    app.state.store.kv_set("workspace:model-defaults", json.dumps({
        "configured": True, "model": "openai/gpt-4o-mini", "inference_mode": "hybrid",
    }))
    context = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    page = context.new_page()
    page.goto(base + "/#/assistant/new")
    page.locator("#setup-page-confirm").wait_for()
    return context, page, base, app


def test_setup_draft_survives_immediate_reload_and_discard_cannot_resurrect_it(browser, app_server):
    context, page, base, _app = _setup_page(browser, app_server)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.locator("#setup-purpose").fill("Prepare a weekly plan from my notes.")
        page.locator("#setup-display_name").fill("My planning assistant")
        # No debounce wait: pagehide must flush the current edit.
        page.reload()
        expect(page.locator("#setup-display_name")).to_have_value("My planning assistant")
        expect(page.locator("#setup-purpose")).to_have_value("Prepare a weekly plan from my notes.")
        expect(page.locator(".setup-restored")).to_be_visible()
        # A second tab must not inherit this draft.
        other = context.new_page()
        other.goto(base + "/#/assistant/new")
        expect(other.locator("#setup-purpose")).to_have_value("")
        other.close()

        page.locator("#setup-purpose").fill("A pending edit just before discard")
        page.locator("#setup-discard-actions").click()
        expect(page.locator(".setup-page")).to_have_count(0)
        page.wait_for_timeout(350)
        assert page.evaluate("sessionStorage.getItem('hutch-assistant-setup-draft')") is None
        page.goto(base + "/#/assistant/new")
        expect(page.locator("#setup-purpose")).to_have_value("")
        assert not errors
    finally:
        context.close()


def test_leaving_during_setup_loading_does_not_take_over_the_next_page(browser, app_server):
    base, _app = app_server
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    pending = []
    page.route("**/api/bots/templates", lambda route: pending.append(route))
    try:
        page.goto(base + "/#/assistant/new", wait_until="domcontentloaded")
        expect(page.get_by_role("status").filter(has_text="Loading assistant setup")).to_be_visible()
        page.evaluate("location.hash = '#/settings'")
        expect(page.locator("#workspace-settings-form")).to_be_visible()
        assert pending
        for route in pending:
            route.fulfill(status=200, json=[])
        page.wait_for_timeout(500)
        expect(page.locator("#workspace-settings-form")).to_be_visible()
        assert page.evaluate("location.hash") == "#/settings"
        assert page.locator(".setup-page").count() == 0
    finally:
        context.close()


def test_setup_inline_validation_and_create_clear_only_the_completed_draft(browser, app_server, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    context, page, _base, app = _setup_page(browser, app_server)
    try:
        before = len(app.state.store.list_bots())
        page.locator("#setup-page-confirm").click()
        expect(page.locator("#bot-setup-error")).to_have_text("Describe what this bot should handle.")
        expect(page.locator("#setup-purpose")).to_be_focused()
        page.locator("#setup-purpose").fill("Summarize the notes I provide.")
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                  and response.request.method == "POST") as created:
            page.locator("#setup-page-confirm").click()
        assert created.value.status == 201, created.value.text()
        expect(page.locator(".setup-page")).to_have_count(0)
        page.wait_for_timeout(350)
        assert page.evaluate("sessionStorage.getItem('hutch-assistant-setup-draft')") is None
        assert len(app.state.store.list_bots()) == before + 1
        assert app.state.store.list_runs() == []
    finally:
        context.close()


def test_starting_an_example_requires_permission_to_replace_an_unsaved_draft(browser, app_server):
    context, page, _base, _app = _setup_page(browser, app_server)
    try:
        purpose = "Keep this unsaved planning request."
        page.locator("#setup-purpose").fill(purpose)
        page.locator("#setup-save-leave").click()
        page.locator("#tpl-gal > summary").click()
        page.locator("#tpl-grid .tpl-card").first.click()
        expect(page.get_by_role("dialog", name="Replace your unsaved setup?")).to_be_visible()
        page.locator("#modal-cancel").click()
        page.locator("#nav-toggle").click()
        page.locator("#topbar-new-bot").click()
        expect(page.locator("#setup-purpose")).to_have_value(purpose)
        page.locator("#setup-save-leave").click()
        page.locator("#tpl-gal > summary").click()
        page.locator("#tpl-grid .tpl-card").first.click()
        page.locator("#modal-confirm").click()
        expect(page.locator("#setup-purpose")).to_have_value("")
        page.reload()
        expect(page.locator("#setup-purpose")).to_have_value("")
    finally:
        context.close()


def test_delayed_creation_does_not_navigate_away_from_the_users_next_task(browser, app_server, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-never-sent-to-a-provider")
    context, page, _base, app = _setup_page(browser, app_server)
    pending = []
    page.route("**/api/v1/bots", lambda route: pending.append(route)
               if route.request.method == "POST" else route.continue_())
    try:
        page.locator("#setup-purpose").fill("Summarize notes without starting any work yet.")
        page.locator("#setup-page-confirm").click()
        expect(page.locator("#setup-page-confirm")).to_be_disabled()
        page.evaluate("location.hash = '#/settings'")
        expect(page.locator("#workspace-settings-form")).to_be_visible()
        assert len(pending) == 1
        with page.expect_response(lambda response: response.url.endswith("/api/v1/bots")
                                  and response.request.method == "POST") as created:
            pending[0].continue_()
        assert created.value.status == 201, created.value.text()
        expect(page.locator("#workspace-settings-form")).to_be_visible()
        expect(page.locator(".toast").filter(has_text="It has not started a run")).to_be_visible()
        assert page.evaluate("location.hash") == "#/settings"
        assert page.evaluate("sessionStorage.getItem('hutch-assistant-setup-draft')") is None
        assert app.state.store.list_runs() == []
    finally:
        context.close()


def test_failed_replacement_loading_leaves_the_original_draft_editable(browser, app_server):
    context, page, _base, _app = _setup_page(browser, app_server)
    try:
        purpose = "Keep my draft if the example cannot load."
        page.locator("#setup-purpose").fill(purpose)
        page.locator("#setup-save-leave").click()
        page.locator("#tpl-gal > summary").click()
        page.route("**/api/bots/templates", lambda route: route.fulfill(
            status=503, json={"detail": "Setup examples are temporarily unavailable"}))
        page.locator("#tpl-grid .tpl-card").first.click()
        page.locator("#modal-confirm").click()
        expect(page.locator(".toast").filter(has_text="Bot setup is unavailable")).to_be_visible()
        page.locator("#nav-toggle").click()
        page.locator("#topbar-new-bot").click()
        expect(page.locator("#setup-purpose")).to_have_value(purpose)
        page.locator("#setup-customize").click()
        expect(page.get_by_role("heading", name="Choose what powers it")).to_be_visible()
        page.locator("#setup-back").click()
        expect(page.locator("#setup-purpose")).to_have_value(purpose)
    finally:
        context.close()
