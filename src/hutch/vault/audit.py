"""Append-only credential audit.

Every row answers a narrow question: *who asked, for which secret, what did Hutch decide, and why*.
Rows never carry a value, and ``reason`` is a closed vocabulary rather than free text, so an error
message that happens to contain a secret cannot be stored here. ``destination`` is only written
when it validates as a bare DNS hostname.

The table's immutability is enforced by triggers in ``schema.py``; this module refuses to write
anything it cannot validate before the trigger ever sees it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..models import iso, utcnow

ACTIONS = frozenset({
    "create", "unlock", "lock", "change_passphrase", "rotate_recovery_key",
    "create_secret", "update_secret", "delete_secret", "restore_secret",
    "grant", "revoke", "use", "reveal", "read_metadata",
})

REASONS = frozenset({
    "", "ok", "wrong_passphrase", "wrong_recovery_key", "throttled", "no_grant",
    "wrong_scope", "locked", "not_initialized", "not_found", "deleted",
    "corrupt", "conflict", "invalid", "owner_only",
})

OUTCOMES = frozenset({"ok", "denied", "failed"})

MAX_ACTION_CHARS = 48
MAX_REASON_CHARS = 64
MAX_DESTINATION_CHARS = 253

_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\Z")


class AuditError(ValueError):
    """An audit row was malformed. Refused rather than written and later trusted."""


@dataclass(frozen=True)
class AuditEntry:
    id: int
    at: str
    actor_kind: str
    actor_id: str
    action: str
    secret_id: str
    scope: str
    outcome: str
    reason: str
    destination: str

    @property
    def actor(self) -> str:
        return "owner" if self.actor_kind == "owner" else f"{self.actor_kind}:{self.actor_id}"


def clean_destination(value: Optional[str]) -> str:
    """A bare lowercase DNS hostname, or empty. Anything else is dropped, not stored."""
    if not value or not isinstance(value, str):
        return ""
    host = value.strip().lower().rstrip(".")
    if len(host) > MAX_DESTINATION_CHARS or not _HOSTNAME.fullmatch(host):
        return ""
    if ".." in host or host.startswith(".") or host.endswith("."):
        return ""
    return host


def record(db, *, actor_kind: str, actor_id: str, action: str, outcome: str,
           secret_id: str = "", scope: str = "", reason: str = "",
           destination: str = "", at: Optional[str] = None) -> None:
    if action not in ACTIONS:
        raise AuditError(f"unknown audit action: {action!r}")
    if reason not in REASONS:
        raise AuditError(f"unknown audit reason: {reason!r}")
    if outcome not in OUTCOMES:
        raise AuditError(f"unknown audit outcome: {outcome!r}")
    if not isinstance(actor_kind, str) or not actor_kind or len(actor_kind) > 32:
        raise AuditError("an audit actor kind must be a short token")
    if not isinstance(actor_id, str) or len(actor_id) > 128:
        raise AuditError("an audit actor id must be short text")
    if len(secret_id) > 64 or len(scope) > 64:
        raise AuditError("an audit reference is too long")
    db.execute(
        "INSERT INTO vault_audit(at, actor_kind, actor_id, action, secret_id, scope, outcome, reason, destination) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (at or iso(utcnow()), actor_kind[:32], actor_id[:128], action, secret_id[:64], scope[:64],
         outcome, reason, clean_destination(destination)),
    )


def recent(db, *, limit: int = 100, secret_id: Optional[str] = None) -> list[AuditEntry]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
        raise AuditError("an audit page must be between 1 and 500 rows")
    if secret_id:
        rows = db.execute(
            "SELECT * FROM vault_audit WHERE secret_id = ? ORDER BY id DESC LIMIT ?",
            (secret_id, limit)).fetchall()
    else:
        rows = db.execute("SELECT * FROM vault_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [AuditEntry(
        id=row["id"], at=row["at"], actor_kind=row["actor_kind"], actor_id=row["actor_id"],
        action=row["action"], secret_id=row["secret_id"], scope=row["scope"],
        outcome=row["outcome"], reason=row["reason"], destination=row["destination"],
    ) for row in rows]
