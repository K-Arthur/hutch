"""Data model: bots, tasks, runs, events, approvals, memory.

Timestamps are ISO-8601 UTC strings with explicit offset — naive local times
are the root cause of the DST double-fire / missed-fire bugs documented in
docs/research/complaints.md, so we never store them.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RunStatus(str, Enum):
    pending = "pending"
    loading_model = "loading_model"        # cold-loading a local model (LM-6)
    running = "running"
    waiting_approval = "waiting_approval"
    waiting_human = "waiting_human"        # login / CAPTCHA wall: a person must act
    succeeded = "succeeded"
    failed = "failed"
    stopped = "stopped"
    skipped = "skipped"


#: statuses in which a run still holds (or is queued for) resources
ACTIVE_STATUSES = (
    RunStatus.pending, RunStatus.loading_model, RunStatus.running,
    RunStatus.waiting_approval, RunStatus.waiting_human,
)


class RuntimeKind(str, Enum):
    builtin = "builtin"      # hutch's own agent loop (OpenAI-compatible providers)
    mock = "mock"            # deterministic offline provider (tests + demos)
    pi = "pi"                # Pi coding agent, driven over RPC stdio
    opencode = "opencode"    # OpenCode, driven via `opencode run`


class CatchUpPolicy(str, Enum):
    """What to do when the machine was asleep/off across a scheduled fire time."""

    coalesce = "coalesce"    # run once, note how many windows were missed
    skip = "skip"            # never run for a past window


class Schedule(BaseModel):
    cron: str                          # 5-field cron expression
    timezone: str = "UTC"              # IANA name; schedule fires in this zone
    catch_up: CatchUpPolicy = CatchUpPolicy.coalesce

    model_config = {"frozen": True}


class Limits(BaseModel):
    """Hard caps enforced per run (and daily per bot for tokens)."""

    max_steps: int = 24                # agent turns before forced stop
    timeout_seconds: int = 900         # wall-clock kill switch
    daily_token_cap: int = 200_000     # estimated tokens (prompt+completion)

    model_config = {"frozen": True}


class ApprovalMode(str, Enum):
    ask = "ask"        # ask before any non-read-only action unless sticky-allowed
    auto = "auto"      # auto-approve non-denied actions (denylist still enforced)


class Bot(BaseModel):
    id: str = Field(default_factory=lambda: new_id("bot"))
    name: str                         # slug, unique
    description: str = ""
    instructions: str = ""            # system-prompt level guidance
    model: str = "mock/demo"          # provider/model spec, e.g. openai/gpt-4o-mini, ollama/llama3.2
    base_url: Optional[str] = None    # override for OpenAI-compatible endpoints
    runtime: RuntimeKind = RuntimeKind.builtin
    tools: list[str] = Field(default_factory=lambda: ["shell", "files", "memory"])
    schedule: Optional[Schedule] = None
    limits: Limits = Field(default_factory=Limits)
    approval_mode: ApprovalMode = ApprovalMode.ask
    memory_enabled: bool = True
    paused: bool = False
    template: Optional[str] = None    # which starter template it came from
    created_at: str = Field(default_factory=lambda: iso(utcnow()))


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
    tool_ms: float = 0.0              # time inside tools
    overhead_ms: float = 0.0          # everything else: Hutch's own cost per step
    context_used: int = 0             # tokens in the last prompt
    context_limit: int = 0            # effective window the model actually got
    model_used: str = ""              # may differ from bot.model after escalation/fallback
    # --- lineage (SR-7)
    origin: str = "manual"            # manual:dashboard | manual:cli | manual:api | schedule | plan
    plan_id: Optional[str] = None
    plan_task_id: Optional[str] = None
    rehearsal: bool = False           # dry run: mutating actions are simulated


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


class Event(BaseModel):
    id: Optional[int] = None          # database row id; only set on events read back
    run_id: str
    seq: int = 0                      # per-run sequence number, 1-based and gap-free (UI-3)
    hash: str = ""                    # hash-chain link to the previous event of this run (SR-11)
    ts: str = Field(default_factory=lambda: iso(utcnow()))
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)

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
    ttl_seconds: int = 600
    expires_at: Optional[str] = None  # default-deny deadline, shown as a countdown
    plan_id: Optional[str] = None     # tagged when the run belongs to a plan (CO-10)


class MemoryItem(BaseModel):
    key: str
    value: str
    updated_at: str = Field(default_factory=lambda: iso(utcnow()))
    run_id: str = ""                  # the run that wrote this entry (UI-10)
    source: str = "bot"               # bot | user
