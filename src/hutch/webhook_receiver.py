"""Webhook receiver: bounded intake, untrusted-content defense, and admission.

Enforces payload size ceiling (64 KB), allowed MIME types, constant-time token
verification, dual-window secret rotation, rate/cooldown limits, idempotency
deduplication, and atomic admission into the durable run store.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from . import ingest
from .models import Run, RunStatus, Task, iso, utcnow
from .webhook_store import find_matching_source


MAX_PAYLOAD_BYTES = 64 * 1024  # 64 KB ceiling
ALLOWED_CONTENT_TYPES = frozenset({"application/json", "text/plain"})


class WebhookAdmissionError(Exception):
    """Base exception for webhook rejection."""

    def __init__(self, status_code: int, message: str, *, source_id: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.source_id = source_id


def _validate_headers_and_payload(raw_body: bytes, content_type: str) -> str:
    if len(raw_body) > MAX_PAYLOAD_BYTES:
        raise WebhookAdmissionError(413, f"payload exceeds {MAX_PAYLOAD_BYTES} bytes cap ({len(raw_body)} bytes)")

    base_type = content_type.split(";")[0].strip().lower() if content_type else "text/plain"
    if base_type not in ALLOWED_CONTENT_TYPES:
        raise WebhookAdmissionError(415, f"unsupported content-type '{content_type}'; only application/json and text/plain are accepted")
    return base_type


def _record_failure(store, source_id: str, status_code: int, error_message: str,
                    raw_body: bytes, content_type: str, idempotency_key: str, client_ip: str, stamp: str) -> None:
    delivery_id = f"whdel_{uuid.uuid4().hex[:16]}"
    body_sha = hashlib.sha256(raw_body).hexdigest()
    with store._tx() as db:
        db.execute(
            """INSERT INTO webhook_deliveries (
                id, source_id, idempotency_key, status, status_code, error_message,
                payload_bytes, payload_sha256, content_type, received_at, client_ip
            ) VALUES (?, ?, ?, 'rejected', ?, ?, ?, ?, ?, ?, ?)""",
            (delivery_id, source_id, idempotency_key, status_code, error_message[:400],
             len(raw_body), body_sha, content_type, stamp, client_ip[:64]),
        )
        db.execute(
            """UPDATE webhook_sources SET
                last_delivery_at = ?, last_error = ?, error_count = error_count + 1
            WHERE id = ?""",
            (stamp, error_message[:400], source_id),
        )


def _check_source_policy(store, source: dict[str, Any], raw_body: bytes,
                         base_type: str, idempotency_key: str, client_ip: str,
                         moment: datetime, stamp: str) -> None:
    if not source["enabled"]:
        _record_failure(store, source["id"], 409, "webhook source is paused", raw_body, base_type, idempotency_key, client_ip, stamp)
        raise WebhookAdmissionError(409, "webhook source is paused", source_id=source["id"])

    if store.workspace_schedule_control()["paused"]:
        _record_failure(store, source["id"], 409, "workspace automations are paused", raw_body, base_type, idempotency_key, client_ip, stamp)
        raise WebhookAdmissionError(409, "workspace automations are paused", source_id=source["id"])

    cooldown = float(source.get("cooldown_seconds") or 0.0)
    if cooldown > 0 and source.get("last_success_at"):
        try:
            last_dt = datetime.fromisoformat(source["last_success_at"])
            elapsed = (moment - last_dt).total_seconds()
            if elapsed < cooldown:
                msg = f"rate limited: cooldown active for {cooldown - elapsed:.1f}s"
                _record_failure(store, source["id"], 429, msg, raw_body, base_type, idempotency_key, client_ip, stamp)
                raise WebhookAdmissionError(429, msg, source_id=source["id"])
        except ValueError:
            pass

    max_hour = int(source.get("max_per_hour") or 0)
    if max_hour > 0:
        hour_ago = iso(moment - timedelta(seconds=3600))
        with store._lock:
            recent_count = store._db.execute(
                "SELECT COUNT(*) AS c FROM webhook_deliveries WHERE source_id = ? AND status = 'processed' AND received_at >= ?",
                (source["id"], hour_ago),
            ).fetchone()["c"]
        if recent_count >= max_hour:
            msg = f"rate limited: hourly quota of {max_hour} reached"
            _record_failure(store, source["id"], 429, msg, raw_body, base_type, idempotency_key, client_ip, stamp)
            raise WebhookAdmissionError(429, msg, source_id=source["id"])


def _check_idempotency(store, source_id: str, idempotency_key: str, raw_body: bytes,
                       base_type: str, client_ip: str, stamp: str) -> Optional[dict[str, Any]]:
    if not idempotency_key:
        return None
    with store._lock:
        existing = store._db.execute(
            "SELECT run_id FROM webhook_deliveries WHERE source_id = ? AND idempotency_key = ? AND status = 'processed'",
            (source_id, idempotency_key),
        ).fetchone()
    if not existing:
        return None

    run_id = existing["run_id"] or ""
    dup_id = f"whdel_{uuid.uuid4().hex[:16]}"
    body_sha = hashlib.sha256(raw_body).hexdigest()
    with store._tx() as db:
        db.execute(
            """INSERT INTO webhook_deliveries (
                id, source_id, idempotency_key, status, status_code, error_message,
                payload_bytes, payload_sha256, content_type, run_id, received_at, processed_at, client_ip
            ) VALUES (?, ?, ?, 'duplicate', 200, '', ?, ?, ?, ?, ?, ?, ?)""",
            (dup_id, source_id, idempotency_key, len(raw_body), body_sha, base_type, run_id, stamp, stamp, client_ip[:64]),
        )
    return {"status": "duplicate", "run_id": run_id, "idempotency_key": idempotency_key}


def _build_prompt(template: str, text: str, bot_name: str, source_name: str) -> str:
    findings = ingest.assess(text)
    note = ingest.annotation(findings, assessed_chars=min(len(text), ingest.DEFAULT_SCAN_CHARS), total_chars=len(text))

    if template:
        body = template.replace("{payload}", text).replace("{name}", source_name)
    else:
        body = f"Webhook payload from {source_name}:\n\n{text}"

    if note:
        return f"{note}\n\n{body}"
    return body


def admit_webhook(
    store,
    token: str,
    raw_body: bytes,
    content_type: str,
    *,
    idempotency_key: str = "",
    client_ip: str = "",
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Validate, sanitize and atomically admit an incoming webhook delivery."""
    moment = now or utcnow()
    stamp = iso(moment)
    base_type = _validate_headers_and_payload(raw_body, content_type)

    matched = find_matching_source(store, token, now=moment)
    if not matched:
        raise WebhookAdmissionError(401, "invalid or expired webhook token")
    source, _is_prev = matched

    clean_idem = (idempotency_key or "").strip()[:200]
    _check_source_policy(store, source, raw_body, base_type, clean_idem, client_ip, moment, stamp)

    duplicate_result = _check_idempotency(store, source["id"], clean_idem, raw_body, base_type, client_ip, stamp)
    if duplicate_result:
        return duplicate_result

    text = raw_body.decode("utf-8", errors="replace")
    prompt = _build_prompt(source.get("prompt_template") or "", text, source["bot_id"], source["name"])

    task_id = f"task_{uuid.uuid4().hex[:16]}"
    run_id = f"run_{uuid.uuid4().hex[:16]}"
    delivery_id = f"whdel_{uuid.uuid4().hex[:16]}"
    body_sha = hashlib.sha256(raw_body).hexdigest()

    task = Task(id=task_id, bot_id=source["bot_id"], kind="webhook", prompt=prompt, created_at=stamp, done=False, state="queued", run_id=run_id)
    run = Run(id=run_id, bot_id=source["bot_id"], task_id=task_id, status=RunStatus.pending, created_at=stamp, prompt=prompt, origin=f"webhook:{source['id']}")

    with store._tx() as db:
        store._assert_execution_ready(db, run.bot_id)
        db.execute(
            """INSERT INTO webhook_deliveries (
                id, source_id, idempotency_key, status, status_code, error_message,
                payload_bytes, payload_sha256, content_type, run_id, received_at, processed_at, client_ip
            ) VALUES (?, ?, ?, 'processed', 200, '', ?, ?, ?, ?, ?, ?, ?)""",
            (delivery_id, source["id"], clean_idem, len(raw_body), body_sha, base_type, run_id, stamp, stamp, client_ip[:64]),
        )
        db.execute(
            """UPDATE webhook_sources SET
                last_delivery_at = ?, last_success_at = ?, error_count = 0, last_error = ''
            WHERE id = ?""",
            (stamp, stamp, source["id"]),
        )
        db.execute(
            """INSERT INTO tasks (id, bot_id, kind, prompt, created_at, done, state, run_id)
            VALUES (?, ?, ?, ?, ?, 0, 'queued', ?)""",
            (task.id, task.bot_id, task.kind, task.prompt, task.created_at, run.id),
        )
        import json
        db.execute(
            """INSERT INTO runs (id, bot_id, task_id, doc, status, created_at, conversation_id, conversation_context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run.id, run.bot_id, task.id, store._run_json(run), run.status.value, run.created_at,
             run.conversation_id, json.dumps(run.conversation_context, ensure_ascii=False)),
        )

    store.bus.notify("work", "runs", "webhooks", f"run:{run.id}")
    return {"status": "admitted", "run_id": run.id, "delivery_id": delivery_id}
