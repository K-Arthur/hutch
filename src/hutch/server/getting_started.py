"""Contextual Getting Started checklist module.

Derives progress dynamically from persisted store facts (assistants, connections,
runs, schedules) and the onboarding setup record. Never relies on fragile browser
storage and never displays to existing experienced users.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from ..models import utcnow
from ..onboarding_store import dismiss_checklist, load_setup
from .security import check_csrf


def compute_checklist(store: Any) -> dict[str, Any]:
    loaded = load_setup(store)
    setup = loaded.setup if loaded.kind == "present" else None

    bots = store.list_bots() if hasattr(store, "list_bots") else []
    runs = store.list_runs(limit=10) if hasattr(store, "list_runs") else []
    conn_book = store.connections if hasattr(store, "connections") else None
    conns = conn_book.list() if conn_book and hasattr(conn_book, "list") else []

    has_request = bool(setup and setup.request_text.strip())
    has_conn = bool((setup and setup.connection_name) or conns)
    has_assistant = bool(bots)
    has_run = bool(setup and setup.first_request_completed_at) or any(
        getattr(r, "status", None) and str(r.status) in ("completed", "finished", "success") for r in runs
    )
    has_advanced = any(bool(getattr(b, "skills", None) or getattr(b, "schedules", None)) for b in bots)

    # Experienced user detection: multiple bots, runs, or dismissed checklist
    dismissed = bool(setup and setup.checklist_dismissed)
    is_experienced = len(bots) >= 2 or (len(bots) >= 1 and len(runs) >= 3 and not (setup and setup.request_text))

    items = [
        {
            "id": "request",
            "title": "Define your first task",
            "completed": has_request,
            "href": "/onboarding",
            "help": "Set what you want Hutch to help you accomplish.",
        },
        {
            "id": "connection",
            "title": "Connect an AI model route",
            "completed": has_conn,
            "href": "/onboarding/ai-service",
            "help": "Configure OpenCode free models, Ollama loopback, or hosted API keys.",
        },
        {
            "id": "assistant",
            "title": "Set up an assistant",
            "completed": has_assistant,
            "href": "/onboarding/assistant",
            "help": "Assign workspace permissions and default execution boundaries.",
        },
        {
            "id": "first_run",
            "title": "Run a request and review actions",
            "completed": has_run,
            "href": "/onboarding/first-request",
            "help": "Experience human-in-the-loop approvals in action.",
        },
        {
            "id": "advanced",
            "title": "Explore skills and automated tasks",
            "completed": has_advanced,
            "href": "/#/skills",
            "help": "Add specialized agent capabilities or recurrent schedules.",
        },
    ]

    completed_count = sum(1 for item in items if item["completed"])
    total_count = len(items)
    percentage = int((completed_count / total_count) * 100) if total_count else 0
    visible = not dismissed and not is_experienced and (completed_count < total_count)

    return {
        "visible": visible,
        "dismissed": dismissed,
        "completed_count": completed_count,
        "total_count": total_count,
        "percentage": percentage,
        "items": items,
    }


def install_getting_started_routes(app: FastAPI, *, store: Any, config: Any) -> None:
    @app.get("/api/v1/getting-started", include_in_schema=False)
    def getting_started_api(request: Request):
        return JSONResponse(compute_checklist(store))

    @app.post("/api/v1/getting-started/dismiss", include_in_schema=False)
    async def getting_started_dismiss(request: Request):
        # Allow JSON or form post
        csrf_token = request.headers.get("x-csrf-token")
        if not csrf_token:
            try:
                form = await request.form()
                csrf_token = form.get("csrf")
            except Exception:
                pass
        if not check_csrf(request, csrf_token):
            return Response("CSRF check failed", status_code=403)
        dismiss_checklist(store, now=utcnow())
        return JSONResponse({"status": "dismissed"})
