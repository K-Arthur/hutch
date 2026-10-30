"""Live visual validation for onboarding slice 02 (real app, real routes).

Captures the AI-service chooser state matrix and the SPA handoff to
docs/onboarding/evidence/slice-02/ as PNG plus capture-results.json. A human
reviewer opens the images and writes validation.json; this test never claims a
visual verdict by itself.

Chromium/Linux only; no real phone, screen reader, browser zoom, Firefox or
WebKit run is claimed (recorded as limitations in the evidence README).
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

expect = pw.expect

from hutch.models import iso, utcnow  # noqa: E402
from hutch.onboarding import apply_request_edit, default_setup, encode_setup  # noqa: E402
from hutch.onboarding_store import SETUP_KEY  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(os.environ.get("HUTCH_ONBOARDING_EVIDENCE_DIR",
                                str(ROOT / "docs" / "onboarding" / "evidence" / "slice-02")))
VIEWPORTS = {"320": (320, 740), "375": (375, 812), "768": (768, 1024), "1440": (1440, 1000)}
REQUEST = "Juno 助手 - Zoë Ångström - plan the launch week and keep the follow-ups"


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        browser = launch_browser(playwright)
        yield browser
        browser.close()


@pytest.fixture()
def app_server(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "local Hutch preview did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", app
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        assert not thread.is_alive(), "local Hutch preview did not stop"


def seed(app, *, text=REQUEST, route_kind="", **overrides):
    """A stored request (revision 1) with an optional already-chosen route."""
    now = utcnow()
    built = apply_request_edit(default_setup(now), expected_revision=0, request_text=text, now=now)
    setup = built.setup.model_copy(update={
        "resume_expires_at": iso(now + timedelta(days=30)),
        "route_kind": route_kind,
        "route_chosen_at": iso(now) if route_kind else "",
        "step": "ai_service" if route_kind else "request",
    } | overrides)
    app.state.store.kv_set(SETUP_KEY, encode_setup(setup))
    return setup


def stored(app) -> dict:
    return json.loads(app.state.store.kv_get(SETUP_KEY))


def stub_first_run_readiness(context):
    """Force the real first-run panel into its no-provider state.

    The host running the browser lane may already have an OpenCode profile, so
    the SPA would otherwise offer a ready route and skip the handoff under test.
    These are the same deterministic fixtures the pinned first-run tests use.
    """

    def route(request):
        path = urlsplit(request.request.url).path
        bodies = {
            "/api/v1/preferences/model-defaults": {"model": "", "inference_mode": "hybrid", "configured": False},
            "/api/v1/opencode/status": {"ready": False, "authenticated": False, "models": [], "integrations": []},
            "/api/v1/model-routes": [],
        }
        if path not in bodies:
            request.continue_()
            return
        request.fulfill(status=200, content_type="application/json", body=json.dumps(bodies[path]))

    context.route("**/api/v1/**", route)


def watch(page, errors, external):
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(("http://127.0.0.1", "http://localhost", "data:", "about:")) else None)


def open_chooser(page, url):
    page.goto(url + "/onboarding/ai-service", wait_until="domcontentloaded")
    page.wait_for_selector("[data-onboarding-state]")


def page_state(page) -> str:
    return page.locator("[data-onboarding-state]").get_attribute("data-onboarding-state")


def dark_background(page) -> bool:
    value = page.evaluate("getComputedStyle(document.body).backgroundColor")
    channels = [int(part) for part in value[value.find("(") + 1:value.find(")")].split(",")[:3]]
    return max(channels) < 120


def snapshot(page, rows, *, state, label, width, height, suffix="",
             color_scheme="dark", forced_colors="none"):
    page.set_viewport_size({"width": width, "height": height})
    page.emulate_media(color_scheme=color_scheme, forced_colors=forced_colors)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(80)
    artifact = f"{state}-{label}-{color_scheme}{suffix}.png"
    page.screenshot(path=str(EVIDENCE / artifact), full_page=True, animations="disabled")
    observed = page.evaluate("""() => ({
        state: document.querySelector("[data-onboarding-state]")?.dataset.onboardingState || "",
        headings: document.querySelectorAll("h1").length,
        visiblePrimary: [...document.querySelectorAll(".btn.primary, [data-primary]")]
            .filter((el) => el.offsetParent !== null || el.getClientRects().length > 0).length,
        radios: document.querySelectorAll('input[name="route_kind"]').length,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        statuses: [...document.querySelectorAll("[role=status]")].map((el) => el.textContent.trim()).filter(Boolean),
        alerts: [...document.querySelectorAll("[role=alert]")].map((el) => el.textContent.trim()).filter(Boolean),
        bodyBackground: getComputedStyle(document.body).backgroundColor,
    })""")
    rows.append({
        "state": state, "label": label, "viewport": f"{width}x{height}",
        "color_scheme": color_scheme, "forced_colors": forced_colors,
        "artifact": f"docs/onboarding/evidence/slice-02/{artifact}",
        "observed": observed, "source": "live app route /onboarding/ai-service",
    })
    assert observed["headings"] == 1, f"{state}: expected exactly one h1"
    assert observed["overflow"] <= 0, f"{state} at {width}px: horizontal overflow {observed['overflow']}px"
    assert observed["visiblePrimary"] == 1, f"{state} at {width}px: primary action count {observed['visiblePrimary']}"
    if color_scheme == "light":
        assert dark_background(page), f"{state}: OS light preference inverted the fixed dark theme"


def choose_route(page, kind, submit_text="Continue with this route"):
    page.check(f'input[name="route_kind"][value="{kind}"]')
    page.click(f'button:has-text("{submit_text}")')
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("[data-onboarding-state]")


def test_capture_chooser_and_handoff_matrix(browser, app_server):
    url, app = app_server
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    errors: list[str] = []
    external: list[str] = []
    context = browser.new_context()
    stub_first_run_readiness(context)
    page = context.new_page()
    watch(page, errors, external)
    try:
        # No-request: the chooser redirects to the request step with a notice.
        app.state.store.kv_set(SETUP_KEY, encode_setup(default_setup(utcnow())))
        open_chooser(page, url)
        assert page.url.endswith("/onboarding")
        assert page_state(page) == "setup.empty_no_route"
        assert "Write your request first" in page.locator(".flash.error").inner_text()
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-no-request", label=label, width=width, height=height)

        # SPA handoff: the empty chat's one action carries the typed request to
        # /onboarding (never the Apps & AI catalog) and the request page restores it.
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(url + "/#/chat", wait_until="domcontentloaded")
        page.get_by_role("heading", name="What would you like help with?").wait_for()
        page.fill("#first-run-request", REQUEST)
        page.screenshot(path=str(EVIDENCE / "handoff-before-375-dark.png"), animations="disabled")
        rows.append({"state": "handoff-before", "label": "375", "viewport": "375x812",
                     "artifact": "docs/onboarding/evidence/slice-02/handoff-before-375-dark.png",
                     "source": "live app route /#/chat", "observed": {"requestDraft": True}})
        page.click("#first-run-submit")
        page.get_by_role("heading", name="What should your assistant do first?").wait_for()
        assert page.url.endswith("/onboarding")
        expect(page.locator("#request")).to_have_value(REQUEST)
        assert json.loads(page.evaluate("sessionStorage.getItem('hutch-first-run-request')"))["request"] == REQUEST
        assert page.locator("[data-draft-note]").is_visible()
        page.screenshot(path=str(EVIDENCE / "handoff-after-375-dark.png"), animations="disabled")
        rows.append({"state": "handoff-after", "label": "375", "viewport": "375x812",
                     "artifact": "docs/onboarding/evidence/slice-02/handoff-after-375-dark.png",
                     "source": "live app route /onboarding", "observed": {"requestRestored": True}})

        # Save the request and use the one primary action to reach the chooser.
        page.click('button:has-text("Save and continue")')
        page.wait_for_selector('[data-onboarding-state="setup.draft.saved"]')
        page.click('a:has-text("Continue to AI service")')
        page.wait_for_url("**/onboarding/ai-service")
        page.wait_for_selector('[data-onboarding-state="setup.ai_service.choose"]')
        assert page.locator('input[name="route_kind"]').count() == 3

        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-default", label=label, width=width, height=height)

        page.check('input[name="route_kind"][value="hosted_key"]')
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-recommended", label=label, width=width, height=height)

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("[data-onboarding-state]")
        for _ in range(6):
            page.keyboard.press("Tab")
            if page.evaluate("document.activeElement?.name") == "route_kind":
                break
        assert page.evaluate("document.activeElement?.name") == "route_kind"
        focus_style = page.evaluate("""() => {
            const input = document.activeElement;
            const label = input.closest(".onboarding-route");
            return {outline: getComputedStyle(label).outlineStyle, width: getComputedStyle(label).outlineWidth};
        }""")
        assert focus_style["outline"] == "solid" and focus_style["width"] != "0px", focus_style
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-keyboard-focus", label=label, width=width, height=height)

        page.evaluate("document.documentElement.style.fontSize = '200%'")
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-text-zoom-200", label=label, width=width, height=height)
        page.evaluate("document.documentElement.style.fontSize = ''")

        page.emulate_media(forced_colors="active")
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-forced-colors", label=label, width=width, height=height,
                     suffix="-forced-colors", forced_colors="active")
        page.emulate_media(forced_colors="none")

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("[data-onboarding-state]")
        choose_route(page, "local_service")
        assert page_state(page) == "setup.ai_service.chosen"
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-chosen", label=label, width=width, height=height)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector('[data-onboarding-state="setup.ai_service.chosen"]')
        page.set_viewport_size({"width": 375, "height": 812})
        snapshot(page, rows, state="chooser-chosen-resumed", label="375", width=375, height=812)
        page.go_back(wait_until="domcontentloaded")
        page.wait_for_selector("[data-onboarding-state]")
        assert page_state(page) in {"setup.ai_service.choose", "setup.ai_service.chosen"}
        page.go_forward(wait_until="domcontentloaded")
        page.wait_for_selector('[data-onboarding-state="setup.ai_service.chosen"]')

        page.emulate_media(reduced_motion="reduce")
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-chosen", label=label, width=width, height=height,
                     suffix="-reduced-motion")
        page.emulate_media(reduced_motion="no-preference")

        page.click('a:has-text("Change route")')
        page.wait_for_selector('[data-onboarding-state="setup.ai_service.choose"]')
        page.set_viewport_size({"width": 375, "height": 812})
        snapshot(page, rows, state="chooser-change", label="375", width=375, height=812)
        assert page.locator('input[value="local_service"]').is_checked()

        # Invalid selection: native validation is bypassed to reach the server state.
        seed(app)
        open_chooser(page, url)
        page.evaluate("document.querySelector('form[data-onboarding-form]').submit()")
        page.wait_for_selector('[data-onboarding-state="setup.ai_service.invalid"]')
        expect(page.locator("[data-error-summary]")).to_be_focused()
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-invalid", label=label, width=width, height=height)
        page.emulate_media(forced_colors="active")
        width, height = VIEWPORTS["375"]
        snapshot(page, rows, state="chooser-invalid", label="375", width=width, height=height,
                 suffix="-forced-colors", forced_colors="active")
        page.emulate_media(forced_colors="none")

        # Stale: requirements drift keeps the request and blocks choosing.
        seed(app, requirements_version=0)
        open_chooser(page, url)
        assert page_state(page) == "setup.ai_service.stale"
        for label in VIEWPORTS:
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-stale", label=label, width=width, height=height)

        # Conflict: two tabs choose differently; the second is an explicit 409.
        seed(app)
        older = context.new_page()
        newer = context.new_page()
        watch(older, errors, external)
        watch(newer, errors, external)
        try:
            open_chooser(older, url)
            open_chooser(newer, url)
            choose_route(older, "hosted_key")
            choose_route(newer, "opencode")
            assert page_state(newer) == "setup.ai_service.conflict"
            for label in VIEWPORTS:
                width, height = VIEWPORTS[label]
                snapshot(newer, rows, state="chooser-conflict", label=label, width=width, height=height)
            assert stored(app)["route_kind"] == "hosted_key"
        finally:
            older.close()
            newer.close()

        # Forbidden: a POST without the session token never changes the record.
        open_chooser(page, url)
        page.evaluate("""() => {
            const form = document.createElement("form");
            form.method = "post"; form.action = "/onboarding/ai-service/choose";
            document.body.append(form); form.submit();
        }""")
        page.wait_for_selector('[data-onboarding-state="auth.csrf_rejected"]')
        for label in ("375", "768", "1440"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-forbidden", label=label, width=width, height=height)

        # OS light preference must not invert the fixed dark theme.
        seed(app)
        open_chooser(page, url)
        for label in ("375", "768", "1440"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="chooser-default", label=label, width=width, height=height,
                     suffix="-light-preference", color_scheme="light")
    finally:
        context.close()

    assert not errors, f"page errors: {errors} (external requests: {external})"
    assert not external, f"unexpected external requests: {external}"
    results = {"slice": "02", "browser": "chromium", "platform": "linux", "rows": rows}
    (EVIDENCE / "capture-results.json").write_text(json.dumps(results, indent=2, sort_keys=True))
    assert len(rows) >= 45, f"expected the full chooser matrix, captured {len(rows)} rows"
