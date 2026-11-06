"""Write the runtime's implicit provider prefix into saved model routes.

``parse_spec`` already treats a bare model name as ``openai-compatible/<model>``. That implicit
default is a hidden part of the route: a saved Bot document says less than the thing Hutch runs.
This migration makes the saved document say what already happens. It never changes the provider,
model, fallback order, billing relationship or runtime, and it is idempotent.

The route chain lives in four places in a Bot document: ``model``, ``fallbacks``,
``escalation.to`` and every value of ``task_routes``.
"""

from __future__ import annotations

import json
import sqlite3


def _normalise(spec) -> tuple[object, bool]:
    if not isinstance(spec, str):
        return spec, False
    text = spec.strip()
    if not text:
        return spec, False
    if "/" not in text:
        text = "openai-compatible/" + text
    return text, text != spec


def _normalise_list(value) -> tuple[object, bool]:
    if not isinstance(value, list):
        return value, False
    changed = False
    rows = []
    for item in value:
        item, item_changed = _normalise(item)
        changed = changed or item_changed
        rows.append(item)
    return rows, changed


def _normalise_routes(value) -> tuple[object, bool]:
    if not isinstance(value, dict):
        return value, False
    changed = False
    rows = {}
    for key, spec in value.items():
        spec, spec_changed = _normalise(spec)
        changed = changed or spec_changed
        rows[key] = spec
    return rows, changed


def migrate(db: sqlite3.Connection) -> None:
    """Rewrite saved route strings in place; no column or table is added."""
    for row in db.execute("SELECT id, doc FROM bots").fetchall():
        doc = json.loads(row["doc"])
        changed = False
        if "model" in doc:
            doc["model"], changed = _normalise(doc["model"])
        if "fallbacks" in doc:
            doc["fallbacks"], list_changed = _normalise_list(doc["fallbacks"])
            changed = changed or list_changed
        escalation = doc.get("escalation")
        if isinstance(escalation, dict) and "to" in escalation:
            escalation["to"], escalation_changed = _normalise_list(escalation["to"])
            changed = changed or escalation_changed
        if "task_routes" in doc:
            doc["task_routes"], route_changed = _normalise_routes(doc["task_routes"])
            changed = changed or route_changed
        if changed:
            db.execute("UPDATE bots SET doc = ? WHERE id = ?",
                       (json.dumps(doc, ensure_ascii=False), row["id"]))
