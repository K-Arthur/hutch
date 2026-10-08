"""OS-level containment for what a bot runs (ADR-0006).

A command parser, a redirected HOME and a path jail in the file tools are *policy*: they check what Hutch's own tools are asked to
do. They do not stop `python script.py` from reading `~/.ssh`, so they are not a boundary. This module is one: it runs a command
inside bubblewrap with

* a filesystem that is a minimal read-only system tree plus **only** the run's workspace writable (no home, no other project, no
  other user data, a private /tmp),
* **no network** unless the bot was explicitly granted it (a new empty network namespace; loopback is not even up),
* its own PID namespace, so when the sandbox ends **everything inside ends**, including a process that double-forked and
  ``setsid``'d to escape its process group (the case ``procguard`` cannot reach from outside),
* a clean environment and resource limits (CPU time, file size, open files, no core dumps).

It fails CLOSED: a bot that requires the sandbox on a host that cannot provide it does not run the command at all; it is told why.

Scope and limits, stated plainly:
* Linux with unprivileged user namespaces and ``bwrap`` (verified on this host: bubblewrap 0.13). macOS/Windows: unavailable.
* It contains the shell tool and (ADR-0007) external runtimes. The in-process file tools stay path-jailed. The browser is separate.
* It does not hide the kernel, the CPU, or other users' processes' existence beyond the PID namespace, and bubblewrap is not a
  hardened VM: a kernel namespace escape is out of scope. Read-only system paths are visible (``/usr``): they hold no user secrets.
* Toolchains installed outside ``/usr`` (pyenv, nvm, ~/.local) are invisible inside; extend with ``HUTCH_SANDBOX_RO`` (colon list).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

#: read-only host paths a normal command needs. (/proc and /dev are fresh mounts, /tmp is a private tmpfs.)
_ETC_FILES = ("passwd", "group", "nsswitch.conf", "os-release", "ld.so.cache", "ld.so.conf", "localtime", "hosts")
_ETC_DIRS = ("ld.so.conf.d", "alternatives")
_NET_ETC = ("resolv.conf", "ssl", "ca-certificates", "pki")
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"

_STATUS: Optional["Status"] = None


@dataclass(frozen=True)
class Status:
    ok: bool
    backend: str = "bubblewrap"
    version: str = ""
    reason: str = ""


@dataclass(frozen=True)
class Policy:
    workspace: Path
    network: bool = False
    extra_ro: tuple[str, ...] = ()
    cpu_seconds: int = 3600
    fsize_mb: int = 1024
    nofile: int = 1024


def binary() -> str:
    return os.environ.get("HUTCH_SANDBOX_BIN") or "bwrap"


def _probe() -> Status:
    exe = shutil.which(binary())
    if not exe:
        return Status(False, reason=f"'{binary()}' (bubblewrap) is not installed; install it (e.g. `apt install bubblewrap`)")
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        argv = [exe, "--unshare-all", "--ro-bind", "/usr", "/usr", "--proc", "/proc", "--dev", "/dev", *_layout(),
                "/usr/bin/true" if Path("/usr/bin/true").exists() else "/bin/true"]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
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
    global _STATUS
    _STATUS = None


def global_override() -> str:
    """``HUTCH_SANDBOX=off`` turns containment off for everything (the documented rollback); logged on every run."""
    v = (os.environ.get("HUTCH_SANDBOX") or "").strip().lower()
    return v if v in ("off", "strict") else ""


def mode_for(bot) -> str:
    """"strict" or "off" for this bot: the global override wins, else the bot's own setting."""
    return global_override() or ("strict" if getattr(bot, "sandbox", "off") == "strict" else "off")


def default_mode() -> str:
    """What a NEWLY created bot gets: strict where the host can do it, otherwise off (and `hutch doctor` says so)."""
    return "strict" if status().ok else "off"


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
    ws = str(policy.workspace.resolve())
    argv = [binary(), "--die-with-parent", "--new-session", "--unshare-all"]
    if policy.network:
        argv.append("--share-net")
    argv += ["--ro-bind", "/usr", "/usr", *_layout(), *_etc(policy.network)]
    for extra in (*policy.extra_ro, *[p for p in os.environ.get("HUTCH_SANDBOX_RO", "").split(":") if p]):
        if Path(extra).exists():
            argv += ["--ro-bind", extra, extra]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run",
             "--bind", ws, ws, "--chdir", ws,
             "--clearenv", "--setenv", "PATH", DEFAULT_PATH, "--setenv", "HOME", ws, "--setenv", "LANG", "C.UTF-8",
             "--setenv", "TERM", "dumb", "--setenv", "TMPDIR", "/tmp",
             "--", shell, "-c", command]
    limits = [f"--cpu={policy.cpu_seconds}", f"--fsize={policy.fsize_mb * 1024 * 1024}", f"--nofile={policy.nofile}", "--core=0"]
    prlimit = shutil.which("prlimit")
    return ([prlimit, *limits, "--", *argv] if prlimit else argv)


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
    net = "network allowed" if getattr(bot, "shell_network", False) else "no network"
    return f"OS sandbox: workspace writable only, {net}, private /tmp, own PID namespace"
