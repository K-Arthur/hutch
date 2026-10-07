"""FastAPI dashboard + REST API.

Serves the single-page dashboard from server/static and a JSON API used by
both the dashboard and remote tooling. A background thread ticks the engine
(schedules, dispatch, approval expiry) so `hutch serve` alone runs the
whole platform.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import re
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__
from ..approvals import resolve_approval
from ..config import get_config
from ..engine import Engine
from ..models import ApprovalMode, ApprovalStatus, Bot, CatchUpPolicy, Limits, RunStatus, Schedule
from ..scheduler import Scheduler
from ..store import Store
from ..templates import TEMPLATES
from ..tools import ALL_TOOL_NAMES, expand_tools

_STATIC = Path(__file__).parent / "static"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


class BotCreate(BaseModel):
    name: str
    template: Optional[str] = None
    description: str = ""
    instructions: str = ""
    model: str = "mock/demo"
    base_url: Optional[str] = None
    tools: list[str] = ["shell", "files", "memory"]
    cron: Optional[str] = None
    timezone: str = "UTC"
    catch_up: CatchUpPolicy = CatchUpPolicy.coalesce
    approval_mode: ApprovalMode = ApprovalMode.ask


class BotPatch(BaseModel):
    description: Optional[str] = None
    instructions: Optional[str] = None
    model: Optional[str] = None
    approval_mode: Optional[ApprovalMode] = None
    paused: Optional[bool] = None
    cron: Optional[str] = None
    clear_cron: bool = False
    timezone: Optional[str] = None


class RunRequest(BaseModel):
    prompt: str


class ApproveRequest(BaseModel):
    always: bool = False


def create_app() -> FastAPI:
    config = get_config()
    store = Store(config)
    engine = Engine(config, store)
    scheduler = Scheduler(store)
    @contextlib.asynccontextmanager
    async def lifespan(app_: FastAPI):
        def loop() -> None:
            import time, traceback
            while True:
                try:
                    engine.tick()
                except Exception:
                    traceback.print_exc()
                time.sleep(15)

        t = threading.Thread(target=loop, daemon=True, name="hutch-tick")
        t.start()
        yield

    app = FastAPI(title="hutch", version=__version__, docs_url="/api/openapi.json", lifespan=lifespan)

    # ------------------------------------------------------------- helpers

    def bot_or_404(ref: str) -> Bot:
        bot = store.get_bot(ref)
        if bot is None:
            raise HTTPException(404, f"no such bot: {ref}")
        return bot

    def bot_view(bot: Bot) -> dict:
        nxt = scheduler.next_fire(bot)
        last = store.last_successful_run(bot.id)
        active = store.active_run_for_bot(bot.id)
        stats = store.bot_stats().get(bot.id, {}).get("counts", {})
        return {
            **bot.model_dump(),
            "next_run": nxt.isoformat() if nxt else None,
            "next_run_local": nxt.astimezone().strftime("%a %d %b %H:%M") if nxt else None,
            "last_success": last.finished_at or last.created_at if last else None,
            "active_run_id": active.id if active else None,
            "run_counts": stats,
            "tokens_today": store.tokens_today(bot.id),
            "memory_count": len(store.recall_all(bot.id)),
            "sticky_allows": store.list_sticky_allows(bot.id),
        }

    def run_view(run) -> dict:
        bot = store.get_bot(run.bot_id)
        return {**run.model_dump(), "bot_name": bot.name if bot else "?"}

    # ------------------------------------------------------------- health

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    # --------------------------------------------------------------- bots

    @app.get("/api/bots")
    def list_bots() -> list[dict]:
        return [bot_view(b) for b in store.list_bots()]

    @app.get("/api/bots/templates")
    def bot_templates() -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "tools": t.tools,
             "schedule": t.schedule.model_dump() if t.schedule else None}
            for t in TEMPLATES.values()
        ]

    @app.post("/api/bots", status_code=201)
    def create_bot(body: BotCreate) -> dict:
        if not _SLUG_RE.match(body.name):
            raise HTTPException(422, "name must be a lowercase slug (a-z, 0-9, -)")
        if store.get_bot(body.name):
            raise HTTPException(409, f"bot already exists: {body.name}")
        if body.template:
            if body.template not in TEMPLATES:
                raise HTTPException(422, f"unknown template: {body.template}")
            bot = TEMPLATES[body.template].model_copy(deep=True)
            bot.name, bot.template = body.name, body.template
        else:
            bot = Bot(name=body.name)
        tools = expand_tools(body.tools)
        unknown = [t for t in tools if t not in ALL_TOOL_NAMES]
        if unknown:
            raise HTTPException(422, f"unknown tools: {unknown}")
        bot.description = body.description or bot.description
        bot.instructions = body.instructions or bot.instructions
        bot.model = body.model
        bot.base_url = body.base_url
        bot.tools = tools
        bot.approval_mode = body.approval_mode
        if body.cron:
            try:
                bot.schedule = Schedule(cron=body.cron, timezone=body.timezone,
                                        catch_up=body.catch_up)
            except Exception:
                raise HTTPException(422, "invalid schedule")
        store.create_bot(bot)
        return bot_view(bot)

    @app.get("/api/bots/{ref}")
    def get_bot(ref: str) -> dict:
        bot = bot_or_404(ref)
        view = bot_view(bot)
        view["recent_runs"] = [run_view(r) for r in store.list_runs(bot.id, limit=10)]
        view["memory"] = [m.model_dump() for m in store.recall_all(bot.id)]
        return view

    @app.patch("/api/bots/{ref}")
    def patch_bot(ref: str, body: BotPatch) -> dict:
        bot = bot_or_404(ref)
        if body.description is not None: bot.description = body.description
        if body.instructions is not None: bot.instructions = body.instructions
        if body.model is not None: bot.model = body.model
        if body.approval_mode is not None: bot.approval_mode = body.approval_mode
        if body.paused is not None: bot.paused = body.paused
        if body.clear_cron:
            bot.schedule = None
        else:
            cron = body.cron or (bot.schedule.cron if bot.schedule else None)
            tz = body.timezone or (bot.schedule.timezone if bot.schedule else "UTC")
            if cron:
                bot.schedule = Schedule(cron=cron, timezone=tz,
                                        catch_up=bot.schedule.catch_up if bot.schedule else CatchUpPolicy.coalesce)
        store.upsert_bot(bot)
        return bot_view(bot)

    @app.delete("/api/bots/{ref}")
    def delete_bot(ref: str) -> dict:
        bot_or_404(ref)
        store.delete_bot(ref)
        return {"deleted": ref}

    @app.delete("/api/bots/{ref}/sticky-allows/{key:path}")
    def delete_sticky_allow(ref: str, key: str) -> dict:
        bot = bot_or_404(ref)
        store.revoke_sticky(bot.id, key)
        return {"revoked": key}

    @app.delete("/api/bots/{ref}/memory/{key:path}")
    def delete_memory(ref: str, key: str) -> dict:
        bot = bot_or_404(ref)
        store.forget(bot.id, key)
        return {"forgot": key}

    @app.post("/api/bots/{ref}/run", status_code=201)
    def run_bot(ref: str, body: RunRequest) -> dict:
        bot = bot_or_404(ref)
        run = engine.submit(bot, body.prompt)
        engine.dispatch_pending()
        return run_view(store.get_run(run.id))

    # --------------------------------------------------------------- runs

    @app.get("/api/runs")
    def list_runs(bot: Optional[str] = None, limit: int = 30) -> list[dict]:
        bot_id = bot_or_404(bot).id if bot else None
        return [run_view(r) for r in store.list_runs(bot_id, limit=min(limit, 200))]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, f"no such run: {run_id}")
        view = run_view(run)
        view["events"] = [e.model_dump() for e in store.list_events(run_id)]
        return view

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: str, after: int = 0) -> dict:
        if store.get_run(run_id) is None:
            raise HTTPException(404, f"no such run: {run_id}")
        events = [e.model_dump() for e in store.list_events(run_id, after_id=after)]
        current = store.get_run(run_id)
        return {"events": events, "status": current.status.value if current else "?"}

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: str) -> dict:
        if store.get_run(run_id) is None:
            raise HTTPException(404, f"no such run: {run_id}")
        engine.stop_run(run_id)
        return {"stopping": run_id}

    # ---------------------------------------------------------- approvals

    @app.get("/api/approvals")
    def list_approvals() -> list[dict]:
        out = []
        for req in store.pending_approvals():
            bot = store.get_bot(req.bot_id)
            out.append({**req.model_dump(), "bot_name": bot.name if bot else "?"})
        return out

    @app.post("/api/approvals/{approval_id}/approve")
    def approve(approval_id: str, body: ApproveRequest) -> dict:
        existing = store.get_approval(approval_id)
        if existing is None:
            raise HTTPException(404, "no such approval")
        if existing.status is not ApprovalStatus.pending:
            raise HTTPException(409, f"approval already {existing.status.value}")
        resolve_approval(store, approval_id, approve=True, by="dashboard", sticky=body.always)
        return {"approved": approval_id, "sticky": body.always}

    @app.post("/api/approvals/{approval_id}/deny")
    def deny(approval_id: str) -> dict:
        existing = store.get_approval(approval_id)
        if existing is None:
            raise HTTPException(404, "no such approval")
        if existing.status is not ApprovalStatus.pending:
            raise HTTPException(409, f"approval already {existing.status.value}")
        resolve_approval(store, approval_id, approve=False, by="dashboard")
        return {"denied": approval_id}

    # --------------------------------------------------------------- stats

    @app.get("/api/stats")
    def stats() -> dict:
        bots = store.list_bots()
        active = store.active_runs()
        pending = store.pending_approvals()
        tokens_today = sum(store.tokens_today(b.id) for b in bots)
        return {
            "bots": len(bots), "paused": sum(1 for b in bots if b.paused),
            "active_runs": len(active), "pending_approvals": len(pending),
            "queued_tasks": len(store.pending_tasks()),
            "tokens_today": tokens_today,
            "version": __version__,
        }

    # -------------------------------------------------------------- static

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    return app
