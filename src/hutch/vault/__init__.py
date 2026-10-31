"""Vault and secret references.

The public entry point is :class:`VaultBook`. Crypto, reference parsing, audit, schema, lifecycle,
secret storage and access live in their own modules so each can be tested without the others.
"""

from __future__ import annotations

from .audit import AuditEntry
from .destinations import DestinationError, canonical_origin, request_origin
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
    vault_for,
)

__all__ = [
    "AccessDenied",
    "AuditEntry",
    "CategoryProfile",
    "DestinationError",
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
    "canonical_origin",
    "category_profile",
    "migrate",
    "request_origin",
    "vault_for",
]
