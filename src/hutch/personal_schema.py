"""Schema v82: durable personal commitments, shared spaces and bot scoping grants.

Additive only: new tables, indexes and append-only triggers. No existing column or
row is rewritten. The migration is idempotent (CREATE ... IF NOT EXISTS) so a
partially applied development database can converge, like the channel migration.
"""
from __future__ import annotations


def migrate(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS spaces (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('household','project','team')),
        description TEXT NOT NULL DEFAULT '',
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
        archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS space_members (
        space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
        member_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('owner','adult','collaborator','read_only','child','guest')),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(space_id, member_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS bot_space_grants (
        space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
        bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        PRIMARY KEY(space_id, bot_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS commitments (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done','cancelled')),
        priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low','normal','high')),
        due_at TEXT,
        due_timezone TEXT NOT NULL DEFAULT 'UTC',
        category TEXT NOT NULL DEFAULT '',
        space_id TEXT REFERENCES spaces(id),
        source TEXT NOT NULL DEFAULT 'user'
            CHECK(source IN ('user','assistant','workflow','schedule','import')),
        source_detail TEXT NOT NULL DEFAULT '',
        conversation_id TEXT,
        run_id TEXT,
        message_id TEXT,
        created_by TEXT NOT NULL DEFAULT 'owner'
            CHECK(created_by IN ('owner','assistant','workflow','system')),
        confirmation TEXT NOT NULL DEFAULT 'confirmed'
            CHECK(confirmation IN ('confirmed','proposed')),
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
        completed_at TEXT,
        completion_evidence TEXT NOT NULL DEFAULT '',
        completion_kind TEXT CHECK(completion_kind IS NULL OR completion_kind IN
            ('owner_confirmed','receipt','unverified')),
        completed_by TEXT NOT NULL DEFAULT '',
        dependencies TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(dependencies)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(status != 'done' OR (completed_at IS NOT NULL AND completion_evidence != ''
              AND completion_kind IS NOT NULL)),
        CHECK(status = 'done' OR (completed_at IS NULL AND completion_evidence = ''
              AND completion_kind IS NULL)),
        CHECK(confirmation = 'confirmed' OR status = 'open')
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS commitment_dependencies (
        commitment_id TEXT NOT NULL REFERENCES commitments(id) ON DELETE CASCADE,
        depends_on_id TEXT NOT NULL REFERENCES commitments(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        PRIMARY KEY(commitment_id, depends_on_id),
        CHECK(commitment_id != depends_on_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS commitment_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        commitment_id TEXT NOT NULL REFERENCES commitments(id) ON DELETE CASCADE,
        revision INTEGER NOT NULL,
        kind TEXT NOT NULL,
        actor TEXT NOT NULL,
        detail_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(detail_json)),
        created_at TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_commitments_status_due ON commitments(status, due_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_commitments_space ON commitments(space_id, status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_commitments_run ON commitments(run_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_commitment_events_one ON commitment_events(commitment_id, id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_space_members_one ON space_members(space_id, status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_bot_space_grants_bot ON bot_space_grants(bot_id)")
    # An audit trail is append-only: corrections are new events, never rewrites.
    db.execute("""CREATE TRIGGER IF NOT EXISTS commitment_events_immutable
        BEFORE UPDATE ON commitment_events
        BEGIN SELECT RAISE(ABORT, 'commitment events are append-only'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS commitment_events_no_delete
        BEFORE DELETE ON commitment_events
        WHEN EXISTS (SELECT 1 FROM commitments WHERE id = OLD.commitment_id)
        BEGIN SELECT RAISE(ABORT, 'commitment events are retained with their commitment'); END""")
