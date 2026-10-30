"""Onboarding slice 01: the dedicated request step with server-owned resume.

Orchestration and rendering only. Domain decisions live in hutch.onboarding;
persistence lives in hutch.onboarding_store. This module translates
form/record outcomes into explicit HTML states; it makes no provider or network
call and never reads or writes a browser draft.

Every mutation is a plain HTML form POST gated by the shared double-submit CSRF
check. The route inventory records these paths with a None capability, so the
existing remote-access middleware refuses paired phones.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, unquote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from .. import __version__
from ..models import utcnow
from ..onboarding import ResumeView, empty_view, resume_view
from ..onboarding_store import load_setup, reset_setup, save_request
from .security import check_csrf

TEMPLATE_DIR = Path(__file__).parent / "templates"
FLASH, FLASH_ERR = "hutch_flash", "hutch_flash_err"
# TEMPORARY: slice 02 replaces this bridge with /onboarding/ai-service.
CONTINUE_TARGET = "/#/connections"

STATE_EMPTY = "setup.empty_no_route"
STATE_SAVED = "setup.draft.saved"
STATE_CURRENT = "setup.resume.current"
STATE_STALE = "setup.resume.stale"
STATE_EXPIRED = "setup.resume.expired"
STATE_CONFLICT = "setup.conflict"
STATE_DAMAGED = "setup.damaged"
STATE_INVALID = "input.invalid"
STATE_FORBIDDEN = "auth.csrf_rejected"
STATE_RESET_BLOCKED = "setup.reset_blocked"

STALE_LABELS = {
    "newer_contract": "the setup was saved by a newer version of Hutch",
    "contract_version": "the setup format changed",
    "requirements_version": "the setup requirements changed",
    "unknown_step": "the saved step is no longer part of the setup",
}


def _flash(request: Request) -> tuple[Optional[str], Optional[str]]:
    notice, error = request.cookies.get(FLASH), request.cookies.get(FLASH_ERR)
    return (unquote(notice) if notice else None, unquote(error) if error else None)


def _local_clock(value: str) -> str:
    """Render a stored UTC timestamp in the owner's local time, or blank."""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M %Z").strip()
    except (TypeError, ValueError):
        return ""


def _redirect(notice: str = "", error: str = "") -> RedirectResponse:
    resp = RedirectResponse("/onboarding", status_code=303)
    if notice:
        resp.set_cookie(FLASH, quote(notice), max_age=15, path="/", samesite="strict")
    if error:
        resp.set_cookie(FLASH_ERR, quote(error), max_age=15, path="/", samesite="strict")
    return resp


async def _form_values(request: Request) -> dict[str, str]:
    raw = (await request.body()).decode("utf-8", "replace")
    return {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}


def _revision(value: str) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _stale_labels(view: ResumeView) -> list[str]:
    return [STALE_LABELS.get(reason, "the saved setup changed") for reason in view.stale_reasons]


def _view_fields(view: ResumeView, state: str) -> dict:
    """Fields shared by every rendered state, derived from one resume view."""
    return {
        "state": state,
        "request_text": view.request_text,
        "revision": view.revision,
        "editable": False,
        "editing": False,
        "field_error": "",
        "error_summary": "",
        "resume_message": "",
        "saved_at_local": _local_clock(view.saved_at) if view.revision else "",
        "conflict_saved_text": "",
        "stale_reasons": [],
        "newer_version": view.newer_version,
        "step_index": view.step_index,
        "step_total": view.required_total,
        "step_label": "your request",
    }


def _render(templates: Jinja2Templates, config, request: Request, fields: dict,
            *, status_code: int = 200) -> Response:
    """Render one request-step state on the shared chrome-less base page."""
    notice, error = _flash(request)
    context = {
        "request": request, "nav": "", "nav_items": [], "chrome": False,
        "csrf": getattr(request.state, "csrf", ""), "pending_count": 0,
        "version": __version__, "state_dir": str(config.state_dir),
        "notice": notice, "error": error, "continue_target": CONTINUE_TARGET,
        **fields,
    }
    resp = templates.TemplateResponse(request, "onboarding.html", context, status_code=status_code)
    # The setup record is owner-local state; never let a shared cache store it.
    resp.headers["Cache-Control"] = "no-store"
    if notice:
        resp.delete_cookie(FLASH, path="/")
    if error:
        resp.delete_cookie(FLASH_ERR, path="/")
    return resp


def _forbidden(templates: Jinja2Templates, config, request: Request, submitted: str) -> Response:
    fields = _view_fields(empty_view(), STATE_FORBIDDEN)
    fields.update(request_text=submitted)
    return _render(templates, config, request, fields, status_code=403)


def _fields_for_page(load, notice: Optional[str], edit: bool) -> dict:
    """Build the render context for a GET; every state is named explicitly."""
    if load.kind == "damaged":
        return _view_fields(empty_view(), STATE_DAMAGED)
    if load.kind == "absent":
        fields = _view_fields(empty_view(), STATE_EMPTY)
        fields.update(editable=True)
        return fields
    view = resume_view(load.setup, now=utcnow())
    if view.newer_version:
        return _view_fields(view, STATE_STALE)
    if view.state == STATE_STALE:
        fields = _view_fields(view, STATE_STALE)
        fields["stale_reasons"] = _stale_labels(view)
        return fields
    if view.state == STATE_EXPIRED:
        return _view_fields(view, STATE_EXPIRED)
    if view.state == STATE_EMPTY:
        fields = _view_fields(view, STATE_EMPTY)
        fields.update(editable=True)
        return fields
    state = STATE_SAVED if notice else STATE_CURRENT
    fields = _view_fields(view, state)
    if edit:
        fields.update(editable=True, editing=True)
    elif not notice:
        saved = fields["saved_at_local"]
        fields["resume_message"] = (
            "You left off here. Hutch resumed the request you saved on this machine"
            + (f" on {saved}." if saved else ".")
        )
    return fields


def _editable_fields(load, *, submitted: str, message: str) -> dict:
    """Build the focused form context for a fixable input problem.

    The form keeps the submitted text and the current stored revision so the
    owner can correct and resubmit without losing work or overwriting a newer
    record by surprise.
    """
    if load.kind == "present" and load.setup is not None:
        fields = _view_fields(resume_view(load.setup, now=utcnow()), STATE_INVALID)
        fields["revision"] = load.setup.revision
        # A blank stored record is still the first-run form, not an edit.
        fields["editing"] = bool(load.setup.request_text.strip())
    else:
        fields = _view_fields(empty_view(), STATE_INVALID)
        fields["editing"] = False
    fields.update(request_text=submitted, editable=True,
                  error_summary="There is a problem", field_error=message)
    return fields


def _reset_allowed(load) -> bool:
    """Start over is offered only when the saved record cannot continue as-is.

    The UI renders the reset form from damaged/stale/expired/newer-version
    states, but a stray POST must not wipe a current saved request either.
    """
    if load.kind != "present" or load.setup is None:
        return True
    if not load.setup.request_text.strip():
        return True
    view = resume_view(load.setup, now=utcnow())
    return view.newer_version or view.state in (STATE_STALE, STATE_EXPIRED)


def _reset_blocked_fields(load) -> dict:
    view = resume_view(load.setup, now=utcnow()) if load.setup is not None else empty_view()
    return _view_fields(view, STATE_RESET_BLOCKED)


def _page_response(store, templates: Jinja2Templates, config, request: Request) -> Response:
    notice, _ = _flash(request)
    edit = request.query_params.get("edit") == "1"
    return _render(templates, config, request, _fields_for_page(load_setup(store), notice, edit))


async def _request_response(store, templates: Jinja2Templates, config, request: Request) -> Response:
    form = await _form_values(request)
    submitted = form.get("request", "")
    if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
        return _forbidden(templates, config, request, submitted)
    revision = _revision(form.get("revision", ""))
    if revision is None:
        fields = _editable_fields(load_setup(store), submitted=submitted,
                                  message="This form was out of date. Check your request and save it again.")
        return _render(templates, config, request, fields, status_code=422)
    result = save_request(store, expected_revision=revision, request_text=submitted, now=utcnow())
    if result.kind in ("accepted", "replayed"):
        notice = "Saved on this machine." if result.kind == "accepted" else "Already saved - nothing changed."
        return _redirect(notice=notice)
    return _unsaved_response(store, templates, config, request, result, submitted)


def _unsaved_response(store, templates, config, request: Request, result, submitted: str) -> Response:
    if result.kind == "invalid":
        fields = _editable_fields(load_setup(store), submitted=submitted, message=result.reason)
        return _render(templates, config, request, fields, status_code=422)
    if result.kind == "stale":
        fields = _view_fields(resume_view(result.setup, now=utcnow()), STATE_CONFLICT)
        fields.update(conflict_saved_text=result.setup.request_text, request_text=submitted,
                      revision=result.setup.revision,
                      error_summary="This setup changed in another window")
        return _render(templates, config, request, fields, status_code=409)
    if result.kind == "newer_version":
        fields = _view_fields(resume_view(result.setup, now=utcnow()), STATE_STALE)
        return _render(templates, config, request, fields, status_code=409)
    return _render(templates, config, request, _view_fields(empty_view(), STATE_DAMAGED), status_code=409)


async def _reset_response(store, templates: Jinja2Templates, config, request: Request) -> Response:
    form = await _form_values(request)
    if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
        return _forbidden(templates, config, request, "")
    load = load_setup(store)
    if not _reset_allowed(load):
        return _render(templates, config, request, _reset_blocked_fields(load), status_code=409)
    reset_setup(store, utcnow())
    return _redirect(notice="Started over: the saved setup was replaced with a blank one.")


def install_onboarding_routes(app: FastAPI) -> None:
    """Install the owner-only onboarding request step (slice 01)."""
    store, config = app.state.store, app.state.config
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    @app.get("/onboarding", response_class=HTMLResponse, include_in_schema=False)
    def onboarding_page(request: Request):
        return _page_response(store, templates, config, request)

    @app.post("/onboarding/request", include_in_schema=False)
    async def onboarding_request(request: Request):
        return await _request_response(store, templates, config, request)

    @app.post("/onboarding/reset", include_in_schema=False)
    async def onboarding_reset(request: Request):
        return await _reset_response(store, templates, config, request)
