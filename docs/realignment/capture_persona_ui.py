"""Capture response-style (persona) acceptance evidence: the settings form beside standing
directions, the chat-options scopes, and the next-reply chip, driven through the real app.

Run from the repository root of a hutch checkout with src on the path:

    PYTHONPATH=src .venv/bin/python docs/realignment/capture_persona_ui.py

Writes docs/realignment/artifacts/persona-ui-2026-10-11/ with screenshots at phone/tablet/desktop
widths, result.json (every check plus console/page-error capture), and a Playwright trace. The test
bot has no model route, so the one send attempt fails honestly at admission and no model call is made.
"""

import os
from pathlib import Path
import threading
import time
import json
import tempfile
import traceback

import uvicorn
from playwright.sync_api import sync_playwright

out = Path(__file__).resolve().parent / 'artifacts' / 'persona-ui-2026-10-11'
out.mkdir(parents=True, exist_ok=True)
os.environ['HUTCH_STATE_DIR'] = tempfile.mkdtemp(prefix='hutch-persona-ui-state-')
os.environ['HUTCH_EXECUTOR'] = 'thread'

from hutch.models import Bot
from hutch.server.app import create_app

app = create_app()
bot = app.state.store.create_bot(Bot(name='persona-ui', display_name='Hutch', tools=[], model=''))
conversation, _ = app.state.store.create_conversation(bot.id, 'Persona check', idem_key='ui-conv',
                                                      request_hash='ui-conv')
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=0, log_level='error'))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
deadline = time.monotonic() + 10
while not server.started and time.monotonic() < deadline:
    time.sleep(.02)
assert server.started
url = f'http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}'

results = {"checks": [], "errors": [], "console": []}
errors = []


def open_options_panel(page):
    for _ in range(8):
        outer = page.locator('#studio-conversation-actions')
        if not page.evaluate("() => document.querySelector('#studio-conversation-actions')?.open"):
            page.locator('#studio-conversation-options').click()
        page.wait_for_function("() => document.querySelector('#studio-conversation-actions')?.open === true")
        page.locator('#persona-chat-options summary').click()
        try:
            page.wait_for_function("() => document.querySelector('#persona-chat-options')?.open === true",
                                   timeout=1500)
            return
        except Exception:
            time.sleep(0.25)
    raise AssertionError("the persona options panel would not stay open")


def check(name, ok, detail=""):
    results["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)})
    assert ok, f"{name}: {detail}"


try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(reduced_motion='reduce')
        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.new_page()
        page.set_default_timeout(10000)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: results["console"].append(f"{m.type}: {m.text}"))

        try:
            page.goto(url + '/#/bot/persona-ui', wait_until='domcontentloaded')
            page.locator('#form-instructions').wait_for(state='attached')
            page.locator('#assistant-more-settings').evaluate('el => el.open = true')
            page.wait_for_selector('#persona-form-slot .persona-form')
            csrf = next(c['value'] for c in context.cookies() if c['name'] == 'hutch_csrf')

            def api(method, path, body=None, key=None):
                headers = {"X-Hutch-CSRF": csrf, "Content-Type": "application/json"}
                if key:
                    headers["Idempotency-Key"] = key
                return context.request.fetch(url + '/api' + path, method=method, headers=headers,
                                             data=json.dumps(body) if body is not None else None)

            form = page.locator('#persona-form-slot .persona-form')
            depth = form.locator('[data-persona-field="depth"]')
            tone = form.locator('[data-persona-field="tone"]')
            status = form.locator('[data-persona-status]')
            check("settings defaults to inherited", depth.input_value() == "inherit")
            origins = form.locator('[data-persona-origin="depth"]').inner_text()
            check("origin names the hutch default", "Hutch default" in origins, origins)

            depth.select_option("brief")
            tone.select_option("warm")
            check("unsaved state is visible", "Unsaved" in status.inner_text(), status.inner_text())
            form.locator('[data-persona-save]').click()
            page.wait_for_function("() => document.querySelector('#persona-form-slot [data-persona-status]').textContent.includes('Saved.')")
            saved = json.loads(api("GET", "/v1/bots/persona-ui/persona").body())
            check("save persisted", saved["revision"] == 1 and saved["override"]["depth"] == "brief"
                  and saved["override"]["tone"] == "warm", saved["override"])
            check("effective source is the saved style",
                  saved["effective"]["depth"] == {"value": "brief", "source": "agent_override"},
                  saved["effective"]["depth"])

            api("PATCH", "/v1/bots/persona-ui/persona", {"tone": "direct", "expected_revision": 1},
                key="ui-conflict-1")
            depth.select_option("thorough")
            form.locator('[data-persona-save]').click()
            page.wait_for_function("() => document.querySelector('#persona-form-slot [data-persona-status]').textContent.includes('changed elsewhere')")
            check("conflict keeps the unsaved edits", depth.input_value() == "thorough")
            check("conflict message asks for review", "review" in status.inner_text(), status.inner_text())
            depth_origin = form.locator('[data-persona-origin="depth"]').inner_text()
            check("conflict labels the differing field as unsaved", "Unsaved change" in depth_origin, depth_origin)
            form.locator('[data-persona-save]').click()
            page.wait_for_function("() => document.querySelector('#persona-form-slot [data-persona-status]').textContent.includes('Saved.')")
            after = json.loads(api("GET", "/v1/bots/persona-ui/persona").body())
            check("re-save after conflict applied", after["override"]["depth"] == "thorough", after["override"])
            saved_origin = form.locator('[data-persona-origin="depth"]').inner_text()
            check("saved field says saved", "Saved for this assistant" in saved_origin, saved_origin)

            tone.select_option("inherit")
            form.locator('[data-persona-save]').click()
            page.wait_for_function("() => document.querySelector('#persona-form-slot [data-persona-status]').textContent.includes('Saved.')")
            reset = json.loads(api("GET", "/v1/bots/persona-ui/persona").body())
            check("reset cleared the tone back to inherited", reset["override"]["tone"] is None
                  and reset["effective"]["tone"]["source"] == "application", reset["effective"]["tone"])
            reset_origin = form.locator('[data-persona-origin="tone"]').inner_text()
            check("reset shows the inherited source", "Hutch default: Neutral" in reset_origin, reset_origin)

            for width in (360, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 960})
                page.goto(url + '/#/bot/persona-ui', wait_until='domcontentloaded')
                page.locator('#form-instructions').wait_for(state='attached')
                page.locator('#assistant-more-settings').evaluate('el => el.open = true')
                page.wait_for_selector('#persona-form-slot .persona-form')
                page.locator('#persona-form-slot').scroll_into_view_if_needed()
                page.screenshot(path=str(out / f'settings-persona-{width}.png'), animations='disabled')
            results["widths"] = {"settings": [360, 768, 1440]}

            page.set_viewport_size({'width': 1440, 'height': 960})
            page.goto(url + '/#/chat/persona-ui', wait_until='domcontentloaded')
            page.locator('#chat-form').wait_for(state='attached')
            open_options_panel(page)
            conv_tone = page.locator('#persona-chat-options .persona-fields-conversation [data-persona-field="tone"]')
            conv_tone.wait_for(state='attached')
            conv_tone.select_option('warm')
            page.wait_for_function("() => document.querySelector('#persona-chat-options [data-persona-conversation-status]').textContent.includes('Saved for this conversation.')")
            cstate = json.loads(api("GET", f"/v1/conversations/{conversation['id']}/persona").body())
            check("conversation save persisted", cstate["revision"] == 1 and cstate["override"]["tone"] == "warm",
                  cstate["override"])

            turn_depth = page.locator('#persona-chat-options .persona-fields-turn [data-persona-field="depth"]')
            turn_depth.select_option('brief')
            chip = page.locator('#persona-turn-slot .persona-turn-chip')
            check("composer chip shows the next-reply style", chip.is_visible() and "short" in chip.inner_text(),
                  chip.inner_text())
            turn_origin = page.locator('#persona-chat-options .persona-fields-turn [data-persona-origin="depth"]').inner_text()
            check("turn origin names the next-reply scope", "For the next reply only" in turn_origin, turn_origin)
            turn_tone_origin = page.locator('#persona-chat-options .persona-fields-turn [data-persona-origin="tone"]').inner_text()
            check("unset turn field names its inherited source", "This conversation" in turn_tone_origin, turn_tone_origin)

            captured = {}
            page.on('request', lambda req: captured.setdefault('body', req.post_data_json)
                    if req.method == 'POST' and '/messages' in req.url else None)
            page.locator('#chat-prompt').fill('hello there')
            page.locator('#chat-send').click()
            wait_until = time.time() + 6
            while 'body' not in captured and time.time() < wait_until:
                time.sleep(0.05)
            check("send carries the one-turn persona", (captured.get('body') or {}).get('persona') == {"depth": "brief"},
                  (captured.get('body') or {}).get('persona'))
            page.wait_for_function("() => !document.querySelector('#persona-turn-slot .persona-turn-chip').hidden")
            check("chip is kept when the send fails honestly", chip.is_visible(), chip.inner_text())
            page.locator('[data-persona-turn-clear]').dispatch_event("click")
            page.wait_for_function("() => document.querySelector('#persona-turn-slot .persona-turn-chip').hidden")
            check("chip clears on remove", chip.is_hidden())

            for width in (360, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 960})
                page.goto(url + '/#/chat/persona-ui', wait_until='domcontentloaded')
                page.reload(wait_until='domcontentloaded')
                page.locator('#chat-form').wait_for(state='attached')
                open_options_panel(page)
                page.locator('#persona-chat-options .persona-fields-turn [data-persona-field="depth"]').select_option('brief')
                page.locator('#persona-chat-options').scroll_into_view_if_needed()
                page.screenshot(path=str(out / f'chat-options-{width}.png'), animations='disabled')
            results["widths"]["chat_options"] = [360, 768, 1440]

            results["browser"] = browser.version
            results["model_calls"] = 0
            results["errors"] = errors
            check("no page errors", not errors, errors)
            context.tracing.stop(path=str(out / 'trace.zip'))
        except Exception:
            debug = {
                "url": page.url,
                "persona_status": page.locator('#persona-form-slot [data-persona-status]').inner_text()
                    if page.locator('#persona-form-slot [data-persona-status]').count() else "(no form)",
                "console": results["console"][-25:],
                "page_errors": errors,
            }
            (out / 'debug.json').write_text(json.dumps(debug, indent=2))
            page.screenshot(path=str(out / 'debug.png'), animations='disabled')
            traceback.print_exc()
            raise
        finally:
            browser.close()
finally:
    server.should_exit = True
    thread.join(10)

(out / 'result.json').write_text(json.dumps(results, indent=2))
assert not thread.is_alive()
assert not errors, errors
print("CHECKS:", len(results["checks"]), "OK")
print(out)
