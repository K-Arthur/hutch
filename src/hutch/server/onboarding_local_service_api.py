"""Onboarding local-service connection step (slice 05).

Configures Ollama or other local OpenAI-compatible inference servers running on
loopback (localhost / 127.0.0.1). Detects available models, shows size and memory
guidance, and verifies reachability through the server backend.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from starlette.templating import Jinja2Templates

from ..connections import ConnectionBook
from ..models import utcnow
from ..onboarding_store import load_setup, save_connection
from .onboarding_pagekit import flash, form_values, redirect, render, revision
from .security import check_csrf

TEMPLATE_PAGE = "onboarding_local_service.html"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_LMSTUDIO_URL = "http://127.0.0.1:1234/v1"

POPULAR_MODELS = [
    {"name": "llama3.2:1b", "size": "1.3 GB", "ram": "4 GB", "desc": "Lightweight, fastest CPU inference"},
    {"name": "llama3.2:3b", "size": "2.0 GB", "ram": "6 GB", "desc": "Good balance for everyday reasoning"},
    {"name": "llama3.1:8b", "size": "4.7 GB", "ram": "16 GB", "desc": "Strongest general assistant, needs 16GB RAM"},
    {"name": "gemma2:2b", "size": "1.6 GB", "ram": "4 GB", "desc": "Google Gemma 2 compact model"},
]


def probe_local_ollama(base_url: str) -> dict[str, Any]:
    """Check Ollama /api/tags server-side with a short timeout."""
    url = base_url.rstrip("/") + "/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Hutch-Onboarding"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
                return {"reachable": True, "models": models, "error": ""}
    except urllib.error.URLError as exc:
        return {"reachable": False, "models": [], "error": str(exc.reason)}
    except Exception as exc:
        return {"reachable": False, "models": [], "error": str(exc)}
    return {"reachable": False, "models": [], "error": "Unknown probe failure"}


def probe_local_openai(base_url: str) -> dict[str, Any]:
    """Check OpenAI-compatible /v1/models or /models server-side."""
    url = base_url.rstrip("/") + ("/models" if base_url.rstrip("/").endswith("/v1") else "/v1/models")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Hutch-Onboarding"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
                return {"reachable": True, "models": models, "error": ""}
    except urllib.error.URLError as exc:
        return {"reachable": False, "models": [], "error": str(exc.reason)}
    except Exception as exc:
        return {"reachable": False, "models": [], "error": str(exc)}
    return {"reachable": False, "models": [], "error": "Unknown probe failure"}


def install_local_service_routes(app: FastAPI, *, store: Any, config: Any, templates: Jinja2Templates) -> None:
    """Install routes for local service setup (Ollama, LM Studio)."""

    @app.get("/onboarding/local-service", response_class=HTMLResponse, include_in_schema=False)
    def onboarding_local_service(request: Request):
        load = load_setup(store)
        if load.kind != "present" or not load.setup or not load.setup.request_text:
            return redirect("/onboarding", error="Write your request first.")
        setup = load.setup
        if setup.route_kind != "local_service":
            return redirect("/onboarding/ai-service", error="Choose the Local Model Service route first.")

        base_url = request.query_params.get("url", DEFAULT_OLLAMA_URL).strip()
        probe = probe_local_ollama(base_url)
        if not probe["reachable"]:
            probe = probe_local_openai(base_url)

        fields = {
            "step_index": 3,
            "step_total": 5,
            "step_label": "connect local service",
            "request_text": setup.request_text,
            "revision": setup.revision,
            "url": base_url,
            "probe": probe,
            "popular_models": POPULAR_MODELS,
            "state": "setup.local_service",
        }
        return render(templates, config, request, fields, template=TEMPLATE_PAGE)

    @app.post("/onboarding/local-service", include_in_schema=False)
    async def onboarding_local_service_submit(request: Request):
        form = await form_values(request)
        if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
            return redirect("/onboarding/local-service", error="Session token was invalid.")

        load = load_setup(store)
        if load.kind != "present" or not load.setup:
            return redirect("/onboarding", error="Write your request first.")
        setup = load.setup

        rev = revision(form.get("revision", ""))
        if rev is None or rev != setup.revision:
            return redirect("/onboarding/local-service", error="This setup was updated in another window.")

        raw_url = form.get("url", "").strip() or DEFAULT_OLLAMA_URL
        if not (raw_url.startswith("http://127.0.0.1") or raw_url.startswith("http://localhost")):
            return redirect(f"/onboarding/local-service?url={raw_url}",
                            error="Local model endpoints must use a loopback address (127.0.0.1 or localhost).")

        book = ConnectionBook(config.state_dir)
        conn_name = "local-service"
        
        # Remove old connection if reconfiguring with a new endpoint
        if conn_name in book.names():
            book.remove(conn_name)
            
        try:
            # Add custom OpenAI-compatible connection pointing to the local service
            book.add("custom-openai", conn_name, title="Local Model Service", base_url=raw_url)
        except ValueError as exc:
            return redirect(f"/onboarding/local-service?url={raw_url}", error=str(exc))

        # Local routes do not require secret keys, but we store a dummy local token
        book.set_key(conn_name, "local-key")

        now = utcnow()
        save_connection(store, expected_revision=setup.revision, connection_name=conn_name, now=now)

        from .onboarding_readiness_api import _start_probe_async
        _start_probe_async(book, conn_name)

        return redirect("/onboarding/connection", notice=f"Saved {conn_name} at {raw_url}.")
