"""Shared-space and Today routes for the personal operations API."""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException

from ..personal import Space, SpaceMember
from ..personal.models import SpaceMemberStatus, SpaceRole
from ..personal.spaces import SpaceRepo
from ..personal.store import PersonalStore
from ..personal.today import InvalidTimezone, build_today
from ..store import RevisionConflict
from .personal_api import wrap_error
from .personal_api_models import (
    SpaceArchive, SpaceBotGrant, SpaceCreate, SpaceMemberCreate, SpaceMemberPatch, SpacePatch,
)


def install_personal_space_routes(app: FastAPI, store, personal: PersonalStore) -> None:
    spaces: SpaceRepo = personal.spaces

    @app.get("/api/v1/today")
    def today(timezone: Optional[str] = None) -> dict:
        try:
            return build_today(store, timezone_name=timezone)
        except InvalidTimezone as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/v1/spaces")
    def list_spaces(include_archived: bool = False) -> dict:
        items = []
        for space in spaces.list(include_archived=include_archived):
            items.append(spaces.public(space.id))
        return {"items": items, "count": len(items)}

    @app.post("/api/v1/spaces", status_code=201)
    def create_space(body: SpaceCreate) -> dict:
        store.assert_execution_ready()
        try:
            space = spaces.create(Space(name=body.name, kind=body.kind, description=body.description))
        except ValueError as exc:
            raise wrap_error(exc) from None
        return spaces.public(space.id)

    @app.get("/api/v1/spaces/{space_id}")
    def get_space(space_id: str) -> dict:
        try:
            return spaces.public(space_id)
        except KeyError:
            raise HTTPException(404, "No such shared space") from None

    @app.patch("/api/v1/spaces/{space_id}")
    def patch_space(space_id: str, body: SpacePatch) -> dict:
        store.assert_execution_ready()
        changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"}, mode="json")
        changes = {key: value for key, value in changes.items() if value is not None}
        try:
            spaces.update(space_id, changes, expected_revision=body.expected_revision)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return spaces.public(space_id)

    @app.post("/api/v1/spaces/{space_id}/archive")
    def archive_space(space_id: str, body: SpaceArchive) -> dict:
        store.assert_execution_ready()
        try:
            spaces.archive(space_id, expected_revision=body.expected_revision)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return spaces.public(space_id)

    @app.post("/api/v1/spaces/{space_id}/members", status_code=201)
    def add_member(space_id: str, body: SpaceMemberCreate) -> dict:
        store.assert_execution_ready()
        try:
            generated = SpaceMember(display_name=body.display_name, role=body.role)
            spaces.add_member(space_id, generated)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return spaces.public(space_id)

    @app.patch("/api/v1/spaces/{space_id}/members/{member_id}")
    def patch_member(space_id: str, member_id: str, body: SpaceMemberPatch) -> dict:
        store.assert_execution_ready()
        changes = body.model_dump(exclude_unset=True, mode="json")
        changes = {key: value for key, value in changes.items() if value is not None}
        if "role" in changes:
            changes["role"] = SpaceRole(changes["role"])
        if "status" in changes:
            changes["status"] = SpaceMemberStatus(changes["status"])
        try:
            spaces.update_member(space_id, member_id, changes)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return spaces.public(space_id)

    @app.delete("/api/v1/spaces/{space_id}/members/{member_id}", status_code=200)
    def revoke_member(space_id: str, member_id: str) -> dict:
        store.assert_execution_ready()
        try:
            spaces.revoke_member(space_id, member_id)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return spaces.public(space_id)

    @app.post("/api/v1/spaces/{space_id}/bots")
    def grant_bot(space_id: str, body: SpaceBotGrant) -> dict:
        store.assert_execution_ready()
        try:
            return spaces.grant(space_id, body.bot_id)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None

    @app.delete("/api/v1/spaces/{space_id}/bots/{bot_id}")
    def revoke_bot(space_id: str, bot_id: str) -> dict:
        store.assert_execution_ready()
        try:
            return spaces.revoke_grant(space_id, bot_id)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
