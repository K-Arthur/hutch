"""Real owner setup/readbacks; fake vault and Telegram, no external dispatch."""
import hashlib
import json
import re
from pathlib import Path

from playwright.sync_api import expect

from hutch.server import channels_api
from hutch.channels.persistence import ChannelBook
from tests.e2e.test_design_system import app_server, browser  # noqa: F401
from tests.support.artifacts import artifact_path
from tests.test_channels_api import FakeTelegram, Vault, TOKEN


def test_telegram_connection_setup_is_explicit_responsive_and_recoverable(browser,app_server,monkeypatch):
    base,app=app_server
    app.state.channels.stop_event.set();app.state.store.bus.notify('channels',remote=False)
    monkeypatch.setattr(app.state.engine,'tick',lambda:[])
    vault=Vault()
    for method in ('available','get','put','delete'):
        monkeypatch.setattr(app.state.channel_secrets,method,getattr(vault,method))
    monkeypatch.setattr(channels_api,'Telegram',FakeTelegram)
    context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    out=artifact_path('telegram-channels');out.mkdir(parents=True,exist_ok=True)
    try:
        page.goto(base+'/#/connections?app=telegram')
        panel=page.locator('#connection-telegram');form=panel.locator('#channel-create')
        expect(panel.get_by_text('No Telegram bots connected.',exact=False)).to_be_visible()
        expect(form.get_by_label('Assistant',exact=True)).to_be_enabled()
        for width,height in ((1440,1000),(768,1024),(390,844),(320,740)):
            page.set_viewport_size({'width':width,'height':height});page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            assert form.get_by_label('Assistant',exact=True).bounding_box()['height']>=44
            panel.evaluate("element=>element.closest('.page-scroll').scrollTop=0")
            page.screenshot(path=str(out/f'setup-{width}.png'),animations='disabled')
            form.evaluate("element=>element.scrollIntoView({block:'start'})")
            page.screenshot(path=str(out/f'form-{width}.png'),animations='disabled')
        style=page.add_style_tag(content='''
          #connection-telegram, #connection-telegram * {line-height:1.5 !important;letter-spacing:.12em !important;word-spacing:.16em !important;}
          #connection-telegram p {margin-bottom:2em !important;}
        ''')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        form.evaluate("element=>element.scrollIntoView({block:'start'})")
        page.screenshot(path=str(out/'setup-spacing-320.png'),animations='disabled')
        style.evaluate('element=>element.remove()')
        page.set_viewport_size({'width':1440,'height':1000})
        form.get_by_label('Connection name',exact=True).fill('Personal Telegram')
        bot=app.state.store.get_bot('design-system-review')
        form.get_by_label('Assistant',exact=True).select_option(bot.id)
        form.get_by_label('Bot token',exact=True).fill(TOKEN)
        form.get_by_role('button',name='Find my Telegram account',exact=True).click()
        expect(panel.get_by_label('Synthetic owner',exact=False)).to_be_visible()
        panel.get_by_label('Synthetic owner',exact=False).check()
        assert not app.state.store.list_runs()
        with page.expect_response(lambda response:response.url.endswith('/api/v1/channels/telegram') and response.request.method=='POST') as saved:
            form.get_by_role('button',name='Save connection',exact=True).click()
        assert saved.value.status==201,saved.value.text()
        expect(panel.get_by_text('Connection saved and paused.',exact=False)).to_be_visible()
        expect(form.get_by_label('Bot token',exact=True)).to_have_value('')
        connection=page.request.get(base+'/api/v1/channels').json()['connections'][0]
        assert not connection['enabled'] and len(vault.values)==1
        card=panel.locator(f'[data-channel="{connection["id"]}"]')
        expect(card.get_by_text('Paused',exact=True)).to_be_visible()
        card.get_by_role('button',name='Start receiving and replying',exact=True).click()
        dialog=page.get_by_role('dialog',name='Start this Telegram connection?',exact=True)
        expect(dialog).to_contain_text('existing knowledge and permitted tools')
        dialog.get_by_role('button',name='Cancel',exact=True).click()
        assert not page.request.get(base+'/api/v1/channels').json()['connections'][0]['enabled']
        card.get_by_role('button',name='Start receiving and replying',exact=True).click()
        page.get_by_role('dialog').get_by_role('button',name='Start receiving and replying',exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(card.get_by_role('button',name='Pause',exact=True)).to_be_visible()
        expect(card.get_by_role('button',name='Pause',exact=True)).to_be_focused()
        card.scroll_into_view_if_needed()
        page.screenshot(path=str(out/'receiving-desktop.png'),animations='disabled')
        card.get_by_role('button',name='Pause',exact=True).click()
        expect(card.get_by_text('Paused',exact=True)).to_be_visible()
        card.get_by_role('button',name='Review deliveries',exact=True).click()
        expect(card.get_by_text('No replies sent yet.',exact=True)).to_be_visible()
        card.locator('details > summary').click()
        access = card.locator('[data-channel-configure]')
        access.get_by_label('Connection name',exact=True).fill('Updated personal Telegram')
        access.get_by_label('Allowed Telegram user IDs',exact=True).fill('123, 456')
        access.get_by_role('button',name='Save channel access',exact=True).click()
        expect(card.get_by_role('heading',name='Updated personal Telegram',exact=True)).to_be_visible()
        assert page.request.get(base+'/api/v1/channels').json()['connections'][0]['allowed_senders']==['123','456']
        card.locator('details > summary').click()
        card.get_by_role('button',name='Disconnect and remove token',exact=True).click()
        expect(card.get_by_text('Disconnected',exact=True)).to_be_visible()
        assert not vault.values
        assert not app.state.store.list_runs()
        assert TOKEN not in page.locator('body').inner_text()
        assert page.evaluate('() => !Object.values(localStorage).concat(Object.values(sessionStorage)).some(value=>value.includes("synthetic-not-a-real-token-value"))')
        page.set_viewport_size({'width':390,'height':844})
        card.evaluate("element=>element.scrollIntoView({block:'start'})")
        page.screenshot(path=str(out/'disconnected-phone.png'),animations='disabled')
        metrics=form.evaluate('''element=>({inputSize:getComputedStyle(element.elements.name).fontSize,
          selectSize:getComputedStyle(element.elements.bot_id).fontSize,gap:getComputedStyle(element).gap})''')
        def offline(route):route.fulfill(status=503,json={'detail':'Synthetic channel service unavailable'})
        page.route('**/api/v1/channels',offline)
        page.reload()
        expect(page.locator('#channel-status')).to_contain_text('Synthetic channel service unavailable')
        assert not errors,errors
        (out/'validation.json').write_text(json.dumps({'scope':'synthetic provider/vault; actual API and Store; no model/service calls',
            'viewports':[[1440,1000],[768,1024],[390,844],[320,740]],'computed_styles':metrics,
            'text_spacing_320':True,'actual_browser_zoom_200':'unverified','page_errors':errors,
            'source_sha256':{path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in
                ['src/hutch/server/static/channels.js','src/hutch/server/static/app.js','app/src/input.css','src/hutch/server/static/ui.css']},
            'checked':['explicit sender choice','save paused','clear token','start cancel','start confirm','pause','delivery empty','paused access edit','disconnect key removal','storage exclusion','503 inline error']},indent=2)+'\n')
    finally:context.close()


def test_telegram_uncertain_delivery_requires_checked_outcome(browser,app_server,monkeypatch):
    from tests.test_channels import ingest,complete
    base,app=app_server
    app.state.channels.stop_event.set();app.state.store.bus.notify('channels',remote=False)
    monkeypatch.setattr(app.state.engine,'tick',lambda:[])
    book=ChannelBook(app.state.store);bot=app.state.store.get_bot('design-system-review')
    connection=book.create(name='Delivery review fixture',bot_id=bot.id,allowed_senders=['123'],
        credential_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),remote_bot_id='123456789')
    connection,_=book.set_enabled(connection['id'],True,connection['revision'])
    fixture=(book,bot,connection);claimed=ingest(fixture);book.admit(connection['id']);complete(fixture)
    book.queue_replies(connection['id']);book.take_reply(claimed,'test-owner');book.claim(connection['id'],'test-owner')
    context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    page=context.new_page();out=artifact_path('telegram-channels');out.mkdir(parents=True,exist_ok=True)
    try:
        page.goto(base+'/#/connections?app=telegram')
        card=page.locator('[data-channel]')
        card.get_by_role('button',name='Review deliveries',exact=True).click()
        expect(card.get_by_text('Delivery unconfirmed',exact=True)).to_be_visible()
        expect(card.get_by_role('link',name='Open task and answer',exact=True)).to_have_attribute('href',re.compile(r'^#/run/run_'))
        card.get_by_role('button',name='Review outcome',exact=True).click()
        dialog=page.get_by_role('dialog',name='Reconcile this reply',exact=True)
        expect(dialog.get_by_role('combobox',name='Checked outcome',exact=True)).to_be_focused()
        dialog.get_by_role('button',name='Close dialog',exact=True).focus()
        page.keyboard.press('Shift+Tab')
        expect(dialog.get_by_role('button',name='Record checked outcome',exact=True)).to_be_focused()
        page.keyboard.press('Tab')
        expect(dialog.get_by_role('button',name='Close dialog',exact=True)).to_be_focused()
        dialog.get_by_role('button',name='Record checked outcome',exact=True).click()
        expect(dialog.get_by_role('status')).to_have_text('Choose a checked outcome and record its independent evidence.')
        for width,height in ((1440,1000),(320,740)):
            page.set_viewport_size({'width':width,'height':height})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.screenshot(path=str(out/f'delivery-review-{width}.png'),animations='disabled')
        dialog.get_by_label('Checked outcome',exact=True).select_option('no')
        dialog.get_by_label('Evidence',exact=True).fill('Checked actual synthetic Telegram history; the reply is absent.')
        dialog.get_by_role('button',name='Record checked outcome',exact=True).click()
        expect(dialog).to_have_count(0)
        expect(card.get_by_role('button',name='Review deliveries',exact=True)).to_be_focused()
        assert book.deliveries(connection['id'])[0]['state']=='pending'
        reply=book.take_reply(claimed,'test-owner');assert reply
        book.claim(connection['id'],'test-owner')
        assert book.deliveries(connection['id'])[0]['attempts']==2
        card.get_by_role('button',name='Review deliveries',exact=True).click()
        card.get_by_role('button',name='Review outcome',exact=True).click()
        dialog=page.get_by_role('dialog',name='Reconcile this reply',exact=True)
        dialog.get_by_label('Checked outcome',exact=True).select_option('yes')
        dialog.get_by_label('Evidence',exact=True).fill('Independent readback confirms the second reply is present.')
        dialog.get_by_role('button',name='Record checked outcome',exact=True).click()
        expect(dialog).to_have_count(0)
        assert book.deliveries(connection['id'])[0]['state']=='sent'
        assert not app.state.channels.thread.is_alive()
    finally:context.close()
