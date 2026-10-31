"""Onboarding readiness API and connection shell (slice 03).

Provides server-side readiness checks without any browser-to-provider network calls.
Snapshots are process-local display data and are never persisted in SQLite.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from starlette.templating import Jinja2Templates

from ..connections import ConnectionBook
from ..models import utcnow
from ..onboarding import default_setup
from ..onboarding_store import load_setup
from ..route_readiness import (
    CHECKING,
    GENERATION_COOLDOWN_SECONDS,
    MODE_GENERATION,
    MODE_METADATA,
    PROBE_DEADLINE_SECONDS,
    ProbeResult,
    display_state,
    is_stale,
    metadata_result,
    revalidation_required,
    retry_allowed,
    retry_in_seconds,
)
from .onboarding_pagekit import flash, form_values, fragment, redirect, render
from .security import check_csrf

READINESS_FRAGMENT = "_onboarding_readiness.html"
CONNECTION_SHELL = "onboarding_connection.html"


@dataclass
class SnapshotEntry:
    result: ProbeResult
    attempt: int = 1
    running: bool = False
    started_at: datetime = datetime.now(timezone.utc)
    last_generation_at: Optional[datetime] = None


_SNAPSHOTS: dict[str, SnapshotEntry] = {}
_LOCK = threading.Lock()


def get_snapshot(name: str) -> Optional[SnapshotEntry]:
    with _LOCK:
        return _SNAPSHOTS.get(name)


def set_snapshot(name: str, entry: SnapshotEntry) -> None:
    with _LOCK:
        _SNAPSHOTS[name] = entry


def clear_snapshot(name: str) -> None:
    with _LOCK:
        _SNAPSHOTS.pop(name, None)


def _start_probe_async(book: ConnectionBook, name: str, *, mode: str = MODE_METADATA, model: str = ""):
    now = utcnow()
    with _LOCK:
        entry = _SNAPSHOTS.get(name)
        if entry and entry.running:
            return  # already running
        attempt = (entry.attempt + 1) if (entry and mode == entry.result.mode) else 1
        initial = ProbeResult(
            state=CHECKING, kind="", http_status=None, retry_after=None,
            detail=f"Checking {name}...", models=entry.result.models if entry else (),
            checked_at=now.isoformat(), mode=mode
        )
        last_gen = entry.last_generation_at if entry else None
        _SNAPSHOTS[name] = SnapshotEntry(result=initial, attempt=attempt, running=True,
                                         started_at=now, last_generation_at=last_gen)

    def worker():
        from ..connections_service import probe_connection
        res = probe_connection(book, name, mode=mode, model=model)
        finished_at = utcnow()
        with _LOCK:
            current = _SNAPSHOTS.get(name)
            gen_time = finished_at if mode == MODE_GENERATION else (current.last_generation_at if current else None)
            _SNAPSHOTS[name] = SnapshotEntry(
                result=res, attempt=current.attempt if current else 1,
                running=False, started_at=finished_at, last_generation_at=gen_time
            )

    t = threading.Thread(target=worker, daemon=True)
    t.start()


def install_readiness_routes(app: FastAPI, *, store: Any, config: Any, templates: Jinja2Templates) -> None:
    """Install readiness fragment and connection shell routes."""

    @app.get("/onboarding/readiness", response_class=HTMLResponse, include_in_schema=False)
    def onboarding_readiness(request: Request, target: str = ""):
        book = ConnectionBook(config.state_dir)
        if not target or target not in book.names():
            return fragment(templates, config, request, {
                "state": "provider.invalid_route", "detail": f"Unknown target '{target}'",
                "target": target, "retry_allowed": False, "retry_wait": 0, "models": (),
            }, template=READINESS_FRAGMENT, status_code=404)

        now = utcnow()
        entry = get_snapshot(target)
        if not entry or revalidation_required(entry.result, now):
            _start_probe_async(book, target, mode=MODE_METADATA)
            entry = get_snapshot(target)

        res = entry.result
        disp_state = display_state(res, now) if not entry.running else CHECKING
        wait_secs = retry_in_seconds(res, now)
        elapsed = (now - entry.started_at).total_seconds() if entry.running else 0
        still_waiting = entry.running and elapsed >= 10.0

        fields = {
            "target": target,
            "state": disp_state,
            "canonical_state": res.state,
            "mode": res.mode,
            "detail": res.detail,
            "models": res.models,
            "attempt": entry.attempt,
            "running": entry.running,
            "still_waiting": still_waiting,
            "retry_allowed": retry_allowed(res.state) and not entry.running and wait_secs == 0,
            "retry_wait": wait_secs,
            "deadline": PROBE_DEADLINE_SECONDS,
            "checked_at": res.checked_at,
        }
        return fragment(templates, config, request, fields, template=READINESS_FRAGMENT)

    @app.post("/onboarding/readiness/retry", include_in_schema=False)
    async def onboarding_readiness_retry(request: Request):
        form = await form_values(request)
        if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
            return redirect("/onboarding/connection", error="Session token was invalid.")
        
        target = form.get("target", "").strip()
        book = ConnectionBook(config.state_dir)
        if target not in book.names():
            return redirect("/onboarding/connection", error=f"Unknown connection '{target}'.")

        now = utcnow()
        entry = get_snapshot(target)
        if entry:
            wait = retry_in_seconds(entry.result, now)
            if wait > 0:
                return redirect("/onboarding/connection", error=f"Rate limited. Please wait {wait} seconds.")
            if not retry_allowed(entry.result.state):
                return redirect("/onboarding/connection", error="This error cannot be resolved by retrying.")

        _start_probe_async(book, target, mode=MODE_METADATA)
        return redirect("/onboarding/connection", notice="Retrying check...")

    @app.post("/onboarding/readiness/verify", include_in_schema=False)
    async def onboarding_readiness_verify(request: Request):
        form = await form_values(request)
        if not check_csrf(request, form.get("csrf") or request.headers.get("x-csrf-token")):
            return redirect("/onboarding/connection", error="Session token was invalid.")

        target = form.get("target", "").strip()
        book = ConnectionBook(config.state_dir)
        if target not in book.names():
            return redirect("/onboarding/connection", error=f"Unknown connection '{target}'.")

        now = utcnow()
        entry = get_snapshot(target)
        if entry and entry.last_generation_at:
            cooldown_left = GENERATION_COOLDOWN_SECONDS - (now - entry.last_generation_at).total_seconds()
            if cooldown_left > 0:
                return redirect("/onboarding/connection", error=f"Please wait {int(cooldown_left)} seconds before testing again.")

        model = form.get("model", "").strip()
        if not model and entry and entry.result.models:
            model = entry.result.models[0]

        _start_probe_async(book, target, mode=MODE_GENERATION, model=model)
        return redirect("/onboarding/connection", notice="Test generation started...")

    @app.get("/onboarding/connection", response_class=HTMLResponse, include_in_schema=False)
    def onboarding_connection_page(request: Request):
        load = load_setup(store)
        if load.kind != "present" or not load.setup or not load.setup.request_text:
            return redirect("/onboarding", error="Write your request first.")
        
        setup = load.setup
        if not setup.route_kind:
            return redirect("/onboarding/ai-service", error="Choose an AI service first.")

        book = ConnectionBook(config.state_dir)
        target = setup.connection_name
        if target and target not in book.names():
            target = ""

        # Default continue target is the assistant step
        continue_target = "/onboarding/assistant"
        fields = {
            "step_index": 3,
            "step_total": len(setup.step) if hasattr(setup, "step") else 5,
            "step_label": "connect route",
            "request_text": setup.request_text,
            "route_kind": setup.route_kind,
            "connection_name": target,
            "continue_target": continue_target,
            "revision": setup.revision,
            "state": "setup.connection",
        }
        return render(templates, config, request, fields, template=CONNECTION_SHELL)
