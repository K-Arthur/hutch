"""Schema v92: append-only schedule revision journal.

The journal is deliberately separate from the bot document. It stores only the
extracted ``schedule``/``schedules`` JSON, so a bot settings change that does not
touch a schedule writes no row, while an API, CLI or direct write to the bot
document is captured by the same trigger.

Triggers are the writer because every caller saves through ``bots.doc``; an
application-level log would miss at least one path. The table is append-only:
corrections are new revisions, never rewrites.
"""

from __future__ import annotations


def _snapshot(column: str) -> str:
    """SQL expression for the schedule portion of a stored bot document."""
    return (f"json_object('schedule', json(json_extract({column}, '$.schedule')), "
            f"'schedules', json(json_extract({column}, '$.schedules')))")


def migrate(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS schedule_revisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id TEXT NOT NULL,
        bot_name TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK(revision >= 1),
        change_type TEXT NOT NULL CHECK(change_type IN ('created','updated')),
        schedules_json TEXT NOT NULL CHECK(json_valid(schedules_json)),
        prev_schedules_json TEXT CHECK(prev_schedules_json IS NULL OR json_valid(prev_schedules_json)),
        changed_at TEXT NOT NULL,
        UNIQUE(bot_id, revision)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_schedule_revisions_bot "
               "ON schedule_revisions(bot_id, revision DESC)")
    db.execute("""CREATE TRIGGER IF NOT EXISTS schedule_revisions_immutable
        BEFORE UPDATE ON schedule_revisions
        BEGIN SELECT RAISE(ABORT, 'schedule revisions are append-only'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS schedule_revisions_no_delete
        BEFORE DELETE ON schedule_revisions
        BEGIN SELECT RAISE(ABORT, 'schedule revisions are append-only'); END""")
    db.execute(f"""CREATE TRIGGER IF NOT EXISTS bots_schedule_revision_insert
        AFTER INSERT ON bots
        WHEN COALESCE(json_array_length(json_extract(NEW.doc, '$.schedules')), 0) > 0
          OR json_extract(NEW.doc, '$.schedule') IS NOT NULL
        BEGIN
            INSERT INTO schedule_revisions
                (bot_id, bot_name, revision, change_type, schedules_json,
                 prev_schedules_json, changed_at)
            VALUES
                (NEW.id, NEW.name, 1, 'created', {_snapshot('NEW.doc')}, NULL,
                 strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'));
        END""")
    db.execute(f"""CREATE TRIGGER IF NOT EXISTS bots_schedule_revision_update
        AFTER UPDATE OF doc ON bots
        WHEN json_extract(OLD.doc, '$.schedules') IS NOT json_extract(NEW.doc, '$.schedules')
          OR json_extract(OLD.doc, '$.schedule') IS NOT json_extract(NEW.doc, '$.schedule')
        BEGIN
            INSERT INTO schedule_revisions
                (bot_id, bot_name, revision, change_type, schedules_json,
                 prev_schedules_json, changed_at)
            VALUES
                (NEW.id, NEW.name,
                 (SELECT COALESCE(MAX(revision), 0) + 1
                  FROM schedule_revisions WHERE bot_id = NEW.id),
                 'updated', {_snapshot('NEW.doc')}, {_snapshot('OLD.doc')},
                 strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'));
        END""")
    # The insert trigger covers future bots. An upgraded database needs one
    # baseline row per bot that already carries a schedule.
    db.execute(f"""INSERT INTO schedule_revisions
        (bot_id, bot_name, revision, change_type, schedules_json,
         prev_schedules_json, changed_at)
        SELECT bots.id, bots.name, 1, 'created', {_snapshot('bots.doc')}, NULL,
               strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
        FROM bots
        WHERE (COALESCE(json_array_length(json_extract(bots.doc, '$.schedules')), 0) > 0
               OR json_extract(bots.doc, '$.schedule') IS NOT NULL)
          AND NOT EXISTS (
              SELECT 1 FROM schedule_revisions WHERE schedule_revisions.bot_id = bots.id
          )""")
