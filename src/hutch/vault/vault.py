"""The Hutch vault: an owner-unlocked encrypted store with per-principal grants.

The invariants this package exists to keep:

1. A value is encrypted before it is written and decrypted only while the vault is unlocked.
2. Reading a value is a separate, named operation from using one. ``reveal`` and
   ``resolve_for_use`` are different methods with different permissions and different audit rows.
3. A principal without a grant gets nothing, and the refusal is recorded.
4. There is no fallback. Missing vault, locked vault, missing key record, failed authentication and
   deleted secret all raise. None of them returns a default, an environment value or a file.

The class below only composes the parts. Lifecycle, secret storage and access each live in their
own module so they can be read, tested and changed independently.
"""

from __future__ import annotations

import threading
from typing import Optional

from .access import AccessMixin
from .core import OWNER, _VaultCore
from .destinations import DestinationError, DestinationsMixin
from .lifecycle import LifecycleMixin
from .model import (  # noqa: F401 - re-exported for callers of the vault package
    AccessDenied,
    Grant,
    SCOPE_WORKSPACE,
    SecretConflict,
    SecretMetadata,
    SecretNotFound,
    UsableSecret,
    VaultAlreadyExists,
    VaultCorrupt,
    VaultCreation,
    VaultError,
    VaultLocked,
    VaultNotInitialized,
    VaultStatus,
    VaultThrottled,
    VaultUnlockError,
)
from .refs import Permission, Principal, SecretCategory, SecretRef
from .secrets import SecretsMixin


class VaultBook(LifecycleMixin, SecretsMixin, DestinationsMixin, AccessMixin, _VaultCore):
    """Vault lifecycle, secret storage, grants and resolution for one Hutch database."""

    def __init__(self, store, *, scrypt_params=None, clock=None):
        super().__init__(store, scrypt_params=scrypt_params, clock=clock)


#: One unlock state per database path in this process. The dashboard and a bot run in the same
#: process must share it: unlocking in Settings must make a mediated use possible in the run loop.
_REGISTRY: dict[str, VaultBook] = {}
_REGISTRY_LOCK = threading.Lock()


def vault_for(store, *, scrypt_params=None) -> VaultBook:
    """The process-wide vault for ``store``'s database. ``scrypt_params`` only applies on creation."""
    key = str(store.config.db_path)
    with _REGISTRY_LOCK:
        book = _REGISTRY.get(key)
        if book is None:
            book = VaultBook(store, scrypt_params=scrypt_params)
            _REGISTRY[key] = book
        return book


__all__ = [
    "AccessDenied",
    "DestinationError",
    "Grant",
    "OWNER",
    "Permission",
    "Principal",
    "SCOPE_WORKSPACE",
    "SecretCategory",
    "SecretConflict",
    "SecretMetadata",
    "SecretNotFound",
    "SecretRef",
    "UsableSecret",
    "VaultAlreadyExists",
    "VaultBook",
    "VaultCorrupt",
    "VaultCreation",
    "VaultError",
    "VaultLocked",
    "VaultNotInitialized",
    "VaultStatus",
    "VaultThrottled",
    "VaultUnlockError",
    "vault_for",
]
