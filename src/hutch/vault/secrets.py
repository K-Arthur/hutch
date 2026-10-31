"""Creating, updating, deleting and listing secrets.

Every value is encrypted before it reaches a statement, and every read path here returns metadata
only. Values leave this module exclusively through ``access.py``.
"""

from __future__ import annotations

from typing import Optional, Union

from . import audit as audit_mod
from . import crypto
from .core import OWNER
from .model import (
    SecretConflict,
    SecretMetadata,
    SecretNotFound,
    clean_expiry,
    value_bytes,
)
from .refs import (
    SecretCategory,
    Principal,
    clean_description,
    clean_name,
    category_profile,
    new_secret_id,
    parse_category,
    parse_scope,
    parse_secret_id,
)


class SecretsMixin:
    """Requires ``_VaultCore`` state plus the key-version reader."""

    def put_secret(self, *, scope: str, category: Union[str, SecretCategory], name: str, value: str,
                   description: str = "", expires_at: str = "", actor: Principal = OWNER,
                   secret_id: Optional[str] = None) -> SecretMetadata:
        parsed_scope = parse_scope(scope)
        parsed_category = parse_category(category)
        clean = clean_name(name)
        note = clean_description(description)
        expiry = clean_expiry(expires_at)
        profile = category_profile(parsed_category)
        raw = value_bytes(value, profile.max_bytes)
        dek = self._require_unlocked()
        sid = parse_secret_id(secret_id) if secret_id else new_secret_id()
        stamp = self._stamp()
        aad = crypto.secret_aad(sid, 1, parsed_scope, parsed_category.value)
        try:
            nonce, ciphertext = crypto.encrypt_secret(dek, bytes(raw), aad)
        finally:
            crypto.zero(raw)
        key_version = int(self._require_meta()["key_version"])
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            if db.execute("SELECT 1 FROM vault_secrets WHERE scope = ? AND name = ? AND deleted_at = ''",
                          (parsed_scope, clean)).fetchone():
                raise SecretConflict("A live secret with that name already exists in this scope.")
            db.execute("INSERT INTO vault_secrets(id, scope, category, name, description, current_version, "
                       "created_at, updated_at, expires_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                       (sid, parsed_scope, parsed_category.value, clean, note, stamp, stamp, expiry))
            db.execute("INSERT INTO vault_secret_versions(secret_id, version, nonce, ciphertext, key_version, "
                       "created_at) VALUES (?, 1, ?, ?, ?, ?)",
                       (sid, nonce, ciphertext, key_version, stamp))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="create_secret",
                             outcome="ok", reason="ok", secret_id=sid, scope=parsed_scope, at=stamp)
        return self.get_metadata(sid)

    def update_secret(self, secret_id: str, value: str, *, name: Optional[str] = None,
                      description: Optional[str] = None, expires_at: Optional[str] = None,
                      actor: Principal = OWNER) -> SecretMetadata:
        sid = parse_secret_id(secret_id)
        dek = self._require_unlocked()
        row = self._secret_row(sid)
        if row is None or row["deleted_at"]:
            raise SecretNotFound("That secret does not exist.")
        category = SecretCategory(row["category"])
        raw = value_bytes(value, category_profile(category).max_bytes)
        version = int(row["current_version"]) + 1
        aad = crypto.secret_aad(sid, version, row["scope"], row["category"])
        try:
            nonce, ciphertext = crypto.encrypt_secret(dek, bytes(raw), aad)
        finally:
            crypto.zero(raw)
        new_name = clean_name(name) if name is not None else row["name"]
        new_note = clean_description(description) if description is not None else row["description"]
        new_expiry = clean_expiry(expires_at) if expires_at is not None else row["expires_at"]
        stamp = self._stamp()
        key_version = int(self._require_meta()["key_version"])
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            if new_name != row["name"] and db.execute(
                    "SELECT 1 FROM vault_secrets WHERE scope = ? AND name = ? AND deleted_at = '' AND id != ?",
                    (row["scope"], new_name, sid)).fetchone():
                raise SecretConflict("A live secret with that name already exists in this scope.")
            # Compare-and-set on the version: a concurrent editor with a stale read cannot
            # overwrite the newer value, and the version in the AAD always matches the row.
            updated = db.execute(
                "UPDATE vault_secrets SET current_version = ?, updated_at = ?, rotated_at = ?, name = ?, "
                "description = ?, expires_at = ? WHERE id = ? AND current_version = ? AND deleted_at = ''",
                (version, stamp, stamp, new_name, new_note, new_expiry, sid, int(row["current_version"]))).rowcount
            if updated != 1:
                raise SecretConflict("This secret changed while you were editing it. Reload and try again.")
            db.execute("INSERT INTO vault_secret_versions(secret_id, version, nonce, ciphertext, key_version, "
                       "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (sid, version, nonce, ciphertext, key_version, stamp))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="update_secret",
                             outcome="ok", reason="ok", secret_id=sid, scope=row["scope"], at=stamp)
        return self.get_metadata(sid)

    def delete_secret(self, secret_id: str, *, hard: bool = False, actor: Principal = OWNER) -> SecretMetadata:
        sid = parse_secret_id(secret_id)
        stamp = self._stamp()
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute("SELECT * FROM vault_secrets WHERE id = ?", (sid,)).fetchone()
            if row is None:
                raise SecretNotFound("That secret does not exist.")
            if not hard and row["deleted_at"]:
                return self._metadata_from_row(row)
            if hard:
                db.execute("DELETE FROM vault_secrets WHERE id = ?", (sid,))
            else:
                db.execute("UPDATE vault_secrets SET deleted_at = ? WHERE id = ? AND deleted_at = ''", (stamp, sid))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="delete_secret",
                             outcome="ok", reason="ok", secret_id=sid, scope=row["scope"], at=stamp)
        return self._metadata_from_row(row) if hard else self.get_metadata(sid)

    def restore_secret(self, secret_id: str, *, actor: Principal = OWNER) -> SecretMetadata:
        sid = parse_secret_id(secret_id)
        stamp = self._stamp()
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            row = db.execute("SELECT * FROM vault_secrets WHERE id = ?", (sid,)).fetchone()
            if row is None:
                raise SecretNotFound("That secret does not exist.")
            if not row["deleted_at"]:
                return self._metadata_from_row(row)
            if db.execute("SELECT 1 FROM vault_secrets WHERE scope = ? AND name = ? AND deleted_at = ''",
                          (row["scope"], row["name"])).fetchone():
                raise SecretConflict("Another live secret now uses that name.")
            db.execute("UPDATE vault_secrets SET deleted_at = '' WHERE id = ?", (sid,))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="restore_secret",
                             outcome="ok", reason="ok", secret_id=sid, scope=row["scope"], at=stamp)
        return self.get_metadata(sid)

    def get_metadata(self, secret_id: str) -> SecretMetadata:
        sid = parse_secret_id(secret_id)
        with self.store._lock:
            row = self.store._db.execute("SELECT * FROM vault_secrets WHERE id = ?", (sid,)).fetchone()
        if row is None:
            raise SecretNotFound("That secret does not exist.")
        return self._metadata_from_row(row)

    def list_secrets(self, *, scope: Optional[str] = None, include_deleted: bool = False) -> list[SecretMetadata]:
        query = "SELECT * FROM vault_secrets"
        clauses = []
        params: list[object] = []
        if scope is not None:
            clauses.append("scope = ?")
            params.append(parse_scope(scope))
        if not include_deleted:
            clauses.append("deleted_at = ''")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, id"
        with self.store._lock:
            rows = self.store._db.execute(query, params).fetchall()
        return [self._metadata_from_row(row) for row in rows]


__all__ = ["SecretsMixin"]
