"""Anonymous browser and visual checks for the static marketing site."""

from __future__ import annotations

import hashlib
import http.server
import json
import platform
import socketserver
import threading
from datetime import datetime, timezone
from html.parser import HTMLParser
from importlib.metadata import version as package_version
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = ROOT / "website"


class _LocalAssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, _tag, attrs):
        attributes = dict(attrs)
        self.urls.extend(attributes[key] for key in ("href", "src") if attributes.get(key))
        for candidate in attributes.get("srcset", "").split(","):
            parts = candidate.strip().split()
            if parts:
                self.urls.append(parts[0])


def test_local_asset_urls_use_current_content_hashes():
    parser = _LocalAssetReferences()
    parser.feed((SITE_DIR / "index.html").read_text(encoding="utf-8"))
    site_root = SITE_DIR.resolve()
    checked = 0
    for url in parser.urls:
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
            continue
        path = (site_root / unquote(parsed.path)).resolve()
        try:
            path.relative_to(site_root)
        except ValueError:
            continue
        if not path.is_file():
            continue
        expected = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
        assert parse_qs(parsed.query).get("v") == [expected], (
            f"stale local asset cache key for {url}: expected v={expected}"
        )
        checked += 1
    assert checked >= 7


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
            except Exception as exc:
                errors.append(f"{engine.name}: {exc}")
        if browser is None:
            pytest.skip("no Playwright browser is installed: " + "; ".join(errors))
        yield browser
        browser.close()


def _page(browser, *, width=1440, height=900, reduced_motion="no-preference", js=True):
    context = browser.new_context(
        viewport={"width": width, "height": height},
        reduced_motion=reduced_motion,
        java_script_enabled=js,
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return context, page, errors


def test_home_loads_real_assets_and_truthful_availability(browser, site_url):
    context, page, errors = _page(browser)
    responses = []
    page.on("response", lambda response: responses.append((response.url, response.status)))
    page.goto(site_url, wait_until="networkidle")
    assert page.title().startswith("hutch")
    assert "Your bots." in page.inner_text("h1.hero-title")
    assert page.locator("#proof .proof-img").count() == 1
    assert "Real application" in page.inner_text("#proof .proof-chrome")
    assert "empty state directory" in page.inner_text("#proof")
    assert page.locator("#gate-card, #gate-demo, #gate-allow, #gate-deny").count() == 0
    assert page.locator("#get").get_by_text("Public access", exact=True).count() == 1
    assert page.locator("#get .ev").filter(has_text="Experimental").count() >= 1
    assert page.locator("#get .ev").filter(has_text="Unavailable").count() >= 1
    for image in page.locator("img").all():
        image.evaluate("img => { img.loading = 'eager'; return img.decode(); }")
    assert page.locator("img").evaluate_all("imgs => imgs.every(img => img.complete && img.naturalWidth > 0)")
    broken = [(url, status) for url, status in responses if status >= 400]
    assert not broken, broken
    # Include closed FAQ answers: their risk and billing qualifications are
    # intentionally collapsed until a visitor chooses to read them.
    text = page.locator("body").text_content().lower().replace("’", "'")
    for retired in ("deterministic mock", "mock/offline", "scripted gate", "no telemetry"):
        assert retired not in text, retired
    assert "provider's own billing controls" in text
    assert "private" in text and "public package or release" in text
    assert "not a virtual machine" in text
    assert "browser egress" in text and "non-http" in text
    assert "sign in with chatgpt is an opt-in local preview" in text
    assert "eligibility for hutch is unconfirmed" in text
    assert "does not allow a provider-enforced output-token limit" in text
    assert "chatgpt sign-in is not implemented" not in text
    assert "github.com/k-arthur/hutch" not in page.content().lower()
    assert not errors, errors
    context.close()


def test_internal_links_resolve_and_external_links_are_public_reports(browser, site_url):
    context, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    broken = page.evaluate("""() => [...document.querySelectorAll('a[href^="#"]')]
      .map(a => a.getAttribute('href'))
      .filter(href => href.length > 1 && !document.getElementById(decodeURIComponent(href.slice(1))))""")
    assert not broken, broken
    external = page.locator("a[href^='https://']").evaluate_all("els => els.map(a => a.href)")
    assert len(external) == 3, external
    assert all("github.com/openclaw/openclaw/issues/138499" in href
               or "github.com/open-webui/open-webui/issues/30055" in href
               or "github.com/open-webui/open-webui/issues/31656" in href for href in external)
    context.close()


def test_static_site_makes_no_external_requests(browser, site_url):
    context, page, _ = _page(browser)
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    page.goto(site_url, wait_until="networkidle")
    page.wait_for_timeout(350)
    assert external == [], external
    context.close()


def test_public_workflow_describes_named_recurring_tasks(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    out = ROOT / "docs/realignment/artifacts/workspace-task-dispatch/site"
    out.mkdir(parents=True, exist_ok=True)
    index = (SITE_DIR / "index.html").read_bytes()
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    captures = []
    try:
        page.goto(site_url, wait_until="networkidle")
        workflow = page.locator("#workflow")
        assert "named recurring tasks" in workflow.inner_text().lower()
        assert "local supervisor" in page.locator("body").inner_text().lower()
        assert "built-in chat can ask you to choose among options" in workflow.inner_text().lower()
        assert "your answer continues the conversation and never approves an action" in workflow.inner_text().lower()
        assert "experimental coordinator handoff" in workflow.inner_text().lower()
        assert "content-free progress timeline" in workflow.inner_text().lower()
        assert "continue only from a safe checkpoint" in workflow.inner_text().lower()
        assert "starts a fresh run" in workflow.inner_text().lower()
        assert "attach only the exact specialist reply you choose" in workflow.inner_text().lower()
        assert "as untrusted text" in workflow.inner_text().lower()
        assert "up to eight current, approved coordinator facts for that task alone" in workflow.inner_text().lower()
        assert "providers may retain submitted copies" in workflow.inner_text().lower()
        assert "locally suggests a professional display name and stable address" in workflow.inner_text().lower()
        assert "without an extra model request" in workflow.inner_text().lower()
        assert "both values remain editable" in workflow.inner_text().lower()
        for label, width, height in (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            workflow.get_by_role("heading", name="Keep each task reviewable from request to result.").scroll_into_view_if_needed()
            workflow.screenshot(
                path=str(out / f"site-workflow-{label}.png"), animations="disabled",
                style="body > header { display: none !important; } .skip-link { display: none !important; }")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "overflow": overflow})
        assert not external, external
        assert not errors, errors
        (out / "site-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "browser": browser.version,
            "index_sha256": hashlib.sha256(index).hexdigest(), "captures": captures,
            "anonymous": True, "external_requests": len(external), "page_errors": errors,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        context.close()


def test_public_bot_setup_copy_matches_reviewed_chat_sourced_creation(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    out = ROOT / "docs/realignment/artifacts/bot-setup-context/site"
    out.mkdir(parents=True, exist_ok=True)
    source = (SITE_DIR / "index.html").read_bytes()
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    captures = []
    try:
        page.goto(site_url, wait_until="networkidle")
        card = page.locator("#workflow .step-card").first
        text = card.inner_text().lower()
        assert "latest chat request" in text
        assert "optionally select earlier user messages from that chat as saved background" in text
        assert "assistant replies and other chats stay excluded" in text
        assert "professional display name and stable address" in text
        assert "without an extra model request" in text
        assert "model route from that bot or your workspace" in text
        assert "no tools" in text and "no schedule" in text
        assert "recurring work" in text
        assert "does not start a run" in text
        model_card = page.locator("#runs .feature").filter(has_text="Hutch supports configured OpenAI").first
        model_text = model_card.inner_text().lower()
        assert "next message" in model_text
        assert "save as bot default" in model_text
        assert "scheduled runs" in model_text
        for label, width, height in (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            card.scroll_into_view_if_needed()
            card.screenshot(path=str(out / f"site-chat-bot-setup-{label}.png"), animations="disabled")
            box = card.bounding_box()
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1 and box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1, (label, box, overflow)
            captures.append({"size": label, "viewport": [width, height], "card": box, "overflow": overflow})
            model_card.scroll_into_view_if_needed()
            model_card.screenshot(path=str(out / f"site-model-default-choice-{label}.png"), animations="disabled")
            model_box = model_card.bounding_box()
            assert overflow <= 1 and model_box and model_box["x"] >= 0 and model_box["x"] + model_box["width"] <= width + 1, (label, model_box, overflow)
            captures.append({"size": label, "viewport": [width, height], "model_card": model_box, "overflow": overflow})
        assert not external, external
        assert not errors, errors
        (out / "site-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_website.py::test_public_bot_setup_copy_matches_reviewed_chat_sourced_creation",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_website.py::test_public_bot_setup_copy_matches_reviewed_chat_sourced_creation",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "browser": browser.version,
            "playwright_version": package_version("playwright"),
            "index_sha256": hashlib.sha256(source).hexdigest(), "captures": captures,
            "anonymous": True, "external_requests": len(external), "page_errors": errors,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        context.close()


def test_provider_availability_is_readable_without_horizontal_page_scroll(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    page.goto(site_url, wait_until="networkidle")
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    out = ROOT / "docs/realignment/artifacts/provider-signin"
    out.mkdir(parents=True, exist_ok=True)
    source = (SITE_DIR / "index.html").read_bytes()
    styles = (SITE_DIR / "styles.css").read_bytes()
    viewports = (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844))
    try:
        assert page.locator("#get .availability").get_by_text("Public access", exact=True).count() == 1
        availability = page.locator("#get").inner_text().lower()
        assert "opencode go api-key handoff" in availability
        assert "chatgpt sign-in preview" in availability
        assert "eligibility unconfirmed" in availability
        assert "read-only google/outlook calendar" in availability
        assert "account consent unverified" in availability
        assert "outlook mail" not in availability
        assert page.locator("a[href='#get']").count() >= 1
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.get_by_role("heading", name="How to get hutch").scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"marketing-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
        feature_sizes = (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844))
        for label, width, height in feature_sizes:
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#runs").screenshot(
                path=str(out / f"marketing-features-{label}.png"), animations="disabled",
                style="body > header { display: none !important; } .skip-link { display: none !important; }")
            cards = page.locator("#runs .feature .card-body")
            assert cards.count() == 6
            for index in range(cards.count()):
                card = cards.nth(index)
                icon_box = card.locator(".card-icon").bounding_box()
                title_box = card.locator(".card-title").bounding_box()
                assert icon_box and title_box
                assert icon_box["x"] + icon_box["width"] <= title_box["x"] + 1, (label, index, icon_box, title_box)
                assert abs((icon_box["y"] + icon_box["height"] / 2) -
                           (title_box["y"] + title_box["height"] / 2)) <= 2, (label, index, icon_box, title_box)
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
        assert external == [], external
        assert not errors, errors
        (out / "marketing-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_website.py::test_provider_availability_is_readable_without_horizontal_page_scroll",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_website.py::test_provider_availability_is_readable_without_horizontal_page_scroll",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "browser": browser.version,
            "index_sha256": hashlib.sha256(source).hexdigest(),
            "styles_sha256": hashlib.sha256(styles).hexdigest(),
            "viewports": [{"name": label, "width": width, "height": height}
                          for label, width, height in viewports],
            "feature_grid_viewports": [{"name": label, "width": width, "height": height}
                                       for label, width, height in feature_sizes],
            "feature_heading_layout": "icon and heading share a row",
            "anonymous": True, "external_requests": len(external),
        }, indent=2) + "\n")
    finally:
        context.close()


def test_outlook_calendar_support_row_is_truthful_and_reachable_at_all_viewports(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    out = ROOT / "docs/realignment/artifacts/outlook-calendar/site"
    out.mkdir(parents=True, exist_ok=True)
    source = (SITE_DIR / "index.html").read_bytes()
    styles = (SITE_DIR / "styles.css").read_bytes()
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    captures = []
    try:
        page.goto(site_url, wait_until="networkidle")
        row = page.locator("#get .availability tbody tr").filter(has_text="Outlook Calendar")
        assert row.count() == 1
        text = row.inner_text().lower()
        assert "experimental" in row.inner_text().lower()
        assert "account consent unverified" in text
        assert "password/captcha handoff" in text
        assert "browser field detection" in text
        assert "outlook mail" not in page.locator("#get").inner_text().lower()
        wrapper = page.locator("#get .overflow-x-auto")
        for label, width, height in (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.evaluate("document.documentElement.style.scrollBehavior = 'auto'")
            page.locator("#get .availability").evaluate(
                "element => window.scrollTo(0, window.scrollY + element.getBoundingClientRect().top - 80)")
            page.screenshot(path=str(out / f"availability-viewport-{label}.png"), animations="disabled")
            page.locator("#get .availability").screenshot(
                path=str(out / f"availability-table-{label}.png"), animations="disabled")
            metrics = wrapper.evaluate("element => ({scrollWidth: element.scrollWidth, clientWidth: element.clientWidth})")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            assert metrics["scrollWidth"] <= metrics["clientWidth"] + 1, (label, metrics)
            if width <= 640:
                assert page.locator("#get .availability thead th:visible").count() == 2
            captures.append({"size": label, "viewport": [width, height], "table": metrics,
                             "table_capture": f"availability-table-{label}.png",
                             "viewport_capture": f"availability-viewport-{label}.png",
                             "page_overflow": overflow})
        assert not external, external
        assert not errors, errors
        (out / "site-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_website.py::test_outlook_calendar_support_row_is_truthful_and_reachable_at_all_viewports",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "browser": browser.version,
            "playwright_version": package_version("playwright"),
            "index_sha256": hashlib.sha256(source).hexdigest(),
            "styles_sha256": hashlib.sha256(styles).hexdigest(),
            "captures": captures, "anonymous": True,
            "external_requests": external, "page_errors": errors,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        context.close()


def test_no_javascript_keeps_the_page_readable(browser, site_url):
    context, page, _ = _page(browser, width=390, height=844, js=False)
    page.goto(site_url, wait_until="load")
    assert page.locator(".section-heading").count() >= 7
    assert page.locator(".section-heading").first.evaluate("el => getComputedStyle(el).opacity") == "1"
    assert page.locator(".navbar-center a[href='#proof']").is_visible()
    context.close()


def test_reduced_motion_never_hides_content(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    page.goto(site_url, wait_until="networkidle")
    page.wait_for_timeout(400)
    opacities = page.locator(".section-heading, .step-card, .receipts tbody tr, .case, .proof-figure")
    assert all(value == "1" for value in opacities.evaluate_all("els => els.map(e => getComputedStyle(e).opacity)"))
    assert not errors, errors
    context.close()


def test_reveal_watchdog_shows_everything(browser, site_url):
    context, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    page.wait_for_timeout(3400)
    hidden = page.locator(".reveal").evaluate_all("els => els.filter(e => getComputedStyle(e).opacity === '0').length")
    assert hidden == 0, f"{hidden} reveal targets remain hidden"
    context.close()


def test_mobile_drawer_focus_and_ctas(browser, site_url):
    context, page, errors = _page(browser, width=390, height=844)
    page.goto(site_url, wait_until="networkidle")
    assert page.get_attribute("#menu-btn", "aria-expanded") == "false"
    assert page.locator("#menu-btn").is_visible()
    assert not page.locator("#menu-drawer").is_visible()
    page.click("#menu-btn")
    assert page.locator("#menu-drawer").evaluate("el => el.open")
    assert page.evaluate("document.querySelector('#menu-drawer').contains(document.activeElement)")
    page.keyboard.press("Escape")
    assert not page.locator("#menu-drawer").evaluate("el => el.open")
    assert page.evaluate("document.activeElement.id === 'menu-btn'")
    assert page.locator("a[href='#get']").count() >= 2
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
    assert not errors, errors
    context.close()


def test_term_tabs_keyboard_operable(browser, site_url):
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
    assert not errors, errors
    context.close()


@pytest.mark.parametrize("width,height,size", [(1440, 1000, "desktop"), (900, 1024, "tablet"), (390, 844, "phone")])
def test_real_setup_capture_is_truthful_and_fits_anonymous_viewports(browser, site_url, width, height, size):
    from hutch.models import iso, utcnow

    context, page, errors = _page(browser, width=width, height=height, reduced_motion="reduce")
    out = ROOT / "docs/realignment/artifacts/no-mock-setup/site"
    out.mkdir(parents=True, exist_ok=True)
    try:
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto(site_url, wait_until="networkidle")
        image = page.locator("img[src^='assets/captures/setup-desktop.webp']")
        image.evaluate("img => { img.loading='eager'; return img.decode(); }")
        figure = image.locator("xpath=ancestor::figure")
        assert image.evaluate("img => img.naturalWidth") == (390 if width <= 640 else 1440)
        assert "state directory was empty" in figure.inner_text()
        assert "no provider call" in figure.inner_text()
        assert page.locator("#gate-card, #gate-demo").count() == 0
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(out / f"site-{size}.png"), animations="disabled", full_page=True)
        page.screenshot(path=str(out / f"site-{size}-viewport.png"), animations="disabled")
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1 and not errors
        assert all(url.startswith(site_url) for url in requests), "static site requested another origin"
        files = [SITE_DIR / path for path in (
            "index.html", "styles.css", "site.js", "app.css", "tokens.css",
            "assets/captures/setup-desktop.webp", "assets/captures/setup-phone.webp")]
        (out / f"site-{size}.json").write_text(json.dumps({
            "captured_at": iso(utcnow()), "browser": browser.browser_type.name, "version": browser.version,
            "viewport": [width, height],
            "scenario": "Anonymous static site with an actual empty first-run app capture; no provider or executor requests",
            "page_errors": errors, "horizontal_overflow": overflow,
            "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in files},
        }, indent=2) + "\n")
    finally:
        context.close()


def test_snapshot_and_workspace_limits_are_explained(browser, site_url):
    context, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    text = page.locator("#runs").text_content().lower()
    for phrase in ("back up", "fresh per run", "managed folder", "survive bot deletion", "database snapshots"):
        assert phrase in text, phrase
    context.close()


@pytest.mark.parametrize("width", [320, 360, 390, 428, 768, 900, 1024, 1440, 1920])
def test_no_horizontal_overflow(browser, site_url, width):
    context, page, _ = _page(browser, width=width, height=820, reduced_motion="reduce")
    page.goto(site_url, wait_until="networkidle")
    page.wait_for_timeout(250)
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 1, f"horizontal overflow at {width}px: {overflow}px"
    context.close()
