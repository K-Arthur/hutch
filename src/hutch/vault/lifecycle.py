"""Vault creation, unlock, passphrase change and recovery-key rotation.

Every method here either changes which credential wraps the DEK or which DEK is in memory. None of
them touches a secret's ciphertext: a passphrase change re-wraps the DEK, it never re-encrypts data.
"""

from __future__ import annotations

import json
from datetime import timedelta

from ..models import iso
from . import audit as audit_mod
from . import crypto
from .core import OWNER
from .model import (
    UNLOCK_FREE_ATTEMPTS,
    UNLOCK_MAX_DELAY_SECONDS,
    VaultAlreadyExists,
    VaultCorrupt,
    VaultError,
    VaultCreation,
    VaultStatus,
    VaultThrottled,
    VaultUnlockError,
    b64,
    parse_iso,
    unb64,
)
from .refs import Principal


class LifecycleMixin:
    """Requires ``_VaultCore`` state: ``store``, ``_state``, ``_dek``, ``_meta``, ``_stamp``."""

    # ----------------------------------------------------------------- wraps

    def _active_wrap(self, kind: str):
        with self.store._lock:
            row = self.store._db.execute(
                "SELECT * FROM vault_key_wraps WHERE kind = ? AND retired_at = ''", (kind,)).fetchone()
        if row is None:
            raise VaultCorrupt(f"The vault has no active {kind} key record.")
        return row

    @staticmethod
    def _scrypt_material(row) -> tuple[crypto.ScryptParams, bytes]:
        """Parse a stored passphrase wrap. Any defect is corruption, never a wrong passphrase."""
        if row["kdf"] != crypto.KDF_SCRYPT:
            raise VaultCorrupt("The passphrase key record uses an unexpected KDF.")
        try:
            value = json.loads(row["params"])
        except (TypeError, ValueError):
            raise VaultCorrupt("The passphrase key record is malformed.") from None
        if not isinstance(value, dict):
            raise VaultCorrupt("The passphrase key record is malformed.")
        salt = unb64(value.pop("salt", None), crypto.SALT_BYTES)
        try:
            params = crypto.ScryptParams.from_dict(value)
        except crypto.VaultCryptoError:
            raise VaultCorrupt("The passphrase key record has invalid cost parameters.") from None
        return params, salt

    @staticmethod
    def _recovery_material(row) -> bytes:
        if row["kdf"] != crypto.KDF_HKDF_SHA256:
            raise VaultCorrupt("The recovery key record uses an unexpected KDF.")
        try:
            value = json.loads(row["params"])
        except (TypeError, ValueError):
            raise VaultCorrupt("The recovery key record is malformed.") from None
        if not isinstance(value, dict) or set(value) != {"salt"}:
            raise VaultCorrupt("The recovery key record is malformed.")
        return unb64(value["salt"], crypto.SALT_BYTES)

    # ------------------------------------------------------------- lifecycle

    def create(self, passphrase: str, *, actor: Principal = OWNER) -> VaultCreation:
        """Create the vault and return its recovery key. The key is not stored anywhere else."""
        problem = crypto.passphrase_problem(passphrase)
        if problem:
            raise VaultError(problem)
        if self._meta() is not None:
            raise VaultAlreadyExists("A vault already exists on this Hutch.")

        vault_id = crypto.new_vault_id()
        dek = crypto.new_dek()
        pass_salt = crypto.new_salt()
        pass_params = self._creation_params
        kek = crypto.derive_passphrase_kek(passphrase, pass_salt, pass_params)
        try:
            pass_nonce, pass_wrapped = crypto.wrap_dek(
                kek, dek, crypto.wrap_aad(vault_id, 1, "passphrase"))
        finally:
            crypto.zero(kek)

        recovery_text, recovery_payload = crypto.generate_recovery_key()
        rec_salt = crypto.new_salt()
        recovery_kek = crypto.derive_recovery_kek(recovery_payload, rec_salt)
        try:
            rec_nonce, rec_wrapped = crypto.wrap_dek(
                recovery_kek, dek, crypto.wrap_aad(vault_id, 1, "recovery"))
        finally:
            crypto.zero(recovery_kek)

        stamp = self._stamp()
        pass_json = json.dumps({**pass_params.as_dict(), "salt": b64(pass_salt)})
        rec_json = json.dumps({"salt": b64(rec_salt)})
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            if db.execute("SELECT 1 FROM vault_meta WHERE singleton = 1").fetchone():
                raise VaultAlreadyExists("A vault already exists on this Hutch.")
            db.execute("INSERT INTO vault_meta(singleton, vault_id, key_version, created_at) "
                       "VALUES (1, ?, 1, ?)", (vault_id, stamp))
            db.execute("INSERT INTO vault_key_wraps(version, kind, kdf, params, nonce, wrapped_dek, created_at) "
                       "VALUES (1, 'passphrase', ?, ?, ?, ?, ?)",
                       (crypto.KDF_SCRYPT, pass_json, pass_nonce, pass_wrapped, stamp))
            db.execute("INSERT INTO vault_key_wraps(version, kind, kdf, params, nonce, wrapped_dek, created_at) "
                       "VALUES (1, 'recovery', ?, ?, ?, ?, ?)",
                       (crypto.KDF_HKDF_SHA256, rec_json, rec_nonce, rec_wrapped, stamp))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="create",
                             outcome="ok", reason="ok", at=stamp)
        with self._state:
            self._dek = dek
            self._vault_id = vault_id
            self._unlocked_at = stamp
        return VaultCreation(status=self.status(), recovery_key=recovery_text)

    def unlock(self, passphrase: str, *, actor: Principal = OWNER) -> VaultStatus:
        if not isinstance(passphrase, str) or not passphrase:
            raise VaultUnlockError("A vault passphrase is required.")
        meta = self._require_meta()
        vault_id = meta["vault_id"]
        self._refuse_if_throttled(vault_id, actor, "unlock")
        row = self._active_wrap("passphrase")
        try:
            params, salt = self._scrypt_material(row)
            kek = crypto.derive_passphrase_kek(passphrase, salt, params)
            try:
                dek = crypto.unwrap_dek(kek, bytes(row["nonce"]), bytes(row["wrapped_dek"]),
                                        crypto.wrap_aad(vault_id, int(row["version"]), "passphrase"))
            finally:
                crypto.zero(kek)
        except (crypto.WrongKey, crypto.VaultCryptoError):
            self._record_unlock_failure(vault_id, actor, "unlock", "wrong_passphrase")
            raise VaultUnlockError("That passphrase does not open this vault.") from None
        self._adopt(dek, vault_id, actor, "unlock")
        return self.status()

    def unlock_with_recovery_key(self, recovery_key: str, *, actor: Principal = OWNER) -> VaultStatus:
        meta = self._require_meta()
        vault_id = meta["vault_id"]
        self._refuse_if_throttled(vault_id, actor, "unlock")
        try:
            payload = crypto.parse_recovery_key(recovery_key)
        except crypto.VaultCryptoError:
            self._record_unlock_failure(vault_id, actor, "unlock", "wrong_recovery_key")
            raise VaultUnlockError("That recovery key is not valid for this vault.") from None
        row = self._active_wrap("recovery")
        try:
            salt = self._recovery_material(row)
            kek = crypto.derive_recovery_kek(payload, salt)
            try:
                dek = crypto.unwrap_dek(kek, bytes(row["nonce"]), bytes(row["wrapped_dek"]),
                                        crypto.wrap_aad(vault_id, int(row["version"]), "recovery"))
            finally:
                crypto.zero(kek)
        except (crypto.WrongKey, crypto.VaultCryptoError):
            self._record_unlock_failure(vault_id, actor, "unlock", "wrong_recovery_key")
            raise VaultUnlockError("That recovery key does not open this vault.") from None
        self._adopt(dek, vault_id, actor, "unlock")
        return self.status()

    def change_passphrase(self, new_passphrase: str, *, actor: Principal = OWNER) -> VaultStatus:
        """Re-wrap the same DEK under a new passphrase. Existing secret ciphertext is untouched."""
        dek = self._require_unlocked()
        problem = crypto.passphrase_problem(new_passphrase)
        if problem:
            raise VaultError(problem)
        meta = self._require_meta()
        vault_id = meta["vault_id"]
        version = int(meta["key_version"]) + 1
        salt = crypto.new_salt()
        params = crypto.DEFAULT_SCRYPT          # never inherit a lower stored cost
        kek = crypto.derive_passphrase_kek(new_passphrase, salt, params)
        try:
            nonce, wrapped = crypto.wrap_dek(kek, dek, crypto.wrap_aad(vault_id, version, "passphrase"))
        finally:
            crypto.zero(kek)
        stamp = self._stamp()
        params_json = json.dumps({**params.as_dict(), "salt": b64(salt)})
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            db.execute("UPDATE vault_key_wraps SET retired_at = ? WHERE kind = 'passphrase' AND retired_at = ''",
                       (stamp,))
            db.execute("INSERT INTO vault_key_wraps(version, kind, kdf, params, nonce, wrapped_dek, created_at) "
                       "VALUES (?, 'passphrase', ?, ?, ?, ?, ?)",
                       (version, crypto.KDF_SCRYPT, params_json, nonce, wrapped, stamp))
            db.execute("UPDATE vault_meta SET key_version = ? WHERE singleton = 1", (version,))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="change_passphrase",
                             outcome="ok", reason="ok", at=stamp)
        return self.status()

    def rotate_recovery_key(self, *, actor: Principal = OWNER) -> str:
        """Replace the recovery wrap and return the new key, shown once."""
        dek = self._require_unlocked()
        meta = self._require_meta()
        vault_id = meta["vault_id"]
        version = int(meta["key_version"]) + 1
        recovery_text, payload = crypto.generate_recovery_key()
        salt = crypto.new_salt()
        kek = crypto.derive_recovery_kek(payload, salt)
        try:
            nonce, wrapped = crypto.wrap_dek(kek, dek, crypto.wrap_aad(vault_id, version, "recovery"))
        finally:
            crypto.zero(kek)
        stamp = self._stamp()
        with self.store._tx() as db:
            self.store._assert_execution_ready(db)
            db.execute("UPDATE vault_key_wraps SET retired_at = ? WHERE kind = 'recovery' AND retired_at = ''",
                       (stamp,))
            db.execute("INSERT INTO vault_key_wraps(version, kind, kdf, params, nonce, wrapped_dek, created_at) "
                       "VALUES (?, 'recovery', ?, ?, ?, ?, ?)",
                       (version, crypto.KDF_HKDF_SHA256, json.dumps({"salt": b64(salt)}), nonce, wrapped, stamp))
            db.execute("UPDATE vault_meta SET key_version = ? WHERE singleton = 1", (version,))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action="rotate_recovery_key",
                             outcome="ok", reason="ok", at=stamp)
        return recovery_text

    def _adopt(self, dek: bytearray, vault_id: str, actor: Principal, action: str) -> None:
        stamp = self._stamp()
        with self.store._tx() as db:
            db.execute("DELETE FROM vault_unlock_failures WHERE vault_id = ?", (vault_id,))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action=action,
                             outcome="ok", reason="ok", at=stamp)
        with self._state:
            if self._dek is not None:
                crypto.zero(self._dek)
            self._dek = dek
            self._vault_id = vault_id
            self._unlocked_at = stamp

    # -------------------------------------------------------------- throttle

    def _throttle_remaining(self, vault_id: str) -> int:
        with self.store._lock:
            row = self.store._db.execute(
                "SELECT blocked_until FROM vault_unlock_failures WHERE vault_id = ?", (vault_id,)).fetchone()
        if row is None:
            return 0
        blocked = parse_iso(row["blocked_until"])
        if blocked is None:
            return 0
        return max(0, int((blocked - self._now()).total_seconds()))

    def _refuse_if_throttled(self, vault_id: str, actor: Principal, action: str) -> None:
        remaining = self._throttle_remaining(vault_id)
        if remaining:
            self._audit(actor, action, "denied", reason="throttled")
            raise VaultThrottled(remaining)

    def _record_unlock_failure(self, vault_id: str, actor: Principal, action: str, reason: str) -> None:
        now = self._now()
        with self.store._tx() as db:
            row = db.execute("SELECT * FROM vault_unlock_failures WHERE vault_id = ?", (vault_id,)).fetchone()
            window_started = parse_iso(row["window_started_at"]) if row is not None else None
            if row is None or window_started is None or window_started < now - timedelta(minutes=15):
                failures = 1
                window_started = now
            else:
                failures = int(row["failures"]) + 1
            delay = 0
            if failures > UNLOCK_FREE_ATTEMPTS:
                delay = min(2 ** (failures - UNLOCK_FREE_ATTEMPTS - 1), UNLOCK_MAX_DELAY_SECONDS)
            blocked_until = iso(now + timedelta(seconds=delay)) if delay else ""
            db.execute(
                "INSERT INTO vault_unlock_failures(vault_id, failures, window_started_at, blocked_until) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(vault_id) DO UPDATE SET "
                "failures = excluded.failures, window_started_at = excluded.window_started_at, "
                "blocked_until = excluded.blocked_until",
                (vault_id, failures, iso(window_started), blocked_until))
            audit_mod.record(db, actor_kind=actor.kind, actor_id=actor.id, action=action,
                             outcome="denied", reason=reason, at=iso(now))


__all__ = ["LifecycleMixin"]
