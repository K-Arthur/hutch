"""Explicit hybrid preferences in the live app; local fixtures, no model call."""
import json

from playwright.sync_api import expect

from hutch.models import Bot
from tests.e2e.test_design_system import app_server, browser  # noqa: F401
from tests.support.artifacts import artifact_path


def test_hybrid_learning_is_visible_scoped_reviewable_and_reversible(browser, app_server, monkeypatch):
    base, app = app_server
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    store = app.state.store
    bot = store.create_bot(Bot(name='hybrid-learning', display_name='Learning Partner', model='mock/demo',
                               tools=['memory'], memory_learning='hybrid'))
    context = browser.new_context(reduced_motion='reduce')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    out = artifact_path('hybrid-learning')
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(f'{base}/#/chat/{bot.name}')
        page.locator('#chat-prompt').wait_for()
        home = page.request.get(f'{base}/api/v1/bots/{bot.id}/home-conversation').json()['conversation']['id']
        sent = page.request.post(f'{base}/api/v1/conversations/{home}/messages',
                                 data={'prompt': 'I prefer concise answers.'},
                                 headers={'Idempotency-Key': 'hybrid-preference'})
        assert sent.status == 201, sent.text()
        preferences = page.get_by_role('region', name='Formatting preferences')
        # A section with a name is a region; it stays visible above collapsed tool output.
        expect(preferences.get_by_text('Use concise answers.', exact=True)).to_be_visible()
        expect(preferences.get_by_text('Saved automatically from your messages in this chat.')).to_be_visible()
        fact = store.recall_fact_page(bot.id, conversation_id=home)[0]
        for width, height in ((1440, 960), (390, 844), (320, 740)):
            page.set_viewport_size({'width': width, 'height': height})
            preferences.scroll_into_view_if_needed()
            page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth - innerWidth') <= 1
            assert preferences.get_by_role('button', name='Undo', exact=True).bounding_box()['height'] >= 44
            preferences.screenshot(path=str(out / f'preferences-{width}.png'), animations='disabled')
        styles = preferences.evaluate("""region => {
          const targets = region.querySelectorAll('button');
          return {fontSize: getComputedStyle(region).fontSize,
            buttons: [...targets].map(button => ({fontSize: getComputedStyle(button).fontSize,
              height: button.getBoundingClientRect().height}))};
        }""")
        spacing = page.add_style_tag(content='''
          .learning-preferences, .learning-preferences * {
            line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important;
          }
          .learning-preferences p { margin-bottom: 2em !important; }
        ''')
        assert page.evaluate('document.documentElement.scrollWidth - innerWidth') <= 1
        for button in preferences.get_by_role('button').all():
            expect(button).to_be_visible()
            box = button.bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= 321
            assert button.evaluate('el => el.scrollHeight <= el.clientHeight + 1')
        preferences.screenshot(path=str(out / 'preferences-text-spacing-320.png'), animations='disabled')
        spacing.evaluate('el => el.remove()')
        preferences.get_by_role('button', name='Details for Use concise answers.').click()
        dialog = page.get_by_role('dialog', name='Reference fact history')
        expect(dialog).to_contain_text(fact['learning']['source_message_id'])
        expect(dialog).to_contain_text('Automatic formatting decision')
        assert page.evaluate('document.documentElement.scrollWidth - innerWidth') <= 1
        dialog.screenshot(path=str(out / 'provenance-320.png'), animations='disabled')
        dialog.get_by_role('button', name='Close', exact=True).click()

        def refuse_undo(route):
            route.fulfill(status=503, json={'detail': 'fixture retryable failure'})
        undo_path = f'**/api/v1/bots/{bot.name}/facts/{fact["id"]}/review'
        page.route(undo_path, refuse_undo)
        preferences.get_by_role('button', name='Undo', exact=True).click()
        expect(page.get_by_text('Could not undo this preference: fixture retryable failure', exact=True)).to_be_visible()
        expect(preferences.get_by_role('button', name='Undo', exact=True)).to_be_enabled()
        assert store.recall_fact_page(bot.id, conversation_id=home)
        page.screenshot(path=str(out / 'undo-error-320.png'), animations='disabled')
        page.unroute(undo_path, refuse_undo)
        preferences.get_by_role('button', name='Undo', exact=True).click()
        expect(preferences).to_have_count(0)
        assert store.recall_fact_page(bot.id, conversation_id=home) == []
        assert store.list_conversation_messages(home)[0]['content'] == 'I prefer concise answers.'

        while page.get_by_role('button', name='Dismiss notification').count():
            page.get_by_role('button', name='Dismiss notification').first.click()

        page.goto(f'{base}/#/bot/{bot.name}')
        page.locator('#assistant-more-settings > summary').click()
        policy = page.get_by_label('Memory and learning', exact=True)
        expect(policy).to_have_value('hybrid')
        with page.expect_response(lambda response: response.request.method == 'PATCH'
                                  and response.url.endswith('/api/bots/' + bot.name)) as changed:
            policy.select_option('review')
        assert changed.value.status == 200
        expect(policy).to_have_value('review')
        expect(policy).to_be_enabled()
        assert store.get_bot(bot.id).memory_learning == 'review'
        while page.get_by_role('button', name='Dismiss notification').count():
            page.get_by_role('button', name='Dismiss notification').first.click()
        for width, height in ((1440, 960), (320, 740)):
            page.set_viewport_size({'width': width, 'height': height})
            policy.scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth - innerWidth') <= 1
            page.screenshot(path=str(out / f'settings-{width}.png'), animations='disabled')
        assert not errors, errors
        (out / 'validation.json').write_text(json.dumps({'browser': browser.version,
            'viewports': [[1440, 960], [390, 844], [320, 740]], 'page_errors': errors,
            'computed_styles': styles, 'text_spacing_override': '1.5 / 2em / .12em / .16em at 320 CSS px',
            'browser_zoom_200_percent': 'not verified by this headless journey',
            'scope': 'synthetic canonical preference; no provider calls; source retained after undo'}, indent=2) + '\n')
    finally:
        context.close()


def test_learning_settings_recover_errors_and_do_not_replace_a_new_chat(browser, app_server, monkeypatch):
    base, app = app_server
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    bot = app.state.store.create_bot(Bot(name='learning-settings', model='mock/demo'))
    context = browser.new_context(reduced_motion='reduce')
    page = context.new_page()
    path = f'**/api/bots/{bot.name}'
    held = []
    try:
        page.goto(f'{base}/#/bot/{bot.name}')
        page.locator('#assistant-more-settings > summary').click()
        policy = page.get_by_label('Memory and learning', exact=True)

        def refuse(route):
            if route.request.method == 'PATCH':
                route.fulfill(status=503, json={'detail': 'fixture unavailable'})
            else:
                route.continue_()

        page.route(path, refuse)
        policy.select_option('off')
        expect(page.get_by_text('Not saved: fixture unavailable', exact=True)).to_be_visible()
        expect(policy).to_have_value('hybrid')
        expect(policy).to_be_enabled()
        assert app.state.store.get_bot(bot.id).memory_enabled
        page.unroute(path, refuse)

        # The owner changes the policy elsewhere while this form stays open.
        changed = page.request.patch(f'{base}/api/bots/{bot.name}', data={'memory_learning': 'review'})
        assert changed.status == 200
        policy.select_option('off')
        expect(page.get_by_text('Not saved: Memory settings changed. Reload them before saving again.', exact=True)).to_be_visible()
        assert app.state.store.get_bot(bot.id).memory_enabled
        page.reload()
        page.locator('#assistant-more-settings > summary').click()
        expect(policy).to_have_value('review')

        def hold(route):
            if route.request.method == 'PATCH':
                held.append((route, route.fetch()))
                page.evaluate('window.learningSaveHeld = true')
            else:
                route.continue_()

        page.route(path, hold)
        policy.select_option('off')
        expect(policy).to_be_disabled()
        page.wait_for_function('() => window.learningSaveHeld === true')
        assert len(held) == 1
        page.evaluate("name => location.hash = '#/chat/' + name", bot.name)
        expect(page.locator('#chat-prompt')).to_be_visible()
        route, response = held.pop()
        route.fulfill(response=response)
        expect(page.get_by_text('Memory disabled.', exact=True)).to_be_visible()
        expect(page.locator('#chat-prompt')).to_be_visible()
        expect(page.locator('#memory-toggle')).to_have_count(0)
        assert app.state.store.get_bot(bot.id).memory_enabled is False
    finally:
        try:
            page.unroute_all(behavior='wait')
            for route, _ in held:
                route.abort()
        finally:
            context.close()


def test_successful_memory_save_is_not_reported_as_unsaved_after_readback_failure(browser, app_server, monkeypatch):
    base, app = app_server
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    bot = app.state.store.create_bot(Bot(name='learning-readback', model='mock/demo'))
    context = browser.new_context(reduced_motion='reduce')
    page = context.new_page()
    saved = []
    try:
        page.goto(f'{base}/#/bot/{bot.name}')
        page.locator('#assistant-more-settings > summary').click()

        def fail_readback(route):
            if route.request.method == 'PATCH':
                response = route.fetch()
                saved.append(response.status)
                route.fulfill(response=response)
            elif saved:
                route.fulfill(status=503, json={'detail': 'fixture readback unavailable'})
            else:
                route.continue_()

        page.route(f'**/api/bots/{bot.name}', fail_readback)
        policy = page.get_by_label('Memory and learning', exact=True)
        policy.select_option('off')
        expect(page.get_by_text('Saved, but settings could not refresh.', exact=False)).to_be_visible()
        expect(page.get_by_text('Not saved:', exact=False)).to_have_count(0)
        expect(policy).to_have_value('off')
        expect(policy).to_be_enabled()
        assert saved == [200] and app.state.store.get_bot(bot.id).memory_enabled is False
    finally:
        context.close()
