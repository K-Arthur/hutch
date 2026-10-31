"""Grants and the two resolution paths: ``use`` for a mediator, ``reveal`` for a person.

The distinction is the point of the whole design. ``use`` returns a value a mediator applies and
never shows to the model; ``reveal`` returns a value a person asked for. They have different
permissions and produce different audit rows, so "the agent used a credential" and "the owner read
a credential" are never the same event.
"""

from __future__ import annotations

from typing import Optional, Union

from . import audit as audit_mod
from . import crypto
from .core import OWNER
from .destinations import canonical_origin
from .model import (
    AccessDenied,
    Grant,
    RefLike,
    SecretNotFound,
    UsableSecret,
    VaultCorrupt,
    VaultError,
)
from .refs import DELEGABLE_PERMISSIONS, Permission, Principal, SecretRef, parse_secret_id


class AccessMixin:
    """Requires ``_VaultCore`` state and ``_secret_row``."""

    # ---------------------------------------------------------------- grants

    def grants(self, secret_id: str) -> list[Grant]:
        sid = parse_secret_id(secret_id)
        with self.store._lock:
            rows = self.store._db.execute(
                "SELECT * FROM vault_grants WHERE secret_id = ? ORDER BY principal_kind, principal_id, permission",
                (sid,)).fetchall()
        return [Grant(secret_id=row["secret_id"], principal_kind=row["principal_kind"],
                      principal_id=row["principal_id"], permission=row["permission"],
                      granted_at=row["granted_at"]) for row in rows]

    def grant(self, secret_id: str, principal: Principal, permission: Union[str, Permission],
              *, actor: Principal = OWNER) -> None:
        if not isinstance(principal, Principal):
            raise VaultError("A grant needs a principal.")
        try:
            wanted = permission if isinstance(permission, Permission) else Permission(permission)
        except ValueError:
            raise VaultError("Unknown permission.") from None
        if not actor.is_owner:
            raise AccessDenied("Only the owner can change vault grants.")
        if principal.is_owner:
            raise VaultError("The owner already has full access; a grant would do nothing.")
        if wanted not in DELEGABLE_PERMISSIONS:
            raise VaultError("Only the owner may rotate or delete a secret.")
        row = self._secret_row(secret_id)
        if row is None or row["deleted_at"]:
            raise SecretNotFound("That secret does not exist.")
        if not principal.scope_allows(row["scope"]):
            raise AccessDenied("That secret belongs to a different scope.")
        stamp = self._stamp()
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            db.execute("INSERT OR IGNORE INTO vault_grants(secret_id, principal_kind, principal_id, permission, "
                       "granted_at) VALUES (?, ?, ?, ?, ?)",
                       (row["id"], principal.kind, principal.id, wanted.value, stamp))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="grant", outcome="ok",
                             reason="ok", secret_id=row["id"], scope=row["scope"], at=stamp)

    def revoke(self, secret_id: str, principal: Principal, permission: Union[str, Permission],
               *, actor: Principal = OWNER) -> None:
        try:
            wanted = permission if isinstance(permission, Permission) else Permission(permission)
        except ValueError:
            raise VaultError("Unknown permission.") from None
        if not actor.is_owner:
            raise AccessDenied("Only the owner can change vault grants.")
        row = self._secret_row(secret_id)
        if row is None:
            raise SecretNotFound("That secret does not exist.")
        stamp = self._stamp()
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            db.execute("DELETE FROM vault_grants WHERE secret_id = ? AND principal_kind = ? "
                       "AND principal_id = ? AND permission = ?",
                       (row["id"], principal.kind, principal.id, wanted.value))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="revoke", outcome="ok",
                             reason="ok", secret_id=row["id"], scope=row["scope"], at=stamp)

    # ----------------------------------------------------------- resolution

    def _authorize(self, secret_id: str, principal: Principal, permission: Permission, *,
                   action: str, destination: str = "") -> tuple:
        """Deny by default, and record the refusal before raising it."""
        row = self._secret_row(secret_id)
        if row is None:
            self._audit(principal, action, "denied", reason="not_found", secret_id=secret_id,
                        destination=destination)
            raise SecretNotFound("That secret does not exist.")
        if row["deleted_at"]:
            self._audit(principal, action, "denied", reason="deleted", secret_id=secret_id,
                        scope=row["scope"], destination=destination)
            raise SecretNotFound("That secret has been deleted.")
        if not principal.scope_allows(row["scope"]):
            self._audit(principal, action, "denied", reason="wrong_scope", secret_id=secret_id,
                        scope=row["scope"], destination=destination)
            raise AccessDenied("That secret belongs to a different scope.")
        if not principal.is_owner:
            with self.store._lock:
                granted = self.store._db.execute(
                    "SELECT 1 FROM vault_grants WHERE secret_id = ? AND principal_kind = ? "
                    "AND principal_id = ? AND permission = ?",
                    (secret_id, principal.kind, principal.id, permission.value)).fetchone()
            if granted is None:
                self._audit(principal, action, "denied", reason="no_grant", secret_id=secret_id,
                            scope=row["scope"], destination=destination)
                raise AccessDenied("This principal has no grant for that secret.")
        return row

    def _decrypt(self, row, version: Optional[int], principal: Principal) -> tuple[int, str]:
        dek = self._require_unlocked()
        wanted = int(row["current_version"]) if version is None else int(version)
        with self.store._lock:
            stored = self.store._db.execute(
                "SELECT * FROM vault_secret_versions WHERE secret_id = ? AND version = ?",
                (row["id"], wanted)).fetchone()
        if stored is None:
            raise SecretNotFound("That version of the secret does not exist.")
        aad = crypto.secret_aad(row["id"], wanted, row["scope"], row["category"])
        try:
            plain = crypto.decrypt_secret(dek, bytes(stored["nonce"]), bytes(stored["ciphertext"]), aad)
        except crypto.VaultCryptoError:
            self._audit(principal, "use", "failed", reason="corrupt",
                        secret_id=row["id"], scope=row["scope"])
            raise VaultCorrupt("That secret failed authentication and was not returned.") from None
        try:
            text = bytes(plain).decode("utf-8")
        except UnicodeDecodeError:
            raise VaultCorrupt("That secret is not valid text.") from None
        finally:
            crypto.zero(plain)
        return wanted, text

    @staticmethod
    def _ref(secret_id: str, version: Optional[int]) -> SecretRef:
        return SecretRef.local_ref(secret_id, version=version)

    def resolve_for_use(self, ref: RefLike, principal: Principal, *, destination: str) -> UsableSecret:
        """Decrypt a value for a mediator that will present it to a bound destination.

        The caller must hand ``UsableSecret.value()`` to the narrowest possible operation — an
        Authorization header, a protocol exchange — and must never return, print or persist it.
        ``destination`` is a canonical origin; a grant alone is not enough to send the value
        anywhere, because the secret must also be bound to that origin by the owner.
        """
        parsed_ref = SecretRef.parse(ref) if not isinstance(ref, SecretRef) else ref
        if not parsed_ref.local:
            raise VaultError("Only the local Hutch vault is implemented.")
        origin = canonical_origin(destination)
        row = self._authorize(parsed_ref.secret_id, principal, Permission.USE,
                              action="use", destination=origin)
        if not self.destination_bound(parsed_ref.secret_id, origin):
            self._audit(principal, "use", "denied", reason="no_destination",
                        secret_id=row["id"], scope=row["scope"], destination=origin)
            raise AccessDenied("This secret is not bound to that destination.")
        version, text = self._decrypt(row, parsed_ref.version, principal)
        self._audit(principal, "use", "ok", reason="ok", secret_id=row["id"], scope=row["scope"],
                    destination=origin)
        return UsableSecret(text, ref=str(self._ref(row["id"], version)), principal=principal,
                            destination=origin)

    def reveal(self, ref: RefLike, principal: Principal) -> UsableSecret:
        """Return a plaintext value to the caller. Separate permission, separate audit row."""
        parsed_ref = SecretRef.parse(ref) if not isinstance(ref, SecretRef) else ref
        if not parsed_ref.local:
            raise VaultError("Only the local Hutch vault is implemented.")
        row = self._authorize(parsed_ref.secret_id, principal, Permission.REVEAL, action="reveal")
        version, text = self._decrypt(row, parsed_ref.version, principal)
        self._audit(principal, "reveal", "ok", reason="ok", secret_id=row["id"], scope=row["scope"])
        return UsableSecret(text, ref=str(self._ref(row["id"], version)), principal=principal)


__all__ = ["AccessMixin"]
