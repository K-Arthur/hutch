"""Real preview, explicit save and local artifact readback; no model requests."""
import json
import time

import pytest

from playwright.sync_api import expect

from tests.e2e.test_design_system import app_server, browser  # noqa: F401
from tests.support.artifacts import artifact_path
from tests.test_campaign_report import SOURCE
from hutch.workflow import submit as wfsubmit


def open_report(page, base):
    page.goto(base + '/#/chat/design-system-review')
    page.get_by_role('button', name='Message options', exact=True).click()
    page.get_by_role('button', name='Create a campaign report', exact=True).click()
    expect(page.get_by_role('dialog', name='Campaign report', exact=True)).to_be_visible()


def test_campaign_report_review_save_and_reflow(browser, app_server):
    base, app = app_server
    context = browser.new_context(viewport={'width':1440,'height':1000}, reduced_motion='reduce')
    page = context.new_page()
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    out=artifact_path('campaign-report');out.mkdir(parents=True,exist_ok=True)
    try:
        open_report(page, base)
        dialog=page.get_by_role('dialog',name='Campaign report',exact=True)
        source=dialog.get_by_label('Campaign CSV',exact=True)
        source.fill('invalid')
        dialog.get_by_role('button',name='Preview report',exact=True).click()
        expect(dialog.locator('#campaign-report-error')).to_contain_text('CSV columns')
        expect(source).to_have_value('invalid')
        dialog.locator('#campaign-file').set_input_files({
            'name':'campaign-fixture.csv','mimeType':'text/csv','buffer':SOURCE.encode(),
        })
        expect(source).to_have_value(SOURCE)
        expect(dialog.locator('#campaign-file-name')).to_have_text('campaign-fixture.csv')
        dialog.get_by_role('button',name='Preview report',exact=True).click()
        expect(dialog.get_by_role('heading',name='Review the report')).to_be_visible()
        expect(dialog.get_by_text('Reporting period unknown',exact=False)).to_be_visible()
        expect(dialog.get_by_role('row',name='Social 0.02 0 Undefined 0 No conversions')).to_be_visible()
        assert not app.state.store.list_runs()
        for width,height in ((1440,1000),(768,1024),(390,844),(320,740)):
            page.set_viewport_size({'width':width,'height':height})
            page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            assert dialog.bounding_box()['width'] <= width
            assert source.evaluate('el=>getComputedStyle(el).fontSize')=='16px'
            assert dialog.get_by_label('Reporting period in whole days',exact=True).bounding_box()['height'] >=44
            assert dialog.get_by_role('button',name='Save local report',exact=True).bounding_box()['height'] >=44
            source.evaluate("el=>el.closest('.modal-body').scrollTop=0")
            page.screenshot(path=str(out/f'source-{width}.png'),animations='disabled')
            dialog.locator('#campaign-preview').evaluate("el=>el.scrollIntoView({block:'start'})")
            page.screenshot(path=str(out/f'preview-{width}.png'),animations='disabled')
        table=dialog.get_by_role('region',name='Campaign metrics, scroll horizontally for all columns',exact=True)
        table.focus();page.keyboard.press('ArrowRight')
        expect(table).to_be_focused()
        assert table.evaluate('el=>el.scrollWidth>el.clientWidth')
        page.wait_for_function("() => document.querySelector('.campaign-report-table').scrollLeft > 0")
        # Supplementary root-text enlargement, not a native browser zoom claim.
        page.add_style_tag(content='html {font-size:200% !important;}').evaluate('el=>el.id="campaign-test-text-scale"')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
        page.screenshot(path=str(out/'text-scale-320.png'),animations='disabled')
        page.locator('#campaign-test-text-scale').evaluate('el=>el.remove()')
        style=page.add_style_tag(content='''.campaign-report-form, .campaign-report-form * {line-height:1.5!important;letter-spacing:.12em!important;word-spacing:.16em!important;} .campaign-report-form p{margin-bottom:2em!important;}''')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
        page.screenshot(path=str(out/'spacing-320.png'),animations='disabled')
        style.evaluate('el=>el.remove()')
        page.set_viewport_size({'width':1440,'height':1000})
        dialog.get_by_label('Reporting period in whole days',exact=True).fill('1')
        expect(dialog.get_by_role('button',name='Preview report',exact=True)).to_be_visible()
        expect(dialog.locator('#campaign-preview')).to_be_hidden()
        dialog.get_by_role('button',name='Preview report',exact=True).click()
        expect(dialog.get_by_text('Above budget',exact=True)).to_be_visible()
        styles=dialog.locator('.campaign-report-form').evaluate('''el => {
          const size=selector=>getComputedStyle(el.querySelector(selector)).fontSize;
          return {input:size('textarea'),label:size('label[for=campaign-days]'),
            help:size('.hint'),body:size('.campaign-report-lead'),
            tableHeader:size('thead th'),groupGap:getComputedStyle(el).gap};
        }''')
        assert styles['label']==styles['help']==styles['tableHeader']=='14px'
        assert styles['input']==styles['body']=='16px'
        with page.expect_response(lambda r:r.url.endswith('/api/v1/workflows/plans') and r.request.method=='POST') as saved:
            dialog.get_by_role('button',name='Save local report',exact=True).click()
        assert saved.value.status==201,saved.value.text()
        workflow_id=saved.value.json()['workflow_run_id']
        expect(dialog).to_be_hidden()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            state=wfsubmit.status(app.state.store,workflow_id)
            if state['workflow']['status'] in ('succeeded','failed','stopped'):break
            time.sleep(.05)
        assert state['workflow']['status']=='succeeded',state['workflow'].get('reason')
        verify=next(node for node in state['nodes'] if node['site_id']=='verify')
        assert verify['result']['verified'] is True
        assert len(state['workflow']['result']['artifacts'])==3
        run=app.state.store.get_run(saved.value.json()['attempt_run_id'])
        assert run.tokens==0 and run.cost_usd==0
        assert not errors
        (out/'result.json').write_text(json.dumps({'viewports':[1440,768,390,320], 'zero_model_calls':True,'saved_artifacts':3,'byte_readback_verified':True,'keyboard_table_scroll':True,'text_scale':'supplementary 200% root size, not native zoom','styles':styles,'page_errors':errors},indent=2))
    finally:
        context.close()


@pytest.mark.parametrize('change',['edit','reopen'])
def test_old_preview_cannot_overwrite_changed_or_reopened_report(browser,app_server,change):
    base,app=app_server
    context=browser.new_context(); page=context.new_page()
    pending=[]
    try:
        open_report(page,base)
        page.locator('#campaign-source').fill(SOURCE)
        page.route('**/workflows/starters/campaign-report/preview',lambda route:pending.append(route),times=1)
        page.get_by_role('button',name='Preview report',exact=True).click()
        expect(page.get_by_role('button',name='Preview report',exact=True)).to_be_disabled()
        deadline=time.monotonic()+5
        while not pending and time.monotonic()<deadline:page.wait_for_timeout(10)
        assert pending
        if change=='reopen':
            page.get_by_role('button',name='Close dialog',exact=True).click()
            page.get_by_role('button',name='Message options',exact=True).click()
            page.get_by_role('button',name='Create a campaign report',exact=True).click()
        page.locator('#campaign-source').fill('new draft')
        pending.pop().fulfill(status=200,json={'plan':{},'report':{'rows':[]}})
        expect(page.locator('#campaign-source')).to_have_value('new draft')
        expect(page.locator('#campaign-preview')).to_be_hidden()
        expect(page.get_by_role('button',name='Preview report',exact=True)).to_be_enabled()
        if change=='edit':expect(page.locator('#campaign-report-error')).to_contain_text('source changed')
        assert not app.state.store.list_runs()
    finally:
        for route in pending:route.abort()
        context.close()


def test_slow_csv_import_cannot_replace_newer_edits_or_save_old_preview(browser,app_server):
    base,app=app_server
    context=browser.new_context();page=context.new_page()
    try:
        open_report(page,base)
        page.locator('#campaign-source').fill(SOURCE)
        page.get_by_role('button',name='Preview report',exact=True).click()
        expect(page.get_by_role('button',name='Save local report',exact=True)).to_be_enabled()
        page.evaluate('''() => {
          const read = File.prototype.text;
          File.prototype.text = function() { return new Promise(resolve => {
            window.releaseCampaignFile = () => read.call(this).then(resolve);
          }); };
        }''')
        page.locator('#campaign-file').set_input_files({
            'name':'slow-fixture.csv','mimeType':'text/csv','buffer':SOURCE.encode(),
        })
        expect(page.get_by_role('button',name='Preview report',exact=True)).to_be_disabled()
        expect(page.locator('#campaign-preview')).to_be_hidden()
        page.locator('#campaign-source').fill('newer edited draft')
        page.evaluate('() => window.releaseCampaignFile()')
        expect(page.get_by_role('button',name='Preview report',exact=True)).to_be_enabled()
        expect(page.locator('#campaign-source')).to_have_value('newer edited draft')
        expect(page.locator('#campaign-preview')).to_be_hidden()
        assert not app.state.store.list_runs()
    finally:context.close()
