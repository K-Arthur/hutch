"""Delayed real conversation requests must not replace a later user destination."""
import pytest
import hashlib
import json
from pathlib import Path
from playwright.sync_api import expect

from tests.e2e.test_design_system import app_server,browser  # noqa: F401
from tests.support.artifacts import artifact_path


@pytest.mark.parametrize('destination',['controls','settings','newer_conversation','failure'])
def test_conversation_open_has_pending_controls_and_route_ownership(browser,app_server,monkeypatch,destination):
    base,app=app_server
    monkeypatch.setattr(app.state.engine,'tick',lambda:[])
    store=app.state.store;bot=store.get_bot('design-system-review')
    first,_=store.create_conversation(bot.id,'Original conversation',idem_key='original',request_hash='original')
    second,_=store.create_conversation(bot.id,'Delayed conversation',idem_key='delayed',request_hash='delayed')
    context=browser.new_context(reduced_motion='reduce');page=context.new_page();held=[];errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def delay(route):
        held.append((route,route.fetch()))
        page.evaluate('window.conversationResponseHeld=true')
    try:
        page.goto(base+'/#/conversation/'+first['id'])
        expect(page.locator('#conversation-switcher')).to_have_value(first['id'])
        expect(page.locator('#studio-conversation-options')).to_be_enabled()
        page.route('**/api/v1/conversations/'+second['id'],delay,times=1)
        page.locator('#chat-prompt').fill('Keep my unsent request.')
        if destination in {'controls','failure'}:
            page.locator('#conversation-switcher').select_option(second['id'])
        else:
            page.evaluate('(id)=>{window.pendingConversationOpen=openConversation(id)}',second['id'])
        page.wait_for_function('()=>window.conversationResponseHeld===true')
        if destination=='controls':
            expect(page.locator('#conversation-switcher')).to_be_disabled()
            options=page.locator('#studio-conversation-options')
            expect(options).to_have_attribute('aria-disabled','true')
            expect(options).to_have_attribute('inert','')
            options.evaluate('element=>element.focus()')
            expect(options).not_to_be_focused()
            expect(page.locator('#chat-prompt')).to_be_disabled()
            expect(page.locator('#chat-send')).to_be_disabled()
            expect(page.get_by_role('status').filter(has_text='Opening conversation…')).to_be_visible()
            out=artifact_path('conversation-loading');out.mkdir(parents=True,exist_ok=True)
            for width,height in ((1440,960),(320,740)):
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(out/f'pending-{width}.png'),animations='disabled')
            page.set_viewport_size({'width':1280,'height':720})
            metrics=page.locator('.conversation-opening').evaluate('element=>({fontSize:getComputedStyle(element).fontSize,padding:getComputedStyle(element).padding})')
            (out/'validation.json').write_text(json.dumps({'scope':'actual UI with one held synthetic conversation read; no inference',
                'viewports':[[1440,960],[320,740]],'computed_styles':metrics,'draft_preserved':True,
                'native_fields_disabled':True,'summary_inert_and_not_focusable':True,
                'source_sha256':{path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in
                    ['src/hutch/server/static/app.js','app/src/input.css','src/hutch/server/static/ui.css']}},indent=2)+'\n')
        elif destination=='settings':
            page.evaluate("location.hash='#/settings'")
            expect(page.locator('#studio-conversation-options')).to_have_count(0)
        elif destination=='newer_conversation':
            page.evaluate('async id=>{await openConversation(id)}',first['id'])
            expect(page.locator('#conversation-switcher')).to_have_value(first['id'])
        route,response=held.pop()
        if destination=='failure':route.fulfill(status=503,json={'detail':'Synthetic conversation unavailable'})
        else:route.fulfill(response=response)
        if destination not in {'controls','failure'}:
            page.evaluate('async()=>{await window.pendingConversationOpen}')
        if destination=='controls':
            expect(page.locator('#conversation-switcher')).to_have_value(second['id'])
            expect(page.locator('#conversation-switcher')).to_be_enabled()
            expect(page.locator('#studio-conversation-options')).to_be_enabled()
            page.locator('#studio-conversation-options').click()
            expect(page.get_by_role('button',name='New section',exact=True)).to_be_visible()
        elif destination=='failure':
            expect(page.locator('#conversation-switcher')).to_have_value(first['id'])
            expect(page.locator('#chat-prompt')).to_be_enabled()
            expect(page.locator('#chat-prompt')).to_have_value('Keep my unsent request.')
            expect(page.locator('#studio-conversation-options')).to_be_enabled()
            page.locator('#studio-conversation-options').click()
            expect(page.get_by_role('button',name='New section',exact=True)).to_be_visible()
        elif destination=='settings':
            assert page.evaluate('location.hash')=='#/settings'
            expect(page.locator('#studio-conversation-options')).to_have_count(0)
        else:
            assert page.evaluate('location.hash')=='#/conversation/'+first['id']
            expect(page.locator('#conversation-switcher')).to_have_value(first['id'])
        assert not errors,errors
    finally:
        try:
            for route,_ in held:route.abort()
            page.unroute_all(behavior='wait')
        finally:context.close()
