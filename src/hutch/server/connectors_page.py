"""The Connectors page: install, review, grant and revoke (ADR-0017 S2/S3).

Kept out of ``pages.py``, which is frozen near its size cap, by exporting one installer that
receives the page factory's own helpers. Server-rendered forms with CSRF are used throughout, so
every action works without JavaScript and the page states exactly what it did.

The page is an administration surface for code that runs on this machine, so it is
local-owner-only: these routes are absent from ``REMOTE_ROUTE_CAPABILITIES`` and a paired phone
receives 403 from the inventory check.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from ..integrations.mcp import service
from ..integrations.mcp.config import McpConfigurationError
from ..integrations.mcp.discovery import McpToolSchemaError
from ..integrations.mcp.network import McpEndpointError
from ..integrations.mcp.persistence import McpStoreError


def _lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _environment(value: str) -> dict[str, Any]:
    """``NAME=value`` or ``NAME=@SOURCE`` per line; ``@`` means 'read this variable at start'."""
    out: dict[str, Any] = {}
    for line in _lines(value):
        name, _, raw = line.partition("=")
        name = name.strip()
        if not name:
            raise McpConfigurationError("an environment line must be NAME=value")
        if raw.startswith("@"):
            out[name] = {"from_env": raw[1:].strip()}
        else:
            out[name] = raw
    return out


def _definition_from(form) -> dict[str, Any]:
    if form.get("transport") == "mcp_http":
        definition: dict[str, Any] = {"transport": "mcp_http", "url": (form.get("url") or "").strip()}
        bearer = (form.get("bearer_env") or "").strip()
        definition["auth"] = {"type": "bearer", "from_env": bearer} if bearer else {"type": "none"}
        return definition
    return {"transport": "mcp_stdio", "command": (form.get("command") or "").strip(),
            "args": _lines(form.get("args")), "read_only_paths": _lines(form.get("read_only_paths")),
            "env": _environment(form.get("env"))}


def _view(store, *, opened: str = "") -> dict[str, Any]:
    """One assembled view model; every value comes from persisted rows, never from a request."""
    bots = [{"id": bot.id, "label": bot.display_name or bot.name} for bot in store.list_bots()]
    connectors = []
    for row in service.overview(store):
        detail = service.detail(store, row["integration_id"])
        granted = {(g["bot_id"], g["server_tool_name"]): g for g in detail["grants"]}
        catalog = []
        for tool in detail["catalog"]:
            existing = next((g for (bot_id, name), g in granted.items()
                             if name == tool["server_tool_name"]), None)
            catalog.append({**tool, "granted": existing is not None,
                            "operation_class": (existing or {}).get("operation_class", "unknown")})
        connectors.append({
            "integration_id": row["integration_id"], "title": row["title"] or row["integration_id"],
            "transport": row["transport"], "state": row["state"], "enabled": row["enabled"],
            "revision": row["revision"], "tool_count": row["tool_count"],
            "grant_count": row["grant_count"], "catalog": catalog, "grants": detail["grants"],
            "diagnostics": [f"{t['server_tool_name']}: {d}" for t in detail["catalog"]
                            for d in t.get("diagnostics") or []],
            "open": row["integration_id"] == opened,
        })
    # notice/error come from the page factory's flash cookie; returning them here would
    # shadow it with an empty string and silently swallow every confirmation.
    return {"connectors": connectors, "bots": bots}


def install_connectors_page(app, store, *, page: Callable, go: Callable, read_form: Callable) -> None:
    @app.get("/connectors", response_class=HTMLResponse, include_in_schema=False)
    def connectors_page(request: Request):
        return page(request, "connectors.html", nav="connectors", **_view(store))

    @app.post("/connectors/add", include_in_schema=False)
    async def add_connector(request: Request):
        form = await read_form(request)
        try:
            await run_in_threadpool(
                service.configure, store, integration_id=(form.get("integration_id") or "").strip(),
                title=(form.get("title") or "").strip(), raw_definition=_definition_from(form))
        except (McpConfigurationError, McpEndpointError, McpStoreError) as exc:
            return go("/connectors", error=str(exc))
        return go("/connectors", notice="Connector saved. It starts nothing and authorizes nothing until you read its tool list and grant access.")

    @app.post("/connectors/{integration_id}/test", include_in_schema=False)
    async def test_connector(request: Request, integration_id: str):
        await read_form(request)
        try:
            result = await run_in_threadpool(service.discover, store, integration_id=integration_id)
        except (McpConfigurationError, McpEndpointError, McpStoreError, McpToolSchemaError) as exc:
            return go("/connectors", error=str(exc))
        return go("/connectors", notice=(f"Read {result['tools']} tool"
                                         f"{'' if result['tools'] == 1 else 's'}. No tool was called."))

    @app.post("/connectors/{integration_id}/grant", include_in_schema=False)
    async def grant_connector(request: Request, integration_id: str):
        form = await read_form(request)
        bot = (form.get("bot") or "").strip()
        tools = form.getlist("tools") if hasattr(form, "getlist") else []
        if not bot or not tools:
            return go("/connectors", error="Choose an assistant and at least one tool to grant.")
        classes = {name: (form.get(f"class_{name}") or "unknown") for name in tools}
        try:
            await run_in_threadpool(
                service.grant, store, integration_id=integration_id, bot_ref=bot, tool_names=tools,
                operation_classes=classes, expected_revision=(form.get("revision") or "").strip())
        except McpStoreError as exc:
            return go("/connectors", error=str(exc))
        return go("/connectors", notice="Access granted. It applies from this assistant's next tool call.")

    @app.post("/connectors/{integration_id}/revoke", include_in_schema=False)
    async def revoke_connector(request: Request, integration_id: str):
        form = await read_form(request)
        try:
            await run_in_threadpool(service.revoke, store, integration_id=integration_id,
                                    bot_ref=(form.get("bot") or "").strip())
        except McpStoreError as exc:
            return go("/connectors", error=str(exc))
        return go("/connectors", notice="Access revoked. The next tool call from that assistant is refused.")

    @app.post("/connectors/{integration_id}/remove", include_in_schema=False)
    async def remove_connector(request: Request, integration_id: str):
        await read_form(request)
        try:
            await run_in_threadpool(service.remove, store, integration_id=integration_id)
        except McpStoreError as exc:
            return go("/connectors", error=str(exc))
        return go("/connectors", notice="Connector removed, including every assistant grant derived from it.")


__all__ = ["install_connectors_page"]
