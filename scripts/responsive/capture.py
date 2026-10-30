"""Orchestrate the viewport x surface measurement and state screenshots."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlsplit

from responsive import checks, config, harness


class _Observer:
    """Collect page errors and non-local requests for the current surface only."""

    def __init__(self) -> None:
        self.surface = "setup"
        self.errors = []
        self.external = []

    def attach(self, page) -> None:
        page.on("pageerror", lambda error: self.errors.append(
            {"surface": self.surface, "message": str(error)[:400]}))
        page.on("request", self._note_request)

    def _note_request(self, request) -> None:
        host = urlsplit(request.url).hostname or ""
        if host and host not in {"127.0.0.1", "localhost"}:
            self.external.append({"surface": self.surface, "url": request.url[:300]})

    def reset(self, surface: str) -> None:
        self.surface = surface
        self.errors.clear()
        self.external.clear()


def _selected_surfaces(options):
    wanted = {label.strip() for label in options.surfaces.split(",") if label.strip()}
    if options.quick:
        wanted = wanted & set(config.QUICK_SURFACES) if wanted else set(config.QUICK_SURFACES)
    surfaces = list(config.SURFACES)
    if wanted:
        surfaces = [surface for surface in surfaces if surface.label in wanted]
    return surfaces


def _selected_viewports(options):
    wanted = {label.strip() for label in options.viewports.split(",") if label.strip()}
    if options.quick:
        wanted = wanted & set(config.QUICK_VIEWPORTS) if wanted else set(config.QUICK_VIEWPORTS)
    viewports = list(config.VIEWPORTS)
    if wanted:
        viewports = [viewport for viewport in viewports if viewport.label in wanted]
    return viewports


def _open_surface(page, surface, options, nav_state) -> None:
    """Navigate to a surface, reusing the loaded SPA shell for hash routes."""
    if surface.kind == "app" and nav_state.get("app_loaded"):
        hash_route = "#" + surface.path.split("#", 1)[1]
        page.evaluate("(value) => { location.hash = value; }", hash_route)
    else:
        page.goto(config.surface_url(surface, options.app_url, options.site_url),
                  wait_until="domcontentloaded", timeout=options.timeout_ms)
    nav_state["app_loaded"] = surface.kind == "app"
    page.locator(surface.ready).first.wait_for(state="visible", timeout=options.timeout_ms)


def _measure_surface(page, surface, viewport, options, output_dir, observer, nav_state):
    """Measure one surface at one viewport and return the evidence record."""
    ready = True
    ready_error = ""
    try:
        _open_surface(page, surface, options, nav_state)
    except Exception as error:
        ready = False
        ready_error = str(error)[:400]
    page.wait_for_timeout(options.settle_ms)
    viewport_contract = checks.measure_viewport(page)
    nav = checks.measure_nav(page) if surface.kind == "pages" else None
    overflow = checks.measure_overflow(page)
    targets = (checks.measure_targets(page, config.MIN_TARGET_PX, config.COMFORT_TARGET_PX)
               if viewport.touch else None)
    contrast = checks.measure_contrast(page) if viewport.label in config.CONTRAST_VIEWPORTS else None
    page.wait_for_timeout(120)
    record = {
        "surface": surface.label,
        "viewport": viewport.label,
        "width": viewport.width,
        "height": viewport.height,
        "pointer": viewport.pointer,
        "ready": ready,
        "ready_error": ready_error,
        "viewport_contract": viewport_contract,
        "js_enabled": not getattr(options, "no_js", False),
        "nav": nav,
        "overflow_px": overflow["overflow_px"],
        "overflow_offenders": overflow["offenders"],
        "external_requests": list(observer.external),
        "page_errors": list(observer.errors),
        "screenshot": None,
    }
    if targets is not None:
        record["targets"] = targets
    if contrast is not None:
        record["contrast"] = contrast
    if ready and options.screenshots and config.wants_screenshot(surface, viewport):
        relative = Path("docs") / "responsive" / "screenshots" / options.label / (
            "%s-%s.png" % (surface.label, viewport.label))
        path = config.REPO_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=(surface.kind == "site"), animations="disabled")
        record["screenshot"] = str(relative)
    return record


def _classify(record, failures, warnings, fail_on):
    """Split measured problems into failures (exit-code) and warnings (report-only)."""
    where = {"surface": record["surface"], "viewport": record["viewport"]}
    if not record["ready"]:
        failures.append({"kind": "ready", **where, "detail": "ready selector did not appear"})
    contract = record.get("viewport_contract") or {}
    if record["ready"] and not (contract.get("present") and contract.get("width_device")):
        failures.append({"kind": "meta", **where,
                         "detail": "viewport meta missing or lacks width=device-width"})
    elif record["ready"] and not contract.get("viewport_fit_cover"):
        failures.append({"kind": "meta", **where,
                         "detail": "viewport meta lacks viewport-fit=cover"})
    if record["overflow_px"] > 0:
        failures.append({"kind": "overflow", **where,
                         "detail": "%dpx; %s" % (record["overflow_px"],
                                                  [item["label"] for item in record["overflow_offenders"][:4]])})
    if record["page_errors"]:
        failures.append({"kind": "errors", **where,
                         "detail": record["page_errors"][0]["message"]})
    if record["external_requests"]:
        failures.append({"kind": "external", **where,
                         "detail": record["external_requests"][0]["url"]})
    targets = record.get("targets") or {}
    if targets.get("under_min_count"):
        entry = {"kind": "touch24", **where,
                 "detail": "%d target(s) below %dpx" % (targets["under_min_count"], config.MIN_TARGET_PX)}
        (failures if "touch24" in fail_on else warnings).append(entry)
    if targets.get("under_comfort_count"):
        warnings.append({"kind": "touch44", **where,
                         "detail": "%d target(s) below %dpx" % (
                             targets["under_comfort_count"], config.COMFORT_TARGET_PX)})
    nav = record.get("nav") or {}
    if nav.get("present"):
        wide = record["width"] > 1024
        if wide and not nav.get("nav_visible"):
            failures.append({"kind": "nav", **where,
                             "detail": "horizontal nav is not visible above 1024px"})
        if wide and nav.get("toggle_display") not in (None, "none"):
            failures.append({"kind": "nav", **where,
                             "detail": "compact menu toggle is visible above 1024px"})
        if not record.get("js_enabled", True) and not nav.get("nav_visible"):
            failures.append({"kind": "nav", **where,
                             "detail": "no-JS reader cannot see the primary nav"})
        if not record.get("js_enabled", True) and nav.get("visible_links", 0) < nav.get("total_links", 0):
            failures.append({"kind": "nav", **where,
                             "detail": "no-JS nav links are clipped or hidden"})
    contrast = record.get("contrast") or {}
    if contrast.get("violation_count"):
        entry = {"kind": "contrast", **where,
                 "detail": "%d sample(s) below WCAG AA" % contrast["violation_count"]}
        (failures if "contrast" in fail_on else warnings).append(entry)


def _capture_states(browser, app_url, options) -> tuple[list[dict], list[dict]]:
    """Capture the interactive states the static matrix cannot express."""
    states = []
    failures = []
    studio = app_url + "/#/chat/design-review"

    def new_page(width: int, height: int, touch: bool):
        context = browser.new_context(viewport={"width": width, "height": height},
                                      has_touch=touch, reduced_motion="reduce")
        return context, context.new_page()

    def grab(page, name: str) -> None:
        relative = Path("docs") / "responsive" / "screenshots" / options.label / ("state-%s.png" % name)
        path = config.REPO_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=False, animations="disabled")
        states.append({"name": name, "screenshot": str(relative)})

    def open_studio(page) -> bool:
        page.goto(studio, wait_until="domcontentloaded", timeout=options.timeout_ms)
        page.locator("#chat-prompt").first.wait_for(state="visible", timeout=options.timeout_ms)
        page.wait_for_timeout(options.settle_ms)
        return True

    def check_sidebar_open(page, name: str) -> None:
        expanded = page.locator("#sidebar-toggle").get_attribute("aria-expanded")
        classes = page.locator(".app-shell").get_attribute("class") or ""
        if expanded != "true" or "collapsed" in classes:
            failures.append({"kind": "state", "surface": "spa-studio", "viewport": name,
                             "detail": "sidebar is not expanded on a wide viewport"})
        grab(page, name)

    for name, width, height, touch in (("spa-sidebar-open-1180", 1180, 820, False),
                                       ("spa-sidebar-open-1366", 1366, 1024, True)):
        context, page = new_page(width, height, touch)
        try:
            open_studio(page)
            check_sidebar_open(page, name)
        finally:
            context.close()

    context, page = new_page(375, 812, True)
    try:
        open_studio(page)
        page.click("#nav-toggle")
        page.locator("#workspace.open").wait_for(state="visible", timeout=options.timeout_ms)
        grab(page, "spa-sheet-open-375")
    except Exception as error:
        failures.append({"kind": "state", "surface": "spa-studio", "viewport": "phone-375",
                         "detail": "phone sheet did not open: %s" % str(error)[:200]})
    finally:
        context.close()

    context, page = new_page(390, 844, True)
    try:
        open_studio(page)
        page.locator("#chat-prompt").focus()
        page.set_viewport_size({"width": 390, "height": 520})
        page.wait_for_timeout(500)
        probe = checks.measure_keyboard(page)
        visual_height = probe["visual_height"]
        composer = probe.get("composer") or {}
        if not composer or composer.get("bottom", 10**6) > visual_height + 1:
            failures.append({"kind": "state", "surface": "spa-studio",
                             "viewport": "keyboard-390",
                             "detail": "composer is not inside the shrunk visual viewport"})
        shell = probe.get("shell") or {}
        if shell and shell.get("height", 10**6) > visual_height + 2:
            failures.append({"kind": "state", "surface": "spa-studio",
                             "viewport": "keyboard-390",
                             "detail": "app shell height does not follow the visual viewport"})
        transcript = probe.get("transcript") or {}
        if transcript and transcript.get("scroll_height", 0) <= transcript.get("client_height", 0):
            failures.append({"kind": "state", "surface": "spa-studio",
                             "viewport": "keyboard-390",
                             "detail": "transcript lost its scroll range after the viewport shrink"})
        grab(page, "spa-keyboard-390")
    except Exception as error:
        failures.append({"kind": "state", "surface": "spa-studio",
                         "viewport": "keyboard-390",
                         "detail": "keyboard scenario failed: %s" % str(error)[:200]})
    finally:
        context.close()

    for name, width, height in (("pages-nav-open-375", 375, 812),
                                ("pages-nav-open-1024", 1024, 768)):
        context, page = new_page(width, height, True)
        try:
            page.goto(app_url + "/models", wait_until="domcontentloaded", timeout=options.timeout_ms)
            page.locator("main").first.wait_for(state="visible", timeout=options.timeout_ms)
            page.wait_for_timeout(options.settle_ms)
            page.click("#nav-toggle")
            page.locator("#primary-nav").first.wait_for(state="visible", timeout=options.timeout_ms)
            grab(page, name)
        except Exception as error:
            failures.append({"kind": "state", "surface": "pages-models", "viewport": name,
                             "detail": "server nav did not open: %s" % str(error)[:200]})
        finally:
            context.close()

    for name, width, height, touch in (("spa-focus-1366", 1366, 1024, False),
                                       ("spa-focus-375", 375, 812, True)):
        context, page = new_page(width, height, touch)
        try:
            open_studio(page)
            for _ in range(3):
                page.keyboard.press("Tab")
            page.wait_for_timeout(150)
            grab(page, name)
        finally:
            context.close()

    return states, failures


def run(app_url: str, site_url: str, options, output_dir: Path) -> dict:
    """Measure every selected surface/viewport pair, then capture state evidence."""
    from playwright.sync_api import sync_playwright

    options.app_url = app_url
    options.site_url = site_url
    fail_on = {kind.strip() for kind in options.fail_on.split(",") if kind.strip()}
    surfaces = _selected_surfaces(options)
    if getattr(options, "no_js", False):
        # The SPA is JavaScript-rendered; only the server-rendered shells and the
        # static site have a meaningful no-JS state.
        surfaces = [surface for surface in surfaces if surface.kind in {"pages", "site"}]
    viewports = _selected_viewports(options)
    results: list[dict] = []
    failures: list[dict] = []
    warnings: list[dict] = []

    with sync_playwright() as playwright:
        browser = harness.launch_browser(playwright, headed=options.headed)
        try:
            scripting = not getattr(options, "no_js", False)
            contexts = {
                "fine": browser.new_context(viewport={"width": 1440, "height": 960},
                                            reduced_motion="reduce",
                                            java_script_enabled=scripting),
                "coarse": browser.new_context(viewport={"width": 390, "height": 844},
                                              has_touch=True, reduced_motion="reduce",
                                              java_script_enabled=scripting),
            }
            pages = {}
            observers = {}
            nav_states = {}
            for mode, context in contexts.items():
                page = context.new_page()
                observer = _Observer()
                observer.attach(page)
                pages[mode] = page
                observers[mode] = observer
                nav_states[mode] = {"app_loaded": False}
            started = time.monotonic()
            for viewport in viewports:
                mode = "coarse" if viewport.touch else "fine"
                page = pages[mode]
                observer = observers[mode]
                page.set_viewport_size({"width": viewport.width, "height": viewport.height})
                for surface in surfaces:
                    observer.reset(surface.label)
                    record = _measure_surface(page, surface, viewport, options, output_dir,
                                              observer, nav_states[mode])
                    results.append(record)
                    _classify(record, failures, warnings, fail_on)
                    print("[%6.1fs] %-18s %-22s overflow=%3dpx ready=%s" % (
                        time.monotonic() - started, surface.label, viewport.label,
                        record["overflow_px"], record["ready"]), flush=True)
            skip_states = options.quick or getattr(options, "no_js", False)
            states, state_failures = ([], []) if skip_states else _capture_states(
                browser, app_url, options)
            failures.extend(state_failures)
        finally:
            browser.close()

    return {
        "label": options.label,
        "surfaces": [surface.label for surface in surfaces],
        "viewports": [
            {"label": viewport.label, "width": viewport.width, "height": viewport.height,
             "pointer": viewport.pointer} for viewport in viewports
        ],
        "results": results,
        "failures": failures,
        "warnings": warnings,
        "states": states,
        "screenshots": [record["screenshot"] for record in results if record["screenshot"]],
        "thresholds": {"min_target_px": config.MIN_TARGET_PX,
                       "comfort_target_px": config.COMFORT_TARGET_PX},
        "fail_on": sorted(fail_on),
    }
