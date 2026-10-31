"""Vault value types, exceptions and shared helpers.

Nothing here touches the database. Keeping the types separate means the lifecycle, secret and
access modules can each be read and tested without the others.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Union

from ..models import iso
from .refs import Principal, SecretRef

#: Attempts that are free before a delay is imposed, and the cap on that delay.
UNLOCK_FREE_ATTEMPTS = 3
UNLOCK_MAX_DELAY_SECONDS = 300

SCOPE_WORKSPACE = "workspace"

RefLike = Union[str, SecretRef]


class VaultError(Exception):
    """A vault operation was refused. Messages are for the operator, never for the model."""


class VaultNotInitialized(VaultError):
    """No vault exists in this database."""


class VaultAlreadyExists(VaultError):
    """A vault already exists; it is never re-initialised over existing ciphertext."""


class VaultLocked(VaultError):
    """A value operation needs an unlocked vault."""


class VaultUnlockError(VaultError):
    """The supplied credential does not open this vault."""


class VaultThrottled(VaultError):
    """Repeated failures; the caller must wait before trying again."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__(f"Too many unlock attempts. Try again in {self.retry_after_seconds} seconds.")


class VaultCorrupt(VaultError):
    """Stored key material or ciphertext failed validation. Nothing is guessed at."""


class SecretNotFound(VaultError):
    """The referenced secret does not exist, is deleted, or has no such version."""


class SecretConflict(VaultError):
    """The secret changed underneath this operation, or the name is already taken."""


class AccessDenied(VaultError):
    """This principal has no grant for this operation on this secret."""


@dataclass(frozen=True)
class VaultStatus:
    initialized: bool
    unlocked: bool
    vault_id: str
    key_version: int
    secret_count: int
    created_at: str
    recovery_configured: bool


@dataclass(frozen=True)
class SecretMetadata:
    """Everything about a secret except its value. Safe for the API, the UI and an agent."""

    id: str
    ref: str
    scope: str
    category: str
    name: str
    description: str
    current_version: int
    created_at: str
    updated_at: str
    rotated_at: str
    expires_at: str
    deleted_at: str

    @property
    def deleted(self) -> bool:
        return bool(self.deleted_at)


@dataclass(frozen=True)
class VaultCreation:
    status: VaultStatus
    recovery_key: str
    """Shown to the owner exactly once. Hutch does not store it anywhere else."""


@dataclass(frozen=True)
class Grant:
    secret_id: str
    principal_kind: str
    principal_id: str
    permission: str
    granted_at: str

    @property
    def principal(self) -> Principal:
        return Principal(self.principal_kind, self.principal_id)


class UsableSecret:
    """A decrypted value that a mediator must consume.

    ``str()`` and ``repr()`` are redacted on purpose: the most common way a credential leaks is an
    f-string or a debug log. A caller that genuinely needs the bytes asks for them by name.
    """

    __slots__ = ("_value", "ref", "principal", "destination")

    def __init__(self, value: str, *, ref: str, principal: Principal, destination: str = ""):
        self._value = value
        self.ref = ref
        self.principal = principal
        self.destination = destination

    def value(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"<UsableSecret {self.ref} principal={self.principal.label} redacted>"

    __str__ = __repr__


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def unb64(value: object, expected: int) -> bytes:
    if not isinstance(value, str) or len(value) > 256:
        raise VaultCorrupt("stored key material is malformed")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        raise VaultCorrupt("stored key material is malformed") from None
    if len(raw) != expected:
        raise VaultCorrupt("stored key material is malformed")
    return raw


def parse_iso(value: object) -> Optional[datetime]:
    """Parse a stored timestamp. Naive or unparseable values are rejected, never assumed local."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def clean_expiry(value: object) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise VaultError("An expiry must be an ISO-8601 timestamp.")
    parsed = parse_iso(value)
    if parsed is None:
        raise VaultError("An expiry must be an ISO-8601 timestamp with a timezone.")
    return iso(parsed)


def value_bytes(value: object, limit: int) -> bytearray:
    """Encode a secret value for encryption, enforcing the category's size and content rules."""
    if not isinstance(value, str):
        raise VaultError("A secret value must be text.")
    if not value:
        raise VaultError("A secret value cannot be empty.")
    if "\x00" in value:
        raise VaultError("A secret value cannot contain a null character.")
    raw = value.encode("utf-8")
    if len(raw) > limit:
        raise VaultError(f"This kind of secret must be at most {limit} bytes.")
    return bytearray(raw)
