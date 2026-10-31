"""Onboarding OpenCode connection step (slice 06).

Detects local OpenCode CLI installation, available login sessions, and supported
models (including free tiers such as opencode-go/beam-free).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from starlette.templating import Jinja2Templates

from ..connections import ConnectionBook
from ..connections_service import (
    acknowledge_terms,
    normalise_and_validate_key,
    store_key,
)
from ..models import utcnow
from ..onboarding_store import load_setup, save_connection
from .onboarding_pagekit import flash, form_values, redirect, render, revision
from .security import check_csrf

TEMPLATE_PAGE = "onboarding_opencode.html"


def find_opencode_binary() -> Optional[str]:
    """Locate opencode binary in standard locations or PATH."""
    standard_paths = [
        os.path.expanduser("~/.opencode/bin/opencode"),
        os.path.expanduser("~/.local/bin/opencode"),
        "/usr/local/bin/opencode",
    ]
    for p in standard_paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("opencode")


def check_opencode_status() -> dict[str, Any]:
    """Probe OpenCode CLI installation and available models."""
    binary = find_opencode_binary()
    if not binary:
        return {
            "installed": False,
            "binary_path": "",
            "models": [],
            "error": "OpenCode CLI is not installed on this computer.",
        }
    
    try:
        proc = subprocess.run([binary, "models"], capture_output=True, text=True, timeout=5.0)
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        # Filter for models (including free tiers like opencode-go/beam-free)
        return {
            "installed": True,
            "binary_path": binary,
            "models": lines[:20],
            "error": "" if lines else (proc.stderr.strip() or "No models found or authentication required."),
        }
    except Exception as exc:
        return {
            "installed": True,
            "binary_path": binary,
            "models": [],
            "error": f"Failed to query OpenCode CLI: {exc}",
        }


def install_opencode_routes(app: FastAPI, *, store: Any, config: Any, templates: Jinja2Templates) -> None:
    """Install routes for OpenCode connection step."""

    @app.get("/onboarding/opencode", response_class=HTMLResponse, include_in_schema=False)
    def onboarding_opencode(request: Request):
        load = load_setup(store)
        if load.kind != "present" or not load.setup or not load.setup.request_text:
            return redirect("/onboarding", error="Write your request first.")
        setup = load.setup
        if setup.route_kind != "opencode":
            return redirect("/onboarding/ai-service", error="Choose OpenCode route first.")

        status = check_opencode_status()
        fields = {
            "step_index": 3,
            "step_total": 5,
            "step_label": "connect opencode",
            "request_text": setup.request_text,
            "revision": setup.revision,
            "status": status,
            "state": "setup.opencode",
        }
        return render(templates, config, request, fields, template=TEMPLATE_PAGE)

    @app.post("/onboarding/opencode", include_in_schema=False)
    async def onboarding_opencode_submit(request: Request):
        form = await form_values(request)
        if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
            return redirect("/onboarding/opencode", error="Session token was invalid.")

        load = load_setup(store)
        if load.kind != "present" or not load.setup:
            return redirect("/onboarding", error="Write your request first.")
        setup = load.setup

        rev = revision(form.get("revision", ""))
        if rev is None or rev != setup.revision:
            return redirect("/onboarding/opencode", error="This setup was updated in another window.")

        book = ConnectionBook(config.state_dir)
        conn_name = "opencode-service"
        
        # Check if user opted for OpenCode Go subscription key or local CLI bridge
        use_key = form.get("use_key") in ("on", "1", "true")
        if use_key:
            raw_key = form.get("key", "").strip()
            terms_agreed = form.get("terms_agree") in ("on", "1", "true")
            if not terms_agreed:
                return redirect("/onboarding/opencode", error="You must agree to OpenCode Go terms to use an API key.")
            
            key_check = normalise_and_validate_key(raw_key)
            if key_check.kind != "ok":
                return redirect("/onboarding/opencode", error=key_check.message)

            if conn_name in book.names():
                book.remove(conn_name)
            try:
                book.add("opencode-go", conn_name)
            except ValueError as exc:
                return redirect("/onboarding/opencode", error=str(exc))
                
            acknowledge_terms(book, store, conn_name, agree=True)
            store_key(book, conn_name, key_check.value)
        else:
            # Local OpenCode runtime bridge
            if conn_name in book.names():
                book.remove(conn_name)
            try:
                # OpenCode Go endpoint or local loopback
                book.add("opencode-go", conn_name)
            except ValueError as exc:
                return redirect("/onboarding/opencode", error=str(exc))
            # Set placeholder key for local CLI delegation
            book.set_key(conn_name, "opencode-local-auth")

        now = utcnow()
        save_connection(store, expected_revision=setup.revision, connection_name=conn_name, now=now)

        from .onboarding_readiness_api import _start_probe_async
        _start_probe_async(book, conn_name)

        return redirect("/onboarding/connection", notice=f"Connected {conn_name}.")
