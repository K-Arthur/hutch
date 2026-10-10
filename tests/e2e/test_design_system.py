"""Rendered checks that the app, server pages, and public site share Hutch's core UI tokens."""

from __future__ import annotations

import hashlib
import http.server
import json
import platform
import socketserver
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import Bot, Run, RunStatus  # noqa: E402
from hutch.server.app import create_app  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "website"
VISUAL_SOURCE_FILES = (
    "src/hutch/server/static/app.js",
    "src/hutch/server/static/index.html",
    "src/hutch/server/static/style.css",
    "src/hutch/server/static/brands/openai-white-monoblossom.svg",
    "website/index.html",
    "website/site.js",
    "website/styles.css",
    "tests/e2e/test_design_system.py",
)


def _visual_source_hashes() -> dict[str, str]:
    """Bind saved browser evidence to the exact app, site, and test sources."""
    return {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in VISUAL_SOURCE_FILES
    }


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


@pytest.fixture()
def app_server(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_MAX_CONCURRENT", "2")
    app = create_app()
    bot = app.state.store.create_bot(Bot(
        name="design-system-review", display_name="Design Partner", model="mock/demo", tools=[]
    ))
    assert bot.name == "design-system-review"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "local Hutch preview did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", app
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "local Hutch preview did not stop"


@pytest.fixture()
def site_server():
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=str(SITE), **kwargs
    )
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            yield f"http://127.0.0.1:{port}/"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive(), "local marketing preview did not stop"


def test_studio_template_gallery_survives_background_refresh(browser, app_server):
    """Polling an unchanged conversation must preserve asynchronously loaded welcome content."""
    app_url, _ = app_server
    context = browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    try:
        page.goto(f"{app_url}/#/chat/design-system-review", wait_until="domcontentloaded")
        gallery = page.locator("#tpl-grid .tpl-card")
        gallery.first.wait_for(state="visible", timeout=15_000)
        page.evaluate("window.__galleryCard = document.querySelector('#tpl-grid .tpl-card')")
        page.wait_for_timeout(4_400)
        assert page.evaluate("window.__galleryCard?.isConnected") is True
        assert gallery.count() == 6
    finally:
        context.close()


def _measure_tokens(page, surface: str) -> dict:
    return page.evaluate("""surface => {
      const root = getComputedStyle(document.documentElement);
      const body = getComputedStyle(document.body);
      const boxClass = surface === 'studio' ? 'card' : surface === 'connections' ? 'panel' : 'step-card';
      const buttonClass = surface === 'marketing' ? 'btn btn-primary' : 'btn primary';
      const box = document.createElement('div');
      box.className = boxClass;
      const button = document.createElement('button');
      button.className = buttonClass;
      button.textContent = 'Token check';
      document.body.append(box, button);
      const boxStyle = getComputedStyle(box);
      const buttonStyle = getComputedStyle(button);
      const result = {
        shared: Object.fromEntries([
          '--color-semantic-bg', '--color-semantic-surface', '--color-semantic-panel',
          '--color-semantic-brand', '--color-semantic-on-brand', '--color-semantic-focus-ring',
          '--color-semantic-border', '--color-semantic-border-strong', '--color-semantic-border-emphasis',
          '--font-body', '--radius-control', '--radius-panel', '--radius-chip'
        ].map(name => [name, root.getPropertyValue(name).trim()])),
        bodyFont: body.fontFamily,
        bodyFontSize: body.fontSize,
        headingFont: getComputedStyle(document.querySelector('h1, .hero-title, .section-heading') || document.body).fontFamily,
        displayFontReady: document.fonts.check('700 32px Archivo'),
        typography: {
          tokens: Object.fromEntries([
            '--font-ui', '--font-display', '--mono', '--type-display-size', '--type-page-size',
            '--type-section-size', '--type-body-size', '--type-reading-size', '--type-label-size',
            '--type-caption-size', '--type-mono-size', '--leading-display', '--leading-heading', '--leading-body', '--leading-reading',
            '--icon-sm', '--icon-md', '--icon-lg', '--icon-stroke'
          ].map(name => [name, root.getPropertyValue(name).trim()])),
          roles: Object.fromEntries(['display', 'page-title', 'section-title', 'reading', 'label', 'caption', 'mono'].map(role => {
            const sample = document.createElement('span');
            sample.className = `type-${role}`;
            sample.textContent = 'Readable sample';
            document.body.append(sample);
            const style = getComputedStyle(sample);
            const measured = {family: style.fontFamily, size: style.fontSize, lineHeight: style.lineHeight, weight: style.fontWeight};
            sample.remove();
            return [role, measured];
          }))
        },
        button: {background: buttonStyle.backgroundColor, color: buttonStyle.color,
          radius: buttonStyle.borderRadius},
        panel: {background: boxStyle.backgroundColor, radius: boxStyle.borderRadius,
          border: boxStyle.borderColor},
      };
      box.remove(); button.remove();
      return result;
    }""", surface)


def _measure_operator_shell(page) -> dict:
    """The primary work views must share the same workspace navigation shell."""
    return page.evaluate("""() => ({
      workspace: !!document.querySelector('.app-shell #workspace[aria-label="Workspace"]'),
      brand: document.querySelector('#workspace .brand-name')?.textContent.trim() || '',
      studioLink: document.querySelector('#workspace .ws-nav a[href="#/chat"]')?.textContent.trim() || '',
      connectionsLink: document.querySelector('#workspace a[href="#/connections"]')?.textContent.trim() || '',
      context: !!document.querySelector('.app-top #app-top-context'),
      view: !!document.querySelector('.app-shell #view')
    })""")


def test_shared_design_tokens_render_consistently_across_all_surfaces(browser, app_server, site_server):
    """Capture current Studio, Connections, and marketing renders at desktop/tablet/phone sizes."""
    app_url, _app = app_server
    out = ROOT / "docs/realignment/artifacts/design-system"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    sizes = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844)}
    evidence = []
    try:
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})

            page.goto(f"{app_url}/#/chat/design-system-review")
            page.locator("#conversation-switcher").wait_for()
            page.evaluate("document.fonts.ready")
            studio_shell = _measure_operator_shell(page)
            assert studio_shell == {
                "workspace": True, "brand": "hutch", "studioLink": "Chats",
                "connectionsLink": "Apps & AI", "context": True, "view": True,
            }, (label, studio_shell)
            studio = _measure_tokens(page, "studio")
            studio["operatorShell"] = studio_shell
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, (label, "Studio")
            page.screenshot(path=str(out / f"studio-{label}.png"), animations="disabled")
            scale_result = page.evaluate("""() => {
              const root = document.documentElement;
              const original = root.style.fontSize;
              root.style.fontSize = '200%';
              const body = getComputedStyle(document.body).fontSize;
              const title = document.createElement('span');
              title.className = 'type-page-title';
              document.body.append(title);
              const pageTitle = getComputedStyle(title).fontSize;
              title.remove();
              root.style.fontSize = original;
              return {body, pageTitle};
            }""")
            assert scale_result == {"body": "32px", "pageTitle": "48px"}, (label, scale_result)
            assert studio["bodyFontSize"] == "16px", (label, studio["bodyFontSize"])

            # The user-facing Connections surface lives in the Studio shell.
            # `/connections` is a compatibility HTML page with a separate legacy
            # layout; using it here would validate the wrong product surface.
            page.goto(f"{app_url}/#/connections")
            page.get_by_role("heading", name="Apps & AI").wait_for()
            page.locator(".service-tile").first.wait_for()
            connections_shell = _measure_operator_shell(page)
            assert connections_shell == studio_shell, (label, studio_shell, connections_shell)
            connections = _measure_tokens(page, "connections")
            connections["operatorShell"] = connections_shell
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, (label, "Connections")
            page.screenshot(path=str(out / f"connections-{label}.png"), animations="disabled")

            page.goto(site_server)
            page.locator(".hero-title").wait_for()
            page.evaluate("document.fonts.ready")
            marketing_provider_marks = page.locator(".benefit-art-apps img[data-provider-mark]")
            assert marketing_provider_marks.count() == 0, (label, "do not ship unlicensed provider artwork")
            category_marks = page.locator(".benefit-art-apps .app-mark svg")
            assert category_marks.evaluate_all(
                "els => els.map(el => [el.closest('[data-service-category]').dataset.serviceCategory, el.dataset.icon])"
            ) == [["calendar", "calendar"], ["gmail", "mail"], ["outlook", "inbox"]]
            assert category_marks.evaluate_all(
                "els => els.every(el => el.getAttribute('stroke') === 'currentColor' && !el.querySelector('text'))"
            ), (label, "marketing service marks should use Hutch's local category icon family")
            assert page.locator(".benefit-copy .example-prompt").filter(
                has_text="Calendar · Gmail · Outlook · your AI"
            ).is_visible()
            marketing = _measure_tokens(page, "marketing")
            marketing["displayFont"] = page.locator(".hero-title").evaluate(
                "element => getComputedStyle(element).fontFamily"
            )
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, (label, "Marketing")
            page.screenshot(path=str(out / f"marketing-{label}-viewport.png"), animations="disabled")
            page.screenshot(path=str(out / f"marketing-{label}.png"), full_page=True, animations="disabled")
            provider_art = page.locator(".benefit-art-apps")
            provider_art.scroll_into_view_if_needed()
            provider_art.locator("xpath=..").screenshot(
                path=str(out / f"marketing-provider-card-{label}.png"), animations="disabled"
            )
            page.evaluate("window.scrollTo(0, 0)")

            views = {"studio": studio, "connections": connections, "marketing": marketing}
            for name, view in views.items():
                assert view["shared"]["--color-semantic-bg"] == "#05070a", (label, name, view)
                assert view["shared"]["--color-semantic-surface"] == "#080c12", (label, name, view)
                assert view["shared"]["--color-semantic-brand"] == "#34d399", (label, name, view)
                assert view["shared"]["--color-semantic-focus-ring"] == "#60a5fa", (label, name, view)
                assert view["shared"]["--color-semantic-border-emphasis"] in {
                    "#ffffff38", "rgba(255,255,255,0.22)"
                }, (label, name, view)
                assert view["shared"]["--radius-control"] == "8px", (label, name, view)
                assert view["shared"]["--radius-panel"] == "12px", (label, name, view)
                assert "system-ui" in view["bodyFont"], (label, name, view["bodyFont"])
                assert "Archivo" in view["headingFont"], (label, name, view["headingFont"])
                assert view["displayFontReady"], (label, name, "local Archivo font did not load")
                assert view["button"]["background"] == "rgb(52, 211, 153)", (label, name, view["button"])
                assert view["button"]["color"] == "rgb(5, 46, 33)", (label, name, view["button"])
                assert view["button"]["radius"] == "8px", (label, name, view["button"])
                assert view["panel"]["background"] == "rgb(8, 12, 18)", (label, name, view["panel"])
                if name != "marketing":
                    type_tokens = view["typography"]["tokens"]
                    assert type_tokens["--type-body-size"] == "1rem", (label, name, type_tokens)
                    assert type_tokens["--type-reading-size"] == "1.0625rem", (label, name, type_tokens)
                    assert type_tokens["--type-label-size"] == "0.875rem", (label, name, type_tokens)
                    assert type_tokens["--type-caption-size"] == "0.75rem", (label, name, type_tokens)
                    assert type_tokens["--type-mono-size"] == "0.8125rem", (label, name, type_tokens)
                    assert "Archivo" in type_tokens["--font-display"], (label, name, type_tokens)
                    assert [type_tokens["--icon-sm"], type_tokens["--icon-md"], type_tokens["--icon-lg"]] == ["16px", "20px", "24px"]
                    assert type_tokens["--icon-stroke"] == "1.75px", (label, name, type_tokens)
                    roles = view["typography"]["roles"]
                    assert roles["display"]["size"] in {"28px", "36px"}, (label, name, roles)
                    assert roles["page-title"]["size"] == "24px", (label, name, roles)
                    assert roles["section-title"]["size"] == "18px", (label, name, roles)
                    assert roles["reading"]["size"] == "17px", (label, name, roles)
                    assert roles["label"]["size"] == "14px", (label, name, roles)
                    assert roles["caption"]["size"] == "12px", (label, name, roles)
                    assert roles["mono"]["size"] == "13px", (label, name, roles["mono"])
                    assert "monospace" in roles["mono"]["family"], (label, name, roles["mono"])
                assert view["panel"]["radius"] == "12px", (label, name, view["panel"])
            assert "Archivo" in marketing["displayFont"], marketing["displayFont"]
            assert max(page.evaluate("document.documentElement.scrollWidth - innerWidth"), 0) <= 1, label
            evidence.append({"size": label, "viewport": [width, height], "views": views})

        page.set_viewport_size({"width": 320, "height": 740})
        for url in (f"{app_url}/#/chat/design-system-review", f"{app_url}/#/connections", site_server):
            page.goto(url)
            page.locator("body").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, (url, "320px reflow")
        assert not external_requests, external_requests
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_design_system.py",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "playwright": package_version("playwright"),
            "viewports": [*evidence, {"size": "reflow", "viewport": [320, 740]}],
            "external_requests": external_requests,
            "provider_calls": 0,
            "states": ["empty selected Studio conversation", "Connections in the shared Studio shell", "marketing landing page"],
            "source_sha256": _visual_source_hashes(),
            "visual_review_required": "Open and inspect all twelve desktop/tablet/phone screenshots before accepting this result.",
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace-failed.zip"))
        except Exception:
            pass
        context.close()


def test_assistant_first_run_and_app_catalog_use_familiar_visual_language(browser, app_server):
    """Capture a real request-first setup and the non-technical app catalog at common sizes."""
    app_url, app = app_server
    assert app.state.store.delete_bot("design-system-review")
    out = ROOT / "docs/realignment/artifacts/app-catalog-source-aligned-2026-10-10"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    app_scroll = page.locator("main#view > .page-scroll")
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = (("desktop", 1440, 960), ("short-desktop", 1280, 720),
                 ("tablet", 900, 1024), ("phone", 390, 844), ("compact-phone", 320, 740))
    evidence = []
    try:
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{app_url}/#/chat")
            page.get_by_role("heading", name="What would you like help with?").wait_for()
            app_scroll.evaluate("el => { el.scrollTop = 0; }")
            assert app_scroll.evaluate("el => el.scrollTop") == 0
            request = page.get_by_label("Your first request")
            assert request.is_visible()
            setup_button = page.get_by_role("button", name="Set up my assistant")
            assert setup_button.is_visible()
            if label in {"phone", "short-desktop"}:
                button_box = setup_button.bounding_box()
                assert button_box and 0 <= button_box["y"] and button_box["y"] + button_box["height"] <= height, button_box
            welcome_marks = page.locator(".welcome-app-mark .service-mark")
            assert welcome_marks.locator("svg").evaluate_all(
                "els => els.map(el => el.dataset.icon)"
            ) == ["calendar", "mail"]
            assert welcome_marks.evaluate_all(
                "els => els.map(el => el.dataset.serviceCategory)"
            ) == ["calendar", "gmail", "chatgpt"]
            assert welcome_marks.locator("img[src='/static/brands/openai-white-monoblossom.svg']").count() == 1
            starter_buttons = page.locator("[data-first-run-example]")
            assert starter_buttons.count() == 3
            starter_requests = (
                ("plan", "Help me plan my week and keep track of the follow-ups."),
                ("email", "Help me find the emails I need to answer and prepare drafts for me to review."),
                ("project", "Help me organize a project and keep track of the next steps."),
            )
            for example, expected in starter_requests:
                page.locator(f"[data-first-run-example='{example}']").click()
                assert request.input_value() == expected, example
                assert page.evaluate("document.activeElement.id === 'first-run-request'")
                if example == "plan" and label in {"desktop", "phone"}:
                    page.screenshot(path=str(out / f"welcome-example-{label}.png"), full_page=True, animations="disabled")
                request.fill("")
            page.evaluate("document.activeElement.blur(); window.scrollTo(0, 0)")
            app_scroll.evaluate("el => { el.scrollTop = 0; }")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, "first run", overflow)
            page.screenshot(path=str(out / f"welcome-{label}.png"), full_page=True, animations="disabled")
            if label == "phone":
                request.focus()
                request.press("Tab")
                assert page.evaluate("document.activeElement.dataset.firstRunExample === 'plan'")
                page.keyboard.press("Tab")
                page.keyboard.press("Tab")
                page.keyboard.press("Tab")
                assert page.evaluate("document.activeElement.type === 'submit'")
            evidence.append({"surface": "first-run", "viewport": [width, height], "overflow": overflow})

        request_text = "Help me plan my week and keep track of the follow-ups."
        page.set_viewport_size({"width": 1440, "height": 960})
        page.goto(f"{app_url}/#/chat")
        page.get_by_label("Your first request").fill(request_text)
        page.get_by_role("button", name="Set up my assistant").click()
        page.get_by_role("heading", name="Create from this request").wait_for()
        purpose = page.locator("#setup-purpose")
        purpose.wait_for()
        assert purpose.input_value() == request_text, "setup must carry the original request forward"
        assert page.get_by_label("Your starting request").is_visible()
        assert page.get_by_text("We carried this over from your first message. You can edit it, but you do not need to repeat it.", exact=True).is_visible()
        suggested_name = page.locator("#setup-display_name").input_value().strip()
        assert suggested_name and len(suggested_name) <= 80
        page.screenshot(path=str(out / "setup-from-request-desktop.png"), full_page=True, animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(out / "setup-from-request-phone.png"), full_page=True, animations="disabled")
        page.get_by_role("button", name="Cancel").click()

        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{app_url}/#/connections")
            page.get_by_role("heading", name="Apps & AI").wait_for()
            app_scroll.evaluate("el => { el.scrollTop = 0; }")
            assert app_scroll.evaluate("el => el.scrollTop") == 0
            assert page.get_by_role("heading", name="Your apps").is_visible()
            assert page.get_by_role("heading", name="How Hutch replies").is_visible()
            cards = page.locator(".service-tile")
            assert cards.count() == 5
            assert page.locator(".service-tile .service-mark img[src='/static/brands/openai-white-monoblossom.svg']").count() == 1
            assert page.locator(".service-tile .service-mark svg").count() == 4
            service_icons = page.locator(".service-tile .service-mark svg")
            assert service_icons.evaluate_all("els => els.map(el => el.dataset.icon)") == [
                "calendar", "mail", "inbox", "cloud"
            ]
            assert service_icons.evaluate_all("els => els.every(el => !el.querySelector('text') && el.getAttribute('stroke') === 'currentColor')")
            assert page.locator(".service-tile .service-mark").evaluate_all(
                "els => els.map(el => el.dataset.serviceCategory)"
            ) == ["calendar", "gmail", "outlook", "chatgpt", "hosted"]
            assert not page.locator("#connection-management").evaluate("el => el.open")
            assert not page.get_by_role("button", name="Add a custom service").is_visible()
            restricted_scope = page.get_by_text("gmail.readonly", exact=True).all()
            assert not any(item.is_visible() for item in restricted_scope), label
            tile_labels = cards.locator("h3").all_text_contents()
            assert tile_labels == ["Google Calendar", "Gmail", "Microsoft Outlook", "ChatGPT", "Other reply services"]
            icon_widths = page.locator(".service-mark").evaluate_all("els => els.map(el => Math.round(el.getBoundingClientRect().width))")
            expected_mark_width = 40 if width <= 640 else 48
            assert icon_widths == [expected_mark_width] * 5, (label, icon_widths)
            if width <= 640:
                card_heights = cards.evaluate_all("els => els.map(el => Math.round(el.getBoundingClientRect().height))")
                action_heights = cards.locator(".service-tile-action").evaluate_all(
                    "els => els.map(el => Math.round(el.getBoundingClientRect().height))"
                )
                assert max(card_heights) <= 190, (label, card_heights)
                assert min(action_heights) >= 44, (label, action_heights)
            assert page.locator(".service-mark").evaluate_all("els => els.every(el => getComputedStyle(el).color !== 'rgb(240, 244, 249)')")
            assert cards.locator(".service-tile-top").evaluate_all("rows => rows.every(row => row.querySelector('h3') && row.querySelector('.service-mark') && row.querySelector('.service-state'))")
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, "Apps & AI", overflow)
            page.screenshot(path=str(out / f"apps-ai-{label}.png"), full_page=True, animations="disabled")
            evidence.append({"surface": "apps-ai", "viewport": [width, height], "overflow": overflow})

        page.set_viewport_size({"width": 1440, "height": 960})
        page.goto(f"{app_url}/#/connections")
        app_scroll.evaluate("el => { el.scrollTop = 0; }")
        page.locator(".service-tile").filter(has_text="Google Calendar").get_by_role("button", name="Check setup").click()
        assert page.locator("#connection-management").evaluate("el => el.open")
        assert page.locator("#connection-google-calendar").evaluate("el => document.activeElement === el")
        page.locator("#connection-google-calendar").scroll_into_view_if_needed()
        page.screenshot(path=str(out / "google-calendar-access-desktop.png"), animations="disabled")
        page.goto(f"{app_url}/#/connections")
        page.locator(".service-tile").filter(has_text="Other reply services").get_by_role("button", name="See options").click()
        assert page.locator("#connection-management").evaluate("el => el.open")
        assert page.get_by_role("heading", name="Add a custom service").is_visible()
        page.locator("#modal-close").click()
        assert not external_requests, external_requests
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_design_system.py::test_assistant_first_run_and_app_catalog_use_familiar_visual_language",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_design_system.py::test_assistant_first_run_and_app_catalog_use_familiar_visual_language",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "playwright": package_version("playwright"),
            "viewports": evidence,
            "states": ["empty first run", "request carried into assistant setup", "service catalog", "Google Calendar access expanded"],
            "external_requests": external_requests,
            "provider_calls": 0,
            "reduced_motion": "reduce",
            "source_sha256": _visual_source_hashes(),
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace-failed.zip"))
        except Exception:
            pass
        context.close()


def test_assistant_settings_keep_everyday_edits_up_front(browser, app_server):
    """A one-assistant setup stays approachable while detailed controls remain available."""
    app_url, _app = app_server
    out = ROOT / "docs/realignment/artifacts/assistant-settings-everyday"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    viewports = (("desktop", 1440, 960), ("tablet", 900, 1024), ("phone", 390, 844))
    evidence = []
    try:
        for label, width, height in viewports:
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{app_url}/#/bot/design-system-review")
            page.get_by_role("heading", name="Design Partner settings").wait_for()
            assert page.get_by_role("heading", name="About this assistant").is_visible()
            assert page.get_by_label("Assistant name").is_visible()
            assert page.get_by_label("What it helps with").is_visible()
            assert page.locator("#btn-set-workspace-coordinator").count() == 0
            assert not page.locator("#assistant-more-settings").evaluate("el => el.open")
            assert not page.locator("#form-model").is_visible()
            assert not page.locator("#form-instructions").is_visible()
            summary = page.locator("#assistant-more-settings > summary")
            assert "Customize how it works" in summary.inner_text()
            assert "Choose its AI, apps, schedule, safety, and saved notes" in summary.inner_text()
            assert summary.get_by_text("More settings", exact=True).is_visible()
            assert not summary.get_by_text("Hide settings", exact=True).is_visible()
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, "collapsed settings", overflow)
            page.screenshot(path=str(out / f"settings-simple-{label}.png"), full_page=True, animations="disabled")

            summary.focus()
            page.keyboard.press("Space")
            assert page.locator("#assistant-more-settings").evaluate("el => el.open")
            assert summary.get_by_text("Hide settings", exact=True).is_visible()
            assert not summary.get_by_text("More settings", exact=True).is_visible()
            assert page.locator("#form-instructions").is_visible()
            assert page.get_by_label("Standing directions").is_visible()
            assert page.locator("#form-model").is_visible()
            assert page.locator("#form-tools").is_visible()
            assert page.locator(".settings-panel-icon svg").count() >= 8
            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow <= 1, (label, "custom settings", overflow)
            if label in {"desktop", "phone"}:
                page.screenshot(path=str(out / f"settings-customize-{label}.png"), full_page=True, animations="disabled")
            summary.focus()
            page.keyboard.press("Space")
            assert not page.locator("#assistant-more-settings").evaluate("el => el.open")
            page.evaluate("document.activeElement?.blur()")
            evidence.append({"viewport": [width, height], "overflow": overflow,
                             "advanced_controls": "keyboard disclosure works"})

        assert not external_requests, external_requests
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_design_system.py::test_assistant_settings_keep_everyday_edits_up_front",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_design_system.py::test_assistant_settings_keep_everyday_edits_up_front",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "playwright": package_version("playwright"),
            "viewports": evidence,
            "states": ["single assistant", "basic details visible", "advanced settings collapsed", "keyboard-expanded controls"],
            "external_requests": external_requests,
            "provider_calls": 0,
            "source_sha256": _visual_source_hashes(),
            "visual_review_required": "Inspect each screenshot independently before accepting this result.",
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace-failed.zip"))
        except Exception:
            pass
        context.close()


def test_flat_mascot_eyes_stay_inside_every_silhouette(browser, app_server):
    """Each flat mascot has a simple shape-fitted pair of dark oval eyes."""
    app_url, app = app_server
    names = [f"mascot-{index}" for index in range(8)]
    for name in names:
        app.state.store.create_bot(Bot(name=name, display_name=name, model="mock/demo", tools=[]))

    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    context.add_init_script(f"""const names = {json.dumps(names)};
      localStorage.setItem("hutch:sigils", JSON.stringify(
        Object.fromEntries(names.map((name, index) => [name, [index, index]]))));""")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    out = ROOT / "docs/realignment/artifacts/mascot-eye-review-2026-10-10"
    out.mkdir(parents=True, exist_ok=True)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        page.goto(f"{app_url}/#/chat/design-system-review")
        page.locator(".ctx-id h1").wait_for()
        page.locator("#roster-list [data-switch-bot='mascot-7'] .avatar svg").wait_for()
        page.screenshot(path=str(out / "desktop.png"), animations="disabled")
        identity = page.locator("#roster-list [data-switch-bot^='mascot-'] .avatar svg").evaluate_all("""svgs => svgs.map(svg => {
          const body = svg.querySelector(':scope > path');
          const shape = new Path2D(body.getAttribute('d'));
          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');
          const points = element => {
            const length = element.getTotalLength();
            const transform = element.transform.baseVal.consolidate()?.matrix;
            return Array.from({length:48}, (_, index) => {
              const point = element.getPointAtLength(length * index / 48);
              const local = new DOMPoint(point.x, point.y);
              return transform ? local.matrixTransform(transform) : local;
            });
          };
          const eyes = [...svg.querySelectorAll('[data-sigil-eye]')];
          const glints = [...svg.querySelectorAll('[data-sigil-glint]')];
          const contained = eyes.map(eye => {
            const eyePoints = points(eye);
            return {
              inHead: eyePoints.every(point => ctx.isPointInPath(shape, point.x, point.y)),
            };
          });
          return {head: body.getAttribute('d'), color: body.getAttribute('fill'),
                  hasMask: !!svg.querySelector('[data-sigil-mask]'),
                      eyes: eyes.map(eye => ({name:eye.dataset.sigilEye, tag: eye.tagName.toLowerCase(), rx: Number(eye.dataset.rx),
                        ry: Number(eye.dataset.ry), cx: Number(eye.dataset.cx), cy: Number(eye.dataset.cy),
                        width: eye.getBBox().width, height: eye.getBBox().height,
                        angle:Number(eye.dataset.angle),
                    transform: eye.getAttribute('transform'),
                    fill: eye.getAttribute('fill') || eye.closest('g')?.getAttribute('fill'),
                    stroke: eye.getAttribute('stroke'), strokeWidth: Number(eye.getAttribute('stroke-width')),
                    contrastInk: eye.dataset.contrastInk})),
          outlines: [...svg.querySelectorAll('[data-sigil-outline]')].map(outline => ({
            stroke:outline.getAttribute('stroke'), width:Number(outline.getAttribute('stroke-width'))})),
                  glints: glints.map(glint => ({tag:glint.tagName.toLowerCase(),
                    cx:Number(glint.getAttribute('cx')), cy:Number(glint.getAttribute('cy')),
                    rx:Number(glint.getAttribute('rx')), ry:Number(glint.getAttribute('ry')),
                    eye:glint.dataset.sigilGlint, fill:glint.getAttribute('fill'),
                    transform:glint.getAttribute('transform')})),
                  contained};
        })""")
        assert len(identity) == 8, identity
        assert len({item["color"] for item in identity}) == 8, identity
        assert all(not item["hasMask"] for item in identity), identity
        assert all(len(item["eyes"]) == 2 for item in identity), identity
        assert all(item["glints"] == [] for item in identity), "the simple faces have no detached highlights"
        assert all(eye["tag"] == "path" and eye["fill"] == "#0b1511"
                   and eye["stroke"] is None
                   and eye["contrastInk"] == "#0b1511"
                   and 1.0 <= eye["height"] / eye["width"] <= 1.35
                   for item in identity for eye in item["eyes"]), identity
        assert all(not item["outlines"] for item in identity), identity
        assert all(abs(item["eyes"][0]["rx"] - item["eyes"][1]["rx"]) <= .3
                   and abs(item["eyes"][0]["ry"] - item["eyes"][1]["ry"]) <= .3
                   for item in identity), "paired eyes should feel balanced"
        assert all(item["eyes"][0]["cx"] < item["eyes"][1]["cx"] for item in identity)
        assert all(-12 <= eye["angle"] <= 12 for item in identity for eye in item["eyes"]), identity
        assert all(abs(item["eyes"][0]["angle"] + item["eyes"][1]["angle"]) <= 4
                   for item in identity), "paired eyes should tilt gently toward one another"
        assert len({tuple((eye["cx"], eye["cy"], eye["rx"], eye["ry"], eye["angle"])
                          for eye in item["eyes"])
                    for item in identity}) == 8, identity
        face_rows = {round(sum(eye["cy"] for eye in item["eyes"]) / 2, 1) for item in identity}
        assert len(face_rows) >= 6, "eye height should follow each silhouette's usable face area"
        assert all(part == {"inHead": True}
                   for item in identity for part in item["contained"]), identity

        # The shape chooser must preview each head with that head's actual face.
        # This catches the old bug where every chooser button inherited the orb
        # eye positions even though the silhouettes themselves were different.
        page.goto(f"{app_url}/#/bot/mascot-0")
        details = page.locator("#assistant-more-settings")
        details.wait_for(state="attached")
        details.locator(":scope > summary").click()
        page.locator("[data-idp-shapes] .shp svg").first.wait_for()
        picker_faces = page.locator("[data-idp-shapes] .shp svg").evaluate_all("""svgs => svgs.map(svg => ({
          head: svg.querySelector(':scope > path')?.getAttribute('d'),
            eyes: [...svg.querySelectorAll('[data-sigil-eye]')].map(eye => ({
            cx:Number(eye.dataset.cx), cy:Number(eye.dataset.cy),
            rx:Number(eye.dataset.rx), ry:Number(eye.dataset.ry), tag:eye.tagName.toLowerCase(),
            transform:eye.getAttribute('transform'),
          }))
        }))""")
        assert len(picker_faces) == len(identity) == 8, picker_faces
        assert [face["head"] for face in picker_faces] == [face["head"] for face in identity]
        assert [face["eyes"] for face in picker_faces] == [
            [{key: eye[key] for key in ("cx", "cy", "rx", "ry", "tag", "transform")} for eye in face["eyes"]]
            for face in identity
        ], picker_faces
        shape_buttons = page.locator("[data-idp-shapes] .shp")
        assert shape_buttons.evaluate_all("""buttons => buttons.every(button => {
          const box = button.getBoundingClientRect(); return box.width === 44 && box.height === 44;
        })"""), "shape choices need 44px touch targets"
        color_buttons = page.locator("[data-idp-colors] .sw")
        assert color_buttons.evaluate_all("""buttons => buttons.every(button => {
          const box = button.getBoundingClientRect(); return box.width === 44 && box.height === 44;
        })"""), "color choices need 44px touch targets"
        identity_panel = page.locator("#idp-panel")
        identity_panel.screenshot(path=str(out / "shape-picker-desktop.png"), animations="disabled")

        shape_keys = ("orb", "capsule", "bean", "drop", "pebble", "shield", "triangle", "hex")
        for index, shape_key in enumerate(shape_keys):
            shape_buttons.nth(index).click()
            assert shape_buttons.nth(index).get_attribute("aria-pressed") == "true"
            preview = page.locator("[data-idp-prev] .avatar svg")
            selected_shape = shape_buttons.nth(index).locator("svg > path").first.get_attribute("d")
            preview_shape = preview.locator(":scope > path").first.get_attribute("d")
            assert preview_shape == selected_shape
            selected_eyes = shape_buttons.nth(index).locator("svg [data-sigil-eye]").evaluate_all(
                "eyes => eyes.map(eye => [eye.dataset.cx, eye.dataset.cy, eye.dataset.rx, eye.dataset.ry, eye.getAttribute('transform')])")
            preview_eyes = preview.locator("[data-sigil-eye]").evaluate_all(
                "eyes => eyes.map(eye => [eye.dataset.cx, eye.dataset.cy, eye.dataset.rx, eye.dataset.ry, eye.getAttribute('transform')])")
            assert preview_eyes == selected_eyes
            selected_glints = shape_buttons.nth(index).locator("svg [data-sigil-glint]").evaluate_all(
                "glints => glints.map(glint => [glint.dataset.sigilGlint, glint.getAttribute('cx'), glint.getAttribute('cy'), glint.getAttribute('transform')])")
            preview_glints = preview.locator("[data-sigil-glint]").evaluate_all(
                "glints => glints.map(glint => [glint.dataset.sigilGlint, glint.getAttribute('cx'), glint.getAttribute('cy'), glint.getAttribute('transform')])")
            assert preview_glints == selected_glints
            avatar_preview = page.locator("[data-idp-prev] .avatar")
            avatar_preview.evaluate("el => el.style.setProperty('--av', '128px')")
            avatar_preview.screenshot(path=str(out / f"face-{shape_key}.png"), animations="disabled")
            avatar_preview.evaluate("el => el.style.removeProperty('--av')")
        shape_buttons.first.click()
        page.set_viewport_size({"width": 900, "height": 1024})
        identity_panel.screenshot(path=str(out / "shape-picker-tablet.png"), animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})
        identity_panel.screenshot(path=str(out / "shape-picker-phone.png"), animations="disabled")
        mobile_button_rows = page.locator("[data-idp-shapes] .shp").evaluate_all("""buttons => {
          const rows = new Set(buttons.map(button => Math.round(button.getBoundingClientRect().top)));
          return {rowCount:rows.size, overflow:document.documentElement.scrollWidth - innerWidth};
        }""")
        assert mobile_button_rows["rowCount"] == 2, mobile_button_rows
        assert mobile_button_rows["overflow"] <= 1, mobile_button_rows
        page.set_viewport_size({"width": 320, "height": 740})
        identity_panel.screenshot(path=str(out / "shape-picker-compact-phone.png"), animations="disabled")
        compact_button_rows = page.locator("[data-idp-shapes] .shp").evaluate_all("""buttons => ({
          rowCount:new Set(buttons.map(button => Math.round(button.getBoundingClientRect().top))).size,
          overflow:document.documentElement.scrollWidth - innerWidth,
        })""")
        assert compact_button_rows["rowCount"] == 2, compact_button_rows
        assert compact_button_rows["overflow"] <= 1, compact_button_rows
        compact_color_rows = page.locator("[data-idp-colors] .sw").evaluate_all("""buttons => new Set(
          buttons.map(button => Math.round(button.getBoundingClientRect().top))).size""")
        assert compact_color_rows == 2, compact_color_rows

        def relative_luminance(color: str) -> float:
            channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in channels]
            return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]

        eye_ink = identity[0]["eyes"][0]["contrastInk"]
        eye_contrast = [
            (max(relative_luminance(eye_ink), relative_luminance(item["color"])) + .05)
            / (min(relative_luminance(eye_ink), relative_luminance(item["color"])) + .05)
            for item in identity
        ]
        assert min(eye_contrast) >= 3, eye_contrast

        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(out / "phone-studio.png"), animations="disabled")
        if page.locator("#nav-toggle").is_visible():
            page.locator("#nav-toggle").click()
            page.locator("#workspace.open").wait_for()
        page.screenshot(path=str(out / "phone-roster.png"), animations="disabled")
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844], "compact_phone": [320, 740]},
            "screenshots": ["desktop.png", "phone-studio.png", "phone-roster.png", "shape-picker-desktop.png", "shape-picker-tablet.png", "shape-picker-phone.png", "shape-picker-compact-phone.png"],
            "individually_reviewed_faces": [f"face-{shape_key}.png" for shape_key in shape_keys],
            "silhouettes": 8,
            "colors": 8,
            "minimum_eye_contrast": round(min(eye_contrast), 2),
            "checks": ["each shape has two balanced ink oval eyes directly on its color", "both eye contours stay inside each distinct head", "shape-specific faces match every picker silhouette and live preview", "eye contrast against every identity color", "44px shape controls", "balanced two-row phone and compact-phone picker", "no phone overflow", "no browser errors"],
            "page_errors": errors,
            "provider_calls": 0,
            "source_sha256": {
                relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                for relative in ("src/hutch/server/static/app.js", "src/hutch/server/static/style.css",
                                 "src/hutch/server/static/index.html", "tests/e2e/test_design_system.py")
            },
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace-failed.zip"))
        except Exception:
            pass
        context.close()


def test_chat_message_search_is_scoped_responsive_and_opens_its_conversation(browser, app_server):
    """Search stays inside the Studio flow and opens the selected chat without URL query leakage."""
    app_url, app = app_server
    store = app.state.store
    default_bot = store.get_bot("design-system-review")
    second_bot = store.create_bot(Bot(
        name="search-travel-planner", display_name="Travel Planner", model="mock/demo", tools=[]
    ))
    first, _ = store.create_conversation(default_bot.id, "Workshop notes", idem_key="search-workshop",
                                         request_hash="search-workshop")
    second, _ = store.create_conversation(second_bot.id, "Trip planning", idem_key="search-trip",
                                          request_hash="search-trip")
    with store._tx() as db:
        store._insert_conversation_message(
            db, message_id="search-workshop-message", conversation_id=first["id"], seq=1,
            run_id="", role="user", content="The violet gearbox needs a service check.",
            created_at="2026-10-09T12:00:00+00:00",
        )
        store._insert_conversation_message(
            db, message_id="search-trip-message", conversation_id=second["id"], seq=1,
            run_id="", role="user", content="We found a violet gearbox in the travel case. <img src=x onerror=alert(1)>",
            created_at="2026-10-09T12:05:00+00:00",
        )

    touch_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                        has_touch=True, reduced_motion="reduce")
    touch_page = touch_context.new_page()
    touch_page.goto(f"{app_url}/#/chat/design-system-review")
    touch_search = touch_page.get_by_role("button", name="Search chats")
    touch_search.wait_for()
    touch_size = touch_search.bounding_box()
    assert touch_size and touch_size["width"] >= 44 and touch_size["height"] >= 44, touch_size
    touch_context.close()

    out = ROOT / "docs/realignment/artifacts/conversation-search"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[str] = []
    external_requests: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    sizes = {"desktop": (1440, 960), "tablet": (900, 1024), "phone": (390, 844),
             "compact-phone": (320, 740)}
    evidence = []
    try:
        for label, (width, height) in sizes.items():
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{app_url}/#/chat/design-system-review")
            page.locator("#conversation-switcher").wait_for()
            search_button = page.get_by_role("button", name="Search chats")
            search_button.click()
            dialog = page.get_by_role("dialog", name="Search chats")
            field = dialog.get_by_role("searchbox", name="Search messages")
            field.fill("violet gearbox")
            page.wait_for_function("document.querySelectorAll('.message-search-result').length === 2")
            assert "violet gearbox" not in page.url.lower(), page.url
            dialog.locator("#message-search-bot").select_option(second_bot.id)
            page.wait_for_function("document.querySelectorAll('.message-search-result').length === 1")
            result = dialog.locator(".message-search-result").first
            assert "Trip planning" in result.inner_text()
            assert "Travel Planner" in result.inner_text()
            assert "violet gearbox" in result.inner_text().lower()
            assert "<img" in result.inner_text()
            assert result.locator("img").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, label
            page.screenshot(path=str(out / f"search-{label}.png"), animations="disabled")
            evidence.append({"size": label, "viewport": [width, height], "all_bot_hits": 2,
                             "filtered_hits": 1, "query_in_url": False})
            if label == "desktop":
                dialog.locator("#message-search-bot").select_option("")
                field.fill("saffron calibration absent")
                page.wait_for_function(
                    "document.querySelector('#message-search-status')?.textContent === 'No messages found in active chats.'"
                )
                assert dialog.locator(".message-search-result").count() == 0
                page.screenshot(path=str(out / "search-empty-desktop.png"), animations="disabled")

                def fail_search(route):
                    route.fulfill(status=503, content_type="application/json",
                                  body=json.dumps({"detail": "search service unavailable"}))

                page.route("**/api/v1/search/messages", fail_search)
                field.fill("violet gearbox")
                page.wait_for_function(
                    "document.querySelector('#message-search-status')?.textContent === 'Search unavailable: search service unavailable'"
                )
                assert dialog.locator(".message-search-result").count() == 0
                page.screenshot(path=str(out / "search-error-desktop.png"), animations="disabled")
                page.unroute("**/api/v1/search/messages", fail_search)
            field.press("Escape")
            assert page.evaluate("document.activeElement.id") == "studio-search-messages"
            if label == "phone":
                dialog = page.get_by_role("dialog", name="Search chats")
                page.get_by_role("button", name="Search chats").click()
                dialog = page.get_by_role("dialog", name="Search chats")
                dialog.get_by_role("searchbox", name="Search messages").fill("violet gearbox")
                page.wait_for_function("document.querySelectorAll('.message-search-result').length === 2")
                dialog.locator("#message-search-bot").select_option(second_bot.id)
                page.wait_for_function("document.querySelectorAll('.message-search-result').length === 1")
                dialog.locator(".message-search-result").click()
                page.wait_for_function(
                    "id => document.querySelector('#conversation-switcher')?.value === id", arg=second["id"]
                )
                assert page.evaluate("location.hash") == "#/chat/search-travel-planner"

        assert not external_requests, external_requests
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_design_system.py::test_chat_message_search_is_scoped_responsive_and_opens_its_conversation",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_design_system.py::test_chat_message_search_is_scoped_responsive_and_opens_its_conversation",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "playwright": package_version("playwright"),
            "viewports": evidence,
            "external_requests": external_requests,
            "provider_calls": 0,
            "touch_search_target_css_pixels": [touch_size["width"], touch_size["height"]],
            "states": ["active conversation search", "Bot filter", "no results", "service error", "escaped HTML excerpt", "conversation opened", "focus restored"],
            "visual_review": "Individually inspected desktop/tablet/phone/compact-phone screenshots; no overflow or layout clipping.",
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace.zip"))
        except Exception:
            pass
        context.close()


def test_every_workspace_route_renders_independently_at_responsive_sizes(browser, app_server, site_server):
    """Keep one screenshot per surface and viewport; never judge these pages from a contact sheet."""
    app_url, app = app_server
    store = app.state.store
    bot_names = [
        "research-partner", "release-reviewer", "calendar-planner", "inbox-organizer",
        "customer-operations-analyst", "coding-partner", "quality-reviewer", "policy-researcher",
        "project-planner", "content-editor",
    ]
    display_names = [
        "Research Partner", "Release Notes Reviewer", "Calendar Planner", "Inbox Organizer",
        "Customer Operations and Knowledge Research Analyst", "Coding Partner", "Quality Reviewer",
        "Policy Researcher", "Project Planner", "Content Editor",
    ]
    for name, display_name in zip(bot_names, display_names, strict=True):
        store.create_bot(Bot(name=name, display_name=display_name, model="mock/demo", tools=[]))
    run = store.create_run(Run(
        bot_id=store.get_bot("design-system-review").id,
        prompt="Review the recent workspace activity.",
        status=RunStatus.succeeded,
        exit_reason="completed",
        finished_at=datetime.now(timezone.utc).isoformat(),
    ))

    out = ROOT / "docs/realignment/artifacts/ui-surface-review"
    out.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
    page = context.new_page()
    errors: list[dict[str, str]] = []
    external_requests: list[str] = []
    active_surface = {"name": "setup"}
    page.on("pageerror", lambda error: errors.append({"surface": active_surface["name"], "error": str(error)}))
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).hostname not in {"127.0.0.1", "localhost"} else None)
    context.tracing.start(screenshots=True, snapshots=True, sources=False)

    viewports = {
        "desktop": (1440, 960),
        "tablet": (900, 1024),
        "phone": (390, 844),
        "compact-phone": (320, 740),
    }
    surfaces = [
        ("studio", f"{app_url}/#/chat/design-system-review", "#conversation-switcher"),
        ("activity", f"{app_url}/#/overview", ".ov-all-clear"),
        ("schedules", f"{app_url}/#/schedules", ".schedule-overview"),
        ("fleet", f"{app_url}/#/bots", ".bot-grid"),
        ("runs", f"{app_url}/#/runs", "#runs-table-wrap"),
        ("approvals", f"{app_url}/#/approvals", "#needs-you"),
        ("connections", f"{app_url}/#/connections", ".service-tile"),
        ("bot-settings", f"{app_url}/#/bot/design-system-review", "#app-top-context h1"),
        ("run-detail", f"{app_url}/#/run/{run.id}", "#run-technical-details > summary"),
        ("marketing", site_server, ".hero-title"),
    ]
    evidence = []
    trace_saved = False
    try:
        for viewport_name, (width, height) in viewports.items():
            page.set_viewport_size({"width": width, "height": height})
            for surface_name, url, ready_selector in surfaces:
                active_surface["name"] = f"{surface_name}-{viewport_name}"
                page.goto(url, wait_until="domcontentloaded")
                page.locator(ready_selector).first.wait_for(timeout=15_000)
                if surface_name == "approvals":
                    page.locator("#needs-you").wait_for(state="visible")
                if surface_name == "studio":
                    page.locator("#chat-stream .welcome").wait_for(state="visible", timeout=15_000)
                    assert page.locator("#chat-stream .welcome").is_visible()
                    assert page.get_by_text("No description yet.", exact=True).count() == 0
                    if viewport_name in {"phone", "compact-phone"}:
                        assert page.locator("#chat-prompt").get_attribute("placeholder") == "Message…"
                if surface_name == "connections":
                    chatgpt_mark = page.locator(".service-mark-chatgpt img")
                    assert chatgpt_mark.get_attribute("src") == "/static/brands/openai-white-monoblossom.svg"
                    outlook_mark = page.locator(".service-mark-outlook svg[data-icon='inbox']")
                    assert outlook_mark.is_visible()
                    assert page.locator(".service-mark-outlook img").count() == 0
                    assert page.get_by_role("heading", name="Microsoft Outlook", exact=True).is_visible()
                if surface_name == "bot-settings":
                    page.wait_for_function(
                        "document.querySelector('#app-top-context h1')?.textContent.trim() === 'Design Partner settings'"
                    )
                page.evaluate("document.fonts.ready")
                metrics = page.evaluate("""() => ({
                  viewport: [innerWidth, innerHeight],
                  documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
                  title: document.querySelector('#app-top-context h1')?.textContent.trim()
                    || document.querySelector('.hero-title')?.textContent.trim()
                    || document.querySelector('#needs-you-title')?.textContent.trim() || '',
                  workspace: !!document.querySelector('.app-shell #workspace'),
                  visibleBotNames: [...document.querySelectorAll('#roster-list .roster-name')]
                    .filter(node => node.getClientRects().length
                      && (!node.closest('details') || node.closest('details').open))
                    .map(node => node.textContent.trim()),
                  menuControls: document.querySelectorAll('#roster-list [data-bot-options]').length
                })""")
                assert metrics["documentWidth"] <= width + 1, (surface_name, viewport_name, metrics)
                if surface_name != "marketing":
                    assert metrics["workspace"], (surface_name, viewport_name, "workspace shell missing")
                if surface_name == "fleet":
                    assert metrics["menuControls"] == 11, metrics
                    assert "Customer Operations and Knowledge Research Analyst" not in metrics["visibleBotNames"]
                    # The long role name is intentionally visible through All bots, whose sidebar is collapsed by default.
                    assert page.locator("#roster-idle-details summary").count() == 1
                    first_card = page.locator(".bot-card").first
                    assert first_card.locator(".card-actions [data-fleet-options]").count() == 1
                    assert first_card.locator(".card-actions > a").count() == 1
                    assert first_card.locator(".bot-card-details").count() == 1
                    detail_summary = " ".join(first_card.locator(".bot-card-details > summary").inner_text().split())
                    assert detail_summary.startswith("More details")
                    assert ("AI service, schedule, and activity" in detail_summary) == (width > 560)
                    assert first_card.locator(".bot-facts").is_hidden()
                    visible_summary = first_card.locator(".bot-chips").inner_text().lower()
                    assert "mock/demo" not in visible_summary and "ask: ask" not in visible_summary
                    if viewport_name in {"phone", "compact-phone"}:
                        create_button = page.locator("#btn-new-bot-top")
                        title_box = page.locator("#app-top-context h1").bounding_box()
                        create_box = create_button.bounding_box()
                        assert title_box and create_box and abs(
                            (title_box["y"] + title_box["height"] / 2)
                            - (create_box["y"] + create_box["height"] / 2)
                        ) <= 3, (viewport_name, title_box, create_box)
                        assert create_button.get_attribute("aria-label") == "New assistant"
                        assert create_box["width"] >= 44
                        assert page.locator("#app-top-context h1").inner_text() == "Manage assistants"
                        assert page.locator("#app-top-context h1").evaluate("el => el.scrollWidth <= el.clientWidth")
                        if viewport_name == "phone":
                            assert create_button.inner_text().strip() == "New"
                            assert create_box["width"] > 80, create_box
                        else:
                            assert create_button.evaluate("el => getComputedStyle(el).fontSize") == "0px"
                if surface_name == "studio":
                    page.locator("#tpl-grid .tpl-name").first.wait_for()
                    gallery_names = page.locator("#tpl-grid .tpl-name").all_text_contents()
                    assert gallery_names[:6] == [
                        "File organizer", "Meeting follow-up", "Weekly review",
                        "Research briefing", "Website change alerts", "Support inbox helper",
                    ], gallery_names
                    assert page.locator('#tpl-grid [data-tpl="tidy-downloads"]').count() == 1
                    assert "repo-sweeper" not in gallery_names
                if surface_name == "schedules":
                    assert page.locator("details.schedule-empty-bots").count() == 1
                    assert page.locator(".schedule-empty-bots summary").inner_text() == "Choose an assistant"
                    assert page.locator(".schedule-empty-bots a[href^='#/bot/']").count() == 11
                if surface_name == "activity":
                    assert page.locator(".ov-summary-stats .kpi").count() == 2
                    usage_details = page.locator(".ov-usage-details")
                    assert usage_details.count() == 1 and not usage_details.evaluate("el => el.open")
                    assert "tokens" not in page.locator(".ov-summary-stats").inner_text().lower()
                    assert "cost" not in page.locator(".ov-summary-stats").inner_text().lower()
                    assert page.locator(".ov-all-clear").is_visible()
                    assert page.locator(".ov-col").count() == 0
                    assert page.get_by_role("link", name="Start a chat").is_visible()
                    assert page.get_by_role("link", name="View past work").is_visible()
                    assert page.locator(".ov-recent .ov-row-prompt").inner_text() == "Review the recent workspace activity."
                    usage_details.locator("summary").click()
                    usage_text = usage_details.inner_text().lower()
                    assert "reported model tokens today" in usage_text
                    assert "recorded provider cost today" in usage_text
                    usage_details.locator("summary").click()
                if surface_name == "runs":
                    run_card = page.locator("#runs-table-wrap .run-card").first
                    assert run_card.is_visible()
                    assert run_card.locator(".run-card-bot b").inner_text() == "Design Partner"
                    assert "Review the recent workspace activity." in run_card.inner_text()
                    assert "tokens" not in run_card.inner_text().lower()
                    assert "steps" not in run_card.inner_text().lower()
                    assert run.id not in run_card.inner_text()
                    assert page.locator("#runs-table-wrap > table").count() == 0
                    assert page.locator("#runs-count").inner_text() == "1 result"
                if surface_name == "run-detail":
                    assert page.get_by_role("heading", name="Task details").is_visible()
                    technical_details = page.locator("#run-technical-details")
                    assert technical_details.is_visible() and technical_details.get_attribute("open") is None
                    assert not page.locator("[data-run-integrity-run]").is_visible()
                    assert page.locator("#chat-stream .mrun").count() == 1
                    assert not page.locator("#chat-stream .mrun").is_visible()
                    assert technical_details.locator("summary").inner_text().startswith("More details")
                evidence.append({"surface": surface_name, "size": viewport_name, **metrics})
                if viewport_name != "compact-phone":
                    page.screenshot(
                        path=str(out / f"{surface_name}-{viewport_name}.png"), animations="disabled"
                    )
                if surface_name == "studio" and viewport_name in {"desktop", "phone"}:
                    last_template = page.locator("#tpl-grid .tpl-card").last
                    last_template.wait_for(state="visible")
                    last_template.scroll_into_view_if_needed()
                    geometry = {
                        "card": last_template.evaluate("el => el.getBoundingClientRect().toJSON()"),
                        "composer": page.locator(".composer").evaluate("el => el.getBoundingClientRect().toJSON()"),
                    }
                    assert geometry and geometry["card"] and geometry["composer"]
                    final_template, composer_box = geometry["card"], geometry["composer"]
                    assert final_template and composer_box
                    assert final_template["y"] + final_template["height"] <= composer_box["y"] + 1, (
                        viewport_name, final_template, composer_box
                    )
                    page.screenshot(
                        path=str(out / f"studio-template-bottom-{viewport_name}.png"), animations="disabled"
                    )

            if viewport_name in {"desktop", "phone"}:
                active_surface["name"] = f"fleet-menu-{viewport_name}"
                page.goto(f"{app_url}/#/bots", wait_until="domcontentloaded")
                page.locator(".bot-card").first.wait_for(timeout=15_000)
                first_card = page.locator(".bot-card").first
                details = first_card.locator(".bot-card-details")
                details.locator("summary").click()
                assert details.locator(".bot-facts").is_visible()
                assert "mock/demo" in details.locator(".bot-facts").inner_text()
                first_card.screenshot(path=str(out / f"fleet-details-{viewport_name}.png"), animations="disabled")
                details.locator("summary").click()
                menu_trigger = first_card.locator(".fleet-card-menu > summary")
                assert menu_trigger.evaluate("node => [node.getBoundingClientRect().width, node.getBoundingClientRect().height]") == [44, 44]
                menu_trigger.click()
                menu = first_card.locator(".fleet-card-menu-panel")
                menu.wait_for(state="visible")
                assert menu.get_by_role("button", name="Pause assistant").is_visible()
                assert menu.get_by_role("link", name="Assistant settings").is_visible()
                assert page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) <= innerWidth + 1")
                page.screenshot(path=str(out / f"fleet-menu-{viewport_name}.png"), animations="disabled")

            if viewport_name in {"desktop", "phone"}:
                active_surface["name"] = f"preferences-{viewport_name}"
                page.goto(f"{app_url}/#/chat/design-system-review", wait_until="domcontentloaded")
                page.locator("#conversation-switcher").wait_for(timeout=15_000)
                if viewport_name == "phone":
                    page.locator("#nav-toggle").click()
                    page.locator("#workspace.open").wait_for()
                page.locator("#prefs-toggle").click()
                page.locator("#prefs-pop:not([hidden])").wait_for()
                metrics = page.evaluate("""() => ({
                  viewport: [innerWidth, innerHeight],
                  documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
                  dialog: document.querySelector('#prefs-pop')?.getBoundingClientRect().toJSON()
                })""")
                assert metrics["documentWidth"] <= width + 1, ("preferences", viewport_name, metrics)
                page.screenshot(path=str(out / f"preferences-{viewport_name}.png"), animations="disabled")
                evidence.append({"surface": "preferences", "size": viewport_name, **metrics})

        assert not external_requests, external_requests
        assert not errors, errors
        context.tracing.stop(path=str(out / "trace.zip"))
        trace_saved = True
        (out / "validation.json").write_text(json.dumps({
            "test": "tests/e2e/test_design_system.py::test_every_workspace_route_renders_independently_at_responsive_sizes",
            "command": ".venv/bin/python -m pytest -q tests/e2e/test_design_system.py::test_every_workspace_route_renders_independently_at_responsive_sizes",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "browser": f"{browser.browser_type.name.title()} {browser.version}",
            "playwright": package_version("playwright"),
            "viewports": evidence,
            "external_requests": external_requests,
            "provider_calls": 0,
            "synthetic_bots": len(bot_names) + 1,
            "long_display_name": display_names[4],
            "individual_surfaces": [name for name, _, _ in surfaces] + ["preferences", "Fleet details disclosure", "Fleet action menu"],
            "visual_review": "Open each desktop, tablet, and phone screenshot individually; 320px compact-phone has overflow assertions.",
            "reference_access": {
                "figma": "MCP node retrieval hit the Starter-plan limit; the supplied community file's chat, list, options-menu, and settings screens were selected and inspected individually in the open browser canvas.",
                "mobbin": "The screen searches returned a paid-plan requirement; no Mobbin result was used.",
            },
            "source_sha256": _visual_source_hashes(),
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if not trace_saved:
            try:
                context.tracing.stop(path=str(out / "trace-failed.zip"))
            except Exception:
                pass
        context.close()
