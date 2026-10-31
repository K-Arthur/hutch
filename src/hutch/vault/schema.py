"""Vault tables, created by one ordered migration in ``hutch.store``.

Design notes that are enforced here rather than in prose:

* Ciphertext, nonce and key version live in ``vault_secret_versions``; metadata lives in
  ``vault_secrets``. A metadata read never touches a ciphertext.
* ``vault_audit`` is append-only: triggers abort any UPDATE or DELETE. ``reason`` is a bounded code,
  never free text, so an error message carrying a value cannot reach the table.
* Grants are keyed by ``(secret, principal kind, principal id, permission)`` with no wildcard
  principal. Deny-by-default is the absence of a row.
* Only one *active* wrap per kind exists (partial unique index). Retiring a wrap and inserting its
  replacement happen in one transaction.
"""

from __future__ import annotations


def migrate(db) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS vault_meta (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        vault_id TEXT NOT NULL CHECK (length(vault_id) = 32),
        key_version INTEGER NOT NULL CHECK (key_version >= 1),
        created_at TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS vault_key_wraps (
        version INTEGER NOT NULL CHECK (version >= 1),
        kind TEXT NOT NULL CHECK (kind IN ('passphrase','recovery')),
        kdf TEXT NOT NULL CHECK (kdf IN ('scrypt','hkdf-sha256')),
        params TEXT NOT NULL CHECK (json_valid(params)),
        nonce BLOB NOT NULL CHECK (length(nonce) = 12),
        wrapped_dek BLOB NOT NULL CHECK (length(wrapped_dek) = 48),
        created_at TEXT NOT NULL,
        retired_at TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (version, kind)
    )""")
    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS vault_key_wraps_active
        ON vault_key_wraps(kind) WHERE retired_at = ''""")
    db.execute("""CREATE TABLE IF NOT EXISTS vault_secrets (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL CHECK (scope = 'workspace' OR scope LIKE 'bot:%'),
        category TEXT NOT NULL,
        name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
        description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 500),
        current_version INTEGER NOT NULL CHECK (current_version >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        rotated_at TEXT NOT NULL DEFAULT '',
        expires_at TEXT NOT NULL DEFAULT '',
        deleted_at TEXT NOT NULL DEFAULT ''
    )""")
    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS vault_secrets_live_name
        ON vault_secrets(scope, name) WHERE deleted_at = ''""")
    db.execute("CREATE INDEX IF NOT EXISTS vault_secrets_scope ON vault_secrets(scope, created_at)")
    db.execute("""CREATE TABLE IF NOT EXISTS vault_secret_versions (
        secret_id TEXT NOT NULL REFERENCES vault_secrets(id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK (version >= 1),
        nonce BLOB NOT NULL CHECK (length(nonce) = 12),
        ciphertext BLOB NOT NULL CHECK (length(ciphertext) BETWEEN 17 AND 131072),
        key_version INTEGER NOT NULL CHECK (key_version >= 1),
        created_at TEXT NOT NULL,
        PRIMARY KEY (secret_id, version)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS vault_grants (
        secret_id TEXT NOT NULL REFERENCES vault_secrets(id) ON DELETE CASCADE,
        principal_kind TEXT NOT NULL CHECK (principal_kind IN ('bot','workspace','connector','skill')),
        principal_id TEXT NOT NULL,
        permission TEXT NOT NULL CHECK (permission IN ('metadata','use','reveal','rotate','delete')),
        granted_at TEXT NOT NULL,
        PRIMARY KEY (secret_id, principal_kind, principal_id, permission)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS vault_grants_principal "
               "ON vault_grants(principal_kind, principal_id)")
    db.execute("""CREATE TABLE IF NOT EXISTS vault_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at TEXT NOT NULL,
        actor_kind TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        action TEXT NOT NULL CHECK (length(action) BETWEEN 1 AND 48),
        secret_id TEXT NOT NULL DEFAULT '',
        scope TEXT NOT NULL DEFAULT '',
        outcome TEXT NOT NULL CHECK (outcome IN ('ok','denied','failed')),
        reason TEXT NOT NULL DEFAULT '' CHECK (length(reason) <= 64),
        destination TEXT NOT NULL DEFAULT '' CHECK (length(destination) <= 253)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS vault_audit_recent ON vault_audit(at DESC, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS vault_audit_secret ON vault_audit(secret_id, at DESC)")
    db.execute("""CREATE TRIGGER IF NOT EXISTS vault_audit_immutable
        BEFORE UPDATE ON vault_audit
        BEGIN SELECT RAISE(ABORT, 'vault audit rows are append-only'); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS vault_audit_no_delete
        BEFORE DELETE ON vault_audit
        BEGIN SELECT RAISE(ABORT, 'vault audit rows are retained'); END""")
    db.execute("""CREATE TABLE IF NOT EXISTS vault_unlock_failures (
        vault_id TEXT PRIMARY KEY,
        failures INTEGER NOT NULL CHECK (failures >= 0),
        window_started_at TEXT NOT NULL,
        blocked_until TEXT NOT NULL DEFAULT ''
    )""")


def migrate_destinations(db) -> None:
    """A separate migration because ``migrate`` had already run on real databases.

    Adding this table inside the original vault migration would have left every installation that
    was already at that schema version without it: the migration runner applies each entry once.
    The runner also executes this on a fresh database, where ``migrate`` has just created the
    secrets table it references.
    """
    db.execute("""CREATE TABLE IF NOT EXISTS vault_destinations (
        secret_id TEXT NOT NULL REFERENCES vault_secrets(id) ON DELETE CASCADE,
        origin TEXT NOT NULL CHECK (length(origin) BETWEEN 8 AND 253),
        created_at TEXT NOT NULL,
        PRIMARY KEY (secret_id, origin)
    )""")
