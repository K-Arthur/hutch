"""Install Hutch as a user-level Linux systemd service, and verify it is really running.

The generated unit only starts the loopback dashboard. Remote supervision is
intentionally not copied from a shell environment or enabled by this command.

Process state is not workflow readiness: ``systemctl is-active`` can say
``active`` while Hutch is still opening its database, or while an unrelated
process owns the port. Every start path therefore completes with a readiness
handshake against ``/api/health`` that must answer for the same state directory
and the process systemd reports as the unit's main PID.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .instance import instance_id

UNIT_NAME = "hutch.service"
MANAGED_MARKER = "# Managed by Hutch CLI."


class ServiceError(RuntimeError):
    """The local systemd service could not be installed or managed safely."""


@dataclass(frozen=True)
class ServiceInstall:
    path: Path
    started: bool
    ready: bool = True
    detail: str = ""
    instance: Optional[dict] = None


@dataclass(frozen=True)
class ServiceProbe:
    """Result of one readiness handshake against the loopback dashboard."""

    reachable: bool
    ready: bool
    detail: str = ""
    instance: Optional[dict] = None
    http_status: Optional[int] = None


@dataclass(frozen=True)
class ServiceStatus:
    state: str
    installed: bool
    active: bool
    port: Optional[int] = None
    unit_path: Optional[Path] = None
    ready: Optional[bool] = None       # None = not probed
    detail: str = ""
    instance: Optional[dict] = None
    linger: str = "unknown"            # enabled | disabled | unavailable | unknown
    main_pid: Optional[int] = None


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


# --------------------------------------------------------------- readiness

def _no_proxy_opener() -> urllib.request.OpenerDirector:
    """Loopback probe opener: no environment proxies, no redirects, short timeout."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
            return None

    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def readiness_probe(port: int, *, state_dir: Path | str | None = None,
                    expected_pid: int | None = None, timeout: float = 2.0,
                    opener: urllib.request.OpenerDirector | None = None) -> ServiceProbe:
    """One handshake against `http://127.0.0.1:<port>/api/health`.

    Readiness means: an HTTP 200 JSON body with ``status: ok``, not in restore
    hold, the same state-directory fingerprint (when one is given), and — when
    systemd reports a main PID — that exact process. Anything else is reported
    with the reason and never treated as ready.
    """
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return ServiceProbe(False, False, "the service port is not usable")
    url = f"http://127.0.0.1:{port}/api/health"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    drive = opener or _no_proxy_opener()
    expected_id = instance_id(state_dir) if state_dir is not None else None
    try:
        with drive.open(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            raw = response.read(64 * 1024)
    except urllib.error.HTTPError as exc:
        return ServiceProbe(True, False, f"Hutch answered HTTP {exc.code} on port {port}", None, exc.code)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return ServiceProbe(False, False, f"no Hutch answered on 127.0.0.1:{port} ({reason})")
    try:
        body = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return ServiceProbe(True, False, f"the process on port {port} did not answer with Hutch's health JSON",
                            None, status)
    if not isinstance(body, dict) or body.get("status") != "ok":
        return ServiceProbe(True, False, f"the process on port {port} reported status {body.get('status')!r}",
                            None, status)
    info = body.get("instance") if isinstance(body.get("instance"), dict) else None
    if body.get("execution_held"):
        return ServiceProbe(True, False, "Hutch is holding execution for restore review", info, status)
    if expected_id is not None:
        actual = str((info or {}).get("id") or "")
        if actual != expected_id:
            return ServiceProbe(True, False,
                                "a different Hutch instance owns this port (state directory mismatch)",
                                info, status)
    if expected_pid is not None and info is not None:
        try:
            actual_pid = int(info.get("pid"))
        except (TypeError, ValueError):
            actual_pid = None
        if actual_pid is not None and actual_pid != expected_pid:
            return ServiceProbe(True, False,
                                f"port {port} is answered by process {actual_pid}, not the unit's main PID {expected_pid}",
                                info, status)
    return ServiceProbe(True, True, "ready", info, status)


def wait_for_ready(port: int, *, state_dir: Path | str | None = None,
                   expected_pid: int | None = None, timeout: float = 15.0,
                   interval: float = 0.25, probe: Callable[..., ServiceProbe] | None = None) -> ServiceProbe:
    """Poll the readiness handshake until it passes or ``timeout`` elapses."""
    import time

    deadline = time.monotonic() + max(0.0, timeout)
    last = ServiceProbe(False, False, "readiness was not checked")
    check = probe or readiness_probe
    first = True
    while first or time.monotonic() < deadline:
        first = False
        remaining = max(0.2, deadline - time.monotonic())
        last = check(port, state_dir=state_dir, expected_pid=expected_pid,
                     timeout=min(2.0, max(0.2, remaining)))
        if last.ready:
            return last
        if timeout <= 0:
            break
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
    return last


def _main_pid(binary: str, runner: Callable[..., Any] | None) -> int | None:
    """The unit's main PID, or None when systemd has not reported one yet."""
    try:
        result = _systemctl(binary, ["show", "-p", "MainPID", "--value", UNIT_NAME], runner)
    except ServiceError:
        return None
    raw = (getattr(result, "stdout", "") or "").strip()
    try:
        pid = int(raw)
    except ValueError:
        return None
    return pid if pid > 0 else None


def linger_state(*, systemctl_runner: Callable[..., Any] | None = None,
                 loginctl_bin: str | None = None, user: str | None = None) -> str:
    """Whether this user's services survive logout (`loginctl enable-linger`).

    Reported, never enabled automatically: lingering changes login semantics and
    requires an explicit, authorized choice.
    """
    if sys.platform != "linux":
        return "unavailable"
    binary = loginctl_bin or shutil.which("loginctl")
    if not binary:
        return "unavailable"
    target_user = user or os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if not target_user:
        return "unknown"
    run = systemctl_runner if systemctl_runner is not None else subprocess.run
    try:
        result = run([binary, "show-user", target_user, "-p", "Linger"], capture_output=True,
                     text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    if result.returncode != 0:
        return "unavailable"
    raw = (getattr(result, "stdout", "") or "").strip().lower()
    if raw in ("linger=yes", "yes"):
        return "enabled"
    if raw in ("linger=no", "no"):
        return "disabled"
    return "unknown"


# ------------------------------------------------------------------ install

def install_user_service(
    state_dir: Path,
    *,
    python_executable: str | None = None,
    config_home: Path | None = None,
    port: int = 8787,
    systemctl_bin: str | None = None,
    systemctl_runner: Callable[..., Any] | None = None,
    ready_timeout: float = 15.0,
    probe: Callable[..., ServiceProbe] | None = None,
) -> ServiceInstall:
    """Write and start a user unit, refusing symlinks and unrelated existing files.

    The install is only reported as started after the readiness handshake passes
    for this state directory and the unit's main process. A failed handshake
    leaves the unit installed and reports the exact reason instead of claiming
    success.
    """
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

    status = wait_for_ready(port, state_dir=Path(state_dir).expanduser().absolute(),
                            expected_pid=_main_pid(binary, systemctl_runner),
                            timeout=ready_timeout, probe=probe)
    if not status.ready:
        raise ServiceError(
            "unit file was written and systemd reports hutch.service active, but the readiness check "
            f"did not confirm the expected instance: {status.detail}. "
            "Inspect `hutch service status` and `journalctl --user -u hutch.service`; the unit was left in place."
        )
    return ServiceInstall(path=path, started=True, ready=True, detail=status.detail, instance=status.instance)


def restart_user_service(*, systemctl_bin: str | None = None,
                         systemctl_runner: Callable[..., Any] | None = None) -> None:
    """Restart the installed unit and confirm systemd reports it active again."""
    binary = _systemd_binary(systemctl_bin)
    path = _unit_path(None)
    if not path.is_file() or path.is_symlink():
        raise ServiceError("hutch.service is not installed as a regular file; run `hutch service install` first")
    _systemctl(binary, ["restart", UNIT_NAME], systemctl_runner)
    active = _systemctl(binary, ["is-active", UNIT_NAME], systemctl_runner)
    if (getattr(active, "stdout", "") or "").strip() != "active":
        raise ServiceError("systemd did not report hutch.service active after the restart")


def stop_user_service(*, systemctl_bin: str | None = None,
                      systemctl_runner: Callable[..., Any] | None = None) -> None:
    """Stop the unit explicitly.

    An explicit stop is a person's decision: ``Restart=on-failure`` does not
    relaunch a unit that systemd was asked to stop. This only stops the
    service; the unit file and all Hutch data stay in place.
    """
    binary = _systemd_binary(systemctl_bin)
    _systemctl(binary, ["stop", UNIT_NAME], systemctl_runner)
    active = _systemctl(binary, ["is-active", UNIT_NAME], systemctl_runner)
    state = (getattr(active, "stdout", "") or "").strip() or "unknown"
    if state not in ("inactive", "failed", "deactivating"):
        raise ServiceError(f"systemd did not report hutch.service stopped (state: {state})")


def set_linger(enabled: bool, *, systemctl_runner: Callable[..., Any] | None = None,
               loginctl_bin: str | None = None, user: str | None = None) -> str:
    """Enable or disable login lingering after an explicit owner choice; verify the new state.

    Lingering changes login semantics: with it enabled, the user manager (and
    therefore Hutch) starts at boot and keeps running after logout. It is never
    changed as a side effect of another command.
    """
    if sys.platform != "linux":
        raise ServiceError("login lingering is a Linux/systemd concept")
    binary = loginctl_bin or shutil.which("loginctl")
    if not binary:
        raise ServiceError("loginctl is not installed; lingering cannot be changed here")
    target_user = user or os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if not target_user:
        raise ServiceError("cannot determine the current user for loginctl")
    run = systemctl_runner if systemctl_runner is not None else subprocess.run
    action = "enable-linger" if enabled else "disable-linger"
    try:
        result = run([binary, action, target_user], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ServiceError(f"loginctl {action} could not be run") from exc
    if result.returncode != 0:
        detail = " ".join(((result.stderr or result.stdout) or "").split())[:200]
        raise ServiceError(f"loginctl {action} failed" + (f": {detail}" if detail else ""))
    state = linger_state(systemctl_runner=run, loginctl_bin=binary, user=target_user)
    expected = "enabled" if enabled else "disabled"
    if state != expected:
        raise ServiceError(f"loginctl reported lingering as {state!r} after the change")
    return state


def user_service_status(*, systemctl_bin: str | None = None,
                        config_home: Path | None = None,
                        systemctl_runner: Callable[..., Any] | None = None,
                        state_dir: Path | None = None,
                        probe: bool = False,
                        probe_runner: Callable[..., ServiceProbe] | None = None,
                        loginctl_bin: str | None = None) -> ServiceStatus:
    """Read systemd's view of the unit, the configured port, and (optionally) readiness."""
    binary = _systemd_binary(systemctl_bin)
    loaded = _systemctl(binary, ["show", "-p", "LoadState", "--value", UNIT_NAME], systemctl_runner)
    if (getattr(loaded, "stdout", "") or "").strip() == "not-found":
        return ServiceStatus("not installed", installed=False, active=False,
                             linger=linger_state(systemctl_runner=systemctl_runner, loginctl_bin=loginctl_bin))
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
    linger = linger_state(systemctl_runner=systemctl_runner, loginctl_bin=loginctl_bin)
    ready: Optional[bool] = None
    detail = ""
    instance: Optional[dict] = None
    main_pid = _main_pid(binary, systemctl_runner)
    if probe and state == "active" and port is not None:
        outcome = (probe_runner or readiness_probe)(port, state_dir=state_dir, expected_pid=main_pid, timeout=2.0)
        ready, detail, instance = outcome.ready, outcome.detail, outcome.instance
    return ServiceStatus(state, installed=True, active=state == "active", port=port, unit_path=path,
                         ready=ready, detail=detail, instance=instance, linger=linger, main_pid=main_pid)


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
