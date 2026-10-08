"""Real-browser checks for the marketing site (website/).

Skipped automatically when Playwright or its Chromium build is not installed:
    pip install playwright && playwright install chromium

These pin behaviour unit tests cannot see: the page is readable with no
JavaScript at all, the intro-gate stays dead, the mobile drawer is a real
dialog with focus ownership, reveals can never strand content, the demo
gate is honestly labelled, and no viewport develops horizontal overflow.
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


def _page(browser, *, width=1440, height=900, reduced_motion="no-preference", js=True):
    ctx = browser.new_context(
        viewport={"width": width, "height": height},
        reduced_motion=reduced_motion,
        java_script_enabled=js,
    )
    page = ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


# ---------------------------------------------------------------- static core

def test_home_loads_clean(browser, site_url):
    ctx, page, errors = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    assert page.title().startswith("hutch")
    assert "Your bots." in page.inner_text("h1.hero-title")
    # signature weave: two registered word layers + a real rendered agent
    assert page.eval_on_selector_all(".weave-word", "e => e.length") == 2
    assert page.eval_on_selector(".weave-agent", "e => e.getBoundingClientRect().width") > 80
    # no intro gate exists at all
    assert page.eval_on_selector_all("#intro", "e => e.length") == 0
    assert not errors, errors
    ctx.close()


def test_no_js_baseline_readable(browser, site_url):
    ctx, page, _ = _page(browser, js=False, width=390, height=844)
    page.goto(site_url, wait_until="load")
    assert page.eval_on_selector(".section-heading", "e => getComputedStyle(e).opacity") == "1"
    assert page.eval_on_selector_all("section .section-heading", "e => e.length") >= 7
    # noscript styles keep section links reachable without enhancement
    assert page.is_visible(".nav-links a[href='#proof']") or page.is_visible(".footer-nav a[href='#proof']")
    ctx.close()


def test_no_external_requests(browser, site_url):
    ctx, page, _ = _page(browser)
    external = []
    page.on("request", lambda r: external.append(r.url) if not (r.url.startswith(site_url) or r.url.startswith("data:")) else None)
    page.goto(site_url, wait_until="networkidle")
    page.wait_for_timeout(600)
    assert external == [], f"unexpected external requests: {external}"
    ctx.close()


def test_reference_patterns_present(browser, site_url):
    """The windowed proof chrome, evidence rows, data-first step cards and the
    model-route pills are the structural upgrades from the design references."""
    ctx, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    assert page.eval_on_selector_all(".proof-chrome .win-dots i", "e => e.length") == 3
    # receipts are a real data table with an evidence pill per row
    assert page.eval_on_selector_all(".rtable tbody tr", "e => e.length") >= 4
    assert page.eval_on_selector_all(".rtable thead th", "e => e.length") == 5
    assert page.eval_on_selector_all(".rtable .c-ans code", "e => e.length") >= 4
    assert page.eval_on_selector_all(".rtable tbody .c-ev .chip", "e => e.length") >= 4
    # feature cards are icon + title + copy; architecture is a separate block
    assert page.eval_on_selector_all("#runs .card-icon", "e => e.length") == 6
    assert page.eval_on_selector_all("#runs .card-title", "e => e.length") == 6
    assert page.eval_on_selector_all("#runs .arch svg", "e => e.length") == 1
    assert page.eval_on_selector_all(".limits-list li", "e => e.length") == 5
    assert page.eval_on_selector_all(".step .step-shot img", "e => e.length") == 3
    routes = page.inner_text(".routes-list")
    for route in ("ollama", "openai", "mock/offline"):
        assert route in routes
    ctx.close()


def test_code_samples_are_distinct_from_prose(browser, site_url):
    """Code lives in chrome-headed windows and colourised blocks, not body text."""
    ctx, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    # window chrome on the terminal and the availability panel
    assert page.eval_on_selector_all(".term-head .win-dots i", "e => e.length") >= 3
    assert page.eval_on_selector_all(".term-head .term-title", "e => e.length") >= 2
    # inline code inside the case cards is syntax-coloured, not plain
    keys = page.eval_on_selector_all(
        ".case-code .k",
        "els => els.map(e => getComputedStyle(e).color)",
    )
    assert len(keys) >= 6
    body = page.eval_on_selector("body", "e => getComputedStyle(e).color")
    assert all(c != body for c in keys), keys
    ctx.close()


def test_agent_frame_set_ships(browser, site_url):
    """The look-at-cursor frame grid exists; the center frame is the still."""
    ctx, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    srcs = page.evaluate("""async () => {
      const made = [];
      for (const s of ['assets/hutch-agent.webp','assets/agent/f3-p1.webp','assets/agent/f0-p0.webp','assets/agent/f6-p2.webp']) {
        const im = new Image();
        const ok = await new Promise(res => { im.onload = () => res(im.naturalWidth > 100); im.onerror = () => res(false); im.src = s; });
        made.push([s, ok]);
      }
      return made;
    }""")
    assert all(ok for _, ok in srcs), srcs
    assert page.get_attribute("#agent", "data-cols") == "7"
    ctx.close()


# ------------------------------------------------------------------- nav

def test_drawer_is_a_real_dialog_with_focus_return(browser, site_url):
    ctx, page, errors = _page(browser, width=390, height=844)
    page.goto(site_url, wait_until="networkidle")
    assert page.get_attribute("#menu-btn", "aria-expanded") == "false"
    page.click("#menu-btn")
    assert page.eval_on_selector("#menu-drawer", "e => e.open") is True
    assert page.get_attribute("#menu-btn", "aria-expanded") == "true"
    assert page.evaluate("document.querySelector('#menu-drawer').contains(document.activeElement)")
    page.keyboard.press("Escape")
    assert page.eval_on_selector("#menu-drawer", "e => e.open") is False
    assert page.evaluate("document.activeElement.id") == "menu-btn"
    assert not errors, errors
    ctx.close()


def test_drawer_link_closes_and_resizes_closed(browser, site_url):
    ctx, page, _ = _page(browser, width=390, height=844)
    page.goto(site_url, wait_until="networkidle")
    page.click("#menu-btn")
    page.click("#menu-drawer a[href='#workflow']")
    assert page.eval_on_selector("#menu-drawer", "e => e.open") is False
    page.click("#menu-btn")
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_timeout(250)
    assert page.eval_on_selector("#menu-drawer", "e => e.open") is False
    ctx.close()


# ----------------------------------------------------------------- effects

def test_reduced_motion_never_hides_content(browser, site_url):
    ctx, page, errors = _page(browser, reduced_motion="reduce")
    page.goto(site_url, wait_until="networkidle")
    page.wait_for_timeout(400)
    opacities = page.eval_on_selector_all(
        ".section-heading, .step, .rtable tbody tr, .case, .proof-figure",
        "els => els.map(e => getComputedStyle(e).opacity)",
    )
    assert all(o == "1" for o in opacities), opacities
    assert not errors, errors
    ctx.close()


def test_reveal_watchdog_shows_everything(browser, site_url):
    """Even if the observer never fired, the watchdog must clear hidden states."""
    ctx, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    page.wait_for_timeout(3400)
    hidden = page.eval_on_selector_all(
        ".reveal",
        "els => els.filter(e => getComputedStyle(e).opacity === '0').length",
    )
    assert hidden == 0, f"{hidden} reveal targets still hidden after watchdog"
    ctx.close()


# ------------------------------------------------------------------ tabs

def test_term_tabs_keyboard_operable(browser, site_url):
    ctx, page, errors = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    page.locator("#tab-deny").focus()
    page.keyboard.press("ArrowRight")
    assert page.get_attribute("#tab-compound", "aria-selected") == "true"
    assert page.eval_on_selector("#panel-deny", "e => e.hidden") is True
    assert not errors, errors
    ctx.close()


# ---------------------------------------------------------------- demo gate

def test_gate_demo_is_labeled_and_deterministic(browser, site_url):
    ctx, page, errors = _page(browser)
    page.goto(site_url + "#workflow", wait_until="networkidle")
    assert "illustrative demo" in page.inner_text("#gate-demo .chip").lower()
    page.click("#gate-allow")
    assert "allowed once" in page.inner_text("#gate-result").lower()
    assert page.eval_on_selector("#gate-reset", "e => !e.classList.contains('hidden')")
    page.click("#gate-reset")
    assert page.eval_on_selector("#gate-result", "e => e.hidden") is True
    page.click("#gate-deny")
    assert "denied" in page.inner_text("#gate-result").lower()
    assert not errors, errors
    ctx.close()


# ------------------------------------------------------------------ facts

def test_honesty_markers_present(browser, site_url):
    ctx, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    body = page.inner_text("body")
    assert "private" in body.lower()
    assert "LIVE" not in body
    assert "not a virtual machine" in body.lower()
    assert "no telemetry" in body.lower()
    ctx.close()


# --------------------------------------------------------------- responsive

@pytest.mark.parametrize("width", [320, 360, 390, 428, 768, 1024, 1440, 1920])
def test_no_horizontal_overflow(browser, site_url, width):
    ctx, page, _ = _page(browser, width=width, height=820)
    page.goto(site_url, wait_until="networkidle")
    page.wait_for_timeout(600)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 1, f"horizontal overflow at {width}px: {overflow}px"
    ctx.close()
