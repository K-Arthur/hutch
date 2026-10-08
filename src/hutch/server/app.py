"""FastAPI dashboard + REST API.

* ``/api/*``  JSON API (scripts, CLI, tests). Run transcripts are paginated by per-run ``seq`` and
  streamed over SSE with ``Last-Event-ID`` resume.
* everything else: server-rendered pages (Jinja2 + HTMX, no build step) from ``pages.py``.

A background thread runs the engine's scheduler loop, which sleeps until work exists (PF-5) — so
`hutch serve` alone runs the whole platform. See ``security.py`` for the CSRF / DNS-rebinding defences.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..approvals import resolve_approval, resolve_approval_ex
from ..config import get_config
from ..engine import Engine, bot_prompt_for_schedule
from ..models import ACTIVE_STATUSES, ApprovalMode, ApprovalStatus, Bot, CatchUpPolicy, CommandRule, RiskTier, Run, RunStatus, Schedule, Task
from ..store import IdempotencyConflict, Store
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


class BotPatch(BaseModel):
    description: Optional[str] = None
    instructions: Optional[str] = None
    model: Optional[str] = None
    approval_mode: Optional[ApprovalMode] = None
    risk_tier: Optional[RiskTier] = None
    command_rules: Optional[list[CommandRule]] = None
    workdir: Optional[str] = None          # "" clears it
    paused: Optional[bool] = None
    cron: Optional[str] = None
    clear_cron: bool = False
    timezone: Optional[str] = None


class RunRequest(BaseModel):
    prompt: str
    rehearse: bool = False
    model: Optional[str] = None          # run this message on another model (the chat switcher); bot is unchanged


class ConversationCreate(BaseModel):
    bot: str
    title: str = Field(default="", max_length=120)


class ConversationMessageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    rehearse: bool = False
    model: Optional[str] = None


class ConversationArchiveRequest(BaseModel):
    archived: bool = True


class ConversationResource(BaseModel):
    id: str
    bot_id: str
    title: str
    created_at: str
    updated_at: str
    archived: bool
    is_legacy: bool
    message_count: int = 0
    last_seq: int = 0
    latest_run_id: Optional[str] = None


class ConversationMessageResource(BaseModel):
    id: str
    conversation_id: str
    seq: int
    run_id: str
    role: str
    content: str
    created_at: str


class ConversationDetail(ConversationResource):
    messages: list[ConversationMessageResource]
    last_seq: int
    has_more: bool


class ConversationSearchResult(BaseModel):
    id: str
    conversation_id: str
    seq: int
    run_id: str
    role: str
    content: str
    created_at: str
    bot_id: str
    title: str


class StatusLabelResource(BaseModel):
    status: str
    label: str
    terminal: bool
    needs_person: bool


class ApproveRequest(BaseModel):
    always: bool = False
    plan_scope: int = 0               # accepted and ignored: plan-wide grants were never implemented
    action_hash: Optional[str] = None  # the fingerprint the person was shown; if the stored action differs nothing is decided


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

    def idempotency_key(request: Request) -> str:
        key = (request.headers.get("Idempotency-Key") or "").strip()
        if not key:
            raise HTTPException(428, "Idempotency-Key is required for this command")
        if len(key) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise HTTPException(422, "Idempotency-Key must be 1–128 printable ASCII characters")
        return key

    def request_digest(payload: dict) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------- health

    @app.get("/api/health")
    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "schema": store.schema_version}

    @app.get("/api/v1/status-labels", response_model=list[StatusLabelResource])
    def status_labels() -> list[dict]:
        from ..lifecycle import LABELS, NEEDS_PERSON
        return [{"status": status.value, "label": LABELS[status], "terminal": status not in ACTIVE_STATUSES,
                 "needs_person": status in NEEDS_PERSON} for status in RunStatus]

    # ------------------------------------------------------ conversations

    @app.get("/api/v1/conversations", response_model=list[ConversationResource])
    def list_conversations(bot: Optional[str] = None, include_legacy: bool = False,
                           limit: int = 50, offset: int = 0) -> list[dict]:
        bot_id = bot_or_404(bot).id if bot else None
        return store.list_conversations(bot_id, include_legacy=include_legacy,
                                        limit=max(1, min(limit, 100)), offset=max(0, offset))

    @app.post("/api/v1/conversations", response_model=ConversationResource)
    def create_conversation(body: ConversationCreate, request: Request, response: Response) -> dict:
        bot = bot_or_404(body.bot)
        key = idempotency_key(request)
        try:
            row, created = store.create_conversation(
                bot.id, body.title, idem_key=key,
                request_hash=request_digest({"bot_id": bot.id, "title": body.title.strip()}))
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        response.status_code = 201 if created else 200
        return store.get_conversation(row["id"])

    @app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationDetail)
    def get_conversation(conversation_id: str, after: int = 0, limit: int = 100) -> dict:
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(404, f"no such conversation: {conversation_id}")
        limit = max(1, min(limit, 100))
        messages = store.list_conversation_messages(conversation_id, after=max(0, after), limit=limit + 1)
        has_more = len(messages) > limit
        messages = messages[:limit]
        return {**conversation, "messages": messages, "last_seq": store.conversation_last_seq(conversation_id),
                "has_more": has_more}

    @app.get("/api/v1/search/messages", response_model=list[ConversationSearchResult])
    def search_messages(q: str, bot: Optional[str] = None, limit: int = 20) -> list[dict]:
        if not q.strip() or len(q) > 256:
            raise HTTPException(422, "q must contain 1–256 characters")
        bot_id = bot_or_404(bot).id if bot else None
        return store.search_conversation_messages(q, bot_id=bot_id, limit=max(1, min(limit, 100)))

    @app.post("/api/v1/conversations/{conversation_id}/messages", response_model=dict)
    def send_conversation_message(conversation_id: str, body: ConversationMessageRequest,
                                  request: Request, response: Response) -> dict:
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(404, f"no such conversation: {conversation_id}")
        bot = store.get_bot(conversation["bot_id"])
        if bot is None:
            raise HTTPException(404, "conversation bot no longer exists")
        from ..modelchoices import ModelNotUsable, validate_override
        try:
            model = validate_override(config, store, bot, body.model or "")
        except ModelNotUsable as exc:
            raise HTTPException(exc.status, f"{exc} - {exc.fix}" if exc.fix else str(exc)) from None
        key = idempotency_key(request)
        digest = request_digest({"conversation_id": conversation_id, **body.model_dump()})
        run = Run(bot_id=bot.id, prompt=body.prompt, origin="manual:api", rehearsal=body.rehearse,
                  model_override="" if model == bot.model else model)
        task = Task(bot_id=bot.id, kind="on_demand", prompt=body.prompt)
        try:
            run_id, created = store.submit_conversation_message(
                conversation_id, body.prompt, run, task, idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except KeyError:
            raise HTTPException(404, f"no such conversation: {conversation_id}") from None
        except PermissionError:
            raise HTTPException(404, f"no such conversation: {conversation_id}") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        response.status_code = 201 if created else 200
        result = run_view(run_or_404(run_id))
        result["replayed"] = not created
        return result

    @app.post("/api/v1/conversations/{conversation_id}/archive", response_model=ConversationResource)
    def archive_conversation(conversation_id: str, body: ConversationArchiveRequest,
                             request: Request, response: Response) -> dict:
        key = idempotency_key(request)
        try:
            row, created = store.archive_conversation(
                conversation_id, body.archived, idem_key=key,
                request_hash=request_digest({"conversation_id": conversation_id, "archived": body.archived}))
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except KeyError:
            raise HTTPException(404, f"no such conversation: {conversation_id}") from None
        response.status_code = 200
        return store.get_conversation(conversation_id)

    # --------------------------------------------------------------- bots

    @app.get("/api/bots")
    @app.get("/api/v1/bots")
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
    @app.get("/api/v1/tasks/runs")
    def list_runs(bot: Optional[str] = None, status: Optional[str] = None, limit: int = 30,
                  offset: int = 0) -> list[dict]:
        bot_id = bot_or_404(bot).id if bot else None
        return [run_view(r) for r in store.list_runs_page(bot_id, status, min(limit, 200), offset)]

    @app.get("/api/runs/{run_id}")
    @app.get("/api/v1/tasks/runs/{run_id}")
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
    @app.get("/api/v1/tasks/runs/{run_id}/events")
    def run_events(run_id: str, after: int = 0, before: int = 0, limit: int = 500) -> dict:
        """Events by per-run ``seq``: ``after=N`` for the next page / resume, ``before=N`` for earlier."""
        run = run_or_404(run_id)
        limit = max(1, min(limit, 1000))
        evs = (store.events_before(run_id, before, limit) if before
               else store.list_events(run_id, after_seq=after, limit=limit))
        return {"events": [e.model_dump() for e in evs], "status": run.status.value,
                "last_seq": store.last_seq(run_id)}

    @app.get("/api/runs/{run_id}/stream")
    @app.get("/api/v1/tasks/runs/{run_id}/stream")
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
    @app.get("/api/v1/tasks/runs/{run_id}/verify")
    def verify_run(run_id: str) -> dict:
        """SR-11: recompute the run's hash chain; ok=false means history was edited."""
        run_or_404(run_id)
        return store.verify_chain(run_id)

    @app.post("/api/runs/{run_id}/stop")
    @app.post("/api/v1/tasks/runs/{run_id}/stop")
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
    @app.get("/api/v1/actions/approvals")
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
    @app.get("/api/v1/actions/approvals/{approval_id}")
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
    @app.post("/api/v1/actions/approvals/{approval_id}/approve")
    def approve(approval_id: str, body: ApproveRequest) -> dict:
        existing = store.get_approval(approval_id)
        if existing is None:
            raise HTTPException(404, "no such approval")
        if existing.status is not ApprovalStatus.pending:
            raise HTTPException(409, f"approval already {existing.status.value}")
        res = resolve_approval_ex(store, approval_id, approve=True, by="api", sticky=body.always,
                                  expected_hash=body.action_hash)
        if not res.won:
            raise HTTPException(409, {"expired": "that approval expired before it was answered, so it was denied",
                                      "mismatch": "the action changed since you reviewed it; review it again",
                                      "already": "somebody already decided that approval"}.get(res.outcome, res.outcome))
        return {"approved": approval_id, "sticky": body.always and not existing.outward}

    @app.post("/api/approvals/{approval_id}/deny")
    @app.post("/api/v1/actions/approvals/{approval_id}/deny")
    def deny(approval_id: str) -> dict:
        existing = store.get_approval(approval_id)
        if existing is None:
            raise HTTPException(404, "no such approval")
        if existing.status is not ApprovalStatus.pending:
            raise HTTPException(409, f"approval already {existing.status.value}")
        res = resolve_approval_ex(store, approval_id, approve=False, by="api")
        if not res.won:
            raise HTTPException(409, "somebody already decided that approval" if res.outcome == "already" else res.outcome)
        return {"denied": approval_id}

    # --------------------------------------------------------------- stats

    @app.get("/api/stats")
    @app.get("/api/v1/usage")
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

    # ------------------------------------------------------- pages + static

    from .pages import register_pages
    register_pages(app)
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    return app


__all__ = ["create_app", "bot_prompt_for_schedule"]
