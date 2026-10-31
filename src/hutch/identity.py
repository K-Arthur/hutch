"""The person's profile and each assistant's bounded identity: reviewed local data, not a prompt trick.

Hutch already has a structured persona (tone, warmth, format) and prose standing directions. Two things a
durable teammate needs are still missing: how the person wants to be treated (one workspace profile) and the
boundaries an assistant must respect (one small file per assistant). Both are plain JSON in the state
directory, bounded, revision-checked and shown for review before they are saved. A damaged file is reported
and never applied; no model tool can write either file. They render into the system prompt as advisory
context after the operator instructions, and never widen tools, approvals, budgets or data access.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

VERSION = 1
MAX_BOUNDARIES = 8
MAX_BOUNDARY_CHARS = 200
MAX_SIGNATURE_CHARS = 400
MAX_PREFERRED_NAME = 80
MAX_ABOUT_CHARS = 2000
MAX_TREAT_CHARS = 1000
MAX_FILE_BYTES = 16 * 1024
DIR_NAME = "identity"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssistantIdentity(_Strict):
    """How one assistant signs off and the boundaries it keeps. Advisory context only."""

    version: int = VERSION
    revision: int = Field(default=0, ge=0)
    signature: str = Field(default="", max_length=MAX_SIGNATURE_CHARS)
    boundaries: list[str] = Field(default_factory=list, max_length=MAX_BOUNDARIES)

    @field_validator("signature")
    @classmethod
    def _trim_signature(cls, value: str) -> str:
        return value.strip()

    @field_validator("boundaries")
    @classmethod
    def _clean_boundaries(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.split()) for value in values if value and value.strip()]
        for item in cleaned:
            if len(item) > MAX_BOUNDARY_CHARS:
                raise ValueError(f"a boundary is longer than {MAX_BOUNDARY_CHARS} characters")
        return cleaned


class PersonProfile(_Strict):
    """How the person wants to be treated. One workspace profile; every assistant sees it."""

    version: int = VERSION
    revision: int = Field(default=0, ge=0)
    preferred_name: str = Field(default="", max_length=MAX_PREFERRED_NAME)
    about: str = Field(default="", max_length=MAX_ABOUT_CHARS)
    treat_person: str = Field(default="", max_length=MAX_TREAT_CHARS)

    @field_validator("preferred_name", "about", "treat_person")
    @classmethod
    def _trim(cls, value: str) -> str:
        return value.strip()


class IdentityError(ValueError):
    """A file or payload that cannot be used, with a reason a person can act on."""


class IdentityConflict(IdentityError):
    """The saved revision moved since the reviewer loaded it."""


def _directory(state_dir: Path | str) -> Path:
    directory = Path(state_dir) / DIR_NAME
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def assistant_path(state_dir: Path | str, bot_id: str) -> Path:
    return _directory(state_dir) / f"assistant-{bot_id}.json"


def person_path(state_dir: Path | str) -> Path:
    return _directory(state_dir) / "person.json"


def content_hash(model: BaseModel) -> str:
    canonical = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load(path: Path, model):
    if not path.exists():
        return model(), None
    try:
        text = path.read_text(encoding="utf-8")
        if len(text.encode("utf-8")) > MAX_FILE_BYTES:
            raise IdentityError(f"larger than {MAX_FILE_BYTES // 1024} KB")
        return model.model_validate_json(text), None
    except (OSError, UnicodeDecodeError, ValidationError, ValueError) as exc:
        return model(), f"{path.name} could not be read ({exc}); nothing from it is applied until you save a new one"


def _save(path: Path, model, updated):
    current, _ = _load(path, model)
    if updated.revision != current.revision:
        raise IdentityConflict(
            f"this text changed since you opened it (saved revision {current.revision}, "
            f"your revision {updated.revision}); reload before saving")
    payload = updated.model_copy(update={"revision": current.revision + 1}).model_dump_json(indent=2) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return updated.model_copy(update={"revision": current.revision + 1})


def load_assistant_identity(state_dir: Path | str, bot_id: str):
    return _load(assistant_path(state_dir, bot_id), AssistantIdentity)


def save_assistant_identity(state_dir: Path | str, bot_id: str, identity: AssistantIdentity):
    return _save(assistant_path(state_dir, bot_id), AssistantIdentity, identity)


def load_person_profile(state_dir: Path | str):
    return _load(person_path(state_dir), PersonProfile)


def save_person_profile(state_dir: Path | str, profile: PersonProfile):
    return _save(person_path(state_dir), PersonProfile, profile)


def render_block(identity: AssistantIdentity, profile: PersonProfile) -> str:
    """The reviewed text as the system prompt shows it. Empty when nothing is saved."""
    person: list[str] = []
    if profile.preferred_name:
        person.append(f"Preferred name: {profile.preferred_name}")
    if profile.about:
        person.append(f"About the person: {profile.about}")
    if profile.treat_person:
        person.append(f"How to treat them: {profile.treat_person}")
    parts: list[str] = []
    if person:
        parts.append("The person you work for:\n" + "\n".join(f"- {line}" for line in person))
    if identity.signature:
        parts.append(f"How you sign off:\n{identity.signature}")
    if identity.boundaries:
        parts.append("Your boundaries (advisory context; the rules of engagement and tool policy still govern):\n"
                     + "\n".join(f"- {item}" for item in identity.boundaries))
    if not parts:
        return ""
    return "Reviewed identity and boundaries:\n\n" + "\n\n".join(parts)


def prompt_block(state_dir: Path | str, bot_id: str) -> str:
    """Best-effort block for the prompt: a damaged file is never applied and never breaks a run."""
    try:
        identity, identity_problem = load_assistant_identity(state_dir, bot_id)
        profile, profile_problem = load_person_profile(state_dir)
        if identity_problem or profile_problem:
            return ""
        return render_block(identity, profile)
    except (OSError, ValueError):
        return ""
