"""Onboarding slice 01: the dedicated request step with server-owned resume.

Orchestration and rendering only. Domain decisions live in hutch.onboarding;
persistence lives in hutch.onboarding_store; shared page plumbing lives in
onboarding_pagekit. This module translates form/record outcomes into explicit
HTML states; it makes no provider or network call and never trusts a browser
draft. The AI-service chooser step lives in onboarding_chooser_api.py.

Every mutation is a plain HTML form POST gated by the shared double-submit CSRF
check. The route inventory records these paths with a None capability, so the
existing remote-access middleware refuses paired phones.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from starlette.templating import Jinja2Templates

from ..models import utcnow
from ..onboarding import ResumeView, empty_view, resume_view
from ..onboarding_store import load_setup, reset_setup, save_request
from .onboarding_chooser_api import install_chooser_routes
from .onboarding_pagekit import (
    TEMPLATE_DIR,
    flash as _flash,
    form_values as _form_values,
    local_clock as _local_clock,
    redirect as _redirect,
    render as _render,
    revision as _revision,
)
from .security import check_csrf

# The chooser is the next step; slices 04-06 add the real connection steps after it.
CONTINUE_TARGET = "/onboarding/ai-service"

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
        "continue_target": CONTINUE_TARGET,
    }


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


def _unsaved_response(store, templates: Jinja2Templates, config, request: Request, result, submitted: str) -> Response:
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
    """Install the owner-only onboarding steps (request + AI-service chooser)."""
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

    install_chooser_routes(app, store=store, config=config, templates=templates)
