"""Data model: bots, tasks, runs, events, approvals, memory.

Timestamps are ISO-8601 UTC strings with explicit offset — naive local times
are the root cause of the DST double-fire / missed-fire bugs documented in
docs/research/complaints.md, so we never store them.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def local_day_bounds(now: Optional[datetime] = None) -> tuple[str, str]:
    """[start, end) of the current LOCAL calendar day, as UTC ISO strings comparable with ``created_at``.

    A "daily" cap should reset at the user's midnight, and every daily figure (tokens, spend, runs) must use the same
    day. Timestamps are stored in UTC, so the local day is converted to UTC bounds; a day that is 23 or 25 hours long
    (DST) is handled because each boundary is converted from its own local midnight.
    """
    local = (now or utcnow()).astimezone()
    day = local.date()
    start = datetime.combine(day, time.min).astimezone()
    end = datetime.combine(day + timedelta(days=1), time.min).astimezone()
    return iso(start), iso(end)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RunStatus(str, Enum):
    """Where a run is in its life. The legal moves between these are defined once, in ``lifecycle.py`` (ADR-0003)."""

    pending = "pending"                    # queued: admitted, nobody owns it yet
    loading_model = "loading_model"        # cold-loading a local model (LM-6)
    running = "running"
    waiting_approval = "waiting_approval"
    waiting_human = "waiting_human"        # login / CAPTCHA wall: a person must act
    waiting_resources = "waiting_resources"  # a free model slot, memory, or an allowance reset
    recovering = "recovering"              # the owner was lost; recovery is deciding the outcome
    cancelling = "cancelling"              # a stop was requested and is not yet verified complete
    succeeded = "succeeded"
    failed = "failed"
    stopped = "stopped"                    # shown as "Cancelled"; the stored name is kept for compatibility
    outcome_unknown = "outcome_unknown"    # an action may or may not have happened: a person must review it
    skipped = "skipped"


#: statuses in which a run still holds (or is queued for) resources
ACTIVE_STATUSES = (
    RunStatus.pending, RunStatus.loading_model, RunStatus.running,
    RunStatus.waiting_approval, RunStatus.waiting_human, RunStatus.waiting_resources,
    RunStatus.recovering, RunStatus.cancelling,
)


class RuntimeKind(str, Enum):
    builtin = "builtin"      # hutch's own agent loop (OpenAI-compatible providers)
    mock = "mock"            # legacy value; unsupported outside the test harness
    pi = "pi"                # Pi coding agent, driven over RPC stdio
    opencode = "opencode"    # OpenCode, driven via `opencode run`


class InferenceMode(str, Enum):
    """Model routing policy. Local model routes do not by themselves mean the run is offline."""

    local = "local"          # local model routes only; tools retain their own network policy
    hybrid = "hybrid"        # hosted model routes remain available under Hutch's route governance
    offline = "offline"      # local model + verified worker egress isolation + network tools withheld


class CatchUpPolicy(str, Enum):
    """What to do when the machine was asleep/off across a scheduled fire time."""

    coalesce = "coalesce"    # run once, note how many windows were missed
    skip = "skip"            # never run for a past window


class TriggerKind(str, Enum):
    """How a routine chooses fire times. Calendar cron, fixed-rate interval, or one-shot."""

    cron = "cron"
    interval = "interval"
    once = "once"


class OverlapPolicy(str, Enum):
    """What to do when a new occurrence is due while this routine or bot is already busy."""

    queue = "queue"              # admit a pending run (per-bot single-instance still serializes execution)
    skip = "skip"                # drop this occurrence with a visible skip record
    buffer_one = "buffer_one"    # admit at most one pending run for this schedule


class Schedule(BaseModel):
    id: str = Field(default_factory=lambda: new_id("schedule"))
    name: str = Field(default="Scheduled task", max_length=80)
    trigger: TriggerKind = TriggerKind.cron
    cron: str = ""                     # 5-field cron when trigger=cron
    interval_seconds: Optional[int] = None  # fixed-rate seconds when trigger=interval (not cron approximation)
    anchor_at: Optional[str] = None    # ISO UTC anchor for interval / once; interval defaults to created_at
    timezone: str = "UTC"              # IANA name; calendar schedules fire in this zone
    catch_up: CatchUpPolicy = CatchUpPolicy.coalesce
    overlap: OverlapPolicy = OverlapPolicy.queue
    enabled: bool = True               # draft/disabled routines do not admit occurrences
    prompt: str = Field(default="", max_length=4000)  # task to perform; empty preserves legacy instruction fallback
    created_at: str = Field(default_factory=lambda: iso(utcnow()))

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("a scheduled task name is required")
        return value

    @field_validator("prompt")
    @classmethod
    def _prompt(cls, value: str) -> str:
        return value.strip()

    @field_validator("interval_seconds")
    @classmethod
    def _interval(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if value < 1 or value > 31_536_000:
            raise ValueError("interval_seconds must be between 1 and 31536000")
        return value

    @model_validator(mode="after")
    def _trigger_fields(self) -> "Schedule":
        if self.trigger is TriggerKind.cron:
            cron = self.cron.strip()
            if not cron:
                raise ValueError("cron trigger requires a five-field cron expression")
            object.__setattr__(self, "cron", cron)
        elif self.trigger is TriggerKind.interval:
            if not self.interval_seconds:
                raise ValueError("interval trigger requires interval_seconds")
            object.__setattr__(self, "cron", "")
        elif self.trigger is TriggerKind.once:
            if not (self.anchor_at or "").strip():
                raise ValueError("once trigger requires anchor_at")
            object.__setattr__(self, "cron", "")
        return self

    model_config = {"frozen": True}


class Limits(BaseModel):
    """Execution guards and estimate-based usage admission limits. 0 means no configured limit."""

    max_steps: int = 24                # agent turns before forced stop
    timeout_seconds: int = 900         # wall-clock kill switch
    daily_token_cap: int = 200_000     # estimated tokens (prompt+completion)
    max_turn_tokens: int = 0           # per-turn generation cap (SR-5); 0 = provider default (local 2048, hosted 16000)
    max_cost_usd: float = 0.0          # priced estimate admission limit for ONE run, hosted models only (SR-2, LM-9)
    daily_cost_cap_usd: float = 0.0    # priced estimate admission limit per bot per local day
    @field_validator("max_steps", "timeout_seconds")
    @classmethod
    def positive_execution_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("execution limits must be positive")
        return value

    @field_validator("daily_token_cap", "max_turn_tokens")
    @classmethod
    def nonnegative_token_limits(cls, value: int) -> int:
        if value < 0:
            raise ValueError("token limits must be non-negative")
        return value

    @field_validator("max_cost_usd", "daily_cost_cap_usd")
    @classmethod
    def finite_cost_limits(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("currency limits must be finite and non-negative")
        return value

    model_config = {"frozen": True}


class BackgroundProviderConsent(BaseModel):
    """Explicit authorization for one provider account and one Bot routing configuration."""

    provider: str = Field(min_length=1, max_length=80)
    account_id: str = Field(min_length=1, max_length=80)
    route_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    terms_revision: str = Field(min_length=1, max_length=32)
    granted_at: str = Field(default_factory=lambda: iso(utcnow()))


class Escalation(BaseModel):
    """Move up the ladder when a local model is not up to the job (LM-9) - one rung at a time."""

    to: list[str] = Field(default_factory=list)    # model specs, tried in order: e.g. ["anthropic/claude-opus-5-5"]
    ask_first: bool = True                         # LM-10: a local-default bot asks before its FIRST hosted call
    after_malformed: int = 2                       # consecutive malformed tool calls that trigger escalation
    on_loop: bool = True
    on_context_overflow: bool = True

    model_config = {"frozen": True}


class BotCreationSource(BaseModel):
    """One explicitly selected user message used to seed a reviewed Bot draft."""

    conversation_id: str
    message_id: str
    source_bot_id: str
    sequence: int
    created_at: str
    original_request: str = Field(max_length=20_000)

    model_config = {"frozen": True}


class RiskTier(str, Enum):
    """SR-12: what the bot may do. High-risk actions (secrets, exfiltration, privilege escalation) are always
    blocked; the tier decides what happens to MEDIUM-risk ones."""

    readonly = "readonly"      # medium-risk actions are blocked outright: a bot that can only look
    supervised = "supervised"  # medium-risk actions ask (default)
    trusted = "trusted"        # medium-risk actions run without asking (same as approval_mode auto)


class CommandRule(BaseModel):
    """Per-command refinement of the tier (SR-12): e.g. {match: "git push*", verdict: "deny"}."""

    match: str                                      # glob against each command segment (first matching rule wins)
    verdict: str                                    # allow | ask | deny

    model_config = {"frozen": True}

    @field_validator("verdict")
    @classmethod
    def _verdict(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("allow", "ask", "deny"):
            raise ValueError("verdict must be allow, ask or deny")
        return v

    @field_validator("match")
    @classmethod
    def _match(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("a rule pattern must be 1-200 characters")
        return v


class ApprovalMode(str, Enum):
    ask = "ask"        # ask before any non-read-only action unless sticky-allowed
    auto = "auto"      # auto-approve non-denied actions (denylist still enforced)


_BOT_NAME_ACRONYMS = {"ai": "AI", "api": "API", "ci": "CI", "cd": "CD", "crm": "CRM",
                      "hr": "HR", "qa": "QA", "sre": "SRE", "ui": "UI", "ux": "UX"}


def bot_slug_display_name(value: str) -> str:
    """Turn a legacy machine address into a stable human-facing fallback."""
    words = [word for word in re.split(r"[-_]+", value.strip()) if word]
    if not words:
        return "Workspace Assistant"
    return " ".join(_BOT_NAME_ACRONYMS.get(word.casefold(), word[:1].upper() + word[1:]) for word in words)


class Bot(BaseModel):
    id: str = Field(default_factory=lambda: new_id("bot"))
    name: str                         # slug, unique
    display_name: str = Field(default="", max_length=80)
    description: str = ""
    instructions: str = ""            # system-prompt level guidance
    model: str = ""                   # a configured provider/model route; empty legacy records need setup before use
    base_url: Optional[str] = None    # override for OpenAI-compatible endpoints
    runtime: RuntimeKind = RuntimeKind.builtin
    inference_mode: InferenceMode = InferenceMode.hybrid
    #: How Hutch represents this Bot's tools to its model (docs/realignment/tool-calling.md).
    #: ``auto`` keeps the provider-native protocol and never silently picks another mode.
    tool_protocol: Literal["auto", "native", "constrained", "prompt", "disabled"] = "auto"
    tools: list[str] = Field(default_factory=lambda: ["shell", "files", "memory", "documents"])
    skills: list[str] = Field(default_factory=list)   # bound Agent Skill names; review state lives in the skill registry
    schedule: Optional[Schedule] = None
    schedules: list[Schedule] = Field(default_factory=list)
    limits: Limits = Field(default_factory=Limits)
    approval_mode: ApprovalMode = ApprovalMode.ask
    memory_enabled: bool = True
    workspace_mode: Literal["fresh", "managed", "folder"] = "fresh"
    workdir: Optional[str] = None     # an existing user folder; overrides the managed workspace
    local_browser_handoff: bool = False  # show this bot's browser on the Linux desktop for same-session human control
    remote_start_enabled: bool = False   # local-owner opt-in for passkey-paired phone starts; never grants new tools
    paused: bool = False
    pinned: bool = False              # workspace roster preference; does not affect execution
    # --- dynamic workflows (schema v53): how Hutch may use a workflow for this Bot.
    # ``off`` never proposes or starts one; ``suggest`` may describe a candidate route;
    # ``auto`` may start within ``workflow_limits`` without a fresh confirmation.
    workflow_mode: Literal["off", "suggest", "auto"] = "off"
    workflow_limits: dict = Field(default_factory=dict)  # auto scope: definitions + budget caps
    sidebar_hidden: bool = False       # removes an idle Bot from the main roster; never pauses work
    roster_section: Optional[str] = Field(default=None, max_length=40)
    template: Optional[str] = None    # which starter template it came from
    creation_source: Optional[BotCreationSource] = None  # explicit request provenance; never grants authority
    creation_context_sources: list[BotCreationSource] = Field(default_factory=list)  # owner-selected same-chat user messages
    preset: Optional[str] = None      # task preset this bot was configured from (LM-7)
    fallbacks: list[str] = Field(default_factory=list)   # tried in order when the model is unavailable (SR-8)
    escalation: Optional[Escalation] = None              # quality ladder (LM-9)
    background_provider_consents: list[BackgroundProviderConsent] = Field(default_factory=list)
    risk_tier: RiskTier = RiskTier.supervised            # SR-12
    command_rules: list[CommandRule] = Field(default_factory=list)
    think: Optional[bool] = None      # None = off for small local models, model default for hosted (SR-5)
    selfcheck: bool = True            # prove the context window works before the first run (LM-2)
    num_ctx: Optional[int] = None     # manual context override; None = computed from hardware and preset
    tool_limits: dict[str, int] = Field(default_factory=dict)   # per-tool output limits in chars (PF-2)
    sandbox: str = Field(default_factory=lambda: _default_sandbox())   # strict | off: OS containment of the shell (ADR-0006)
    shell_network: bool = False       # may commands in the sandbox use the network? (default: no)
    created_at: str = Field(default_factory=lambda: iso(utcnow()))

    @model_validator(mode="after")
    def folder_workspace_requires_path(self) -> "Bot":
        # Persisted Bot documents from older schemas have no display_name.
        # Normalize here so API and server-rendered views share one fallback.
        self.display_name = " ".join(self.display_name.split()) or bot_slug_display_name(self.name)
        # Existing bot JSON only has ``workdir``. When a pre-mode record loads,
        # preserve its actual behavior and surface it as the folder choice.
        if self.workdir and self.workspace_mode == "fresh":
            self.workspace_mode = "folder"
        elif self.workdir and self.workspace_mode != "folder":
            raise ValueError("workdir can only be used with folder workspace mode")
        if self.workspace_mode == "folder" and not self.workdir:
            raise ValueError("folder workspace mode requires an existing workdir")
        if self.schedules:
            self.schedule = self.schedules[0]
        elif self.schedule:
            self.schedules = [self.schedule]
        return self

    @field_validator("roster_section")
    @classmethod
    def normalize_roster_section(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None

    def set_schedules(self, schedules: list[Schedule]) -> None:
        """Update the multi-task list and its first-schedule compatibility alias together."""
        if len(schedules) > 100:
            raise ValueError("a bot can have at most 100 scheduled tasks")
        ids = [schedule.id for schedule in schedules]
        if len(ids) != len(set(ids)):
            raise ValueError("scheduled task IDs must be unique within a bot")
        self.schedules = list(schedules)
        self.schedule = self.schedules[0] if self.schedules else None

    def replace_primary_schedule(self, schedule: Schedule | None) -> None:
        """Replace or remove the legacy-visible first task while retaining the other streams."""
        remaining = self.schedules[1:] if self.schedules else []
        self.set_schedules(([schedule] if schedule else []) + remaining)

    @field_validator("sandbox")
    @classmethod
    def _sandbox(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ("strict", "off"):
            raise ValueError("sandbox must be 'strict' or 'off'")
        return v


def _default_sandbox() -> str:
    """New bots get OS containment where the host can provide it; bots from before it existed were migrated to 'off'."""
    from .sandbox import default_mode
    return default_mode()


class Task(BaseModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    bot_id: str
    kind: str = "on_demand"           # on_demand | scheduled
    prompt: str
    created_at: str = Field(default_factory=lambda: iso(utcnow()))


class Run(BaseModel):
    id: str = Field(default_factory=lambda: new_id("run"))
    bot_id: str
    task_id: Optional[str] = None
    prompt: str
    status: RunStatus = RunStatus.pending
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    exit_reason: str = ""             # completed | failed | stopped | timeout | steps_exceeded | token_cap | approval_expired | error
    error: str = ""
    steps: int = 0
    tokens: int = 0                   # running estimate
    workspace: Optional[str] = None
    missed_windows: int = 0           # >0 when this run is a catch-up coalescence
    created_at: str = Field(default_factory=lambda: iso(utcnow()))
    # --- accounting (SR-2, UI-4, PF-11): exact per step, summed per run
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    model_ms: float = 0.0             # time waiting on the model
    queue_ms: float = 0.0             # measured local-inference admission waits (also before startup)
    tool_ms: float = 0.0              # time inside tools
    overhead_ms: float = 0.0          # everything else: Hutch's own cost per step
    context_used: int = 0             # tokens in the last prompt
    context_limit: int = 0            # effective window the model actually got
    model_used: str = ""              # may differ from bot.model after escalation/fallback
    # --- lineage (SR-7)
    origin: str = "manual"            # manual:dashboard | manual:cli | manual:api | schedule | plan
    schedule_id: str = ""              # source schedule for recurring work; empty for other origins
    plan_id: Optional[str] = None
    plan_task_id: Optional[str] = None
    parent_run_id: Optional[str] = None  # bounded delegation lineage; immutable after admission
    delegation_budget_cost_usd: Optional[float] = None  # immutable shared currency cap inherited by descendants
    rehearsal: bool = False           # dry run: mutating actions are simulated
    model_override: str = ""          # the model picked for THIS message in the chat switcher (bot.model is untouched)
    skill_activation: list[str] = Field(default_factory=list)  # operator-selected skills for this run (validated at submit)
    skill_snapshot: list[dict] = Field(default_factory=list)   # effective skills recorded when this run started
    tool_access: Literal["bot", "none"] = "bot"  # per-run capability ceiling; "none" is reserved for review-only drafts
    conversation_id: str = ""          # canonical conversation this run belongs to, if submitted through /api/v1
    conversation_context: list[dict[str, str]] = Field(default_factory=list, exclude=True)
    owner: str = ""                   # pid of the process executing this run (kept for compatibility; see lease_owner)
    # --- ownership (ADR-0001/0003). These mirror columns; the columns are authoritative.
    fence: int = 0                    # bumped at every claim and recovery; a write with a stale fence is rejected
    lease_owner: str = ""             # host:pid:nonce of the process that holds this run
    lease_expires_at: Optional[str] = None
    cancel_requested: bool = False    # set by any client; the owner acts on it
    pgid: int = 0                     # process group of the worker, so a supervisor that did not spawn it can still end it
    verified: Optional[bool] = None   # did the task's expectation hold? None = no expectation was declared
    reason: str = ""                  # why a waiting/recovering run is in that state (shown with the label)
    # --- dynamic workflows (schema v53). ``kind`` also exists as a column, because claim
    # admission needs it in SQL; the document copy keeps it readable everywhere else.
    kind: Literal["attempt", "workflow", "step"] = "attempt"
    workflow_run_id: str = ""          # the workflow instance this attempt/step belongs to
    workflow_step: Optional[dict] = None  # a step's frozen execution contract (tools, limits, role)

    @field_validator("parent_run_id")
    @classmethod
    def valid_parent_run_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and (not value or value != value.strip() or len(value) > 80):
            raise ValueError("parent_run_id must be a non-empty run ID")
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status_label(self) -> str:
        from .lifecycle import LABELS
        label = LABELS[self.status]
        reason = (self.reason or self.exit_reason or "").lower()
        if self.status is RunStatus.recovering and "cleanup" in reason:
            return "Cleanup could not be verified"
        if self.status is RunStatus.pending and reason:
            return f"Queued — {self.reason or self.exit_reason}"
        return label

    @computed_field  # type: ignore[prop-decorator]
    @property
    def terminal(self) -> bool:
        return self.status not in ACTIVE_STATUSES

    @computed_field  # type: ignore[prop-decorator]
    @property
    def needs_person(self) -> bool:
        from .lifecycle import NEEDS_PERSON
        return self.status in NEEDS_PERSON


class EventType(str, Enum):
    status = "status"
    message = "message"               # assistant/user message
    tool_call = "tool_call"
    tool_result = "tool_result"
    approval_request = "approval_request"
    approval_resolved = "approval_resolved"
    error = "error"
    log = "log"
    step = "step"                     # one model turn: tokens, cost, timing split
    human_needed = "human_needed"     # login / CAPTCHA / 2FA wall: a person must act
    human_resumed = "human_resumed"
    choice_requested = "choice_requested"  # conversational clarification; grants no action authority
    choice_answered = "choice_answered"


class Event(BaseModel):
    id: Optional[int] = None          # database row id; only set on events read back
    run_id: str
    seq: int = 0                      # per-run sequence number, 1-based and gap-free (UI-3)
    hash: str = ""                    # hash-chain link to the previous event of this run (SR-11)
    ts: str = Field(default_factory=lambda: iso(utcnow()))
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)
    owner_fence: Optional[int] = Field(default=None, exclude=True)  # commit-time worker authority, not transcript data

    def json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False)


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: new_id("apr"))
    run_id: str
    bot_id: str
    tool: str                         # e.g. shell, files, browser
    action: str                       # human-readable summary of what will happen
    detail: dict[str, Any] = Field(default_factory=dict)  # e.g. {"command": "rm -rf build/"}
    sticky_key: str = ""              # key under which "always allow" is remembered
    status: ApprovalStatus = ApprovalStatus.pending
    created_at: str = Field(default_factory=lambda: iso(utcnow()))
    resolved_at: Optional[str] = None
    decided_by: str = ""              # "dashboard" | "cli:<user>" | "timeout"
    # --- what the human needs to decide well (UI-5)
    segments: list[dict[str, Any]] = Field(default_factory=list)  # parsed command segments + verdicts
    rule: str = ""                    # the rule that triggered the prompt
    risk: str = "medium"              # low | medium | high
    outward: bool = False             # sends something out: sticky allows never apply (SR-4)
    action_hash: str = ""             # fingerprint of the exact action shown; a decision is only valid for this action
    ttl_seconds: int = 600
    expires_at: Optional[str] = None  # default-deny deadline, shown as a countdown
    plan_id: Optional[str] = None     # tagged when the run belongs to a plan (CO-10)


class MemoryItem(BaseModel):
    id: str = ''
    bot_id: str = ''
    key: str
    value: str
    updated_at: str = Field(default_factory=lambda: iso(utcnow()))
    run_id: str = ""                  # the run that wrote this entry (UI-10)
    source: str = "bot"               # bot | user
    scope_kind: Literal['conversation', 'run', 'bot', 'legacy'] = 'legacy'
    scope_id: str = ''
    revision: int = 1
    content_hash: str = ''
    status: Literal['proposed', 'approved', 'archived'] = 'proposed'
    truncated: bool = False
    conversation_title: str = ''
