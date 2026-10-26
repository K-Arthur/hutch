"""Explicit, provider-scoped reuse of an existing local OpenCode API login.

Only connection setup calls this module. Runtime startup never imports ambient
credentials. OAuth sessions must use OpenCode's own sign-in/refresh flow.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

MAX_AUTH_BYTES = 128 * 1024
_PROVIDER = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}\Z")


class LocalLoginError(ValueError):
    """A safe-to-display connection error, without file contents or secrets."""


def _auth_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "opencode" / "auth.json"


def _read_logins() -> dict:
    path = _auth_path()
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return {}
    except OSError:
        raise LocalLoginError("The local OpenCode login file could not be opened safely.") from None
    try:
        info = os.fstat(fd)
        link = path.lstat()
        if stat.S_ISLNK(link.st_mode) or (getattr(link, "st_file_attributes", 0) & 0x400) \
                or (link.st_dev, link.st_ino) != (info.st_dev, info.st_ino):
            raise LocalLoginError("The local OpenCode login file must not be a link or reparse point.")
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_AUTH_BYTES:
            raise LocalLoginError("The local OpenCode login file is not a bounded regular file.")
        if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise LocalLoginError("The local OpenCode login file must be private to your user (chmod 600).")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_AUTH_BYTES + 1)
        if len(raw) > MAX_AUTH_BYTES:
            raise LocalLoginError("The local OpenCode login file is too large.")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except LocalLoginError:
        raise
    except (OSError, ValueError, UnicodeError):
        raise LocalLoginError("The local OpenCode login file could not be read safely.") from None
    finally:
        os.close(fd)


def local_logins() -> list[dict]:
    """Return provider identifiers and reusability, never credentials or account data."""
    rows = []
    for provider, entry in _read_logins().items():
        if not isinstance(provider, str) or not _PROVIDER.fullmatch(provider) or not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        if kind not in ("api", "oauth"):
            continue
        reusable = kind == "api" and isinstance(entry.get("key"), str) and bool(entry["key"].strip()) \
            and len(entry["key"]) <= 4096
        rows.append({"provider_id": provider, "reusable": reusable,
                     "detail": "Use this API login" if reusable else "Sign in again for this private profile"})
    return sorted(rows, key=lambda row: row["provider_id"])


def reuse_local_login(server, provider_id: str) -> None:
    """Transfer exactly the selected API key through the owned server's connection API."""
    if not _PROVIDER.fullmatch(provider_id):
        raise LocalLoginError("Choose a valid local provider.")
    entry = _read_logins().get(provider_id)
    if not isinstance(entry, dict) or entry.get("type") != "api":
        raise LocalLoginError("This login needs a fresh sign-in in Hutch's private profile.")
    key = entry.get("key")
    if not isinstance(key, str) or not key.strip() or len(key) > 4096:
        raise LocalLoginError("This local provider has no usable API login.")
    integration = next((row for row in server.integrations() if row.get("id") == provider_id), None)
    if not integration or not any(method.get("type") == "key" for method in integration.get("methods", [])
                                  if isinstance(method, dict)):
        raise LocalLoginError("The installed OpenCode server cannot connect this provider with an API key.")
    try:
        server.connect_key(provider_id, key, label="Existing local login")
    except Exception:
        # A provider error body could echo input. Never forward it to the UI.
        raise LocalLoginError("OpenCode could not save this local login. Try the provider's sign-in instead.") from None
