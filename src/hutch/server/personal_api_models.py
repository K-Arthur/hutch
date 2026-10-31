"""Request/response bodies for the personal operations API (commitments, spaces, Today)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from ..personal.models import CommitmentPriority, SpaceKind, SpaceRole


class CommitmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=4_000)
    priority: CommitmentPriority = CommitmentPriority.normal
    due_at: Optional[str] = None
    due_timezone: str = Field(default="UTC", max_length=100)
    category: str = Field(default="", max_length=40)
    space_id: Optional[str] = Field(default=None, max_length=100)


class CommitmentPatch(BaseModel):
    expected_revision: int = Field(ge=1)
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    detail: Optional[str] = Field(default=None, max_length=4_000)
    priority: Optional[CommitmentPriority] = None
    due_at: Optional[str] = None
    due_timezone: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=40)
    space_id: Optional[str] = Field(default=None, max_length=100)


class CommitmentComplete(BaseModel):
    evidence: str = Field(min_length=1, max_length=2_000)
    expected_revision: Optional[int] = Field(default=None, ge=1)


class CommitmentRevision(BaseModel):
    expected_revision: Optional[int] = Field(default=None, ge=1)


class CommitmentDependencies(BaseModel):
    depends_on: list[str] = Field(default_factory=list, max_length=20)
    expected_revision: Optional[int] = Field(default=None, ge=1)


class SpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: SpaceKind = SpaceKind.household
    description: str = Field(default="", max_length=1_000)


class SpacePatch(BaseModel):
    expected_revision: int = Field(ge=1)
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=1_000)
    kind: Optional[SpaceKind] = None


class SpaceArchive(BaseModel):
    expected_revision: int = Field(ge=1)


class SpaceMemberCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    role: SpaceRole = SpaceRole.collaborator


class SpaceMemberPatch(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    role: Optional[SpaceRole] = None
    status: Optional[Literal["active", "revoked"]] = None


class SpaceBotGrant(BaseModel):
    bot_id: str = Field(min_length=1, max_length=100)
