"""Live validation: a real third-party MCP server through Hutch's contained launcher.

This is not a fixture. It installs the official `mcp-server-time` from PyPI into its own virtual
environment, registers it through the real service layer, discovers its tools, grants one to an
assistant, and calls it. The child runs inside Hutch's bubblewrap containment.

Run:
    uv run --frozen --no-sync python docs/implementation/connectors-integrations-plugins-skills/live_validate_third_party.py
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

SERVER_ROOT = pathlib.Path.home() / "mcp-connectors" / "time"
VENV = SERVER_ROOT / "venv"


def site_packages() -> pathlib.Path:
    """The server's package tree. Read from the venv, not from the interpreter running this script."""
    lib = VENV / "lib"
    for child in sorted(lib.glob("python3*")):
        candidate = child / "site-packages"
        if candidate.is_dir():
            return candidate
    raise SystemExit(f"no site-packages in {lib}")


def ensure_server(skip_install: bool) -> pathlib.Path:
    """Install the official time server into an isolated environment if it is not there."""
    try:
        site = site_packages()
    except SystemExit:
        site = None
    if site is not None and (site / "mcp_server_time").exists():
        return site
    if skip_install:
        raise SystemExit(f"the third-party server is not installed at {SERVER_ROOT}")
    SERVER_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(VENV, ignore_errors=True)
    subprocess.run(["/usr/bin/python3", "-m", "venv", str(VENV)], check=True)
    subprocess.run([str(VENV / "bin" / "pip"), "install", "--quiet", "--disable-pip-version-check",
                    "mcp-server-time==2025.9.25", "mcp>=1.9,<2"], check=True)
    return site_packages()


def main() -> int:
    site = ensure_server(skip_install="--no-install" in sys.argv)
    evidence: dict[str, object] = {}

    state = pathlib.Path(tempfile.mkdtemp(prefix="mcp-live-", dir=pathlib.Path.home() / ".hutch-tmp"))
    os.environ["HUTCH_STATE_DIR"] = str(state)

    from hutch.config import get_config
    from hutch.integrations.mcp import config, persistence, service
    from hutch.models import Bot, Run, RunStatus, ApprovalMode
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine
    from hutch.tools.base import ToolContext
    from hutch.runtime.steps import call_tool
    from hutch.tools import build_tools

    cfg = get_config()
    cfg.ensure()
    from hutch.store import Store
    store = Store(cfg)

    # The server is third-party code from PyPI. It is mounted read-only and its interpreter is
    # the system python; PYTHONPATH points at the package tree inside the reviewed mount.
    definition = {
        "transport": "mcp_stdio",
        "command": "/usr/bin/python3",
        "args": ["-m", "mcp_server_time", "--local-timezone", "UTC"],
        "read_only_paths": [str(site)],
        "env": {"PYTHONPATH": str(site)},
    }
    state_text = state / "server-install.txt"
    state_text.write_text(
        f"package: mcp-server-time==2025.9.25 from PyPI\nsite-packages: {site}\n"
        f"python: {sys.version.split()[0]}\n")
    evidence["server"] = json.loads(json.dumps({"definition": definition}))

    configured = service.configure(store, integration_id="time", title="Time (official MCP server)",
                                   raw_definition=definition)
    evidence["configure"] = {"revision": configured["revision"], "invalidated": configured["invalidated"]}

    discovered = service.discover(store, integration_id="time")
    names = sorted(tool["server_tool_name"] for tool in discovered["catalog"])
    evidence["discovery"] = {
        "tool_count": discovered["tools"],
        "tools": names,
        "supported": {t["server_tool_name"]: t["supported"] for t in discovered["catalog"]},
        "schemas": {t["server_tool_name"]: t["description"][:120] for t in discovered["catalog"]},
    }
    if not names:
        print(json.dumps({"result": "FAILED", "evidence": evidence}, indent=2))
        return 1

    bot = store.create_bot(Bot(name="timekeeper", model="mock/demo", tools=[],
                               approval_mode=ApprovalMode.auto))
    read_only = "get_current_time" if "get_current_time" in names else names[0]
    service.grant(store, integration_id="time", bot_ref=bot.id, tool_names=[read_only],
                  operation_classes={read_only: "read"}, expected_revision=configured["revision"])

    run = store.create_run(Run(bot_id=bot.id, prompt="what time is it", status=RunStatus.running))
    emit = lambda ev: store.append_event(ev)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    workspace = state / "ws"
    workspace.mkdir(exist_ok=True)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=cfg, workspace=workspace, emit=emit)

    tools = build_tools(bot.tools, ctx)
    canonical = f"mcp__time__{read_only}"
    evidence["build_tools"] = {"connector_tools": sorted(n for n in tools if n.startswith("mcp__"))}

    out = call_tool(run, ctx, tools, canonical, {"timezone": "Europe/London"})
    evidence["call"] = {"ok": out.ok, "output": out.output[:600],
                        "data": {k: str(v)[:120] for k, v in out.data.items()}}

    # An ungranted tool must not be reachable: it is absent from the built tool set entirely.
    other = next((n for n in names if n != read_only), "")
    if other:
        absent = call_tool(run, ctx, tools, f"mcp__time__{other}", {"timezone": "UTC"})
        evidence["ungranted_tool"] = {"ok": absent.ok, "output": absent.output[:200]}
        # A granted tool called with arguments its own schema rejects is refused before any request
        # reaches the server, using the schema the server published rather than a Hutch guess.
        wrong = call_tool(run, ctx, tools, canonical, {"nonsense": 1})
        evidence["schema_refusal"] = {"ok": wrong.ok, "output": wrong.output[:300]}

    store.close()
    evidence["state_dir"] = str(state)
    print(json.dumps(evidence, indent=2, default=str))
    return 0 if evidence["call"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
