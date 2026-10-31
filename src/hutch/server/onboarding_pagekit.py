"""Shared HTTP plumbing for the onboarding step pages.

Rendering, flash-cookie, plain-form parsing and CSRF-adjacent form helpers only:
no step decisions and no persistence. Slice 01 kept these bounded helpers inside
onboarding_api.py; slice 02 adds a second step module, so they move here instead
of being copied or growing pages.py (which is over its frozen budget). Each step
still owns its own orchestration: onboarding_api.py (request) and
onboarding_chooser_api.py (AI-service chooser).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, unquote

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from starlette.templating import Jinja2Templates

from .. import __version__

TEMPLATE_DIR = Path(__file__).parent / "templates"
FLASH, FLASH_ERR = "hutch_flash", "hutch_flash_err"
REQUEST_PAGE = "onboarding.html"


def flash(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Read and decode the one-shot flash cookies, if present."""
    notice, error = request.cookies.get(FLASH), request.cookies.get(FLASH_ERR)
    return (unquote(notice) if notice else None, unquote(error) if error else None)


def local_clock(value: str) -> str:
    """Render a stored UTC timestamp in the owner's local time, or blank."""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M %Z").strip()
    except (TypeError, ValueError):
        return ""


def redirect(location: str = "/onboarding", notice: str = "", error: str = "") -> RedirectResponse:
    """POST/GET redirect with a short-lived flash; no user-controlled target."""
    resp = RedirectResponse(location, status_code=303)
    if notice:
        resp.set_cookie(FLASH, quote(notice), max_age=15, path="/", samesite="strict")
    if error:
        resp.set_cookie(FLASH_ERR, quote(error), max_age=15, path="/", samesite="strict")
    return resp


async def form_values(request: Request) -> dict[str, str]:
    """Parse a plain form-encoded body without third-party form middleware."""
    raw = (await request.body()).decode("utf-8", "replace")
    return {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}


def revision(value: str) -> Optional[int]:
    """Parse the revision field, refusing missing/negative/non-integer values."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def render(templates: Jinja2Templates, config, request: Request, fields: dict, *,
           template: str = REQUEST_PAGE, status_code: int = 200) -> Response:
    """Render one onboarding state on the shared chrome-less base page."""
    notice, error = flash(request)
    context = {
        "request": request, "nav": "", "nav_items": [], "chrome": False,
        "csrf": getattr(request.state, "csrf", ""), "pending_count": 0,
        "version": __version__, "state_dir": str(config.state_dir),
        "notice": notice, "error": error,
        **fields,
    }
    resp = templates.TemplateResponse(request, template, context, status_code=status_code)
    # The setup record is owner-local state; never let a shared cache store it.
    resp.headers["Cache-Control"] = "no-store"
    if notice:
        resp.delete_cookie(FLASH, path="/")
    if error:
        resp.delete_cookie(FLASH_ERR, path="/")
    return resp


def fragment(templates: Jinja2Templates, config, request: Request, fields: dict, *,
             template: str, status_code: int = 200) -> Response:
    """Render an HTML fragment without base chrome (e.g. for htmx polling)."""
    context = {
        "request": request,
        "csrf": getattr(request.state, "csrf", ""),
        "version": __version__,
        **fields,
    }
    resp = templates.TemplateResponse(request, template, context, status_code=status_code)
    resp.headers["Cache-Control"] = "no-store"
    return resp

