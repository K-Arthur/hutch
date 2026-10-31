"""Personal operations API: commitments with provenance, confirmation and evidence.

Mounted from create_app like the other split API modules. This module owns the
commitment commands; spaces and the Today briefing live in personal_spaces_api.
The dashboard is the owner surface, so owner commands create confirmed records
and owner-confirmed completions. Assistant tools have their own narrower paths.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response

from ..personal import Commitment, CompletionKind
from ..personal.commitments import ANY_SPACE, public
from ..personal.store import PersonalStore
from ..personal.today import InvalidTimezone
from ..store import RevisionConflict
from .personal_api_models import (
    CommitmentComplete, CommitmentCreate, CommitmentDependencies, CommitmentPatch, CommitmentRevision,
)


def resource(commitment: Commitment, blocked: bool = False) -> dict[str, Any]:
    return public(commitment, blocked=blocked)


def wrap_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(404, "No such commitment")
    if isinstance(exc, RevisionConflict):
        return HTTPException(409, str(exc))
    if isinstance(exc, (InvalidTimezone, ValueError)):
        return HTTPException(422, str(exc))
    return HTTPException(500, "The commitment command could not be completed")


def idempotency_key(request: Request) -> str:
    """The same command-key contract as the other split API modules."""
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key:
        raise HTTPException(428, "Idempotency-Key is required for this command")
    if len(key) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise HTTPException(422, "Idempotency-Key must be 1-128 printable ASCII characters")
    principal = getattr(request.state, "hutch_principal", None)
    if principal and principal.get("kind") == "paired":
        return hashlib.sha256(f"{principal['credential_id']}:{key}".encode()).hexdigest()
    return key


def request_digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def install_personal_routes(app: FastAPI, store, config) -> None:
    from .personal_spaces_api import install_personal_space_routes
    personal = PersonalStore(store)

    @app.get("/api/v1/commitments")
    def list_commitments(status: Optional[str] = None, space: Optional[str] = None,
                         include_proposed: bool = True, limit: int = 200,
                         offset: int = 0) -> dict:
        if status not in (None, "open", "done", "cancelled"):
            raise HTTPException(422, "status must be open, done or cancelled")
        if space in (None, ""):
            scope: Any = ANY_SPACE
        elif space == "personal":
            scope = None
        else:
            if personal.spaces.get(space) is None:
                raise HTTPException(404, "No such shared space")
            scope = space
        rows = personal.commitments.list(status=status, space=scope, include_proposed=include_proposed,
                                         limit=min(max(1, limit), 500), offset=max(0, offset))
        blocked = personal.commitments.blocked_map([row.id for row in rows])
        counts = {
            "open": sum(1 for row in rows if row.status.value == "open"),
            "done": sum(1 for row in rows if row.status.value == "done"),
            "cancelled": sum(1 for row in rows if row.status.value == "cancelled"),
        }
        return {"items": [resource(row, blocked.get(row.id, False)) for row in rows],
                "counts": counts, "next_offset": None}

    @app.post("/api/v1/commitments", status_code=201)
    def create_commitment(body: CommitmentCreate, request: Request, response: Response) -> dict:
        store.assert_execution_ready()
        key, digest = idempotency_key(request), request_digest(body.model_dump(mode="json"))
        try:
            commitment = Commitment(title=body.title, detail=body.detail, priority=body.priority,
                                    due_at=body.due_at, due_timezone=body.due_timezone,
                                    category=body.category, space_id=body.space_id,
                                    source="user", created_by="owner", confirmation="confirmed")
            saved, created = personal.commitments.create(commitment, idem_key=key, request_hash=digest,
                                                         actor="owner")
        except ValueError as exc:
            raise wrap_error(exc) from None
        response.status_code = 201 if created else 200
        return resource(saved)

    @app.get("/api/v1/commitments/{commitment_id}")
    def get_commitment(commitment_id: str) -> dict:
        commitment = personal.commitments.get(commitment_id)
        if commitment is None:
            raise HTTPException(404, "No such commitment")
        blocked = personal.commitments.blocked_map([commitment.id]).get(commitment.id, False)
        return resource(commitment, blocked)

    @app.patch("/api/v1/commitments/{commitment_id}")
    def patch_commitment(commitment_id: str, body: CommitmentPatch) -> dict:
        store.assert_execution_ready()
        changes = body.model_dump(exclude_unset=True, exclude={"expected_revision"}, mode="json")
        # An omitted field is untouched; explicit null clears an optional date or scope.
        changes = {key: value for key, value in changes.items() if value is not None or key in ("due_at", "space_id")}
        try:
            updated = personal.commitments.update(commitment_id, changes,
                                                  expected_revision=body.expected_revision, actor="owner")
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return resource(updated)

    @app.post("/api/v1/commitments/{commitment_id}/confirm")
    def confirm_commitment(commitment_id: str, body: CommitmentRevision) -> dict:
        store.assert_execution_ready()
        try:
            updated = personal.commitments.confirm(commitment_id, expected_revision=body.expected_revision)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return resource(updated)

    @app.post("/api/v1/commitments/{commitment_id}/complete")
    def complete_commitment(commitment_id: str, body: CommitmentComplete) -> dict:
        store.assert_execution_ready()
        try:
            updated = personal.commitments.complete(
                commitment_id, evidence=body.evidence, kind=CompletionKind.owner_confirmed,
                actor="owner", expected_revision=body.expected_revision)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return resource(updated)

    @app.post("/api/v1/commitments/{commitment_id}/verify")
    def verify_commitment(commitment_id: str, body: CommitmentRevision) -> dict:
        store.assert_execution_ready()
        try:
            updated = personal.commitments.verify_completion(commitment_id,
                                                             expected_revision=body.expected_revision)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return resource(updated)

    @app.post("/api/v1/commitments/{commitment_id}/reopen")
    def reopen_commitment(commitment_id: str, body: CommitmentRevision) -> dict:
        store.assert_execution_ready()
        try:
            updated = personal.commitments.reopen(commitment_id, expected_revision=body.expected_revision)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return resource(updated)

    @app.post("/api/v1/commitments/{commitment_id}/cancel")
    def cancel_commitment(commitment_id: str, body: CommitmentRevision) -> dict:
        store.assert_execution_ready()
        try:
            updated = personal.commitments.cancel(commitment_id, expected_revision=body.expected_revision)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return resource(updated)

    @app.put("/api/v1/commitments/{commitment_id}/dependencies")
    def set_commitment_dependencies(commitment_id: str, body: CommitmentDependencies) -> dict:
        store.assert_execution_ready()
        try:
            updated = personal.commitments.set_dependencies(
                commitment_id, body.depends_on, expected_revision=body.expected_revision)
        except (KeyError, RevisionConflict, ValueError) as exc:
            raise wrap_error(exc) from None
        return resource(updated)

    @app.get("/api/v1/commitments/{commitment_id}/events")
    def commitment_events(commitment_id: str, limit: int = 100) -> dict:
        if personal.commitments.get(commitment_id) is None:
            raise HTTPException(404, "No such commitment")
        return {"items": personal.commitments.events(commitment_id, limit=limit)}

    install_personal_space_routes(app, store, personal)
