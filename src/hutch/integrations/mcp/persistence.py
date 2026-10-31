"""Persistence for reviewed MCP servers, their catalogs and per-assistant grants (ADR-0017 S2/S3).

The rules that matter here are all about *not inheriting* authority:

* saving a new definition revision drops the integration back to ``installed`` and disables it;
* refreshing a catalog deletes any grant whose tool schema changed, because the owner approved
  the old schema and not the new one;
* a grant is written only for a tool that exists in the current catalog, with the catalog's own
  schema revision baked into the row;
* removing a server removes its grants in the same transaction, so a later re-add starts with no
  authority at all (the uninstall-without-revocation failure recorded in the research ledger).

Secrets are never written: ``mcp_servers.definition_json`` holds references
(``{"from_env": "NAME"}``), which the launcher resolves at spawn time.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from ...models import iso, utcnow
from ...mcp_schema import OPERATION_CLASSES


class McpStoreError(ValueError):
    """A reviewed definition, catalog or grant cannot be persisted."""


def _now() -> str:
    return iso(utcnow())


def _rows(db: sqlite3.Connection, sql: str, params: tuple) -> list[sqlite3.Row]:
    return db.execute(sql, params).fetchall()


def save_definition(db: sqlite3.Connection, *, integration_id: str, title: str,
                    definition: dict[str, Any], revision: str) -> dict[str, Any]:
    """Record a reviewed definition. Any change returns the integration to a disabled state."""
    previous = db.execute("SELECT revision, state, enabled FROM integrations WHERE integration_id = ?",
                          (integration_id,)).fetchone()
    transport = str(definition.get("transport") or "")
    if transport not in {"mcp_stdio", "mcp_http"}:
        raise McpStoreError("an MCP definition must declare a stdio or http transport")
    now = _now()
    db.execute(
        "INSERT INTO integrations(integration_id, revision, title, transport, credential_id, state, enabled, created_at) "
        "VALUES (?,?,?,?,'','installed',0,?) "
        "ON CONFLICT(integration_id) DO UPDATE SET revision=excluded.revision, title=excluded.title, "
        "transport=excluded.transport, "
        "state=CASE WHEN integrations.revision = excluded.revision THEN integrations.state ELSE 'installed' END, "
        "enabled=CASE WHEN integrations.revision = excluded.revision THEN integrations.enabled ELSE 0 END",
        (integration_id, revision, title[:120], transport, now))
    db.execute(
        "INSERT INTO mcp_servers(integration_id, definition_json, definition_revision, created_at, updated_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(integration_id) DO UPDATE SET "
        "definition_json=excluded.definition_json, definition_revision=excluded.definition_revision, "
        "updated_at=excluded.updated_at",
        (integration_id, json.dumps(definition, sort_keys=True, separators=(",", ":")), revision, now, now))
    changed = previous is not None and previous["revision"] != revision
    if changed:
        # A definition change is a new thing to consent to: the catalog it produced is stale and
        # the grants were approved against a different program or endpoint.
        db.execute("DELETE FROM integration_tool_catalog WHERE integration_id = ?", (integration_id,))
        db.execute("DELETE FROM integration_tool_grants WHERE integration_id = ?", (integration_id,))
    return {"integration_id": integration_id, "revision": revision, "invalidated": changed}


def definition_for(db: sqlite3.Connection, integration_id: str) -> Optional[dict[str, Any]]:
    row = db.execute("SELECT d.definition_json, d.definition_revision, i.title, i.state, i.enabled, "
                     "i.transport, i.revision FROM mcp_servers d JOIN integrations i USING (integration_id) "
                     "WHERE d.integration_id = ?", (integration_id,)).fetchone()
    if row is None:
        return None
    try:
        definition = json.loads(row["definition_json"])
    except (TypeError, ValueError):
        return None
    if not isinstance(definition, dict):
        return None
    return {"definition": definition, "revision": row["definition_revision"], "title": row["title"],
            "state": row["state"], "enabled": bool(row["enabled"]),
            "transport": row["transport"], "integration_revision": row["revision"]}


def save_catalog(db: sqlite3.Connection, integration_id: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace the discovered catalog, invalidating grants for tools whose schema changed."""
    row = db.execute("SELECT revision FROM integrations WHERE integration_id = ?", (integration_id,)).fetchone()
    if row is None:
        raise McpStoreError("discover the server before saving its catalog")
    previous = {r["server_tool_name"]: r["schema_revision"] for r in _rows(
        db, "SELECT server_tool_name, schema_revision FROM integration_tool_catalog WHERE integration_id = ?",
        (integration_id,))}
    now = _now()
    invalidated: list[str] = []
    db.execute("DELETE FROM integration_tool_catalog WHERE integration_id = ?", (integration_id,))
    for tool in tools:
        db.execute(
            "INSERT INTO integration_tool_catalog(integration_id, server_tool_name, canonical_name, "
            "schema_revision, title, description, input_schema_json, output_schema_json, annotations_json, "
            "supported, diagnostics_json, discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (integration_id, tool["server_tool_name"], tool["canonical_name"], tool["schema_revision"],
             tool.get("title", ""), tool.get("description", ""),
             json.dumps(tool.get("input_schema") or {}, sort_keys=True, separators=(",", ":")),
             json.dumps(tool["output_schema"], sort_keys=True, separators=(",", ":")) if tool.get("output_schema") is not None else None,
             json.dumps(tool.get("annotations") or {}, sort_keys=True, separators=(",", ":")),
             1 if tool.get("supported", True) else 0,
             json.dumps(tool.get("diagnostics") or []), now))
    for name, revision in previous.items():
        current = next((t for t in tools if t["server_tool_name"] == name), None)
        if current is None or current["schema_revision"] != revision:
            invalidated.append(name)
    for name in invalidated:
        db.execute("DELETE FROM integration_tool_grants WHERE integration_id = ? AND server_tool_name = ?",
                   (integration_id, name))
    # A usable catalog with at least one supported tool means capabilities were discovered.
    supported = any(t.get("supported", True) for t in tools)
    db.execute(
        "UPDATE integrations SET state = CASE WHEN state = 'operation_authorized' THEN state "
        "ELSE ? END WHERE integration_id = ?",
        ("capabilities_discovered" if supported else "installed", integration_id))
    return {"tools": len(tools), "invalidated": invalidated}


def catalog_for(db: sqlite3.Connection, integration_id: str) -> list[dict[str, Any]]:
    rows = _rows(db, "SELECT * FROM integration_tool_catalog WHERE integration_id = ? "
                     "ORDER BY server_tool_name", (integration_id,))
    out = []
    for row in rows:
        out.append({
            "server_tool_name": row["server_tool_name"], "canonical_name": row["canonical_name"],
            "schema_revision": row["schema_revision"], "title": row["title"],
            "description": row["description"],
            "input_schema": json.loads(row["input_schema_json"]),
            "output_schema": json.loads(row["output_schema_json"]) if row["output_schema_json"] else None,
            "annotations": json.loads(row["annotations_json"]),
            "supported": bool(row["supported"]),
            "diagnostics": json.loads(row["diagnostics_json"]),
        })
    return out


def grant_row(db: sqlite3.Connection, bot_id: str, integration_id: str,
              server_tool_name: str) -> Optional[dict[str, Any]]:
    row = db.execute(
        "SELECT g.schema_revision, g.operation_class, g.canonical_name, i.title, i.revision "
        "FROM integration_tool_grants g JOIN integrations i USING (integration_id) "
        "WHERE g.bot_id = ? AND g.integration_id = ? AND g.server_tool_name = ? "
        "AND i.enabled = 1 AND i.state = 'operation_authorized'",
        (bot_id, integration_id, server_tool_name)).fetchone()
    if row is None:
        return None
    return {"schema_revision": row["schema_revision"], "operation_class": row["operation_class"],
            "canonical_name": row["canonical_name"], "account_label": row["title"],
            "integration_revision": row["revision"]}


def grant_tools(db: sqlite3.Connection, *, integration_id: str, bot_id: str, tool_names: list[str],
                operation_classes: dict[str, str], expected_revision: str) -> dict[str, Any]:
    """Grant reviewed tools to one assistant, binding each to the catalog's schema revision."""
    row = db.execute("SELECT revision, state, enabled FROM integrations WHERE integration_id = ?",
                     (integration_id,)).fetchone()
    if row is None or row["revision"] != expected_revision:
        raise McpStoreError("this connector changed; discover and review its tools again")
    catalog = {tool["server_tool_name"]: tool for tool in catalog_for(db, integration_id)}
    names = sorted(set(tool_names))
    if not names:
        raise McpStoreError("choose at least one tool to grant")
    unknown = [name for name in names if name not in catalog]
    if unknown:
        raise McpStoreError("these tools are not in the reviewed catalog: " + ", ".join(unknown[:8]))
    unsupported = [name for name in names if not catalog[name]["supported"]]
    if unsupported:
        raise McpStoreError("these tools cannot be executed safely as described: " + ", ".join(unsupported[:8]))
    for name, klass in operation_classes.items():
        if name in names and klass not in OPERATION_CLASSES:
            raise McpStoreError(f"unrecognized operation class for {name}")
    now = _now()
    db.execute("DELETE FROM integration_tool_grants WHERE integration_id = ? AND bot_id = ?",
               (integration_id, bot_id))
    for name in names:
        klass = operation_classes.get(name, "unknown")
        db.execute(
            "INSERT INTO integration_tool_grants(integration_id, bot_id, server_tool_name, canonical_name, "
            "schema_revision, operation_class, granted_at) VALUES (?,?,?,?,?,?,?)",
            (integration_id, bot_id, name, catalog[name]["canonical_name"],
             catalog[name]["schema_revision"], klass, now))
    db.execute("UPDATE integrations SET enabled = 1, state = 'operation_authorized' "
               "WHERE integration_id = ?", (integration_id,))
    return {"integration_id": integration_id, "bot_id": bot_id, "tools": names}


def revoke_tools(db: sqlite3.Connection, *, integration_id: str, bot_id: str) -> dict[str, Any]:
    """Withdraw one assistant's access; the connector stays available to assistants that still have grants."""
    db.execute("DELETE FROM integration_tool_grants WHERE integration_id = ? AND bot_id = ?",
               (integration_id, bot_id))
    remaining = db.execute("SELECT COUNT(*) AS n FROM integration_tool_grants WHERE integration_id = ?",
                           (integration_id,)).fetchone()["n"]
    if not remaining:
        db.execute("UPDATE integrations SET enabled = 0, state = 'capabilities_discovered' "
                   "WHERE integration_id = ?", (integration_id,))
    return {"integration_id": integration_id, "bot_id": bot_id, "remaining_grants": remaining}


def delete_server(db: sqlite3.Connection, integration_id: str) -> None:
    """Remove a server and every authority derived from it. Re-adding starts signed out."""
    db.execute("DELETE FROM integration_tool_grants WHERE integration_id = ?", (integration_id,))
    db.execute("DELETE FROM integration_tool_catalog WHERE integration_id = ?", (integration_id,))
    db.execute("DELETE FROM mcp_servers WHERE integration_id = ?", (integration_id,))
    db.execute("DELETE FROM integrations WHERE integration_id = ?", (integration_id,))


def tools_for_bot(db: sqlite3.Connection, bot_id: str) -> list[dict[str, Any]]:
    """Joined grant+catalog+definition rows the tool adapter needs, in canonical-name order."""
    rows = _rows(db,
                 "SELECT g.integration_id, g.server_tool_name, g.canonical_name, g.schema_revision, "
                 "g.operation_class, c.title, c.description, c.input_schema_json, s.definition_json, i.title AS label "
                 "FROM integration_tool_grants g "
                 "JOIN integrations i USING (integration_id) "
                 "JOIN integration_tool_catalog c USING (integration_id, server_tool_name) "
                 "JOIN mcp_servers s USING (integration_id) "
                 "WHERE g.bot_id = ? AND i.enabled = 1 AND i.state = 'operation_authorized' "
                 "ORDER BY g.canonical_name", (bot_id,))
    out = []
    for row in rows:
        try:
            definition = json.loads(row["definition_json"])
            schema = json.loads(row["input_schema_json"])
        except (TypeError, ValueError):
            continue
        # A catalog refresh already deleted grants whose schema changed (save_catalog), so the
        # join itself proves the grant is against the current catalog entry.
        out.append({"integration_id": row["integration_id"], "server_tool_name": row["server_tool_name"],
                    "canonical_name": row["canonical_name"], "schema_revision": row["schema_revision"],
                    "operation_class": row["operation_class"], "title": row["title"] or row["server_tool_name"],
                    "description": row["description"], "input_schema": schema,
                    "definition": definition, "account_label": row["label"]})
    return out


def servers(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every configured server with its grant count, for the connectors list."""
    rows = _rows(db, "SELECT i.integration_id, i.title, i.transport, i.state, i.enabled, i.revision, "
                     "s.definition_revision, "
                     "(SELECT COUNT(*) FROM integration_tool_catalog c WHERE c.integration_id = i.integration_id) AS tool_count, "
                     "(SELECT COUNT(*) FROM integration_tool_grants g WHERE g.integration_id = i.integration_id) AS grant_count "
                     "FROM integrations i JOIN mcp_servers s USING (integration_id) ORDER BY i.title, i.integration_id", ())
    return [{"integration_id": r["integration_id"], "title": r["title"], "transport": r["transport"],
             "state": r["state"], "enabled": bool(r["enabled"]), "revision": r["revision"],
             "tool_count": r["tool_count"], "grant_count": r["grant_count"]} for r in rows]


__all__ = ["McpStoreError", "catalog_for", "definition_for", "delete_server", "grant_row",
           "grant_tools", "revoke_tools", "save_catalog", "save_definition", "servers", "tools_for_bot"]
