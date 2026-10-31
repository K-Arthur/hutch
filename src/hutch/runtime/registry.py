"""Runtime registry: which execution engines exist, what each one may do, and what it may not.

A runtime is not a provider. This registry describes the boundary of each execution engine so the UI and
audit can state, for example, that only the built-in runtime reserves provider usage before a call, that
the managed OpenCode runtime keeps its own tools outside Hutch's shell sandbox, and that a documented
CLI executor is not enabled merely because its binary exists.

Registering a runtime never enables it. get_runtime in runtime/__init__.py keeps its existing behaviour
for persisted Bot documents; this module is descriptive and is used by server/API surfaces and tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

STATUSES = ("implemented", "experimental", "documented", "blocked")


@dataclass(frozen=True)
class RuntimeDescriptor:
    id: str
    title: str
    status: str
    process_model: str
    credential_boundary: str
    permission_boundary: str
    usage_reservation: bool
    cancellation: str
    session: str
    notes: str = ""
    cli_binary: str = ""

    @property
    def enabled(self) -> bool:
        """Only implemented/experimental runtimes can be selected by a Bot."""
        return self.status in ("implemented", "experimental")


#: The ordered registry. Built-in is the only runtime that reserves provider usage before a model call.
RUNTIMES: tuple[RuntimeDescriptor, ...] = (
    RuntimeDescriptor(
        id="builtin", title="Hutch built-in runtime", status="implemented",
        process_model="In-process agent loop in the Hutch worker; owned process group per run.",
        credential_boundary="Uses only the selected model route's own connection credential; ambient keys are exact-official-host only.",
        permission_boundary="Hutch policy engine, approvals, path jail and usage reservations apply to every step.",
        usage_reservation=True, cancellation="Stop closes the active response and is independent of the model loop.",
        session="Durable run events and transcript; the run is the unit of context.",
        notes="Default runtime for every Bot that does not select an external engine."),
    RuntimeDescriptor(
        id="opencode", title="OpenCode managed runtime", status="experimental",
        process_model="Hutch launches and supervises a private opencode serve process.",
        credential_boundary="OpenCode keeps its own sign-in and provider credentials; Hutch does not import them into its stores.",
        permission_boundary="Each OpenCode tool permission is brokered once/reject through Hutch; approved tools run with the user's OS authority outside Hutch's shell sandbox.",
        usage_reservation=False, cancellation="Hutch stops the run and supervises its owned child process; provider-side use may already have occurred.",
        session="Durable OpenCode session history is read for completion; the live event stream is not trusted as the record.",
        notes="Requires an installed OpenCode CLI v2 and explicit login. External tool authority is a deliberate boundary, not sandboxed.",
        cli_binary="opencode"),
    RuntimeDescriptor(
        id="pi", title="Pi RPC executor", status="blocked",
        process_model="No process is launched: the runtime fails closed before creation.",
        credential_boundary="Pi owns direct provider traffic; Hutch cannot scope its credentials.",
        permission_boundary="No per-action approval hook and no shared usage reservation.",
        usage_reservation=False, cancellation="Not implemented for the process.",
        session="Not available.",
        notes="Kept registered only so a persisted Bot that selected it can be moved to the built-in runtime.",
        cli_binary="pi"),
    RuntimeDescriptor(
        id="claude-code", title="Claude Code CLI", status="documented",
        process_model="Interactive vendor CLI; not a Hutch executor.",
        credential_boundary="Its own sign-in or API key; Hutch does not import or proxy the credential.",
        permission_boundary="The CLI's own permission model, outside Hutch approvals and budgets.",
        usage_reservation=False, cancellation="Vendor-managed; no Hutch cancellation contract.",
        session="Vendor-managed.",
        notes="Documented only. A future executor needs an approval/budget/lifecycle contract first.",
        cli_binary="claude"),
    RuntimeDescriptor(
        id="codex", title="Codex CLI", status="documented",
        process_model="Interactive vendor CLI; not a Hutch executor.",
        credential_boundary="API-key-first or vendor-managed sign-in; not an arbitrary API credential.",
        permission_boundary="Vendor permission model, outside Hutch approvals and budgets.",
        usage_reservation=False, cancellation="Vendor-managed.",
        session="Vendor-managed.",
        notes="Documented only. Codex subscription access tokens are limited to Business/Enterprise per vendor docs.",
        cli_binary="codex"),
    RuntimeDescriptor(
        id="gemini-cli", title="Gemini CLI", status="documented",
        process_model="Interactive vendor CLI; not a Hutch executor.",
        credential_boundary="Consumer authentication changed in 2026; paid API/Vertex keys and Code Assist entitlement remain documented routes.",
        permission_boundary="Vendor permission model, outside Hutch approvals and budgets.",
        usage_reservation=False, cancellation="Vendor-managed.",
        session="Vendor-managed.",
        notes="Documented only; no retired consumer OAuth flow is supported.",
        cli_binary="gemini"),
)

#: Runtimes a Bot may select in this build. Kept in sync with get_runtime's outcomes.
ENABLED_RUNTIME_IDS = ("builtin", "opencode")


def descriptors() -> tuple[RuntimeDescriptor, ...]:
    return RUNTIMES


def descriptor(runtime_id: str) -> Optional[RuntimeDescriptor]:
    return next((item for item in RUNTIMES if item.id == runtime_id), None)


def enabled() -> tuple[RuntimeDescriptor, ...]:
    return tuple(item for item in RUNTIMES if item.id in ENABLED_RUNTIME_IDS)


def _version_runner(binary: str, timeout: float = 2.0) -> dict:
    """Run only --version, with a bounded timeout and no inherited provider environment.

    Detection must never read a credential store, pass a secret or accept a network prompt. A binary that
    cannot report a version is reported as installed without a version, which is honest and sufficient.
    """
    try:
        completed = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=timeout,
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
                 "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            stdin=subprocess.DEVNULL, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"installed": True, "version": "", "error": type(exc).__name__}
    text = (completed.stdout or completed.stderr or "").strip().splitlines()
    version = text[0][:120] if text else ""
    return {"installed": True, "version": version, "error": ""}


def detect_installed_clis(*, finder: Callable[[str], Optional[str]] = shutil.which,
                          runner: Callable[[str], dict] = _version_runner) -> dict[str, dict]:
    """Installed CLI binaries, detected without reading any credential or configuration file."""
    out: dict[str, dict] = {}
    for item in RUNTIMES:
        if not item.cli_binary:
            continue
        path = finder(item.cli_binary)
        out[item.id] = {"binary": item.cli_binary, "installed": bool(path)}
        if path:
            out[item.id].update(runner(path))
    return out


def registry_json(*, detect: bool = True) -> dict:
    """Serializable registry for the API. Paths are omitted; only installed/version are exposed."""
    installed = detect_installed_clis() if detect else {}
    return {
        "enabled": list(ENABLED_RUNTIME_IDS),
        "runtimes": [
            {"id": item.id, "title": item.title, "status": item.status, "enabled": item.enabled,
             "process_model": item.process_model, "credential_boundary": item.credential_boundary,
             "permission_boundary": item.permission_boundary,
             "usage_reservation": item.usage_reservation, "cancellation": item.cancellation,
             "session": item.session, "notes": item.notes,
             "cli": installed.get(item.id)}
            for item in RUNTIMES
        ],
    }
