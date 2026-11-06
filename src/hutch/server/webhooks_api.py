"""Inbound webhook ingress and local-owner management API routes.

Provides public webhook ingress on /api/v1/webhooks/{token} and local-owner
CRUD and secret rotation endpoints for webhook sources.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..store import RevisionConflict
from ..webhook_receiver import WebhookAdmissionError, admit_webhook
from ..webhook_store import (
    create_webhook_source,
    delete_webhook_source,
    get_webhook_source,
    list_webhook_deliveries,
    list_webhook_sources,
    rotate_webhook_secret,
    update_webhook_source,
)


class WebhookSourceCreate(BaseModel):
    bot_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    prompt_template: str = ""
    workflow_id: str = ""
    cooldown_seconds: float = Field(default=0.0, ge=0.0)
    max_per_hour: int = Field(default=60, ge=0)
    enabled: bool = True


class WebhookSourceUpdate(BaseModel):
    name: Optional[str] = None
    prompt_template: Optional[str] = None
    workflow_id: Optional[str] = None
    cooldown_seconds: Optional[float] = Field(default=None, ge=0.0)
    max_per_hour: Optional[int] = Field(default=None, ge=0)
    enabled: Optional[bool] = None
    expected_revision: Optional[int] = Field(default=None, ge=1)


class WebhookSourceRotate(BaseModel):
    overlap_hours: int = Field(default=24, ge=1, le=168)
    expected_revision: Optional[int] = Field(default=None, ge=1)


def register_webhook_routes(app, store, bot_or_404) -> None:
    """Register public webhook ingress and owner CRUD routes."""

    @app.post("/api/v1/webhooks/{token}")
    async def post_webhook(token: str, request: Request) -> dict[str, Any]:
        raw_body = await request.body()
        content_type = request.headers.get("content-type", "")
        idem = (
            request.headers.get("idempotency-key")
            or request.headers.get("x-idempotency-key")
            or ""
        )
        if not idem and "application/json" in content_type:
            try:
                parsed = json.loads(raw_body.decode("utf-8"))
                if isinstance(parsed, dict) and "idempotency_key" in parsed:
                    idem = str(parsed["idempotency_key"])
            except Exception:
                pass

        client_ip = request.client.host if request.client else ""
        try:
            return admit_webhook(
                store,
                token,
                raw_body,
                content_type,
                idempotency_key=idem,
                client_ip=client_ip,
            )
        except WebhookAdmissionError as exc:
            raise HTTPException(exc.status_code, exc.message) from None

    @app.get("/api/v1/webhook-sources")
    def get_webhook_sources(bot_id: Optional[str] = Query(None)) -> list[dict[str, Any]]:
        return list_webhook_sources(store, bot_id=bot_id)

    @app.post("/api/v1/webhook-sources")
    def post_webhook_source(body: WebhookSourceCreate) -> dict[str, Any]:
        bot_or_404(body.bot_id)
        try:
            source, raw_token = create_webhook_source(
                store,
                bot_id=body.bot_id,
                name=body.name,
                prompt_template=body.prompt_template,
                workflow_id=body.workflow_id,
                cooldown_seconds=body.cooldown_seconds,
                max_per_hour=body.max_per_hour,
                enabled=body.enabled,
            )
            return {"source": source, "token": raw_token}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/v1/webhook-sources/{source_id}")
    def get_single_webhook_source(source_id: str) -> dict[str, Any]:
        source = get_webhook_source(store, source_id)
        if not source:
            raise HTTPException(404, f"webhook source not found: {source_id}")
        return source

    @app.put("/api/v1/webhook-sources/{source_id}")
    def put_webhook_source(source_id: str, body: WebhookSourceUpdate) -> dict[str, Any]:
        try:
            return update_webhook_source(
                store,
                source_id,
                name=body.name,
                prompt_template=body.prompt_template,
                workflow_id=body.workflow_id,
                cooldown_seconds=body.cooldown_seconds,
                max_per_hour=body.max_per_hour,
                enabled=body.enabled,
                expected_revision=body.expected_revision,
            )
        except KeyError:
            raise HTTPException(404, f"webhook source not found: {source_id}") from None
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/v1/webhook-sources/{source_id}/rotate-secret")
    def post_rotate_secret(source_id: str, body: WebhookSourceRotate) -> dict[str, Any]:
        try:
            source, raw_token = rotate_webhook_secret(
                store,
                source_id,
                overlap_hours=body.overlap_hours,
                expected_revision=body.expected_revision,
            )
            return {"source": source, "token": raw_token}
        except KeyError:
            raise HTTPException(404, f"webhook source not found: {source_id}") from None
        except RevisionConflict as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post("/api/v1/webhook-sources/{source_id}/pause")
    def post_pause_webhook_source(source_id: str) -> dict[str, Any]:
        try:
            return update_webhook_source(store, source_id, enabled=False)
        except KeyError:
            raise HTTPException(404, f"webhook source not found: {source_id}") from None

    @app.post("/api/v1/webhook-sources/{source_id}/resume")
    def post_resume_webhook_source(source_id: str) -> dict[str, Any]:
        try:
            return update_webhook_source(store, source_id, enabled=True)
        except KeyError:
            raise HTTPException(404, f"webhook source not found: {source_id}") from None

    @app.delete("/api/v1/webhook-sources/{source_id}")
    def delete_single_webhook_source(source_id: str) -> dict[str, Any]:
        deleted = delete_webhook_source(store, source_id)
        if not deleted:
            raise HTTPException(404, f"webhook source not found: {source_id}")
        return {"deleted": True, "id": source_id}

    @app.get("/api/v1/webhook-sources/{source_id}/deliveries")
    def get_source_deliveries(
        source_id: str,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> list[dict[str, Any]]:
        source = get_webhook_source(store, source_id)
        if not source:
            raise HTTPException(404, f"webhook source not found: {source_id}")
        return list_webhook_deliveries(store, source_id, limit=limit, offset=offset)
