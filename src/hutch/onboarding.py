"""Onboarding setup record: the server-owned source of truth for setup progress.

Slice 01 keeps one OnboardingSetup per installation and one request step. This
module is pure (no store, templates, filesystem, or network): it validates the
persisted record and turns a submitted request edit into an explicit EditResult.
Expected outcomes are returned as dataclasses, never raised. A record written by
a newer Hutch stays parseable (contract_version is an integer, not a literal)
and surfaces as a stale resume state, never as "damaged".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .models import iso

ONBOARDING_CONTRACT_VERSION = 1
ONBOARDING_REQUIREMENTS_VERSION = 1
REQUEST_MAX_CHARS = 20000
RESUME_TTL = timedelta(days=30)
STEP_ORDER = ("request", "ai_service", "connection", "assistant", "first_request")
REQUIRED_STEPS = STEP_ORDER
OPTIONAL_STEPS = ()

STATE_EMPTY_NO_ROUTE = "setup.empty_no_route"
STATE_RESUME_CURRENT = "setup.resume.current"
STATE_RESUME_STALE = "setup.resume.stale"
STATE_RESUME_EXPIRED = "setup.resume.expired"

_TIMESTAMP_ERROR = "timestamp must be ISO-8601 with an explicit offset"


class OnboardingSetup(BaseModel):
    """One installation's setup record (the kv value for onboarding:setup:v1)."""

    model_config = ConfigDict(extra="ignore")

    contract_version: int = ONBOARDING_CONTRACT_VERSION
    revision: int = Field(ge=0)
    step: str
    request_text: str
    requirements_version: int
    resume_expires_at: str
    created_at: str
    updated_at: str
    # Slice 02 adds the chosen AI service route. They stay plain strings (not a
    # literals) so a record written by a newer Hutch parses and surfaces as the
    # explicit stale/resume state instead of "damaged"; an empty value means no
    # route was chosen yet. Route validation lives in onboarding_choices.py.
    route_kind: str = ""
    route_chosen_at: str = ""

    @field_validator("resume_expires_at", "created_at", "updated_at")
    @classmethod
    def _timestamp_with_offset(cls, value: str) -> str:
        """Reject naive or unparseable timestamps; keep the stored string as-is."""
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError(_TIMESTAMP_ERROR) from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(_TIMESTAMP_ERROR)
        return value


@dataclass(frozen=True)
class SetupRecord:
    """Result of parsing the stored kv value: absent, present, or damaged."""

    kind: str
    setup: OnboardingSetup | None
    detail: str = ""


@dataclass(frozen=True)
class EditResult:
    """Outcome of one request edit: accepted, replayed, stale, or invalid."""

    kind: str
    setup: OnboardingSetup | None
    reason: str = ""


@dataclass(frozen=True)
class ResumeView:
    """Render-safe projection of one stored record for the request step page."""

    state: str
    step: str
    step_index: int
    required_total: int
    request_text: str
    revision: int
    saved_at: str
    stale: bool
    stale_reasons: tuple[str, ...]
    expired: bool
    newer_version: bool
    resume_expires_at: str


def default_setup(now: datetime) -> OnboardingSetup:
    """A fresh unedited record (revision 0) stamped at now."""
    stamp = iso(now)
    return OnboardingSetup(
        revision=0, step=STEP_ORDER[0], request_text="",
        requirements_version=ONBOARDING_REQUIREMENTS_VERSION,
        resume_expires_at=iso(now + RESUME_TTL), created_at=stamp, updated_at=stamp,
    )


def parse_setup(raw: str | None) -> SetupRecord:
    """Parse the stored kv value into a record; never raises for bad input."""
    if raw is None:
        return SetupRecord("absent", None)
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return SetupRecord("damaged", None, "invalid JSON")
    if not isinstance(payload, dict):
        return SetupRecord("damaged", None, "record is not a JSON object")
    try:
        setup = OnboardingSetup.model_validate(payload)
    except ValidationError:
        return SetupRecord("damaged", None, "record failed validation")
    return SetupRecord("present", setup)


def encode_setup(setup: OnboardingSetup) -> str:
    """Compact, key-sorted JSON for the kv value."""
    return json.dumps(setup.model_dump(), sort_keys=True, separators=(",", ":"))


def _stale_reasons(setup: OnboardingSetup, *, active_requirements_version: int,
                   active_contract_version: int) -> tuple[str, ...]:
    """Machine reason codes for a record this code cannot resume as current."""
    reasons: list[str] = []
    if setup.contract_version > active_contract_version:
        reasons.append("newer_contract")
    elif setup.contract_version < active_contract_version:
        reasons.append("contract_version")
    if setup.requirements_version != active_requirements_version:
        reasons.append("requirements_version")
    if setup.step not in REQUIRED_STEPS:
        reasons.append("unknown_step")
    return tuple(reasons)


def _is_expired(setup: OnboardingSetup, now: datetime) -> bool:
    """True when now is at or past the stored TTL; unreadable dates count as expired."""
    try:
        deadline = datetime.fromisoformat(setup.resume_expires_at)
    except (TypeError, ValueError):
        return True
    return deadline.tzinfo is None or now >= deadline


def _refreshed(setup: OnboardingSetup, *, text: str, now: datetime,
               requirements_version: int, contract_version: int) -> OnboardingSetup:
    """The record an accepted edit writes: one revision bump and a fresh TTL."""
    step = setup.step if setup.step in REQUIRED_STEPS else STEP_ORDER[0]
    return setup.model_copy(update={
        "contract_version": contract_version, "revision": setup.revision + 1,
        "step": step, "request_text": text, "requirements_version": requirements_version,
        "resume_expires_at": iso(now + RESUME_TTL), "updated_at": iso(now),
    })


def apply_request_edit(
    setup: OnboardingSetup, *, expected_revision: int, request_text: str, now: datetime,
    requirements_version: int = ONBOARDING_REQUIREMENTS_VERSION,
    contract_version: int = ONBOARDING_CONTRACT_VERSION,
) -> EditResult:
    """Decide one request-step submission against the current stored record.

    Returns accepted (persist the returned record), replayed (identical content
    on a current record), stale (different content from a revision the caller no
    longer holds; the returned record is the current one), or invalid (fixable
    user input; nothing is written).
    """
    if expected_revision < 0:
        return EditResult("invalid", setup, "Reload the page before saving.")
    text = str(request_text or "").strip()
    if not text:
        return EditResult("invalid", setup, "Enter a request before saving.")
    if len(text) > REQUEST_MAX_CHARS:
        return EditResult("invalid", setup,
                          f"Shorten the request to {REQUEST_MAX_CHARS:,} characters or fewer.")
    refreshed = _refreshed(setup, text=text, now=now,
                           requirements_version=requirements_version,
                           contract_version=contract_version)
    if text != setup.request_text.strip():
        if expected_revision != setup.revision:
            return EditResult("stale", setup, "This setup changed in another window.")
        return EditResult("accepted", refreshed)
    reasons = _stale_reasons(setup, active_requirements_version=requirements_version,
                             active_contract_version=contract_version)
    if not reasons and not _is_expired(setup, now):
        return EditResult("replayed", setup)
    # Identical content on an expired or version-stale record is an intentional
    # recovery: refresh the TTL and versions, and bump the revision once.
    return EditResult("accepted", refreshed)


def empty_view() -> ResumeView:
    """The neutral view a page renders when no record is stored."""
    return ResumeView(
        state=STATE_EMPTY_NO_ROUTE, step=STEP_ORDER[0], step_index=1,
        required_total=len(REQUIRED_STEPS), request_text="", revision=0, saved_at="",
        stale=False, stale_reasons=(), expired=False, newer_version=False, resume_expires_at="",
    )


def resume_view(
    setup: OnboardingSetup, *, now: datetime,
    active_requirements_version: int = ONBOARDING_REQUIREMENTS_VERSION,
    active_contract_version: int = ONBOARDING_CONTRACT_VERSION,
) -> ResumeView:
    """Project a stored record as stale, expired, empty, or current.

    Precedence is stale, then expired, then empty, then current. Stale reasons
    are machine tokens ordered contract/version, requirements, unknown step.
    """
    reasons = _stale_reasons(setup, active_requirements_version=active_requirements_version,
                             active_contract_version=active_contract_version)
    expired = _is_expired(setup, now)
    if reasons:
        state = STATE_RESUME_STALE
    elif expired:
        state = STATE_RESUME_EXPIRED
    elif not setup.request_text.strip():
        state = STATE_EMPTY_NO_ROUTE
    else:
        state = STATE_RESUME_CURRENT
    step_index = REQUIRED_STEPS.index(setup.step) + 1 if setup.step in REQUIRED_STEPS else 1
    return ResumeView(
        state=state, step=setup.step, step_index=step_index,
        required_total=len(REQUIRED_STEPS), request_text=setup.request_text,
        revision=setup.revision, saved_at=setup.updated_at, stale=bool(reasons),
        stale_reasons=reasons, expired=expired,
        newer_version=setup.contract_version > active_contract_version,
        resume_expires_at=setup.resume_expires_at,
    )
