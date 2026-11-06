"""Webhook source persistence, token generation and dual-secret rotation.

All secrets are hashed with SHA-256 at rest and verified in constant time.
The raw secret is returned exactly once upon creation or rotation.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional
import uuid

from .models import iso, utcnow


MAX_DELIVERIES_LIMIT = 100
DEFAULT_ROTATION_WINDOW_HOURS = 24


def generate_webhook_token() -> tuple[str, str, str]:
    """Generate a high-entropy secret token, short prefix, and SHA-256 hash."""
    raw = f"whsec_{secrets.token_urlsafe(32)}"
    prefix = f"{raw[:10]}..."
    token_hash = hash_token(raw)
    return raw, prefix, token_hash


def hash_token(token: str) -> str:
    """Compute the SHA-256 digest of a webhook token string."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "bot_id": row["bot_id"],
        "name": row["name"],
        "token_prefix": row["token_prefix"],
        "prev_token_prefix": row["prev_token_prefix"],
        "prev_token_expires_at": row["prev_token_expires_at"],
        "prompt_template": row["prompt_template"],
        "workflow_id": row["workflow_id"],
        "cooldown_seconds": row["cooldown_seconds"],
        "max_per_hour": row["max_per_hour"],
        "enabled": bool(row["enabled"]),
        "revision": row["revision"],
        "last_delivery_at": row["last_delivery_at"],
        "last_success_at": row["last_success_at"],
        "last_error": row["last_error"],
        "error_count": row["error_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_webhook_source(
    store,
    *,
    bot_id: str,
    name: str,
    prompt_template: str = "",
    workflow_id: str = "",
    cooldown_seconds: float = 0.0,
    max_per_hour: int = 60,
    enabled: bool = True,
    now: Optional[datetime] = None,
) -> tuple[dict[str, Any], str]:
    """Create a new webhook source, storing only the hash and returning the raw secret once."""
    moment = now or utcnow()
    stamp = iso(moment)
    raw_token, prefix, token_hash = generate_webhook_token()
    source_id = f"whsrc_{uuid.uuid4().hex[:16]}"
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("webhook source name must not be empty")

    with store._tx() as db:
        bot_exists = db.execute("SELECT 1 FROM bots WHERE id = ?", (bot_id,)).fetchone()
        if not bot_exists:
            raise KeyError(f"bot not found: {bot_id}")

        db.execute(
            """INSERT INTO webhook_sources (
                id, bot_id, name, token_prefix, token_hash, prompt_template,
                workflow_id, cooldown_seconds, max_per_hour, enabled, revision,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                source_id, bot_id, clean_name, prefix, token_hash,
                prompt_template.strip(), workflow_id.strip(),
                max(0.0, float(cooldown_seconds)), max(0, int(max_per_hour)),
                1 if enabled else 0, stamp, stamp,
            ),
        )
        row = db.execute("SELECT * FROM webhook_sources WHERE id = ?", (source_id,)).fetchone()
        return _row_to_dict(row), raw_token


def get_webhook_source(store, source_id: str) -> Optional[dict[str, Any]]:
    """Fetch a webhook source by id, omitting secret hashes."""
    with store._lock:
        row = store._db.execute("SELECT * FROM webhook_sources WHERE id = ?", (source_id,)).fetchone()
        return _row_to_dict(row) if row else None


def list_webhook_sources(store, bot_id: Optional[str] = None) -> list[dict[str, Any]]:
    """List webhook sources, optionally filtered by bot_id."""
    with store._lock:
        if bot_id:
            rows = store._db.execute(
                "SELECT * FROM webhook_sources WHERE bot_id = ? ORDER BY created_at DESC",
                (bot_id,),
            ).fetchall()
        else:
            rows = store._db.execute(
                "SELECT * FROM webhook_sources ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]


def update_webhook_source(
    store,
    source_id: str,
    *,
    name: Optional[str] = None,
    prompt_template: Optional[str] = None,
    workflow_id: Optional[str] = None,
    cooldown_seconds: Optional[float] = None,
    max_per_hour: Optional[int] = None,
    enabled: Optional[bool] = None,
    expected_revision: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Update settings on a webhook source with revision CAS check."""
    stamp = iso(now or utcnow())
    with store._tx() as db:
        curr = db.execute("SELECT * FROM webhook_sources WHERE id = ?", (source_id,)).fetchone()
        if not curr:
            raise KeyError(f"webhook source not found: {source_id}")
        if expected_revision is not None and curr["revision"] != expected_revision:
            from .store import RevisionConflict
            raise RevisionConflict(f"revision conflict: expected {expected_revision}, got {curr['revision']}")

        new_name = name.strip() if name is not None else curr["name"]
        if not new_name:
            raise ValueError("webhook source name must not be empty")
        new_template = prompt_template.strip() if prompt_template is not None else curr["prompt_template"]
        new_wf = workflow_id.strip() if workflow_id is not None else curr["workflow_id"]
        new_cooldown = max(0.0, float(cooldown_seconds)) if cooldown_seconds is not None else curr["cooldown_seconds"]
        new_max_hour = max(0, int(max_per_hour)) if max_per_hour is not None else curr["max_per_hour"]
        new_enabled = (1 if enabled else 0) if enabled is not None else curr["enabled"]

        db.execute(
            """UPDATE webhook_sources SET
                name = ?, prompt_template = ?, workflow_id = ?, cooldown_seconds = ?,
                max_per_hour = ?, enabled = ?, revision = revision + 1, updated_at = ?
            WHERE id = ?""",
            (new_name, new_template, new_wf, new_cooldown, new_max_hour, new_enabled, stamp, source_id),
        )
        row = db.execute("SELECT * FROM webhook_sources WHERE id = ?", (source_id,)).fetchone()
        return _row_to_dict(row)


def rotate_webhook_secret(
    store,
    source_id: str,
    *,
    overlap_hours: int = DEFAULT_ROTATION_WINDOW_HOURS,
    expected_revision: Optional[int] = None,
    now: Optional[datetime] = None,
) -> tuple[dict[str, Any], str]:
    """Rotate secret token, preserving the old token for the overlap window."""
    moment = now or utcnow()
    stamp = iso(moment)
    prev_expires = iso(moment + timedelta(hours=max(1, int(overlap_hours))))
    new_raw, new_prefix, new_hash = generate_webhook_token()

    with store._tx() as db:
        curr = db.execute("SELECT * FROM webhook_sources WHERE id = ?", (source_id,)).fetchone()
        if not curr:
            raise KeyError(f"webhook source not found: {source_id}")
        if expected_revision is not None and curr["revision"] != expected_revision:
            from .store import RevisionConflict
            raise RevisionConflict(f"revision conflict: expected {expected_revision}, got {curr['revision']}")

        db.execute(
            """UPDATE webhook_sources SET
                prev_token_prefix = token_prefix,
                prev_token_hash = token_hash,
                prev_token_expires_at = ?,
                token_prefix = ?,
                token_hash = ?,
                revision = revision + 1,
                updated_at = ?
            WHERE id = ?""",
            (prev_expires, new_prefix, new_hash, stamp, source_id),
        )
        row = db.execute("SELECT * FROM webhook_sources WHERE id = ?", (source_id,)).fetchone()
        return _row_to_dict(row), new_raw


def delete_webhook_source(store, source_id: str) -> bool:
    """Delete a webhook source and its deliveries (via cascade)."""
    with store._tx() as db:
        res = db.execute("DELETE FROM webhook_sources WHERE id = ?", (source_id,))
        return res.rowcount > 0


def list_webhook_deliveries(store, source_id: str, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """List recent delivery events for a webhook source."""
    safe_limit = max(1, min(int(limit), MAX_DELIVERIES_LIMIT))
    safe_offset = max(0, int(offset))
    with store._lock:
        rows = store._db.execute(
            """SELECT * FROM webhook_deliveries
            WHERE source_id = ?
            ORDER BY received_at DESC, id DESC
            LIMIT ? OFFSET ?""",
            (source_id, safe_limit, safe_offset),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "source_id": r["source_id"],
                "idempotency_key": r["idempotency_key"],
                "status": r["status"],
                "status_code": r["status_code"],
                "error_message": r["error_message"],
                "payload_bytes": r["payload_bytes"],
                "payload_sha256": r["payload_sha256"],
                "content_type": r["content_type"],
                "run_id": r["run_id"],
                "received_at": r["received_at"],
                "processed_at": r["processed_at"],
                "client_ip": r["client_ip"],
            }
            for r in rows
        ]


def find_matching_source(
    store, candidate_token: str, *, now: Optional[datetime] = None
) -> Optional[tuple[dict[str, Any], bool]]:
    """Identify the webhook source in constant time using its SHA-256 digest."""
    candidate_hash = hash_token(candidate_token)
    current_stamp = iso(now or utcnow())
    with store._lock:
        rows = store._db.execute("SELECT * FROM webhook_sources").fetchall()
        for row in rows:
            if hmac.compare_digest(candidate_hash, row["token_hash"]):
                return _row_to_dict(row), False
            if row["prev_token_hash"] and hmac.compare_digest(candidate_hash, row["prev_token_hash"]):
                if row["prev_token_expires_at"] and row["prev_token_expires_at"] > current_stamp:
                    return _row_to_dict(row), True
        return None
