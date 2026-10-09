"""FastAPI dashboard + REST API.

* ``/api/*``  JSON API (scripts, CLI, tests). Run transcripts are paginated by per-run ``seq`` and
  streamed over SSE with ``Last-Event-ID`` resume.
* everything else: server-rendered pages (Jinja2 + HTMX, no build step) from ``pages.py``.

A background thread runs the engine's scheduler loop, which sleeps until work exists (PF-5) — so
`hutch serve` alone runs the whole platform. See ``security.py`` for the CSRF / DNS-rebinding defences.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import json
import os
import platform
import re
import stat
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Literal, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .. import __version__
from ..approvals import resolve_approval, resolve_approval_ex
from ..action_receipts import ActionConflict
from ..fact_memory import FactConflict
from ..config import get_config
from ..durable_changes import SnapshotRequired
from ..engine import Engine, bot_prompt_for_schedule
from ..lifecycle import LABELS
from ..models import ACTIVE_STATUSES, ApprovalMode, ApprovalStatus, Bot, BotCreationSource, CatchUpPolicy, CommandRule, Event, EventType, InferenceMode, Limits, MemoryItem, RiskTier, Run, RunStatus, RuntimeKind, Schedule, Task
from ..store import ActiveRunConflict, BotConflict, IdempotencyConflict, Store
from ..state_snapshot import ExecutionHeld
from ..templates import TEMPLATE_INFO, TEMPLATES
from ..tools import ALL_TOOL_NAMES, expand_tools
from .security import DEVICE_COOKIE, SecurityMiddleware, allowed_hosts_from_env
from .sse import global_event_stream, resource_change_stream, resume_cursor, run_event_stream

_STATIC = Path(__file__).parent / "static"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
_ARTIFACT_NAME_RE = re.compile(r"^[0-9]{3,6}-[a-z0-9_-]{1,40}\.txt$")
_ARTIFACT_SHA_RE = re.compile(r"^[a-f0-9]{64}$")
_CONVERSATION_ARTIFACT_CURSOR_RE = re.compile(r"^([1-9][0-9]{0,18}):(tool_output|workspace_file)$")
_MAX_ARTIFACT_BYTES = 4_000_000
MAX_CONVERSATION_EXPORT_MESSAGES = 10_000
MAX_CONVERSATION_EXPORT_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CONVERSATION_EXPORT_BYTES = 16 * 1024 * 1024

#: transcript window returned by default (PF-9): the run page stays usable at 10,000+ events
DEFAULT_EVENT_WINDOW = 200


def _encode_conversation_artifact_cursor(event_id: int, kind: str) -> str:
    payload = f"{event_id}:{kind}".encode("ascii")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_conversation_artifact_cursor(value: Optional[str]) -> Optional[tuple[int, str]]:
    if value is None:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise HTTPException(422, "invalid conversation artifact cursor")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        decoded = raw.decode("ascii")
    except (binascii.Error, UnicodeDecodeError):
        raise HTTPException(422, "invalid conversation artifact cursor") from None
    match = _CONVERSATION_ARTIFACT_CURSOR_RE.fullmatch(decoded)
    if match is None:
        raise HTTPException(422, "invalid conversation artifact cursor")
    event_id = int(match.group(1))
    if event_id > 9_223_372_036_854_775_807:
        raise HTTPException(422, "invalid conversation artifact cursor")
    return event_id, match.group(2)


class BotCreate(BaseModel):
    name: str
    template: Optional[str] = None
    description: str = ""
    instructions: str = ""
    model: str = ""
    base_url: Optional[str] = None
    inference_mode: InferenceMode = InferenceMode.hybrid
    tools: list[str] = ["shell", "files", "memory"]
    memory_enabled: bool = True
    cron: Optional[str] = None
    timezone: str = "UTC"
    catch_up: CatchUpPolicy = CatchUpPolicy.coalesce
    schedule_prompt: str = Field(default="", max_length=4000)
    approval_mode: ApprovalMode = ApprovalMode.ask
    risk_tier: RiskTier = RiskTier.supervised
    command_rules: list[CommandRule] = []
    workspace_mode: Optional[Literal["fresh", "managed", "folder"]] = None
    local_browser_handoff: bool = False
    workdir: Optional[str] = None
    limits: Optional[Limits] = None
    source_conversation_id: Optional[str] = Field(default=None, max_length=100)
    source_message_id: Optional[str] = Field(default=None, max_length=100)


class RestoreReportResource(BaseModel):
    id: str
    created_at: str
    execution_held: bool
    counts: dict[str, int]
    verification: dict[str, int]
    source_schema: int
    schema_version: int = Field(alias='schema')
    excluded: list[str]
    source_processes_stopped: bool
    old_work_will_resume: bool
    activated_at: Optional[str] = None
    activation_evidence: str = ''
    verified_code_hash: str


class RestoreItemResource(BaseModel):
    kind: Literal['runs', 'tasks', 'processes', 'approvals', 'devices', 'bots']
    resource_id: str
    prior_status: str


class RestorePageResource(BaseModel):
    report: Optional[RestoreReportResource]
    items: list[RestoreItemResource]
    limit: int
    offset: int


class BotPatch(BaseModel):
    description: Optional[str] = None
    instructions: Optional[str] = None
    model: Optional[str] = None
    runtime: Optional[Literal["builtin"]] = None
    inference_mode: Optional[InferenceMode] = None
    tools: Optional[list[str]] = None
    memory_enabled: Optional[bool] = None
    approval_mode: Optional[ApprovalMode] = None
    risk_tier: Optional[RiskTier] = None
    command_rules: Optional[list[CommandRule]] = None
    workspace_mode: Optional[Literal["fresh", "managed", "folder"]] = None
    local_browser_handoff: Optional[bool] = None
    workdir: Optional[str] = None          # "" clears it
    limits: Optional[Limits] = None
    tool_limits: Optional[dict[str, int]] = None   # per-tool output caps in chars (PF-2); "" clears a tool
    paused: Optional[bool] = None
    cron: Optional[str] = None
    clear_cron: bool = False
    timezone: Optional[str] = None
    schedule_prompt: Optional[str] = Field(default=None, max_length=4000)


class RunRequest(BaseModel):
    prompt: str
    rehearse: bool = False
    model: Optional[str] = None          # run this message on another model (the chat switcher); bot is unchanged


class VersionedRunCreateRequest(BaseModel):
    bot: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=20_000)
    rehearse: bool = False
    model: Optional[str] = Field(default=None, max_length=200)


class ResumeRunRequest(BaseModel):
    human_event_seq: int = Field(ge=1)


class ConversationCreate(BaseModel):
    bot: str
    title: str = Field(default="", max_length=120)


class ConversationMessageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    rehearse: bool = False
    model: Optional[str] = None
    reply_to_message_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class ConversationArchiveRequest(BaseModel):
    archived: bool = True


class PairingExchangeRequest(BaseModel):
    code: str = Field(min_length=14, max_length=24)
    label: str = Field(default="Phone", max_length=80)


class PairingExchangeResource(BaseModel):
    id: str
    label: str
    paired: bool
    expires_in_seconds: int


class DeviceResource(BaseModel):
    id: str
    label: str
    created_at: str
    expires_at: str
    last_used_at: Optional[str] = None
    revoked_at: Optional[str] = None
    current: bool


class DeviceRevocationResource(BaseModel):
    revoked: str


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
    reply_to_message_id: Optional[str] = None
    reply_to_role: Optional[str] = None
    reply_to_excerpt: Optional[str] = None
    content_truncated: bool = False


class ConversationDetail(ConversationResource):
    messages: list[ConversationMessageResource]
    last_seq: int
    has_more: bool


class ConversationExportScope(BaseModel):
    included: list[str]
    excluded: list[str]
    notice: str


class ConversationExportMetadata(BaseModel):
    id: str
    bot_id: str
    title: str
    created_at: str
    updated_at: str
    archived: bool
    is_legacy: bool
    message_count: int


class ConversationExportMessage(BaseModel):
    id: str
    seq: int
    run_id: str
    role: str
    content: str
    created_at: str
    reply_to_message_id: Optional[str] = None


class ConversationExportResource(BaseModel):
    format: Literal["hutch-conversation-export-v1"]
    scope: ConversationExportScope
    conversation: ConversationExportMetadata
    messages: list[ConversationExportMessage]


class ArtifactShareTargetResource(BaseModel):
    id: str
    target_conversation_id: str
    target_conversation_title: str
    created_at: str


class ArtifactResource(BaseModel):
    id: str
    run_id: str
    bot_id: str
    conversation_id: str = ""
    version: int
    source_tool: str
    kind: Literal["tool_output", "workspace_file"] = "tool_output"
    filename: str
    sha256: str = ""
    size_bytes: int = 0
    chars: int = 0
    created_at: str
    state: Literal["available", "missing", "unverified"]
    download_url: Optional[str] = None
    share_id: Optional[str] = None
    shared_from: Optional[str] = None
    shared_with: list[ArtifactShareTargetResource] = Field(default_factory=list)


class ConversationArtifactShareRequest(BaseModel):
    source_run_id: str = Field(min_length=4, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    source_version: int = Field(gt=0)
    kind: Literal["tool_output", "workspace_file"]


class ConversationArtifactShareResource(BaseModel):
    id: str
    target_conversation_id: str
    source_run_id: str
    source_version: int
    kind: Literal["tool_output", "workspace_file"]
    actor: str
    created_at: str
    revoked_at: Optional[str] = None
    revoked_by: str = ""


class ArtifactPageResource(BaseModel):
    artifacts: list[ArtifactResource]
    limit: int
    offset: int
    next_offset: Optional[int] = None


class ConversationArtifactPageResource(BaseModel):
    artifacts: list[ArtifactResource]
    limit: int
    next_cursor: Optional[str] = None


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
    auth_type: str
    output_token_limit_enforced: bool
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


class CompatibilityEvidenceResource(BaseModel):
    title: str
    url: str
    observed_on: str


class CompatibilityRequestMappingResource(BaseModel):
    sent: list[str]
    omitted: list[str]


class CompatibilityRouteResource(BaseModel):
    id: str
    title: str
    state: Literal["supported", "experimental", "unavailable", "blocked"]
    harness: str
    api_shape: str
    auth_flow: str
    models: str
    streaming: str
    tool_calls: str
    structured_output: str
    vision: str
    context_limits: str
    cancellation: str
    usage_reporting: str
    quota_reporting: str
    retention: str
    hutch_request_mapping: CompatibilityRequestMappingResource
    verification: str
    verified_on: str
    policy_evidence: list[CompatibilityEvidenceResource]


class CompatibilityMatrixResource(BaseModel):
    version: int
    reviewed_on: str
    routes: list[CompatibilityRouteResource]


class ScheduleResource(BaseModel):
    id: str
    bot_id: str
    bot_name: str
    name: str
    cron: str
    timezone: str
    catch_up: str
    prompt: str = ""
    created_at: str
    paused: bool
    next_fire: Optional[str] = None
    last_dispatched: Optional[str] = None
    last_skip: Optional[dict] = None


class SchedulePut(BaseModel):
    name: str = Field(default="Scheduled task", min_length=1, max_length=80)
    cron: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    catch_up: CatchUpPolicy = CatchUpPolicy.coalesce
    prompt: str = Field(default="", max_length=4000)


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
                      "usage_reservations", "memory", "permissions", "devices", "transcript_mirrors", "state"]
    resource_id: str
    operation: Literal["created", "updated", "deleted"]
    ts: str
    context: dict[str, Optional[str]]


class ChangePageResource(BaseModel):
    changes: list[ResourceChange]
    cursor: str
    high_water: str
    has_more: bool


class FactPageResource(BaseModel):
    facts: list[MemoryItem]
    limit: int
    offset: int
    next_offset: Optional[int]


class FactProposeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = None


class FactReviewRequest(BaseModel):
    model_config = {"extra": "forbid"}
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    action: Literal['approve', 'archive', 'share']
    note: str = Field(default='', max_length=1000)


class FactReviewResource(BaseModel):
    fact_id: str
    result_id: str
    action: Literal['approve', 'archive', 'share']
    content_hash: str


class FactDecisionResource(BaseModel):
    fact_id: str
    result_id: str
    action: Literal['approve','archive','share']
    actor: str
    note: str
    created_at: str


class FactHistoryResource(FactPageResource):
    reviews: list[FactDecisionResource]


class ActionReconciliationRequest(BaseModel):
    model_config = {"extra": "forbid"}
    intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["confirmed_done", "confirmed_failed", "not_applied"]
    evidence: str = Field(min_length=1, max_length=4000)

    @field_validator('evidence')
    @classmethod
    def valid_evidence(cls, value: str) -> str:
        value.encode('utf-8')
        return value


class ActionSummaryResource(BaseModel):
    id: str
    run_id: str
    bot_name: str
    tool: str
    idem_key: str
    effect: str
    summary: str
    status: Literal["started", "done", "failed", "unknown"]
    started_at: str
    finished_at: Optional[str]
    result_digest: str
    intent_hash: str
    legacy: bool
    reconciliation: Optional[dict]


class ActionResource(ActionSummaryResource):
    effect_key: str
    intent: dict
    intent_valid: bool


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


class ChatGPTSignInRequest(BaseModel):
    account_id: Optional[str] = None


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

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError):
        # Do not echo private arguments/credentials, or unpaired Unicode that
        # would make the error response itself fail UTF-8 serialization.
        def safe(value):
            return value.encode('utf-8', errors='backslashreplace').decode() if isinstance(value, str) else value
        return JSONResponse(status_code=422, content={'detail': [
            {'loc': [safe(part) for part in error['loc']], 'type': safe(error['type']), 'msg': safe(error['msg'])}
            for error in exc.errors()
        ]})

    @app.exception_handler(ExecutionHeld)
    async def execution_held(_request: Request, exc: ExecutionHeld):
        return JSONResponse(status_code=409, content={'detail': str(exc), 'code': 'restore_review_required',
                                                      'restore_id': exc.restore_id})

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
        bot_data = bot.model_dump()
        if bot.creation_source is not None:
            # Keep the exact source request with the Bot's local durable record for
            # auditability, but do not repeat its full text in every roster/API view.
            bot_data["creation_source"] = bot.creation_source.model_dump(exclude={"original_request"})
        return {
            **bot_data,
            # Older records may have a workdir but no workspace_mode. Present the
            # effective choice so the settings control never hides an active folder.
            "workspace_mode": "folder" if bot.workdir else bot.workspace_mode,
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
            "memory_count": store.count_facts(bot.id),
            "sticky_allows": store.list_sticky_allows(bot.id),
        }

    def run_view(run) -> dict:
        bot = store.get_bot(run.bot_id)
        unresolved = store.count_unresolved_actions(run.id)
        return {**run.model_dump(), "bot_name": bot.name if bot else "?",
                "receipt_review_required": bool(unresolved), "unresolved_action_count": unresolved,
                "needs_person": run.needs_person or bool(unresolved)}

    def run_or_404(run_id: str):
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, f"no such run: {run_id}")
        return run

    def artifact_target(run, artifact_ref: str) -> Optional[Path]:
        """Resolve only a recorded run-local artifact; reject traversal and every symlink component."""
        if not isinstance(artifact_ref, str):
            return None
        relative = PurePosixPath(artifact_ref)
        if (str(relative) != artifact_ref or len(relative.parts) != 2 or relative.parts[0] != "artifacts"
                or not _ARTIFACT_NAME_RE.fullmatch(relative.name)
                or not re.fullmatch(r"[a-zA-Z0-9_-]{4,80}", run.id)):
            return None
        root = config.bots_dir
        try:
            if root.is_symlink() or not root.is_dir():
                return None
            bot = store.get_bot(run.bot_id)
            folders = [root / bot.name] if bot else list(root.iterdir())
            matches = []
            for folder in folders:
                runs = folder / "runs"
                run_dir = runs / run.id
                if (folder.is_symlink() or runs.is_symlink() or run_dir.is_symlink()
                        or not folder.is_dir() or not runs.is_dir() or not run_dir.is_dir()):
                    continue
                artifact_dir = run_dir / "artifacts"
                target = artifact_dir / relative.name
                if artifact_dir.is_symlink() or target.is_symlink() or not artifact_dir.is_dir():
                    continue
                info = target.lstat()
                if stat.S_ISREG(info.st_mode) and info.st_size <= _MAX_ARTIFACT_BYTES:
                    matches.append(target)
            if len(matches) == 1:
                return matches[0]
        except OSError:
            return None
        return None

    def artifact_resource(run, event, artifact_kind: str = "tool_output") -> ArtifactResource:
        data = event.data
        workspace_file = data.get("workspace_file") if isinstance(data.get("workspace_file"), dict) else {}
        is_workspace_file = artifact_kind == "workspace_file"
        artifact_ref = workspace_file.get("artifact", "") if is_workspace_file else data.get("artifact", "")
        stored_name = PurePosixPath(artifact_ref).name if isinstance(artifact_ref, str) else ""
        name = workspace_file.get("name", "") if is_workspace_file else stored_name
        digest = workspace_file.get("sha256", "") if is_workspace_file else data.get("artifact_sha256", "")
        has_hash = isinstance(digest, str) and bool(_ARTIFACT_SHA_RE.fullmatch(digest))
        target = artifact_target(run, artifact_ref) if has_hash else None
        state = "unverified" if not has_hash else "available" if target else "missing"
        size_bytes = workspace_file.get("bytes", 0) if is_workspace_file else data.get("artifact_bytes", 0)
        chars = data.get("chars", 0)
        return ArtifactResource(
            id=f"{run.id}:event:{event.seq}:{artifact_kind}", run_id=run.id, bot_id=run.bot_id,
            conversation_id=run.conversation_id or "", version=event.seq,
            source_tool=str(data.get("tool", "unknown"))[:80],
            kind="workspace_file" if is_workspace_file else "tool_output",
            filename=name[:120] if is_workspace_file and isinstance(name, str) else
            name if _ARTIFACT_NAME_RE.fullmatch(name) else "", sha256=digest if has_hash else "",
            size_bytes=(max(0, min(_MAX_ARTIFACT_BYTES, size_bytes)) if isinstance(size_bytes, int)
                        and not isinstance(size_bytes, bool) else 0),
            chars=(max(0, chars) if isinstance(chars, int) and not isinstance(chars, bool) else 0),
            created_at=event.ts, state=state,
            download_url=(f"/api/v1/tasks/runs/{run.id}/artifacts/{stored_name}" if state == "available" else None),
        )

    def read_artifact_file(run, filename: str) -> Optional[bytes]:
        """Read a run-local artifact through no-follow directory descriptors.

        Each path component is opened relative to its already-open parent. This
        prevents a replaced parent directory or symlink from redirecting the
        download after the list endpoint checked the path.
        """
        if not _ARTIFACT_NAME_RE.fullmatch(filename) or not re.fullmatch(r"[a-zA-Z0-9_-]{4,80}", run.id):
            return None
        bot = store.get_bot(run.bot_id)
        if bot is not None and not _SLUG_RE.fullmatch(bot.name):
            return None
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            root_fd = os.open(config.bots_dir, directory_flags)
        except OSError:
            return None
        matches: list[bytes] = []
        try:
            folder_names = [bot.name] if bot else os.listdir(root_fd)
            for folder_name in folder_names:
                descriptors: list[int] = []
                parent_fd = root_fd
                try:
                    for component in (folder_name, "runs", run.id, "artifacts"):
                        parent_fd = os.open(component, directory_flags, dir_fd=parent_fd)
                        descriptors.append(parent_fd)
                    file_fd = os.open(filename, file_flags, dir_fd=parent_fd)
                    try:
                        info = os.fstat(file_fd)
                        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_ARTIFACT_BYTES:
                            continue
                        with os.fdopen(file_fd, "rb", closefd=False) as stream:
                            content = stream.read(_MAX_ARTIFACT_BYTES + 1)
                        if len(content) <= _MAX_ARTIFACT_BYTES:
                            matches.append(content)
                    finally:
                        os.close(file_fd)
                except OSError:
                    continue
                finally:
                    for descriptor in reversed(descriptors):
                        os.close(descriptor)
        finally:
            os.close(root_fd)
        return matches[0] if len(matches) == 1 else None

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
        report = store.restoration_status()
        return {"status": "ok", "version": __version__, "schema": store.schema_version,
                "execution_held": bool(report and report['execution_held'])}

    @app.get('/api/v1/state/restore', response_model=RestorePageResource)
    def restoration_status(limit: int = 100, offset: int = 0) -> dict:
        if not 1 <= limit <= 200 or offset < 0:
            raise HTTPException(422, 'limit must be 1–200 and offset cannot be negative')
        report = store.restoration_status()
        return {'report': report, 'items': store.restoration_items(report['id'], limit=limit, offset=offset) if report else [],
                'limit': limit, 'offset': offset}

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

    @app.post("/api/v1/pairing/exchange", response_model=PairingExchangeResource)
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

    @app.get("/api/v1/devices", response_model=list[DeviceResource])
    def list_devices(request: Request) -> list[dict]:
        token = request.cookies.get(DEVICE_COOKIE, "")
        current = store.device_identity(token) if token else None
        return [{**device, "current": device["id"] == current}
                for device in store.list_device_sessions()]

    @app.post("/api/v1/devices/{device_id}/revoke", response_model=DeviceRevocationResource)
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
        trusted_proxy_configured = (os.environ.get("HUTCH_REMOTE_ENABLED") == "1" and
                                    bool(SecurityMiddleware._trusted_proxy_networks()) and
                                    bool(allowed_hosts_from_env()))
        from ..sandbox import offline_egress_status
        from ..tools.browser import local_handoff_status
        offline = offline_egress_status()
        handoff_ok, handoff_reason = local_handoff_status()
        offline_reason = ("Hutch's isolated worker blocked TCP to tested IPv4/IPv6 loopback and host-interface listeners, "
                          "and its PID namespace exposes only namespace processes; configured model traffic uses a "
                          "private per-run Unix socket broker. The separate local "
                          "inference service may still have its own network access." if offline.ok else
                          offline.reason)
        return [
            {"id": "process_executor", "status": "supported" if linux else "unavailable",
             "reason": "Linux process groups and boot/start identity are supported" if linux else
                       "Only Linux is supported for process execution", "verification": "offline_process_tests"},
            {"id": "strict_shell", "status": "experimental" if linux else "unavailable",
             "reason": "Linux bubblewrap/cgroup containment is required; shell networking is disabled",
             "verification": "host_dependent_sandbox_tests" if linux else "not_tested"},
            {"id": "strict_offline", "status": "experimental" if offline.ok else "unavailable",
             "reason": offline_reason,
             "verification": "network_pid_namespace_tcp_unix_socket_probe"},
            {"id": "remote_pairing", "status": "experimental",
             "reason": "Direct HTTPS pairing is fixture-tested; no live network or phone validation",
             "verification": "offline_fixtures"},
            {"id": "trusted_https_proxy", "status": "experimental" if trusted_proxy_configured else "unavailable",
             "reason": ("An operator-configured trusted proxy and public-host allowlist are set; only local forwarding fixtures "
                        "have been checked, with no real tunnel or network validation" if trusted_proxy_configured else
                        "Requires --allow-remote, HUTCH_TRUSTED_PROXIES and HUTCH_ALLOWED_HOSTS"),
             "verification": "local_forwarded_scope_fixtures" if trusted_proxy_configured else "configuration_required"},
            {"id": "phone_control", "status": "unavailable",
             "reason": "No phone control surface or authenticated interactive control route is implemented",
             "verification": "not_tested"},
            {"id": "browser_handoff", "status": "experimental" if handoff_ok else "unavailable",
             "reason": handoff_reason if not handoff_ok else
                      "Local Linux desktop only: Hutch pauses the owned browser process while a person completes a challenge; no phone control",
             "verification": "host_display_and_playwright_check" if handoff_ok else "host_prerequisite_check"},
            {"id": "external_runtimes", "status": "unavailable",
             "reason": "Pi and OpenCode lack governed permission, sandbox and budget integration",
             "verification": "adapter_start_refusal_tests"},
        ]

    @app.get("/api/v1/compatibility", response_model=CompatibilityMatrixResource)
    def compatibility() -> dict:
        from ..compat import compatibility_matrix
        return compatibility_matrix()

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
                         "auth_type": conn.auth_type,
                         "output_token_limit_enforced": conn.output_token_limit_enforced,
                         "key_present": book.has_key(name), "key_source": book.key_source(name),
                         "terms_status": book.ack_status(store, name), "terms_url": conn.terms.url,
                         "quota_window": conn.quota.window, "quota_tokens": conn.quota.tokens,
                         "quota_used_tokens": quota_used, "quota_reserved_tokens": quota_reserved,
                         "account_daily_cost_used_usd": account_cost_used,
                         "account_daily_cost_reserved_usd": account_cost_reserved,
                         "models_endpoint": conn.models_endpoint})
        return rows

    @app.get("/api/v1/schedules", response_model=list[ScheduleResource])
    def list_schedules(bot: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict]:
        bot_id = bot_or_404(bot).id if bot else None
        rows = []
        for bot in store.list_bots():
            if bot_id and bot.id != bot_id:
                continue
            for scheduled in bot.schedules or ([bot.schedule] if bot.schedule else []):
                nxt = scheduler.next_fire(bot, schedule=scheduled)
                rows.append({"id": scheduled.id, "bot_id": bot.id, "bot_name": bot.name,
                             "name": scheduled.name, "cron": scheduled.cron, "timezone": scheduled.timezone,
                             "catch_up": scheduled.catch_up.value, "prompt": scheduled.prompt,
                             "created_at": scheduled.created_at, "paused": bot.paused,
                             "next_fire": nxt.isoformat() if nxt else None,
                             "last_dispatched": scheduler._last_dispatched(bot, scheduled).isoformat(),
                             "last_skip": scheduler.last_skip(bot, scheduled)})
        start = max(0, offset)
        return rows[start:start + max(1, min(limit, 100))]

    @app.put("/api/v1/bots/{ref}/schedules/{schedule_id}", response_model=ScheduleResource)
    def put_schedule(ref: str, schedule_id: str, body: SchedulePut) -> dict:
        bot = bot_or_404(ref)
        from croniter import croniter
        if len(body.cron.split()) != 5 or not croniter.is_valid(body.cron):
            raise HTTPException(422, "cron must be a valid five-field schedule")
        try:
            ZoneInfo(body.timezone)
        except Exception:
            raise HTTPException(422, "timezone must be a valid IANA time zone") from None
        try:
            schedule = Schedule(id=schedule_id, name=body.name, cron=body.cron, timezone=body.timezone,
                                catch_up=body.catch_up, prompt=body.prompt)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        try:
            updated = store.put_schedule(bot.id, schedule)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        if updated is None:
            raise HTTPException(404, f"no such bot: {ref}")
        saved = next(item for item in updated.schedules if item.id == schedule_id)
        nxt = scheduler.next_fire(updated, schedule=saved)
        return {"id": saved.id, "bot_id": updated.id, "bot_name": updated.name, "name": saved.name,
                "cron": saved.cron, "timezone": saved.timezone, "catch_up": saved.catch_up.value,
                "prompt": saved.prompt, "created_at": saved.created_at, "paused": updated.paused,
                "next_fire": nxt.isoformat() if nxt else None,
                "last_dispatched": scheduler._last_dispatched(updated, saved).isoformat(),
                "last_skip": scheduler.last_skip(updated, saved)}

    @app.delete("/api/v1/bots/{ref}/schedules/{schedule_id}", status_code=204)
    def remove_schedule(ref: str, schedule_id: str) -> Response:
        bot = bot_or_404(ref)
        try:
            updated = store.delete_schedule(bot.id, schedule_id)
        except KeyError:
            raise HTTPException(404, f"no such scheduled task: {schedule_id}") from None
        if updated is None:
            raise HTTPException(404, f"no such bot: {ref}")
        return Response(status_code=204)

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

    @app.get("/api/v1/conversations/{conversation_id}/export", response_model=ConversationExportResource)
    def export_conversation(conversation_id: str, response: Response) -> ConversationExportResource:
        snapshot = store.conversation_export_snapshot(
            conversation_id, max_messages=MAX_CONVERSATION_EXPORT_MESSAGES,
            max_source_bytes=MAX_CONVERSATION_EXPORT_SOURCE_BYTES)
        if snapshot is None:
            raise HTTPException(404, f"no such conversation: {conversation_id}")
        if snapshot["limit"] == "messages":
            raise HTTPException(
                413, "Conversation export is limited to 10,000 messages; use the paginated conversation API.")
        if snapshot["limit"] == "bytes":
            raise HTTPException(413, "Conversation export source data exceeds 2 MiB; use the paginated conversation API.")

        resource = ConversationExportResource(
            format="hutch-conversation-export-v1",
            scope=ConversationExportScope(
                included=["conversation metadata", "ordered message text and provenance"],
                excluded=["stored provider credentials and connection secrets", "tool receipts", "action receipts",
                          "workspace content", "artifact bytes", "memory records"],
                notice="Message text is included verbatim. Review it for sensitive content before sharing the file.",
            ),
            conversation=snapshot["conversation"], messages=snapshot["messages"],
        )
        if len(resource.model_dump_json().encode("utf-8")) > MAX_CONVERSATION_EXPORT_BYTES:
            raise HTTPException(413, "Conversation export exceeds 16 MiB; use the paginated conversation API.")
        response.headers["Content-Disposition"] = 'attachment; filename="hutch-conversation-export.json"'
        response.headers["Cache-Control"] = "no-store"
        return resource

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

    @app.get("/api/v1/conversations/{conversation_id}/messages/{message_id}",
             response_model=ConversationMessageResource)
    def get_conversation_message(conversation_id: str, message_id: str) -> dict:
        message = store.get_conversation_message(conversation_id, message_id)
        if message is None:
            # Keep absent and cross-conversation message IDs indistinguishable.
            raise HTTPException(404, "no such Bot message in this conversation")
        return message

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
        # A restore hold governs the whole executor. Report it before model
        # setup or request-specific checks so a stale/unavailable route cannot
        # obscure the operator review that is currently required.
        store.assert_execution_ready()
        from ..modelchoices import ModelNotUsable, validate_override
        try:
            model = validate_override(config, store, bot, body.model or "")
        except ModelNotUsable as exc:
            raise HTTPException(exc.status, f"{exc} - {exc.fix}" if exc.fix else str(exc)) from None
        key = idempotency_key(request)
        request_body = body.model_dump(exclude={"reply_to_message_id"})
        if body.reply_to_message_id is not None:
            request_body["reply_to_message_id"] = body.reply_to_message_id
        digest = request_digest({"conversation_id": conversation_id, **request_body})
        run = Run(bot_id=bot.id, prompt=body.prompt, origin="manual:api", rehearsal=body.rehearse,
                  model_override="" if model == bot.model else model)
        task = Task(bot_id=bot.id, kind="on_demand", prompt=body.prompt)
        try:
            run_id, created = store.submit_conversation_message(
                conversation_id, body.prompt, run, task, idem_key=key, request_hash=digest,
                reply_to_message_id=body.reply_to_message_id)
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

    @app.get("/api/v1/model-routes")
    def model_routes_v1(inference_mode: InferenceMode = InferenceMode.hybrid) -> list[dict]:
        """Return route choices for setup without creating a bot or run."""
        from ..modelchoices import choices_json, model_choices
        draft = Bot(name="bot-setup-draft", model="", tools=[], inference_mode=inference_mode)
        return choices_json(model_choices(config, store, draft))

    def _checked_workdir(raw: str) -> str:
        from ..workdir import validate_workdir
        try:
            return str(validate_workdir(raw, config.state_dir))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    def _checked_tool_limits(limits: dict[str, int]) -> dict[str, int]:
        """PF-2 per-tool output caps: known tools only, 0 (unlimited) to 10M chars."""
        out: dict[str, int] = {}
        for tool, val in limits.items():
            if tool not in ALL_TOOL_NAMES:
                raise HTTPException(422, f"unknown tool: {tool}")
            if not 0 <= int(val) <= 10_000_000:
                raise HTTPException(422, f"limit for {tool} must be 0..10000000 chars")
            out[tool] = int(val)
        return out

    def _checked_rules(rules: list[CommandRule]) -> list[CommandRule]:
        from ..safety import MAX_RULES
        if len(rules) > MAX_RULES:
            raise HTTPException(422, f"at most {MAX_RULES} command rules")
        return rules

    def bot_from_create_request(body: BotCreate, *, creation_source: Optional[BotCreationSource] = None) -> Bot:
        if not _SLUG_RE.match(body.name):
            raise HTTPException(422, "name must be a lowercase slug (a-z, 0-9, -)")
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
        from ..providers.registry import validate_inference_mode, validate_offline_bot
        try:
            validate_inference_mode(body.inference_mode, bot.model, base_url=body.base_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        from ..modelchoices import ModelNotUsable, validate_override
        try:
            bot.model = validate_override(config, store, bot, body.model)
        except ModelNotUsable as exc:
            raise HTTPException(422, f"{exc} - {exc.fix}" if exc.fix else str(exc)) from None
        bot.inference_mode = body.inference_mode
        bot.base_url = body.base_url
        bot.tools = tools
        bot.memory_enabled = body.memory_enabled
        bot.approval_mode = body.approval_mode
        bot.risk_tier = body.risk_tier
        bot.local_browser_handoff = body.local_browser_handoff
        bot.creation_source = creation_source
        bot.command_rules = _checked_rules(body.command_rules)
        if body.limits is not None:
            bot.limits = body.limits
        if body.workdir:
            if body.workspace_mode not in (None, "folder"):
                raise HTTPException(422, "choose folder workspace mode when supplying a folder path")
            bot.workdir = _checked_workdir(body.workdir)
            bot.workspace_mode = "folder"
        if body.workspace_mode is not None:
            if body.workspace_mode == "folder":
                if not bot.workdir:
                    raise HTTPException(422, "folder workspace mode requires an existing workdir")
            else:
                bot.workdir = None
            bot.workspace_mode = body.workspace_mode
        if body.schedule_prompt.strip() and not body.cron:
            raise HTTPException(422, "a scheduled task prompt requires a cron schedule")
        if body.cron:
            try:
                bot.replace_primary_schedule(Schedule(cron=body.cron, timezone=body.timezone,
                                                      catch_up=body.catch_up, prompt=body.schedule_prompt))
            except Exception:
                raise HTTPException(422, "invalid schedule")
        try:
            validate_offline_bot(bot, check_host=body.inference_mode is InferenceMode.offline,
                                 refresh_host=body.inference_mode is InferenceMode.offline)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return bot

    @app.post("/api/v1/bots", status_code=201)
    def create_bot_v1(body: BotCreate, request: Request, response: Response) -> dict:
        key = idempotency_key(request)
        digest = request_digest(body.model_dump(mode="json"))
        try:
            replay = store.replay_bot_creation(key, digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        if replay is not None:
            response.status_code = 200
            return bot_view(replay)
        if store.get_bot(body.name):
            raise HTTPException(409, f"bot already exists: {body.name}")
        source_conversation_id = body.source_conversation_id
        source_message_id = body.source_message_id
        if bool(source_conversation_id) != bool(source_message_id):
            raise HTTPException(422, "source_conversation_id and source_message_id must be provided together")
        creation_source = None
        if source_conversation_id and source_message_id:
            conversation = store.get_conversation(source_conversation_id)
            message = store.get_conversation_user_message(source_conversation_id, source_message_id)
            if conversation is None or message is None:
                raise HTTPException(404, "no such user message in the source conversation")
            if len(message["content"]) > 20_000:
                raise HTTPException(422, "source message exceeds the 20,000-character bot-draft limit")
            creation_source = BotCreationSource(
                conversation_id=source_conversation_id,
                message_id=source_message_id,
                source_bot_id=conversation["bot_id"],
                sequence=message["seq"],
                created_at=message["created_at"],
                original_request=message["content"],
            )
        bot = bot_from_create_request(body, creation_source=creation_source)
        try:
            saved, created = store.create_bot_idempotent(bot, idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except BotConflict as exc:
            raise HTTPException(409, str(exc)) from None
        response.status_code = 201 if created else 200
        return bot_view(saved)

    @app.post("/api/bots", status_code=201)
    def create_bot(body: BotCreate) -> dict:
        if body.source_conversation_id or body.source_message_id:
            raise HTTPException(422, "chat-sourced Bot creation requires the versioned /api/v1/bots route")
        if not _SLUG_RE.match(body.name):
            raise HTTPException(422, "name must be a lowercase slug (a-z, 0-9, -)")
        if store.get_bot(body.name):
            raise HTTPException(409, f"bot already exists: {body.name}")
        bot = bot_from_create_request(body)
        store.create_bot(bot)
        return bot_view(bot)

    @app.get("/api/bots/{ref}")
    def get_bot(ref: str) -> dict:
        bot = bot_or_404(ref)
        view = bot_view(bot)
        view["recent_runs"] = [run_view(r) for r in store.list_runs(bot.id, limit=10)]
        # This legacy resource has no conversation scope. Only return reviewed
        # bot-wide references; private chat facts belong to the scoped v1 route.
        view["memory"] = [m.model_dump() for m in store.shared_facts(bot.id)]
        return view

    @app.patch("/api/bots/{ref}")
    def patch_bot(ref: str, body: BotPatch) -> dict:
        bot = bot_or_404(ref)
        changing_runtime = body.runtime is not None and bot.runtime.value != body.runtime
        if changing_runtime:
            active = store.active_run_for_bot(bot.id)
            if active is not None:
                raise HTTPException(409, f"Stop or finish active run {active.id} before changing this bot's runtime")
        proposed_tools = None
        if body.tools is not None:
            proposed_tools = expand_tools(body.tools)
            unknown = [tool for tool in proposed_tools if tool not in ALL_TOOL_NAMES]
            if unknown:
                raise HTTPException(422, f"unknown tools: {unknown}")
        schedule_update_requested = body.clear_cron or body.cron is not None or body.timezone is not None \
            or body.schedule_prompt is not None
        from ..providers.registry import validate_inference_mode, validate_offline_bot
        proposed_mode = body.inference_mode if body.inference_mode is not None else bot.inference_mode
        proposed_model = body.model if body.model is not None else bot.model
        proposed_runtime = RuntimeKind(body.runtime) if body.runtime is not None else bot.runtime
        if body.model is not None or changing_runtime:
            from ..modelchoices import ModelNotUsable, validate_override
            policy_bot = bot.model_copy(update={"inference_mode": proposed_mode, "runtime": proposed_runtime})
            try:
                proposed_model = validate_override(config, store, policy_bot,
                                                   body.model if body.model is not None else proposed_model)
            except ModelNotUsable as exc:
                raise HTTPException(422, f"{exc} - {exc.fix}" if exc.fix else str(exc)) from None
        try:
            validate_inference_mode(proposed_mode, proposed_model, base_url=bot.base_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if body.description is not None: bot.description = body.description
        if body.instructions is not None: bot.instructions = body.instructions
        if body.model is not None: bot.model = body.model
        if changing_runtime: bot.runtime = proposed_runtime
        if body.inference_mode is not None: bot.inference_mode = body.inference_mode
        if proposed_tools is not None: bot.tools = proposed_tools
        if body.memory_enabled is not None: bot.memory_enabled = body.memory_enabled
        if body.approval_mode is not None: bot.approval_mode = body.approval_mode
        if body.risk_tier is not None: bot.risk_tier = body.risk_tier
        if body.local_browser_handoff is not None: bot.local_browser_handoff = body.local_browser_handoff
        if body.limits is not None: bot.limits = body.limits
        if body.tool_limits is not None: bot.tool_limits = _checked_tool_limits(body.tool_limits)
        if body.command_rules is not None: bot.command_rules = _checked_rules(body.command_rules)
        if body.workdir is not None: bot.workdir = _checked_workdir(body.workdir) if body.workdir else None
        if body.workspace_mode is not None:
            if body.workspace_mode == "folder":
                if not bot.workdir:
                    raise HTTPException(422, "folder workspace mode requires an existing workdir")
            else:
                bot.workdir = None
            bot.workspace_mode = body.workspace_mode
        elif body.workdir is not None:
            bot.workspace_mode = "folder" if bot.workdir else "fresh"
        if body.paused is not None: bot.paused = body.paused
        if body.clear_cron:
            if body.schedule_prompt and body.schedule_prompt.strip():
                raise HTTPException(422, "a scheduled task prompt requires a cron schedule")
            bot.replace_primary_schedule(None)
        else:
            cron = body.cron or (bot.schedule.cron if bot.schedule else None)
            tz = body.timezone or (bot.schedule.timezone if bot.schedule else "UTC")
            task_prompt = (bot.schedule.prompt if bot.schedule else "")
            if body.schedule_prompt is not None:
                task_prompt = body.schedule_prompt.strip()
            if cron:
                previous = bot.schedule
                replacement = Schedule(cron=cron, timezone=tz,
                                       catch_up=previous.catch_up if previous else CatchUpPolicy.coalesce,
                                       prompt=task_prompt)
                if previous:
                    replacement = Schedule(id=previous.id, name=previous.name, created_at=previous.created_at,
                                           cron=replacement.cron, timezone=replacement.timezone,
                                           catch_up=replacement.catch_up, prompt=replacement.prompt)
                bot.replace_primary_schedule(replacement)
            elif task_prompt:
                raise HTTPException(422, "a scheduled task prompt requires a cron schedule")
        try:
            validate_offline_bot(bot, check_host=body.inference_mode is InferenceMode.offline,
                                 refresh_host=proposed_mode is InferenceMode.offline)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        try:
            if schedule_update_requested:
                bot = store.upsert_bot(bot, primary_schedule_update=None if body.clear_cron else bot.schedule,
                                       require_no_active_runs=changing_runtime)
            else:
                bot = store.upsert_bot(bot, preserve_schedules=True,
                                       require_no_active_runs=changing_runtime)
        except ActiveRunConflict as exc:
            raise HTTPException(409, f"Stop or finish active run {exc.run_id} before changing this bot's runtime") from None
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
        return {"forgot": key, "operation": "archived", "scope": "all facts with this key for this bot", "history_retained": True}

    @app.get('/api/v1/bots/{ref}/facts', response_model=FactPageResource)
    def list_facts(ref: str, conversation_id: str | None = None, all_scopes: bool = False,
                   query: str = '', limit: int = 50, offset: int = 0, include_archived: bool = False) -> dict:
        bot = bot_or_404(ref)
        if not 1 <= limit <= 100 or offset < 0 or len(query) > 256:
            raise HTTPException(422, 'limit must be 1–100; offset nonnegative; query at most 256 characters')
        if all_scopes and conversation_id:
            raise HTTPException(422, 'choose one chat or explicitly request all scopes')
        try:
            facts = store.fact_page(bot.id, conversation_id=conversation_id, admin=all_scopes,
                                    query=query, limit=limit, offset=offset, include_archived=include_archived)
        except KeyError:
            raise HTTPException(404, 'no such conversation for this bot') from None
        return {'facts': facts, 'limit': limit, 'offset': offset,
                'next_offset': offset + limit if len(facts) == limit else None}

    @app.get('/api/v1/bots/{ref}/facts/{fact_id}/history', response_model=FactHistoryResource)
    def fact_history(ref: str, fact_id: str, limit: int = 50, offset: int = 0):
        bot = bot_or_404(ref)
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(422, 'limit must be 1–100; offset nonnegative')
        try:
            return store.fact_history(bot.id, fact_id, limit=limit, offset=offset)
        except KeyError:
            raise HTTPException(404, 'no such fact for this bot') from None

    @app.post('/api/v1/bots/{ref}/facts', response_model=MemoryItem)
    def propose_fact(ref: str, body: FactProposeRequest, request: Request, response: Response):
        bot = bot_or_404(ref)
        key = idempotency_key(request)
        try:
            fact, created = store.propose_fact_command(bot.id, **body.model_dump(), idem_key=key,
                                                       request_hash=request_digest({'bot_id': bot.id, **body.model_dump()}))
        except KeyError:
            raise HTTPException(404, 'no such conversation for this bot') from None
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        response.status_code = 201 if created else 200
        return fact

    @app.post('/api/v1/bots/{ref}/facts/{fact_id}/review', response_model=FactReviewResource)
    def review_fact(ref: str, fact_id: str, body: FactReviewRequest, request: Request):
        bot = bot_or_404(ref)
        key = idempotency_key(request)
        token = request.cookies.get(DEVICE_COOKIE, '')
        bearer = request.headers.get('authorization', '')
        if bearer.startswith('Bearer '): token = bearer[7:]
        device = store.device_identity(token)
        actor = f'device:{device}' if device else 'operator'
        try:
            return store.review_fact(bot.id, fact_id, **body.model_dump(), actor=actor, idem_key=key,
                                     request_hash=request_digest({'bot_id': bot.id, 'fact_id': fact_id,
                                                                  'actor': actor, **body.model_dump()}))
        except (FactConflict, IdempotencyConflict) as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/bots/{ref}/run", status_code=201)
    def run_bot(ref: str, body: RunRequest) -> dict:
        store.assert_execution_ready()
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

    @app.post("/api/v1/tasks/runs", response_model=dict)
    def create_run_v1(body: VersionedRunCreateRequest, request: Request, response: Response) -> dict:
        key = idempotency_key(request)
        digest = request_digest(body.model_dump())
        try:
            replay = store.replay_submitted_run(key, digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        if replay is not None:
            response.status_code = 200
            return {**run_view(replay), "replayed": True}

        # A restore hold is reported before route validation for new commands.
        # Exact retries above return the already admitted run without authorizing
        # another dispatch or hiding its result behind mutable host configuration.
        bot = bot_or_404(body.bot)
        store.assert_execution_ready()
        from ..modelchoices import ModelNotUsable, validate_override
        try:
            model = validate_override(config, store, bot, body.model or "")
        except ModelNotUsable as exc:
            raise HTTPException(exc.status, f"{exc} - {exc.fix}" if exc.fix else str(exc)) from None
        try:
            run, created = engine.submit_idempotent(
                bot, body.prompt, idem_key=key, request_hash=digest, rehearsal=body.rehearse,
                model="" if model == bot.model else model)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        response.status_code = 201 if created else 200
        return {**run_view(run), "replayed": not created}

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
        view["transcript_mirror"] = store._mirror.status(run_id)
        view["unknown_actions"] = store.list_actions(run_id, unresolved=True, limit=5)
        view["reviewed_actions"] = store.list_actions(run_id, reviewed=True, limit=5)
        view["event_count"] = total
        view["events_truncated"] = bool(window) and window[0].seq > 1
        return view

    @app.get("/api/v1/tasks/runs/{run_id}/artifacts", response_model=ArtifactPageResource)
    def list_run_artifacts(run_id: str, limit: int = 50, offset: int = 0) -> ArtifactPageResource:
        run = run_or_404(run_id)
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(422, "limit must be 1–100; offset must be nonnegative")
        records = store.artifact_records(run.id, limit=limit + 1, offset=offset)
        has_more = len(records) > limit
        items = [artifact_resource(run, event, kind) for event, kind in records[:limit]]
        return ArtifactPageResource(artifacts=items, limit=limit, offset=offset,
                                    next_offset=offset + limit if has_more else None)

    @app.get("/api/v1/conversations/{conversation_id}/artifacts", response_model=ConversationArtifactPageResource)
    def list_conversation_artifacts(conversation_id: str, limit: int = 50,
                                    cursor: Optional[str] = None) -> ConversationArtifactPageResource:
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(404, f"no such conversation: {conversation_id}")
        if not 1 <= limit <= 100:
            raise HTTPException(422, "limit must be 1–100")
        records = store.conversation_artifact_records(
            conversation_id, conversation["bot_id"], limit=limit + 1,
            cursor=_decode_conversation_artifact_cursor(cursor))
        has_more = len(records) > limit
        items: list[ArtifactResource] = []
        for event, kind, share in records[:limit]:
            run = store.get_run(event.run_id)
            if run is None or event.run_id != run.id:
                continue
            if share["share_id"]:
                # The store query binds the active share to this exact target, source
                # run, event and artifact kind. Its download URL is a target-bound
                # capability so stopping the share also stops future downloads.
                base_item = artifact_resource(run, event, kind)
                item = base_item.model_copy(update={
                    **share,
                    "download_url": (f"/api/v1/conversations/{conversation_id}/artifact-shares/"
                                     f"{share['share_id']}/content")
                    if base_item.state == "available" else None,
                })
            else:
                # Recheck original ownership at the response boundary as well as in
                # the query; other chats stay private unless explicitly shared.
                if run.bot_id != conversation["bot_id"] or run.conversation_id != conversation_id:
                    continue
                base_item = artifact_resource(run, event, kind)
                active_shares = store.active_artifact_share_targets(
                    conversation_id, run.id, event.seq, kind)
                item = base_item.model_copy(update={
                    "shared_with": [ArtifactShareTargetResource(**share) for share in active_shares],
                })
            items.append(item)
        next_cursor = None
        if has_more:
            boundary_event, boundary_kind, _ = records[limit - 1]
            next_cursor = _encode_conversation_artifact_cursor(boundary_event.id, boundary_kind)
        return ConversationArtifactPageResource(artifacts=items, limit=limit, next_cursor=next_cursor)

    def artifact_share_resource(row: dict[str, Any]) -> ConversationArtifactShareResource:
        return ConversationArtifactShareResource(
            id=row["id"], target_conversation_id=row["target_conversation_id"],
            source_run_id=row["source_run_id"], source_version=row["source_version"],
            kind=row["artifact_kind"], actor=row["actor"], created_at=row["created_at"],
            revoked_at=row["revoked_at"], revoked_by=row["revoked_by"])

    @app.post("/api/v1/conversations/{conversation_id}/artifact-shares",
              response_model=ConversationArtifactShareResource)
    def share_conversation_artifact(conversation_id: str, body: ConversationArtifactShareRequest,
                                    request: Request, response: Response) -> ConversationArtifactShareResource:
        key = idempotency_key(request)
        digest = request_digest({"target_conversation_id": conversation_id, **body.model_dump()})
        try:
            replay = store.replay_conversation_artifact_share(conversation_id, idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        if replay is not None:
            response.status_code = 200
            return artifact_share_resource(replay)

        run = run_or_404(body.source_run_id)
        events = store.list_events(run.id, after_seq=body.source_version - 1, limit=1)
        if not events or events[0].seq != body.source_version:
            raise HTTPException(404, "source artifact version does not exist")
        event = events[0]
        item = artifact_resource(run, event, body.kind)
        if item.state != "available" or not item.download_url:
            raise HTTPException(409, "only available artifacts with a verified hash and size can be shared")
        data = event.data
        workspace_file = data.get("workspace_file") if isinstance(data.get("workspace_file"), dict) else {}
        artifact_ref = workspace_file.get("artifact", "") if body.kind == "workspace_file" else data.get("artifact", "")
        filename = PurePosixPath(artifact_ref).name if isinstance(artifact_ref, str) else ""
        content = read_artifact_file(run, filename)
        if content is None or len(content) != item.size_bytes or hashlib.sha256(content).hexdigest() != item.sha256:
            raise HTTPException(409, "artifact bytes do not match their recorded hash and size")
        token = request.cookies.get(DEVICE_COOKIE, "")
        bearer = request.headers.get("authorization", "")
        if bearer.startswith("Bearer "):
            token = bearer[7:]
        device = store.device_identity(token)
        actor = f"device:{device}" if device else "operator"
        try:
            row, created = store.share_conversation_artifact(
                conversation_id, run.id, body.source_version, body.kind, actor=actor,
                idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        response.status_code = 201 if created else 200
        return artifact_share_resource(row)

    @app.delete("/api/v1/conversations/{conversation_id}/artifact-shares/{share_id}",
                response_model=ConversationArtifactShareResource)
    def revoke_conversation_artifact_share(conversation_id: str, share_id: str,
                                           request: Request) -> ConversationArtifactShareResource:
        key = idempotency_key(request)
        digest = request_digest({"command": "revoke_artifact_share", "conversation_id": conversation_id,
                                 "share_id": share_id})
        token = request.cookies.get(DEVICE_COOKIE, "")
        bearer = request.headers.get("authorization", "")
        if bearer.startswith("Bearer "):
            token = bearer[7:]
        device = store.device_identity(token)
        actor = f"device:{device}" if device else "operator"
        try:
            row, _changed = store.revoke_conversation_artifact_share(
                conversation_id, share_id, actor=actor, idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except KeyError:
            raise HTTPException(404, "no such shared artifact") from None
        return artifact_share_resource(row)

    def verified_artifact_response(run, event: Event, artifact_kind: str, filename: str) -> Response:
        if not _ARTIFACT_NAME_RE.fullmatch(filename) or event.type is not EventType.tool_result:
            raise HTTPException(404, "no such artifact")
        data = event.data
        workspace_file = data.get("workspace_file") if isinstance(data.get("workspace_file"), dict) else {}
        artifact_ref = workspace_file.get("artifact", "") if artifact_kind == "workspace_file" else data.get("artifact", "")
        if artifact_ref != f"artifacts/{filename}":
            raise HTTPException(404, "no such artifact")
        is_workspace_file = artifact_kind == "workspace_file"
        expected_hash = workspace_file.get("sha256", "") if is_workspace_file else data.get("artifact_sha256", "")
        expected_bytes = workspace_file.get("bytes") if is_workspace_file else data.get("artifact_bytes")
        if (not isinstance(expected_hash, str) or not _ARTIFACT_SHA_RE.fullmatch(expected_hash)
                or not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool)
                or not 0 <= expected_bytes <= _MAX_ARTIFACT_BYTES):
            raise HTTPException(409, "this historical artifact has no verifiable content hash")
        content = read_artifact_file(run, filename)
        if content is None:
            raise HTTPException(404, "artifact file is missing or is not a regular run-local file")
        if len(content) != expected_bytes:
            raise HTTPException(409, "artifact size no longer matches its recorded version")
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected_hash:
            raise HTTPException(409, "artifact failed its recorded SHA-256 integrity check")
        if is_workspace_file:
            requested_name = workspace_file.get("name", "")
            download_name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(requested_name)).strip("._-")[:120]
            download_name = download_name or filename
        else:
            download_name = filename
        return Response(content=content, media_type="text/plain; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "Cache-Control": "no-store", "ETag": f'"{digest}"',
            "X-Content-Type-Options": "nosniff", "X-Hutch-Artifact-Verified": "sha256",
        })

    @app.get("/api/v1/conversations/{conversation_id}/artifact-shares/{share_id}/content")
    def download_shared_conversation_artifact(conversation_id: str, share_id: str) -> Response:
        share = store.active_conversation_artifact_share(conversation_id, share_id)
        if share is None:
            raise HTTPException(404, "no active share for this chat")
        run = run_or_404(share["source_run_id"])
        events = store.list_events(run.id, after_seq=share["source_version"] - 1, limit=1)
        if not events or events[0].seq != share["source_version"]:
            raise HTTPException(404, "shared artifact history is unavailable")
        return verified_artifact_response(run, events[0], share["artifact_kind"],
                                          PurePosixPath((events[0].data.get("workspace_file", {}) or {}).get("artifact", "")
                                                        if share["artifact_kind"] == "workspace_file"
                                                        else events[0].data.get("artifact", "")).name)

    @app.get("/api/v1/tasks/runs/{run_id}/artifacts/{filename}")
    def download_run_artifact(run_id: str, filename: str) -> Response:
        run = run_or_404(run_id)
        if not _ARTIFACT_NAME_RE.fullmatch(filename):
            raise HTTPException(404, "no such artifact")
        artifact_ref = f"artifacts/{filename}"
        event = store.artifact_event(run.id, artifact_ref)
        if event is None:
            raise HTTPException(404, "no such artifact")
        data = event.data
        workspace_file = data.get("workspace_file") if isinstance(data.get("workspace_file"), dict) else {}
        is_workspace_file = workspace_file.get("artifact") == artifact_ref
        return verified_artifact_response(run, event, "workspace_file" if is_workspace_file else "tool_output", filename)

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

    @app.get("/api/runs/{run_id}/artifacts/{rel_path:path}")
    def run_artifact(run_id: str, rel_path: str) -> Response:
        """Compatibility alias for the verified run-artifact endpoint."""
        run = run_or_404(run_id)
        relative = PurePosixPath("artifacts") / PurePosixPath(rel_path)
        if (str(relative) != f"artifacts/{rel_path}" or len(relative.parts) != 2
                or not _ARTIFACT_NAME_RE.fullmatch(relative.name)):
            raise HTTPException(404, "no such artifact")
        artifact_ref = str(relative)
        event = store.artifact_event(run_id, artifact_ref)
        if event is None:
            raise HTTPException(404, "no such artifact")
        workspace_file = event.data.get("workspace_file")
        kind = ("workspace_file" if isinstance(workspace_file, dict)
                and workspace_file.get("artifact") == artifact_ref else "tool_output")
        response = verified_artifact_response(run, event, kind, relative.name)
        # The compatibility source card opens readable plain text in a tab. The
        # versioned API retains attachment semantics for explicit downloads.
        response.headers["Content-Disposition"] = "inline"
        return response

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

    @app.post("/api/v1/tasks/runs/{run_id}/resume", response_model=dict)
    def resume_run_v1(run_id: str, body: ResumeRunRequest, request: Request) -> dict:
        key = idempotency_key(request)
        digest = request_digest({"command": "human-resume", "run_id": run_id,
                                 "human_event_seq": body.human_event_seq})
        try:
            result, created = store.resume_run_idempotent(
                run_id, body.human_event_seq, idem_key=key, request_hash=digest)
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except KeyError:
            raise HTTPException(404, f"no such run: {run_id}") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"resumed": result["run_id"], "human_event_seq": result["human_event_seq"],
                "replayed": not created}

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

    @app.get("/api/v1/actions/receipts", response_model=list[ActionSummaryResource])
    def action_receipts(run_id: Optional[str] = None, unresolved: bool = False, reviewed: bool = False,
                        limit: int = 100, offset: int = 0) -> list[dict]:
        if run_id is not None:
            run_or_404(run_id)
        return store.list_actions(run_id, unresolved=unresolved, reviewed=reviewed, limit=limit, offset=offset)

    @app.get("/api/v1/actions/receipts/{action_id}", response_model=ActionResource)
    def action_receipt(action_id: str) -> dict:
        action = store.get_action(action_id)
        if action is None:
            raise HTTPException(404, "no such action receipt")
        return action

    @app.post("/api/v1/actions/receipts/{action_id}/reconcile", response_model=ActionResource)
    def reconcile_action(action_id: str, body: ActionReconciliationRequest, request: Request, response: Response) -> dict:
        key = idempotency_key(request)
        token = request.cookies.get(DEVICE_COOKIE, "")
        bearer = request.headers.get("authorization", "")
        if bearer.startswith("Bearer "):
            token = bearer[7:]
        device = store.device_identity(token)
        by = f"device:{device}" if device else "operator"
        digest = request_digest({"action_id": action_id, **body.model_dump()})
        try:
            action, created = store.reconcile_action(action_id, by=by, idem_key=key, request_hash=digest, **body.model_dump())
        except KeyError:
            raise HTTPException(404, "no such action receipt") from None
        except (ActionConflict, IdempotencyConflict) as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        response.status_code = 201 if created else 200
        return action

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
            "unresolved_actions": store.count_unresolved_actions(),
            "execution_held": bool((report := store.restoration_status()) and report['execution_held']),
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
                "has_key": book.has_key(name), "key_source": book.key_source(name),
                "auth_type": c.auth_type,
                "output_token_limit_enforced": c.output_token_limit_enforced,
                "ack": book.ack_status(store, name),
                "terms_notice": c.terms.notice, "terms_url": getattr(c.terms, "url", ""),
                "quota_window": c.quota.window, "quota_tokens": c.quota.tokens, "warn_at": c.quota.warn_at,
                "used": used, "quota_hint": c.quota_hint, "get_key_url": c.get_key_url,
                "signin_guidance": book.templates().get(c.template, {}).get("signin_guidance", ""),
            })
        from ..chatgpt_auth import ChatGPTAuthBook, chatgpt_plan_signin_enabled
        templates = [{"key": k, "title": v.get("title", k), "billing": v.get("billing", ""),
                      "base_url": v.get("base_url", ""), "terms_notice": (v.get("terms") or {}).get("notice", "")}
                     for k, v in book.templates().items()]
        accounts = ChatGPTAuthBook(config.state_dir).accounts()
        return {"connections": out, "templates": templates, "errors": book.errors,
                "chatgpt_enabled": chatgpt_plan_signin_enabled(), "chatgpt_accounts": accounts}

    @app.post("/api/chatgpt/sign-in")
    def chatgpt_sign_in(request: Request, body: ChatGPTSignInRequest) -> dict:
        from ..chatgpt_auth import (ChatGPTAuthBook, ChatGPTAuthError, chatgpt_plan_signin_enabled,
                                    loopback_callback_uri)
        if not chatgpt_plan_signin_enabled():
            raise HTTPException(409, "Sign in with ChatGPT is an eligibility-gated preview. Set HUTCH_ENABLE_CHATGPT_PLAN=1 only if Hutch is eligible for this flow.")
        try:
            callback = loopback_callback_uri(request)
            url = ChatGPTAuthBook(config.state_dir).start(callback, account_id=body.account_id or "")
        except (ChatGPTAuthError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        return {"authorization_url": url}

    @app.post("/api/chatgpt/accounts/{account_id}/disconnect")
    def chatgpt_disconnect(account_id: str) -> dict:
        from ..chatgpt_auth import ChatGPTAuthBook, ChatGPTAuthError
        from ..connections import ConnectionBook
        try:
            revoked = ChatGPTAuthBook(config.state_dir).disconnect(account_id)
            book = ConnectionBook(config.state_dir)
            for name, conn in book.configured().items():
                if conn.auth_type == "chatgpt-siws" and conn.auth_account_id == account_id:
                    book.remove(name)
        except ChatGPTAuthError as exc:
            raise HTTPException(404, str(exc)) from None
        detail = ("ChatGPT access revoked and removed from this Hutch." if revoked else
                  "Local ChatGPT credentials were cleared, but OpenAI did not confirm remote revocation.")
        return {"ok": True, "remote_revoked": revoked, "detail": detail}

    @app.get("/auth/callback", include_in_schema=False)
    def chatgpt_oauth_callback(request: Request):
        from ..chatgpt_auth import (ChatGPTAuthBook, ChatGPTAuthError, chatgpt_plan_signin_enabled,
                                    loopback_callback_uri)
        from ..connections import ConnectionBook
        if not chatgpt_plan_signin_enabled():
            raise HTTPException(404, "Sign in with ChatGPT preview is disabled.")
        try:
            callback = loopback_callback_uri(request)
            values: dict[str, str] = {}
            for key in ("state", "code", "client_id", "error"):
                entries = request.query_params.getlist(key)
                if len(entries) > 1:
                    raise ChatGPTAuthError("ChatGPT returned a duplicate sign-in field; start again")
                values[key] = entries[0] if entries else ""
            if not values["state"]:
                raise ChatGPTAuthError("ChatGPT did not return sign-in state; start again")
            result = ChatGPTAuthBook(config.state_dir).finish(
                state=values["state"], code=values["code"], returned_client_id=values["client_id"],
                error=values["error"], callback_uri=callback)
            if result["plan_usage"] == "enabled":
                ConnectionBook(config.state_dir).add_chatgpt_account(result["account_id"], result["email"])
            status = "connected" if result["plan_usage"] == "enabled" else "identity-only"
        except (ChatGPTAuthError, ValueError) as exc:
            status = "error"
            detail = str(exc)
        response = RedirectResponse(f"/?chatgpt_result={status}#/connections", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        if status == "error":
            response.headers["Location"] = f"/?chatgpt_result=error&detail={quote(str(detail))}#/connections"
        return response

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
            if book.get(name).auth_type != "api_key":
                raise HTTPException(422, "This connection uses a sign-in account. Manage it from Connections instead of setting an API key.")
            if not (body.key or "").strip():
                raise HTTPException(422, "The key was empty.")
            book.set_key(name, body.key.strip())      # written 0600; never echoed back
            return {"ok": True, "detail": f"Key stored for {name}."}
        if action == "clear-key":
            if book.get(name).auth_type != "api_key":
                raise HTTPException(422, "This connection uses a sign-in account. Disconnect the account from Connections instead.")
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
