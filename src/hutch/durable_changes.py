"""Transactional, content-free resource invalidations for reconnecting clients.

Run transcript events retain their own API/cursors. These rows identify changed
resources so a client can fetch authoritative state without copying messages,
action arguments, fact values, credentials or device tokens into another log.
"""
from __future__ import annotations

import json
import sqlite3
import uuid

MAX_RETAINED_ROWS = 50_000

# Identifiers below are schema constants, never caller-provided SQL. Columns
# are checked explicitly: SQLite silently accepts unknown UPDATE OF columns.
# table, resource, identifier, material update columns, contextual identifiers
_RESOURCES = (
    ("bots", "bots", "id", ("doc",), ()),
    ("conversations", "conversations", "id", ("title", "archived", "updated_at"), ("bot_id",)),
    ("messages", "messages", "id", (), ("conversation_id", "run_id")),
    ("runs", "runs", "id", ("status", "doc", "cancel_requested", "fence"), ("bot_id", "conversation_id")),
    ("tasks", "tasks", "id", ("state", "done", "prompt"), ("bot_id", "run_id")),
    ("approvals", "approvals", "id", ("status", "doc"), ("run_id", "bot_id")),
    ("tool_actions", "actions", "id", ("status", "result_digest"), ("run_id",)),
    ("usage", "usage", "id", (), ("run_id", "bot_id")),
    ("usage_reservations", "usage_reservations", "id", ("status",), ("run_id", "bot_id")),
    ("memory", "memory", "bot_id", ("value", "source"), ()),
    ("tool_allows", "permissions", "bot_id", (), ()),
    # Routine session touches/heartbeat renewals must not cause refresh loops.
    ("device_sessions", "devices", "id", ("label", "revoked_at"), ()),
)


def migrate(db: sqlite3.Connection) -> None:
    """Install outbox writes in the same transaction as every observed mutation."""
    db.execute("""CREATE TABLE resource_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, previous_id INTEGER NOT NULL,
        resource TEXT NOT NULL, resource_id TEXT NOT NULL,
        operation TEXT NOT NULL CHECK(operation IN ('created','updated','deleted')),
        ts TEXT NOT NULL, context TEXT NOT NULL CHECK(json_valid(context)))""")
    db.execute("CREATE TABLE resource_outbox_meta (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
               "epoch TEXT NOT NULL, tail_id INTEGER NOT NULL DEFAULT 0)")
    db.execute("INSERT INTO resource_outbox_meta(singleton, epoch) VALUES (1, ?)", (uuid.uuid4().hex,))
    install_resources(db, _RESOURCES)


def install_resources(db: sqlite3.Connection, resources) -> None:
    """Install checked trigger definitions for resources added by later migrations."""
    for table, resource, identifier, material, context in resources:
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        required = {identifier, *material, *context}
        if not required <= columns:
            raise RuntimeError(f"outbox schema mismatch for {table}: missing {sorted(required - columns)}")
        for verb, operation, prefix in (("INSERT", "created", "NEW"), ("UPDATE", "updated", "NEW"),
                                        ("DELETE", "deleted", "OLD")):
            if verb == "UPDATE" and not material:
                continue
            when = ""
            if verb == "UPDATE":
                when = "WHEN " + " OR ".join(f"OLD.{column} IS NOT NEW.{column}" for column in material)
            payload = "json_object(" + ", ".join(f"'{column}', {prefix}.{column}" for column in context) + ")"
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS resource_outbox_{table}_{verb.lower()}
                AFTER {verb} ON {table} {when} BEGIN
                INSERT INTO resource_outbox(previous_id, resource, resource_id, operation, ts, context)
                SELECT tail_id, '{resource}', CAST({prefix}.{identifier} AS TEXT), '{operation}',
                       strftime('%Y-%m-%dT%H:%M:%fZ','now'), {payload}
                FROM resource_outbox_meta WHERE singleton = 1;
                UPDATE resource_outbox_meta SET tail_id = last_insert_rowid() WHERE singleton = 1;
                END""")


def bounds(db: sqlite3.Connection) -> tuple[str, int]:
    row = db.execute("SELECT epoch, tail_id FROM resource_outbox_meta WHERE singleton = 1").fetchone()
    return str(row[0]), int(row[1])


def prune(db: sqlite3.Connection, keep: int = MAX_RETAINED_ROWS) -> int:
    """Remove only old invalidation rows, preserving the cursor boundary and high-water mark.

    ``db`` must be inside the caller's write transaction. The first retained row
    keeps its original ``previous_id`` so clients exactly at that boundary may
    continue; older cursors detect the gap and must fetch a snapshot.
    """
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 1:
        raise ValueError("resource-change retention must keep at least one row")
    count = int(db.execute("SELECT COUNT(*) FROM resource_outbox").fetchone()[0])
    if count <= keep:
        return 0
    first_retained = db.execute(
        "SELECT id FROM resource_outbox ORDER BY id DESC LIMIT 1 OFFSET ?", (keep - 1,)
    ).fetchone()
    if first_retained is None:
        return 0
    result = db.execute("DELETE FROM resource_outbox WHERE id < ?", (int(first_retained[0]),))
    return max(0, int(result.rowcount))


class SnapshotRequired(ValueError):
    """The supplied cursor cannot describe a complete replay of retained changes."""


def read(db: sqlite3.Connection, cursor: str | None = None, limit: int = 200) -> dict:
    """Read an ordered page in the caller's consistent read transaction.

    Link to the previous *committed* row, not id-1: AUTOINCREMENT allows gaps.
    The separate tail survives complete retention removal and never invents an
    empty new stream after old changes were deleted.
    """
    epoch, tail = bounds(db)
    after = 0
    if cursor:
        parts = cursor.split(":")
        if (len(cursor) > 64 or len(parts) != 2 or parts[0] != epoch
                or not parts[1].isascii() or not parts[1].isdigit()):
            raise SnapshotRequired("resource cursor belongs to another history or is malformed")
        after = int(parts[1])
    if after > tail:
        raise SnapshotRequired("resource cursor is ahead of the database")
    rows = db.execute("SELECT id, previous_id, resource, resource_id, operation, ts, context "
                      "FROM resource_outbox WHERE id > ? ORDER BY id LIMIT ?",
                      (after, max(1, min(int(limit), 500)))).fetchall()
    changes = []
    for row in rows:
        if int(row[1]) != after:
            raise SnapshotRequired("resource changes were removed; reconcile a snapshot")
        after = int(row[0])
        changes.append({"id": after, "resource": row[2], "resource_id": row[3], "operation": row[4],
                        "ts": row[5], "context": json.loads(row[6])})
    if not rows and after < tail:
        raise SnapshotRequired("resource changes were removed; reconcile a snapshot")
    return {"changes": changes, "cursor": f"{epoch}:{after}", "high_water": f"{epoch}:{tail}",
            "has_more": after < tail}
