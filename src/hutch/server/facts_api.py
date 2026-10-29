"""Governed permanent deletion of saved reference facts (two-step API).

Content is erased only after a preview with exact counts and a typed confirmation.
The module lives outside ``app.py`` so the frozen dashboard module can delegate
without growing, following the ``install_*_routes`` convention used by the other
JSON APIs. The small request-identity helpers below intentionally mirror the
closures in ``app.py``; ``app.py`` is frozen for size and its equivalents are
covered by the existing API suite, so both spellings are exercised by tests.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .. import fact_purge
from ..fact_memory import FactConflict
from ..store import IdempotencyConflict
from .security import DEVICE_COOKIE


class FactPurgePreviewRequest(BaseModel):
    model_config = {"extra": "forbid"}
    key: Optional[str] = Field(default=None, min_length=1, max_length=120)
    all: bool = False
    note: str = Field(default='', max_length=1000)


class FactPurgeCountsResource(BaseModel):
    fact_revisions: int
    legacy_rows: int
    outgoing_shares: int
    incoming_shares: int
    task_snapshots: int
    receipts_redacted: int
    total: int


class FactPurgePreviewResource(BaseModel):
    request_id: str
    token: str
    expires_at: str
    scope_kind: Literal['key', 'all']
    scope_key: str
    counts: FactPurgeCountsResource
    confirmation_hint: str
    remaining: list[str]


class FactPurgeConfirmRequest(BaseModel):
    model_config = {"extra": "forbid"}
    token: str = Field(min_length=16, max_length=200)
    confirmation: str = Field(min_length=1, max_length=200)


class FactPurgeResultResource(BaseModel):
    request_id: str
    status: Literal['confirmed']
    purged_at: str
    counts: FactPurgeCountsResource
    remaining: list[str]


class FactPurgeRequestResource(BaseModel):
    id: str
    scope_kind: Literal['key', 'all']
    scope_key: str
    actor: str
    note: str
    created_at: str
    expires_at: str
    confirmed_at: str
    status: Literal['pending', 'confirmed', 'expired', 'superseded']
    counts: FactPurgeCountsResource


class FactPurgeRequestPageResource(BaseModel):
    requests: list[FactPurgeRequestResource]


def _bot_or_404(store, ref):
    """Resolve one Bot or fail the request with the dashboard's 404 wording."""
    bot = store.get_bot(ref)
    if not bot:
        raise HTTPException(404, f"no such bot: {ref}")
    return bot


def _acting_actor(store, request: Request) -> str:
    """Attribute a destructive command to the paired device when one is present."""
    token = request.cookies.get(DEVICE_COOKIE, "")
    bearer = request.headers.get("authorization", "")
    if bearer.startswith("Bearer "):
        token = bearer[7:]
    device = store.device_identity(token)
    return f"device:{device}" if device else "operator"


def _idempotency_key(request: Request) -> str:
    """Require a bounded command key, isolated per paired credential."""
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key:
        raise HTTPException(428, "Idempotency-Key is required for this command")
    if len(key) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise HTTPException(422, "Idempotency-Key must be 1-128 printable ASCII characters")
    principal = getattr(request.state, "hutch_principal", None)
    if principal and principal.get("kind") == "paired":
        return hashlib.sha256(f"{principal['credential_id']}:{key}".encode()).hexdigest()
    return key


def _request_digest(payload: dict) -> str:
    """Canonical digest used to detect a changed retry of the same command."""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def install_fact_purge_routes(app, store) -> None:
    """Register the two-step permanent-deletion routes on one app instance."""

    @app.get('/api/v1/bots/{ref}/facts/purge-requests', response_model=FactPurgeRequestPageResource)
    def list_fact_purge_requests(ref: str, limit: int = 20) -> dict:
        """Recent purge previews and outcomes for one Bot, without tokens or fact text."""
        bot = _bot_or_404(store, ref)
        if not 1 <= limit <= 100:
            raise HTTPException(422, 'limit must be 1–100')
        return {'requests': fact_purge.requests(store, bot.id, limit=limit)}

    @app.post('/api/v1/bots/{ref}/facts/purge-requests', response_model=FactPurgePreviewResource,
              status_code=201)
    def preview_fact_purge(ref: str, body: FactPurgePreviewRequest, request: Request):
        """Step one: show exactly what a permanent erase would remove and what remains."""
        bot = _bot_or_404(store, ref)
        if body.all == (body.key is not None):
            raise HTTPException(422, 'choose exactly one purge scope: one key or all saved facts')
        try:
            preview = fact_purge.preview(store, bot.id, key=body.key, all=body.all,
                                               actor=_acting_actor(store, request), note=body.note)
        except FactConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return preview

    @app.post('/api/v1/bots/{ref}/facts/purge-requests/{request_id}/confirm',
              response_model=FactPurgeResultResource)
    def confirm_fact_purge(ref: str, request_id: str, body: FactPurgeConfirmRequest, request: Request):
        """Step two: erase the previewed scope after a typed confirmation."""
        bot = _bot_or_404(store, ref)
        key = _idempotency_key(request)
        actor = _acting_actor(store, request)
        try:
            return fact_purge.confirm(
                store, bot.id, request_id, token=body.token, confirmation=body.confirmation, actor=actor,
                idem_key=key,
                request_hash=_request_digest({'bot_id': bot.id, 'request_id': request_id,
                                             'actor': actor, 'confirmation': body.confirmation}))
        except KeyError:
            raise HTTPException(404, 'no such purge request for this Bot') from None
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except FactConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
