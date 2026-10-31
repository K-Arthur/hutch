"""Onboarding slice 07: Assistant creation step.

Guides the owner through creating their first assistant based on their carried
request and verified connection. Domain decisions, approvals, and workspace
isolation are explicitly shown to build trust before execution.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from ..connections import ConnectionBook
from ..models import ApprovalMode, Bot, utcnow
from ..onboarding import empty_view, resume_view
from ..onboarding_store import load_setup, save_assistant
from .onboarding_pagekit import (
    TEMPLATE_DIR,
    flash as _flash,
    form_values as _form_values,
    redirect as _redirect,
    render as _render,
    revision as _revision,
)
from .security import check_csrf

DEFAULT_DISPLAY_NAME = "Personal Assistant"
DEFAULT_SLUG = "assistant"
DEFAULT_INSTRUCTIONS = (
    "You are a helpful, transparent personal assistant. Always explain what you "
    "are doing and ask before performing sensitive local operations."
)


def _suggest_slug(request_text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", request_text.strip().lower()).strip("-")
    words = [w for w in cleaned.split("-") if w and len(w) > 2]
    if words:
        slug = "-".join(words[:3])
        if len(slug) <= 30:
            return slug
    return DEFAULT_SLUG


def _suggest_models_for_connection(conn_name: str) -> list[dict[str, str]]:
    cn = conn_name.lower()
    if "opencode" in cn:
        return [
            {"id": "opencode/opencode-go/beam-free", "label": "OpenCode Beam Free (Zero cost)", "recommended": "true"},
            {"id": "opencode/console-xiaomi/mimo-v2.6-flash", "label": "Mimo Flash (Fast)", "recommended": "false"},
        ]
    if "ollama" in cn:
        return [
            {"id": "ollama/llama3.2:latest", "label": "Ollama Llama 3.2 (Local)", "recommended": "true"},
            {"id": "ollama/qwen2.5-coder:latest", "label": "Ollama Qwen 2.5 Coder (Local)", "recommended": "false"},
        ]
    if "anthropic" in cn:
        return [
            {"id": "anthropic/claude-3-5-sonnet", "label": "Claude 3.5 Sonnet", "recommended": "true"},
            {"id": "anthropic/claude-3-5-haiku", "label": "Claude 3.5 Haiku", "recommended": "false"},
        ]
    return [
        {"id": f"{conn_name}/gpt-4o-mini" if conn_name else "openai/gpt-4o-mini", "label": "GPT-4o mini (Balanced)", "recommended": "true"},
        {"id": f"{conn_name}/gpt-4o" if conn_name else "openai/gpt-4o", "label": "GPT-4o (High capability)", "recommended": "false"},
    ]


def _build_context(setup, *, error: str = "", submitted_name: str = "", submitted_display: str = "") -> dict:
    req_text = setup.request_text if setup else ""
    slug = submitted_name or _suggest_slug(req_text)
    display = submitted_display or DEFAULT_DISPLAY_NAME
    conn = setup.connection_name if setup else "local"
    models = _suggest_models_for_connection(conn)
    return {
        "step_index": 4,
        "step_total": 5,
        "step_label": "Create Assistant",
        "request_text": req_text,
        "revision": setup.revision if setup else 0,
        "name": slug,
        "display_name": display,
        "connection_name": conn,
        "models": models,
        "default_model": models[0]["id"] if models else "",
        "instructions": DEFAULT_INSTRUCTIONS,
        "approval_mode": "ask",
        "workspace_mode": "fresh",
        "field_error": error,
        "error_summary": "Please fix the error below" if error else "",
    }


def install_assistant_routes(app: FastAPI, *, store: Any, config: Any, templates: Jinja2Templates) -> None:
    @app.get("/onboarding/assistant", response_class=HTMLResponse, include_in_schema=False)
    def assistant_get(request: Request):
        loaded = load_setup(store)
        if loaded.kind != "present" or not loaded.setup or not loaded.setup.request_text.strip():
            return RedirectResponse("/onboarding", status_code=303)
        ctx = _build_context(loaded.setup)
        ctx["csrf"] = getattr(request.state, "csrf", "")
        return templates.TemplateResponse(request, "onboarding_assistant.html", ctx)

    @app.post("/onboarding/assistant", response_class=HTMLResponse, include_in_schema=False)
    async def assistant_post(request: Request):
        form = await _form_values(request)
        if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
            return Response("CSRF check failed", status_code=403)

        loaded = load_setup(store)
        if loaded.kind != "present" or not loaded.setup:
            return RedirectResponse("/onboarding", status_code=303)

        setup = loaded.setup
        rev = _revision(form.get("revision", ""))
        name = (form.get("name") or "").strip().lower()
        name = re.sub(r"[^a-z0-9_-]+", "-", name).strip("-")
        display_name = (form.get("display_name") or "").strip() or DEFAULT_DISPLAY_NAME
        model = (form.get("model") or "").strip()
        instructions = (form.get("instructions") or "").strip() or DEFAULT_INSTRUCTIONS

        if not name:
            ctx = _build_context(setup, error="Choose a short identifier for your assistant (letters and numbers only).",
                                 submitted_name=name, submitted_display=display_name)
            ctx["csrf"] = getattr(request.state, "csrf", "")
            return templates.TemplateResponse(request, "onboarding_assistant.html", ctx, status_code=422)

        existing = store.get_bot(name)
        if existing is not None:
            ctx = _build_context(setup, error=f"An assistant named '{name}' already exists. Choose a different name.",
                                 submitted_name=name, submitted_display=display_name)
            ctx["csrf"] = getattr(request.state, "csrf", "")
            return templates.TemplateResponse(request, "onboarding_assistant.html", ctx, status_code=409)

        bot = Bot(
            name=name,
            display_name=display_name,
            instructions=instructions,
            model=model or (setup.connection_name or "builtin"),
            approval_mode=ApprovalMode.ask,
            workspace_mode="fresh",
        )
        created = store.create_bot(bot)
        save_res = save_assistant(store, expected_revision=setup.revision if rev is None else rev,
                                  assistant_id=created.id, now=utcnow())
        if save_res.kind == "conflict":
            ctx = _build_context(save_res.setup or setup, error="The setup changed in another window.",
                                 submitted_name=name, submitted_display=display_name)
            ctx["csrf"] = getattr(request.state, "csrf", "")
            return templates.TemplateResponse(request, "onboarding_assistant.html", ctx, status_code=409)

        return RedirectResponse("/onboarding/first-request", status_code=303)
