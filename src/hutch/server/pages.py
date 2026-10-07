"""Server-rendered pages (UI-12): Jinja2 templates + HTMX, no build step.

Every action is a plain ``<form method="post">`` that works without JavaScript and redirects back;
HTMX only upgrades a few of them to in-place swaps (approvals, load-earlier, live partials). That keeps
"stop" and "approve" boring and reliable — the two buttons that must never silently fail.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from starlette.templating import Jinja2Templates

from .. import __version__
from ..approvals import resolve_approval
from ..engine import bot_prompt_for_schedule
from ..models import ApprovalStatus, Bot, CatchUpPolicy, EventType, RunStatus, Schedule
from ..templates import TEMPLATES
from ..tools import ALL_TOOL_NAMES, expand_tools
from .. import views
from .security import AUTH_COOKIE, auth_digest, check_csrf
from .sse import FINISHED, live_stream, resume_cursor, run_event_stream

TEMPLATE_DIR = Path(__file__).parent / "templates"
PAGE_WINDOW = 200            # transcript events rendered on first paint (PF-9)
RUNS_PAGE = 50
FLASH, FLASH_ERR = "hutch_flash", "hutch_flash_err"

NAV = [
    ("home", "/", "Home", "home"),
    ("bots", "/bots", "Bots", "bot"),
    ("runs", "/runs", "Runs", "list"),
    ("approvals", "/approvals", "Approvals", "shield"),
]


class RV:
    """A Run plus its bot's name, so templates read ``run.bot_name`` like the JSON API does."""

    def __init__(self, run, bot_name: str):
        self._run, self.bot_name = run, bot_name

    def __getattr__(self, item):
        return getattr(self._run, item)


class Form:
    def __init__(self, data: dict[str, list[str]]):
        self._d = data

    def get(self, key: str, default: str = "") -> str:
        v = self._d.get(key)
        return v[-1] if v else default

    def getlist(self, key: str) -> list[str]:
        return list(self._d.get(key, []))

    def flag(self, key: str) -> bool:
        return self.get(key) in ("1", "on", "true", "yes")


def safe_next(value: str, default: str) -> str:
    v = (value or "").strip()
    if v.startswith("/") and not v.startswith("//") and "\\" not in v and "\n" not in v and "\r" not in v:
        return v
    return default


def register_pages(app: FastAPI) -> None:
    store, engine, scheduler, config = app.state.store, app.state.engine, app.state.scheduler, app.state.config
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    env = templates.env
    env.filters.update({
        "ago": views.timeago, "money": views.fmt_money, "tokens": views.fmt_tokens,
        "duration": views.fmt_duration, "clock": views.fmt_clock, "origin": views.origin_label,
        "until": lambda ts: views.fmt_clock(max(0.0, (views.parse_ts(ts) - views.utcnow()).total_seconds()))
        if views.parse_ts(ts) else "-",
    })

    # --------------------------------------------------------------- helpers

    def page(request: Request, name: str, nav: str = "", status_code: int = 200, **ctx) -> Response:
        flash, flash_err = request.cookies.get(FLASH), request.cookies.get(FLASH_ERR)
        base = {
            "request": request, "nav": nav, "nav_items": NAV, "csrf": getattr(request.state, "csrf", ""),
            "pending_count": len(store.pending_approvals()), "version": __version__,
            "state_dir": str(config.state_dir),
            "notice": unquote(flash) if flash else None, "error": unquote(flash_err) if flash_err else None,
        }
        resp = templates.TemplateResponse(request, name, {**base, **ctx}, status_code=status_code)
        if flash:
            resp.delete_cookie(FLASH, path="/")
        if flash_err:
            resp.delete_cookie(FLASH_ERR, path="/")
        return resp

    def fragment(request: Request, name: str, **ctx) -> HTMLResponse:
        base = {"request": request, "csrf": getattr(request.state, "csrf", "")}
        return templates.TemplateResponse(request, name, {**base, **ctx})

    def go(target: str, notice: str = "", error: str = "") -> RedirectResponse:
        resp = RedirectResponse(target, status_code=303)
        if notice:
            resp.set_cookie(FLASH, quote(notice), max_age=15, path="/", samesite="strict")
        if error:
            resp.set_cookie(FLASH_ERR, quote(error), max_age=15, path="/", samesite="strict")
        return resp

    async def read_form(request: Request) -> Form:
        raw = (await request.body()).decode("utf-8", "replace")
        form = Form(parse_qs(raw, keep_blank_values=True))
        token = form.get("csrf") or request.headers.get("x-csrf-token")
        if not check_csrf(request, token):
            raise HTTPException(403, "Missing or invalid CSRF token. Reload the page and try again.")
        return form

    def bot_or_404(name: str) -> Bot:
        bot = store.get_bot(name)
        if bot is None:
            raise HTTPException(404, f"No bot named '{name}'.")
        return bot

    def run_or_404(run_id: str):
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, f"No run '{run_id}'.")
        return run

    def bot_name_of(run) -> str:
        b = store.get_bot(run.bot_id)
        return b.name if b else "(deleted bot)"

    def rv(run) -> RV:
        return RV(run, bot_name_of(run))

    def render_events(request: Request, evs, run) -> str:
        approvals = {}
        for e in evs:
            if e.type is EventType.approval_request:
                a = store.get_approval(e.data.get("approval_id", ""))
                if a is not None:
                    approvals[a.id] = a
        return env.get_template("_events_fragment.html").render(
            evs=evs, approvals=approvals, run=run, csrf=getattr(request.state, "csrf", ""))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/") or "text/html" not in request.headers.get("accept", "text/html"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return page(request, "error.html", status_code=exc.status_code,
                    status=exc.status_code, message=exc.detail)

    # ------------------------------------------------------------------ legacy SPA

    @app.get("/legacy", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/legacy/", response_class=HTMLResponse, include_in_schema=False)
    def legacy_spa():
        """The v0.1 single-page dashboard, kept reachable (read-only) while the server-rendered pages
        replace it at `/`. Delete `static/app.js|index.html|style.css` once nothing needs them."""
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    # ------------------------------------------------------------------ home

    def home_ctx():
        return views.home_state(store, scheduler, engine)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(request: Request):
        return page(request, "home.html", nav="home", home=home_ctx(), has_bots=bool(store.list_bots()))

    @app.get("/_home", response_class=HTMLResponse, include_in_schema=False)
    def home_partial(request: Request):
        return fragment(request, "_home_lists.html", home=home_ctx())

    @app.get("/_badge", response_class=HTMLResponse, include_in_schema=False)
    def badge():
        return HTMLResponse(str(len(store.pending_approvals())))

    @app.get("/stream/live", include_in_schema=False)
    async def stream_live(request: Request):
        return StreamingResponse(
            live_stream(request, store, ["work", "approvals", "runs", "bots"]),
            media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------------ bots

    @app.get("/bots", response_class=HTMLResponse, include_in_schema=False)
    def bots_page(request: Request):
        views_ = []
        for b in store.list_bots():
            nxt = scheduler.next_fire(b)
            last = store.last_successful_run(b.id)
            active = store.active_run_for_bot(b.id)
            d = b.model_dump()
            d.update(
                next_run_local=nxt.astimezone().strftime("%a %d %b %H:%M") if nxt else None,
                last_success=(last.finished_at or last.created_at) if last else None,
                active_run_id=active.id if active else None, tokens_today=store.tokens_today(b.id),
                memory_count=len(store.recall_all(b.id)))
            d["schedule"] = b.schedule
            d["approval_mode"] = b.approval_mode
            views_.append(_Obj(d))
        return page(request, "bots.html", nav="bots", bots=views_)

    @app.get("/bots/new", response_class=HTMLResponse, include_in_schema=False)
    def bot_new(request: Request):
        return page(request, "bot_new.html", nav="bots", templates=list(TEMPLATES.values()),
                    picked=request.query_params.get("template", ""))

    @app.post("/bots", include_in_schema=False)
    async def bot_create(request: Request):
        import re
        form = await read_form(request)
        name = form.get("name").strip()
        if not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", name):
            return go("/bots/new", error="Name must be a lowercase slug: a-z, 0-9 and hyphens, 2-41 characters.")
        if store.get_bot(name):
            return go("/bots/new", error=f"A bot named '{name}' already exists.")
        template = form.get("template")
        if template and template not in TEMPLATES:
            return go("/bots/new", error=f"Unknown template '{template}'.")
        bot = TEMPLATES[template].model_copy(deep=True) if template else Bot(name=name)
        bot.name, bot.template = name, template or None
        bot.description = form.get("description") or bot.description
        bot.model = form.get("model") or bot.model
        cron = form.get("cron").strip()
        if cron:
            try:
                bot.schedule = Schedule(cron=cron, timezone=form.get("timezone") or "UTC")
                scheduler.next_fire(bot)
            except Exception:
                return go("/bots/new", error="That cron expression is not valid (5 fields, e.g. 0 9 * * 1).")
        store.create_bot(bot)
        return go(f"/bots/{name}", notice=f"Created {name}.")

    @app.get("/bots/{name}", response_class=HTMLResponse, include_in_schema=False)
    def bot_page(request: Request, name: str):
        bot = bot_or_404(name)
        return page(request, "bot.html", nav="bots", bot=bot,
                    runs=[rv(r) for r in store.list_runs(bot.id, limit=8)],
                    memory=store.recall_all(bot.id), allows=store.list_sticky_allows(bot.id),
                    tokens_today=store.tokens_today(bot.id))

    @app.post("/bots/{name}/run", include_in_schema=False)
    async def bot_run(request: Request, name: str):
        form = await read_form(request)
        bot = bot_or_404(name)
        prompt = form.get("prompt").strip()
        if form.flag("standing"):
            prompt = bot_prompt_for_schedule(bot)
        if not prompt:
            return go(f"/bots/{name}", error="Write a task first.")
        run = engine.submit(bot, prompt, origin="manual:dashboard", rehearsal=form.flag("rehearse"))
        engine.dispatch_pending()
        target = f"/runs/{run.id}" if not form.flag("standing") else safe_next(form.get("next"), f"/runs/{run.id}")
        return go(target, notice=f"Started {'a rehearsal of ' if form.flag('rehearse') else ''}{name}.")

    @app.post("/bots/{name}/{action}", include_in_schema=False)
    async def bot_action(request: Request, name: str, action: str):
        form = await read_form(request)
        bot = bot_or_404(name)
        nxt = safe_next(form.get("next"), f"/bots/{name}")
        if action in ("pause", "resume"):
            bot.paused = action == "pause"
            store.upsert_bot(bot)
            return go(nxt, notice=f"{'Paused' if bot.paused else 'Resumed'} {name}.")
        if action == "update":
            bot.description = form.get("description")
            bot.model = form.get("model").strip() or bot.model
            bot.instructions = form.get("instructions")
            from ..models import ApprovalMode
            bot.approval_mode = ApprovalMode(form.get("approval_mode") or bot.approval_mode.value)
            cron = form.get("cron").strip()
            if cron:
                try:
                    sched = Schedule(cron=cron, timezone=form.get("timezone") or "UTC",
                                     catch_up=bot.schedule.catch_up if bot.schedule else CatchUpPolicy.coalesce)
                    probe = bot.model_copy(update={"schedule": sched})
                    if scheduler.next_fire(probe) is None:
                        raise ValueError("bad cron")
                    bot.schedule = sched
                except Exception:
                    return go(nxt, error="That cron expression or time zone is not valid.")
            else:
                bot.schedule = None
            store.upsert_bot(bot)
            return go(nxt, notice="Saved.")
        if action == "delete":
            store.delete_bot(name)
            return go("/bots", notice=f"Deleted {name}.")
        raise HTTPException(404, "Unknown action.")

    @app.post("/bots/{name}/memory/delete", include_in_schema=False)
    async def memory_delete(request: Request, name: str):
        form = await read_form(request)
        bot = bot_or_404(name)
        store.forget(bot.id, form.get("key"))
        return go(safe_next(form.get("next"), f"/bots/{name}"), notice="Forgotten.")

    @app.post("/bots/{name}/allows/revoke", include_in_schema=False)
    async def allow_revoke(request: Request, name: str):
        form = await read_form(request)
        bot = bot_or_404(name)
        store.revoke_sticky(bot.id, form.get("key"))
        return go(safe_next(form.get("next"), f"/bots/{name}"), notice="Revoked. That action asks again.")

    # ------------------------------------------------------------------ runs

    @app.get("/runs", response_class=HTMLResponse, include_in_schema=False)
    def runs_page(request: Request, bot: str = "", status: str = "", offset: int = 0, fragment_: Optional[str] = None):
        bot_obj = store.get_bot(bot) if bot else None
        rows = store.list_runs_page(bot_obj.id if bot_obj else None, status or None, RUNS_PAGE + 1, offset)
        has_more = len(rows) > RUNS_PAGE
        query = f"bot={quote(bot)}&status={quote(status)}"
        ctx = dict(runs=[rv(r) for r in rows[:RUNS_PAGE]], has_more=has_more,
                   next_offset=offset + RUNS_PAGE, query=query)
        if request.query_params.get("fragment"):
            return fragment(request, "_runs_table.html", **ctx)
        return page(request, "runs.html", nav="runs", bots=store.list_bots(), f_bot=bot, f_status=status, **ctx)

    @app.get("/runs/{run_id}", response_class=HTMLResponse, include_in_schema=False)
    def run_page(request: Request, run_id: str):
        run = run_or_404(run_id)
        bot = store.get_bot(run.bot_id)
        active = run.status in views.ACTIVE_STATUSES
        total = store.count_events(run_id)
        evs = store.tail_events(run_id, PAGE_WINDOW)
        first_seq = evs[0].seq if evs else 1
        wait = views.explain_run(store, run, engine, bot) if active else views.explain_outcome(run, bot)
        meters = views.run_meters(store, run, bot)
        view = rv(run)
        return page(request, "run.html", nav="runs", run=view, active=active, wait=wait,
                    meters=meters, split=views.timing_split(run), evs=evs, first_seq=first_seq,
                    hidden=max(0, first_seq - 1), last_seq=evs[-1].seq if evs else 0, event_count=total,
                    bot_model=bot.model if bot else "?", verify=store.verify_chain(run_id) if not active else {},
                    approvals={a.id: a for a in (store.get_approval(e.data.get("approval_id", ""))
                                                 for e in evs if e.type is EventType.approval_request) if a})

    @app.get("/runs/{run_id}/events", response_class=HTMLResponse, include_in_schema=False)
    def run_events_fragment(request: Request, run_id: str, before: int = 0, after: int = 0, upto: int = 0):
        """HTML fragment: older events ("load earlier") or a gap fill the client asked for."""
        run = run_or_404(run_id)
        view = rv(run)
        if before:
            evs = store.events_before(run_id, before, PAGE_WINDOW)
            first = evs[0].seq if evs else before
            return HTMLResponse(env.get_template("_events_more.html").render(
                request=request, csrf=getattr(request.state, "csrf", ""), evs=evs, run=view, first_seq=first,
                hidden=max(0, first - 1), run_id=run_id,
                approvals={a.id: a for a in (store.get_approval(e.data.get("approval_id", "")) for e in evs
                                             if e.type is EventType.approval_request) if a}))
        evs = store.list_events(run_id, after_seq=after, limit=PAGE_WINDOW)
        if upto:
            evs = [e for e in evs if e.seq <= upto]
        return HTMLResponse(render_events(request, evs, view))

    @app.get("/runs/{run_id}/meters", response_class=HTMLResponse, include_in_schema=False)
    def run_meters_fragment(request: Request, run_id: str):
        run = run_or_404(run_id)
        bot = store.get_bot(run.bot_id)
        return fragment(request, "_meters.html", run=run, active=run.status in views.ACTIVE_STATUSES,
                        meters=views.run_meters(store, run, bot), split=views.timing_split(run))

    @app.get("/runs/{run_id}/wait", response_class=HTMLResponse, include_in_schema=False)
    def run_wait_fragment(request: Request, run_id: str):
        run = run_or_404(run_id)
        bot = store.get_bot(run.bot_id)
        active = run.status in views.ACTIVE_STATUSES
        wait = views.explain_run(store, run, engine, bot) if active else views.explain_outcome(run, bot)
        return HTMLResponse(env.get_template("_wait_fragment.html").render(
            request=request, csrf=getattr(request.state, "csrf", ""), wait=wait))

    @app.get("/runs/{run_id}/stream", include_in_schema=False)
    async def run_stream(request: Request, run_id: str, after: int = 0):
        """SSE: HTML fragments of new events. Honors Last-Event-ID so a dropped connection resumes gap-free."""
        run_or_404(run_id)
        cursor = resume_cursor(request, after)
        csrf = getattr(request.state, "csrf", "")

        def render(evs, run):
            view = rv(run) if run else None
            approvals = {a.id: a for a in (store.get_approval(e.data.get("approval_id", "")) for e in evs
                                           if e.type is EventType.approval_request) if a}
            html = env.get_template("_events_fragment.html").render(
                evs=evs, approvals=approvals, run=view, csrf=csrf)
            return {"html": html, "count": len(evs)}

        return StreamingResponse(run_event_stream(request, store, run_id, cursor, render),
                                 media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/runs/{run_id}/stop", include_in_schema=False)
    async def run_stop(request: Request, run_id: str):
        form = await read_form(request)
        run_or_404(run_id)
        engine.stop_run(run_id)
        if request.headers.get("hx-request"):
            return Response(status_code=204, headers={"HX-Refresh": "true"})
        return go(safe_next(form.get("next"), f"/runs/{run_id}"), notice="Stop requested. Child processes are being killed.")

    @app.post("/runs/{run_id}/resume", include_in_schema=False)
    async def run_resume(request: Request, run_id: str):
        form = await read_form(request)
        run_or_404(run_id)
        store.resume_run(run_id)
        return go(safe_next(form.get("next"), f"/runs/{run_id}"), notice="Resumed.")

    @app.post("/runs/{run_id}/dismiss", include_in_schema=False)
    async def run_dismiss(request: Request, run_id: str):
        form = await read_form(request)
        run_or_404(run_id)
        store.kv_set(f"dismissed:{run_id}", "1")
        store.bus.notify("runs")
        return go(safe_next(form.get("next"), "/"), notice="Dismissed. The run is still in Runs.")

    @app.post("/stop-all", include_in_schema=False)
    async def stop_all(request: Request):
        form = await read_form(request)
        n = engine.stop_all()
        return go(safe_next(form.get("next"), "/"),
                  notice=f"Stopped {n} run{'' if n == 1 else 's'}." if n else "Nothing was running.")

    # ------------------------------------------------------------- approvals

    def approvals_ctx():
        items = []
        for a in store.pending_approvals():
            b = store.get_bot(a.bot_id)
            items.append((a, b.name if b else "?"))
        return items

    def recent_decided():
        out = []
        for a in store.recent_approvals(limit=8):
            b = store.get_bot(a.bot_id)
            out.append((a, b.name if b else "?"))
        return out

    @app.get("/approvals", response_class=HTMLResponse, include_in_schema=False)
    def approvals_page(request: Request):
        return page(request, "approvals.html", nav="approvals", items=approvals_ctx(), recent=recent_decided())

    @app.get("/_approvals", response_class=HTMLResponse, include_in_schema=False)
    def approvals_partial(request: Request):
        return fragment(request, "_approval_list.html", items=approvals_ctx(), recent=recent_decided())

    @app.post("/approvals/{approval_id}/decide", include_in_schema=False)
    async def approval_decide(request: Request, approval_id: str):
        form = await read_form(request)
        a = store.get_approval(approval_id)
        if a is None:
            raise HTTPException(404, "No such approval.")
        choice = form.get("choice")
        nxt = safe_next(form.get("next"), "/approvals")
        if a.status is not ApprovalStatus.pending:
            return go(nxt, error=f"That approval was already {a.status.value}.")
        if choice not in ("once", "always", "plan", "deny"):
            raise HTTPException(422, "Choose once, always, plan or deny.")
        resolve_approval(store, approval_id, approve=choice != "deny", by="dashboard",
                         sticky=choice == "always", plan_scope=20 if choice == "plan" else 0)
        if request.headers.get("hx-request"):
            return fragment(request, "_approval_resolved.html", a=store.get_approval(approval_id), choice=choice)
        return go(nxt, notice="Denied." if choice == "deny" else "Allowed - the run continues.")

    # ----------------------------------------------------------- login (remote)

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request):
        return page(request, "login.html")

    @app.post("/login", include_in_schema=False)
    async def login(request: Request):
        import os
        form = await read_form(request)
        token = os.environ.get("HUTCH_AUTH_TOKEN", "")
        import hmac
        if token and hmac.compare_digest(form.get("token"), token):
            resp = RedirectResponse("/", status_code=303)
            resp.set_cookie(AUTH_COOKIE, auth_digest(token), httponly=True, samesite="strict", max_age=86400 * 7)
            return resp
        return go("/login", error="That token is not right.")


class _Obj:
    """Dict -> attribute access for templates (bot summaries)."""

    def __init__(self, d: dict):
        self.__dict__.update(d)
