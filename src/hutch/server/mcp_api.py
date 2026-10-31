"""Local-owner administration of MCP connectors (ADR-0017 S2/S3).

Configuring a connector means choosing a program to run on this machine or an endpoint to reach,
so every route here is local-owner-only by construction: none of them appear in
``REMOTE_ROUTE_CAPABILITIES``, so a paired phone receives 403 from the inventory check.

The routes are deliberately thin. Each one calls one ``integrations.mcp.service`` function and
returns the evidence the interface shows: what is installed, what was discovered, what an
assistant may use, and why something is refused. A refusal is a 409 with the service's own
sentence, never a generic failure.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from ..integrations.mcp import service
from ..integrations.mcp.config import McpConfigurationError
from ..integrations.mcp.discovery import McpToolSchemaError
from ..integrations.mcp.network import McpEndpointError
from ..integrations.mcp.persistence import McpStoreError

INTEGRATION_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ConnectorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integration_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    definition: dict[str, Any]


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bot: str = Field(min_length=1, max_length=100)
    tools: list[str] = Field(min_length=1, max_length=200)
    operation_classes: dict[str, str] = Field(default_factory=dict)
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")


def _refusal(exc: Exception) -> HTTPException:
    """A connector refusal is the service's own sentence, not a stack trace or a bare 400."""
    return HTTPException(409, str(exc)[:400])


def install_mcp_routes(app, store) -> None:
    @app.get("/api/v1/integrations")
    def list_connectors(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"connectors": service.overview(store),
                "detail": ("Each connector is installed here, tested here, and then granted to named "
                           "assistants. Installing and testing never run a tool; nothing is authorized "
                           "until you grant it.")}

    @app.post("/api/v1/integrations")
    def configure_connector(body: ConnectorBody, response: Response):
        if not INTEGRATION_ID.match(body.integration_id):
            raise HTTPException(400, "connector id must be a lowercase slug starting with a letter")
        try:
            result = service.configure(store, integration_id=body.integration_id,
                                       title=body.title, raw_definition=body.definition)
        except (McpConfigurationError, McpEndpointError, McpStoreError) as exc:
            raise _refusal(exc) from None
        response.headers["Cache-Control"] = "no-store"
        return result

    @app.get("/api/v1/integrations/{integration_id}")
    def connector_detail(integration_id: str, response: Response):
        try:
            result = service.detail(store, integration_id)
        except McpStoreError as exc:
            raise HTTPException(404, str(exc)) from None
        response.headers["Cache-Control"] = "no-store"
        return result

    @app.post("/api/v1/integrations/{integration_id}/test")
    def test_connector(integration_id: str, response: Response):
        """Start the server once, read its catalog, and stop it. No tool is executed."""
        try:
            result = service.discover(store, integration_id=integration_id)
        except (McpConfigurationError, McpEndpointError, McpStoreError) as exc:
            raise _refusal(exc) from None
        except McpToolSchemaError as exc:
            raise HTTPException(409, f"the connector's tool catalog was refused: {exc}") from None
        response.headers["Cache-Control"] = "no-store"
        return {"integration_id": integration_id, "tool_count": result["tools"],
                "invalidated": result["invalidated"], "catalog": result["catalog"],
                "detail": "Testing reads the connector's tool list only. It never calls a tool."}

    @app.post("/api/v1/integrations/{integration_id}/grants")
    def grant_connector(integration_id: str, body: GrantBody, response: Response):
        try:
            result = service.grant(store, integration_id=integration_id, bot_ref=body.bot,
                                   tool_names=body.tools, operation_classes=body.operation_classes,
                                   expected_revision=body.revision)
        except McpStoreError as exc:
            raise _refusal(exc) from None
        response.headers["Cache-Control"] = "no-store"
        return result

    @app.delete("/api/v1/integrations/{integration_id}/grants/{bot}")
    def revoke_connector(integration_id: str, bot: str, response: Response):
        try:
            result = service.revoke(store, integration_id=integration_id, bot_ref=bot)
        except McpStoreError as exc:
            raise _refusal(exc) from None
        response.headers["Cache-Control"] = "no-store"
        return {**result, "detail": "Revocation applies to the next tool call, not the next run."}

    @app.delete("/api/v1/integrations/{integration_id}")
    def remove_connector(integration_id: str, response: Response):
        try:
            result = service.remove(store, integration_id=integration_id)
        except McpStoreError as exc:
            raise HTTPException(404, str(exc)) from None
        response.headers["Cache-Control"] = "no-store"
        return {**result, "detail": "The definition, its catalog and every assistant grant were removed."}


__all__ = ["install_mcp_routes"]
