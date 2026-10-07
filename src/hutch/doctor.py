"""`hutch doctor` (SR-14): runtimes, context size, database, permissions and the service - each check says what it
found and how to fix it, so the output is a to-do list, not a diagnosis you have to interpret.

Exit status is non-zero if any check FAILS (warnings do not fail it), so it can gate a script or CI.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import __version__
from .models import RunStatus

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"


@dataclass
class Check:
    id: str
    title: str
    status: str
    detail: str
    fix: str = ""


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def run_doctor(config: Any, store: Any, hw: Any = None, deep: bool = False, online: bool = False,
               systemctl: Optional[Any] = None) -> list[Check]:
    from .connections import ConnectionBook
    from .context import run_selfcheck
    from .hardware import probe
    from .health import runtime_health
    from .modelview import installed
    from .presets import load_presets
    from .fit import estimate_fit
    hw = hw or probe()
    out: list[Check] = []
    add = lambda *a, **k: out.append(Check(*a, **k))

    # ---- environment
    ok_py = sys.version_info >= (3, 11)
    add("python", "Python", OK if ok_py else FAIL, f"{sys.version.split()[0]} (hutch {__version__})",
        "" if ok_py else "hutch needs Python 3.11 or newer")

    # ---- database
    db = config.db_path
    try:
        with store._lock:
            integrity = store._db.execute("PRAGMA integrity_check").fetchone()[0]
            mode = store._db.execute("PRAGMA journal_mode").fetchone()[0]
        size = db.stat().st_size / 1e6
        status = OK if integrity == "ok" and mode == "wal" else FAIL
        add("database", "Database", status, f"schema v{store.schema_version}, integrity {integrity}, journal {mode}, "
                                          f"{size:.1f} MB", "" if status == OK else
            "restore from a backup (`hutch.db.bak-v*` next to it) or export what you need and re-init")
    except sqlite3.Error as exc:
        add("database", "Database", FAIL, str(exc), "restore from a backup next to the database")
    backups = sorted(config.state_dir.glob("hutch.db.bak-v*"))
    if backups:
        add("backups", "Upgrade backups", INFO, f"{len(backups)} pre-upgrade backup(s): {', '.join(b.name for b in backups)}",
            "delete them once you are happy with the upgrade")

    # ---- permissions
    loose = []
    for path in (config.state_dir, config.state_dir / "keys"):
        if path.exists() and _mode(path) & 0o077:
            loose.append(f"{path} is {oct(_mode(path))}")
    keys = config.state_dir / "keys"
    if keys.exists():
        loose += [f"{k} is {oct(_mode(k))}" for k in keys.glob("*.key") if _mode(k) & 0o077]
    add("permissions", "Permissions", WARN if loose else OK,
        "; ".join(loose) if loose else "state directory and key files are private",
        f"chmod 700 {config.state_dir}; chmod 600 {keys}/*.key" if loose else "")

    # ---- scheduler / service
    orphans = [r for r in store.active_runs() if r.owner and r.status is not RunStatus.pending
               and not _pid_alive(r.owner)]
    add("orphans", "Interrupted runs", WARN if orphans else OK,
        f"{len(orphans)} run(s) belong to a process that exited" if orphans else "no orphaned runs",
        "they are marked failed automatically the next time `hutch serve` or `hutch daemon` ticks" if orphans else "")
    svc = _service_status(systemctl)
    add("service", "Background service", svc[0], svc[1], svc[2])

    # ---- runtimes
    bots = store.list_bots()
    wanted = {b.model.partition("/")[0].replace("llama.cpp", "llamacpp") for b in bots}
    for h in runtime_health(config, store, hw, [b.model for b in bots]):
        in_use = h.name.replace(".", "") in wanted or h.kind != "local-runtime"
        # a stopped runtime is a failure only when a bot depends on it; otherwise it is just worth knowing
        status = {"healthy": OK, "idle": INFO, "degraded": WARN, "needs_setup": WARN,
                  "down": FAIL if in_use else WARN}[h.state]
        add(f"runtime:{h.name}", f"Runtime: {h.name}", status, h.detail or h.state, h.fix)

    # ---- local models
    ollama_up = any(r.name == "ollama" and r.reachable for r in hw.runtimes)
    local_bots = [b for b in bots if b.model.startswith("ollama/")]
    if local_bots and ollama_up:
        from .runtime.ladder import get_provider
        prov = get_provider("ollama", None)
        have = installed(prov)
        presets = load_presets(config.state_dir / "presets.json")
        for b in local_bots:
            tag = b.model.split("/", 1)[1]
            meta = have.get(tag)
            if meta is None:
                add(f"model:{b.name}", f"Model for {b.name}", FAIL, f"{tag} is not installed", f"ollama pull {tag}")
                continue
            want = b.num_ctx or (presets[b.preset].want_ctx if b.preset in presets else 16384)
            fit = estimate_fit(meta, hw, want)
            add(f"model:{b.name}", f"Model for {b.name}",
                {"fits": OK, "tight": WARN, "wont_fit": FAIL}[fit.status],
                f"{tag}: {fit.label} - {fit.reason}; context it will actually get: {fit.effective_ctx:,} tokens",
                "" if fit.status == "fits" else "choose a smaller model or lower num_ctx on the Models page")
            if len(b.tools) > 8:
                add(f"tools:{b.name}", f"Tools for {b.name}", WARN,
                    f"{len(b.tools)} tools: small models get unreliable past about 8",
                    "remove tools this bot does not need")
            if deep and b.selfcheck:
                sc = run_selfcheck(prov, tag, fit.effective_ctx or 8192)
                add(f"selfcheck:{b.name}", f"Context self-check for {b.name}", OK if sc.ok else FAIL, sc.detail,
                    "" if sc.ok else "the model drops the start of long prompts at this window: lower num_ctx, "
                                     "raise the runtime's context limit, or pick another model")
    elif local_bots:
        add("models", "Local models", WARN, "bots use local models but Ollama is not reachable",
            "start it with `ollama serve`, or give those bots a fallback model")

    # ---- connections
    book = ConnectionBook(config.state_dir)
    for name, c in book.configured().items():
        if book.key(name) is None:
            add(f"connection:{name}", f"Connection: {name}", FAIL, "no API key",
                f"set ${c.api_key_env} or run `hutch connections set-key {name}`")
            continue
        ack = book.ack_status(store, name)
        if ack in ("required", "stale"):
            add(f"connection:{name}", f"Connection: {name}", FAIL, "terms not acknowledged",
                f"hutch connections ack {name}")
            continue
        if online:
            from .providers.connection import check_connection
            res = check_connection(book, name)
            add(f"connection:{name}", f"Connection: {name}", OK if res.ok else FAIL, res.detail,
                "" if res.ok else f"hutch connections test {name}")
        else:
            add(f"connection:{name}", f"Connection: {name}", OK, "key present, terms acknowledged "
                                                               "(add --online to authenticate; spends no tokens)")
    for e in book.errors:
        add("connections-file", "Connections file", FAIL, e, f"fix or delete {book.path}")

    # ---- bot hygiene
    for b in bots:
        if b.approval_mode.value == "auto" and "shell" in b.tools:
            add(f"auto-shell:{b.name}", f"{b.name}: auto approvals with a shell", WARN,
                "medium-risk shell commands run without asking (secrets, sudo and exfiltration stay blocked)",
                "use ask mode, or add per-command rules")
        lim = b.limits
        if not b.model.startswith(("mock/", "ollama/")) and not (lim.max_cost_usd or lim.daily_cost_cap_usd) \
                and (b.model.split("/", 1)[0] in ("anthropic", "openai")):
            add(f"nocap:{b.name}", f"{b.name}: hosted model with no spend cap", WARN,
                f"{b.model} can spend without a ceiling", "set max_cost_usd and daily_cost_cap_usd on the bot")

    # ---- optional tools
    try:
        import playwright  # noqa: F401
        add("browser", "Browser tool", INFO, "playwright installed (`playwright install chromium` if a bot uses browser)")
    except ImportError:
        add("browser", "Browser tool", INFO, "playwright not installed (only needed for bots with the browser tool)",
            "pip install 'hutch[browser]'")
    add("bwrap", "Bubblewrap", INFO, "available" if shutil.which("bwrap") else "not found (optional sandbox, planned)")
    return out


def _pid_alive(pid: str) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True


def _service_status(systemctl: Optional[Any]) -> tuple[str, str, str]:
    """(status, detail, fix) for the user-level systemd service (UI-14)."""
    run = systemctl or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=5))
    if systemctl is None and not shutil.which("systemctl"):
        return INFO, "systemd not available on this system", ""
    try:
        # `is-active` answers "inactive" for a unit that does not exist; LoadState tells the two apart
        loaded = ((run(["systemctl", "--user", "show", "-p", "LoadState", "--value", "hutch.service"]).stdout or "")
                  .strip())
        state = (run(["systemctl", "--user", "is-active", "hutch.service"]).stdout or "").strip()
    except Exception as exc:
        return INFO, f"could not query systemd ({exc})", ""
    if loaded == "not-found":
        state = "not-installed"
    if state == "active":
        return OK, "hutch.service is active", ""
    if state in ("inactive", "failed"):
        return WARN, f"hutch.service is {state}", "systemctl --user restart hutch   (logs: journalctl --user -u hutch)"
    return INFO, "not installed: schedules only run while `hutch serve` or `hutch daemon` is running",\
        "hutch service install"


def worst(checks: list[Check]) -> str:
    return FAIL if any(c.status == FAIL for c in checks) else WARN if any(c.status == WARN for c in checks) else OK
