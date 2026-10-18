"""Capture isolated deterministic UI-state fixtures; never reads operator state or writes site assets.

PLAYWRIGHT_BROWSERS_PATH=/<local-path-redacted> .venv/bin/python \
  docs/realignment/capture_navigation.py
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
from importlib.metadata import version as package_version
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

import playwright.sync_api as pw
import uvicorn

# This source-checkout-only script drives the deterministic scenario fixture.
# Production launch paths never set this flag and built wheels omit tests/.
os.environ["HUTCH_TESTING"] = "1"

from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.approvals import resolve_approval_ex
from hutch.server.app import create_app

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/realignment/artifacts/navigation'
SIZES = {'desktop': (1440, 1000), 'tablet': (900, 1024), 'phone': (390, 844)}
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def source_hashes():
    files = [p for p in (ROOT / 'src/hutch').rglob('*') if p.suffix in {'.py', '.js', '.css', '.html'}]
    files += [p for p in (ROOT / 'website').iterdir() if p.suffix in {'.html', '.js', '.css'}]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


class QuietHTTP(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def wait_for(fn):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if fn():
            return
        time.sleep(.05)
    raise RuntimeError('fixture did not reach expected state')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    source_before = source_hashes()
    with tempfile.TemporaryDirectory(prefix='hutch-navigation-') as state:
        os.environ['HUTCH_STATE_DIR'] = state
        os.environ['HUTCH_MAX_CONCURRENT'] = '4'
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=0, log_level='error'))
        thread = threading.Thread(target=server.run)
        thread.start()
        wait_for(lambda: server.started)
        base = f'http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}'
        site = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHTTP, directory=str(ROOT / 'website')))
        site_thread = threading.Thread(target=site.serve_forever)
        site_thread.start()
        try:
            with pw.sync_playwright() as p:
                browser = p.firefox.launch()
                contexts = []
                pages = {}
                errors = {}
                def snap(page, name, size):
                    page.screenshot(path=str(OUT / f'{name}-{size}.png'), full_page=True, animations='disabled')
                    heading = page.evaluate("""() => {
                      const element = document.querySelector('h1');
                      if (!element) return null;
                      const style = getComputedStyle(element);
                      const fontSize = parseFloat(style.fontSize);
                      const lineHeight = parseFloat(style.lineHeight);
                      return {text: element.innerText.trim(), fontSize: style.fontSize,
                              lineHeight: style.lineHeight, ratio: lineHeight / fontSize};
                    }""")
                    records.append({'state': name, 'size': size, 'pageErrors': list(errors[size]),
                                    'overflow': page.evaluate('document.documentElement.scrollWidth - innerWidth'),
                                    'heading': heading,
                                    'screenshot': f'{name}-{size}.png'})
                for size, (width, height) in SIZES.items():
                    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
                    context.tracing.start(screenshots=True, snapshots=True)
                    contexts.append((size, context))
                    page = context.new_page()
                    errors[size] = []
                    page.on('pageerror', lambda err, size=size: errors[size].append(str(err)))
                    pages[size] = page
                    page.goto(base + '/#/chat')
                    page.get_by_text('No bots yet.', exact=True).wait_for()
                    snap(page, 'empty', size)
                store = app.state.store
                store.create_bot(Bot(name='research-assistant', description='A deterministic demonstration; no hosted model or external action.', model='mock/demo', tools=['files', 'memory'], approval_mode=ApprovalMode.ask))
                store.create_bot(Bot(name='weekly-notes', model='mock/demo', tools=[], paused=True))
                store.create_bot(Bot(name='repository-review-with-a-long-bot-name', model='mock/demo', tools=[]))
                desktop = pages['desktop']
                desktop.goto(base + '/#/chat/research-assistant')
                desktop.locator('#conversation-switcher').wait_for()
                desktop.locator('#chat-prompt').fill('write a report')
                desktop.locator('#chat-send').click()
                desktop.locator('#chat-stream [data-approval-card]').wait_for()
                for size, page in pages.items():
                    if size != 'desktop':
                        page.goto(base + '/#/chat/research-assistant')
                    page.locator('#chat-stream [data-approval-card]').wait_for()
                    snap(page, 'waiting', size)
                    if size != 'desktop':
                        page.locator('#nav-toggle').click()
                    page.locator('#needs-you-open').click()
                    page.locator('#needs-you [data-approval-card]').wait_for()
                    page.locator('#needs-you .approval-review summary').click()
                    snap(page, 'needs-you', size)
                    page.keyboard.press('Escape')
                    page.goto(base + '/#/bot/research-assistant')
                    page.locator('#form-limits').wait_for()
                    snap(page, 'settings', size)
                for i in range(7):
                    store.create_bot(Bot(name=f'fleet-helper-{i}', model='mock/demo', tools=[], paused=i == 3))
                for size, page in pages.items():
                    page.goto(base + '/#/bots')
                    page.locator('#fleet-search').wait_for()
                    page.locator('#fleet-state').select_option('paused')
                    snap(page, 'fleet', size)
                    page.goto(base + '/#/overview')
                    page.get_by_role('heading', name='Activity', exact=True).wait_for()
                    snap(page, 'activity', size)

                [approval] = store.pending_approvals()
                assert resolve_approval_ex(store, approval.id, True, expected_hash=approval.action_hash).won
                wait_for(lambda: store.get_run(approval.run_id).status is RunStatus.succeeded)
                for size, page in pages.items():
                    page.goto(base + '/#/chat/research-assistant')
                    page.locator('#chat-stream .msg.agent').wait_for()
                    page.get_by_text('Done', exact=True).first.wait_for()
                    snap(page, 'completion', size)
                    page.goto(base + '/#/run/' + approval.run_id)
                    page.locator('.run-stats').wait_for()
                    snap(page, 'run-detail', size)

                # Synthetic lifecycle fixtures supplement the real mock approval/completion.
                # Hold the supervisor; these records do not represent actual model loading or cleanup.
                app.state.engine.tick = lambda: None
                for name, status in [('loading', RunStatus.loading_model),
                                     ('cancelling', RunStatus.cancelling)]:
                    bot = store.get_bot('research-assistant')
                    fixture = store.create_run(Run(bot_id=bot.id, prompt='Synthetic lifecycle fixture', status=status))
                    for size, page in pages.items():
                        page.goto(base + '/#/run/' + fixture.id)
                        # During route transitions, a hidden status copy can precede the
                        # visible run chip in the DOM. Wait for the actual state chip.
                        page.locator(f'.status.{status.value}:visible').first.wait_for()
                        snap(page, name, size)
                for size, page in pages.items():
                    page.route('**/api/bots/research-assistant', lambda route: route.abort())
                    page.goto(base + '/#/bot/research-assistant')
                    page.get_by_text('Could not load this view.', exact=True).wait_for()
                    snap(page, 'error', size)
                    page.unroute('**/api/bots/research-assistant')
                    page.goto(base + '/#/chat/research-assistant')
                    page.locator('#conversation-switcher').wait_for()
                    page.route('**/api/health', lambda route: route.abort())
                for size, page in pages.items():
                    page.locator('#daemon-pill[data-state="reconnecting"]').wait_for(timeout=20000, state='attached')
                    if size != 'desktop':
                        page.locator('#nav-toggle').click()
                    snap(page, 'reconnecting', size)
                    if size != 'desktop':
                        page.keyboard.press('Escape')
                    page.unroute('**/api/health')

                # Build local inspection sheets from fixture states. Never copy fixture images to the site.
                image_python = os.environ.get('HUTCH_IMAGE_PYTHON', sys.executable)
                image_script = '''
from PIL import Image, __version__
from PIL import ImageDraw, ImageFont
from pathlib import Path
import sys
out = Path(sys.argv[1])
print(__version__)
states = ['empty', 'waiting', 'needs-you', 'settings', 'fleet', 'activity', 'completion',
          'run-detail', 'loading', 'cancelling', 'error', 'reconnecting', 'site']
for size, viewport in {'desktop': (1440, 1000), 'tablet': (900, 1024), 'phone': (390, 844)}.items():
    sheet = Image.new('RGB', (1296, 1660), '#12181e')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=18)
    for i, state in enumerate(states):
        x, y = (i % 3) * 432, (i // 3) * 332
        draw.text((x + 12, y + 8), f'{state} / {size}', fill='#e5eaf0', font=font)
        with Image.open(out / f'{state}-{size}.png') as im:
            if state == 'site':
                im = im.crop((0, 0, im.width, min(viewport[1], im.height)))
            im.thumbnail((408, 292), Image.Resampling.LANCZOS)
            sheet.paste(im, (x + 12 + (408 - im.width) // 2, y + 34))
    sheet.save(out / f'{size}-inspection.png')
'''
                pillow_version = subprocess.check_output([image_python, '-c', image_script, str(OUT)], text=True).strip()
                for size, page in pages.items():
                    page.goto(f'http://127.0.0.1:{site.server_port}/')
                    page.locator('main').wait_for()
                    snap(page, 'site', size)
                    if size == 'desktop':
                        page.screenshot(path=str(OUT / 'site-desktop-fold.png'), animations='disabled')
                for size, context in contexts:
                    context.tracing.stop(path=str(OUT / f'{size}-trace.zip'))
                    context.close()
                version = browser.version
                browser.close()
        finally:
            site.shutdown()
            site_thread.join(10)
            site.server_close()
            server.should_exit = True
            thread.join(20)
            if thread.is_alive():
                raise RuntimeError('server failed to stop')
    source_status = subprocess.check_output(
        ['git', 'status', '--porcelain', '--', 'src/hutch', 'website'], cwd=ROOT, text=True
    ).strip()
    result = {'browser': 'Firefox', 'version': version, 'python': platform.python_version(),
              'playwright': package_version('playwright'), 'captured_at': datetime.now(timezone.utc).isoformat(),
              'pillow': pillow_version,
              'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'tree': ('application and website sources are clean at this revision' if not source_status
                       else 'application or website sources differ from this revision; per-file source hashes are authoritative'),
              'fixture': 'isolated mock/demo; temporary state removed; loading/cancelling records synthetic', 'captures': records}
    if source_hashes() != source_before:
        raise RuntimeError('application sources changed during capture; repeat against a stable tree')
    result['source_sha256'] = source_before
    (OUT / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'captures': len(records), 'errors': [r for r in records if r['pageErrors'] or r['overflow'] > 1]}))


if __name__ == '__main__':
    main()
