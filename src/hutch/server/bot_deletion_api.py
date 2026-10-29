"""Typed JSON API for governed whole-Bot permanent deletion (two-step).

This module is installed from app.py with one hook line pair and follows the
install_*_routes convention used by the other JSON APIs. Whole-Bot deletion is a
local owner action: a paired-phone principal is refused with 403 even when it
reaches a route, and remote access is already outside the route capability list
(REMOTE_ROUTE_CAPABILITIES has no entry for these paths, so remote requests are
refused too). Responses never contain erased text, filesystem paths or
confirmation tokens after the preview.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .. import bot_deletion
from ..store import IdempotencyConflict
from .security import DEVICE_COOKIE

logger = logging.getLogger(__name__)

LOCAL_OWNER_REFUSAL = 'whole-Bot deletion is a local owner action'


class BotDeletionPreviewRequest(BaseModel):
    """Step one input: an optional bounded operator note; unknown fields are refused."""
    model_config = {"extra": "forbid"}
    note: str = Field(default='', max_length=1000)


class BotDeletionConfirmRequest(BaseModel):
    """Step two input: the one-time token plus the typed Bot address."""
    model_config = {"extra": "forbid"}
    token: str = Field(min_length=16, max_length=200)
    confirmation: str = Field(min_length=1, max_length=200)


class BotDeletionPreviewResource(BaseModel):
    """Exactly what a permanent erase would remove, and the token that authorizes it."""
    request_id: str
    token: str
    expires_at: str
    created_at: str
    bot_id: str
    bot_name: str
    counts: dict[str, int]
    remaining: list[str]
    confirmation_hint: str


class BotDeletionResultResource(BaseModel):
    """The committed outcome; an exact retry replays this same document."""
    request_id: str
    status: Literal['confirmed']
    deleted_at: str
    counts: dict[str, int]
    remaining: list[str]
    cleanup_state: Literal['none', 'pending', 'cleaning', 'cleaned', 'needs_attention']


class BotDeletionRequestResource(BaseModel):
    """One content-free preview or outcome in the Bot's deletion history."""
    request_id: str
    bot_id: str
    status: Literal['pending', 'confirmed', 'expired', 'superseded', 'failed']
    actor: str
    note: str
    created_at: str
    expires_at: str
    confirmed_at: str
    deleted_at: str
    cleanup_state: Literal['none', 'pending', 'cleaning', 'cleaned', 'needs_attention']
    counts: dict[str, int]
    result: dict[str, Any]


class BotDeletionRequestPageResource(BaseModel):
    """Content-free deletion previews and outcomes for one Bot, newest first."""
    requests: list[BotDeletionRequestResource]


def require_local_owner(request: Request) -> None:
    """Refuse whole-Bot deletion for a paired-phone principal; it is a local owner action.

    Remote access is already outside the route capability list, so this helper is
    the in-process defense for a paired browser session on the host itself.
    """
    principal = getattr(request.state, 'hutch_principal', None)
    if principal and principal.get('kind') == 'paired':
        raise HTTPException(403, LOCAL_OWNER_REFUSAL)


def _bot_or_404(store, ref: str):
    """Resolve one existing Bot or fail the request with the dashboard's 404 wording."""
    bot = store.get_bot(ref)
    if bot is None:
        raise HTTPException(404, f'no such bot: {ref}')
    return bot


def _record_bot_name_hash(store, request_id: str):
    """The address hash retained for one request, read from its evidence row."""
    with store._lock:
        row = store._db.execute('SELECT bot_name_hash FROM bot_deletions WHERE id = ?',
                                (request_id,)).fetchone()
    return row['bot_name_hash'] if row else None


def _confirmation_bot_id(store, ref: str, request_id: str) -> str:
    """Resolve the Bot for a confirmation, evidence first so an exact retry can replay.

    The request evidence outlives the Bot; resolving it before the live row lets an
    exact retry replay after the Bot is gone. A replay is scoped to the same typed
    Bot address, so an arbitrary name cannot replay another deleted Bot's request.
    """
    record = bot_deletion.request_record(store, request_id)
    if record is None:
        raise HTTPException(404, 'no such deletion request for this Bot')
    bot = store.get_bot(ref)
    if bot is not None:
        if bot.id != record['bot_id']:
            raise HTTPException(404, 'no such deletion request for this Bot')
        return bot.id
    if record['status'] != 'confirmed':
        raise HTTPException(404, f'no such bot: {ref}')
    address_hash = hashlib.sha256(ref.encode('utf-8')).hexdigest()
    if address_hash != _record_bot_name_hash(store, request_id):
        raise HTTPException(404, f'no such bot: {ref}')
    return record['bot_id']


def _acting_actor(store, request: Request) -> str:
    """Attribute a destructive command to the paired device when one is present."""
    token = request.cookies.get(DEVICE_COOKIE, '')
    bearer = request.headers.get('authorization', '')
    if bearer.startswith('Bearer '):
        token = bearer[7:]
    device = store.device_identity(token)
    return f'device:{device}' if device else 'operator'


def _idempotency_key(request: Request) -> str:
    """Require a bounded command key, isolated per paired credential."""
    key = (request.headers.get('Idempotency-Key') or '').strip()
    if not key:
        raise HTTPException(428, 'Idempotency-Key is required for this command')
    if len(key) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise HTTPException(422, 'Idempotency-Key must be 1-128 printable ASCII characters')
    principal = getattr(request.state, 'hutch_principal', None)
    if principal and principal.get('kind') == 'paired':
        return hashlib.sha256(f"{principal['credential_id']}:{key}".encode()).hexdigest()
    return key


def _request_digest(payload: dict) -> str:
    """Canonical digest used to detect a changed retry of the same command."""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _recover_cleanup(store) -> None:
    """Resume committed-but-uncleaned deletions without ever blocking route install."""
    try:
        bot_deletion.recover_cleanup(store)
    except Exception:
        logger.exception('whole-Bot deletion cleanup recovery failed; routes stay available')


def install_bot_deletion_routes(app, store) -> None:
    """Register the two-step whole-Bot deletion routes on one app instance."""
    _recover_cleanup(store)

    @app.get('/api/v1/bots/{ref}/deletion-requests', response_model=BotDeletionRequestPageResource)
    def list_bot_deletion_requests(ref: str, request: Request, limit: int = 20) -> dict:
        """Content-free deletion previews and outcomes for one Bot, without tokens."""
        require_local_owner(request)
        bot = _bot_or_404(store, ref)
        if not 1 <= limit <= 100:
            raise HTTPException(422, 'limit must be 1-100')
        return {'requests': bot_deletion.requests(store, bot.id, limit=limit)}

    @app.post('/api/v1/bots/{ref}/deletion-requests',
              response_model=BotDeletionPreviewResource, status_code=201)
    def preview_bot_deletion(ref: str, body: BotDeletionPreviewRequest, request: Request) -> dict:
        """Step one: show exactly what deleting the whole Bot would erase and what remains."""
        require_local_owner(request)
        bot = _bot_or_404(store, ref)
        try:
            return bot_deletion.preview(store, bot.id, actor=_acting_actor(store, request),
                                        note=body.note)
        except bot_deletion.BotDeletionConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post('/api/v1/bots/{ref}/deletion-requests/{request_id}/confirm',
              response_model=BotDeletionResultResource)
    def confirm_bot_deletion(ref: str, request_id: str, body: BotDeletionConfirmRequest,
                             request: Request) -> dict:
        """Step two: erase the whole Bot after a typed confirmation; exact retries replay."""
        require_local_owner(request)
        key = _idempotency_key(request)
        actor = _acting_actor(store, request)
        bot_id = _confirmation_bot_id(store, ref, request_id)
        digest = _request_digest({'bot_id': bot_id, 'request_id': request_id,
                                  'actor': actor, 'confirmation': body.confirmation})
        try:
            return bot_deletion.confirm(store, bot_id, request_id, token=body.token,
                                        confirmation=body.confirmation, actor=actor,
                                        idem_key=key, request_hash=digest)
        except KeyError:
            raise HTTPException(404, 'no such deletion request for this Bot') from None
        except IdempotencyConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except bot_deletion.BotDeletionConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
