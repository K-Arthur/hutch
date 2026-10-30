"""Pydantic models for the coordinated workspace-task API (see tasks_api)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class WorkspaceTaskAssignment(BaseModel):
    """A second concurrent specialist in the same coordinated task plan."""
    target_bot_id: str = Field(min_length=1, max_length=100)
    task_brief: str = Field(min_length=1, max_length=20_000)
    model_override: str = Field(default="", max_length=200)


class WorkspaceTaskCreate(BaseModel):
    parent_conversation_id: str = Field(min_length=1, max_length=100)
    source_run_id: str = Field(min_length=1, max_length=100)
    source_user_message_id: str = Field(min_length=1, max_length=128)
    source_assistant_message_id: str = Field(min_length=1, max_length=128)
    target_bot_id: str = Field(min_length=1, max_length=100)
    task_brief: str = Field(min_length=1, max_length=20_000)
    assumptions: str = Field(default="", max_length=4_000)
    memory_fact_ids: list[str] = Field(default_factory=list, max_length=8)
    model_override: str = Field(default="", max_length=200)
    additional_assignments: list[WorkspaceTaskAssignment] = Field(default_factory=list, max_length=1)


class WorkspaceTaskRedirect(BaseModel):
    task_brief: str = Field(min_length=1, max_length=20_000)
    assumptions: Optional[str] = Field(default=None, max_length=4_000)


class WorkspaceTaskCheckpointResource(BaseModel):
    event_id: int
    event_seq: int
    event_type: str
    run_status: str
    kind: str
    recovery_state: str
    reference_id: str = ""
    created_at: str


class WorkspaceTaskQuestionOptionResource(BaseModel):
    id: str
    label: str


class WorkspaceTaskQuestionResource(BaseModel):
    """A pending conversational question from the assigned specialist.

    The question is a needed input, not an accepted result; the owner answers it through the
    specialist conversation's normal single-resolution question endpoint. ``status`` stays the
    derived task state: ``needs_input`` while the question waits.
    """
    id: str
    question: str
    selection_mode: Literal["single", "multiple"]
    options: list[WorkspaceTaskQuestionOptionResource] = Field(default_factory=list)
    run_id: str
    assistant_message_id: str
    created_at: str


class WorkspaceTaskSharedFactResource(BaseModel):
    fact_id: str
    source_bot_id: str
    source_display_name: str
    source_scope_kind: Literal["bot", "conversation"]
    source_scope_id: str
    source_conversation_id: str = ""
    key: str
    value: str
    revision: int
    content_hash: str


class WorkspaceTaskResource(BaseModel):
    id: str
    parent_conversation_id: str
    source_run_id: str
    source_user_message_id: str
    source_assistant_message_id: str
    target_bot_id: str
    target_display_name: str
    original_request: str
    original_request_truncated: bool = False
    proposed_brief: str
    proposed_brief_truncated: bool = False
    task_brief: str
    assumptions: str
    child_conversation_id: str
    child_run_id: str
    current_run_id: str
    continuation_of_task_id: Optional[str] = None
    continuation_checkpoint_event_id: Optional[int] = None
    status: str
    reason: str
    pending_question: Optional[WorkspaceTaskQuestionResource] = None
    result: str
    result_truncated: bool = False
    result_message_id: Optional[str] = None
    model: str
    inference_mode: str
    tools: list[str]
    risk_tier: str
    workspace_mode: str
    created_at: str
    checkpoint_count: int = 0
    checkpoints: list[WorkspaceTaskCheckpointResource] = Field(default_factory=list)
    shared_facts: list[WorkspaceTaskSharedFactResource] = Field(default_factory=list)
    continuation_available: bool = False
    continuation_reason: str = ""
    continuation_checkpoint_kind: str = ""
    continuation_checkpoint_event_seq: int = 0
    continuation_checkpoint_preview: str = ""
    default_model: str = ""
    model_override: str = ""
    model_source: Literal["specialist_default", "assignment_override"] = "specialist_default"
    model_used: str = ""
    tokens: int = 0
    cost_usd: float = 0.0
    plan_group_id: str = ""
    assignment_index: int = 0
    assignment_total: int = 1
    brief_revision: int = 1
    peer_task_ids: list[str] = Field(default_factory=list)
