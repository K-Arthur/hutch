"""Typed secret references, categories and permissions.

A reference identifies a secret. It never contains a value, and holding one grants nothing: the
grant is checked separately at resolution time. References are safe in configuration, API
responses, audit rows and UI; values are not.

The grammar is deliberately strict. Anything that does not match exactly is refused rather than
normalised, because a permissive parser is how a value ends up embedded in something that gets
logged.

    secret://hutch/local/sec_0123456789abcdef01234567
    secret://hutch/local/sec_0123456789abcdef01234567#v3
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Optional

SCHEME = "secret"
#: Implemented providers. External providers are added here only once an adapter is validated.
PROVIDERS = ("hutch",)
DEFAULT_ALIAS = "local"
LOCAL_PROVIDER = "hutch"

ALIAS_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")
SECRET_ID_PATTERN = re.compile(r"sec_[0-9a-f]{24}\Z")
REF_PATTERN = re.compile(
    r"secret://(?P<provider>[a-z][a-z0-9-]{0,31})/"
    r"(?P<alias>[a-z][a-z0-9-]{0,31})/"
    r"(?P<secret_id>sec_[0-9a-f]{24})"
    r"(?:#v(?P<version>[1-9][0-9]{0,8}))?\Z"
)
MAX_REF_CHARS = 128

BOT_ID_PATTERN = re.compile(r"bot_[0-9a-f]{12}\Z")
CONNECTOR_ID_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
SKILL_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
MAX_NAME_CHARS = 120
MAX_DESCRIPTION_CHARS = 500


class SecretRefError(ValueError):
    """A reference, scope or principal was malformed or unsupported. Carries no secret content."""


class SecretCategory(str, Enum):
    """Categories with genuinely different lifecycles, not a cosmetic tag list."""

    API_KEY = "api_key"
    OAUTH_ACCESS_TOKEN = "oauth_access_token"
    OAUTH_REFRESH_TOKEN = "oauth_refresh_token"
    CONNECTOR_CREDENTIAL = "connector_credential"
    SERVICE_ACCOUNT = "service_account"
    DATABASE_CREDENTIAL = "database_credential"
    SSH_PRIVATE_KEY = "ssh_private_key"
    WEBHOOK_SIGNING_SECRET = "webhook_signing_secret"
    APP_PASSWORD = "app_password"
    RECOVERY_MATERIAL = "recovery_material"
    OTHER = "other"


class Lifecycle(str, Enum):
    """How a value is expected to age. Drives rotation and expiry warnings, not access control."""

    STATIC = "static"
    ROTATING = "rotating"
    SHORT_LIVED = "short_lived"
    OAUTH_MANAGED = "oauth_managed"
    PRIVATE_KEY = "private_key"


@dataclass(frozen=True)
class CategoryProfile:
    category: SecretCategory
    label: str
    lifecycle: Lifecycle
    max_bytes: int
    warns_when_unrotated_days: int = 0


CATEGORY_PROFILES: dict[SecretCategory, CategoryProfile] = {
    SecretCategory.API_KEY: CategoryProfile(
        SecretCategory.API_KEY, "API key", Lifecycle.ROTATING, 8192, 180),
    SecretCategory.OAUTH_ACCESS_TOKEN: CategoryProfile(
        SecretCategory.OAUTH_ACCESS_TOKEN, "OAuth access token", Lifecycle.SHORT_LIVED, 16384),
    SecretCategory.OAUTH_REFRESH_TOKEN: CategoryProfile(
        SecretCategory.OAUTH_REFRESH_TOKEN, "OAuth refresh token", Lifecycle.OAUTH_MANAGED, 16384),
    SecretCategory.CONNECTOR_CREDENTIAL: CategoryProfile(
        SecretCategory.CONNECTOR_CREDENTIAL, "Connector credential", Lifecycle.ROTATING, 16384, 180),
    SecretCategory.SERVICE_ACCOUNT: CategoryProfile(
        SecretCategory.SERVICE_ACCOUNT, "Service-account credential", Lifecycle.ROTATING, 65536, 180),
    SecretCategory.DATABASE_CREDENTIAL: CategoryProfile(
        SecretCategory.DATABASE_CREDENTIAL, "Database credential", Lifecycle.ROTATING, 8192, 180),
    SecretCategory.SSH_PRIVATE_KEY: CategoryProfile(
        SecretCategory.SSH_PRIVATE_KEY, "SSH private key", Lifecycle.PRIVATE_KEY, 65536, 365),
    SecretCategory.WEBHOOK_SIGNING_SECRET: CategoryProfile(
        SecretCategory.WEBHOOK_SIGNING_SECRET, "Webhook signing secret", Lifecycle.ROTATING, 4096, 180),
    SecretCategory.APP_PASSWORD: CategoryProfile(
        SecretCategory.APP_PASSWORD, "Application password", Lifecycle.ROTATING, 4096, 180),
    SecretCategory.RECOVERY_MATERIAL: CategoryProfile(
        SecretCategory.RECOVERY_MATERIAL, "Recovery material", Lifecycle.STATIC, 16384),
    SecretCategory.OTHER: CategoryProfile(
        SecretCategory.OTHER, "Other secret", Lifecycle.STATIC, 65536),
}


def category_profile(category: SecretCategory) -> CategoryProfile:
    return CATEGORY_PROFILES[category]


def parse_category(value: object) -> SecretCategory:
    if isinstance(value, SecretCategory):
        return value
    if not isinstance(value, str):
        raise SecretRefError("a secret category must be text")
    try:
        return SecretCategory(value)
    except ValueError:
        raise SecretRefError(f"unknown secret category: {value!r}") from None


class Permission(str, Enum):
    """What a principal may do with one secret. ``use`` and ``reveal`` are deliberately distinct."""

    METADATA = "metadata"
    USE = "use"
    REVEAL = "reveal"
    ROTATE = "rotate"
    DELETE = "delete"


#: Only these may be granted to a non-owner principal. Rotation and deletion stay with the owner.
DELEGABLE_PERMISSIONS = (Permission.METADATA, Permission.USE, Permission.REVEAL)


@dataclass(frozen=True)
class SecretRef:
    provider: str
    alias: str
    secret_id: str
    version: Optional[int] = None

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            raise SecretRefError(f"unsupported secret provider: {self.provider!r}")
        if not ALIAS_PATTERN.fullmatch(self.alias or ""):
            raise SecretRefError("a secret alias must be a lowercase slug")
        if not SECRET_ID_PATTERN.fullmatch(self.secret_id or ""):
            raise SecretRefError("a secret id must be 'sec_' followed by 24 lowercase hex characters")
        if self.version is not None and (not isinstance(self.version, int) or isinstance(self.version, bool)
                                         or self.version < 1):
            raise SecretRefError("a secret version must be a positive integer")

    @property
    def local(self) -> bool:
        return self.provider == LOCAL_PROVIDER

    def __str__(self) -> str:
        suffix = f"#v{self.version}" if self.version is not None else ""
        return f"{SCHEME}://{self.provider}/{self.alias}/{self.secret_id}{suffix}"

    @classmethod
    def parse(cls, text: object) -> "SecretRef":
        """Parse a canonical reference. Refuses anything else, including near-misses."""
        if not isinstance(text, str):
            raise SecretRefError("a secret reference must be text")
        if len(text) > MAX_REF_CHARS:
            raise SecretRefError("a secret reference is too long")
        match = REF_PATTERN.fullmatch(text)
        if match is None:
            raise SecretRefError("a secret reference must look like secret://hutch/local/sec_<24 hex>")
        version = match.group("version")
        return cls(provider=match.group("provider"), alias=match.group("alias"),
                   secret_id=match.group("secret_id"),
                   version=int(version) if version is not None else None)

    @classmethod
    def local_ref(cls, secret_id: str, version: Optional[int] = None,
                  alias: str = DEFAULT_ALIAS) -> "SecretRef":
        return cls(provider=LOCAL_PROVIDER, alias=alias, secret_id=secret_id, version=version)


def new_secret_id() -> str:
    return "sec_" + secrets.token_hex(12)


def parse_secret_id(value: object) -> str:
    if not isinstance(value, str) or not SECRET_ID_PATTERN.fullmatch(value):
        raise SecretRefError("a secret id must be 'sec_' followed by 24 lowercase hex characters")
    return value


def clean_name(value: object) -> str:
    if not isinstance(value, str):
        raise SecretRefError("a secret needs a name")
    name = " ".join(value.split())
    if not name:
        raise SecretRefError("a secret needs a name")
    if len(name) > MAX_NAME_CHARS:
        raise SecretRefError(f"a secret name must be at most {MAX_NAME_CHARS} characters")
    if any(ord(char) < 32 for char in name):
        raise SecretRefError("a secret name cannot contain control characters")
    return name


def clean_description(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SecretRefError("a secret description must be text")
    description = " ".join(value.split())
    if len(description) > MAX_DESCRIPTION_CHARS:
        raise SecretRefError(f"a secret description must be at most {MAX_DESCRIPTION_CHARS} characters")
    if any(ord(char) < 32 for char in description):
        raise SecretRefError("a secret description cannot contain control characters")
    return description


SCOPE_WORKSPACE = "workspace"


def parse_scope(value: object) -> str:
    """``workspace`` or ``bot:<bot_id>``. This is the second check after a grant, not the first."""
    if value == SCOPE_WORKSPACE:
        return SCOPE_WORKSPACE
    if isinstance(value, str) and value.startswith("bot:"):
        bot_id = value[4:]
        if BOT_ID_PATTERN.fullmatch(bot_id):
            return value
    raise SecretRefError("a secret scope must be 'workspace' or 'bot:<bot id>'")


@dataclass(frozen=True)
class Principal:
    """Who is asking. ``owner`` is the local operator; everything else must be granted access."""

    kind: str
    id: str = ""

    KINDS = ("owner", "workspace", "bot", "connector", "skill")

    def __post_init__(self) -> None:
        if self.kind not in self.KINDS:
            raise SecretRefError(f"unknown principal kind: {self.kind!r}")
        if self.kind == "owner":
            if self.id not in ("", "owner"):
                raise SecretRefError("the owner principal has no separate identity")
            object.__setattr__(self, "id", "owner")
        elif self.kind == "workspace":
            if self.id not in ("", SCOPE_WORKSPACE):
                raise SecretRefError("the workspace principal has no separate identity")
            object.__setattr__(self, "id", SCOPE_WORKSPACE)
        elif self.kind == "bot":
            if not BOT_ID_PATTERN.fullmatch(self.id):
                raise SecretRefError("a bot principal id must look like bot_<12 hex>")
        elif self.kind == "connector":
            if not CONNECTOR_ID_PATTERN.fullmatch(self.id):
                raise SecretRefError("a connector principal id must be a lowercase slug")
        elif self.kind == "skill":
            if not SKILL_NAME_PATTERN.fullmatch(self.id):
                raise SecretRefError("a skill principal id must be a lowercase name")

    @classmethod
    def owner(cls) -> "Principal":
        return cls("owner")

    @classmethod
    def bot(cls, bot_id: str) -> "Principal":
        return cls("bot", bot_id)

    @classmethod
    def workspace(cls) -> "Principal":
        return cls("workspace")

    @property
    def label(self) -> str:
        return "owner" if self.kind == "owner" else f"{self.kind}:{self.id}"

    @property
    def is_owner(self) -> bool:
        return self.kind == "owner"

    def scope_allows(self, scope: str) -> bool:
        """A bot-scoped secret is never reachable by another bot, whatever a grant says."""
        if scope == SCOPE_WORKSPACE:
            return True
        return self.kind == "bot" and scope == f"bot:{self.id}"
