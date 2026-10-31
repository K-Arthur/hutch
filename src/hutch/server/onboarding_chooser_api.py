"""Onboarding slice 02: the in-context AI-service chooser page (HTML only).

Orchestration and rendering only. Route decisions live in
hutch.onboarding_choices; persistence lives in hutch.onboarding_store.save_route;
schemas/record fields live in hutch.onboarding. No provider or localhost call is
made from this page or from the browser: the recommendation is static and is
labelled as such until slice 03 replaces it with a detected/verified route.

Every mutation is a plain HTML form POST gated by the shared double-submit CSRF
check; route_kind is validated against the server-side allowlist. The route
inventory records both paths with a None capability, so the existing
remote-access middleware refuses paired phones.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response

from ..models import utcnow
from ..onboarding import default_setup
from ..onboarding_choices import (
    RECOMMENDED_ROUTE,
    ROUTE_KINDS,
    ROUTE_LABELS,
    STATE_AI_SERVICE_CHOOSE,
    STATE_AI_SERVICE_CHOSEN,
    STATE_AI_SERVICE_CONFLICT,
    STATE_AI_SERVICE_INVALID,
    STATE_AI_SERVICE_NO_REQUEST,
    STATE_AI_SERVICE_STALE,
    ChooserView,
    choose_route,
    chooser_view,
)
from ..onboarding_store import load_setup, save_route
from .onboarding_pagekit import (
    form_values,
    redirect,
    render,
    revision,
)
from .security import check_csrf

CHOOSER_TEMPLATE = "onboarding_ai_service.html"
ROUTE_TARGETS = {
    "hosted_key": "/onboarding/hosted-key",
    "local_service": "/onboarding/local-service",
    "opencode": "/onboarding/opencode",
}
STEP_LABEL = "AI service"
STATE_FORBIDDEN = "auth.csrf_rejected"

STALE_LABELS = {
    "newer_contract": "the setup was saved by a newer version of Hutch",
    "contract_version": "the setup format changed",
    "requirements_version": "the setup requirements changed",
    "unknown_step": "the saved step is no longer part of the setup",
    "route_removed": "the AI service route saved earlier is no longer offered",
    "expired": "the saved setup needs refreshing",
}


def _stale_labels(view: ChooserView) -> list[str]:
    return [STALE_LABELS.get(reason, "the saved setup changed") for reason in view.stale_reasons]


def _chooser_fields(view: ChooserView, state: str, **overrides) -> dict:
    """Fields shared by every chooser state, derived from one pure chooser view."""
    fields = {
        "state": state,
        "options": view.options,
        "recommended": view.recommended,
        "recommended_qualifier": view.recommended_qualifier,
        "selected_route": view.selected_route,
        "selected_label": view.selected_label,
        "submitted_route": view.selected_route or "",
        "request_text": view.request_text,
        "revision": view.revision,
        "step_index": view.step_index,
        "step_total": view.required_total,
        "step_label": STEP_LABEL,
        "can_choose": view.can_choose,
        "stale_reasons": _stale_labels(view),
        "newer_version": view.newer_version,
        "expired": view.expired,
        "changing": False,
        "conflict_saved_label": "",
        "conflict_submitted_label": "",
        "continue_target": overrides.get("continue_target") or ROUTE_TARGETS.get(view.selected_route, "/onboarding/connection"),
        "error_summary": "",
        "field_error": "",
    }
    fields.update(overrides)
    return fields


def _render_chooser(templates, config, request: Request, fields: dict, *,
                    status_code: int = 200) -> Response:
    return render(templates, config, request, fields,
                  template=CHOOSER_TEMPLATE, status_code=status_code)


def _view_for(store) -> ChooserView:
    """Current chooser projection; a blank default stands in for an absent record."""
    load = load_setup(store)
    setup = load.setup if load.setup is not None else default_setup(utcnow())
    return chooser_view(setup, now=utcnow())


def _chooser_page_response(store, templates, config, request: Request) -> Response:
    load = load_setup(store)
    if load.kind == "damaged":
        return redirect(error="The saved setup on this machine is unreadable. Nothing was changed.")
    if load.setup is None:
        return redirect(error="Write your request first.")
    view = chooser_view(load.setup, now=utcnow())
    if view.state == STATE_AI_SERVICE_NO_REQUEST:
        return redirect(error="Write your request first.")
    state = view.state
    changing = state == STATE_AI_SERVICE_CHOSEN and request.query_params.get("change") == "1"
    if changing:
        state = STATE_AI_SERVICE_CHOOSE
    return _render_chooser(templates, config, request,
                           _chooser_fields(view, state, changing=changing))


def _invalid_fields(view: ChooserView, submitted: str, message: str) -> dict:
    """Fixable input: keep the form, the submitted route and the current revision."""
    selected = submitted if submitted in ROUTE_KINDS else view.selected_route
    fields = _chooser_fields(view, STATE_AI_SERVICE_INVALID,
                             can_choose=True, selected_route=selected,
                             submitted_route=selected or "",
                             error_summary="There is a problem", field_error=message)
    return fields


def _forbidden_fields(view: ChooserView, submitted: str) -> dict:
    selected = submitted if submitted in ROUTE_KINDS else ""
    return _chooser_fields(view, STATE_FORBIDDEN, can_choose=False,
                           submitted_route=selected)


def _conflict_fields(view: ChooserView, submitted: str) -> dict:
    return _chooser_fields(
        view, STATE_AI_SERVICE_CONFLICT, can_choose=False,
        submitted_route=submitted if submitted in ROUTE_KINDS else "",
        conflict_saved_label=view.selected_label or "No route saved yet",
        conflict_submitted_label=ROUTE_LABELS.get(submitted, "No valid route submitted"),
        error_summary="This setup changed in another window",
    )


async def _chooser_submit_response(store, templates, config, request: Request) -> Response:
    form = await form_values(request)
    submitted = str(form.get("route_kind", "") or "").strip()
    if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
        return _render_chooser(templates, config, request,
                               _forbidden_fields(_view_for(store), submitted), status_code=403)
    submitted_revision = revision(form.get("revision", ""))
    if submitted_revision is None:
        fields = _invalid_fields(_view_for(store), submitted,
                                 "This form was out of date. Choose a route again.")
        return _render_chooser(templates, config, request, fields, status_code=422)
    result = save_route(store, expected_revision=submitted_revision,
                        route_kind=submitted, now=utcnow())
    if result.kind in ("chosen", "replayed"):
        notice = "Route selected." if result.kind == "chosen" else "Route already selected - nothing changed."
        return redirect("/onboarding/ai-service", notice=notice)
    if result.kind == "no_request":
        return redirect(error="Write your request first.")
    if result.kind == "invalid":
        fields = _invalid_fields(_view_for(store), submitted, result.reason)
        return _render_chooser(templates, config, request, fields, status_code=422)
    if result.kind == "conflict" and result.setup is not None:
        view = chooser_view(result.setup, now=utcnow())
        return _render_chooser(templates, config, request,
                               _conflict_fields(view, submitted), status_code=409)
    if result.setup is not None:
        view = chooser_view(result.setup, now=utcnow())
        return _render_chooser(templates, config, request,
                               _chooser_fields(view, STATE_AI_SERVICE_STALE, can_choose=False),
                               status_code=409)
    return redirect(error="The saved setup on this machine is unreadable. Nothing was changed.")


def install_chooser_routes(app: FastAPI, *, store, config, templates) -> None:
    """Install the owner-only AI-service chooser on the shared onboarding installer."""

    @app.get("/onboarding/ai-service", response_class=HTMLResponse, include_in_schema=False)
    def onboarding_ai_service(request: Request):
        return _chooser_page_response(store, templates, config, request)

    @app.post("/onboarding/ai-service/choose", include_in_schema=False)
    async def onboarding_ai_service_choose(request: Request):
        return await _chooser_submit_response(store, templates, config, request)
