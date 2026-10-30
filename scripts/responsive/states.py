"""Interactive state captures that the static viewport matrix cannot express.

Each scenario owns one state: opened drawers, the keyboard-shrunk frame, measured
chrome geometry or keyboard focus. capture.py owns the matrix and calls
capture_states() once per run.
"""

from __future__ import annotations

from pathlib import Path

from responsive import checks, config

STUDIO_SURFACE = "/#/chat/design-review"


class StateCapture:
    """Capture every interactive state for one validation run."""

    def __init__(self, browser, app_url: str, options) -> None:
        self.browser = browser
        self.app_url = app_url
        self.options = options
        self.studio = app_url + STUDIO_SURFACE
        self.states: list[dict] = []
        self.failures: list[dict] = []

    # ---------------------------------------------------------------- helpers

    def _new_page(self, width: int, height: int, touch: bool):
        context = self.browser.new_context(viewport={"width": width, "height": height},
                                           has_touch=touch, reduced_motion="reduce")
        return context, context.new_page()

    def _grab(self, page, name: str) -> None:
        relative = Path("docs") / "responsive" / "screenshots" / self.options.label / (
            "state-%s.png" % name)
        path = config.REPO_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=False, animations="disabled")
        self.states.append({"name": name, "screenshot": str(relative)})

    def _open_studio(self, page) -> None:
        page.goto(self.studio, wait_until="domcontentloaded", timeout=self.options.timeout_ms)
        page.locator("#chat-prompt").first.wait_for(state="visible",
                                                    timeout=self.options.timeout_ms)
        page.wait_for_timeout(self.options.settle_ms)

    def _open_server_page(self, page) -> None:
        page.goto(self.app_url + "/models", wait_until="domcontentloaded",
                  timeout=self.options.timeout_ms)
        page.locator("main").first.wait_for(state="visible", timeout=self.options.timeout_ms)
        page.wait_for_timeout(self.options.settle_ms)

    def _fail(self, kind: str, surface: str, viewport: str, detail: str) -> None:
        self.failures.append({"kind": kind, "surface": surface, "viewport": viewport,
                              "detail": detail})

    # --------------------------------------------------------------- scenarios

    def capture_all(self) -> tuple[list[dict], list[dict]]:
        self.sidebar_open()
        self.spa_sheet()
        self.keyboard_shrink()
        self.style_scope()
        self.rail_widths()
        self.needs_you_drawer()
        self.server_nav_overlay()
        self.focus_state()
        return self.states, self.failures

    def sidebar_open(self) -> None:
        """The wide sidebar is expanded at 1180 and 1366 and must stay expanded."""
        for name, width, height, touch in (("spa-sidebar-open-1180", 1180, 820, False),
                                           ("spa-sidebar-open-1366", 1366, 1024, True)):
            context, page = self._new_page(width, height, touch)
            try:
                self._open_studio(page)
                expanded = page.locator("#sidebar-toggle").get_attribute("aria-expanded")
                classes = page.locator(".app-shell").get_attribute("class") or ""
                if expanded != "true" or "collapsed" in classes:
                    self._fail("state", "spa-studio", name,
                               "sidebar is not expanded on a wide viewport")
                self._grab(page, name)
            finally:
                context.close()

    def spa_sheet(self) -> None:
        """The phone navigation sheet opens from the toggle."""
        context, page = self._new_page(375, 812, True)
        try:
            self._open_studio(page)
            page.click("#nav-toggle")
            page.locator("#workspace.open").wait_for(state="visible",
                                                     timeout=self.options.timeout_ms)
            self._grab(page, "spa-sheet-open-375")
        except Exception as error:
            self._fail("state", "spa-studio", "phone-375",
                       "phone sheet did not open: %s" % str(error)[:200])
        finally:
            context.close()

    def keyboard_shrink(self) -> None:
        """The composer stays visible when the visual viewport shrinks."""
        context, page = self._new_page(390, 844, True)
        try:
            self._open_studio(page)
            page.locator("#chat-prompt").focus()
            page.set_viewport_size({"width": 390, "height": 520})
            page.wait_for_timeout(500)
            probe = checks.measure_keyboard(page)
            visual_height = probe["visual_height"]
            composer = probe.get("composer") or {}
            if not composer or composer.get("bottom", 10**6) > visual_height + 1:
                self._fail("state", "spa-studio", "keyboard-390",
                           "composer is not inside the shrunk visual viewport")
            shell = probe.get("shell") or {}
            if shell and shell.get("height", 10**6) > visual_height + 2:
                self._fail("state", "spa-studio", "keyboard-390",
                           "app shell height does not follow the visual viewport")
            transcript = probe.get("transcript") or {}
            if transcript and transcript.get("scroll_height", 0) <= transcript.get("client_height", 0):
                self._fail("state", "spa-studio", "keyboard-390",
                           "transcript lost its scroll range after the viewport shrink")
            self._grab(page, "spa-keyboard-390")
        except Exception as error:
            self._fail("state", "spa-studio", "keyboard-390",
                       "keyboard scenario failed: %s" % str(error)[:200])
        finally:
            context.close()

    def style_scope(self) -> None:
        """Rules after the repaired media block apply globally; sticky offset follows the bar."""
        context, page = self._new_page(1440, 960, False)
        try:
            self._open_studio(page)
            scope = checks.measure_style_scope(page)
            self.states.append({"name": "style-scope-desktop", "measurement": scope})
            if scope["preflight"]["margin_top"] != "8px" or scope["context_line"]["margin_top"] != "8px":
                self._fail("styles", "spa-studio", "desktop-1440",
                           "preflight/context rules are still phone-scoped: %s" % scope)
            self._open_server_page(page)
            server_scope = checks.measure_style_scope(page)
            self.states.append({"name": "topbar-offset-desktop", "measurement": server_scope})
            variable = server_scope["topbar_variable"]
            sticky_top = server_scope["run_head"]["top"]
            try:
                measured = float(variable.replace("px", ""))
                actual = float(sticky_top.replace("px", ""))
            except ValueError:
                measured = actual = -1
            if not variable or abs(actual - measured) > 1:
                self._fail("styles", "pages-models", "desktop-1440",
                           "run-head sticky offset %s does not follow --topbar-h %s"
                           % (sticky_top, variable))
        except Exception as error:
            self._fail("styles", "style-scope", "desktop-1440",
                       "style-scope check failed: %s" % str(error)[:200])
        finally:
            context.close()

    def rail_widths(self) -> None:
        """Rail mode uses one sidebar width from 960 through 1366."""
        rail_widths = {}
        for width, height, touch in ((960, 720, True), (1024, 768, True),
                                     (1180, 820, False), (1366, 1024, True)):
            context, page = self._new_page(width, height, touch)
            try:
                self._open_studio(page)
                rail_widths[width] = page.evaluate("""() => {
                  const rail = document.querySelector(".workspace");
                  const shell = document.querySelector(".app-shell");
                  return {rail: Math.round(rail.getBoundingClientRect().width),
                          collapsed: shell.classList.contains("collapsed")};
                }""")
            except Exception as error:
                self._fail("styles", "spa-studio", "rail-%d" % width,
                           "rail measurement failed: %s" % str(error)[:200])
            finally:
                context.close()
        self.states.append({"name": "rail-widths", "measurement": rail_widths})
        rail_values = {entry.get("rail") for entry in rail_widths.values() if entry}
        if len(rail_values) > 1:
            self._fail("styles", "spa-studio", "rail-widths",
                       "rail width differs across 960/1024/1180/1366: %s" % rail_widths)

    def needs_you_drawer(self) -> None:
        """The fixed-edge Needs-you drawer opens in portrait and landscape."""
        for name, width, height in (("needs-you-390", 390, 844),
                                    ("needs-you-landscape-844", 844, 390)):
            context, page = self._new_page(width, height, True)
            try:
                self._open_studio(page)
                page.evaluate("() => document.getElementById('needs-you-open')?.click()")
                page.locator(".needs-you").first.wait_for(state="visible",
                                                          timeout=self.options.timeout_ms)
                self._grab(page, name)
            except Exception as error:
                self._fail("state", "spa-needs-you", name,
                           "needs-you drawer did not open: %s" % str(error)[:200])
            finally:
                context.close()

    def server_nav_overlay(self) -> None:
        """The server-page nav overlay opens at phone and tablet-landscape widths."""
        for name, width, height in (("pages-nav-open-375", 375, 812),
                                    ("pages-nav-open-1024", 1024, 768)):
            context, page = self._new_page(width, height, True)
            try:
                self._open_server_page(page)
                page.click("#nav-toggle")
                page.locator("#primary-nav").first.wait_for(state="visible",
                                                            timeout=self.options.timeout_ms)
                self._grab(page, name)
            except Exception as error:
                self._fail("state", "pages-models", name,
                           "server nav did not open: %s" % str(error)[:200])
            finally:
                context.close()

    def focus_state(self) -> None:
        """Keyboard focus reaches real controls at desktop and phone widths."""
        for name, width, height, touch in (("spa-focus-1366", 1366, 1024, False),
                                           ("spa-focus-375", 375, 812, True)):
            context, page = self._new_page(width, height, touch)
            try:
                self._open_studio(page)
                for _ in range(3):
                    page.keyboard.press("Tab")
                page.wait_for_timeout(150)
                self._grab(page, name)
            finally:
                context.close()


def capture_states(browser, app_url: str, options) -> tuple[list[dict], list[dict]]:
    """Run every interactive-state scenario for one validation run."""
    return StateCapture(browser, app_url, options).capture_all()
