"""Live visual validation for onboarding slice 01 (real app, real routes).

Captures the request-step state matrix to docs/onboarding/evidence/slice-01/
as PNG plus capture-results.json. A human reviewer opens the images and writes
validation.json; this test never claims a visual verdict by itself.

Chromium/Linux only; no real phone, screen reader, or browser-zoom run is
claimed (recorded as limitations in the evidence README).
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from hutch.models import iso, utcnow  # noqa: E402
from hutch.onboarding import apply_request_edit, default_setup, encode_setup  # noqa: E402
from hutch.onboarding_store import SETUP_KEY  # noqa: E402
from hutch.server.app import create_app  # noqa: E402
from tests.support.artifacts import artifact_path  # noqa: E402
from tests.support.browser import launch_browser  # noqa: E402

# Captures go to the isolated test-artifact root. Set HUTCH_ONBOARDING_EVIDENCE_DIR to refresh the
# committed evidence under docs/onboarding/evidence/ on purpose; a passing run never rewrites it.
EVIDENCE = Path(os.environ.get("HUTCH_ONBOARDING_EVIDENCE_DIR", str(artifact_path("onboarding-evidence"))))
VIEWPORTS = {"320": (320, 740), "375": (375, 812), "768": (768, 1024), "1440": (1440, 1000)}
LONG_NON_LATIN = "Juno 助手 - Zoë Ångström - محمد - e\u0301 - Alexandria-Cassandra Montgomery-Worthington the Third"


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


def seed(app, *, text="A seeded request", contract_version=1, requirements_version=1,
         expires_in=timedelta(days=30), step="request", raw=None):
    store = app.state.store
    if raw is not None:
        store.kv_set(SETUP_KEY, raw)
        return
    now = utcnow()
    result = apply_request_edit(default_setup(now), expected_revision=0, request_text=text, now=now)
    setup = result.setup.model_copy(update={
        "contract_version": contract_version,
        "requirements_version": requirements_version,
        "resume_expires_at": iso(now + expires_in),
        "step": step,
    })
    store.kv_set(SETUP_KEY, encode_setup(setup))


def blank(app):
    app.state.store.kv_set(SETUP_KEY, encode_setup(default_setup(utcnow())))


def watch(page, errors, external):
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url)
            if not request.url.startswith(("http://127.0.0.1", "http://localhost", "data:", "about:")) else None)


def open_page(page, url):
    page.goto(url + "/onboarding", wait_until="domcontentloaded")
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
        mode: document.querySelector("[data-onboarding-state]")?.dataset.onboardingMode || "",
        headings: document.querySelectorAll("h1").length,
        visiblePrimary: [...document.querySelectorAll(".btn.primary, [data-primary]")]
            .filter((el) => el.offsetParent !== null || el.getClientRects().length > 0).length,
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        statuses: [...document.querySelectorAll("[role=status]")].map((el) => el.textContent.trim()).filter(Boolean),
        alerts: [...document.querySelectorAll("[role=alert]")].map((el) => el.textContent.trim()).filter(Boolean),
        bodyBackground: getComputedStyle(document.body).backgroundColor,
    })""")
    rows.append({
        "state": state,
        "label": label,
        "viewport": f"{width}x{height}",
        "color_scheme": color_scheme,
        "forced_colors": forced_colors,
        "artifact": f"docs/onboarding/evidence/slice-01/{artifact}",
        "observed": observed,
        "source": "live app route /onboarding",
    })
    overflow = observed["overflow"]
    assert observed["headings"] == 1, f"{state}: expected exactly one h1"
    assert overflow <= 0, f"{state} at {width}px: horizontal overflow {overflow}px"
    primary = observed["visiblePrimary"]
    assert primary == 1, f"{state} at {width}px: primary action count {primary}"
    if color_scheme == "light":
        assert dark_background(page), f"{state}: OS light preference inverted the fixed dark theme"


def fill_and_submit(page, text, submit_text="Save and continue"):
    page.fill("#request", text)
    page.click(f'button:has-text("{submit_text}")')
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector("[data-onboarding-state]")


def test_capture_state_matrix(browser, app_server):
    url, app = app_server
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    errors: list[str] = []
    external: list[str] = []
    context = browser.new_context()
    page = context.new_page()
    watch(page, errors, external)
    try:
        blank(app)
        open_page(page, url)
        assert page_state(page) == "setup.empty_no_route"
        for label in ("375", "768", "1440"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="empty", label=label, width=width, height=height)
        width, height = VIEWPORTS["320"]
        snapshot(page, rows, state="empty", label="320", width=width, height=height)

        open_page(page, url)
        fill_and_submit(page, LONG_NON_LATIN)
        assert page_state(page) == "setup.draft.saved"
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="saved", label=label, width=width, height=height)
            snapshot(page, rows, state="non-latin-long-request", label=label,
                     width=width, height=height, suffix="-long-non-latin")

        open_page(page, url)
        assert page_state(page) == "setup.resume.current"
        pw.expect(page.locator("[data-resume-message]")).to_contain_text("left off")
        resumed_statuses = [item for item in page.locator("[role=status]").all_inner_texts()
                            if "left off" in item.lower()]
        assert len(resumed_statuses) == 1, resumed_statuses
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="resumed", label=label, width=width, height=height)

        blank(app)
        open_page(page, url)
        fill_and_submit(page, "   ")
        assert page_state(page) == "input.invalid"
        assert page.locator("[data-error-summary]").count() == 1
        pw.expect(page.locator("[data-error-summary]")).to_be_focused(timeout=5_000)
        assert page.evaluate("document.activeElement === document.querySelector('[data-error-summary]')")
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="validation-error", label=label, width=width, height=height)
        page.emulate_media(forced_colors="active")
        for label in ("320", "375", "768", "1440"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="validation-error", label=label, width=width, height=height,
                     suffix="-forced-colors", forced_colors="active")

        blank(app)
        open_page(page, url)
        page.fill("#request", "A request that is being saved")
        page.evaluate("""() => {
            const form = document.querySelector("form[data-onboarding-form]");
            form.addEventListener("submit", (event) => event.preventDefault(), { once: true });
            form.requestSubmit();
        }""")
        page.wait_for_selector("[data-saving-status]:not([hidden])")
        assert page.locator("form[data-onboarding-form]").get_attribute("aria-busy") == "true"
        assert page.locator("[data-submit]").is_disabled()
        width, height = VIEWPORTS["375"]
        snapshot(page, rows, state="saving", label="375", width=width, height=height)

        seed(app, text="Keep this stored request", requirements_version=0)
        open_page(page, url)
        assert page_state(page) == "setup.resume.stale"
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="stale", label=label, width=width, height=height)

        seed(app, text="An old stored request", expires_in=timedelta(days=-2))
        open_page(page, url)
        assert page_state(page) == "setup.resume.expired"
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="expired", label=label, width=width, height=height)

        seed(app, raw="{not valid json")
        open_page(page, url)
        assert page_state(page) == "setup.damaged"
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="damaged", label=label, width=width, height=height)

        seed(app, text="Written by the future", contract_version=2)
        open_page(page, url)
        assert page_state(page) == "setup.resume.stale"
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="newer-version", label=label, width=width, height=height)

        blank(app)
        older = context.new_page()
        newer = context.new_page()
        watch(older, errors, external)
        watch(newer, errors, external)
        try:
            open_page(older, url)
            open_page(newer, url)
            fill_and_submit(older, "Saved first in this tab")
            newer.fill("#request", "Typed second in the other tab")
            newer.click('button:has-text("Save and continue")')
            newer.wait_for_load_state("domcontentloaded")
            newer.wait_for_selector('[data-onboarding-state="setup.conflict"]')
            for label in ("375", "768", "1440", "320"):
                width, height = VIEWPORTS[label]
                snapshot(newer, rows, state="conflict", label=label, width=width, height=height)
        finally:
            older.close()
            newer.close()

        blank(app)
        forbidden = context.new_page()
        watch(forbidden, errors, external)
        try:
            open_page(forbidden, url)
            forbidden.evaluate("""() => {
                const form = document.createElement("form");
                form.method = "post"; form.action = "/onboarding/request";
                document.body.append(form); form.submit();
            }""")
            forbidden.wait_for_load_state("domcontentloaded")
            forbidden.wait_for_selector('[data-onboarding-state="auth.csrf_rejected"]')
            for label in ("375", "768", "1440"):
                width, height = VIEWPORTS[label]
                snapshot(forbidden, rows, state="forbidden", label=label, width=width, height=height)
        finally:
            forbidden.close()

        blank(app)
        open_page(page, url)
        for label in ("375", "768", "1440"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="empty", label=label, width=width, height=height,
                     suffix="-light-preference", color_scheme="light")

        open_page(page, url)
        fill_and_submit(page, "Reduced motion request")
        page.emulate_media(reduced_motion="reduce")
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="saved", label=label, width=width, height=height,
                     suffix="-reduced-motion")

        blank(app)
        open_page(page, url)
        tab_stops = []
        for _ in range(8):
            page.keyboard.press("Tab")
            tab_stops.append(page.evaluate("document.activeElement?.id || document.activeElement?.tagName || ''"))
            if tab_stops[-1] == "request":
                break
        assert "request" in tab_stops, f"request field not keyboard reachable: {tab_stops}"
        focus_style = page.evaluate("""() => {
            const el = document.activeElement;
            const style = getComputedStyle(el);
            return {outline: style.outlineStyle + " " + style.outlineWidth, shadow: style.boxShadow};
        }""")
        assert focus_style["outline"] != "none 0px" or focus_style["shadow"] != "none", focus_style
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="keyboard-focus", label=label, width=width, height=height)

        open_page(page, url)
        page.evaluate("document.documentElement.style.fontSize = '200%'")
        for label in ("375", "768", "1440", "320"):
            width, height = VIEWPORTS[label]
            snapshot(page, rows, state="text-zoom-200", label=label, width=width, height=height)

        fill_and_submit(page, "Check the announcement")
        page.goto(url + "/onboarding", wait_until="domcontentloaded")
        page.wait_for_selector("[data-onboarding-state]")
        pw.expect(page.locator("[data-resume-message]")).to_contain_text("left off")
        statuses = page.locator("[role=status]").all_inner_texts()
        assert len([item for item in statuses if "left off" in item.lower()]) == 1, statuses
    finally:
        context.close()

    assert not errors, f"page errors: {errors} (external requests: {external})"
    assert not external, f"unexpected external requests: {external}"
    results = {"slice": "01", "browser": "chromium", "platform": "linux", "rows": rows}
    (EVIDENCE / "capture-results.json").write_text(json.dumps(results, indent=2, sort_keys=True))
    assert len(rows) >= 60, f"expected the full state matrix, captured {len(rows)} rows"