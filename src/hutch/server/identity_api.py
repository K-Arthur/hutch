"""Identity API: the person's profile and each assistant's boundaries, reviewed before saving.

These routes are owner configuration (local-owner-only; paired phones are refused by the default-deny
inventory). A save carries the revision the reviewer saw, so two tabs cannot silently overwrite each other;
a damaged file on disk is reported and never applied. Nothing here is written by a model tool.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import identity as identity_store
from ..identity import MAX_BOUNDARIES, MAX_BOUNDARY_CHARS, MAX_SIGNATURE_CHARS


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssistantIdentityUpdate(_Strict):
    expected_revision: int = Field(ge=0)
    signature: str = Field(default="", max_length=MAX_SIGNATURE_CHARS)
    boundaries: list[str] = Field(default_factory=list, max_length=MAX_BOUNDARIES)


class PersonProfileUpdate(_Strict):
    expected_revision: int = Field(ge=0)
    preferred_name: str = Field(default="", max_length=identity_store.MAX_PREFERRED_NAME)
    about: str = Field(default="", max_length=identity_store.MAX_ABOUT_CHARS)
    treat_person: str = Field(default="", max_length=identity_store.MAX_TREAT_CHARS)


def install_identity_routes(app: FastAPI, store, config) -> None:
    from .bot_deletion_api import require_local_owner

    state_dir = config.state_dir

    def bot_or_404(ref: str):
        bot = store.get_bot(ref)
        if bot is None:
            raise HTTPException(404, f"no such bot: {ref}")
        return bot

    def bounded(reason: Exception) -> HTTPException:
        first = reason.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "identity"
        return HTTPException(422, f"{where}: {first['msg']}")

    def assistant_payload(bot, document, problem=None) -> dict:
        profile, profile_problem = identity_store.load_person_profile(state_dir)
        diagnostics = [line for line in (problem, profile_problem) if line]
        return {"bot": bot.name, "identity": document.model_dump(mode="json"),
                "content_hash": identity_store.content_hash(document),
                "rendered": identity_store.render_block(document, profile),
                "diagnostics": diagnostics,
                "limits": {"max_boundaries": MAX_BOUNDARIES, "max_boundary_chars": MAX_BOUNDARY_CHARS,
                           "max_signature_chars": MAX_SIGNATURE_CHARS}}

    def person_payload(document, problem=None) -> dict:
        return {"profile": document.model_dump(mode="json"),
                "content_hash": identity_store.content_hash(document),
                "rendered": identity_store.render_block(identity_store.AssistantIdentity(), document),
                "diagnostics": [line for line in (problem,) if line],
                "shared_with_every_assistant": True}

    @app.get("/api/v1/identity/person")
    def get_person_profile() -> dict:
        document, problem = identity_store.load_person_profile(state_dir)
        return person_payload(document, problem)

    @app.put("/api/v1/identity/person")
    def put_person_profile(body: PersonProfileUpdate, request: Request) -> dict:
        require_local_owner(request)
        document = identity_store.PersonProfile(
            revision=body.expected_revision, preferred_name=body.preferred_name,
            about=body.about, treat_person=body.treat_person)
        try:
            saved = identity_store.save_person_profile(state_dir, document)
        except identity_store.IdentityConflict as exc:
            raise HTTPException(409, str(exc)) from None
        return person_payload(saved)

    @app.get("/api/v1/bots/{ref}/identity")
    def get_assistant_identity(ref: str) -> dict:
        bot = bot_or_404(ref)
        document, problem = identity_store.load_assistant_identity(state_dir, bot.id)
        return assistant_payload(bot, document, problem)

    @app.put("/api/v1/bots/{ref}/identity")
    def put_assistant_identity(ref: str, body: AssistantIdentityUpdate, request: Request) -> dict:
        require_local_owner(request)
        bot = bot_or_404(ref)
        try:
            document = identity_store.AssistantIdentity(
                revision=body.expected_revision, signature=body.signature, boundaries=body.boundaries)
        except ValidationError as exc:
            raise bounded(exc) from None
        try:
            saved = identity_store.save_assistant_identity(state_dir, bot.id, document)
        except identity_store.IdentityConflict as exc:
            raise HTTPException(409, str(exc)) from None
        return assistant_payload(bot, saved)
