"""Vault and secret references.

The public entry point is :class:`VaultBook`. Crypto, reference parsing, audit, schema, lifecycle,
secret storage and access live in their own modules so each can be tested without the others.
"""

from __future__ import annotations

from .audit import AuditEntry
from .refs import (
    CategoryProfile,
    Lifecycle,
    Permission,
    Principal,
    SecretCategory,
    SecretRef,
    SecretRefError,
    category_profile,
)
from .schema import migrate
from .vault import (
    AccessDenied,
    Grant,
    SecretConflict,
    SecretMetadata,
    SecretNotFound,
    UsableSecret,
    VaultAlreadyExists,
    VaultBook,
    VaultCorrupt,
    VaultCreation,
    VaultError,
    VaultLocked,
    VaultNotInitialized,
    VaultStatus,
    VaultThrottled,
    VaultUnlockError,
)

__all__ = [
    "AccessDenied",
    "AuditEntry",
    "CategoryProfile",
    "Grant",
    "Lifecycle",
    "Permission",
    "Principal",
    "SecretCategory",
    "SecretConflict",
    "SecretMetadata",
    "SecretNotFound",
    "SecretRef",
    "SecretRefError",
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
    "category_profile",
    "migrate",
]
