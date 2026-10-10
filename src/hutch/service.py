"""Install Hutch as a user-level Linux systemd service.

The generated unit only starts the loopback dashboard. Remote supervision is
intentionally not copied from a shell environment or enabled by this command.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


UNIT_NAME = "hutch.service"
MANAGED_MARKER = "# Managed by Hutch CLI."


class ServiceError(RuntimeError):
    """The local systemd service could not be installed or managed safely."""


@dataclass(frozen=True)
class ServiceInstall:
    path: Path
    started: bool


@dataclass(frozen=True)
class ServiceStatus:
    state: str
    installed: bool
    active: bool
    port: int | None = None


def _unit_quote(value: str) -> str:
    """Quote one systemd command-line word without allowing specifier expansion."""
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ServiceError("service command paths cannot contain control characters")
    escaped = (value.replace("\\", "\\\\").replace('"', '\\"')
               .replace("%", "%%").replace("$", "$$"))
    return f'"{escaped}"'


def _environment_value(value: str) -> str:
    """Quote a systemd Environment value and protect literal specifier characters."""
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ServiceError("the Hutch state directory cannot contain control characters")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def render_user_unit(python_executable: str, state_dir: Path, *, port: int = 8787) -> str:
    """Render the safe, loopback-only unit used by `hutch service install`."""
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ServiceError("the Hutch service port must be between 1 and 65535")
    executable = Path(python_executable).expanduser()
    if not executable.is_absolute():
        raise ServiceError("the Python executable for the service must be an absolute path")
    state = Path(state_dir).expanduser()
    if not state.is_absolute():
        raise ServiceError("the Hutch state directory for the service must be an absolute path")
    command = " ".join(_unit_quote(word) for word in (
        str(executable), "-m", "hutch.cli", "serve", "--host", "127.0.0.1", "--port", str(port)
    ))
    return "\n".join((
        MANAGED_MARKER,
        "# Local dashboard only. Remote access requires an explicit interactive launch.",
        "[Unit]",
        "Description=Hutch personal assistant",
        "After=default.target",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={command}",
        f"Environment=HUTCH_STATE_DIR={_environment_value(str(state))}",
        "Environment=HUTCH_EXECUTOR=process",
        "UMask=0077",
        "NoNewPrivileges=yes",
        "PrivateTmp=yes",
        "KillMode=mixed",
        "TimeoutStopSec=45s",
        "Restart=on-failure",
        "RestartSec=3s",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ))


def _systemd_binary(binary: str | None) -> str:
    if sys.platform != "linux":
        raise ServiceError("Hutch's user service installer currently supports Linux with systemd")
    executable = binary or shutil.which("systemctl")
    if not executable:
        raise ServiceError("systemctl is not installed; run `hutch serve` in a terminal instead")
    if not Path(executable).is_absolute():
        raise ServiceError("systemctl must resolve to an absolute executable path")
    return executable


def _systemctl(binary: str, args: list[str], runner: Callable[..., Any] | None) -> subprocess.CompletedProcess:
    run = runner or subprocess.run
    try:
        result = run([binary, "--user", *args], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ServiceError("the systemd user manager could not be reached; keep Hutch running in a terminal") from exc
    if result.returncode != 0:
        detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "").strip()
        detail = " ".join(detail.split())[:300]
        raise ServiceError("systemctl --user " + " ".join(args) + " failed" + (f": {detail}" if detail else ""))
    return result


def _unit_path(config_home: Path | None) -> Path:
    if config_home is None:
        raw = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        config_home = Path(raw).expanduser()
    if not config_home.is_absolute():
        raise ServiceError("XDG_CONFIG_HOME must be an absolute path")
    return config_home.resolve() / "systemd" / "user" / UNIT_NAME


def _prepare_unit_dir(path: Path) -> None:
    unit_dir = path.parent
    if unit_dir.is_symlink():
        raise ServiceError("the systemd user-unit directory cannot be a symbolic link")
    try:
        unit_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise ServiceError("could not create the systemd user-unit directory") from exc
    if unit_dir.is_symlink() or not unit_dir.is_dir():
        raise ServiceError("the systemd user-unit path is not a real directory")


def _atomic_write(path: Path, contents: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".hutch.service.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def install_user_service(
    state_dir: Path,
    *,
    python_executable: str | None = None,
    config_home: Path | None = None,
    port: int = 8787,
    systemctl_bin: str | None = None,
    systemctl_runner: Callable[..., Any] | None = None,
) -> ServiceInstall:
    """Write and start a user unit, refusing symlinks and unrelated existing files."""
    binary = _systemd_binary(systemctl_bin)
    python_executable = python_executable or sys.executable
    contents = render_user_unit(python_executable, Path(state_dir).expanduser().absolute(), port=port)
    path = _unit_path(config_home)
    _prepare_unit_dir(path)
    if path.is_symlink():
        raise ServiceError("hutch.service is a symbolic link; it was not followed or changed")
    if path.exists():
        if not path.is_file():
            raise ServiceError("hutch.service exists but is not a regular file")
        try:
            current = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ServiceError("could not read the existing hutch.service") from exc
        if current != contents:
            raise ServiceError("hutch.service already exists and is not an unchanged Hutch unit; review it manually")
    else:
        try:
            _atomic_write(path, contents)
        except OSError as exc:
            raise ServiceError("could not safely write hutch.service") from exc

    try:
        _systemctl(binary, ["daemon-reload"], systemctl_runner)
        _systemctl(binary, ["enable", "--now", UNIT_NAME], systemctl_runner)
        active = _systemctl(binary, ["is-active", UNIT_NAME], systemctl_runner)
    except ServiceError as exc:
        raise ServiceError(f"unit file was written but could not be confirmed running: {exc}") from exc
    if (getattr(active, "stdout", "") or "").strip() != "active":
        raise ServiceError("unit file was written but systemd did not report hutch.service active")
    return ServiceInstall(path=path, started=True)


def user_service_status(*, systemctl_bin: str | None = None,
                        config_home: Path | None = None,
                        systemctl_runner: Callable[..., Any] | None = None) -> ServiceStatus:
    binary = _systemd_binary(systemctl_bin)
    loaded = _systemctl(binary, ["show", "-p", "LoadState", "--value", UNIT_NAME], systemctl_runner)
    if (getattr(loaded, "stdout", "") or "").strip() == "not-found":
        return ServiceStatus("not installed", installed=False, active=False)
    active = _systemctl(binary, ["is-active", UNIT_NAME], systemctl_runner)
    state = (getattr(active, "stdout", "") or "").strip() or "unknown"
    path = _unit_path(config_home)
    if path.is_symlink():
        raise ServiceError("hutch.service is a symbolic link; its configuration was not followed")
    try:
        contents = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        raise ServiceError("could not read the installed hutch.service") from exc
    match = re.search(r'"--port"\s+"([0-9]{1,5})"', contents)
    port = int(match.group(1)) if match else None
    return ServiceStatus(state, installed=True, active=state == "active", port=port)


def remove_user_service(*, config_home: Path | None = None, systemctl_bin: str | None = None,
                        systemctl_runner: Callable[..., Any] | None = None) -> bool:
    """Stop/disable Hutch and remove its unit only; never alter the Hutch state directory."""
    binary = _systemd_binary(systemctl_bin)
    path = _unit_path(config_home)
    if path.is_symlink():
        raise ServiceError("hutch.service is a symbolic link; it was not followed or changed")
    if not path.exists():
        return False
    if not path.is_file():
        raise ServiceError("hutch.service exists but is not a regular file")
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ServiceError("could not read the existing hutch.service") from exc
    if not contents.startswith(MANAGED_MARKER + "\n"):
        raise ServiceError("hutch.service is not marked as managed by Hutch; it was left unchanged")
    _systemctl(binary, ["disable", "--now", UNIT_NAME], systemctl_runner)
    try:
        path.unlink()
    except OSError as exc:
        raise ServiceError("Hutch was stopped, but its unit file could not be removed") from exc
    _systemctl(binary, ["daemon-reload"], systemctl_runner)
    return True
