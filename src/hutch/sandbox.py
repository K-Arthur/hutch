"""OS-level containment for what a bot runs (ADR-0006).

A command parser, a redirected HOME and a path jail in the file tools are *policy*: they check what Hutch's own tools are asked to
do. They do not stop `python script.py` from reading `~/.ssh`, so they are not a boundary. This module is one: it runs a command
inside bubblewrap with

* a filesystem that is a minimal read-only system tree plus **only** the run's workspace writable (no home, no other project, no
  other user data, a private /tmp),
* **no shell network** (a new empty network namespace; loopback is not even up); public-page access uses Hutch's checked
  ``web_fetch`` tool rather than joining the host network,
* its own PID namespace, so when the sandbox ends **everything inside ends**, including a process that double-forked and
  ``setsid``'d to escape its process group (the case ``procguard`` cannot reach from outside),
* a clean environment and resource limits (CPU time, file size, open files, no core dumps).

It fails CLOSED: a bot that requires the sandbox on a host that cannot provide it does not run the command at all; it is told why.

Scope and limits, stated plainly:
* Linux with unprivileged user namespaces and ``bwrap`` (verified on this host: bubblewrap 0.13). macOS/Windows: unavailable.
* It contains the shell tool and (ADR-0007) external runtimes. The in-process file tools stay path-jailed. The browser is separate.
* It does not hide the kernel, the CPU, or other users' processes' existence beyond the PID namespace, and bubblewrap is not a
  hardened VM: a kernel namespace escape is out of scope. Read-only system paths are visible (``/usr``): they hold no user secrets.
* Additional read-only mounts are limited to explicitly configured ``Policy.extra_ro`` paths. The old ambient
  ``HUTCH_SANDBOX_RO`` environment variable is ignored so a service environment cannot silently widen a bot's view.
"""

from __future__ import annotations

import os
import ipaddress
import json
import socket
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: read-only host paths a normal command needs. (/proc and /dev are fresh mounts, /tmp is a private tmpfs.)
_ETC_FILES = ("passwd", "group", "nsswitch.conf", "os-release", "ld.so.cache", "ld.so.conf", "localtime", "hosts")
_ETC_DIRS = ("ld.so.conf.d", "alternatives")
_NET_ETC = ("resolv.conf", "ssl", "ca-certificates", "pki")
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"

_STATUS: Optional["Status"] = None
_OFFLINE_STATUS: Optional["OfflineStatus"] = None


@dataclass(frozen=True)
class Status:
    ok: bool
    backend: str = "bubblewrap+systemd-user-scope"
    version: str = ""
    reason: str = ""


@dataclass(frozen=True)
class OfflineStatus:
    ok: bool
    backend: str = "bubblewrap-network-pid-namespaces/unix-model-broker"
    reason: str = ""


@dataclass(frozen=True)
class Policy:
    workspace: Path
    network: bool = False
    extra_ro: tuple[str, ...] = ()
    cpu_seconds: int = 3600
    fsize_mb: int = 1024
    nofile: int = 1024
    memory_mb: int = 4096
    processes: int = 256


def binary() -> str:
    return os.environ.get("HUTCH_SANDBOX_BIN") or "bwrap"


def _probe() -> Status:
    exe = shutil.which(binary())
    if not exe:
        return Status(False, reason=f"'{binary()}' (bubblewrap) is not installed; install it (e.g. `apt install bubblewrap`)")
    prlimit = shutil.which("prlimit")
    if not prlimit:
        return Status(False, reason="'prlimit' (util-linux) is not installed; strict mode needs it for resource limits")
    systemd_run = shutil.which("systemd-run")
    if not systemd_run:
        return Status(False, reason="'systemd-run' is not installed; strict mode needs a delegated cgroup for memory and process limits")
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        argv = [exe, "--unshare-all", "--ro-bind", "/usr", "/usr", "--proc", "/proc", "--dev", "/dev", *_layout(),
                "/usr/bin/true" if Path("/usr/bin/true").exists() else "/bin/true"]
        r = subprocess.run([systemd_run, "--user", "--scope", "--quiet", "--property=MemoryMax=512M",
                            "--property=TasksMax=64", "--", prlimit, "--as=536870912", "--nofile=128",
                            "--core=0", "--", *argv], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return Status(False, reason=f"could not run bubblewrap: {exc}")
    if r.returncode != 0:
        why = (r.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        hint = " (unprivileged user namespaces may be disabled: sysctl kernel.unprivileged_userns_clone / user.max_user_namespaces)"
        return Status(False, version=ver, reason=f"bubblewrap cannot create a sandbox here: {why[0]}{hint}")
    return Status(True, version=ver)


def status(refresh: bool = False) -> Status:
    """Can this host sandbox? Probed once (a real trial sandbox), cached for the process."""
    global _STATUS
    if _STATUS is None or refresh:
        _STATUS = _probe()
    return _STATUS


def reset_cache() -> None:
    global _STATUS, _OFFLINE_STATUS
    _STATUS = None
    _OFFLINE_STATUS = None


def offline_scope_prefix() -> list[str]:
    """Start the worker in fresh Linux namespaces; only mounted Unix sockets cross network isolation."""
    exe = shutil.which(binary())
    if not exe:
        raise RuntimeError(f"'{binary()}' (bubblewrap) is not installed; Strict Offline needs a network namespace")
    return [exe, "--die-with-parent", "--unshare-all"]


def offline_worker_environment(source: dict[str, str], state_dir: str, lease_seconds: float,
                               broker_dir: str) -> dict[str, str]:
    """Environment passed through ``env -i`` to an Offline worker.

    Keep only interpreter/runtime essentials and Hutch's state coordinates.
    In particular, provider keys, proxy settings, custom provider endpoints,
    cloud credentials, and user service-bus access are not exposed to the run.
    Saved connection definitions and key files are also masked by read-only
    mounts in the worker's filesystem namespace.
    """
    # All ambient values remain excluded except two supervisor-owned coordinates
    # that the parent Engine sets explicitly before constructing the sandbox.
    # Nested delegation needs the same global admission limit inside workers.
    if source.get("HUTCH_EXECUTOR", "process") != "process":
        raise ValueError("Strict Offline workers require the supervised process executor")
    try:
        max_concurrent = int(source.get("HUTCH_MAX_CONCURRENT", "2"))
    except (TypeError, ValueError):
        raise ValueError("invalid supervised global concurrency limit") from None
    if not 1 <= max_concurrent <= 128:
        raise ValueError("supervised global concurrency limit must be between 1 and 128")
    source_root = str(Path(__file__).resolve().parents[1])
    # Run the real interpreter binary rather than the venv's symlink: the
    # latter can point through a uv-managed alias outside the mounted tree.
    # Mount the venv's installed packages explicitly so the base interpreter
    # gets the same dependencies without executing venv activation hooks.
    package_dir = sysconfig.get_paths().get("purelib", "")
    python_path = [source_root]
    if package_dir and Path(package_dir).is_dir() and not Path(package_dir).is_relative_to("/usr"):
        python_path.append(package_dir)
    return {
        "PATH": DEFAULT_PATH, "HOME": "/tmp/hutch-home", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "PYTHONPATH": os.pathsep.join(python_path), "PYTHONUNBUFFERED": "1", "VIRTUAL_ENV": sys.prefix,
        "HUTCH_STATE_DIR": state_dir, "HUTCH_LEASE_SECONDS": str(lease_seconds),
        "HUTCH_EXECUTOR": "process", "HUTCH_MAX_CONCURRENT": str(max_concurrent),
        "HUTCH_OFFLINE_BROKER_DIR": "/run/hutch-offline", "HUTCH_OFFLINE_RUN": "1",
        "TMPDIR": "/tmp", "TERM": "dumb",
    }


def offline_worker_argv(command: list[str], source: dict[str, str], state_dir: str,
                        lease_seconds: float, broker_dir: str, *, memory_mb: int = 4096,
                        processes: int = 256) -> list[str]:
    """Launch a credential-redacted worker with only its scoped model sockets mounted."""
    from .offline import BROKER_MOUNT

    systemd_run, prlimit = shutil.which("systemd-run"), shutil.which("prlimit")
    if not systemd_run or not prlimit:
        raise RuntimeError("Strict Offline needs systemd-run and prlimit for worker resource limits")
    source_root = Path(__file__).resolve().parents[1]
    prefix = Path(sys.prefix).resolve()
    # Preserve the host-visible symlink path: venv interpreter links may point
    # through it even though Path.resolve() names a versioned target directory.
    base_prefix = Path(sys.base_prefix)
    argv = offline_scope_prefix()
    argv += ["--ro-bind", "/usr", "/usr", *_layout(), *_etc(network=False)]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run",
             ]
    made_dirs: set[str] = {"/", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/lib32", "/etc", "/tmp", "/run"}

    def prepare_target(target: Path) -> None:
        if target.is_relative_to(Path("/usr")) or target.is_relative_to(Path("/etc")):
            return
        for directory in reversed((target, *target.parents)):
            value = str(directory)
            if value not in made_dirs:
                argv.extend(["--dir", value])
                made_dirs.add(value)

    state_path = Path(state_dir).resolve()
    state_path.mkdir(parents=True, exist_ok=True, mode=0o700)
    connections_path = state_path / "connections.json"
    try:
        connection_stat = connections_path.lstat()
    except FileNotFoundError:
        try:
            descriptor = os.open(connections_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            connection_stat = connections_path.lstat()
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as config_file:
                config_file.write('{"connections": {}}\n')
            connection_stat = connections_path.lstat()
        if not stat.S_ISREG(connection_stat.st_mode):
            raise RuntimeError("Strict offline cannot safely mask a non-regular connections file")
    else:
        if not stat.S_ISREG(connection_stat.st_mode):
            raise RuntimeError("Strict offline cannot safely mask a non-regular connections file")
    keys_path = state_path / "keys"
    if keys_path.is_symlink() or (keys_path.exists() and not keys_path.is_dir()):
        raise RuntimeError("Strict offline cannot safely mask the connection-key directory")
    keys_path.mkdir(mode=0o700, exist_ok=True)
    redaction_dir = Path(broker_dir) / "state-redaction"
    redaction_dir.mkdir(mode=0o700)
    os.chmod(redaction_dir, 0o700)
    safe_connections = redaction_dir / "connections.json"
    safe_connections.write_text('{"connections": {}}\n', encoding="utf-8")
    os.chmod(safe_connections, 0o400)
    empty_keys = redaction_dir / "keys"
    empty_keys.mkdir(mode=0o500)
    os.chmod(empty_keys, 0o500)
    prepare_target(state_path)
    argv += ["--bind", str(state_path), str(state_path)]
    argv += ["--ro-bind", str(safe_connections), str(connections_path),
             "--ro-bind", str(empty_keys), str(keys_path)]
    if prefix.exists() and not source_root.is_relative_to(prefix):
        prepare_target(prefix)
        argv += ["--ro-bind", str(prefix), str(prefix)]
    if base_prefix.exists() and base_prefix != Path("/usr") and not base_prefix.is_relative_to(Path("/usr")):
        prepare_target(base_prefix)
        argv += ["--ro-bind", str(base_prefix), str(base_prefix)]
    if source_root.exists():
        prepare_target(source_root)
        argv += ["--ro-bind", str(source_root), str(source_root)]
    argv += ["--dir", BROKER_MOUNT, "--ro-bind", broker_dir, BROKER_MOUNT,
             "--dir", "/tmp/hutch-home", "--chdir", "/tmp/hutch-home", "--clearenv"]
    for key, value in sorted(offline_worker_environment(source, state_dir, lease_seconds, broker_dir).items()):
        argv += ["--setenv", key, value]
    worker_command = list(command)
    if worker_command and Path(worker_command[0]).resolve() == Path(sys.executable).resolve():
        worker_command[0] = str(Path(sys.executable).resolve())
    argv += ["--", *worker_command]
    return [systemd_run, "--user", "--scope", "--quiet", f"--property=MemoryMax={memory_mb}M",
            f"--property=TasksMax={processes}", "--", prlimit, f"--as={memory_mb * 1024 * 1024}",
            "--nofile=1024", "--core=0", "--", *argv]


def _local_non_loopback_addresses() -> dict[int, list[str]]:
    """List local IPv4/IPv6 interface addresses without making a network request."""
    ip = shutil.which("ip")
    if not ip:
        return {socket.AF_INET: [], socket.AF_INET6: []}
    try:
        result = subprocess.run([ip, "-o", "addr", "show", "scope", "global"],
                                capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return {socket.AF_INET: [], socket.AF_INET6: []}
    if result.returncode != 0:
        return {socket.AF_INET: [], socket.AF_INET6: []}
    addresses: dict[int, list[str]] = {socket.AF_INET: [], socket.AF_INET6: []}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[2] != "inet":
            continue
        try:
            address = ipaddress.ip_address(parts[3].split("/", 1)[0])
        except ValueError:
            continue
        if not address.is_loopback and not address.is_unspecified:
            family = socket.AF_INET if isinstance(address, ipaddress.IPv4Address) else socket.AF_INET6
            addresses[family].append(str(address))
    return {family: list(dict.fromkeys(items)) for family, items in addresses.items()}


def _probe_offline_egress() -> OfflineStatus:
    """Verify network/PID isolation and that a mounted broker UDS stays reachable.

    All TCP listeners are on this machine and the Unix-socket broker exchanges
    only a two-byte marker. No public or remote destination is contacted.
    """
    if not sys_platform_linux():
        return OfflineStatus(False, reason="strict offline egress isolation is only implemented for Linux")
    if not shutil.which(binary()):
        return OfflineStatus(False, reason=f"'{binary()}' (bubblewrap) is not installed")
    resource_status = status()
    if not resource_status.ok:
        return OfflineStatus(False, reason=f"worker resource limits are unavailable: {resource_status.reason}")
    addresses = _local_non_loopback_addresses()
    if not any(addresses.values()):
        return OfflineStatus(False, reason="no local non-loopback interface is available for the network-namespace check")

    listeners: list[socket.socket] = []
    tcp_targets: list[tuple[int, str, int]] = []
    broker_listener: socket.socket | None = None
    broker_thread: threading.Thread | None = None
    try:
        loopbacks = {socket.AF_INET: "127.0.0.1", socket.AF_INET6: "::1"}
        for family, host_addresses in addresses.items():
            if not host_addresses:
                continue
            loop_host = loopbacks[family]
            loop_listener = socket.socket(family, socket.SOCK_STREAM)
            loop_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                loop_listener.bind((loop_host, 0))
                loop_listener.listen(1)
            except OSError as exc:
                loop_listener.close()
                return OfflineStatus(False, reason=f"could not open a loopback TCP test listener: {exc}")
            port = loop_listener.getsockname()[1]
            host_listener = None
            for address in host_addresses:
                candidate = socket.socket(family, socket.SOCK_STREAM)
                candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    target = (address, port) if family == socket.AF_INET else (address, port, 0, 0)
                    candidate.bind(target)
                    candidate.listen(1)
                    host_listener = candidate
                    break
                except OSError:
                    candidate.close()
            if host_listener is None:
                loop_listener.close()
                return OfflineStatus(False, reason=f"could not open a local {family} interface TCP test listener")
            listeners.extend((loop_listener, host_listener))
            tcp_targets.extend(((family, loop_host, port),
                               (family, host_listener.getsockname()[0], port)))
        if not tcp_targets:
            return OfflineStatus(False, reason="no local TCP address family could be tested")
        with tempfile.TemporaryDirectory(prefix="hutch-probe-", dir="/tmp") as broker_dir:
            broker_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            broker_path = str(Path(broker_dir) / "probe.sock")
            broker_listener.bind(broker_path)
            broker_listener.listen(1)

            def answer_probe() -> None:
                if broker_listener is None:
                    return
                broker_listener.settimeout(5)
                try:
                    conn, _ = broker_listener.accept()
                    with conn:
                        if conn.recv(2) == b"hi":
                            conn.sendall(b"ok")
                except OSError:
                    pass

            broker_thread = threading.Thread(target=answer_probe, name="hutch-offline-probe", daemon=True)
            broker_thread.start()
            code = "\n".join((
                "import json,os,socket,sys",
                "u=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); u.settimeout(2)",
                "u.connect(sys.argv[1]); u.sendall(b'hi'); ok=u.recv(2)==b'ok'; u.close()",
                "blocked=True",
                "for family,host,port in json.loads(sys.argv[2]):",
                "    s=socket.socket(family,socket.SOCK_STREAM); s.settimeout(.5)",
                "    blocked=blocked and s.connect_ex((host,port) if family==socket.AF_INET else (host,port,0,0))!=0",
                "    s.close()",
                "pids={int(p) for p in os.listdir('/proc') if p.isdigit()}",
                "sys.exit(0 if ok and blocked and os.getpid()==2 and pids<={1,2} else 7)",
            ))
            bwrap = offline_scope_prefix()
            bwrap += ["--ro-bind", "/usr", "/usr", *_layout(), *_etc(network=False),
                      "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run",
                      "--dir", "/run/hutch-offline", "--ro-bind", broker_dir, "/run/hutch-offline",
                      "--", shutil.which("python3") or sys.executable, "-c", code,
                      "/run/hutch-offline/probe.sock", json.dumps(tcp_targets)]
            isolated = subprocess.run(bwrap, capture_output=True, text=True, timeout=12, check=False)
            broker_thread.join(timeout=1)
            if isolated.returncode != 0:
                detail = (isolated.stderr or isolated.stdout or f"child exited {isolated.returncode}").strip()[-240:]
                families = ", ".join("IPv4" if family == socket.AF_INET else "IPv6" for family, _, _ in tcp_targets)
                return OfflineStatus(False, reason=f"network/PID namespace failed its local {families}/Unix-socket checks: {detail}")
        return OfflineStatus(True)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        return OfflineStatus(False, reason=f"could not verify strict offline egress isolation: {exc}")
    finally:
        for listener in listeners:
            listener.close()
        if broker_listener is not None:
            broker_listener.close()
        if broker_thread is not None and broker_thread.is_alive():
            broker_thread.join(timeout=1)


def sys_platform_linux() -> bool:
    return os.name == "posix" and os.uname().sysname == "Linux"


def offline_egress_status(refresh: bool = False) -> OfflineStatus:
    """Return a cached host test for egress filtering; unsupported means Offline must fail closed."""
    global _OFFLINE_STATUS
    if _OFFLINE_STATUS is None or refresh:
        _OFFLINE_STATUS = _probe_offline_egress()
    return _OFFLINE_STATUS


def global_override() -> str:
    """``HUTCH_SANDBOX=off`` turns containment off for everything (the documented rollback); logged on every run."""
    v = (os.environ.get("HUTCH_SANDBOX") or "").strip().lower()
    return v if v in ("off", "strict") else ""


def mode_for(bot) -> str:
    """"strict" or "off" for this bot: the global override wins, else the bot's own setting."""
    return global_override() or ("strict" if getattr(bot, "sandbox", "off") == "strict" else "off")


def default_mode() -> str:
    """New bots always request containment; unsupported hosts report an actionable error at execution time."""
    return "strict"


_SENSITIVE_COMPONENTS = {
    ".ssh", ".aws", ".azure", ".gnupg", ".kube", ".config", ".docker", ".netrc", ".npmrc",
    ".pypirc", ".env", ".env.local", ".env.production", "credentials", "secrets",
}


def _extra_readonly_mounts(paths: tuple[str, ...]) -> list[str]:
    """Build explicit read-only mounts and refuse common credential directories/files."""
    out: list[str] = []
    for raw in paths:
        source = Path(raw).expanduser()
        if not source.exists():
            raise ValueError(f"read-only mount does not exist: {raw}")
        resolved = source.resolve(strict=True)
        if any(part.lower() in _SENSITIVE_COMPONENTS for part in resolved.parts):
            raise ValueError(f"read-only mount may expose credentials or secrets: {raw}")
        if source.is_file() and source.name.lower().startswith(".env"):
            raise ValueError(f"read-only mount may expose credentials or secrets: {raw}")
        # Selecting an ancestor is not permission to expose secrets beneath it.
        if resolved.is_dir():
            count = 0
            def cannot_inspect(exc):
                raise ValueError(f"could not inspect the read-only mount safely: {exc}")
            for root, dirs, files in os.walk(resolved, followlinks=False, onerror=cannot_inspect):
                for name in dirs + files:
                    count += 1
                    if count > 10_000:
                        raise ValueError("read-only mount inspection exceeds 10000 entries; choose a narrower folder")
                    if name.lower() in _SENSITIVE_COMPONENTS or name.lower().startswith(".env"):
                        raise ValueError(f"read-only mount may expose credentials or secrets beneath: {raw}")
                    child = Path(root) / name
                    if child.is_symlink() and not child.resolve(strict=True).is_relative_to(resolved):
                        raise ValueError(f"read-only mount contains a symlink outside its granted folder: {raw}")
        out += ["--ro-bind", str(resolved), str(resolved)]
    return out


# --------------------------------------------------------------------------- building the command


def _layout() -> list[str]:
    """Recreate the host's top-level system directories read-only (symlinks stay symlinks: /bin -> usr/bin on merged-/usr hosts)."""
    out: list[str] = []
    for name in ("bin", "sbin", "lib", "lib64", "lib32"):
        p = Path("/") / name
        if p.is_symlink():
            out += ["--symlink", os.readlink(p), str(p)]
        elif p.is_dir():
            out += ["--ro-bind", str(p), str(p)]
    return out


def _etc(network: bool) -> list[str]:
    out: list[str] = []
    for name in _ETC_FILES + _ETC_DIRS + (_NET_ETC if network else ()):
        p = Path("/etc") / name
        if p.exists():
            out += ["--ro-bind", str(p.resolve() if p.is_symlink() and name != "localtime" else p), str(p)]
    if network and Path("/etc/resolv.conf").is_symlink():      # systemd-resolved: the target lives under /run
        target = Path("/etc/resolv.conf").resolve()
        if target.exists():
            out += ["--ro-bind", str(target), str(target)]
    return out


def shell_argv(command: str, policy: Policy, shell: str = "/bin/bash") -> list[str]:
    """The full argv that runs ``bash -c command`` inside the sandbox, with limits applied to the sandbox process."""
    if policy.network:
        raise ValueError("shell network access is unavailable in strict mode; use Hutch's checked web_fetch tool")
    ws = str(policy.workspace.resolve())
    argv = [binary(), "--die-with-parent", "--new-session", "--unshare-all"]
    argv += ["--ro-bind", "/usr", "/usr", *_layout(), *_etc(policy.network)]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run",
             "--bind", ws, ws]
    # Mount after private /tmp and the writable workspace: earlier mounts were
    # hidden or widened by their parent mount, contradicting the declared grant.
    for raw in policy.extra_ro:
        source = Path(raw).expanduser().resolve(strict=True)
        if Path(ws).is_relative_to(source):
            raise ValueError("read-only mount cannot cover the writable workspace; choose a narrower folder")
    argv += _extra_readonly_mounts(policy.extra_ro)
    argv += ["--chdir", ws,
             "--clearenv", "--setenv", "PATH", DEFAULT_PATH, "--setenv", "HOME", ws, "--setenv", "LANG", "C.UTF-8",
             "--setenv", "TERM", "dumb", "--setenv", "TMPDIR", "/tmp",
             "--", shell, "-c", command]
    limits = [f"--cpu={policy.cpu_seconds}", f"--fsize={policy.fsize_mb * 1024 * 1024}",
              f"--nofile={policy.nofile}", f"--as={policy.memory_mb * 1024 * 1024}", "--core=0"]
    prlimit = shutil.which("prlimit")
    systemd_run = shutil.which("systemd-run")
    if not prlimit:
        raise RuntimeError("strict sandbox requires prlimit for CPU, memory, process and file limits")
    if os.environ.get("HUTCH_OFFLINE_RUN") == "1":
        # Offline's outer worker scope already owns the cgroup memory/task cap;
        # reaching the host user bus here would let systemd start a process
        # outside the worker's isolated network namespace.
        return [prlimit, *limits, "--", *argv]
    if not systemd_run:
        raise RuntimeError("strict sandbox requires prlimit and systemd-run for CPU, memory, process and file limits")
    return [systemd_run, "--user", "--scope", "--quiet",
            f"--property=MemoryMax={policy.memory_mb}M", f"--property=TasksMax={policy.processes}",
            "--", prlimit, *limits, "--", *argv]


def policy_for(bot, workspace: Path) -> Policy:
    kw = {}
    if os.environ.get("HUTCH_SANDBOX_FSIZE_MB"):
        kw["fsize_mb"] = int(os.environ["HUTCH_SANDBOX_FSIZE_MB"])
    return Policy(workspace=workspace, network=bool(getattr(bot, "shell_network", False)), **kw)


def describe(bot) -> str:
    """A one-line statement of the containment a bot's commands get, for transcripts and the UI."""
    m = mode_for(bot)
    if m == "off":
        return "no OS containment: commands run as your user"
    return "OS sandbox: workspace writable only, no shell network, private /tmp, own PID namespace, bounded CPU/memory/processes/files"
