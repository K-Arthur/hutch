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
