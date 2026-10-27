"""Workspace reconciliation and native fonts must preserve usable controls."""
from playwright.sync_api import expect

from hutch.models import Bot, Schedule
from tests.e2e.test_design_system import app_server, browser  # noqa: F401
from tests.support.artifacts import artifact_path


def test_unchanged_schedule_refresh_preserves_rows_details_and_focus(browser, app_server, monkeypatch):
    base, app = app_server
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    bot = app.state.store.create_bot(Bot(name='stable-schedule', model='mock/demo',
        schedules=[Schedule(cron='0 9 * * 1', timezone='America/Vancouver', prompt='Prepare the report.')]))
    context = browser.new_context(reduced_motion='reduce')
    page = context.new_page()
    try:
        page.goto(base + '/#/schedules')
        row = page.locator(f'[data-schedule-id="{bot.schedules[0].id}"]')
        expect(row).to_be_visible()
        row.locator('summary').click()
        row.get_by_role('button', name='Skip next', exact=True).focus()
        result = page.evaluate('''async () => {
          const row = document.querySelector('.schedule-overview-row');
          const focused = document.activeElement;
          await renderSchedules();
          return {same: row === document.querySelector('.schedule-overview-row'),
            focus: focused === document.activeElement,
            details: document.querySelector('.schedule-overview-details').open};
        }''')
        assert result == {'same': True, 'focus': True, 'details': True}, result

        # A genuine saved change still updates the authoritative status.
        fresh = app.state.store.get_bot(bot.id)
        fresh.paused = True
        app.state.store.upsert_bot(fresh)
        page.evaluate('async () => { await renderSchedules(); }')
        expect(row).to_contain_text('Paused for this assistant')
        assert row.locator('details').evaluate('el => el.open')
        assert row.get_by_role('button', name='Skip next', exact=True).evaluate('el => el === document.activeElement')
        page.evaluate("name => location.hash = '#/chat/' + name", bot.name)
        expect(page.locator('#chat-prompt')).to_be_visible()
        page.evaluate('async () => { await renderSchedules(); }')
        expect(page.locator('#chat-prompt')).to_be_visible()
    finally:
        context.close()


def test_roster_fits_typical_names_with_a_wider_system_font(browser, app_server, monkeypatch):
    base, app = app_server
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    bot = app.state.store.create_bot(Bot(name='wide-system-font', display_name='Workspace Coordinator',
                                        model='mock/demo', tools=[]))
    app.state.store.set_workspace_coordinator(bot.id)
    context = browser.new_context(viewport={'width': 1440, 'height': 960})
    page = context.new_page()
    try:
        page.goto(base + '/#/chat')
        # Preserve the configured system-font architecture; exercise a common
        # wider Linux fallback rather than shrinking the shared type scale.
        page.add_style_tag(content=':root { --font-body: "DejaVu Sans", sans-serif; }')
        name = page.locator('#roster-list .roster-name').filter(has_text='Workspace Coordinator')
        expect(name).to_be_visible()
        page.evaluate('document.fonts.ready')
        metrics = name.evaluate('el => ({width: el.clientWidth, textWidth: el.scrollWidth, font: getComputedStyle(el).fontSize})')
        assert metrics['font'] == '14px' and metrics['textWidth'] <= metrics['width'] + 1, metrics
        out = artifact_path('workspace-stability')
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / 'system-font-desktop.png'), animations='disabled')
    finally:
        context.close()


def test_late_assistant_directory_cannot_redirect_an_open_settings_page(browser, app_server, monkeypatch):
    base, app = app_server
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    bot = app.state.store.create_bot(Bot(name='owned-settings', model='mock/demo', tools=[]))
    context = browser.new_context(reduced_motion='reduce')
    page = context.new_page()
    held = []
    try:
        page.goto(base + '/#/chat/' + bot.name)
        expect(page.locator('#chat-prompt')).to_be_visible()

        def hold(route):
            if not held and page.url.endswith('#/bots'):
                held.append((route, route.fetch()))
                page.evaluate('window.directoryHeld = true')
            else:
                route.continue_()

        page.route('**/api/bots', hold)
        page.evaluate("() => { history.replaceState(null, '', '#/bots'); window.pendingDirectory = renderBots(); }")
        page.wait_for_function('() => window.directoryHeld === true')
        assert len(held) == 1
        page.evaluate("name => location.hash = '#/bot/' + name", bot.name)
        expect(page.locator('#assistant-more-settings')).to_be_attached()
        route, response = held.pop()
        route.fulfill(response=response)
        page.evaluate('async () => { await window.pendingDirectory; }')
        assert page.url.endswith('#/bot/' + bot.name)
        expect(page.locator('#assistant-more-settings')).to_be_attached()
    finally:
        for route, _ in held:
            route.abort()
        context.close()


def test_unchanged_roster_refresh_preserves_open_menu_and_focus(browser, app_server, monkeypatch):
    base, app = app_server
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    bot = app.state.store.create_bot(Bot(name='stable-roster', model='mock/demo', tools=[]))
    context = browser.new_context(reduced_motion='reduce')
    page = context.new_page()
    try:
        page.goto(base + '/#/chat/' + bot.name)
        expect(page.locator('#chat-prompt')).to_be_visible()
        page.locator('[data-bot-options="stable-roster"]').click()
        menu = page.locator('#roster-action-menu')
        expect(menu).to_be_visible()
        menu.get_by_role('menuitem', name='Pin to sidebar', exact=True).focus()
        state = page.evaluate('''() => {
          const row = document.querySelector('[data-switch-bot="stable-roster"]');
          const menu = document.querySelector('#roster-action-menu');
          const focused = document.activeElement;
          renderRoster();
          return {row: row.isConnected, menu: menu.isConnected, focus: focused === document.activeElement};
        }''')
        assert state == {'row': True, 'menu': True, 'focus': True}
        # Search changes still repaint the directory instead of freezing it.
        page.locator('#bot-search').fill('no-match-for-this-assistant')
        expect(page.get_by_text('No assistant matches.', exact=True)).to_be_visible()
    finally:
        context.close()
