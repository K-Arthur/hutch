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
    running = "running"
    waiting_approval = "waiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    stopped = "stopped"
    skipped = "skipped"


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


class EventType(str, Enum):
    status = "status"
    message = "message"               # assistant/user message
    tool_call = "tool_call"
    tool_result = "tool_result"
    approval_request = "approval_request"
    approval_resolved = "approval_resolved"
    error = "error"
    log = "log"


class Event(BaseModel):
    id: Optional[int] = None
    run_id: str
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


class MemoryItem(BaseModel):
    key: str
    value: str
    updated_at: str = Field(default_factory=lambda: iso(utcnow()))
