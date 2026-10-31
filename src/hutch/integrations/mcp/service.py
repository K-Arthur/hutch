"""The operations behind connector configuration, testing, discovery and grants (ADR-0017 S2/S3).

Each function does one thing and is callable outside a run, so the HTTP layer stays a thin
adapter. Nothing here decides authority: it records what the owner reviewed and returns the
evidence (tool count, schema revisions, diagnostics) the interface shows.

Discovery is the step that turns "installed" into "capabilities discovered". It runs the server
once, reads its bounded catalog, and stores it. It deliberately executes no tool: a test that
called tools would be an unapproved side effect performed by a button labelled "test"
(research §7.2).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional

from ...models import iso, utcnow
from .config import (McpConfigurationError, definition_revision, validate_http_definition,
                     validate_stdio_definition)
from .discovery import McpToolSchemaError, normalize_mcp_tools
from .persistence import (McpStoreError, catalog_for, definition_for, delete_server, grant_row,
                          grant_tools, revoke_tools, save_catalog, save_definition, servers,
                          tools_for_bot)
from .transport import DISCOVERY_DEADLINE_SECONDS, open_client

#: Discovery never runs tools; it only lists them, so its workspace stays empty and disposable.
def _scratch_workspace(state_dir: str | Path) -> Path:
    root = Path(state_dir) / "mcp-scratch"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return Path(tempfile.mkdtemp(prefix="discover-", dir=root))


def configure(store, *, integration_id: str, title: str, raw_definition: dict[str, Any]) -> dict[str, Any]:
    """Validate and save a reviewed definition. Saving does not enable or authorize anything."""
    existing = definition_for(store._db, integration_id)
    expected = None
    if existing is not None:
        expected = {k: existing["definition"].get(k) for k in ("command_sha256", "read_only_fingerprints")}
        if existing["definition"].get("transport") != (raw_definition or {}).get("transport"):
            expected = None
    transport = (raw_definition or {}).get("transport")
    if transport == "mcp_stdio":
        normalized = validate_stdio_definition(raw_definition, expected=expected)
    elif transport == "mcp_http":
        normalized = validate_http_definition(raw_definition)
    else:
        raise McpConfigurationError("an MCP definition must declare a stdio or http transport")
    revision = definition_revision(normalized)
    with store._tx() as db:
        result = save_definition(db, integration_id=integration_id, title=title,
                                 definition=normalized, revision=revision)
    store.bus.notify("work", "bots")
    return {**result, "definition": normalized}


def discover(store, *, integration_id: str, workspace: Optional[Path] = None) -> dict[str, Any]:
    """Read the server's bounded tool catalog. Never runs a tool and never grants anything."""
    record = definition_for(store._db, integration_id)
    if record is None:
        raise McpStoreError("configure the connector before testing it")
    scratch = workspace or _scratch_workspace(store.config.state_dir)
    tools = _list_tools_sync(record["definition"], scratch)
    normalized = normalize_mcp_tools(integration_id, tools)
    with store._tx() as db:
        result = save_catalog(db, integration_id, normalized)
    store.bus.notify("work", "bots")
    return {**result, "catalog": catalog_for(store._db, integration_id)}


def _describe_failure(error: BaseException) -> str:
    """A bounded, secret-free sentence for a transport or protocol failure.

    Protocol and HTTP exceptions can carry server response bodies and request headers, so none of
    their text is forwarded. What matters to the owner is which stage failed, because the fix
    differs: a wrong URL, an endpoint that is not an MCP server, or one that never answered.
    """
    kinds: list[str] = []

    def walk(item: BaseException, depth: int = 0) -> None:
        if depth > 8:
            return
        kinds.append(type(item).__name__)
        if isinstance(item, BaseExceptionGroup):
            for child in item.exceptions:
                walk(child, depth + 1)

    walk(error)
    if "TimeoutError" in kinds:
        return (f"the connector did not answer within {DISCOVERY_DEADLINE_SECONDS} seconds; "
                "check that the endpoint is reachable and is an MCP server")
    if any("MCPError" in kind or "McpError" in kind for kind in kinds):
        return ("the endpoint answered, but not as an MCP server; check the URL path and whether "
                "it needs authentication")
    if any("TransportError" in kind or "ConnectError" in kind for kind in kinds):
        return "the connector could not be reached; check the URL, the certificate and the network"
    return "the connector did not complete MCP discovery; check the definition and try again"


def _list_tools_sync(definition: dict[str, Any], workspace: Path) -> list[Any]:
    import anyio

    async def run() -> list[Any]:
        discovered: list[Any] = []
        with anyio.fail_after(DISCOVERY_DEADLINE_SECONDS):
            async with open_client(definition, workspace) as client:
                cursor = None
                for _page in range(20):
                    page = await client.list_tools(cursor=cursor, cache_mode="refresh")
                    discovered.extend(page.tools)
                    if len(discovered) > 200:
                        raise McpToolSchemaError("the server advertises more than 200 tools")
                    cursor = page.next_cursor
                    if not cursor:
                        return discovered
                raise McpToolSchemaError("tool discovery exceeded Hutch's pagination limit")

    try:
        return anyio.run(run)
    except (McpToolSchemaError, McpConfigurationError, McpStoreError):
        raise
    except BaseException as error:  # noqa: BLE001 - SDK and HTTP failures are one class here
        # A wrong URL must read as "this is not an MCP endpoint", not as a 500 and not as an
        # empty tool list. The SDK's exception text is discarded on purpose.
        raise McpConfigurationError(_describe_failure(error)) from None


def grant(store, *, integration_id: str, bot_ref: str, tool_names: list[str],
          operation_classes: dict[str, str], expected_revision: str) -> dict[str, Any]:
    """Grant reviewed tools to one assistant. New grants are explicit; nothing defaults on."""
    bot = store.get_bot(bot_ref)
    if bot is None:
        raise McpStoreError("choose an existing assistant")
    if getattr(getattr(bot, "inference_mode", None), "value", "") == "offline":
        raise McpStoreError("Strict Offline assistants cannot use external connectors")
    with store._tx() as db:
        result = grant_tools(db, integration_id=integration_id, bot_id=bot.id, tool_names=tool_names,
                             operation_classes=operation_classes, expected_revision=expected_revision)
    store.bus.notify("work", "bots")
    return result


def revoke(store, *, integration_id: str, bot_ref: str) -> dict[str, Any]:
    """Withdraw one assistant's access to a connector."""
    bot = store.get_bot(bot_ref)
    if bot is None:
        raise McpStoreError("choose an existing assistant")
    with store._tx() as db:
        result = revoke_tools(db, integration_id=integration_id, bot_id=bot.id)
    store.bus.notify("work", "bots")
    return result


def remove(store, *, integration_id: str) -> dict[str, Any]:
    """Remove a server: its definition, catalog and every grant derived from it."""
    record = definition_for(store._db, integration_id)
    if record is None:
        raise McpStoreError("that connector is not configured")
    with store._tx() as db:
        delete_server(db, integration_id)
    store.bus.notify("work", "bots")
    return {"integration_id": integration_id, "removed": True}


def overview(store) -> list[dict[str, Any]]:
    return servers(store._db)


def detail(store, integration_id: str) -> dict[str, Any]:
    record = definition_for(store._db, integration_id)
    if record is None:
        raise McpStoreError("that connector is not configured")
    catalog = catalog_for(store._db, integration_id)
    grants = store._db.execute(
        "SELECT g.bot_id, g.server_tool_name, g.canonical_name, g.operation_class, g.schema_revision, "
        "b.name AS bot_name FROM integration_tool_grants g JOIN bots b ON b.id = g.bot_id "
        "WHERE g.integration_id = ? ORDER BY b.name, g.server_tool_name", (integration_id,)).fetchall()
    return {
        "integration_id": integration_id, "title": record["title"], "state": record["state"],
        "enabled": record["enabled"], "transport": record["transport"], "revision": record["revision"],
        "definition": _public_definition(record["definition"]),
        "catalog": catalog,
        "grants": [{"bot_id": r["bot_id"], "bot_name": r["bot_name"],
                    "server_tool_name": r["server_tool_name"], "canonical_name": r["canonical_name"],
                    "operation_class": r["operation_class"]} for r in grants],
    }


def _public_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """The definition as the interface may show it: no resolved secret ever appears here."""
    shown = dict(definition)
    shown.pop("command_sha256", None)
    shown.pop("read_only_fingerprints", None)
    return shown


def construct_tools(store, bot, run=None) -> dict[str, Any]:
    """The ``build_tools`` hook: this Bot's reviewed MCP tools, or nothing."""
    from .tool import construct_mcp_tools
    return construct_mcp_tools(store, bot, run)


def grant_for(store, bot_id: str, integration_id: str, server_tool_name: str) -> Optional[dict[str, Any]]:
    """One reviewd grant row, read under the store lock (the integrations package's access pattern)."""
    with store._lock:
        return grant_row(store._db, bot_id, integration_id, server_tool_name)


def tools_for(store, bot_id: str) -> list[dict[str, Any]]:
    with store._lock:
        return tools_for_bot(store._db, bot_id)


__all__ = ["configure", "construct_tools", "detail", "discover", "grant", "grant_for", "overview",
           "remove", "revoke", "tools_for"]
