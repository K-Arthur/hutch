"""Data model for personal operations: commitments and shared spaces.

A commitment is a promise the person made, not a run, not a specialist assignment
and not a chat-continuity entry. Its provenance, confirmation state and completion
evidence are first-class because the product must never present a model suggestion,
an attempt, or a claim as verified work.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from ..models import iso, utcnow

MAX_TITLE = 200
MAX_DETAIL = 4_000
MAX_CATEGORY = 40
MAX_EVIDENCE = 2_000
MAX_DEPENDENCIES = 20


def _new_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _clean_title(value: str) -> str:
    text = " ".join((value or "").split())
    if not text:
        raise ValueError("a commitment needs a title")
    if len(text) > MAX_TITLE:
        raise ValueError(f"a commitment title is at most {MAX_TITLE} characters")
    return text


def _valid_zone(value: str) -> str:
    name = (value or "UTC").strip()
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA timezone: {name}") from exc
    return name


def _utc_instant(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("due_at must be an ISO-8601 instant") from exc
    if when.tzinfo is None:
        raise ValueError("due_at needs an explicit UTC offset or Z")
    return iso(when.astimezone(timezone.utc))


class CommitmentStatus(str, Enum):
    open = "open"
    done = "done"
    cancelled = "cancelled"


class CommitmentPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class CompletionKind(str, Enum):
    owner_confirmed = "owner_confirmed"   # the owner marked it done
    receipt = "receipt"                   # a run/action receipt backs the completion
    unverified = "unverified"             # an assistant reported it; nobody verified


class Commitment(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("cmt"))
    title: str
    detail: str = ""
    status: CommitmentStatus = CommitmentStatus.open
    priority: CommitmentPriority = CommitmentPriority.normal
    due_at: Optional[str] = None            # UTC instant; None means no date promised
    due_timezone: str = "UTC"               # the IANA zone the date was expressed in
    category: str = ""
    space_id: Optional[str] = None          # None = personal; a space id = shared scope
    # --- provenance (immutable after creation)
    source: Literal["user", "assistant", "workflow", "schedule", "import"] = "user"
    source_detail: str = ""
    conversation_id: Optional[str] = None
    run_id: Optional[str] = None
    message_id: Optional[str] = None
    created_by: Literal["owner", "assistant", "workflow", "system"] = "owner"
    confirmation: Literal["confirmed", "proposed"] = "confirmed"
    # --- lifecycle
    revision: int = Field(default=1, ge=1)
    completed_at: Optional[str] = None
    completion_evidence: str = ""
    completion_kind: Optional[CompletionKind] = None
    completed_by: str = ""
    dependencies: list[str] = Field(default_factory=list, max_length=MAX_DEPENDENCIES)
    created_at: str = Field(default_factory=lambda: iso(utcnow()))
    updated_at: str = Field(default_factory=lambda: iso(utcnow()))

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _clean_title(value)

    @field_validator("detail")
    @classmethod
    def _detail(cls, value: str) -> str:
        return (value or "").strip()[:MAX_DETAIL]

    @field_validator("category")
    @classmethod
    def _category(cls, value: str) -> str:
        return (value or "").strip()[:MAX_CATEGORY]

    @field_validator("due_at")
    @classmethod
    def _due(cls, value: Optional[str]) -> Optional[str]:
        return _utc_instant(value)

    @field_validator("due_timezone")
    @classmethod
    def _zone(cls, value: str) -> str:
        return _valid_zone(value)

    @field_validator("completion_evidence")
    @classmethod
    def _evidence(cls, value: str) -> str:
        return (value or "").strip()[:MAX_EVIDENCE]

    @model_validator(mode="after")
    def _coherent(self) -> "Commitment":
        if self.status is CommitmentStatus.done:
            if not self.completed_at or not self.completion_evidence:
                raise ValueError("a completed commitment needs a completion timestamp and evidence")
            if self.completion_kind is None:
                raise ValueError("a completed commitment needs a completion kind")
        else:
            if self.completed_at or self.completion_evidence or self.completion_kind:
                raise ValueError("only a completed commitment carries completion fields")
        if self.confirmation == "proposed" and self.status is not CommitmentStatus.open:
            raise ValueError("a proposed commitment is open until the owner confirms it")
        return self

    def as_dict(self) -> dict:
        return self.model_dump(mode="json")


class SpaceKind(str, Enum):
    household = "household"
    project = "project"
    team = "team"


class SpaceRole(str, Enum):
    owner = "owner"
    adult = "adult"
    collaborator = "collaborator"
    read_only = "read_only"
    child = "child"
    guest = "guest"


class SpaceMemberStatus(str, Enum):
    active = "active"
    revoked = "revoked"


class Space(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("space"))
    name: str
    kind: SpaceKind = SpaceKind.household
    description: str = ""
    revision: int = Field(default=1, ge=1)
    archived: bool = False
    created_at: str = Field(default_factory=lambda: iso(utcnow()))
    updated_at: str = Field(default_factory=lambda: iso(utcnow()))

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        text = " ".join((value or "").split())
        if not text:
            raise ValueError("a shared space needs a name")
        if len(text) > 80:
            raise ValueError("a shared space name is at most 80 characters")
        return text

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return (value or "").strip()[:1_000]


class SpaceMember(BaseModel):
    space_id: str = ""   # filled by the repository on insert
    member_id: str = Field(default_factory=lambda: _new_id("mem"))
    display_name: str
    role: SpaceRole = SpaceRole.collaborator
    status: SpaceMemberStatus = SpaceMemberStatus.active
    created_at: str = Field(default_factory=lambda: iso(utcnow()))
    updated_at: str = Field(default_factory=lambda: iso(utcnow()))

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str) -> str:
        text = " ".join((value or "").split())
        if not text:
            raise ValueError("a space member needs a display name")
        if len(text) > 80:
            raise ValueError("a member name is at most 80 characters")
        return text


class BotSpaceGrant(BaseModel):
    space_id: str
    bot_id: str
    created_at: str = Field(default_factory=lambda: iso(utcnow()))
