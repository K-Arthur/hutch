"""Representative output widgets in the real run transcript and shared shell."""

import json
from pathlib import Path

from playwright.sync_api import expect

from hutch.models import Event, EventType, Run, RunStatus
from tests.e2e.test_design_system import app_server, browser  # noqa: F401
from tests.support.artifacts import artifact_path


def test_typed_output_widgets_fit_the_run_transcript_at_responsive_sizes(browser, app_server):
    base, app = app_server
    store = app.state.store
    bot = store.get_bot("design-system-review")
    run = store.create_run(Run(bot_id=bot.id, prompt="Review these synthetic output examples.",
        status=RunStatus.succeeded, exit_reason="completed"))
    fixtures = Path(__file__).resolve().parents[1] / "fixtures/blocks"
    kinds = ("text", "table", "chart", "comparison", "flowchart", "status", "timeline", "code_receipt")
    for index, kind in enumerate(kinds):
        block = json.loads((fixtures / f"{kind}.json").read_text())
        block["provenance"]["run_id"] = run.id
        store.append_event(Event(run_id=run.id, type=EventType.tool_call,
            data={"tool": "shell", "call_id": f"widget-{index}", "args": {"example": kind}}))
        store.append_event(Event(run_id=run.id, type=EventType.tool_result,
            data={"tool": "shell", "call_id": f"widget-{index}", "ok": True,
                  "output": block["text_fallback"], "blocks": [block]}))
    store.flush_events()
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = artifact_path("holistic-experience/widgets")
    out.mkdir(parents=True, exist_ok=True)
    try:
        for width, height in ((1440, 960), (900, 1024), (390, 844), (320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{base}/#/run/{run.id}")
            # Grouped tool output stays an explicit disclosure in the product.
            cards = page.locator(".widget-card")
            expect(cards).to_have_count(len(kinds))
            stream = page.locator(".tool-stream:not([open]) > summary")
            if stream.count():
                stream.first.click()
            for group in page.locator('[data-group-toggle][aria-expanded="false"]').all():
                group.click()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            for index, kind in enumerate(kinds):
                card = cards.nth(index)
                card.scroll_into_view_if_needed()
                box = card.bounding_box()
                assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1
                card.screenshot(path=str(out / f"{kind}-{width}.png"), animations="disabled")
        assert not errors, errors
    finally:
        context.close()


def test_active_server_rendered_pages_share_type_and_readable_layout(browser, app_server):
    base, _app = app_server
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    out = artifact_path("holistic-experience/server-pages")
    out.mkdir(parents=True, exist_ok=True)
    try:
        for width, height in ((1440, 960), (900, 1024), (390, 844), (320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            for name, route in (("models", "/models"), ("usage", "/usage"),
                                ("assistant", "/bots/design-system-review"),
                                ("legacy-connections", "/legacy/connections"),
                                ("login", "/login"), ("pair", "/pair"), ("error", "/not-a-page")):
                page.goto(base + route)
                expect(page.locator("main h1")).to_be_visible()
                page.evaluate("document.fonts.ready")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (name, width)
                assert page.locator("body").evaluate("el => getComputedStyle(el).fontSize") == "16px"
                assert page.locator("main h1").evaluate("el => getComputedStyle(el).fontSize") == "24px"
                if name == "assistant":
                    assert page.locator(".estimate strong").bounding_box()["height"] < 30
                page.screenshot(path=str(out / f"{name}-{width}.png"), animations="disabled")
        page.set_viewport_size({"width": 1440, "height": 960})
        page.goto(base + "/usage")
        page.evaluate("document.documentElement.style.fontSize = '200%'")
        assert page.locator("body").evaluate("el => getComputedStyle(el).fontSize") == "32px"
        assert page.locator("main h1").evaluate("el => getComputedStyle(el).fontSize") == "48px"
    finally:
        context.close()


def test_unchanged_completed_transcript_keeps_widgets_and_focus_during_other_run_changes(browser, app_server, monkeypatch):
    """A global change notification is not a reason to discard an owned widget."""
    base, app = app_server
    store = app.state.store
    bot = store.get_bot("design-system-review")
    run = store.create_run(Run(bot_id=bot.id, prompt="Keep this completed result open.",
        status=RunStatus.succeeded, exit_reason="completed"))
    block = json.loads((Path(__file__).resolve().parents[1] / "fixtures/blocks/table.json").read_text())
    block['provenance']['run_id'] = run.id
    store.append_event(Event(run_id=run.id, type=EventType.tool_call,
        data={"tool": "shell", "call_id": "stable-widget", "args": {}}))
    store.append_event(Event(run_id=run.id, type=EventType.tool_result,
        data={"tool": "shell", "call_id": "stable-widget", "ok": True,
              "output": block['text_fallback'], "blocks": [block]}))
    store.flush_events()
    real_status = store._mirror.status
    mirror_state = {'pending': True, 'error': ''}
    def status(run_id):
        info = real_status(run_id)
        return {**info, **mirror_state} if run_id == run.id else info
    monkeypatch.setattr(store._mirror, 'status', status)
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    try:
        with page.expect_response(lambda response: '/api/v1/changes/stream?' in response.url):
            page.goto(f"{base}/#/run/{run.id}")
        expect(page.locator(".widget-card")).to_have_count(1)
        page.locator('#run-technical-details > summary').focus()
        card = page.locator('.widget-card').element_handle()
        focus = page.locator('#run-technical-details > summary').element_handle()
        expect(page.locator('[data-run-mirror-notice]')).to_contain_text('catching up')
        mirror_state['pending'] = False
        with page.expect_response(lambda response: response.url.endswith('/api/runs/' + run.id)):
            store.create_run(Run(bot_id=bot.id, prompt="Another completed task.",
                status=RunStatus.succeeded, exit_reason="completed"))
        # Cover the scheduled render after its metadata request, including a
        # second transcript request in the previous implementation.
        page.wait_for_timeout(750)
        assert card.evaluate('node => node.isConnected'), 'unchanged widget was discarded'
        assert focus.evaluate('node => node === document.activeElement'), 'unchanged transcript lost keyboard focus'
        expect(page.locator('[data-run-mirror-notice]')).to_be_empty()
        mirror_state['error'] = 'Fixture mirror needs recovery.'
        store.create_run(Run(bot_id=bot.id, prompt="Another resource update.",
            status=RunStatus.succeeded, exit_reason="completed"))
        expect(page.locator('[data-run-mirror-notice]')).to_contain_text('Fixture mirror needs recovery.')
        assert card.evaluate('node => node.isConnected'), 'mirror error discarded the widget'
        store.append_event(Event(run_id=run.id, type=EventType.message,
            data={'role': 'assistant', 'content': 'A newly recorded correction remains visible.'}))
        store.flush_events()
        expect(page.get_by_text('A newly recorded correction remains visible.', exact=True)).to_be_visible()
    finally:
        context.close()


def test_run_transcript_uses_the_same_saved_identity_as_the_assistant_roster(browser, app_server):
    base, app = app_server
    bot = app.state.store.get_bot("design-system-review")
    run = app.state.store.create_run(Run(bot_id=bot.id, prompt="Review identity consistency.",
        status=RunStatus.succeeded, exit_reason="completed"))
    app.state.store.append_event(Event(run_id=run.id, type=EventType.message,
        data={"role": "assistant", "content": "My identity stays the same across your workspace."}))
    app.state.store.flush_events()
    context = browser.new_context(reduced_motion="reduce")
    context.add_init_script("localStorage.setItem('hutch:sigils', JSON.stringify({'design-system-review': [4, 2]}))")
    page = context.new_page()
    out = artifact_path("holistic-experience/identity")
    out.mkdir(parents=True, exist_ok=True)
    try:
        for width, height in ((1440, 960), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{base}/#/run/{run.id}")
            avatar = page.locator(".mhead .avatar svg")
            expect(avatar).to_be_visible()
            roster = page.locator('[data-switch-bot="design-system-review"] .avatar svg')
            assert avatar.inner_html() == roster.inner_html()
            assert page.locator(".mhead b").inner_text() == "Design Partner"
            page.screenshot(path=str(out / f"run-identity-{width}.png"), animations="disabled")
    finally:
        context.close()
