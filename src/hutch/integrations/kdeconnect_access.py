"""Explicit per-device/per-assistant status grants in the canonical integration store."""
import hashlib
import json

from .base import canonical_tool_name
from .kdeconnect import KDEConnectError, validate_device
from ..models import iso, utcnow


TOOL = "device-status"
SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _manifest(device_id):
    return {"device_id": validate_device(device_id), "capability": "status-battery-read-v1", "parameters": SCHEMA}


def identity(device_id):
    return "kdeconnect_" + hashlib.sha256(validate_device(device_id).encode()).hexdigest()[:24]


def grant(store, device_id, label, bot_ref):
    bot = store.get_bot(bot_ref)
    if bot is None or bot.inference_mode.value == "offline" or bot.runtime.value not in {"builtin", "opencode"}:
        raise KDEConnectError("Choose a built-in or governed OpenCode assistant outside Strict Offline mode")
    manifest = _manifest(device_id)
    integration_id = identity(device_id)
    revision = _digest(manifest)
    with store._tx() as db:
        old = db.execute("SELECT transport,credential_id,revision FROM integrations WHERE integration_id=?", (integration_id,)).fetchone()
        if old and (old["transport"] != "in_process" or old["credential_id"]):
            raise KDEConnectError("Device identity belongs to another integration")
        if old and old["revision"] != revision:
            db.execute("DELETE FROM integration_tool_grants WHERE integration_id=?", (integration_id,))
        db.execute("INSERT INTO integrations(integration_id,revision,title,transport,credential_id,state,enabled,created_at) "
                   "VALUES (?,?,?,'in_process','','operation_authorized',1,?) ON CONFLICT(integration_id) "
                   "DO UPDATE SET revision=excluded.revision,title=excluded.title,state='operation_authorized',enabled=1",
                   (integration_id, revision, str(label)[:160], iso(utcnow())))
        db.execute("INSERT INTO kv(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   ("integration-manifest:" + integration_id, json.dumps(manifest)))
        db.execute("INSERT INTO integration_tool_grants(integration_id,bot_id,server_tool_name,canonical_name,schema_revision,granted_at) "
                   "VALUES (?,?,?,?,?,?) ON CONFLICT(integration_id,bot_id,server_tool_name) DO UPDATE SET "
                   "schema_revision=excluded.schema_revision,granted_at=excluded.granted_at",
                   (integration_id, bot.id, TOOL, canonical_tool_name(integration_id, TOOL), _digest(SCHEMA), iso(utcnow())))
    store.bus.notify("work", "bots")
    return {"integration_id": integration_id, "bot_id": bot.id, "read_only": True}


def bindings(store, bot_ref=None):
    bot = store.get_bot(bot_ref) if bot_ref is not None else None
    if bot_ref is not None and (bot is None or bot.inference_mode.value == "offline" or bot.runtime.value not in {"builtin", "opencode"}):
        return []
    with store._lock:
        rows = store._db.execute("SELECT g.*,i.revision,i.title,i.transport,i.credential_id,k.value FROM integration_tool_grants g "
            "JOIN integrations i USING(integration_id) JOIN kv k ON k.key='integration-manifest:'||i.integration_id "
            "WHERE i.enabled=1 AND i.state='operation_authorized' AND i.integration_id GLOB 'kdeconnect_*' "
            + ("AND g.bot_id=? " if bot else "") + "ORDER BY g.canonical_name", (bot.id,) if bot else ()).fetchall()
    result = []
    for row in rows:
        try:
            manifest = json.loads(row["value"])
            device_id = manifest["device_id"]
            if (manifest != _manifest(device_id) or row["integration_id"] != identity(device_id) or
                    row["transport"] != "in_process" or row["credential_id"] or row["server_tool_name"] != TOOL or
                    row["schema_revision"] != _digest(SCHEMA) or row["revision"] != _digest(manifest) or
                    row["canonical_name"] != canonical_tool_name(row["integration_id"], TOOL)):
                continue
            result.append({"device_id": device_id, "label": row["title"], "integration_id": row["integration_id"],
                           "bot_id": row["bot_id"], "canonical_name": row["canonical_name"], "revision": row["revision"]})
        except (ValueError, KeyError, TypeError):
            continue
    return result


def bindings_for_run(store, bot, run):
    run_id = getattr(run, "id", None)
    reader = getattr(store, "run_capability_snapshot", None)
    if not isinstance(run_id, str) or not run_id or not callable(reader):
        return []
    snapshot = reader(run_id) or {}
    captured = snapshot.get("integration_tools", [])
    if (getattr(run, "tool_access", "none") == "none" or snapshot.get("snapshot_version") != 1 or
            snapshot.get("bot_id") != bot.id or run.bot_id != bot.id or not isinstance(captured, list) or
            any(not isinstance(name, str) for name in captured)):
        return []
    return [binding for binding in bindings(store, bot.id) if binding["canonical_name"] in captured]


def revoke(store, device_id, bot_ref):
    bot = store.get_bot(bot_ref)
    if bot is None:
        raise KDEConnectError("Assistant is no longer available")
    with store._tx() as db:
        db.execute("DELETE FROM integration_tool_grants WHERE integration_id=? AND bot_id=?", (identity(device_id), bot.id))
    store.bus.notify("work", "bots")
