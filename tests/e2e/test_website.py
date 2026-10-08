"""Anonymous-browser checks for the static marketing site."""

from __future__ import annotations

import http.server
import socketserver
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

SITE_DIR = Path(__file__).resolve().parents[2] / "website"


@pytest.fixture(scope="module")
def site_url():
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(SITE_DIR), **k)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{port}/"
        httpd.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive(), "marketing preview server did not stop"


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        browser = None
        errors = []
        for engine in (playwright.chromium, playwright.firefox):
            try:
                browser = engine.launch()
                break
            except Exception as exc:  # missing browser build; try the next local engine
                errors.append(f"{engine.name}: {exc}")
        if browser is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield browser
        browser.close()


def _page(browser, *, width=1440, height=900, reduced_motion="no-preference"):
    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion=reduced_motion)
    page = context.new_page()
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return context, page, errors


def test_home_loads_assets_and_truthful_availability(browser, site_url):
    context, page, errors = _page(browser)
    responses = []
    page.on("response", lambda response: responses.append((response.url, response.status)))
    page.goto(site_url, wait_until="networkidle")
    assert page.title().startswith("hutch")
    assert "Your bots." in page.inner_text("h1.hero-title")
    assert page.locator("#proof .chip.demo").count() == 1
    assert page.locator("#get").get_by_text("Public access", exact=True).count() == 1
    assert page.locator("#get .get-row").filter(has_text="Experimental").count() == 1
    assert page.locator("#get .get-row").nth(3).locator(".chip").inner_text() == "Unavailable"
    for image in page.locator("img").all():
        image.evaluate("img => { img.loading = 'eager'; return img.decode(); }")
    assert page.locator("img").evaluate_all("imgs => imgs.every(img => img.complete && img.naturalWidth > 0)")
    broken = [(url, status) for url, status in responses if status >= 400]
    assert not broken, broken
    text = page.locator("body").inner_text().lower()
    assert "provider's own billing controls" in text.replace("’", "'")
    assert "private" in text and "no public package" in text
    assert "hard spend cap" not in text and "jailed workspace" not in text
    assert "github.com/k-arthur/hutch" not in page.content().lower()
    assert not errors, errors
    context.close()


def test_every_internal_link_has_a_target_and_external_refs_are_public(browser, site_url):
    context, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    broken = page.evaluate("""() => [...document.querySelectorAll('a[href^="#"]')]
      .map(a => a.getAttribute('href'))
      .filter(href => href.length > 1 && !document.getElementById(decodeURIComponent(href.slice(1))))""")
    assert not broken, broken
    external = page.locator("a[href^='https://']").evaluate_all("els => els.map(a => a.href)")
    assert len(external) == 3
    assert all("github.com/openclaw/openclaw/issues/138499" in href
               or "github.com/open-webui/open-webui/issues/30055" in href
               or "github.com/open-webui/open-webui/issues/31656" in href for href in external)
    context.close()


def test_reduced_motion_is_reflected_in_controls(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    page.goto(site_url, wait_until="domcontentloaded")
    assert page.get_attribute("#fx-btn", "aria-pressed") == "true"
    assert page.locator(".step").first.evaluate("el => getComputedStyle(el).opacity") == "1"
    page.locator("#fx-btn").click()
    assert page.get_attribute("#fx-btn", "aria-pressed") == "false"
    assert not errors, errors
    context.close()


def test_mobile_drawer_restores_focus_and_site_does_not_overflow(browser, site_url):
    context, page, errors = _page(browser, width=390, height=844)
    page.goto(site_url, wait_until="networkidle")
    assert page.get_attribute("#menu-btn", "aria-expanded") == "false"
    assert not page.locator("#fx-btn").is_visible()
    assert not page.locator(".nav-cta .hero-cta-mirror").is_visible()
    assert page.locator("#menu-btn").is_visible()
    assert not page.locator("#menu-drawer").is_visible()
    page.click("#menu-btn")
    assert page.get_attribute("#menu-btn", "aria-expanded") == "true"
    assert page.locator("#menu-drawer").evaluate("el => el.open")
    assert page.evaluate("document.activeElement.closest('#menu-drawer') !== null")
    page.keyboard.press("Escape")
    assert page.get_attribute("#menu-btn", "aria-expanded") == "false"
    assert not page.locator("#menu-drawer").is_visible()
    assert page.evaluate("document.activeElement.id === 'menu-btn'")
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    assert not errors, errors
    context.close()


def test_tabs_support_arrow_home_end_and_ignore_unrelated_keys(browser, site_url):
    context, page, errors = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    tabs = page.locator(".term-tabs [role=tab]")
    tabs.first.focus()
    page.keyboard.press("ArrowRight")
    assert tabs.nth(1).get_attribute("aria-selected") == "true"
    page.keyboard.press("End")
    assert tabs.last.get_attribute("aria-selected") == "true"
    page.keyboard.press("Home")
    assert tabs.first.get_attribute("aria-selected") == "true"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") != tabs.first.get_attribute("id")
    assert not errors, errors
    context.close()


def test_scripted_approval_demo_is_explicit_and_non_executing(browser, site_url):
    context, page, errors = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    page.click("#gate-allow")
    result = page.inner_text("#gate-result")
    assert "Allowed once (demo)" in result and "Nothing executed" in result
    assert page.locator("#gate-reset").is_visible()
    page.click("#gate-reset")
    assert page.locator("#gate-result").is_hidden()
    assert not errors, errors
    context.close()


@pytest.mark.parametrize('width,height,size',[(1440,1000,'desktop'),(900,1024,'tablet'),(390,844,'phone')])
def test_receipt_proof_is_labelled_and_fits_anonymous_viewports(browser, site_url, width, height, size):
    import hashlib
    import json
    from hutch.models import iso, utcnow
    context, page, errors = _page(browser,width=width,height=height)
    out = SITE_DIR.parent/'docs/realignment/artifacts/action-receipts'
    out.mkdir(parents=True,exist_ok=True)
    try:
        page.goto(site_url,wait_until='networkidle')
        image = page.locator('img[src="assets/captures/proof-receipt.webp"]')
        image.evaluate("img=>{img.loading='eager';return img.decode()}")
        figure = image.locator('xpath=ancestor::figure')
        assert image.evaluate('img=>img.naturalWidth') == (390 if width <= 640 else 1440)
        assert 'Synthetic missing receipt' in figure.inner_text()
        assert 'human report' in figure.inner_text()
        assert 'not live-provider or physical-phone verification' in figure.inner_text()
        figure.screenshot(path=str(out/f'site-{size}.png'),animations='disabled')
        # An oversized locator crop in Firefox can include fixed layers from
        # outside the physical viewport. Preserve the actual viewport too.
        assert page.locator('.skip-link').evaluate('e=>e.getBoundingClientRect().bottom <= 0')
        page.screenshot(path=str(out/f'site-{size}-viewport.png'),animations='disabled')
        overflow = page.evaluate('document.documentElement.scrollWidth-innerWidth')
        assert overflow <= 1 and not errors
        (out/f'site-{size}.json').write_text(json.dumps({
            'captured_at':iso(utcnow()),'browser':browser.browser_type.name,'version':browser.version,'viewport':[width,height],
            'scenario':'Anonymous marketing figure; synthetic missing receipt screenshot; no localhost credentials or provider access',
            'figure_capture_note':'Inspect the viewport PNG for fixed navigation; an oversized Firefox locator crop includes off-viewport fixed layers.',
            'page_errors':errors,'horizontal_overflow':overflow,
            'source_sha256':{str(p.relative_to(SITE_DIR.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              (SITE_DIR/'index.html',SITE_DIR/'styles.css',SITE_DIR/'assets/captures/proof-receipt.webp',
                               SITE_DIR/'assets/captures/proof-receipt-phone.webp')},
        },indent=2)+'\n')
    finally:
        context.close()


@pytest.mark.parametrize('width,height,size',[(1440,1000,'desktop'),(900,1024,'tablet'),(390,844,'phone')])
def test_database_snapshot_scope_is_readable_and_has_no_executor_requests(browser, site_url, width, height, size):
    import hashlib
    import json
    from hutch.models import iso, utcnow
    context, page, errors = _page(browser, width=width, height=height, reduced_motion='reduce')
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    out = SITE_DIR.parent / 'docs/realignment/artifacts/restoration'
    out.mkdir(parents=True, exist_ok=True)
    try:
        page.goto(site_url, wait_until='networkidle')
        state = page.locator('#runs .spec').filter(has=page.get_by_text('State', exact=True))
        text = state.inner_text()
        assert 'execution held for review' in text and 'new directory' in text
        assert 'Credentials, browser profiles and user files need separate backups' in text
        state_text = text.lower()
        assert 'require human review before recall' in state_text and 'sharing across a bot' in state_text
        assert 'archiving retains fact and review history' in state_text and 'permanent scoped deletion remain unfinished' in state_text
        state.scroll_into_view_if_needed()
        state.screenshot(path=str(out / f'site-{size}-state.png'), animations='disabled')
        page.screenshot(path=str(out / f'site-{size}-viewport.png'), animations='disabled')
        overflow = page.evaluate('document.documentElement.scrollWidth - innerWidth')
        assert overflow <= 1 and not errors
        assert all(url.startswith(site_url) for url in requests), 'static site contacted another origin'
        (out / f'site-{size}.json').write_text(json.dumps({
            'captured_at': iso(utcnow()), 'browser': browser.browser_type.name, 'version': browser.version,
            'viewport': [width, height], 'page_errors': errors, 'horizontal_overflow': overflow,
            'scenario': 'Anonymous static database-snapshot scope; no executor requests or credentials',
            'source_sha256': {str(p.relative_to(SITE_DIR.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (SITE_DIR/'index.html', SITE_DIR/'styles.css', SITE_DIR/'site.js')},
        }, indent=2) + '\n')
    finally:
        context.close()
