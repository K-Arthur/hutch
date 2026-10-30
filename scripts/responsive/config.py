"""Viewport matrix, surface catalogue and thresholds for responsive validation.

This module is the single source of truth for what responsive covers in this
repository: which surfaces are measured, at which viewports, with which pointer
mode, and where evidence is written. Task files under docs/responsive/tasks use
the labels defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "docs" / "responsive" / "screenshots"

MIN_TARGET_PX = 24
COMFORT_TARGET_PX = 44
SETTLE_MS = 450


@dataclass(frozen=True)
class Viewport:
    label: str
    width: int
    height: int
    pointer: str  # "fine" (mouse/trackpad) or "coarse" (touch)

    @property
    def touch(self) -> bool:
        return self.pointer == "coarse"


@dataclass(frozen=True)
class Surface:
    label: str
    kind: str  # "app" (SPA), "pages" (server-rendered), "site" (marketing)
    path: str
    ready: str  # selector proving the surface rendered
    note: str = ""


def _viewport(label: str, width: int, height: int, pointer: str) -> Viewport:
    return Viewport(label, width, height, pointer)


# Ordered from the tightest phone to the widest desktop. 1366x1024 is the
# 12.9/13-inch iPad Pro landscape class; 1180x820 is the 13-inch laptop class.
VIEWPORTS: tuple[Viewport, ...] = (
    _viewport("compact-phone-320", 320, 740, "coarse"),
    _viewport("phone-375", 375, 812, "coarse"),
    _viewport("phone-390", 390, 844, "coarse"),
    _viewport("phone-landscape-844", 844, 390, "coarse"),
    _viewport("tablet-portrait-768", 768, 1024, "coarse"),
    _viewport("tablet-landscape-1024", 1024, 768, "coarse"),
    _viewport("laptop-1180", 1180, 820, "fine"),
    _viewport("ipad-13in-1366", 1366, 1024, "coarse"),
    _viewport("desktop-1440", 1440, 960, "fine"),
    _viewport("desktop-wide-1536", 1536, 864, "fine"),
)

# The seeded workspace always exposes the assistant "design-review".
SURFACES: tuple[Surface, ...] = (
    Surface("spa-studio", "app", "/#/chat/design-review", "#chat-prompt",
            "chat transcript and composer"),
    Surface("spa-runs", "app", "/#/runs", "#runs-table-wrap", "densest data table"),
    Surface("spa-tasks", "app", "/#/tasks", ".page-scroll", "task board page"),
    Surface("spa-runtime", "app", "/#/runtime", ".page-scroll", "runtime status page"),
    Surface("spa-settings", "app", "/#/settings", "#workspace-settings-effects",
            "settings forms"),
    Surface("spa-bot-settings", "app", "/#/bot/design-review", "#app-top-context h1",
            "per-assistant settings"),
    Surface("spa-activity", "app", "/#/overview", "#view", "activity feed"),
    # Server-rendered pages. Legacy aliases /overview, /bots, /runs, /connections and
    # /approvals 302-redirect into the SPA hash routes above, so they are not separate
    # surfaces; these Jinja pages are the real server shells (pages.py:246-720).
    Surface("pages-models", "pages", "/models", "main", "model forms and controls"),
    Surface("pages-usage", "pages", "/usage", "main", "usage table and meters"),
    Surface("pages-bot-detail", "pages", "/bots/design-review", "main", "assistant detail page"),
    Surface("pages-login", "pages", "/login", "main", "authentication form"),
    Surface("pages-pair", "pages", "/pair", "main", "device pairing flow"),
    Surface("site-home", "site", "/", ".hero-title", "marketing landing page"),
)

SURFACE_BY_LABEL = {surface.label: surface for surface in SURFACES}
VIEWPORT_BY_LABEL = {viewport.label: viewport for viewport in VIEWPORTS}

# Screenshot policy: three representative surfaces get the full matrix; the
# remaining surfaces get the phone, tablet and 13-inch widths.
FULL_MATRIX_SURFACES = frozenset({"spa-studio", "pages-models", "site-home"})
SECONDARY_SCREENSHOT_VIEWPORTS = frozenset({"phone-375", "tablet-portrait-768", "ipad-13in-1366"})
MARKETING_SCREENSHOT_VIEWPORTS = frozenset({"phone-375", "tablet-portrait-768", "ipad-13in-1366"})
CONTRAST_VIEWPORTS = frozenset({"phone-390", "ipad-13in-1366"})

QUICK_SURFACES = frozenset({"spa-studio", "pages-models", "site-home"})
QUICK_VIEWPORTS = frozenset({"phone-390", "ipad-13in-1366", "desktop-1440"})


def surface_url(surface: Surface, app_url: str, site_url: str) -> str:
    """Resolve the absolute URL a surface should be measured at."""
    if surface.kind == "site":
        return site_url.rstrip("/") + surface.path
    return app_url.rstrip("/") + surface.path


def wants_screenshot(surface: Surface, viewport: Viewport) -> bool:
    """Whether this surface/viewport pair is part of the committed evidence set."""
    if surface.kind == "site":
        return viewport.label in MARKETING_SCREENSHOT_VIEWPORTS
    if surface.label in FULL_MATRIX_SURFACES:
        return True
    return viewport.label in SECONDARY_SCREENSHOT_VIEWPORTS
