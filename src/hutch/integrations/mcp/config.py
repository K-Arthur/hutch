"""Owner-reviewed MCP server definitions: validation, secret hygiene and fingerprints (ADR-0017 S2).

A definition is *review material*, not permission. Saving one records exactly what the owner
consented to run: an executable and its arguments, or an endpoint URL. The fingerprint of that
material is stored with the definition, and a later change to the executable or the mounted
package invalidates it until the owner reviews it again (``integrations.mcp.service``).

Two rules are enforced here rather than in the UI:

* **Secrets never enter configuration.** A value that looks like a credential is refused outright,
  and a credential-shaped *name* may only be supplied as an environment reference. The launcher
  resolves references at spawn time, so the value never reaches SQLite, the transcript or a log.
* **A command is never a shell string.** There is no shell, no glob expansion and no argument
  interpolation; the argv list is passed to ``exec`` through Hutch's sandbox, matching
  ``sandbox.shell_argv``'s discipline for the shell tool.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

MAX_ARGUMENTS = 64
MAX_ARGUMENT_CHARS = 4_096
MAX_CONFIG_BYTES = 32 * 1024
MAX_MOUNTS = 16
MAX_MOUNT_BYTES = 128 * 1024 * 1024
MAX_ENV_ENTRIES = 32

#: A value whose *name* matches one of these must be supplied by reference, never literally.
_SECRET_NAME_PARTS = ("token", "secret", "password", "apikey", "clientsecret", "authorization",
                      "cookie", "credential", "privatekey")

#: System roots an MCP executable may live under without an explicit read-only mount.
_SYSTEM_ROOTS = (Path("/usr"), Path("/bin"), Path("/sbin"), Path("/lib"), Path("/lib64"))

#: Host paths an MCP process may never be granted, whatever the definition says.
_FORBIDDEN_MOUNTS = (Path("/"), Path("/home"), Path("/root"), Path("/etc"), Path("/var"),
                     Path("/proc"), Path("/dev"), Path("/run"), Path("/tmp"), Path("/sys"))
_FORBIDDEN_SUBTREES = (Path("/etc"), Path("/var"), Path("/proc"), Path("/dev"), Path("/run"),
                       Path("/root"), Path("/sys"))

_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")


class McpConfigurationError(ValueError):
    """A server definition cannot be safely reviewed, saved or launched."""


def _normalized(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def looks_secret_name(name: str) -> bool:
    """True when a configuration *name* suggests its value is a credential."""
    folded = _normalized(name)
    return any(part in folded for part in _SECRET_NAME_PARTS)


def _argument_is_sensitive(value: str) -> bool:
    """Refuse ``--token=abc`` style credential flags in a reviewed command line."""
    if not value.startswith("-"):
        return False
    flag = value.lstrip("-").split("=", 1)[0]
    return looks_secret_name(flag)


def _fingerprint_mount(path: Path) -> str:
    """Hash a bounded read-only package tree without following symlinks."""
    digest = hashlib.sha256()
    total_bytes = 0

    def add_file(file_path: Path, relative: str) -> None:
        nonlocal total_bytes
        info = file_path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise McpConfigurationError("read-only server paths may contain only regular files and directories")
        if info.st_size > MAX_MOUNT_BYTES - total_bytes:
            raise McpConfigurationError("reviewed server files exceed Hutch's 128 MiB package limit")
        digest.update(b"file\0" + relative.encode("utf-8", "surrogateescape") + b"\0")
        digest.update(str(stat.S_IMODE(info.st_mode)).encode("ascii") + b"\0")
        total_bytes += info.st_size
        with file_path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)

    try:
        root_info = path.lstat()
        if stat.S_ISREG(root_info.st_mode):
            add_file(path, ".")
            return digest.hexdigest()
        if not stat.S_ISDIR(root_info.st_mode):
            raise McpConfigurationError("read-only server paths must be regular files or directories")
        for root, directories, files in os.walk(path, topdown=True, followlinks=False):
            current = Path(root)
            directories.sort()
            files.sort()
            for name in tuple(directories):
                child = current / name
                relative = child.relative_to(path).as_posix()
                info = child.lstat()
                if stat.S_ISLNK(info.st_mode):
                    digest.update(b"link\0" + relative.encode("utf-8", "surrogateescape") + b"\0")
                    digest.update(os.readlink(child).encode("utf-8", "surrogateescape") + b"\0")
                    directories.remove(name)
                elif stat.S_ISDIR(info.st_mode):
                    digest.update(b"dir\0" + relative.encode("utf-8", "surrogateescape") + b"\0")
                    digest.update(str(stat.S_IMODE(info.st_mode)).encode("ascii") + b"\0")
                else:
                    raise McpConfigurationError("read-only server paths may contain only regular files and directories")
            for name in files:
                child = current / name
                relative = child.relative_to(path).as_posix()
                info = child.lstat()
                if stat.S_ISLNK(info.st_mode):
                    digest.update(b"link\0" + relative.encode("utf-8", "surrogateescape") + b"\0")
                    digest.update(os.readlink(child).encode("utf-8", "surrogateescape") + b"\0")
                else:
                    add_file(child, relative)
    except McpConfigurationError:
        raise
    except (OSError, RuntimeError, UnicodeError) as exc:
        raise McpConfigurationError(f"could not verify a reviewed server path: {exc}") from None
    return digest.hexdigest()


def _resolve_mount(raw: str, known_mounts: list[Path]) -> Path:
    """Resolve one requested read-only path against the host's credential boundaries."""
    if not isinstance(raw, str) or not Path(raw).is_absolute() or "\x00" in raw:
        raise McpConfigurationError("read-only server paths must be absolute local paths")
    try:
        resolved = Path(raw).resolve(strict=True)
    except (OSError, RuntimeError):
        raise McpConfigurationError(f"a read-only server path is unavailable: {raw}") from None
    if any(resolved == denied or denied.is_relative_to(resolved) for denied in _FORBIDDEN_MOUNTS):
        raise McpConfigurationError(f"this path cannot be mounted into an MCP process: {raw}")
    if any(resolved.is_relative_to(denied) for denied in _FORBIDDEN_SUBTREES):
        raise McpConfigurationError(f"system paths cannot be mounted into an MCP process: {raw}")
    if any(resolved == root or root.is_relative_to(resolved) for root in _SYSTEM_ROOTS if root.exists()):
        raise McpConfigurationError("system library paths are already mounted read-only and cannot be re-granted")
    home = Path.home().resolve()
    if resolved == home or home.is_relative_to(resolved):
        raise McpConfigurationError("the home directory and its ancestors cannot be mounted into an MCP process")
    shared_home = Path("/home").resolve()
    if resolved.is_relative_to(shared_home) and not resolved.is_relative_to(home):
        raise McpConfigurationError("another user's home directory cannot be mounted into an MCP process")
    from ...config import get_config
    try:
        state_dir = Path(get_config().state_dir).resolve()
    except Exception:  # noqa: BLE001 - contract-only callers have no config loaded
        raw_state = os.environ.get("HUTCH_STATE_DIR")
        state_dir = Path(raw_state).resolve() if raw_state else None
    if state_dir and (resolved == state_dir or resolved.is_relative_to(state_dir)
                      or state_dir.is_relative_to(resolved)):
        raise McpConfigurationError("Hutch's state directory cannot be mounted into an MCP process")
    if any(resolved.is_relative_to(existing) or existing.is_relative_to(resolved) for existing in known_mounts):
        raise McpConfigurationError("read-only server paths cannot overlap")
    # The same credential-name and symlink screen the shell sandbox applies to extra mounts.
    from ...sandbox import _extra_readonly_mounts
    try:
        _extra_readonly_mounts((str(resolved),))
    except (OSError, RuntimeError, ValueError) as exc:
        raise McpConfigurationError(str(exc)) from None
    return resolved


def _validate_env(raw: Any) -> dict[str, str]:
    """Return ``name -> reference`` entries; a credential-shaped name must be a reference."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict) or len(raw) > MAX_ENV_ENTRIES:
        raise McpConfigurationError(f"server environment must be an object of at most {MAX_ENV_ENTRIES} entries")
    out: dict[str, str] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not _ENV_NAME.match(name):
            raise McpConfigurationError("server environment names must be uppercase shell identifiers")
        if isinstance(value, dict):
            if set(value) != {"from_env"} or not isinstance(value["from_env"], str) \
                    or not _ENV_NAME.match(value["from_env"]):
                raise McpConfigurationError("an environment reference must be {\"from_env\": \"NAME\"}")
            out[name] = f"env:{value['from_env']}"
        elif isinstance(value, str):
            if looks_secret_name(name):
                raise McpConfigurationError(
                    f"{name} looks like a credential; supply it as {{\"from_env\": \"NAME\"}} instead of a literal value")
            if len(value) > MAX_ARGUMENT_CHARS or "\x00" in value or "\n" in value:
                raise McpConfigurationError(f"environment value for {name} is not a single safe line")
            out[name] = f"literal:{value}"
        else:
            raise McpConfigurationError(f"environment value for {name} must be a string or a reference")
    return out


def validate_stdio_definition(raw: Any, *, expected: dict[str, str] | None = None) -> dict[str, Any]:
    """Validate a local server definition and return the normalized, fingerprinted form.

    ``expected`` carries the previously reviewed fingerprints. When they are supplied and differ,
    the executable or a mounted package changed after review and the caller must ask the owner
    again rather than silently running new code (brief §6.7).
    """
    if not isinstance(raw, dict):
        raise McpConfigurationError("a local server definition must be an object")
    if not shutil.which("bwrap"):
        raise McpConfigurationError("local MCP servers need bubblewrap; install bwrap to enable them")
    command = raw.get("command")
    if not isinstance(command, str) or not command.strip():
        raise McpConfigurationError("a local server needs an executable path")
    try:
        resolved_command = Path(command).resolve(strict=True)
        resolved_command.stat()
    except (OSError, RuntimeError):
        raise McpConfigurationError("the local MCP server executable could not be resolved") from None
    if not resolved_command.is_file() or not os.access(resolved_command, os.X_OK):
        raise McpConfigurationError("the local MCP server command must be an executable file")

    raw_args = raw.get("args", [])
    if not isinstance(raw_args, list) or len(raw_args) > MAX_ARGUMENTS:
        raise McpConfigurationError(f"stdio server arguments must be a list of at most {MAX_ARGUMENTS} items")
    args: list[str] = []
    for item in raw_args:
        if not isinstance(item, str) or "\x00" in item or len(item) > MAX_ARGUMENT_CHARS:
            raise McpConfigurationError(
                "stdio server arguments must be plain text with no NULs and at most 4,096 characters each")
        if _argument_is_sensitive(item):
            raise McpConfigurationError(
                "credential values and credential-like command flags cannot be stored in a server definition")
        args.append(item)
    if sum(len(item.encode("utf-8")) for item in args) > MAX_CONFIG_BYTES:
        raise McpConfigurationError("stdio server arguments exceed Hutch's 32 KiB configuration limit")

    raw_mounts = raw.get("read_only_paths", [])
    if not isinstance(raw_mounts, list) or len(raw_mounts) > MAX_MOUNTS:
        raise McpConfigurationError(f"choose at most {MAX_MOUNTS} read-only server paths")
    mounts: list[Path] = []
    for item in raw_mounts:
        mounts.append(_resolve_mount(item, mounts))

    resolved_mounts = mounts
    command_is_system = any(resolved_command.is_relative_to(root.resolve())
                            for root in _SYSTEM_ROOTS if root.exists())
    command_is_mounted = any(resolved_command == mount or resolved_command.is_relative_to(mount)
                             for mount in resolved_mounts)
    if not command_is_system and not command_is_mounted:
        raise McpConfigurationError("the executable must be under /usr or inside one of the reviewed read-only paths")
    if resolved_command.stat().st_size > MAX_MOUNT_BYTES:
        raise McpConfigurationError("the local MCP executable exceeds Hutch's 128 MiB review limit")

    digest = hashlib.sha256()
    with resolved_command.open("rb") as executable:
        for chunk in iter(lambda: executable.read(1024 * 1024), b""):
            digest.update(chunk)
    command_sha256 = digest.hexdigest()
    mount_fingerprints = {str(item): _fingerprint_mount(item) for item in resolved_mounts}

    if expected is not None:
        if expected.get("command_sha256") != command_sha256:
            raise McpConfigurationError("the local MCP executable changed since review; review the server again")
        if expected.get("read_only_fingerprints") != mount_fingerprints:
            raise McpConfigurationError("reviewed server files changed since approval; review the server again")

    return {
        "transport": "mcp_stdio",
        "command": str(resolved_command),
        "args": args,
        "read_only_paths": [str(item) for item in resolved_mounts],
        "env": _validate_env(raw.get("env")),
        "command_sha256": command_sha256,
        "read_only_fingerprints": mount_fingerprints,
    }


def validate_http_definition(raw: Any) -> dict[str, Any]:
    """Validate a remote server definition: HTTPS, no embedded credentials, explicit auth."""
    if not isinstance(raw, dict):
        raise McpConfigurationError("a remote server definition must be an object")
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        raise McpConfigurationError("Enter an MCP endpoint URL")
    try:
        parts = urlsplit(url.strip())
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError:
        raise McpConfigurationError("MCP endpoint URL is malformed") from None
    if (parts.scheme.lower() not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment):
        raise McpConfigurationError(
            "MCP endpoint must be an HTTP(S) URL without credentials, query, or fragment")
    if not 1 <= port <= 65535:
        raise McpConfigurationError("MCP endpoint port is invalid")
    if parts.scheme.lower() == "http":
        from .network import is_local_host
        if not is_local_host(parts.hostname):
            raise McpConfigurationError("plaintext HTTP is only accepted for a loopback MCP endpoint")

    auth = raw.get("auth") or {"type": "none"}
    if not isinstance(auth, dict):
        raise McpConfigurationError("MCP authentication must be an object")
    kind = auth.get("type", "none")
    if kind not in {"none", "bearer"}:
        raise McpConfigurationError("MCP authentication must be 'none' or 'bearer'")
    normalized_auth: dict[str, str] = {"type": kind}
    if kind == "bearer":
        reference = auth.get("from_env")
        if not isinstance(reference, str) or not _ENV_NAME.match(reference):
            raise McpConfigurationError("a bearer endpoint needs {\"from_env\": \"NAME\"} naming a credential variable")
        normalized_auth["from_env"] = reference
    return {"transport": "mcp_http", "url": url.strip(), "auth": normalized_auth}


def definition_revision(normalized: dict[str, Any]) -> str:
    """Stable hash of the reviewed, non-secret definition."""
    import json
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def resolve_environment(definition: dict[str, Any]) -> dict[str, str]:
    """Resolve ``env`` references at spawn time. A missing reference fails closed."""
    out: dict[str, str] = {}
    for name, entry in (definition.get("env") or {}).items():
        kind, _, payload = str(entry).partition(":")
        if kind == "literal":
            out[name] = payload
            continue
        if kind != "env":
            raise McpConfigurationError(f"environment entry {name} is not a reference")
        value = os.environ.get(payload, "")
        if not value:
            raise McpConfigurationError(
                f"the credential variable {payload} is not set; set it before starting this server")
        out[name] = value
    return out


__all__ = ["MAX_ARGUMENTS", "MAX_CONFIG_BYTES", "MAX_MOUNTS", "McpConfigurationError",
           "definition_revision", "looks_secret_name", "resolve_environment",
           "validate_http_definition", "validate_stdio_definition"]
