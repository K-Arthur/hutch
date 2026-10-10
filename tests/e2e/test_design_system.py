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
          return {head: body.getAttribute('d'), color: body.getAttribute('fill'),
                  eyes: eyes.map(eye => ({tag: eye.tagName.toLowerCase(), rx: Number(eye.getAttribute('rx')),
                    ry: Number(eye.getAttribute('ry')), cx: Number(eye.getAttribute('cx')),
                    cy: Number(eye.getAttribute('cy')), transform: eye.getAttribute('transform'),
                    fill: eye.getAttribute('fill') || eye.closest('g')?.getAttribute('fill')})),
                  contained};
        })""")
        assert len(identity) == 8, identity
        assert len({item["color"] for item in identity}) == 8, identity
        assert all(len(item["eyes"]) == 2 for item in identity), identity
        assert all(eye["tag"] == "ellipse" and eye["fill"] == "#10161f" and eye["ry"] > eye["rx"] * 1.15
                   for item in identity for eye in item["eyes"]), identity
        assert len({tuple((eye["rx"], eye["ry"]) for eye in item["eyes"])
                    for item in identity}) == 8, identity
        face_rows = {round(sum(eye["cy"] for eye in item["eyes"]) / 2, 1) for item in identity}
        assert len(face_rows) >= 6, "eye height should follow each silhouette's usable face area"
        assert all(part == {"center": True, "perimeter": True}
                   for item in identity for part in item["contained"]), identity

        # The shape chooser must preview each head with that head's actual face.
        # This catches the old bug where every chooser button inherited the orb
        # eye positions even though the silhouettes themselves were different.
        page.goto(f"{app_url}/#/bot/mascot-0")
        page.locator("[data-idp-shapes] .shp svg").first.wait_for()
        picker_faces = page.locator("[data-idp-shapes] .shp svg").evaluate_all("""svgs => svgs.map(svg => ({
          head: svg.querySelector('path')?.getAttribute('d'),
          eyes: [...svg.querySelectorAll('[data-sigil-eye]')].map(eye => ({
            cx:Number(eye.getAttribute('cx')), cy:Number(eye.getAttribute('cy')),
            rx:Number(eye.getAttribute('rx')), ry:Number(eye.getAttribute('ry')),
            transform:eye.getAttribute('transform'),
          }))
        }))""")
        assert len(picker_faces) == len(identity) == 8, picker_faces
        assert [face["head"] for face in picker_faces] == [face["head"] for face in identity]
        assert [face["eyes"] for face in picker_faces] == [
            [{key: eye[key] for key in ("cx", "cy", "rx", "ry", "transform")} for eye in face["eyes"]]
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
            selected_shape = shape_buttons.nth(index).locator("svg path").get_attribute("d")
            preview_shape = preview.locator(":scope > path").get_attribute("d")
            assert preview_shape == selected_shape
            selected_eyes = shape_buttons.nth(index).locator("svg [data-sigil-eye]").evaluate_all(
                "eyes => eyes.map(eye => [eye.getAttribute('cx'), eye.getAttribute('cy'), eye.getAttribute('transform')])")
            preview_eyes = preview.locator("[data-sigil-eye]").evaluate_all(
                "eyes => eyes.map(eye => [eye.getAttribute('cx'), eye.getAttribute('cy'), eye.getAttribute('transform')])")
            assert preview_eyes == selected_eyes
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
            "viewports": {"desktop": [1440, 960], "tablet": [900, 1024], "phone": [390, 844], "compact_phone": [320, 740]},
            "screenshots": ["desktop.png", "phone-studio.png", "phone-roster.png", "shape-picker-desktop.png", "shape-picker-tablet.png", "shape-picker-phone.png", "shape-picker-compact-phone.png"],
            "individually_reviewed_faces": [f"face-{shape_key}.png" for shape_key in shape_keys],
            "silhouettes": 8,
            "colors": 8,
            "minimum_eye_contrast": round(min(eye_contrast), 2),
            "checks": ["upright soft oval eyes with silhouette-specific center, spacing, scale, height, and tilt", "shape-specific faces match every picker silhouette and live preview", "eyes inside each mascot silhouette", "44px shape controls", "balanced two-row phone and compact-phone picker", "no phone overflow", "no browser errors"],
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
        ("activity", f"{app_url}/#/overview", ".ov-grid"),
        ("schedules", f"{app_url}/#/schedules", ".schedule-overview"),
        ("fleet", f"{app_url}/#/bots", ".bot-grid"),
        ("runs", f"{app_url}/#/runs", "#runs-table-wrap"),
        ("approvals", f"{app_url}/#/approvals", "#needs-you"),
        ("connections", f"{app_url}/#/connections", ".conn-card"),
        ("bot-settings", f"{app_url}/#/bot/design-system-review", "#app-top-context h1"),
        ("run-detail", f"{app_url}/#/run/{run.id}", "[data-run-integrity-run]"),
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
                if surface_name == "schedules":
                    assert page.locator("details.schedule-empty-bots").count() == 1
                    assert page.locator(".schedule-empty-bots summary").inner_text() == "Choose a Bot"
                    assert page.locator(".schedule-empty-bots a[href^='#/bot/']").count() == 11
                if surface_name == "runs":
                    if width <= 900:
                        run_card = page.locator("#runs-table-wrap .run-card").first
                        assert run_card.is_visible()
                        assert run_card.locator(".run-card-bot b").inner_text() == "Design Partner"
                        assert page.locator("#runs-table-wrap > table").is_hidden()
                    else:
                        assert page.locator("#runs-table-wrap tbody tr td:nth-child(2) b").first.inner_text() == "Design Partner"
                evidence.append({"surface": surface_name, "size": viewport_name, **metrics})
                if viewport_name != "compact-phone":
                    page.screenshot(
                        path=str(out / f"{surface_name}-{viewport_name}.png"), animations="disabled"
                    )

            if viewport_name in {"desktop", "phone"}:
                active_surface["name"] = f"fleet-menu-{viewport_name}"
                page.goto(f"{app_url}/#/bots", wait_until="domcontentloaded")
                page.locator(".bot-card").first.wait_for(timeout=15_000)
                first_card = page.locator(".bot-card").first
                menu_trigger = first_card.locator(".fleet-card-menu > summary")
                assert menu_trigger.evaluate("node => [node.getBoundingClientRect().width, node.getBoundingClientRect().height]") == [44, 44]
                menu_trigger.click()
                menu = first_card.locator(".fleet-card-menu-panel")
                menu.wait_for(state="visible")
                assert menu.get_by_role("button", name="Pause bot").is_visible()
                assert menu.get_by_role("link", name="Bot settings").is_visible()
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
            "individual_surfaces": [name for name, _, _ in surfaces] + ["preferences", "Fleet action menu"],
            "visual_review": "Open each desktop, tablet, and phone screenshot individually; 320px compact-phone has overflow assertions.",
            "reference_access": {
                "mobbin": "Search blocked by the paid-plan gate.",
                "figma": "Whole file rendered at 1600px; node-level detail calls hit the Starter-plan tool limit.",
            },
        }, indent=2) + "\n", encoding="utf-8")
    finally:
        if not trace_saved:
            try:
                context.tracing.stop(path=str(out / "trace-failed.zip"))
            except Exception:
                pass
        context.close()
