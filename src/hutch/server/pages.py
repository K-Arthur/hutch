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
from ..templates import TEMPLATE_INFO, TEMPLATES
from ..tools import ALL_TOOL_NAMES, expand_tools
from .. import views
from .security import AUTH_COOKIE, auth_digest, check_csrf
from .sse import FINISHED, live_stream, resume_cursor, run_event_stream
from ..estimate import estimate_run

TEMPLATE_DIR = Path(__file__).parent / "templates"
PAGE_WINDOW = 200            # transcript events rendered on first paint (PF-9)
RUNS_PAGE = 50
FLASH, FLASH_ERR = "hutch_flash", "hutch_flash_err"

NAV = [
    ("studio", "/", "Studio", "chat"),
    ("overview", "/overview", "Overview", "home"),
    ("bots", "/bots", "Bots", "bot"),
    ("runs", "/runs", "Runs", "list"),
    ("approvals", "/approvals", "Approvals", "shield"),
    ("models", "/models", "Models", "cpu"),
    ("usage", "/usage", "Usage", "chart"),
    ("connections", "/connections", "Connections", "layers"),
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

    def has(self, key: str) -> bool:
        return key in self._d

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
        "ago": views.timeago, "money": views.fmt_money, "tokens": views.fmt_tokens, "ms": views.fmt_ms,
        "jsonish": views.json_pretty, "argsum": views.arg_summary, "argsum_for": views.arg_summary, "outsum": views.output_summary,
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
    def studio_home():
        """The chat interface is the home (Grok-bot style): open the app and talk to a bot.
        The triage dashboard lives at /overview; /legacy serves the same studio app."""
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/overview", response_class=HTMLResponse, include_in_schema=False)
    def overview(request: Request):
        return RedirectResponse("/#/overview", status_code=302)

    @app.get("/_home", response_class=HTMLResponse, include_in_schema=False)
    def home_partial(request: Request):
        return fragment(request, "_home_lists.html", home=home_ctx())

    @app.get("/api/overview", include_in_schema=False)
    def api_overview():
        """The triage data the studio's Overview view renders (same source as /overview)."""
        h = home_ctx()

        def rj(run, name, wait=None):
            d = {"id": run.id, "bot_name": name, "status": run.status.value, "status_label": run.status_label,
                 "terminal": run.terminal, "prompt": run.prompt,
                 "steps": run.steps, "tokens": run.tokens, "cost_usd": run.cost_usd,
                 "created_at": run.created_at, "finished_at": run.finished_at,
                 "started_at": run.started_at}
            if wait:
                d["wait"] = {"cause": wait.cause, "fix": wait.fix, "kind": wait.kind,
                             "href": wait.href, "link_text": wait.link_text, "deadline": wait.deadline}
            return d

        return {
            "stats": h.stats, "needs_count": h.needs_count,
            "approvals": [{"id": a.id, "bot_name": name, "action": a.action, "tool": a.tool,
                           "risk": a.risk, "outward": a.outward, "expires_at": a.expires_at}
                          for a, name in h.approvals],
            "humans": [rj(r, n, w) for r, n, w in h.humans],
            "failures": [rj(r, n, w) for r, n, w in h.failures],
            "running": [rj(r, n, w) for r, n, w in h.running],
            "stale": [{"bot_name": s.bot.name, "cause": s.cause, "fix": s.fix,
                       "last_success": s.last_success,
                       "last_run_id": s.last_run.id if s.last_run else None} for s in h.stale],
        }

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
                active_run_id=active.id if active else None,
                tokens_today=sum(store.bot_budget_today(b.id)[:2]),
                memory_count=len(store.recall_all(b.id)))
            d["schedule"] = b.schedule
            d["approval_mode"] = b.approval_mode
            views_.append(_Obj(d))
        return RedirectResponse("/#/bots", status_code=302)

    @app.get("/bots/new", response_class=HTMLResponse, include_in_schema=False)
    def bot_new(request: Request):
        return RedirectResponse("/#/bots", status_code=302)

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
        from ..modelchoices import ModelNotUsable, validate_override
        try:
            bot.model = validate_override(config, store, bot, form.get("model"))
        except ModelNotUsable as exc:
            return go("/bots/new", error=f"{exc}. {exc.fix}" if exc.fix else str(exc))
        cron = form.get("cron").strip()
        if cron:
            try:
                bot.replace_primary_schedule(Schedule(cron=cron, timezone=form.get("timezone") or "UTC"))
                scheduler.next_fire(bot)
            except Exception:
                return go("/bots/new", error="That cron expression is not valid (5 fields, e.g. 0 9 * * 1).")
        store.create_bot(bot)
        info = TEMPLATE_INFO.get(template or "")
        hint = (f" It reads files ({info.reads}): set a working folder under Settings or it starts with nothing to look at."
                if info and info.needs_folder and not bot.workdir else "")
        return go(f"/bots/{name}", notice=f"Created {name}.{hint}")

    @app.get("/bots/{name}", response_class=HTMLResponse, include_in_schema=False)
    def bot_page(request: Request, name: str):
        bot = bot_or_404(name)
        measured_tokens, reserved_tokens, _, _ = store.bot_budget_today(bot.id)
        return page(request, "bot.html", nav="bots", bot=bot,
                    runs=[rv(r) for r in store.list_runs(bot.id, limit=8)],
                    memory=store.shared_facts(bot.id), allows=store.list_sticky_allows(bot.id),
                    tokens_today=measured_tokens + reserved_tokens, estimate=estimate_run(config, store, bot))

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
        target = f"/runs/{run.id}" if not form.flag("standing") else safe_next(form.get("next"), f"/runs/{run.id}")
        return go(target, notice=f"Started {'a rehearsal of ' if form.flag('rehearse') else ''}{name}.")

    @app.post("/bots/{name}/{action}", include_in_schema=False)
    async def bot_action(request: Request, name: str, action: str):
        form = await read_form(request)
        bot = bot_or_404(name)
        nxt = safe_next(form.get("next"), f"/bots/{name}")
        if action in ("pause", "resume"):
            bot.paused = action == "pause"
            store.upsert_bot(bot, preserve_schedules=True)
            return go(nxt, notice=f"{'Paused' if bot.paused else 'Resumed'} {name}.")
        if action == "update":
            if form.has("display_name"):
                display_name = " ".join(form.get("display_name").split())
                if not display_name or len(display_name) > 80:
                    return go(nxt, error="Display name must contain 1–80 characters.")
                bot.display_name = display_name
            bot.description = form.get("description")
            bot.model = form.get("model").strip() or bot.model
            bot.instructions = form.get("instructions")
            from ..models import ApprovalMode, CommandRule, RiskTier
            from ..safety import parse_rules
            bot.approval_mode = ApprovalMode(form.get("approval_mode") or bot.approval_mode.value)
            try:
                bot.risk_tier = RiskTier(form.get("risk_tier") or bot.risk_tier.value)
                bot.command_rules = [CommandRule(verdict=v, match=g) for v, g in parse_rules(form.get("command_rules"))]
            except ValueError as exc:
                return go(nxt, error=f"Command rules not saved: {exc}")
            from ..workdir import validate_workdir
            wd = form.get("workdir").strip()
            workspace_mode = form.get("workspace_mode") or ("folder" if wd else "fresh")
            if workspace_mode not in ("fresh", "managed", "folder"):
                return go(nxt, error="Workspace not saved: choose fresh, managed, or an existing folder.")
            if workspace_mode == "folder":
                try:
                    bot.workdir = str(validate_workdir(wd, config.state_dir)) if wd else None
                    if not bot.workdir:
                        return go(nxt, error="Workspace not saved: folder mode needs an existing folder path.")
                except ValueError as exc:
                    return go(nxt, error=f"Working folder not saved: {exc}")
            else:
                bot.workdir = None
            bot.workspace_mode = workspace_mode
            bot.local_browser_handoff = form.flag("local_browser_handoff")
            cron = form.get("cron").strip()
            if cron:
                try:
                    sched = Schedule(cron=cron, timezone=form.get("timezone") or "UTC",
                                     catch_up=bot.schedule.catch_up if bot.schedule else CatchUpPolicy.coalesce)
                    probe = bot.model_copy(update={"schedule": sched, "schedules": [sched, *bot.schedules[1:]]})
                    if scheduler.next_fire(probe) is None:
                        raise ValueError("bad cron")
                    previous = bot.schedule
                    if previous:
                        sched = Schedule(id=previous.id, name=previous.name, created_at=previous.created_at,
                                         cron=sched.cron, timezone=sched.timezone, catch_up=sched.catch_up,
                                         prompt=sched.prompt)
                    bot.replace_primary_schedule(sched)
                except Exception:
                    return go(nxt, error="That cron expression or time zone is not valid.")
            else:
                bot.replace_primary_schedule(None)
            store.upsert_bot(bot, primary_schedule_update=bot.schedule if cron else None)
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
        return RedirectResponse("/#/runs", status_code=302)

    @app.get("/runs/{run_id}", response_class=HTMLResponse, include_in_schema=False)
    def run_page(request: Request, run_id: str):
        run_or_404(run_id)
        return RedirectResponse(f"/#/run/{run_id}", status_code=302)

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
                        meters=views.run_meters(store, run, bot), split=views.timing_split(run),
                        timing=views.timing_abs(run))

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
        return RedirectResponse("/#/approvals", status_code=302)

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

    from .pages_models import register_model_pages
    register_model_pages(app, page, go, read_form)
    from .pages_usage import register_usage_page
    register_usage_page(app, page)

    # ----------------------------------------------------------- connections (CN)

    from ..connections import WINDOWS, ConnectionBook
    from ..chatgpt_auth import ChatGPTAuthBook, ChatGPTAuthError, chatgpt_plan_signin_enabled, loopback_callback_uri
    from ..providers.connection import check_connection

    def conn_book() -> ConnectionBook:
        return ConnectionBook(config.state_dir)

    def conn_views(book: ConnectionBook):
        out = []
        for name, c in book.configured().items():
            used = store.account_usage_tokens_since(c.account_id, c.quota.seconds) if c.quota.tokens else 0
            reserved, _ = store.reserved_account_usage_since(c.account_id, c.quota.seconds)
            day = store.account_usage_tokens_since(c.account_id, 86400)
            day_reserved, _ = store.reserved_account_usage_since(c.account_id, 86400)
            cost_used, cost_reserved = store.account_daily_costs(c.account_id)
            account_cost_cap, _ = book.account_policy(c.account_id)
            projected = used + reserved
            out.append(_Obj({
                "c": c, "key": book.key_source(name), "has_key": book.has_key(name),
                "ack": book.ack_status(store, name), "used": used, "reserved": reserved,
                "day": day, "day_reserved": day_reserved, "cost_used": cost_used,
                "cost_reserved": cost_reserved, "account_cost_cap": account_cost_cap,
                "pct": min(100.0, projected / c.quota.tokens * 100) if c.quota.tokens else 0.0,
                "level": ("hot" if c.quota.tokens and projected / c.quota.tokens >= 0.9 else
                          "warn" if c.quota.tokens and projected / c.quota.tokens >= c.quota.warn_at else "ok")}))
        return out

    @app.get("/connections", response_class=HTMLResponse, include_in_schema=False)
    def connections_page():
        # Preserve the bookmark while sending people into Apps & AI in the
        # shared workspace. Old form clients can use /legacy/connections.
        return RedirectResponse("/#/connections", status_code=302)

    @app.get("/legacy/connections", response_class=HTMLResponse, include_in_schema=False)
    def legacy_connections_page(request: Request):
        book = conn_book()
        have = set(book.names())
        return page(request, "connections.html", nav="connections", conns=conn_views(book),
                    templates=[(k, v) for k, v in book.templates().items()], have=have, windows=list(WINDOWS),
                    errors=book.errors, chatgpt_accounts=ChatGPTAuthBook(config.state_dir).accounts(),
                    chatgpt_enabled=chatgpt_plan_signin_enabled())

    @app.post("/connections/chatgpt/sign-in", include_in_schema=False)
    async def chatgpt_sign_in_page(request: Request):
        form = await read_form(request)
        if not chatgpt_plan_signin_enabled():
            return go("/legacy/connections", error="Sign in with ChatGPT is an eligibility-gated preview. Set HUTCH_ENABLE_CHATGPT_PLAN=1 only if Hutch is eligible for this flow.")
        try:
            url = ChatGPTAuthBook(config.state_dir).start(
                loopback_callback_uri(request), account_id=form.get("account_id"))
        except ChatGPTAuthError as exc:
            return go("/legacy/connections", error=str(exc))
        response = RedirectResponse(url, status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.post("/connections/chatgpt/disconnect", include_in_schema=False)
    async def chatgpt_disconnect_page(request: Request):
        form = await read_form(request)
        account_id = form.get("account_id")
        try:
            revoked = ChatGPTAuthBook(config.state_dir).disconnect(account_id)
            store.revoke_background_provider_consents(account_id=account_id)
            book = conn_book()
            for name, conn in book.configured().items():
                if conn.auth_type == "chatgpt-siws" and conn.auth_account_id == account_id:
                    book.remove(name)
        except ChatGPTAuthError as exc:
            return go("/legacy/connections", error=str(exc))
        return go("/legacy/connections", notice=("ChatGPT access was revoked and removed from this Hutch." if revoked else
                                           "Local ChatGPT credentials were cleared, but OpenAI did not confirm remote revocation."))

    @app.post("/connections/add", include_in_schema=False)
    async def connection_add(request: Request):
        form = await read_form(request)
        book = conn_book()
        tpl = form.get("template")
        try:
            over = {"base_url": form.get("base_url").strip() or None, "api_key_env": form.get("api_key_env").strip() or None}
            c = book.add(tpl, form.get("name").strip() or None, **over)
        except ValueError as exc:
            return go("/legacy/connections", error=str(exc))
        return go("/legacy/connections", notice=f"Added {c.name}. Now give it a key, and acknowledge its terms if it has any.")

    @app.post("/connections/{name}/{action}", include_in_schema=False)
    async def connection_action(request: Request, name: str, action: str):
        form = await read_form(request)
        book = conn_book()
        conn = book.get(name)
        if conn is None:
            raise HTTPException(404, f"No connection named '{name}'.")
        if action == "key":
            if conn.auth_type != "api_key":
                return go("/legacy/connections", error="This connection uses a sign-in account. Manage it from Connections instead of setting an API key.")
            key = form.get("key").strip()
            if not key:
                return go("/legacy/connections", error="That key was empty.")
            book.set_key(name, key)          # written to a 0600 file; never echoed, logged or stored in the database
            return go("/legacy/connections", notice=f"Key stored for {name}.")
        if action == "clear-key":
            if conn.auth_type != "api_key":
                return go("/legacy/connections", error="This connection uses a sign-in account. Disconnect the account from Connections instead.")
            book.clear_key(name)
            return go("/legacy/connections", notice=f"Stored key removed for {name}.")
        if action == "ack":
            if not form.flag("agree"):
                return go("/legacy/connections", error="Tick the box to confirm you read the terms.")
            book.acknowledge(store, name)
            return go("/legacy/connections", notice=f"Terms acknowledged for {name}.")
        if action == "test":
            res = check_connection(book, name)
            return go("/legacy/connections", **({"notice": f"{name}: {res.detail}"} if res.ok else {"error": f"{name}: {res.detail}"}))
        if action == "allowance":
            try:
                book.set_quota(name, form.get("window") or "month", int(form.get("tokens") or 0))
            except (ValueError, KeyError) as exc:
                return go("/legacy/connections", error=str(exc))
            return go("/legacy/connections", notice="Allowance saved. Hutch will stop before it is spent.")
        if action == "account-cap":
            try:
                raw = form.get("daily_usd").strip()
                cap = float(raw or 0)
                book.update(name, account_daily_cost_cap_usd=cap)
            except (ValueError, KeyError) as exc:
                return go("/legacy/connections", error=str(exc))
            return go("/legacy/connections", notice=f"Shared daily account cap saved for {name}.")
        if action == "protocol":
            try:
                book.set_model_protocol(name, form.get("model").strip(), form.get("protocol"))
            except (ValueError, KeyError) as exc:
                return go("/legacy/connections", error=str(exc))
            return go("/legacy/connections", notice="Protocol saved for that model.")
        if action == "remove":
            if conn.auth_type == "chatgpt-siws":
                store.revoke_background_provider_consents(provider=name)
            book.remove(name)
            return go("/legacy/connections", notice=f"Removed {name} and its stored key.")
        raise HTTPException(404, "Unknown action.")

    # ----------------------------------------------------------- login (remote)

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request):
        return page(request, "login.html")

    @app.get("/pair", response_class=HTMLResponse, include_in_schema=False)
    def pair_page(request: Request):
        """Exchange a host-issued one-time code for this browser's revocable device session."""
        return page(request, "pair.html")

    @app.post("/login", include_in_schema=False)
    async def login(request: Request):
        if getattr(request.state, "hutch_remote", False):
            raise HTTPException(403, "owner-token sign-in is available only on the Hutch host")
        import os
        form = await read_form(request)
        token = os.environ.get("HUTCH_AUTH_TOKEN", "")
        import hmac
        if token and hmac.compare_digest(form.get("token"), token):
            resp = RedirectResponse("/", status_code=303)
            resp.set_cookie(AUTH_COOKIE, auth_digest(token), httponly=True, secure=request.url.scheme == "https",
                            samesite="strict", max_age=86400 * 7)
            return resp
        return go("/login", error="That token is not right.")


class _Obj:
    """Dict -> attribute access for templates (bot summaries)."""

    def __init__(self, d: dict):
        self.__dict__.update(d)
