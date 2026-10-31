"""Vault state, metadata access, audit and status.

``_VaultCore`` owns the two things every other module depends on: whether the vault is unlocked,
and where its rows live. Everything else is composed from it.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from ..models import iso, utcnow
from . import audit as audit_mod
from . import crypto
from .model import (
    SCOPE_WORKSPACE,
    SecretMetadata,
    VaultLocked,
    VaultNotInitialized,
    VaultStatus,
)
from .refs import Principal

OWNER = Principal.owner()


class _VaultCore:
    """Unlock state, clock, metadata lookup and audit. Not instantiated on its own."""

    def __init__(self, store, *, scrypt_params: Optional[crypto.ScryptParams] = None, clock=None):
        self.store = store
        self._creation_params = scrypt_params or crypto.DEFAULT_SCRYPT
        self._creation_params.validate()
        self._clock = clock or utcnow
        self._state = threading.RLock()
        self._dek: Optional[bytearray] = None
        self._vault_id = ""
        self._unlocked_at = ""

    # ------------------------------------------------------------------ time

    def _now(self) -> datetime:
        return self._clock()

    def _stamp(self) -> str:
        return iso(self._now())

    # ----------------------------------------------------------------- state

    @property
    def is_unlocked(self) -> bool:
        with self._state:
            return self._dek is not None

    def _require_unlocked(self) -> bytearray:
        with self._state:
            if self._dek is None:
                # Distinguish "there is no vault" from "the vault is locked": the first is a setup
                # problem, the second is a prompt. Neither falls back to another store.
                if self._meta() is None:
                    raise VaultNotInitialized("No vault exists on this Hutch yet.")
                raise VaultLocked("Unlock the vault before working with secret values.")
            return self._dek

    def _meta(self):
        with self.store._lock:
            return self.store._db.execute("SELECT * FROM vault_meta WHERE singleton = 1").fetchone()

    def _require_meta(self):
        row = self._meta()
        if row is None:
            raise VaultNotInitialized("No vault exists on this Hutch yet.")
        return row

    def status(self) -> VaultStatus:
        meta = self._meta()
        if meta is None:
            return VaultStatus(initialized=False, unlocked=False, vault_id="", key_version=0,
                               secret_count=0, created_at="", recovery_configured=False)
        with self.store._lock:
            count = self.store._db.execute(
                "SELECT COUNT(*) FROM vault_secrets WHERE deleted_at = ''").fetchone()[0]
            recovery = self.store._db.execute(
                "SELECT 1 FROM vault_key_wraps WHERE kind = 'recovery' AND retired_at = ''").fetchone()
        return VaultStatus(initialized=True, unlocked=self.is_unlocked, vault_id=meta["vault_id"],
                           key_version=int(meta["key_version"]), secret_count=int(count),
                           created_at=meta["created_at"], recovery_configured=recovery is not None)

    # ----------------------------------------------------------------- audit

    def _audit(self, actor: Principal, action: str, outcome: str, *, reason: str = "ok",
               secret_id: str = "", scope: str = "", destination: str = "") -> None:
        with self.store._tx() as db:
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action=action,
                             outcome=outcome, reason=reason, secret_id=secret_id, scope=scope,
                             destination=destination, at=self._stamp())

    def audit_log(self, *, limit: int = 100, secret_id: Optional[str] = None) -> list[audit_mod.AuditEntry]:
        with self.store._lock:
            return audit_mod.recent(self.store._db, limit=limit, secret_id=secret_id or None)

    # -------------------------------------------------------------- metadata

    @staticmethod
    def _metadata_from_row(row) -> SecretMetadata:
        from .refs import SecretRef
        return SecretMetadata(
            id=row["id"], ref=str(SecretRef.local_ref(row["id"])), scope=row["scope"],
            category=row["category"], name=row["name"], description=row["description"],
            current_version=int(row["current_version"]), created_at=row["created_at"],
            updated_at=row["updated_at"], rotated_at=row["rotated_at"],
            expires_at=row["expires_at"], deleted_at=row["deleted_at"])

    def _secret_row(self, secret_id: str):
        from .refs import parse_secret_id
        sid = parse_secret_id(secret_id)
        with self.store._lock:
            return self.store._db.execute("SELECT * FROM vault_secrets WHERE id = ?", (sid,)).fetchone()

    def lock(self, *, actor: Principal = OWNER) -> VaultStatus:
        with self._state:
            if self._dek is not None:
                crypto.zero(self._dek)
            self._dek = None
            self._unlocked_at = ""
        if self._meta() is not None:
            self._audit(actor, "lock", "ok")
        return self.status()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} unlocked={self.is_unlocked}>"


__all__ = ["OWNER", "SCOPE_WORKSPACE", "_VaultCore"]
