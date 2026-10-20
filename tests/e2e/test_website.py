"""Anonymous browser and visual checks for the static marketing site."""

from __future__ import annotations

from tests.support.browser import wait_for_page

import hashlib
import http.server
import json
import os
import platform
import socketserver
import threading
from datetime import datetime, timezone
from html.parser import HTMLParser
from importlib.metadata import version as package_version
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from tests.support.artifacts import artifact_path

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
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(site_url, wait_until="networkidle")
    assert page.title().startswith("hutch")
    assert "A little help with what’s next." in page.inner_text("h1.hero-title")
    mascot = page.locator("img.weave-agent")
    assert mascot.count() == 1 and "assets/hutch-agent.webp" in mascot.get_attribute("src")
    assert page.locator(".hero-promises li").count() == 3
    assert page.locator(".benefit-card").count() == 3
    assert page.locator(".benefit-art svg").count() == 7  # The three illustrated cards include 7 distinct icon paths.
    assert page.locator("#proof .proof-img").count() == 1
    assert "Real application" in page.inner_text("#proof .proof-chrome")
    assert "carries your words into assistant setup" in page.inner_text("#proof")
    assert "2026-10-10" in page.inner_text("#proof")
    assert page.locator("#gate-card, #gate-demo, #gate-allow, #gate-deny").count() == 0
    assert page.locator("#get").get_by_text("Public access", exact=True).count() == 1
    assert page.locator("#get .ev").filter(has_text="Experimental").count() >= 1
    assert page.locator("#get .ev").filter(has_text="Unavailable").count() >= 1
    workflow_details = page.locator(".workflow-details")
    assert workflow_details.count() == 3
    assert all(not detail.evaluate("el => el.open") for detail in workflow_details.all())
    workflow_details.nth(1).locator("summary").click()
    coordinator_card = page.locator(".step-card").filter(has_text="Experimental coordinator handoff")
    assert "only assistants on the owner-approved roster can receive a new task" in coordinator_card.inner_text()
    assert "changing the roster never stops existing work" in coordinator_card.inner_text()
    saved_requests_card = page.locator(".step-card").filter(has_text="Come back to the result")
    workflow_details.nth(2).locator("summary").click()
    saved_requests_copy = saved_requests_card.inner_text().lower()
    assert "save a reviewed request in hutch’s local library" in saved_requests_copy
    assert "choosing one fills a draft only; you still review and send it yourself" in saved_requests_copy
    workflow_details.evaluate_all("els => els.forEach(el => el.open = false)")
    for image in page.locator("img").all():
        image.evaluate("img => { img.loading = 'eager'; return img.decode(); }")
    assert page.locator("img").evaluate_all("imgs => imgs.every(img => img.complete && img.naturalWidth > 0)")
    assert mascot.evaluate("img => img.naturalWidth > 0")
    broken = [(url, status) for url, status in responses if status >= 400]
    assert not broken, broken
    # Include closed FAQ answers: their risk and billing qualifications are
    # intentionally collapsed until a visitor chooses to read them.
    text = page.locator("body").text_content().lower().replace("’", "'")
    for retired in ("deterministic mock", "mock/offline", "scripted gate", "no telemetry"):
        assert retired not in text, retired
    assert "provider-side billing limits" in text
    assert "can i review cost and context before sending?" in text
    assert "bounded recent conversation context" in text
    assert "automatic classification is not enabled" in text
    assert "private" in text and "no anonymous download or public release" in text
    assert "not a virtual machine" in text
    assert "fixture-tested dns pinning" in text and "browser field detection" in text
    assert "sign in with chatgpt is an opt-in local preview" in text
    assert "eligibility for hutch is unconfirmed" in text
    assert "does not enforce hutch's output-token allowance" in text
    assert "scheduled or coordinator-assigned work needs your express permission for each bot and connected account" in text
    assert "chatgpt sign-in is not implemented" not in text
    assert "github.com/k-arthur/hutch" not in page.content().lower()
    assert not errors, errors
    external_requests = [url for url in requests if urlsplit(url).netloc not in {urlsplit(site_url).netloc, ""}]
    assert not external_requests, external_requests
    out = artifact_path("assistant-first-ui/marketing")
    out.mkdir(parents=True, exist_ok=True)
    viewports = (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844))
    for label, width, height in viewports:
        page.set_viewport_size({"width": width, "height": height})
        page.evaluate("scrollTo(0, 0)")
        assert mascot.is_visible()
        page.screenshot(path=str(out / f"site-mascot-{label}.png"), animations="disabled")
    (out / "site-mascot-validation.json").write_text(json.dumps({
        "test": "tests/e2e/test_website.py::test_home_loads_real_assets_and_truthful_availability",
        "browser": browser.version, "playwright": package_version("playwright"),
        "mascot_asset": mascot.get_attribute("src"), "natural_width": mascot.evaluate("img => img.naturalWidth"),
        "provider_calls": 0, "external_requests": len(external_requests), "page_errors": errors,
        "viewports": [{"name": label, "size": [width, height]} for label, width, height in viewports],
        "source_sha256": hashlib.sha256((ROOT / "website/index.html").read_bytes()).hexdigest(),
    }, indent=2) + "\n", encoding="utf-8")
    saved_out = artifact_path("assistant-first-ui/marketing/repeat-work")
    saved_out.mkdir(parents=True, exist_ok=True)
    saved_viewports = []
    for label, width, height in viewports:
        page.set_viewport_size({"width": width, "height": height})
        saved_requests_card.evaluate("element => element.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'})")
        card_box = saved_requests_card.bounding_box()
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert card_box and card_box["y"] >= -1 and card_box["y"] + card_box["height"] <= height + 1, (label, card_box)
        assert overflow <= 1, (label, overflow)
        page.screenshot(path=str(saved_out / f"marketing-repeat-work-{label}.png"), animations="disabled")
        saved_viewports.append({"name": label, "size": [width, height], "card": card_box, "overflow": overflow})
    (saved_out / "validation.json").write_text(json.dumps({
        "test": "tests/e2e/test_website.py::test_home_loads_real_assets_and_truthful_availability",
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright_version": package_version("playwright"), "external_requests": external_requests,
        "page_errors": errors, "provider_calls": 0, "viewports": saved_viewports,
        "source_sha256": hashlib.sha256((ROOT / "website/index.html").read_bytes()).hexdigest(),
        "verified": ["local saved-request library is described", "reuse fills a draft without sending",
                     "responsive marketing card has no horizontal overflow"],
    }, indent=2) + "\n", encoding="utf-8")
    handoff_out = artifact_path("assistant-first-ui/marketing/specialists")
    handoff_out.mkdir(parents=True, exist_ok=True)
    for label, width, height in viewports:
        page.set_viewport_size({"width": width, "height": height})
        coordinator_card.evaluate("element => element.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'})")
        card_box = coordinator_card.bounding_box()
        assert card_box and card_box["y"] >= -1 and card_box["y"] + card_box["height"] <= height + 1, (label, card_box)
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
        page.screenshot(path=str(handoff_out / f"marketing-roster-{label}.png"), animations="disabled")
    (handoff_out / "validation.json").write_text(json.dumps({
        "test": "tests/e2e/test_website.py::test_home_loads_real_assets_and_truthful_availability",
        "browser": browser.browser_type.name, "browser_version": browser.version,
        "playwright_version": package_version("playwright"), "external_requests": len(external_requests),
        "page_errors": errors, "provider_calls": 0,
        "viewports": {label: [width, height] for label, width, height in viewports},
        "source_sha256": hashlib.sha256((ROOT / "website/index.html").read_bytes()).hexdigest(),
    }, indent=2) + "\n", encoding="utf-8")
    context.close()


def test_marketing_card_hierarchy_and_mobile_labels_are_readable(browser, site_url):
    """Keep feature icons with their labels and make mobile helper text legible."""
    context, page, errors = _page(browser, width=1440, height=960, reduced_motion="reduce")
    output = artifact_path("marketing-card-hierarchy-2026-10-10")
    output.mkdir(parents=True, exist_ok=True)
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    captures = []
    trace_stopped = False
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        for label, width, height in (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844), ("compact-phone", 320, 740)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto(site_url, wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            values = page.evaluate("""() => {
              const metrics = selector => {
                const element = document.querySelector(selector);
                const style = getComputedStyle(element);
                return {fontSize: parseFloat(style.fontSize), lineHeight: parseFloat(style.lineHeight)};
              };
              return {
                choiceHead: getComputedStyle(document.querySelector('.choice-heading')).display,
                reviewHead: getComputedStyle(document.querySelector('.review-flow-heading')).display,
                choiceIconBackground: getComputedStyle(document.querySelector('.choice-icon')).backgroundColor,
                choiceIconWidth: parseFloat(getComputedStyle(document.querySelector('.choice-icon')).width),
                heroSceneBackground: getComputedStyle(document.querySelector('.hero-scene')).backgroundImage,
                heroSceneDecorations: [
                  getComputedStyle(document.querySelector('.hero-scene'), '::before').content,
                  getComputedStyle(document.querySelector('.hero-scene'), '::after').content,
                ],
                heroSceneGlowCount: document.querySelectorAll('.hero-scene-glow').length,
                heroNote: metrics('.hero-note small'),
                heroPromise: metrics('.hero-promises li'),
                exampleLabel: metrics('.case-kicker'),
                scrollWidth: document.documentElement.scrollWidth,
              };
            }""")
            assert values["choiceHead"] == values["reviewHead"] == "flex", (label, values)
            assert values["choiceIconBackground"] == "rgba(0, 0, 0, 0)", (label, values)
            assert values["choiceIconWidth"] <= 40, (label, values)
            assert "radial-gradient" not in values["heroSceneBackground"], (label, values)
            assert values["heroSceneDecorations"] == ["none", "none"], (label, values)
            assert values["heroSceneGlowCount"] == 0, (label, values)
            for key in ("heroNote", "heroPromise", "exampleLabel"):
                assert values[key]["fontSize"] >= 12, (label, key, values[key])
                assert values[key]["lineHeight"] >= values[key]["fontSize"] * 1.35, (label, key, values[key])
            overflow = values["scrollWidth"] - width
            assert overflow <= 1, (label, overflow)
            screenshots = []
            if label in {"desktop", "tablet", "phone"}:
                page.evaluate("scrollTo(0, 0)")
                filename = f"website-{label}.png"
                page.screenshot(path=str(output / filename), animations="disabled")
                screenshots.append(filename)
                for selector, name in (("#runs .choice-grid", "choices"), ("#control .review-flow", "review-flow"),
                                       ("#receipts .benefit-grid", "everyday-help"), ("#cases .grid", "examples")):
                    section = page.locator(selector)
                    if label == "phone" and name in {"everyday-help", "examples"}:
                        cards = section.locator("article")
                        for index in range(cards.count()):
                            card = cards.nth(index)
                            card.evaluate("element => element.scrollIntoView({block: 'center', behavior: 'instant'})")
                            box = card.bounding_box()
                            assert box and box["y"] >= 80 and box["y"] + box["height"] <= height, (name, index, box)
                            filename = f"{name}-{index + 1}-{label}.png"
                            card.screenshot(path=str(output / filename), animations="disabled")
                            screenshots.append(filename)
                    else:
                        filename = f"{name}-{label}.png"
                        section.screenshot(path=str(output / filename), animations="disabled")
                        screenshots.append(filename)
            captures.append({"size": label, "viewport": [width, height], **values,
                             "horizontal_overflow": overflow, "screenshots": screenshots})
        assert not errors, errors
        external = [url for url in requests if not url.startswith(site_url)]
        assert not external, external
        files = [SITE_DIR / path for path in ("index.html", "styles.css", "tokens.css", "app.css")]
        (output / "validation.json").write_text(json.dumps({
            "browser": page.context.browser.browser_type.name,
            "browser_version": page.context.browser.version,
            "playwright_version": package_version("playwright"),
            "provider_calls": 0,
            "external_requests": external,
            "page_errors": errors,
            "captures": captures,
            "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        }, indent=2) + "\n", encoding="utf-8")
        context.tracing.stop(path=str(output / "trace.zip"))
        trace_stopped = True
    finally:
        if not trace_stopped:
            try:
                context.tracing.stop(path=str(output / "trace-failed.zip"))
            except Exception:
                pass
        context.close()


def test_chatgpt_background_consent_marketing_copy_at_responsive_sizes(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    out = artifact_path("chatgpt-background-consent/marketing")
    out.mkdir(parents=True, exist_ok=True)
    external: list[str] = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(site_url, wait_until="networkidle")
        page.locator("#runs .technical-details > summary").click()
        card = page.locator("#runs article.feature").filter(has=page.get_by_role("heading", name="Plans & keys"))
        assert "scheduled use requires a separate permission for each Bot and account" in card.inner_text()
        faq = page.locator("details.faq-item").filter(has_text="Can I run it on my ChatGPT or Claude subscription?")
        faq.locator("summary").click()
        assert "scheduled or coordinator-assigned work needs your express permission" in faq.inner_text().lower()
        assert "the permission follows that bot's current provider routes and can be revoked" in faq.inner_text().lower()
        wrapped_faq = page.locator("details.faq-item").filter(
            has_text="What happens when my laptop sleeps on a schedule?"
        ).locator("summary")
        for label, width, height in (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            if label == "phone":
                layout = wrapped_faq.evaluate("""summary => {
                    const range = document.createRange();
                    range.selectNodeContents(summary);
                    const textRects = [...range.getClientRects()].map(rect => ({right: rect.right, top: rect.top, bottom: rect.bottom}));
                    const bounds = summary.getBoundingClientRect();
                    return {textRects, right: bounds.right, height: bounds.height};
                }""")
                assert len(layout["textRects"]) >= 2, layout
                assert all(rect["right"] <= layout["right"] - 40 for rect in layout["textRects"]), layout
            page.get_by_role("heading", name="Plans & keys").scroll_into_view_if_needed()
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            page.screenshot(path=str(out / f"marketing-consent-plan-{label}.png"), animations="disabled")
            faq.scroll_into_view_if_needed()
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            page.screenshot(path=str(out / f"marketing-consent-faq-{label}.png"), animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})
        wrapped_faq.evaluate("element => element.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'})")
        page.screenshot(path=str(out / "marketing-faq-wrapped-phone.png"), animations="disabled")
        faq.locator("summary").click()
        coding_faq = page.locator("details.faq-item").filter(has_text="Can I hand coding work to OpenCode?")
        coding_faq.locator("summary").click()
        coding_text = coding_faq.inner_text().lower()
        assert "completed hutch answer into a reviewed coding task" in coding_text
        assert "hutch code login" in coding_text
        assert "hutch's private profile" in coding_text
        assert "separate worktree from the selected git commit" in coding_text
        assert "outside hutch's budget and sandbox" in coding_text
        for label, width, height in (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            coding_faq.scroll_into_view_if_needed()
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            page.screenshot(path=str(out / f"marketing-coding-handoff-faq-{label}.png"), animations="disabled")
        assert not errors, errors
        assert not external, external
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_website.py::test_chatgpt_background_consent_marketing_copy_at_responsive_sizes",
            "browser": browser.browser_type.name,
            "browser_version": browser.version,
            "playwright_version": package_version("playwright"),
            "viewports": {"desktop": [1440, 900], "tablet": [900, 1024], "phone": [390, 844]},
            "external_requests": external,
            "page_errors": errors,
            "source_sha256": hashlib.sha256((ROOT / "website/index.html").read_bytes()).hexdigest(),
            "styles_sha256": hashlib.sha256((ROOT / "website/styles.css").read_bytes()).hexdigest(),
            "coding_handoff_screenshots": [f"marketing-coding-handoff-faq-{name}.png"
                                            for name in ("desktop", "tablet", "phone")],
            "wrapped_faq_screenshot": "marketing-faq-wrapped-phone.png",
            "verified": ["clear per-Bot express consent disclosure", "revoke and route-change disclosure",
                         "OpenCode CLI handoff boundaries", "wrapped phone FAQ title clears disclosure arrow",
                         "responsive FAQ and copy", "no horizontal overflow"],
        }, indent=2) + "\n", encoding="utf-8")
        context.tracing.stop(path=str(out / "trace.zip"))
    finally:
        try:
            context.tracing.stop()
        except Exception:
            pass
        context.close()


def test_internal_links_resolve_and_external_links_are_public_reports(browser, site_url):
    context, page, _ = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    broken = page.evaluate("""() => [...document.querySelectorAll('a[href^="#"]')]
      .map(a => a.getAttribute('href'))
      .filter(href => href.length > 1 && !document.getElementById(decodeURIComponent(href.slice(1))))""")
    assert not broken, broken
    external = page.locator("a[href^='https://']").evaluate_all("els => els.map(a => a.href)")
    assert external == [], external
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
    out = artifact_path("assistant-first-ui/marketing/workflow")
    out.mkdir(parents=True, exist_ok=True)
    index = (SITE_DIR / "index.html").read_bytes()
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    captures = []
    schedule_captures = []
    try:
        page.goto(site_url, wait_until="networkidle")
        workflow = page.locator("#workflow")
        workflow.locator("details").evaluate_all("els => els.forEach(el => el.open = true)")
        technical = page.locator("#runs .technical-details")
        technical.locator("summary").click()
        scheduling = page.locator("#runs .card.feature").filter(has_text="Scheduling")
        assert "dedicated assistant" in workflow.inner_text().lower()
        assert "local supervisor" in page.locator("body").inner_text().lower()
        assert "one workspace-wide pause stops new scheduled admissions" in scheduling.inner_text().lower()
        assert "queued or running work continues" in scheduling.inner_text().lower()
        assert "when resumed, missed windows are coalesced or skipped" in scheduling.inner_text().lower()
        assert "teammate name" in workflow.inner_text().lower()
        assert "clear work role" in workflow.inner_text().lower()
        assert "if hutch needs your preference" in workflow.inner_text().lower()
        assert "your reply guides the conversation; it never approves an action" in workflow.inner_text().lower()
        assert "experimental (built-in coordinator only)" in workflow.inner_text().lower()
        assert "tool-free purpose rewrite from the exact source" in workflow.inner_text().lower()
        assert "each request returns one response" in workflow.inner_text().lower()
        assert "select earlier user messages if useful" in workflow.inner_text().lower()
        assert "hosted providers may retain the text" in workflow.inner_text().lower()
        assert "drafting creates no assistant or permission changes" in workflow.inner_text().lower()
        assert "normal route and fallback limits still apply" in workflow.inner_text().lower()
        assert "live quality is unverified" in workflow.inner_text().lower()
        assert "experimental coordinator handoff" in workflow.inner_text().lower()
        assert "content-free progress timeline" in workflow.inner_text().lower()
        assert "continue only from a safe checkpoint" in workflow.inner_text().lower()
        assert "no recorded action or child work" in workflow.inner_text().lower()
        assert "starts a fresh run" in workflow.inner_text().lower()
        assert "reviewed brief, constraints and committed response" in workflow.inner_text().lower()
        assert "attach only the exact specialist reply you choose" in workflow.inner_text().lower()
        assert "as untrusted text" in workflow.inner_text().lower()
        assert "up to eight current, approved coordinator facts for that task alone" in workflow.inner_text().lower()
        assert "providers may retain submitted copies" in workflow.inner_text().lower()
        assert "keep memory private by default" in workflow.inner_text().lower()
        assert "share the reviewed snapshot with that named assistant" in workflow.inner_text().lower()
        assert "either side can revoke" in workflow.inner_text().lower()
        assert "the share adds no tools, account access or workspace context" in workflow.inner_text().lower()
        assert "without describing the work again" in workflow.inner_text().lower()
        assert "editable teammate name, clear work role and stable local address" in workflow.inner_text().lower()
        assert "without an extra model request" in workflow.inner_text().lower()
        assert "suggests an editable teammate name" in workflow.inner_text().lower()
        for label, width, height in (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            workflow.get_by_role("heading", name="Turn one conversation into help you can return to.").scroll_into_view_if_needed()
            workflow.screenshot(
                path=str(out / f"site-workflow-{label}.png"), animations="disabled",
                style="body > header { display: none !important; } .skip-link { display: none !important; }")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            captures.append({"size": label, "viewport": [width, height], "overflow": overflow})
            scheduling.scroll_into_view_if_needed()
            schedule_path = out / f"site-scheduling-{label}.png"
            scheduling.screenshot(path=str(schedule_path), animations="disabled")
            schedule_captures.append({"size": label, "viewport": [width, height], "screenshot": schedule_path.name})
        assert not external, external
        assert not errors, errors
        (out / "site-validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "browser": browser.version,
            "index_sha256": hashlib.sha256(index).hexdigest(), "captures": captures,
            "schedule_card_captures": schedule_captures,
            "anonymous": True, "external_requests": len(external), "page_errors": errors,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        context.close()


def test_public_bot_setup_copy_matches_reviewed_chat_sourced_creation(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    out = artifact_path("bot-from-message/marketing")
    out.mkdir(parents=True, exist_ok=True)
    source = (SITE_DIR / "index.html").read_bytes()
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    captures = []
    try:
        page.goto(site_url, wait_until="networkidle")
        card = page.locator("#workflow .step-card").first
        card.locator("details.workflow-details > summary").click()
        text = card.inner_text().lower()
        assert "start in chat" in text
        assert "carries your words into setup" in text
        assert "without describing the work again" in text
        assert "latest request" in text
        assert "later messages, assistant replies and other chats stay excluded" in text
        assert "earlier user messages you choose become saved background" in text
        assert "assistant replies and other chats stay excluded" in text
        assert "editable teammate name, clear work role and stable local address" in text
        assert "without an extra model request" in text
        assert "workspace or source-chat model route" in text
        assert "no tools" in text and "schedule" in text
        assert "starts no run" in text
        assert "experimental (built-in coordinator only)" in page.locator("#workflow").inner_text().lower()
        page.locator("#runs .technical-details > summary").click()
        model_card = page.locator("#runs .feature").filter(has_text="Hutch supports configured OpenAI").first
        model_text = model_card.inner_text().lower()
        assert "next message" in model_text
        assert "save as bot default" in model_text
        assert "scheduled runs" in model_text
        assert "openrouter" in model_text and "searchable model catalog" in model_text
        assert "listed prices can change" in model_text
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
    out = artifact_path("assistant-first-ui/marketing/availability")
    out.mkdir(parents=True, exist_ok=True)
    source = (SITE_DIR / "index.html").read_bytes()
    styles = (SITE_DIR / "styles.css").read_bytes()
    viewports = (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844))
    try:
        page.locator("#get .availability-details > summary").click()
        assert page.locator("#get .availability").get_by_text("Public access", exact=True).count() == 1
        availability = page.locator("#get").inner_text().lower()
        assert "opencode go api-key handoff" in availability
        assert "chatgpt sign-in preview" in availability
        assert "eligibility unconfirmed" in availability
        assert "google calendar lookup" in availability
        assert "consent unverified" in availability
        assert "private gmail search" in availability
        assert "public release awaits google scope verification" in availability
        assert "outlook calendar lookup and optional guest-free event creation on one selected calendar" in availability
        assert "read-only outlook mail previews" in availability
        assert page.locator("a[href='#get']").count() >= 1
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.get_by_role("heading", name="Hutch is still a private preview.").scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"marketing-{label}.png"), animations="disabled")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
        feature_sizes = (("desktop", 1440, 900), ("tablet", 900, 1024), ("phone", 390, 844))
        for label, width, height in feature_sizes:
            page.set_viewport_size({"width": width, "height": height})
            if not page.locator("#runs .technical-details").evaluate("el => el.open"):
                page.locator("#runs .technical-details > summary").click()
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


def test_outlook_calendar_and_mail_support_row_is_truthful_and_reachable_at_all_viewports(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    out = artifact_path("outlook-calendar-write/marketing")
    out.mkdir(parents=True, exist_ok=True)
    source = (SITE_DIR / "index.html").read_bytes()
    styles = (SITE_DIR / "styles.css").read_bytes()
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    captures = []
    try:
        page.goto(site_url, wait_until="networkidle")
        page.locator("#get .availability-details > summary").click()
        row = page.locator("#get .availability tbody tr").filter(has_text="Outlook Calendar")
        assert row.count() == 1
        text = row.inner_text().lower()
        assert "experimental" in row.inner_text().lower()
        assert "consent unverified" in text
        assert "credential/captcha handoff" in text
        assert "browser field detection" in text
        assert "outlook calendar lookup and optional guest-free event creation on one selected calendar" in text
        assert "exact approval each time" in text
        assert "microsoft consent is account-wide and unverified" in text
        assert "read-only outlook mail previews" in text
        assert "consent unverified" in text
        assert "private gmail search" in text
        assert "public release awaits google scope verification" in text
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
            "test": "tests/e2e/test_website.py::test_outlook_calendar_and_mail_support_row_is_truthful_and_reachable_at_all_viewports",
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


def test_dynamic_workflow_marketing_is_truthful_and_responsive(browser, site_url):
    context, page, errors = _page(browser, reduced_motion="reduce")
    out = Path(os.environ.get("HUTCH_DYNAMIC_WORKFLOW_MARKETING_ARTIFACTS",
                              artifact_path("dynamic-workflows/marketing")))
    out.mkdir(parents=True, exist_ok=True)
    external = []
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(site_url) and not request.url.startswith("data:") else None)
    source_hashes = {
        "website/index.html": hashlib.sha256((SITE_DIR / "index.html").read_bytes()).hexdigest(),
        "website/styles.css": hashlib.sha256((SITE_DIR / "styles.css").read_bytes()).hexdigest(),
    }
    captures = []
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(site_url, wait_until="networkidle")
        preview = page.locator("#workflow .workflow-preview")
        assert preview.count() == 1
        preview_text = preview.inner_text().lower()
        workflow_copy_words = len(preview_text.split())
        assert workflow_copy_words <= 100, "the workflow explanation should stay concise"
        for phrase in ("private preview", "saved steps, started by you", "planned steps stay distinct from discovered instances",
                       "answer each pending question", "pause lets active work settle before the next step is held",
                       "resume or stop from chat",
                       "completed step is not necessarily verified", "a qualified selector for the exact model profile",
                       "neither tested local profile qualified", "auto does not create new plans",
                       "an owner can link an activated workflow to a routine", "enabling stays separate"):
            assert phrase in preview_text, phrase
        assert page.locator("#workflow .workflow-details").count() == 3

        page.locator("#get .availability-details > summary").click()
        workflow_row = page.locator("#get .availability tbody tr").filter(has_text="Workflows")
        assert workflow_row.count() == 1
        availability = workflow_row.inner_text().lower()
        for phrase in ("owner-started saved workflows", "chat route cards", "auto starts of activated saved methods",
                       "selector qualification for the exact model profile", "two local profiles tested did not qualify",
                       "auto does not create new plans", "an owner can link an activated saved method to an existing routine",
                       "pins the exact revision and checked inputs", "enabling the routine stays separate",
                       "run now starts one copy without advancing the schedule",
                       "the existing local supervisor and host must be running", "live provider execution remains unverified",
                       "experimental"):
            assert phrase in availability, phrase

        faq_expectations = {
            "How do Suggest and Auto work for workflows?": "the two local profiles tested did not qualify",
            "Can a local model design or choose a workflow?": "neither of the two qwen3 profiles tested qualified",
            "What happens if I stop a workflow or Hutch restarts?": "a pause request does not cancel active work",
            "What is the difference between a workflow and a routine?": "hutch pins the exact revision and checks its inputs",
        }
        for question, expected in faq_expectations.items():
            item = page.locator("#faq details").filter(has=page.get_by_text(question, exact=True))
            assert item.count() == 1, question
            item.locator("summary").click()
            answer = item.locator(".collapse-content")
            assert answer.is_visible()
            assert expected in answer.inner_text().lower(), question

        page.get_by_role("link", name="Workflow questions").click()
        assert page.evaluate("location.hash") == "#faq"

        viewports = (("desktop", 1440, 900), ("tablet", 768, 1024),
                     ("phone", 360, 800), ("compact-phone", 320, 800))
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#workflow").scroll_into_view_if_needed()
            preview.scroll_into_view_if_needed()
            preview.evaluate("element => window.scrollBy(0, element.getBoundingClientRect().top - 90)")
            page.wait_for_timeout(60)
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, overflow)
            box = preview.bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1, (label, box)
            copy_box = preview.locator(".workflow-preview-copy").bounding_box()
            headline = preview.locator("h3").bounding_box()
            assert copy_box and headline and headline["x"] >= copy_box["x"] - 1
            assert headline["x"] + headline["width"] <= copy_box["x"] + copy_box["width"] + 1
            assert headline["height"] <= 120, (label, headline)
            page.screenshot(path=str(out / f"workflow-{label}.png"), animations="disabled")

            workflow_row.locator(".av-v").scroll_into_view_if_needed()
            page.wait_for_timeout(40)
            row_box = workflow_row.bounding_box()
            assert row_box and row_box["x"] >= 0 and row_box["x"] + row_box["width"] <= width + 1, (label, row_box)
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            page.screenshot(path=str(out / f"availability-{label}.png"), animations="disabled")
            captures.append({"name": label, "viewport": [width, height], "workflow_preview": box,
                             "availability_row": row_box, "horizontal_overflow_px": overflow})

        # Exercise the new workflow teaser under the WCAG text-spacing override and
        # system high-contrast colors. These are separate states from the normal
        # responsive captures above so their visual evidence stays inspectable.
        page.set_viewport_size({"width": 320, "height": 800})
        page.add_style_tag(content=(
            "* { letter-spacing: .12em !important; word-spacing: .16em !important; "
            "line-height: 1.5 !important; } "
            "p { margin-bottom: 2em !important; }"
        ))
        preview.scroll_into_view_if_needed()
        preview.evaluate("element => window.scrollBy(0, element.getBoundingClientRect().top - 70)")
        spacing_box = preview.bounding_box()
        spacing_overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert spacing_box and spacing_box["x"] >= 0 and spacing_box["x"] + spacing_box["width"] <= 321
        assert spacing_overflow <= 1, spacing_overflow
        page.screenshot(path=str(out / "workflow-text-spacing-start-compact-phone.png"), animations="disabled")
        preview_link = preview.locator(".workflow-preview-link")
        preview_link.focus()
        page.keyboard.press("Tab")
        page.keyboard.press("Shift+Tab")
        assert preview_link.evaluate("el => document.activeElement === el")
        assert preview_link.evaluate("el => getComputedStyle(el).outlineStyle !== 'none'")
        link_box = preview_link.bounding_box()
        assert link_box and link_box["height"] >= 44 and 0 <= link_box["y"] < 800
        page.screenshot(path=str(out / "workflow-text-spacing-focus-compact-phone.png"), animations="disabled")

        page.emulate_media(forced_colors="active")
        preview.scroll_into_view_if_needed()
        preview.evaluate("element => window.scrollBy(0, element.getBoundingClientRect().top - 70)")
        page.screenshot(path=str(out / "workflow-forced-colors-start-compact-phone.png"), animations="disabled")
        preview_link.focus()
        page.keyboard.press("Tab")
        page.keyboard.press("Shift+Tab")
        forced_outline = preview_link.evaluate("el => getComputedStyle(el).outlineStyle")
        assert forced_outline != "none", forced_outline
        forced_link_box = preview_link.bounding_box()
        assert forced_link_box and forced_link_box["height"] >= 44 and 0 <= forced_link_box["y"] < 800
        page.screenshot(path=str(out / "workflow-forced-colors-focus-compact-phone.png"), animations="disabled")
        captures.append({"name": "compact-phone-text-spacing", "viewport": [320, 800],
                         "workflow_preview": spacing_box, "workflow_link": link_box,
                         "horizontal_overflow_px": spacing_overflow})
        captures.append({"name": "compact-phone-forced-colors", "viewport": [320, 800],
                         "workflow_link": forced_link_box, "outline_style": forced_outline,
                         "horizontal_overflow_px": page.evaluate("document.documentElement.scrollWidth - innerWidth")})

        assert external == [], external
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        hashes = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                  for file in out.iterdir() if file.suffix in {".png", ".zip"}}
        (out / "results.json").write_text(json.dumps({
            "test": "tests/e2e/test_website.py::test_dynamic_workflow_marketing_is_truthful_and_responsive",
            "command": "TMPDIR=/var/tmp .venv/bin/pytest -q tests/e2e/test_website.py::test_local_asset_urls_use_current_content_hashes tests/e2e/test_website.py::test_dynamic_workflow_marketing_is_truthful_and_responsive --basetemp=/var/tmp/hutch-marketing-a11y-review",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": browser.browser_type.name, "browser_version": browser.version,
            "playwright_version": package_version("playwright"), "reduced_motion": "reduce",
            "accessibility_states": {"text_spacing": "WCAG 1.4.12 user override injected",
                                     "forced_colors": "active", "keyboard_focus": "workflow FAQ link"},
            "workflow_preview_word_count": workflow_copy_words,
            "provider_calls": 0, "external_requests": external, "page_errors": errors,
            "viewports": captures, "source_sha256": source_hashes,
            "visual_artifact_sha256": hashes,
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if context.tracing:
            try:
                context.tracing.stop()
            except Exception:
                pass
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
    hidden_disclosure_targets = page.locator("details:not([open]) .reveal")
    assert hidden_disclosure_targets.count() == 0, "closed disclosures must not receive hidden reveal styles"
    hidden = page.locator(".reveal").evaluate_all("els => els.filter(e => getComputedStyle(e).opacity === '0').length")
    assert hidden == 0, f"{hidden} reveal targets remain hidden"
    context.close()


def test_mobile_drawer_focus_and_ctas(browser, site_url):
    context, page, errors = _page(browser, width=390, height=844)
    page.goto(site_url, wait_until="networkidle")
    skip_link = page.locator(".skip-link")
    assert skip_link.evaluate("el => getComputedStyle(el).transitionProperty") == "transform"
    hidden_skip_box = skip_link.bounding_box()
    assert hidden_skip_box and hidden_skip_box["y"] + hidden_skip_box["height"] < 0, hidden_skip_box
    skip_link.focus()
    wait_for_page(page, "document.activeElement?.matches('.skip-link') && document.querySelector('.skip-link').getBoundingClientRect().top >= 0")
    visible_skip_box = skip_link.bounding_box()
    assert visible_skip_box and 0 <= visible_skip_box["y"] <= 16, visible_skip_box
    page.keyboard.press("Enter")
    assert page.evaluate("location.hash") == "#main"
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


def test_adaptive_response_style_marketing_is_labeled_and_fits(browser, site_url):
    context, page, errors = _page(browser, width=1440, height=900, reduced_motion="reduce")
    requests: list[tuple[str, str]] = []
    page.on("request", lambda request: requests.append((request.method, request.url)))
    page.goto(site_url, wait_until="networkidle")

    block = page.locator("#response-style")
    assert block.get_by_role("heading", name="Choose the voice. Set the depth separately.").count() == 1
    for option in (
        "Direct · Warm · Dry Wit",
        "Auto · Brief · Standard · Detailed",
        "Off · Subtle · Playful",
    ):
        assert option in block.inner_text()
    assert "Humor defaults to off" in block.inner_text()
    assert "fixed written examples" in block.inner_text().lower()
    assert block.locator(".response-style-voice-examples .response-style-example").count() == 3
    assert block.locator(".response-style-depth-grid .response-style-example").count() == 2
    assert "Changing a setting makes no model request" in block.inner_text()
    image = block.locator("picture img")
    assert image.get_attribute("alt")
    assert "fictional assistant and no model request" in block.inner_text()

    faq = page.locator("#faq .faq-item").filter(has_text="Can I choose how Hutch answers?")
    faq.locator("summary").focus()
    page.keyboard.press("Enter")
    assert faq.evaluate("element => element.open")
    assert "voice (direct, warm, or dry wit)" in faq.inner_text().lower()
    assert "live answer quality remain unverified" in faq.inner_text().lower()
    image_input = page.locator("#faq .faq-item").filter(has_text="Can Hutch look at an image I attach?")
    image_input.locator("summary").focus()
    page.keyboard.press("Enter")
    assert image_input.evaluate("element => element.open")
    assert "text-only today" in image_input.inner_text().lower()
    assert "does not enable image input" in image_input.inner_text().lower()

    out = artifact_path("persona-marketing-2026-10-11")
    out.mkdir(parents=True, exist_ok=True)
    # This is a tall, section-only capture. Keep the sticky site header from being
    # composited repeatedly over the captured content by the browser's full-element shot.
    page.add_style_tag(content="body > header, .skip-link { visibility: hidden !important; }")
    viewports = ((1440, 1000, "desktop"), (768, 1024, "tablet"),
                 (720, 480, "200-percent-effective"), (360, 844, "phone"),
                 (320, 800, "compact-phone"))
    measurements = []
    for width, height, label in viewports:
        page.set_viewport_size({"width": width, "height": height})
        block.scroll_into_view_if_needed()
        wait_for_page(page, """() => {
          const img = document.querySelector('#response-style picture img');
          return img && img.complete && img.naturalWidth > 0;
        }""")
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1, f"{label} has {overflow}px horizontal overflow"
        assert not errors, errors
        assert all(method == "GET" and url.startswith(site_url) for method, url in requests), requests
        block.screenshot(path=str(out / f"response-style-{label}.png"), animations="disabled")
        measurements.append({"label": label, "viewport": [width, height], "overflow_px": overflow})

    source_files = (
        "website/index.html", "website/styles.css", "website/app.css", "website/site.js",
        "website/assets/captures/response-style-desktop.webp",
        "website/assets/captures/response-style-phone.webp",
    )
    manifest = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "test": "tests/e2e/test_website.py::test_adaptive_response_style_marketing_is_labeled_and_fits",
        "browser": browser.browser_type.name,
        "browser_version": browser.version,
        "scenario": "Anonymous static page; written examples and real local settings screenshot; no provider or inference requests",
        "model_calls": 0,
        "sticky_header_and_skip_link_suppressed_for_component_captures": True,
        "requests": requests,
        "errors": errors,
        "viewports": measurements,
        "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                           for path in source_files},
    }
    (out / "validation.json").write_text(json.dumps(manifest, indent=2) + "\n")
    context.close()


def test_term_tabs_keyboard_operable(browser, site_url):
    context, page, errors = _page(browser)
    page.goto(site_url, wait_until="networkidle")
    page.locator("#control .control-details > summary").click()
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
    out = artifact_path("no-mock-setup/site")
    out.mkdir(parents=True, exist_ok=True)
    try:
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto(site_url, wait_until="networkidle")
        image = page.locator("img[src^='assets/captures/setup-desktop.webp']")
        image.evaluate("img => { img.loading='eager'; return img.decode(); }")
        figure = image.locator("xpath=ancestor::figure")
        assert image.evaluate("img => img.naturalWidth") == (390 if width <= 640 else 1440)
        assert "temporary account was empty" in figure.inner_text()
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
