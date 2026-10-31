"""Onboarding slice 08: First request execution and human-in-the-loop approval intro.

Allows the owner to review their carried request, introduces Hutch's local-first
and human-in-the-loop approval model, executes the real first request via the
engine, and guides the owner to their dashboard or live run stream.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from ..models import utcnow
from ..onboarding_store import load_setup, save_first_request_completion
from .onboarding_pagekit import (
    TEMPLATE_DIR,
    flash as _flash,
    form_values as _form_values,
    redirect as _redirect,
    revision as _revision,
)
from .security import check_csrf


def _build_context(
    setup,
    bot,
    *,
    run=None,
    submitted: bool = False,
    error: str = "",
) -> dict:
    req_text = setup.request_text if setup else ""
    return {
        "step_index": 5,
        "step_total": 5,
        "step_label": "First Request",
        "request_text": req_text,
        "revision": setup.revision if setup else 0,
        "bot": bot,
        "run": run,
        "submitted": submitted,
        "field_error": error,
        "error_summary": "Please fix the error below" if error else "",
        "first_request_completed": bool(setup.first_request_completed_at) if setup else False,
    }


def install_first_request_routes(
    app: FastAPI,
    *,
    store: Any,
    config: Any,
    templates: Jinja2Templates,
) -> None:
    @app.get("/onboarding/first-request", response_class=HTMLResponse, include_in_schema=False)
    def first_request_get(request: Request):
        loaded = load_setup(store)
        if loaded.kind != "present" or not loaded.setup:
            return RedirectResponse("/onboarding", status_code=303)
        setup = loaded.setup
        if not setup.request_text.strip():
            return RedirectResponse("/onboarding", status_code=303)

        bot = None
        if setup.assistant_id:
            bot = store.get_bot(setup.assistant_id)
        if bot is None:
            # Fallback to looking up the most recent bot or redirecting to assistant setup
            bots = store.list_bots() if hasattr(store, "list_bots") else []
            if bots:
                bot = bots[0]
            else:
                return RedirectResponse("/onboarding/assistant", status_code=303)

        run_id = request.query_params.get("run_id")
        run = store.get_run(run_id) if run_id and hasattr(store, "get_run") else None
        submitted = request.query_params.get("submitted") == "1" or run is not None

        ctx = _build_context(setup, bot, run=run, submitted=submitted)
        ctx["csrf"] = getattr(request.state, "csrf", "")
        return templates.TemplateResponse(request, "onboarding_first_request.html", ctx)

    @app.post("/onboarding/first-request/run", response_class=HTMLResponse, include_in_schema=False)
    async def first_request_post(request: Request):
        form = await _form_values(request)
        if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
            return Response("CSRF check failed", status_code=403)

        loaded = load_setup(store)
        if loaded.kind != "present" or not loaded.setup:
            return RedirectResponse("/onboarding", status_code=303)

        setup = loaded.setup
        rev = _revision(form.get("revision", ""))
        bot = None
        if setup.assistant_id:
            bot = store.get_bot(setup.assistant_id)
        if bot is None:
            bots = store.list_bots() if hasattr(store, "list_bots") else []
            if bots:
                bot = bots[0]
            else:
                return RedirectResponse("/onboarding/assistant", status_code=303)

        prompt = (form.get("request") or setup.request_text).strip()
        if not prompt:
            ctx = _build_context(setup, bot, error="Please enter a task or request to run.")
            ctx["csrf"] = getattr(request.state, "csrf", "")
            return templates.TemplateResponse(request, "onboarding_first_request.html", ctx, status_code=422)

        engine = getattr(app.state, "engine", None)
        run_id = ""
        if engine is not None and hasattr(engine, "submit"):
            run = engine.submit(bot, prompt, origin="onboarding")
            run_id = run.id

        save_first_request_completion(
            store,
            expected_revision=setup.revision if rev is None else rev,
            now=utcnow(),
        )

        if run_id:
            return RedirectResponse(f"/onboarding/first-request?run_id={run_id}&submitted=1", status_code=303)
        return RedirectResponse("/onboarding/first-request?submitted=1", status_code=303)
