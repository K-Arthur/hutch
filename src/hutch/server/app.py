"""FastAPI dashboard + REST API.

* ``/api/*``  JSON API (scripts, CLI, tests). Run transcripts are paginated by per-run ``seq`` and
  streamed over SSE with ``Last-Event-ID`` resume.
* everything else: server-rendered pages (Jinja2 + HTMX, no build step) from ``pages.py``.

A background thread runs the engine's scheduler loop, which sleeps until work exists (PF-5) — so
`hutch serve` alone runs the whole platform. See ``security.py`` for the CSRF / DNS-rebinding defences.
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__
from ..approvals import resolve_approval
from ..config import get_config
from ..engine import Engine, bot_prompt_for_schedule
from ..models import ApprovalMode, ApprovalStatus, Bot, CatchUpPolicy, CommandRule, Limits, RiskTier, Schedule
from ..store import Store
from ..templates import TEMPLATE_INFO, TEMPLATES
from ..tools import ALL_TOOL_NAMES, expand_tools
from .security import SecurityMiddleware
from .sse import resume_cursor, run_event_stream

_STATIC = Path(__file__).parent / "static"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")

#: transcript window returned by default (PF-9): the run page stays usable at 10,000+ events
DEFAULT_EVENT_WINDOW = 200


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
    risk_tier: RiskTier = RiskTier.supervised
    command_rules: list[CommandRule] = []
    workdir: Optional[str] = None
    limits: Optional[Limits] = None


class BotPatch(BaseModel):
    description: Optional[str] = None
    instructions: Optional[str] = None
    model: Optional[str] = None
    approval_mode: Optional[ApprovalMode] = None
    risk_tier: Optional[RiskTier] = None
    command_rules: Optional[list[CommandRule]] = None
    workdir: Optional[str] = None          # "" clears it
    limits: Optional[Limits] = None
    paused: Optional[bool] = None
    cron: Optional[str] = None
    clear_cron: bool = False
    timezone: Optional[str] = None


class RunRequest(BaseModel):
    prompt: str
    rehearse: bool = False
    model: Optional[str] = None          # run this message on another model (the chat switcher); bot is unchanged


class ApproveRequest(BaseModel):
    always: bool = False
    plan_scope: int = 0


class ConnectionCreate(BaseModel):
    template: str
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None


class ConnectionAction(BaseModel):
    key: Optional[str] = None
    agree: bool = False
    window: Optional[str] = None
    tokens: Optional[int] = None


def create_app() -> FastAPI:
    config = get_config()
    store = Store(config)
    engine = Engine(config, store)
    scheduler = engine.scheduler

    @contextlib.asynccontextmanager
    async def lifespan(app_: FastAPI):
        # The scheduler loop sleeps until the next due run or a bus event (PF-5); no fixed tick.
        store.ensure_listening()
        _thread, stop = engine.start_background()
        try:
            yield
        finally:
            stop.set()
            store.bus.notify("work", remote=False)
            engine.shutdown()          # let in-flight runs record their outcome before the DB closes
            store.close()

    app = FastAPI(title="hutch", version=__version__, docs_url="/api/openapi.json", lifespan=lifespan)
    app.state.config, app.state.store, app.state.engine, app.state.scheduler = config, store, engine, scheduler
    app.add_middleware(SecurityMiddleware, auth_token=os.environ.get("HUTCH_AUTH_TOKEN") or None)

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

    def run_or_404(run_id: str):
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, f"no such run: {run_id}")
        return run

    # ------------------------------------------------------------- health

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "schema": store.schema_version}

    # --------------------------------------------------------------- bots

    @app.get("/api/bots")
    def list_bots() -> list[dict]:
        return [bot_view(b) for b in store.list_bots()]

    @app.get("/api/bots/templates")
    def bot_templates() -> list[dict]:
        return [
            {"name": i.key, "description": i.bot.description, "tools": i.bot.tools, "category": i.category,
             "tagline": i.tagline, "reads": i.reads, "produces": i.produces, "safety": i.safety,
             "needs_folder": i.needs_folder, "preset": i.bot.preset, "risk_tier": i.bot.risk_tier.value,
             "rules": [{"match": r.match, "verdict": r.verdict} for r in i.bot.command_rules],
             "schedule": i.bot.schedule.model_dump() if i.bot.schedule else None}
            for i in TEMPLATE_INFO.values()
        ]

    def _checked_workdir(raw: str) -> str:
        from ..workdir import validate_workdir
        try:
            return str(validate_workdir(raw, config.state_dir))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    def _checked_rules(rules: list[CommandRule]) -> list[CommandRule]:
        from ..safety import MAX_RULES
        if len(rules) > MAX_RULES:
            raise HTTPException(422, f"at most {MAX_RULES} command rules")
        return rules

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
        bot.risk_tier = body.risk_tier
        bot.command_rules = _checked_rules(body.command_rules)
        if body.limits is not None:
            bot.limits = body.limits
        if body.workdir:
            bot.workdir = _checked_workdir(body.workdir)
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
        if body.risk_tier is not None: bot.risk_tier = body.risk_tier
        if body.limits is not None: bot.limits = body.limits
        if body.command_rules is not None: bot.command_rules = _checked_rules(body.command_rules)
        if body.workdir is not None: bot.workdir = _checked_workdir(body.workdir) if body.workdir else None
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
        from ..modelchoices import ModelNotUsable, validate_override
        try:
            model = validate_override(config, store, bot, body.model or "")
        except ModelNotUsable as exc:
            raise HTTPException(exc.status, f"{exc} - {exc.fix}" if exc.fix else str(exc)) from None
        run = engine.submit(bot, body.prompt, origin="manual:api", rehearsal=body.rehearse,
                            model="" if model == bot.model else model)
        engine.dispatch_pending()
        return run_view(store.get_run(run.id))

    @app.get("/api/bots/{ref}/estimate")
    def bot_estimate(ref: str, model: Optional[str] = None, prompt: str = "") -> dict:
        """What one run can cost, before it starts (SR-2): a ceiling, or why there is none."""
        from dataclasses import asdict
        from ..estimate import estimate_run
        bot = bot_or_404(ref)
        e = estimate_run(config, store, bot, prompt, model)
        return {**asdict(e), "effective_ceiling_usd": e.effective_ceiling_usd, "summary": e.summary}

    @app.get("/api/bots/{ref}/models")
    def bot_models(ref: str) -> dict:
        """The switcher's list for this bot: its own model first, then what is usable, then what needs setup."""
        from ..modelchoices import choices_json, model_choices
        bot = bot_or_404(ref)
        return {"default": bot.model, "models": choices_json(model_choices(config, store, bot))}

    # --------------------------------------------------------------- runs

    @app.get("/api/runs")
    def list_runs(bot: Optional[str] = None, status: Optional[str] = None, limit: int = 30,
                  offset: int = 0) -> list[dict]:
        bot_id = bot_or_404(bot).id if bot else None
        return [run_view(r) for r in store.list_runs_page(bot_id, status, min(limit, 200), offset)]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, events: int = DEFAULT_EVENT_WINDOW) -> dict:
        """Run + the newest ``events`` transcript entries (0 = all). Page further with /events?before=."""
        run = run_or_404(run_id)
        view = run_view(run)
        total = store.count_events(run_id)
        window = store.tail_events(run_id, events) if events else store.list_events(run_id)
        view["events"] = [e.model_dump() for e in window]
        view["event_count"] = total
        view["events_truncated"] = bool(window) and window[0].seq > 1
        return view

    @app.get("/api/runs/{run_id}/events")
    def run_events(run_id: str, after: int = 0, before: int = 0, limit: int = 500) -> dict:
        """Events by per-run ``seq``: ``after=N`` for the next page / resume, ``before=N`` for earlier."""
        run = run_or_404(run_id)
        limit = max(1, min(limit, 1000))
        evs = (store.events_before(run_id, before, limit) if before
               else store.list_events(run_id, after_seq=after, limit=limit))
        return {"events": [e.model_dump() for e in evs], "status": run.status.value,
                "last_seq": store.last_seq(run_id)}

    @app.get("/api/runs/{run_id}/stream")
    async def run_stream(run_id: str, request: Request, after: int = 0) -> StreamingResponse:
        """SSE of JSON event batches. Reconnect with ``Last-Event-ID`` (browsers do this automatically)."""
        run_or_404(run_id)
        cursor = resume_cursor(request, after)

        def render(events, run):
            return {"events": [e.model_dump(exclude={"id"}) for e in events]}

        return StreamingResponse(run_event_stream(request, store, run_id, cursor, render),
                                 media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/runs/{run_id}/verify")
    def verify_run(run_id: str) -> dict:
        """SR-11: recompute the run's hash chain; ok=false means history was edited."""
        run_or_404(run_id)
        return store.verify_chain(run_id)

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: str) -> dict:
        run_or_404(run_id)
        engine.stop_run(run_id)
        return {"stopping": run_id}

    @app.post("/api/runs/{run_id}/resume")
    def resume_run(run_id: str) -> dict:
        run_or_404(run_id)
        store.resume_run(run_id)
        return {"resumed": run_id}

    @app.post("/api/stop-all")
    def stop_all() -> dict:
        return {"stopping": engine.stop_all()}

    # ---------------------------------------------------------- approvals

    @app.get("/api/approvals")
    def list_approvals(status: str = "pending", limit: int = 20) -> list[dict]:
        """``status=pending`` (default) lists the queue; ``status=resolved`` lists recently decided.

        Both carry ``bot_name`` and the resolution fields so the UI can show "already resolved
        elsewhere" honestly instead of guessing.
        """
        if status == "resolved":
            reqs = store.recent_approvals(min(max(limit, 1), 50))
        else:
            reqs = store.pending_approvals()
        out = []
        for req in reqs:
            bot = store.get_bot(req.bot_id)
            out.append({**req.model_dump(), "bot_name": bot.name if bot else "?"})
        return out

    @app.get("/api/approvals/{approval_id}")
    def get_approval(approval_id: str) -> dict:
        """One approval in any state — the reconciliation endpoint after a 409/404.

        Approvals are atomically resolved: two devices racing to answer the same card
        must be able to learn who won rather than silently disagreeing.
        """
        req = store.get_approval(approval_id)
        if req is None:
            raise HTTPException(404, "no such approval")
        bot = store.get_bot(req.bot_id)
        return {**req.model_dump(), "bot_name": bot.name if bot else "?"}

    @app.post("/api/approvals/{approval_id}/approve")
    def approve(approval_id: str, body: ApproveRequest) -> dict:
        existing = store.get_approval(approval_id)
        if existing is None:
            raise HTTPException(404, "no such approval")
        if existing.status is not ApprovalStatus.pending:
            raise HTTPException(409, f"approval already {existing.status.value}")
        resolve_approval(store, approval_id, approve=True, by="api", sticky=body.always,
                         plan_scope=body.plan_scope)
        return {"approved": approval_id, "sticky": body.always and not existing.outward}

    @app.post("/api/approvals/{approval_id}/deny")
    def deny(approval_id: str) -> dict:
        existing = store.get_approval(approval_id)
        if existing is None:
            raise HTTPException(404, "no such approval")
        if existing.status is not ApprovalStatus.pending:
            raise HTTPException(409, f"approval already {existing.status.value}")
        resolve_approval(store, approval_id, approve=False, by="api")
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

    # ------------------------------------------------------------ connections
    # JSON for the SPA's Connections view. Same semantics as the server-rendered
    # /connections page in pages.py; keys are write-only via set-key (stored 0600,
    # never returned).

    @app.get("/api/connections")
    def connections_api() -> dict:
        from ..connections import ConnectionBook

        book = ConnectionBook(config.state_dir)
        out = []
        for name, c in book.configured().items():
            used = store.usage_tokens_since(name, c.quota.seconds) if c.quota.tokens else 0
            out.append({
                "name": name, "title": c.title, "template": c.template, "protocol": c.protocol,
                "base_url": c.base_url, "api_key_env": c.api_key_env, "billing": c.billing,
                "has_key": book.key(name) is not None, "key_source": book.key_source(name),
                "ack": book.ack_status(store, name),
                "terms_notice": c.terms.notice, "terms_url": getattr(c.terms, "url", ""),
                "quota_window": c.quota.window, "quota_tokens": c.quota.tokens, "warn_at": c.quota.warn_at,
                "used": used, "quota_hint": c.quota_hint, "get_key_url": c.get_key_url,
            })
        templates = [{"key": k, "title": v.get("title", k), "billing": v.get("billing", ""),
                      "base_url": v.get("base_url", ""), "terms_notice": (v.get("terms") or {}).get("notice", "")}
                     for k, v in book.templates().items()]
        return {"connections": out, "templates": templates, "errors": book.errors}

    @app.post("/api/connections", status_code=201)
    def connection_add_api(body: ConnectionCreate) -> dict:
        from ..connections import ConnectionBook

        book = ConnectionBook(config.state_dir)
        try:
            c = book.add(body.template, body.name or None,
                         base_url=body.base_url or None, api_key_env=body.api_key_env or None)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"added": c.name}

    @app.post("/api/connections/{name}/{action}")
    def connection_action_api(name: str, action: str, body: ConnectionAction) -> dict:
        from ..connections import ConnectionBook
        from ..providers.connection import check_connection

        book = ConnectionBook(config.state_dir)
        if book.get(name) is None:
            raise HTTPException(404, f"no such connection: {name}")
        if action == "set-key":
            if not (body.key or "").strip():
                raise HTTPException(422, "The key was empty.")
            book.set_key(name, body.key.strip())      # written 0600; never echoed back
            return {"ok": True, "detail": f"Key stored for {name}."}
        if action == "clear-key":
            book.clear_key(name)
            return {"ok": True, "detail": f"Stored key removed for {name}."}
        if action == "ack":
            if not body.agree:
                raise HTTPException(422, "Confirm you read the terms first.")
            book.acknowledge(store, name)
            return {"ok": True, "detail": f"Terms acknowledged for {name}."}
        if action == "test":
            res = check_connection(book, name)
            if not res.ok:
                raise HTTPException(400, res.detail)
            return {"ok": True, "detail": res.detail}
        if action == "allowance":
            try:
                book.set_quota(name, body.window or "month", int(body.tokens or 0))
            except (ValueError, KeyError) as exc:
                raise HTTPException(422, str(exc)) from None
            return {"ok": True, "detail": "Allowance estimate saved. Hutch tracks local token totals; provider accounting can differ."}
        if action == "remove":
            book.remove(name)
            return {"ok": True, "detail": f"Removed {name} and its stored key."}
        raise HTTPException(404, "Unknown action.")

    # ------------------------------------------------------- pages + static

    from .pages import register_pages
    register_pages(app)
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    return app


__all__ = ["create_app", "bot_prompt_for_schedule"]
