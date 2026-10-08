"""Immutable effect intent and separate operator reconciliation; no effect replay."""
from __future__ import annotations

import hashlib
import json
import sqlite3

MAX_INTENT_BYTES = 4 * 1024 * 1024


class ActionConflict(ValueError):
    pass


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def freeze(value):
    return json.loads(canonical(value))


def migrate(db: sqlite3.Connection) -> None:
    db.execute("ALTER TABLE tool_actions ADD COLUMN intent_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(intent_json))")
    db.execute("ALTER TABLE tool_actions ADD COLUMN intent_hash TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE tool_actions ADD COLUMN effect_key TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE tool_actions ADD COLUMN legacy INTEGER NOT NULL DEFAULT 1 CHECK(legacy IN (0, 1))")
    rows = db.execute("SELECT id, tool, effect, summary, idem_key FROM tool_actions")
    while batch := rows.fetchmany(100):
        for row in batch:
            # Arguments cannot be inferred reliably from adjacent tool events.
            raw = canonical({"schema": 0, "tool": row[1], "effect": row[2], "summary": row[3],
                             "arguments": None, "legacy_argument_fingerprint": row[4]})
            db.execute("UPDATE tool_actions SET intent_json = ?, intent_hash = ? WHERE id = ?", (raw, digest(raw), row[0]))
    db.execute("CREATE INDEX idx_actions_effect ON tool_actions(effect_key, run_id, status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_runs_conversation ON runs(conversation_id)")
    db.execute("""CREATE TABLE action_reconciliations (
        action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, intent_hash TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK(outcome IN ('confirmed_done', 'confirmed_failed', 'not_applied')),
        evidence TEXT NOT NULL CHECK(length(evidence) BETWEEN 1 AND 4000),
        recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL)""")
    db.execute("""CREATE TRIGGER action_intent_immutable BEFORE UPDATE OF
        id, run_id, tool, idem_key, effect, summary, started_at, intent_json, intent_hash, effect_key, legacy
        ON tool_actions BEGIN SELECT RAISE(ABORT, 'action intent is immutable'); END""")
    db.execute("""CREATE TRIGGER action_receipt_sealed BEFORE UPDATE OF status, result_digest, finished_at
        ON tool_actions WHEN OLD.status != 'started' OR NEW.status NOT IN ('done', 'failed', 'unknown')
        OR (NEW.status IN ('done', 'failed') AND EXISTS(SELECT 1 FROM runs WHERE id = OLD.run_id AND sealed = 1))
        BEGIN SELECT RAISE(ABORT, 'action receipt is sealed'); END""")
    for table in ("tool_actions", "action_reconciliations"):
        db.execute(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
                   "BEGIN SELECT RAISE(ABORT, 'action history requires an explicit scoped deletion command'); END")
    db.execute("CREATE TRIGGER reconciliation_immutable BEFORE UPDATE ON action_reconciliations "
               "BEGIN SELECT RAISE(ABORT, 'action reconciliation is immutable'); END")


def view(row) -> dict:
    result = dict(row)
    raw = result.pop("intent_json")
    result["intent"] = json.loads(raw)
    result["intent_valid"] = digest(raw) == result["intent_hash"]
    result["legacy"] = result["intent"].get("schema") != 1 or result["intent"].get("arguments") is None
    return result
