"""MCP client construction and the contained local-server launcher (ADR-0017 §4.2, §8.2).

stdlib ``stdio`` is not a sandbox. A local MCP server is third-party code, so Hutch runs it the
way it runs a shell command: inside the same bubblewrap containment, with no ambient
credentials, no host network, no writable host path, one writable directory (the run workspace),
and resource limits enforced by ``prlimit``/``systemd-run`` with verification that the process is
gone afterwards.

The server process is created per operation and ended before returning. That is deliberately
simpler than a long-lived pool: a pooled child outliving its run is precisely the orphan class
``procguard`` exists to prevent, and a per-operation process makes "revoked means stopped"
true by construction.
"""

from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from ... import sandbox
from .config import McpConfigurationError, resolve_environment, validate_stdio_definition
from .network import PinnedMcpHTTPTransport, is_local_host, validate_mcp_endpoint

#: Wall-clock ceiling for one operation, whatever the server reports as progress.
OPERATION_DEADLINE_SECONDS = 60
#: Per-request read timeout handed to the SDK.
READ_TIMEOUT_SECONDS = 20
#: Discovery gets its own, slightly larger budget for pagination.
DISCOVERY_DEADLINE_SECONDS = 45


def stdio_launch_argv(definition: dict[str, Any], workspace: str | Path) -> list[str]:
    """Return a resource-limited, no-network argv for one contained MCP server process."""
    config = validate_stdio_definition(definition, expected=definition)
    status = sandbox.status()
    if not status.ok:
        raise McpConfigurationError(f"local MCP processes need Hutch's Linux sandbox: {status.reason}")
    if os.environ.get("HUTCH_OFFLINE_RUN") == "1":
        raise McpConfigurationError("MCP server processes are not available inside Strict Offline runs")
    try:
        writable = Path(workspace).resolve(strict=True)
    except (OSError, RuntimeError):
        raise McpConfigurationError("the assistant's run workspace is unavailable") from None
    if not writable.is_dir():
        raise McpConfigurationError("the assistant's run workspace is not a directory")
    mounts = [Path(item) for item in config["read_only_paths"]]
    if any(writable == mount or writable.is_relative_to(mount) or mount.is_relative_to(writable)
           for mount in mounts):
        raise McpConfigurationError("read-only server paths cannot overlap the assistant's writable run workspace")

    bwrap = shutil.which(sandbox.binary())
    prlimit = shutil.which("prlimit")
    systemd_run = shutil.which("systemd-run")
    if not bwrap or not prlimit or not systemd_run:
        raise McpConfigurationError("the configured Linux process-containment tools are unavailable")
    inner = [bwrap, "--die-with-parent", "--new-session", "--unshare-all",
             "--ro-bind", "/usr", "/usr", *sandbox._layout(), *sandbox._etc(network=False),
             "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run"]
    known = {"/", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/lib32", "/etc", "/tmp", "/run"}
    for path in mounts:
        inner += _parents_for_mount(path, known)
        inner += ["--ro-bind", str(path), str(path)]
    inner += _parents_for_mount(Path("/workspace"), known)
    # ``--clearenv`` plus an explicit allowlist: the child inherits no credential from Hutch's
    # own environment. Only references the owner reviewed are passed, resolved here.
    inner += ["--bind", str(writable), "/workspace", "--dir", "/tmp/hutch-home",
              "--chdir", "/workspace", "--clearenv",
              "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
              "--setenv", "HOME", "/tmp/hutch-home",
              "--setenv", "LANG", "C.UTF-8", "--setenv", "LC_ALL", "C.UTF-8",
              "--setenv", "TERM", "dumb", "--setenv", "TMPDIR", "/tmp"]
    for name, value in resolve_environment(config).items():
        inner += ["--setenv", name, value]
    inner += ["--", config["command"], *config["args"]]
    limits = ["--cpu=120", "--fsize=67108864", "--nofile=128", "--as=536870912", "--core=0"]
    return [systemd_run, "--user", "--scope", "--quiet",
            "--property=MemoryMax=512M", "--property=TasksMax=32", "--",
            prlimit, *limits, "--", *inner]


def _parents_for_mount(path: Path, known: set[str]) -> list[str]:
    additions: list[str] = []
    for parent in reversed(path.parents):
        name = str(parent)
        if name == "/" or name in known:
            continue
        additions.extend(("--dir", name))
        known.add(name)
    if str(path) not in known:
        additions.extend(("--dir", str(path)))
        known.add(str(path))
    return additions


def _supervisor_environment() -> dict[str, str]:
    """``systemd-run --user`` needs its session variables; nothing else is forwarded."""
    out = {}
    for name in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR"):
        value = os.environ.get(name, "")
        if value and len(value) <= 4096 and not any(ord(char) < 32 for char in value):
            out[name] = value
    if set(out) != {"DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR"}:
        raise McpConfigurationError("a local systemd user session is required to launch a contained MCP process")
    return out


@asynccontextmanager
async def open_client(definition: dict[str, Any], workspace: Optional[str | Path] = None):
    """Yield an initialized MCP ``Client`` for a reviewed definition.

    ``mode="auto"`` lets the pinned SDK negotiate the modern discovery shape or fall back to the
    documented legacy initialize handshake. Hutch never follows ``latest``: the SDK version is
    pinned in ``pyproject.toml`` and the negotiation result is recorded with the catalog.
    """
    from mcp import Client

    transport = (definition.get("transport") or "").value if hasattr(definition.get("transport"), "value") else definition.get("transport")
    if transport == "mcp_stdio":
        from mcp.client.stdio import StdioServerParameters, stdio_client
        if workspace is None:
            raise McpConfigurationError("a local MCP server needs a run workspace")
        argv = stdio_launch_argv(definition, workspace)
        parameters = StdioServerParameters(command=argv[0], args=argv[1:],
                                           env=_supervisor_environment(), cwd="/")
        # Server stderr is untrusted text; it never becomes run output.
        with open(os.devnull, "w", encoding="utf-8") as diagnostics:
            async with Client(stdio_client(parameters, errlog=diagnostics), mode="auto",
                              read_timeout_seconds=READ_TIMEOUT_SECONDS) as client:
                yield client
        return
    if transport == "mcp_http":
        from mcp.client.streamable_http import streamable_http_client
        import httpx2

        url = validate_mcp_endpoint(str(definition.get("url") or ""))
        headers: dict[str, str] = {}
        auth = definition.get("auth") or {"type": "none"}
        if auth.get("type") == "bearer":
            reference = str(auth.get("from_env") or "")
            token = os.environ.get(reference, "")
            if not token:
                raise McpConfigurationError(
                    f"the credential variable {reference} is not set; set it before connecting")
            headers["Authorization"] = f"Bearer {token}"
        local = is_local_host((url.split("://", 1)[-1].split("/", 1)[0]).split(":")[0])
        allowed = (url,) if local else ()
        async with httpx2.AsyncClient(
                transport=PinnedMcpHTTPTransport(allowed_local_origins=allowed),
                trust_env=False, follow_redirects=False,
                timeout=httpx2.Timeout(READ_TIMEOUT_SECONDS)) as http:
            async with Client(
                    streamable_http_client(url, http_client=http, max_sse_event_size=1_048_576),
                    mode="auto", read_timeout_seconds=READ_TIMEOUT_SECONDS) as client:
                yield client
        return
    raise McpConfigurationError("unsupported MCP transport")


__all__ = ["DISCOVERY_DEADLINE_SECONDS", "OPERATION_DEADLINE_SECONDS", "READ_TIMEOUT_SECONDS",
           "open_client", "stdio_launch_argv"]
