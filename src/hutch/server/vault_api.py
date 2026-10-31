"""Owner-only vault routes: lifecycle, secrets, grants, audit and an explicit reveal.

The dashboard talks to the vault only through this module. Rules it exists to keep:

* Every route is owner-only. A paired phone is refused by ``authorize_remote_route`` because these
  paths are not in its capability set, and this module checks the principal again rather than
  relying on that alone.
* No response contains a value except ``POST .../reveal``, which is a deliberate, audited act.
* Mutating routes require ``X-Hutch-Request: 1`` in addition to the middleware's origin check, so a
  cross-site form post cannot reach them even if a browser misbehaves.
* Errors carry a code and a sentence, never request content.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..vault import (
    AccessDenied,
    Principal,
    SecretConflict,
    SecretNotFound,
    SecretRef,
    VaultAlreadyExists,
    VaultBook,
    VaultCorrupt,
    VaultError,
    VaultLocked,
    VaultNotInitialized,
    VaultThrottled,
    VaultUnlockError,
)

NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class VaultPassphrase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passphrase: SecretStr = Field(min_length=1, max_length=1024)


class VaultRecoveryKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recovery_key: SecretStr = Field(min_length=1, max_length=256)


class SecretCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=48)
    name: str = Field(min_length=1, max_length=120)
    value: SecretStr = Field(min_length=1, max_length=131072)
    description: str = Field(default="", max_length=500)
    expires_at: str = Field(default="", max_length=64)


class SecretUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: SecretStr = Field(min_length=1, max_length=131072)
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    expires_at: str | None = Field(default=None, max_length=64)


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    principal_kind: str = Field(min_length=1, max_length=32)
    principal_id: str = Field(default="", max_length=64)
    permission: str = Field(min_length=1, max_length=16)


def _status_payload(vault: VaultBook) -> dict:
    status = vault.status()
    return {
        "contract_version": 1,
        "initialized": status.initialized,
        "unlocked": status.unlocked,
        "vault_id": status.vault_id,
        "key_version": status.key_version,
        "secret_count": status.secret_count,
        "created_at": status.created_at,
        "recovery_configured": status.recovery_configured,
        "kdf": "scrypt",
        "kdf_memory_mib": 128,
    }


def _metadata(meta) -> dict:
    return {
        "id": meta.id, "ref": meta.ref, "scope": meta.scope, "category": meta.category,
        "name": meta.name, "description": meta.description,
        "current_version": meta.current_version, "created_at": meta.created_at,
        "updated_at": meta.updated_at, "rotated_at": meta.rotated_at,
        "expires_at": meta.expires_at, "deleted": meta.deleted,
    }


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, VaultNotInitialized):
        return HTTPException(409, "Create a vault first.")
    if isinstance(error, VaultAlreadyExists):
        return HTTPException(409, "A vault already exists on this Hutch.")
    if isinstance(error, VaultThrottled):
        return HTTPException(429, "Too many unlock attempts. Wait and try again.",
                             headers={"Retry-After": str(error.retry_after_seconds)})
    if isinstance(error, VaultUnlockError):
        return HTTPException(403, "That credential does not open this vault.")
    if isinstance(error, VaultLocked):
        return HTTPException(423, "Unlock the vault first.")
    if isinstance(error, VaultCorrupt):
        return HTTPException(500, "Stored vault data failed validation. Do not retry; restore from backup.")
    if isinstance(error, SecretNotFound):
        return HTTPException(404, "That secret does not exist.")
    if isinstance(error, SecretConflict):
        return HTTPException(409, str(error))
    if isinstance(error, AccessDenied):
        return HTTPException(403, str(error))
    if isinstance(error, VaultError):
        return HTTPException(422, str(error))
    if isinstance(error, ValueError):
        # Reference and principal grammars raise ValueError subclasses; a bad shape is a
        # client error, never a server failure.
        return HTTPException(422, str(error))
    return HTTPException(500, "The vault operation failed.")


def install_vault_routes(app, store) -> VaultBook:
    """One VaultBook per process: unlock state must outlive a single request."""
    vault = VaultBook(store)
    app.state.vault = vault

    def owner(request: Request) -> None:
        principal = getattr(request.state, "hutch_principal", None)
        if not principal or principal.get("kind") != "owner":
            raise HTTPException(403, "The vault is available to the local owner only.")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = request.headers.get("x-hutch-request", "")
            if not hmac.compare_digest(token, "1"):
                raise HTTPException(403, "browser request verification failed")

    def guard(action):
        try:
            return action()
        except (VaultError, ValueError) as error:
            raise _http_error(error) from None

    @app.get("/api/v1/vault")
    def vault_status(request: Request, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        return _status_payload(vault)

    @app.post("/api/v1/vault/create")
    def vault_create(request: Request, body: VaultPassphrase, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        creation = guard(lambda: vault.create(body.passphrase.get_secret_value()))
        return {**_status_payload(vault), "recovery_key": creation.recovery_key,
                "recovery_key_shown_once": True}

    @app.post("/api/v1/vault/unlock")
    def vault_unlock(request: Request, body: VaultPassphrase, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        guard(lambda: vault.unlock(body.passphrase.get_secret_value()))
        return _status_payload(vault)

    @app.post("/api/v1/vault/unlock-recovery")
    def vault_unlock_recovery(request: Request, body: VaultRecoveryKey, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        guard(lambda: vault.unlock_with_recovery_key(body.recovery_key.get_secret_value()))
        return _status_payload(vault)

    @app.post("/api/v1/vault/lock")
    def vault_lock(request: Request, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        vault.lock()
        return _status_payload(vault)

    @app.post("/api/v1/vault/passphrase")
    def vault_change_passphrase(request: Request, body: VaultPassphrase, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        guard(lambda: vault.change_passphrase(body.passphrase.get_secret_value()))
        return _status_payload(vault)

    @app.post("/api/v1/vault/recovery-key")
    def vault_rotate_recovery(request: Request, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        new_key = guard(lambda: vault.rotate_recovery_key())
        return {**_status_payload(vault), "recovery_key": new_key, "recovery_key_shown_once": True}

    @app.get("/api/v1/vault/secrets")
    def vault_secrets(request: Request, response: Response, scope: str = ""):
        owner(request)
        response.headers.update(NO_STORE)
        items = guard(lambda: vault.list_secrets(scope=scope or None))
        return {"contract_version": 1, "secrets": [_metadata(item) for item in items]}

    @app.get("/api/v1/vault/secrets/{secret_id}")
    def vault_secret(request: Request, secret_id: str, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        meta = guard(lambda: vault.get_metadata(secret_id))
        grants = guard(lambda: vault.grants(secret_id))
        return {"secret": _metadata(meta),
                "grants": [{"principal_kind": g.principal_kind, "principal_id": g.principal_id,
                            "permission": g.permission, "granted_at": g.granted_at} for g in grants]}

    @app.post("/api/v1/vault/secrets")
    def vault_create_secret(request: Request, body: SecretCreate, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        meta = guard(lambda: vault.put_secret(
            scope=body.scope, category=body.category, name=body.name,
            value=body.value.get_secret_value(), description=body.description,
            expires_at=body.expires_at))
        return _metadata(meta)

    @app.put("/api/v1/vault/secrets/{secret_id}")
    def vault_update_secret(request: Request, secret_id: str, body: SecretUpdate, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        meta = guard(lambda: vault.update_secret(
            secret_id, body.value.get_secret_value(), name=body.name,
            description=body.description, expires_at=body.expires_at))
        return _metadata(meta)

    @app.delete("/api/v1/vault/secrets/{secret_id}")
    def vault_delete_secret(request: Request, secret_id: str, response: Response, hard: bool = False):
        owner(request)
        response.headers.update(NO_STORE)
        meta = guard(lambda: vault.delete_secret(secret_id, hard=hard))
        return _metadata(meta)

    @app.post("/api/v1/vault/secrets/{secret_id}/restore")
    def vault_restore_secret(request: Request, secret_id: str, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        return _metadata(guard(lambda: vault.restore_secret(secret_id)))

    @app.post("/api/v1/vault/secrets/{secret_id}/reveal")
    def vault_reveal(request: Request, secret_id: str, response: Response):
        """The only route that returns a value. It is audited as a reveal, not a use."""
        owner(request)
        response.headers.update(NO_STORE)
        reference = guard(lambda: SecretRef.local_ref(secret_id))
        usable = guard(lambda: vault.reveal(reference, Principal.owner()))
        return {"value": usable.value(), "ref": usable.ref}

    @app.post("/api/v1/vault/secrets/{secret_id}/grants")
    def vault_grant(request: Request, secret_id: str, body: GrantBody, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        principal = guard(lambda: Principal(body.principal_kind, body.principal_id))
        guard(lambda: vault.grant(secret_id, principal, body.permission))
        return {"ok": True}

    @app.delete("/api/v1/vault/secrets/{secret_id}/grants")
    def vault_revoke(request: Request, secret_id: str, body: GrantBody, response: Response):
        owner(request)
        response.headers.update(NO_STORE)
        principal = guard(lambda: Principal(body.principal_kind, body.principal_id))
        guard(lambda: vault.revoke(secret_id, principal, body.permission))
        return {"ok": True}

    @app.get("/api/v1/vault/audit")
    def vault_audit(request: Request, response: Response, limit: int = 100, secret_id: str = ""):
        owner(request)
        response.headers.update(NO_STORE)
        entries = guard(lambda: vault.audit_log(limit=max(1, min(limit, 500)), secret_id=secret_id or None))
        return {"contract_version": 1, "entries": [
            {"at": e.at, "actor": e.actor, "action": e.action, "secret_id": e.secret_id,
             "scope": e.scope, "outcome": e.outcome, "reason": e.reason, "destination": e.destination}
            for e in entries]}

    return vault
