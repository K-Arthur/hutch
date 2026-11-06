"""Schema v93: schedule approval policy and pre-run approval mapping.

A schedule policy is a sidecar row, not a new field on the frozen ``Schedule``
model. It carries its own revision for compare-and-swap edits. The policy table
is cleaned up by a trigger when a schedule disappears from the bot document.

The approval mapping is separate from ``approvals``: it answers "is this run
parked before it ever executed?", while ``approvals`` remains the single
decision record shared with tool-approval gates.
"""

from __future__ import annotations


def migrate(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS schedule_policies (
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        schedule_id TEXT NOT NULL,
        approval_required INTEGER NOT NULL DEFAULT 0 CHECK(approval_required IN (0,1)),
        conditions_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(conditions_json)),
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
        updated_at TEXT NOT NULL,
        PRIMARY KEY (bot_id, schedule_id)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_schedule_policies_bot "
               "ON schedule_policies(bot_id, schedule_id)")
    db.execute("""CREATE TABLE IF NOT EXISTS schedule_approval_requests (
        run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
        approval_id TEXT NOT NULL UNIQUE,
        bot_id TEXT NOT NULL,
        schedule_id TEXT NOT NULL,
        occurrence TEXT NOT NULL,
        created_at TEXT NOT NULL,
        reconciled_at TEXT NOT NULL DEFAULT ''
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_schedule_approval_requests_approval "
               "ON schedule_approval_requests(approval_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_schedule_approval_requests_open "
               "ON schedule_approval_requests(reconciled_at, bot_id, schedule_id)")
    # A removed schedule must not leave an active policy behind. The bot
    # document is the only schedule registry, so the trigger compares against it.
    db.execute("""CREATE TRIGGER IF NOT EXISTS bots_schedule_policy_cleanup
        AFTER UPDATE OF doc ON bots
        BEGIN
            DELETE FROM schedule_policies
            WHERE bot_id = NEW.id
              AND schedule_id NOT IN (
                  SELECT json_extract(value, '$.id')
                  FROM json_each(json_extract(NEW.doc, '$.schedules'))
                  WHERE json_extract(value, '$.id') IS NOT NULL
                  UNION
                  SELECT json_extract(NEW.doc, '$.schedule.id')
                  WHERE json_extract(NEW.doc, '$.schedule.id') IS NOT NULL
              );
        END""")
