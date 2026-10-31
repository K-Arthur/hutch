"""Read-only list of owner notifications and their delivery receipts.

A notification row is written by the trigger that created the fact it describes; its
delivery row lives in the channel outbox. This route renders both without exposing
message bodies or provider text: kind, subject identity, an optional machine reason
code and the outbox state.
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Response

from ..notification_schema import NOTIFICATION_KINDS
from ..notifications import KIND_LABELS, public


def install_notification_routes(app: FastAPI, store) -> None:
    @app.get("/api/v1/notifications")
    def notifications(response: Response, limit: int = 50, kind: Optional[str] = None) -> dict:
        if kind is not None and kind not in NOTIFICATION_KINDS:
            raise HTTPException(422, "kind must be one of: " + ", ".join(NOTIFICATION_KINDS))
        response.headers["Cache-Control"] = "no-store"
        labels = {bot.id: (bot.display_name or bot.name) for bot in store.list_bots()}
        with store._lock:
            rows = [dict(row) for row in store._db.execute(
                "SELECT n.*, d.channel_id, d.state AS delivery_state, d.attempts, d.error AS delivery_error "
                "FROM notifications n LEFT JOIN channel_deliveries d ON d.notification_id = n.id "
                "WHERE (? IS NULL OR n.kind = ?) "
                "AND EXISTS (SELECT 1 FROM bots b WHERE b.id = n.bot_id) "
                "ORDER BY n.created_at DESC, n.rowid DESC LIMIT ?",
                (kind, kind, max(1, min(limit, 200))))]
        counts = {key: 0 for key in NOTIFICATION_KINDS}
        for row in rows:
            counts[row["kind"]] = counts.get(row["kind"], 0) + 1
        return {
            "contract_version": 1,
            "items": [public(row, labels.get(row["bot_id"], row["bot_id"])) for row in rows],
            "counts": counts,
            "kinds": KIND_LABELS,
        }
