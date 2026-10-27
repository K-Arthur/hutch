"""Account-wide spending controls use real settings/ledger APIs, without model calls."""
import json
from datetime import timedelta

from playwright.sync_api import expect

from hutch.connections import ConnectionBook
from hutch.models import Bot, Run, utcnow
from tests.e2e.test_design_system import app_server, browser  # noqa: F401
from tests.support.artifacts import artifact_path


def test_shared_account_spending_preview_save_conflict_and_recovery(browser, app_server, monkeypatch):
    base, app = app_server
    monkeypatch.setattr(app.state.engine, 'tick', lambda: None)
    book = ConnectionBook(app.state.config.state_dir)
    book.add('openrouter', 'research-models', title='Research models', account_id='shared-budget')
    book.add('openrouter', 'writing-models', title='Writing models', account_id='shared-budget')
    bot = app.state.store.create_bot(Bot(name='account-spending-fixture', model='mock/demo', tools=[]))
    run = app.state.store.create_run(Run(bot_id=bot.id, prompt='Synthetic past usage'))
    now = utcnow()
    with monkeypatch.context() as clock:
        clock.setattr('hutch.store.utcnow', lambda: now - timedelta(days=2))
        app.state.store.add_usage(run.id, bot.id, 'research-models', 'fixture', 10, 5,
                                  cost_usd=.4, account_id='shared-budget')
    context = browser.new_context(reduced_motion='reduce', viewport={'width': 1440, 'height': 960})
    page = context.new_page()
    errors = []
    held = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    out = artifact_path('account-spending')
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(base + '/#/connections?app=models')
        open_limits = page.get_by_role('button', name='Spending limits for Research models', exact=True)
        open_limits.click()
        dialog = page.get_by_role('dialog', name='Shared model spending')
        expect(dialog).to_contain_text('Research models, Writing models')
        period = dialog.get_by_label('Budget period', exact=True)
        expect(period).to_have_value('local_day')
        expect(dialog.locator('#account-budget-totals')).to_contain_text('$0.00 recorded')
        period.select_option('lifetime')
        expect(dialog.locator('#account-budget-totals')).to_contain_text('$0.40 recorded')
        dialog.get_by_label('Warn me at (USD)', exact=True).fill('.5')
        dialog.get_by_label('Ask before exceeding (USD)', exact=True).fill('.75')
        dialog.get_by_label('Stop before exceeding (USD)', exact=True).fill('1')
        for width, height in ((1440, 960), (390, 844), (320, 740)):
            page.set_viewport_size({'width': width, 'height': height})
            page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            assert period.bounding_box()['height'] >= 44
            dialog.screenshot(path=str(out / f'limits-{width}.png'), animations='disabled')
        metrics = dialog.evaluate("""el => ({
          inputSize: getComputedStyle(el.querySelector('input')).fontSize,
          selectSize: getComputedStyle(el.querySelector('select')).fontSize,
          selectHeight: el.querySelector('select').getBoundingClientRect().height,
          noteGap: getComputedStyle(el.querySelector('.account-spending-note')).marginTop
        })""")
        spacing = page.add_style_tag(content='''
          .modal-card, .modal-card * {line-height:1.5 !important; letter-spacing:.12em !important; word-spacing:.16em !important;}
          .modal-card p {margin-bottom:2em !important;}
        ''')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        expect(dialog.get_by_role('button', name='Save limits', exact=True)).to_be_visible()
        dialog.screenshot(path=str(out / 'limits-spacing-320.png'), animations='disabled')
        spacing.evaluate('el => el.remove()')
        with page.expect_response(lambda response: response.url.endswith('/api/v1/budgets')
                                  and response.request.method == 'PUT') as saved:
            dialog.get_by_role('button', name='Save limits', exact=True).click()
        assert saved.value.status == 200, saved.value.text()
        expect(dialog).to_have_count(0)
        policy = app.state.store.get_budget_policy('account', 'shared-budget')
        assert policy.reset == 'lifetime' and policy.ceiling_usd == 1 and policy.revision == 1
        open_limits.click()
        expect(period).to_have_value('lifetime')
        changed = page.request.put(base + '/api/v1/budgets', data={
            'scope_kind': 'account', 'scope_id': 'shared-budget', 'reset': 'lifetime',
            'warn_usd': .5, 'pause_usd': .75, 'ceiling_usd': .8, 'expected_revision': 1})
        assert changed.status == 200
        dialog.get_by_label('Stop before exceeding (USD)', exact=True).fill('2')
        dialog.get_by_role('button', name='Save limits', exact=True).click()
        expect(dialog.get_by_role('status')).to_contain_text('Spending limits changed')
        assert app.state.store.get_budget_policy('account', 'shared-budget').ceiling_usd == .8
        dialog.get_by_role('button', name='Reload saved limits', exact=True).click()
        expect(dialog.get_by_label('Stop before exceeding (USD)', exact=True)).to_have_value('0.8')

        def refuse_put(route):
            route.fulfill(status=503, json={'detail': 'fixture service unavailable'})

        page.route('**/api/v1/budgets', refuse_put)
        dialog.get_by_label('Stop before exceeding (USD)', exact=True).fill('.9')
        dialog.get_by_role('button', name='Save limits', exact=True).click()
        expect(dialog.get_by_role('status')).to_contain_text('fixture service unavailable')
        expect(period).to_be_enabled()
        expect(dialog.get_by_role('button', name='Save limits', exact=True)).to_be_enabled()
        assert app.state.store.get_budget_policy('account', 'shared-budget').ceiling_usd == .8
        page.unroute('**/api/v1/budgets', refuse_put)

        def refuse_reload(route):
            route.fulfill(status=503, json={'detail': 'fixture reload unavailable'})

        page.route('**/api/v1/budgets?*', refuse_reload)
        dialog.get_by_role('button', name='Reload saved limits', exact=True).click()
        expect(dialog.get_by_role('status')).to_have_text('Could not load spending limits: fixture reload unavailable')
        expect(dialog.get_by_role('button', name='Reload saved limits', exact=True)).to_be_enabled()
        page.unroute('**/api/v1/budgets?*', refuse_reload)
        dialog.get_by_role('button', name='Reload saved limits', exact=True).click()
        expect(dialog.get_by_label('Stop before exceeding (USD)', exact=True)).to_have_value('0.8')
        dialog.get_by_role('button', name='Cancel', exact=True).click()

        def hold_limits(route):
            held.append((route, route.fetch()))
            page.evaluate("window.accountBudgetHeld = true")

        page.route('**/api/v1/budgets?*', hold_limits)
        page.evaluate('''() => {
          const original = openAccountSpending;
          openAccountSpending = (...args) => window.pendingSpending = original(...args);
        }''')
        open_limits.click()
        page.wait_for_function('() => window.accountBudgetHeld === true')
        assert len(held) == 1
        page.evaluate("location.hash = '#/chat/account-spending-fixture'")
        expect(page.locator('#chat-prompt')).to_be_visible()
        route, response = held.pop()
        route.fulfill(response=response)
        page.evaluate('async () => { await window.pendingSpending; }')
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(page.locator('#chat-prompt')).to_be_visible()
        assert not errors, errors
        (out / 'validation.json').write_text(json.dumps({'scope': 'synthetic historical ledger; no credentials/model calls',
            'viewports': [[1440, 960], [390, 844], [320, 740]], 'page_errors': errors,
            'computed_styles': metrics, 'text_spacing_override': '1.5 / 2em / .12em / .16em at 320 CSS px',
            'browser_zoom_200_percent': 'not verified by this headless journey',
            'tested': ['period preview', 'shared aliases', 'saved limits', 'stale revision conflict', '503 recovery',
                       'late response cannot replace chat']}, indent=2) + '\n')
    finally:
        try:
            page.unroute_all(behavior='wait')
            for route, _ in held:
                route.abort()
        finally:
            context.close()
