"""Onboarding hosted-key connection step (slice 04).

Allows pasting and validating provider API keys, acknowledging terms, and storing
keys safely in private 0600 files.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from starlette.templating import Jinja2Templates

from ..connections import ConnectionBook
from ..connections_service import (
    acknowledge_terms,
    key_source_view,
    normalise_and_validate_key,
    store_key,
    terms_view,
)
from ..models import utcnow
from ..onboarding_store import load_setup, save_connection
from .onboarding_pagekit import flash, form_values, redirect, render, revision
from .security import check_csrf

HOSTED_KEY_TEMPLATES = ("openai-api", "anthropic-api", "openrouter", "opencode-go")
TEMPLATE_PAGE = "onboarding_hosted_key.html"

PROVIDER_NAMES = {
    "openai-api": "OpenAI API",
    "anthropic-api": "Anthropic API",
    "openrouter": "OpenRouter",
    "opencode-go": "OpenCode Go",
}


def _provider_info(book: ConnectionBook, template_id: str) -> dict[str, Any]:
    tpl = book.templates().get(template_id, {})
    terms = tpl.get("terms", {})
    env_name = tpl.get("api_key_env", "")
    import os
    env_set = bool(env_name and os.environ.get(env_name))
    return {
        "id": template_id,
        "name": PROVIDER_NAMES.get(template_id, tpl.get("title", template_id)),
        "title": tpl.get("title", template_id),
        "requires_terms": bool(terms.get("requires_ack")),
        "env_var": env_name,
        "env_set": env_set,
        "get_key_url": tpl.get("get_key_url", ""),
    }


def install_hosted_key_routes(app: FastAPI, *, store: Any, config: Any, templates: Jinja2Templates) -> None:
    """Install routes for the hosted key entry step."""

    @app.get("/onboarding/hosted-key", response_class=HTMLResponse, include_in_schema=False)
    def onboarding_hosted_key(request: Request):
        load = load_setup(store)
        if load.kind != "present" or not load.setup or not load.setup.request_text:
            return redirect("/onboarding", error="Write your request first.")
        setup = load.setup
        if setup.route_kind != "hosted_key":
            return redirect("/onboarding/ai-service", error="Choose the Hosted Key route first.")

        book = ConnectionBook(config.state_dir)
        provider = request.query_params.get("provider", "").strip()
        connection = request.query_params.get("connection", "").strip()

        if provider and provider not in HOSTED_KEY_TEMPLATES:
            return redirect("/onboarding/hosted-key", error=f"Unknown provider '{provider}'.")

        providers = [_provider_info(book, tid) for tid in HOSTED_KEY_TEMPLATES]
        selected = _provider_info(book, provider) if provider else None
        
        terms_data = None
        if selected and selected["requires_terms"]:
            terms_data = book.templates().get(provider, {}).get("terms", {})

        fields = {
            "step_index": 3,
            "step_total": 5,
            "step_label": "connect hosted key",
            "request_text": setup.request_text,
            "revision": setup.revision,
            "provider": provider,
            "providers": providers,
            "selected_provider": selected,
            "connection": connection,
            "terms": terms_data,
            "state": "setup.hosted_key",
        }
        return render(templates, config, request, fields, template=TEMPLATE_PAGE)

    @app.post("/onboarding/hosted-key", include_in_schema=False)
    async def onboarding_hosted_key_submit(request: Request):
        form = await form_values(request)
        if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
            return redirect("/onboarding/hosted-key", error="Session token was invalid.")

        load = load_setup(store)
        if load.kind != "present" or not load.setup:
            return redirect("/onboarding", error="Write your request first.")
        setup = load.setup

        rev = revision(form.get("revision", ""))
        if rev is None or rev != setup.revision:
            return redirect("/onboarding/hosted-key", error="This setup was updated in another window.")

        provider = form.get("provider", "").strip()
        if provider not in HOSTED_KEY_TEMPLATES:
            return redirect("/onboarding/hosted-key", error="Please choose a supported provider.")

        book = ConnectionBook(config.state_dir)
        tpl = book.templates().get(provider, {})
        requires_ack = bool(tpl.get("terms", {}).get("requires_ack"))
        if requires_ack:
            terms_agreed = form.get("terms_agree") in ("on", "1", "true", "yes")
            if not terms_agreed:
                return redirect(f"/onboarding/hosted-key?provider={provider}",
                                error="You must agree to the provider terms to continue.")

        mode = form.get("mode", "key")
        conn_name = form.get("connection", "").strip() or f"{provider}-onboard"
        
        # Create connection if not existing
        if conn_name not in book.names():
            try:
                book.add(provider, conn_name)
            except ValueError as exc:
                return redirect(f"/onboarding/hosted-key?provider={provider}", error=str(exc))

        # Acknowledge terms if required
        if requires_ack:
            acknowledge_terms(book, store, conn_name, agree=True)

        if mode == "key":
            raw_key = form.get("key", "")
            key_check = normalise_and_validate_key(raw_key)
            if key_check.kind == "empty":
                return redirect(f"/onboarding/hosted-key?provider={provider}", error="API key cannot be blank.")
            if key_check.kind == "too_long":
                return redirect(f"/onboarding/hosted-key?provider={provider}", error="API key is too long (max 4096 bytes).")
            if key_check.kind == "malformed":
                return redirect(f"/onboarding/hosted-key?provider={provider}", error="API key contains invalid characters.")

            save_res = store_key(book, conn_name, key_check.value)
            if save_res.kind != "stored":
                return redirect(f"/onboarding/hosted-key?provider={provider}", error=save_res.message)

        now = utcnow()
        save_connection(store, expected_revision=setup.revision, connection_name=conn_name, now=now)
        
        # Trigger readiness probe in background
        from .onboarding_readiness_api import _start_probe_async
        _start_probe_async(book, conn_name)

        return redirect("/onboarding/connection", notice=f"Saved {conn_name} on this machine.")
