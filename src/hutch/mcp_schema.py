"""Schema v85: reviewed MCP server definitions, their discovered catalogs, and operation classes.

A top-level ``*_schema`` module for the same reason as ``personal_schema``/``bot_deletion_schema``:
the frozen ``store.py`` migration list delegates, and the store module does not grow.

Three additive objects:

* ``mcp_servers`` holds the *non-secret* reviewed definition (command/args/mounts with their
  fingerprints, or endpoint URL plus the name of an environment variable). A credential value is
  never a column here.
* ``integration_tool_catalog`` holds the normalized ``tools/list`` result. ``schema_revision`` is
  the digest a grant is approved against, so a server that changes a tool's schema invalidates the
  review instead of inheriting it.
* ``integration_tool_grants.operation_class`` records how the owner classified the tool. It
  defaults to ``unknown``, which requires approval on every call: a connector is not read-only
  because its server says so.

Existing rows keep working: the column is added with a non-null default, and the two new tables
start empty. Nothing here is enabled by the migration alone.
"""

from __future__ import annotations

import sqlite3

#: The classes an owner may assign. Anything unrecognized is treated as ``unknown`` at read time.
OPERATION_CLASSES = ("read", "write", "destructive", "unknown")


def migrate(db: sqlite3.Connection) -> None:
    """Install disabled MCP server definitions, the discovered catalog and grant classifications."""
    db.execute("""CREATE TABLE IF NOT EXISTS mcp_servers (
        integration_id TEXT PRIMARY KEY REFERENCES integrations(integration_id) ON DELETE CASCADE,
        definition_json TEXT NOT NULL CHECK(json_valid(definition_json)),
        definition_revision TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS integration_tool_catalog (
        integration_id TEXT NOT NULL REFERENCES integrations(integration_id) ON DELETE CASCADE,
        server_tool_name TEXT NOT NULL,
        canonical_name TEXT NOT NULL,
        schema_revision TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        input_schema_json TEXT NOT NULL CHECK(json_valid(input_schema_json)),
        output_schema_json TEXT CHECK(output_schema_json IS NULL OR json_valid(output_schema_json)),
        annotations_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(annotations_json)),
        supported INTEGER NOT NULL DEFAULT 1 CHECK(supported IN (0, 1)),
        diagnostics_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(diagnostics_json)),
        discovered_at TEXT NOT NULL,
        PRIMARY KEY (integration_id, server_tool_name)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_integration_tool_catalog_canonical "
               "ON integration_tool_catalog(canonical_name)")
    columns = {str(row[1]) for row in db.execute("PRAGMA table_info(integration_tool_grants)")}
    if "operation_class" not in columns:
        # Default 'unknown' means every pre-existing grant now requires approval, which is the
        # safe direction: the migration can only narrow authority, never widen it.
        db.execute("ALTER TABLE integration_tool_grants ADD COLUMN operation_class TEXT NOT NULL "
                   "DEFAULT 'unknown' CHECK(operation_class IN ('read', 'write', 'destructive', 'unknown'))")


__all__ = ["OPERATION_CLASSES", "migrate"]
