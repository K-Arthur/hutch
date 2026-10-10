"""Rendered checks that the app, server pages, and public site share Hutch's core UI tokens."""

from __future__ import annotations

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

from hutch.models import Bot  # noqa: E402
from hutch.server.app import create_app  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "website"


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
            studio_shell = _measure_operator_shell(page)
            assert studio_shell == {
                "workspace": True, "brand": "hutch", "studioLink": "Studio",
                "connectionsLink": "Connections", "context": True, "view": True,
            }, (label, studio_shell)
            studio = _measure_tokens(page, "studio")
            studio["operatorShell"] = studio_shell
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, (label, "Studio")
            page.screenshot(path=str(out / f"studio-{label}.png"), animations="disabled")

            # The user-facing Connections surface lives in the Studio shell.
            # `/connections` is a compatibility HTML page with a separate legacy
            # layout; using it here would validate the wrong product surface.
            page.goto(f"{app_url}/#/connections")
            page.get_by_role("heading", name="Connections").wait_for()
            page.locator(".conn-card").first.wait_for()
            connections_shell = _measure_operator_shell(page)
            assert connections_shell == studio_shell, (label, studio_shell, connections_shell)
            connections = _measure_tokens(page, "connections")
            connections["operatorShell"] = connections_shell
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, (label, "Connections")
            page.screenshot(path=str(out / f"connections-{label}.png"), animations="disabled")

            page.goto(site_server)
            page.locator(".hero-title").wait_for()
            page.evaluate("document.fonts.ready")
            marketing = _measure_tokens(page, "marketing")
            marketing["displayFont"] = page.locator(".hero-title").evaluate(
                "element => getComputedStyle(element).fontFamily"
            )
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1, (label, "Marketing")
            page.screenshot(path=str(out / f"marketing-{label}-viewport.png"), animations="disabled")
            page.screenshot(path=str(out / f"marketing-{label}.png"), full_page=True, animations="disabled")

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
                assert view["button"]["background"] == "rgb(52, 211, 153)", (label, name, view["button"])
                assert view["button"]["color"] == "rgb(5, 46, 33)", (label, name, view["button"])
                assert view["button"]["radius"] == "8px", (label, name, view["button"])
                assert view["panel"]["background"] == "rgb(8, 12, 18)", (label, name, view["panel"])
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
            "visual_review_required": "Open and inspect all twelve desktop/tablet/phone screenshots before accepting this result.",
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            context.tracing.stop(path=str(out / "trace-failed.zip"))
        except Exception:
            pass
        context.close()


def test_flat_mascot_eyes_stay_inside_every_silhouette(browser, app_server):
    """The app's paired eyes read as a face and remain contained across all eight shapes."""
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
    out = ROOT / "docs/realignment/artifacts/mascot-eye-review"
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
          const eyes = [...svg.querySelectorAll('[data-sigil-eye]')];
          const contained = eyes.map(eye => {
            const x = Number(eye.getAttribute('cx'));
            const y = Number(eye.getAttribute('cy'));
            const rx = Number(eye.getAttribute('rx')) * .98;
            const ry = Number(eye.getAttribute('ry')) * .98;
            const transform = eye.transform.baseVal.consolidate()?.matrix;
            const points = Array.from({length:32}, (_, index) => {
              const angle = index * Math.PI / 16;
              return new DOMPoint(x + Math.cos(angle) * rx, y + Math.sin(angle) * ry)
                .matrixTransform(transform);
            });
            const center = new DOMPoint(x, y).matrixTransform(transform);
            return {center: ctx.isPointInPath(shape, center.x, center.y),
                    perimeter: points.every(point => ctx.isPointInPath(shape, point.x, point.y))};
          });
          return {color: body.getAttribute('fill'),
                  eyes: eyes.map(eye => ({tag: eye.tagName.toLowerCase(), rx: Number(eye.getAttribute('rx')),
                    ry: Number(eye.getAttribute('ry')), fill: eye.getAttribute('fill') || eye.closest('g')?.getAttribute('fill')})),
                  contained};
        })""")
        assert len(identity) == 8, identity
        assert len({item["color"] for item in identity}) == 8, identity
        assert all(len(item["eyes"]) == 2 for item in identity), identity
        assert all(eye["tag"] == "ellipse" and eye["fill"] == "#10161f" and eye["rx"] > eye["ry"]
                   for item in identity for eye in item["eyes"]), identity
        assert len({tuple((eye["rx"], eye["ry"]) for eye in item["eyes"])
                    for item in identity}) == 8, identity
        assert all(part == {"center": True, "perimeter": True}
                   for item in identity for part in item["contained"]), identity

        def relative_luminance(color: str) -> float:
            channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in channels]
            return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]

        eye_ink = identity[0]["eyes"][0]["fill"]
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
            "viewports": {"desktop": [1440, 960], "phone": [390, 844]},
            "screenshots": ["desktop.png", "phone-studio.png", "phone-roster.png"],
            "silhouettes": 8,
            "colors": 8,
            "minimum_eye_contrast": round(min(eye_contrast), 2),
            "checks": ["paired diagonal oval eyes", "shape-specific face proportions", "eyes inside each mascot silhouette", "no phone overflow", "no browser errors"],
            "page_errors": errors,
            "provider_calls": 0,
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
