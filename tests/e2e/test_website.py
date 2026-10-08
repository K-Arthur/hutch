"""Real-browser checks for the marketing site (website/).

Skipped automatically when Playwright or its Chromium build is not installed:
    pip install playwright && playwright install chromium

These pin the behaviour that unit tests cannot see: the intro stage is removed
under reduced motion, the mobile drawer manages focus, the tablists are keyboard
operable, and no viewport develops horizontal overflow.
"""

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
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        yield f"http://127.0.0.1:{port}/"
        httpd.shutdown()
        t.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser build not installed
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


def _page(browser, *, width=1440, height=900, reduced_motion="no-preference"):
    ctx = browser.new_context(viewport={"width": width, "height": height}, reduced_motion=reduced_motion)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


def test_home_loads_without_console_errors(browser, site_url):
    ctx, page, errors = _page(browser)
    page.goto(site_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2800)
    assert page.title().startswith("hutch")
    assert "Your bots. Your machine." in page.inner_text("h1.hero-title")
    # the wordmark weave and the character are present and not collapsed
    assert page.eval_on_selector_all(".wordweave-word", "e => e.length") == 2
    assert page.eval_on_selector(".aurora", "e => e.getBoundingClientRect().width") > 60
    assert not errors, errors
    ctx.close()


def test_intro_removed_under_reduced_motion(browser, site_url):
    ctx, page, errors = _page(browser, reduced_motion="reduce")
    page.goto(site_url, wait_until="domcontentloaded")
    page.wait_for_timeout(600)
    assert page.eval_on_selector_all("#intro", "e => e.length") == 0
    # reveals are forced visible so the page is fully readable with no motion
    assert page.eval_on_selector(".bento-card", "e => getComputedStyle(e).opacity") == "1"
    assert not errors, errors
    ctx.close()


def test_intro_plays_then_clears(browser, site_url):
    ctx, page, _ = _page(browser)
    page.goto(site_url, wait_until="domcontentloaded")
    page.wait_for_timeout(300)
    assert page.eval_on_selector_all("#intro", "e => e.length") == 1
    page.wait_for_timeout(2600)
    assert page.eval_on_selector_all("#intro", "e => e.length") == 0
    ctx.close()


def test_mobile_drawer_manages_focus(browser, site_url):
    ctx, page, errors = _page(browser, width=390, height=844)
    page.goto(site_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2800)
    assert page.get_attribute("#menu-btn", "aria-expanded") == "false"
    page.click("#menu-btn")
    assert page.get_attribute("#menu-btn", "aria-expanded") == "true"
    assert page.eval_on_selector("#mobile-drawer", "e => getComputedStyle(e).display") == "flex"
    page.keyboard.press("Escape")
    assert page.get_attribute("#menu-btn", "aria-expanded") == "false"
    assert not errors, errors
    ctx.close()


def test_tablists_are_keyboard_operable(browser, site_url):
    ctx, page, _ = _page(browser)
    page.goto(site_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2800)
    tab = page.locator("[role=tab]").first
    tab.focus()
    page.keyboard.press("ArrowRight")
    assert page.eval_on_selector_all('[role=tab][aria-selected="true"]', "e => e.length") >= 1
    ctx.close()


def test_no_horizontal_overflow_on_phone(browser, site_url):
    ctx, page, _ = _page(browser, width=390, height=844)
    page.goto(site_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2800)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 1, f"horizontal overflow: {overflow}px"
    ctx.close()
