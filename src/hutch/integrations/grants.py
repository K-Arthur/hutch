"""Grant reads at the execution boundary (ADR-0017 S1/S3).

The integration tables live in ``store.py``'s migration list, but the queries that decide
*whether a Bot may use a tool right now* live here. ``store.Store`` delegates to these
functions so the frozen store module does not grow, and so configuration
(``integration_tool_names``, which shapes a run's tool set and the capability snapshot) and
enforcement (``integration_tool_granted``, read before every dispatch) cannot drift: both use
the same enabled-and-operation-authorized join.
"""

from __future__ import annotations

import sqlite3

#: A grant counts only for an integration that is both enabled and operation-authorized.
#: A discovered-tool row on a disabled integration is review material, not authority.
_GRANT_JOIN = ("FROM integration_tool_grants g JOIN integrations i USING (integration_id) "
               "WHERE g.bot_id = ? AND i.enabled = 1 AND i.state = 'operation_authorized'")


def integration_tool_names(db: sqlite3.Connection, bot_id: str) -> list[str]:
    """Return sorted canonical names for grants on enabled, operation-authorized integrations."""
    rows = db.execute(f"SELECT g.canonical_name {_GRANT_JOIN} ORDER BY g.canonical_name",
                      (bot_id,)).fetchall()
    return [str(row["canonical_name"]) for row in rows]


def integration_tool_granted(db: sqlite3.Connection, bot_id: str, integration_id: str,
                             server_tool_name: str) -> bool:
    """Whether one tool is still granted, enabled and operation-authorized for this Bot.

    This is the execution-boundary read (``runtime.dispatch.dispatch_refusal``). It is never
    cached, because a revocation that only takes effect on the next run is not a revocation.
    """
    row = db.execute(f"SELECT 1 {_GRANT_JOIN} AND g.integration_id = ? AND g.server_tool_name = ?",
                     (bot_id, integration_id, server_tool_name)).fetchone()
    return row is not None


__all__ = ["integration_tool_granted", "integration_tool_names"]
