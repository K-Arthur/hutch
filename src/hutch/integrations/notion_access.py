"""Notion grants use ADR 0017's canonical integration rows, not another permission store."""
from __future__ import annotations

import json

from ..models import iso, utcnow
from .base import canonical_tool_name
from .notion import ACCOUNT_PATTERN, NotionError, ORIGIN
from .notion_mcp import READ_TOOLS, canonical_json, revision


def _identity(account_id):
    if not ACCOUNT_PATTERN.fullmatch(account_id):
        raise NotionError("Notion account reference is invalid")
    return account_id


def _key(account_id):
    return "integration-manifest:" + _identity(account_id)


def save_discovery(store, account_id: str, discovery: dict) -> dict:
    _identity(account_id)
    tools = discovery["tools"]
    if set(tools) - READ_TOOLS:
        raise NotionError("Unsupported Notion tools cannot be authorized")
    manifest = {"account_id": account_id, "endpoint": ORIGIN + "/mcp", "tools": tools}
    digest = revision(manifest)
    with store._tx() as db:
        old = db.execute("SELECT revision,transport,credential_id FROM integrations WHERE integration_id = ?", (account_id,)).fetchone()
        if old is not None and (old["transport"] != "mcp_http" or old["credential_id"] != account_id):
            raise NotionError("This integration identity belongs to another connection")
        changed = old is not None and old["revision"] != digest
        if changed:
            db.execute("DELETE FROM integration_tool_grants WHERE integration_id = ?", (account_id,))
        db.execute("INSERT INTO integrations(integration_id,revision,title,transport,credential_id,state,enabled,created_at) "
                   "VALUES (?,?,?,'mcp_http',?,'capabilities_discovered',0,?) "
                   "ON CONFLICT(integration_id) DO UPDATE SET revision=excluded.revision, "
                   "state=CASE WHEN revision=excluded.revision AND state='operation_authorized' THEN state ELSE 'capabilities_discovered' END, "
                   "enabled=CASE WHEN revision=excluded.revision AND state='operation_authorized' THEN enabled ELSE 0 END",
                   (account_id, digest, "Notion", account_id, iso(utcnow())))
        db.execute("INSERT INTO kv(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (_key(account_id), canonical_json(manifest)))
    store.bus.notify("work", "bots")
    return {"revision": digest, "tools": tools, "grants_invalidated": changed}


def grant_tools(store, account_id, bot_ref, tool_names, expected_revision):
    _identity(account_id)
    names = sorted(set(tool_names))
    if not names or set(names) - READ_TOOLS:
        raise NotionError("Choose Notion search and/or page fetch")
    bot = store.get_bot(bot_ref)
    if bot is None:
        raise NotionError("Choose an existing assistant")
    if bot.inference_mode.value == "offline":
        raise NotionError("Strict Offline assistants cannot use Notion")
    if bot.runtime.value not in {"builtin", "opencode"}:
        raise NotionError("Notion reads require a built-in or governed OpenCode assistant")
    with store._tx() as db:
        row = db.execute("SELECT revision,state,transport,credential_id FROM integrations WHERE integration_id=?", (account_id,)).fetchone()
        raw = db.execute("SELECT value FROM kv WHERE key=?", (_key(account_id),)).fetchone()
        if row is None or raw is None or row["transport"] != "mcp_http" or row["credential_id"] != account_id or row["revision"] != expected_revision or row["state"] not in {"capabilities_discovered", "operation_authorized"}:
            raise NotionError("Notion access changed; discover and review its tools again")
        manifest = json.loads(raw["value"])
        if revision(manifest) != expected_revision or any(name not in manifest["tools"] for name in names):
            raise NotionError("Notion tool definitions do not match this review")
        db.execute("DELETE FROM integration_tool_grants WHERE integration_id=? AND bot_id=?", (account_id, bot.id))
        for name in names:
            db.execute("INSERT INTO integration_tool_grants(integration_id,bot_id,server_tool_name,canonical_name,schema_revision,granted_at) VALUES (?,?,?,?,?,?)",
                       (account_id, bot.id, name, canonical_tool_name(account_id, name), revision(manifest["tools"][name]), iso(utcnow())))
        db.execute("UPDATE integrations SET enabled=1,state='operation_authorized' WHERE integration_id=?", (account_id,))
    store.bus.notify("work", "bots")
    return {"account_id": account_id, "bot_id": bot.id, "tools": names, "revision": expected_revision}


def bindings(store, bot_ref=None) -> list[dict]:
    bot = store.get_bot(bot_ref) if bot_ref is not None else None
    if bot_ref is not None and (bot is None or bot.inference_mode.value == "offline"):
        return []
    with store._lock:
        rows = store._db.execute("SELECT g.*, i.revision, i.transport, i.credential_id, k.value FROM integration_tool_grants g "
            "JOIN integrations i USING(integration_id) JOIN kv k ON k.key='integration-manifest:'||i.integration_id "
            "WHERE i.enabled=1 AND i.state='operation_authorized' "
            + ("AND g.bot_id=? " if bot else "") + "ORDER BY g.canonical_name", (bot.id,) if bot else ()).fetchall()
        result = []
        for row in rows:
            if not ACCOUNT_PATTERN.fullmatch(row["integration_id"]) or row["server_tool_name"] not in READ_TOOLS:
                continue
            try:
                manifest = json.loads(row["value"])
                item = manifest["tools"][row["server_tool_name"]]
                if (row["transport"] != "mcp_http" or row["credential_id"] != row["integration_id"] or
                    manifest["account_id"] != row["integration_id"] or manifest["endpoint"] != ORIGIN + "/mcp" or
                    revision(manifest) != row["revision"] or revision(item) != row["schema_revision"] or
                    row["canonical_name"] != canonical_tool_name(row["integration_id"], row["server_tool_name"])):
                    continue
                result.append({"account_id": row["integration_id"], "bot_id": row["bot_id"], "name": row["server_tool_name"],
                               "canonical_name": row["canonical_name"], "schema_revision": row["schema_revision"], "item": item})
            except (ValueError, KeyError, TypeError):
                continue
        return result


def revoke(store, account_id, bot_ref=None):
    _identity(account_id)
    bot = store.get_bot(bot_ref) if bot_ref is not None else None
    if bot_ref is not None and bot is None:
        raise NotionError("Assistant is no longer available")
    with store._tx() as db:
        if bot:
            db.execute("DELETE FROM integration_tool_grants WHERE integration_id=? AND bot_id=?", (account_id, bot.id))
        else:
            db.execute("DELETE FROM integration_tool_grants WHERE integration_id=?", (account_id,))
            db.execute("UPDATE integrations SET enabled=0,state='installed' WHERE integration_id=?", (account_id,))
    store.bus.notify("work", "bots")


def bindings_for_run(store, bot, run) -> list[dict]:
    """An in-flight run cannot gain integrations that were absent at admission."""
    run_id = getattr(run, "id", None)
    if not isinstance(run_id, str) or not run_id:
        return []
    reader = getattr(store, "run_capability_snapshot", None)
    snapshot = (reader(run_id) if callable(reader) else None) or {}
    if (getattr(run, "tool_access", "none") == "none" or snapshot.get("snapshot_version") != 1 or
            snapshot.get("bot_id") != bot.id or run.bot_id != bot.id):
        return []
    captured = snapshot.get("integration_tools", [])
    if not isinstance(captured, list) or any(not isinstance(name, str) for name in captured):
        return []
    allowed = set(captured)
    return [binding for binding in bindings(store, bot.id) if binding["canonical_name"] in allowed]


def names_for_run(store, bot, run) -> set[str]:
    return {binding["canonical_name"] for binding in bindings_for_run(store, bot, run)}
