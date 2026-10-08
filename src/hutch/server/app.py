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
import platform
import re
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..approvals import resolve_approval, resolve_approval_ex
from ..config import get_config
from ..durable_changes import SnapshotRequired
from ..engine import Engine, bot_prompt_for_schedule
from ..lifecycle import LABELS
from ..models import ACTIVE_STATUSES, ApprovalMode, ApprovalStatus, Bot, CatchUpPolicy, CommandRule, Limits, RiskTier, Run, RunStatus, Schedule, Task
from ..store import IdempotencyConflict, Store
from ..templates import TEMPLATE_INFO, TEMPLATES
from ..tools import ALL_TOOL_NAMES, expand_tools
from .security import DEVICE_COOKIE, SecurityMiddleware
from .sse import global_event_stream, resource_change_stream, resume_cursor, run_event_stream

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


class ConversationCreate(BaseModel):
    bot: str
    title: str = Field(default="", max_length=120)


class ConversationMessageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    rehearse: bool = False
    model: Optional[str] = None


class ConversationArchiveRequest(BaseModel):
    archived: bool = True


class PairingExchangeRequest(BaseModel):
    code: str = Field(min_length=14, max_length=24)
    label: str = Field(default="Phone", max_length=80)


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
    active_run_id: Optional[str] = None
    active_run_status: Optional[str] = None
    active_run_status_label: Optional[str] = None


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


class ConnectionResource(BaseModel):
    name: str
    title: str
    account_id: str
    account_daily_cost_cap_usd: float
    configured_account_daily_cost_cap_usd: float
    protocol: str
    model_protocols: dict[str, str]
    billing: str
    key_present: bool
    key_source: str
    terms_status: str
    terms_url: str
    quota_window: str
    quota_tokens: int
    quota_used_tokens: int
    quota_reserved_tokens: int
    account_daily_cost_used_usd: float
    account_daily_cost_reserved_usd: float
    models_endpoint: bool


class CapabilityResource(BaseModel):
    id: str
    status: str
    reason: str
    verification: str


class ScheduleResource(BaseModel):
    id: str
    bot_id: str
    bot_name: str
    cron: str
    timezone: str
    catch_up: str
    paused: bool
    next_fire: Optional[str] = None
    last_dispatched: Optional[str] = None
    last_skip: Optional[dict] = None


class EventPageResource(BaseModel):
    events: list[dict[str, Any]]
    after: int
    next_after: int
    high_watermark: int
    oldest_event_id: int
    has_more: bool


class ResourceChange(BaseModel):
    id: int
    resource: Literal["bots", "conversations", "messages", "runs", "tasks", "approvals", "actions", "usage",
                      "usage_reservations", "memory", "permissions", "devices"]
    resource_id: str
    operation: Literal["created", "updated", "deleted"]
    ts: str
    context: dict[str, Optional[str]]


class ChangePageResource(BaseModel):
    changes: list[ResourceChange]
    cursor: str
    high_water: str
    has_more: bool


class SnapshotResource(BaseModel):
    event_cursor: int
    replay_after: int
    change_cursor: str
    limit: int
    items: dict[str, list[dict[str, Any]]]
    totals: dict[str, int]
    truncated: dict[str, bool]
    next: dict[str, Optional[str]]


class UsageReservationResource(BaseModel):
    id: str
    run_id: str
    bot_id: str
    provider: str
    account_id: str
    model: str
    reserved_tokens: int
    reserved_cost_usd: float
    status: str
    created_at: str
    reason: str


class ApproveRequest(BaseModel):
    always: bool = False
    plan_scope: int = 0               # accepted and ignored: plan-wide grants were never implemented
    action_hash: Optional[str] = None  # the fingerprint the person was shown; if the stored action differs nothing is decided


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
    app.add_middleware(SecurityMiddleware, auth_token=os.environ.get("HUTCH_AUTH_TOKEN") or None,
                       device_auth=store.validate_device_token)

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
        measured_tokens, reserved_tokens, measured_cost, reserved_cost = store.bot_budget_today(bot.id)
        return {
            **bot.model_dump(),
            "next_run": nxt.isoformat() if nxt else None,
            "next_run_local": nxt.astimezone().strftime("%a %d %b %H:%M") if nxt else None,
            "last_success": last.finished_at or last.created_at if last else None,
            "active_run_id": active.id if active else None,
            "active_run_status": active.status.value if active else None,
            "active_run_status_label": LABELS[active.status] if active else None,
            "run_counts": stats,
            "tokens_today": measured_tokens + reserved_tokens,
            "tokens_measured_today": measured_tokens,
            "tokens_reserved_today": reserved_tokens,
            "cost_measured_today_usd": measured_cost,
            "cost_reserved_today_usd": reserved_cost,
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

    @app.get("/api/v1/events", response_model=EventPageResource)
    def global_events(after: int = 0, limit: int = 200) -> dict:
        """Read a bounded, globally ordered event page; per-run ``seq`` remains available on each event."""
        if after < 0:
            raise HTTPException(422, "after must be zero or a positive event ID")
        limit = max(1, min(limit, 500))
        oldest, high = store.global_event_bounds()
        if after > high or (oldest and after < oldest - 1):
            raise HTTPException(409, detail={"code": "snapshot_required", "reason": "event_cursor_unavailable",
                                             "snapshot_url": "/api/v1/snapshot", "event_cursor": high})
        events = store.list_global_events(after, limit)
        next_after = events[-1].id if events else after
        return {"events": [event.model_dump() for event in events], "after": after, "next_after": next_after,
                "high_watermark": high, "oldest_event_id": oldest,
                "has_more": bool(events) and next_after < high}

    @app.get("/api/v1/events/stream")
    async def global_events_stream(request: Request, after: int = 0) -> StreamingResponse:
        """Global durable SSE. Reconnect using Last-Event-ID; fetch `/api/v1/snapshot` on `snapshot_required`."""
        cursor = resume_cursor(request, after)
        return StreamingResponse(global_event_stream(request, store, cursor), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/v1/changes", response_model=ChangePageResource)
    def resource_changes(cursor: Optional[str] = None, limit: int = 200) -> dict:
        """Ordered, content-free resource invalidations. Fetch each changed resource's authoritative state."""
        try:
            return store.list_resource_changes(cursor, limit)
        except SnapshotRequired as exc:
            raise HTTPException(409, detail={"code": "snapshot_required", "reason": "change_cursor_unavailable",
                                             "message": str(exc), "snapshot_url": "/api/v1/snapshot"}) from exc

    @app.get("/api/v1/changes/stream")
    async def resource_changes_stream(request: Request, cursor: Optional[str] = None) -> StreamingResponse:
        """Last-Event-ID overrides the initial cursor, including malformed IDs requiring reconciliation."""
        cursor = request.headers.get("last-event-id", cursor)
        return StreamingResponse(resource_change_stream(request, store, cursor), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/v1/snapshot", response_model=SnapshotResource)
    def api_snapshot(limit: int = 100) -> dict:
        """Bounded consistent state for resynchronizing after an expired event cursor.

        Continue with each non-null `next` URL. Replay events after `replay_after` to include changes made during paging.
        """
        limit = max(1, min(limit, 500))
        snap = store.reconciliation_snapshot(limit)
        bots = [bot.model_dump(mode="json") for bot in snap["items"]["bots"]]
        bot_names = {bot["id"]: bot["name"] for bot in bots}
        def bot_name(bot_id: str) -> str:
            if bot_id not in bot_names:
                bot = store.get_bot(bot_id)
                bot_names[bot_id] = bot.name if bot else "?"
            return bot_names[bot_id]

        runs = [{**run.model_dump(mode="json"), "bot_name": bot_name(run.bot_id)}
                for run in snap["items"]["runs"]]
        approvals = [{**req.model_dump(mode="json"), "bot_name": bot_name(req.bot_id)}
                     for req in snap["items"]["approvals"]]
        conversations = []
        for row in snap["items"]["conversations"]:
            conversations.append({**row, "archived": bool(row["archived"]), "is_legacy": bool(row["is_legacy"])})
        items = {"bots": bots, "runs": runs, "approvals": approvals, "conversations": conversations}
        paths = {
            "bots": "/api/v1/bots",
            "runs": "/api/v1/tasks/runs",
            "approvals": "/api/v1/actions/approvals?status=pending",
            "conversations": "/api/v1/conversations?include_legacy=true",
        }
        next_urls = {name: f"{paths[name]}&limit={limit}&offset={limit}" if "?" in paths[name]
                     else f"{paths[name]}?limit={limit}&offset={limit}" if snap["truncated"][name] else None
                     for name in paths}
        # A query string already containing pagination parameters uses '&'; the base paths use '?'.
        for name in paths:
            if not snap["truncated"][name]:
                next_urls[name] = None
            elif "?" in paths[name]:
                next_urls[name] = f"{paths[name]}&limit={limit}&offset={limit}"
        return {"event_cursor": snap["event_cursor"], "replay_after": snap["event_cursor"],
                "change_cursor": snap["change_cursor"], "limit": limit,
                "items": items, "totals": snap["totals"], "truncated": snap["truncated"], "next": next_urls}

    @app.post("/api/v1/pairing/exchange")
    def exchange_pairing(body: PairingExchangeRequest, request: Request, response: Response) -> dict:
        """Exchange a short-lived host-issued code for an HttpOnly, revocable device session."""
        remote = request.client.host if request.client else "unknown"
        session, outcome = store.exchange_pairing_code(body.code, body.label, remote)
        if outcome == "rate_limited":
            raise HTTPException(429, "pairing attempts are temporarily limited; try again in ten minutes")
        if session is None:
            raise HTTPException(401, "pairing code is invalid, expired, or already used")
        response.set_cookie(DEVICE_COOKIE, session["token"], httponly=True, secure=request.url.scheme == "https",
                            samesite="strict", max_age=30 * 24 * 3600, path="/")
        return {"id": session["id"], "label": session["label"], "paired": True,
                "expires_in_seconds": 30 * 24 * 3600}

    @app.get("/api/v1/devices")
    def list_devices() -> list[dict]:
        return store.list_device_sessions()

    @app.post("/api/v1/devices/{device_id}/revoke")
    def revoke_device(device_id: str) -> dict:
        if not store.revoke_device_session(device_id):
            raise HTTPException(404, "no active device session with that id")
        return {"revoked": device_id}

    @app.get("/api/v1/status-labels", response_model=list[StatusLabelResource])
    def status_labels() -> list[dict]:
        from ..lifecycle import LABELS, NEEDS_PERSON
        return [{"status": status.value, "label": LABELS[status], "terminal": status not in ACTIVE_STATUSES,
                 "needs_person": status in NEEDS_PERSON} for status in RunStatus]

    @app.get("/api/v1/capabilities", response_model=list[CapabilityResource])
    def capabilities() -> list[dict]:
        linux = platform.system() == "Linux"
        return [
            {"id": "process_executor", "status": "supported" if linux else "unavailable",
             "reason": "Linux process groups and boot/start identity are supported" if linux else
                       "Only Linux is supported for process execution", "verification": "offline_process_tests"},
            {"id": "strict_shell", "status": "experimental" if linux else "unavailable",
             "reason": "Linux bubblewrap/cgroup containment is required; shell networking is disabled",
             "verification": "host_dependent_sandbox_tests" if linux else "not_tested"},
            {"id": "remote_pairing", "status": "experimental",
             "reason": "Direct HTTPS pairing is fixture-tested; no live network or phone validation",
             "verification": "offline_fixtures"},
            {"id": "phone_control", "status": "unavailable",
             "reason": "No phone control surface or authenticated interactive control route is implemented",
             "verification": "not_tested"},
            {"id": "browser_handoff", "status": "unavailable",
             "reason": "Same-session human browser control is not implemented", "verification": "not_tested"},
            {"id": "external_runtimes", "status": "unavailable",
             "reason": "Pi and OpenCode lack governed permission, sandbox and budget integration",
             "verification": "adapter_start_refusal_tests"},
        ]

    @app.get("/api/v1/connections", response_model=list[ConnectionResource])
    def list_connections() -> list[dict]:
        from ..connections import ConnectionBook
        book = ConnectionBook(config.state_dir)
        rows = []
        for name, conn in sorted(book.configured().items()):
            account_cap, _ = book.account_policy(conn.account_id)
            quota_used = store.account_usage_tokens_since(conn.account_id, conn.quota.seconds) if conn.quota.tokens else 0
            quota_reserved, _ = store.reserved_account_usage_since(conn.account_id, conn.quota.seconds)
            account_cost_used, account_cost_reserved = store.account_daily_costs(conn.account_id)
            rows.append({"name": name, "title": conn.title, "protocol": conn.protocol,
                         "account_id": conn.account_id,
                         "account_daily_cost_cap_usd": account_cap,
                         "configured_account_daily_cost_cap_usd": conn.account_daily_cost_cap_usd,
                         "model_protocols": conn.model_protocols, "billing": conn.billing,
                         "key_present": book.key(name) is not None, "key_source": book.key_source(name),
                         "terms_status": book.ack_status(store, name), "terms_url": conn.terms.url,
                         "quota_window": conn.quota.window, "quota_tokens": conn.quota.tokens,
                         "quota_used_tokens": quota_used, "quota_reserved_tokens": quota_reserved,
                         "account_daily_cost_used_usd": account_cost_used,
                         "account_daily_cost_reserved_usd": account_cost_reserved,
                         "models_endpoint": conn.models_endpoint})
        return rows

    @app.get("/api/v1/schedules", response_model=list[ScheduleResource])
    def list_schedules() -> list[dict]:
        rows = []
        for bot in store.list_bots():
            if not bot.schedule:
                continue
            nxt = scheduler.next_fire(bot)
            rows.append({"id": f"schedule:{bot.id}", "bot_id": bot.id, "bot_name": bot.name,
                         "cron": bot.schedule.cron, "timezone": bot.schedule.timezone,
                         "catch_up": bot.schedule.catch_up.value, "paused": bot.paused,
                         "next_fire": nxt.isoformat() if nxt else None,
                         "last_dispatched": scheduler._last_dispatched(bot).isoformat(),
                         "last_skip": scheduler.last_skip(bot)})
        return rows

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
    def list_bots() -> list[dict]:
        return [bot_view(b) for b in store.list_bots()]

    @app.get("/api/v1/bots")
    def list_bots_v1(limit: int = 100, offset: int = 0) -> list[dict]:
        bots = store.list_bots()
        start = max(0, offset)
        return [bot_view(bot) for bot in bots[start:start + max(1, min(limit, 500))]]

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
        return run_view(store.get_run(run.id))

    @app.get("/api/bots/{ref}/estimate")
    def bot_estimate(ref: str, model: Optional[str] = None, prompt: str = "") -> dict:
        """Estimate one run's priced usage before it starts; actual provider billing can differ."""
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
        return [run_view(r) for r in store.list_runs_page(bot_id, status, max(1, min(limit, 200)), max(0, offset))]

    @app.get("/api/runs/{run_id}")
    @app.get("/api/v1/tasks/runs/{run_id}")
    def get_run(run_id: str, events: int = DEFAULT_EVENT_WINDOW) -> dict:
        """Run + the newest ``events`` transcript entries (0 = all). Page further with /events?before=."""
        run = run_or_404(run_id)
        view = run_view(run)
        total = store.count_events(run_id)
        window = store.tail_events(run_id, events) if events else store.list_events(run_id)
        view["events"] = [e.model_dump() for e in window]
        view["approval_states"] = store.approval_states_for_events(run_id, window)
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
        return {"events": [e.model_dump() for e in evs], "approval_states": store.approval_states_for_events(run_id, evs),
                "status": run.status.value,
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
    def stop_run(run_id: str, request: Request) -> dict:
        run_or_404(run_id)
        idem_key = request_hash = None
        if request.url.path.startswith("/api/v1/"):
            idem_key = idempotency_key(request)
            request_hash = request_digest({"command": "stop", "run_id": run_id})
        try:
            engine.stop_run(run_id, idem_key=idem_key, request_hash=request_hash)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
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
        return approval_views(reqs)

    @app.get("/api/v1/actions/approvals")
    def list_approvals_v1(status: str = "pending", limit: int = 50, offset: int = 0) -> list[dict]:
        if status not in ("pending", "resolved"):
            raise HTTPException(422, "status must be pending or resolved")
        limit, offset = max(1, min(limit, 200)), max(0, offset)
        reqs = (store.recent_approvals(limit, offset) if status == "resolved" else
                store.pending_approvals(limit=limit, offset=offset))
        return approval_views(reqs)

    def approval_views(reqs: list) -> list[dict]:
        out = []
        for req in reqs:
            bot = store.get_bot(req.bot_id)
            run = store.get_run(req.run_id)
            out.append({**req.model_dump(), "bot_name": bot.name if bot else "?",
                        "conversation_id": run.conversation_id if run else None})
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
    def approve(approval_id: str, body: ApproveRequest, request: Request) -> dict:
        existing = store.get_approval(approval_id)
        if existing is None:
            raise HTTPException(404, "no such approval")
        idem_key = request_hash = None
        if request.url.path.startswith("/api/v1/"):
            idem_key = idempotency_key(request)
            if not body.action_hash:
                raise HTTPException(422, "action_hash from the approval resource is required")
            request_hash = request_digest({"command": "approve", "approval_id": approval_id,
                                           **body.model_dump()})
        if existing.status is not ApprovalStatus.pending and idem_key is None:
            raise HTTPException(409, f"approval already {existing.status.value}")
        try:
            res = resolve_approval_ex(store, approval_id, approve=True, by="api", sticky=body.always,
                                      expected_hash=body.action_hash, idem_key=idem_key, request_hash=request_hash)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        if not res.won and not (res.outcome == "replayed" and res.request is not None
                                and res.request.status is ApprovalStatus.approved):
            raise HTTPException(409, {"expired": "that approval expired before it was answered, so it was denied",
                                      "mismatch": "the action changed since you reviewed it; review it again",
                                      "already": "somebody already decided that approval"}.get(res.outcome, res.outcome))
        return {"approved": approval_id, "sticky": body.always and not existing.outward}

    @app.post("/api/approvals/{approval_id}/deny")
    @app.post("/api/v1/actions/approvals/{approval_id}/deny")
    def deny(approval_id: str, request: Request) -> dict:
        existing = store.get_approval(approval_id)
        if existing is None:
            raise HTTPException(404, "no such approval")
        idem_key = request_hash = None
        if request.url.path.startswith("/api/v1/"):
            idem_key = idempotency_key(request)
            request_hash = request_digest({"command": "deny", "approval_id": approval_id})
        if existing.status is not ApprovalStatus.pending and idem_key is None:
            raise HTTPException(409, f"approval already {existing.status.value}")
        try:
            res = resolve_approval_ex(store, approval_id, approve=False, by="api", idem_key=idem_key,
                                      request_hash=request_hash)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        if not res.won and not (res.outcome == "replayed" and res.request is not None
                                and res.request.status is ApprovalStatus.denied):
            raise HTTPException(409, "somebody already decided that approval" if res.outcome == "already" else res.outcome)
        return {"denied": approval_id}

    # --------------------------------------------------------------- stats

    @app.get("/api/stats")
    @app.get("/api/v1/usage")
    def stats() -> dict:
        bots = store.list_bots()
        active = store.active_runs()
        pending = store.pending_approvals()
        budgets = [store.bot_budget_today(b.id) for b in bots]
        tokens_today = sum(measured + held for measured, held, _, _ in budgets)
        return {
            "bots": len(bots), "paused": sum(1 for b in bots if b.paused),
            "active_runs": len(active), "pending_approvals": len(pending),
            "queued_tasks": len(store.pending_tasks()),
            "tokens_today": tokens_today,
            "tokens_measured_today": sum(row[0] for row in budgets),
            "tokens_reserved_today": sum(row[1] for row in budgets),
            "cost_measured_today_usd": sum(row[2] for row in budgets),
            "cost_reserved_today_usd": sum(row[3] for row in budgets),
            "version": __version__,
        }

    @app.get("/api/v1/usage/reservations", response_model=list[UsageReservationResource])
    def usage_reservations(limit: int = 100) -> list[dict]:
        return store.unresolved_usage_reservations(max(1, min(limit, 500)))

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
