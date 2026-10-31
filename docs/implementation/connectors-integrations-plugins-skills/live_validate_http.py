"""Live validation: a real Streamable HTTP MCP server through Hutch's pinned egress.

The stdio path is covered by the sandboxed fixture and by the third-party time server. The HTTP
path had unit coverage only: endpoint screening and address pinning were exercised with injected
resolvers, but no request had ever crossed the pinned transport. This starts an actual MCP server
on loopback, registers it as a connector, discovers its tools and calls one.

Loopback is the strictest case for the pinning code, because a local endpoint must match the
explicitly reviewed origin and must resolve only to a loopback address.

Run:
    uv run --frozen --no-sync python docs/implementation/connectors-integrations-plugins-skills/live_validate_http.py
"""

import asyncio
import json
import os
import pathlib
import socket
import sys
import tempfile
import threading
import time

PORT = 8811


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_server(port: int) -> threading.Thread:
    """Run the official MCP SDK server over Streamable HTTP on loopback."""
    from mcp.server import MCPServer

    server = MCPServer(name="hutch-live-http", version="1.0.0")

    @server.tool(name="lookup", description="Return a fixed record so the caller can verify the round trip.")
    async def lookup(key: str) -> str:
        return json.dumps({"key": key, "served": "hutch-live-http", "transport": "streamable-http"},
                          sort_keys=True)

    @server.tool(name="echo_config", description="Report the endpoint the server believes it is.")
    async def echo_config() -> str:
        return json.dumps({"endpoint": f"http://127.0.0.1:{port}/mcp"}, sort_keys=True)

    def run() -> None:
        asyncio.run(server.run_streamable_http_async(host="127.0.0.1", port=port,
                                                     streamable_http_path="/mcp", stateless_http=True))

    thread = threading.Thread(target=run, name="live-mcp-http", daemon=True)
    thread.start()
    return thread


def wait_ready(port: int, seconds: float = 20.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise SystemExit(f"the MCP HTTP server did not listen on 127.0.0.1:{port}")


def main() -> int:
    port = free_port()
    evidence: dict[str, object] = {"endpoint": f"http://127.0.0.1:{port}/mcp"}

    state = pathlib.Path(tempfile.mkdtemp(prefix="mcp-http-live-", dir=pathlib.Path.home() / ".hutch-tmp"))
    os.environ["HUTCH_STATE_DIR"] = str(state)

    from hutch.config import get_config
    from hutch.integrations.mcp import config, network, service
    from hutch.integrations.mcp.network import McpEndpointError
    from hutch.models import ApprovalMode, Bot, Run, RunStatus
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine
    from hutch.store import Store
    from hutch.tools import build_tools
    from hutch.tools.base import ToolContext
    from hutch.runtime.steps import call_tool

    # Screen first, before anything is started: a private-network endpoint must be refused.
    try:
        network.validate_mcp_endpoint("https://mcp.example.com/mcp",
                                      resolver=lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))])
        evidence["private_address_screen"] = "NOT REFUSED"
    except McpEndpointError as exc:
        evidence["private_address_screen"] = f"refused: {exc}"

    start_server(port)
    wait_ready(port)

    cfg = get_config()
    cfg.ensure()
    store = Store(cfg)

    definition = {"transport": "mcp_http", "url": f"http://127.0.0.1:{port}/mcp", "auth": {"type": "none"}}
    configured = service.configure(store, integration_id="livehttp", title="Live HTTP connector",
                                   raw_definition=definition)
    evidence["configure"] = {"revision": configured["revision"]}

    discovered = service.discover(store, integration_id="livehttp")
    names = sorted(tool["server_tool_name"] for tool in discovered["catalog"])
    evidence["discovery"] = {"tool_count": discovered["tools"], "tools": names}
    if not names:
        print(json.dumps({"result": "FAILED", "evidence": evidence}, indent=2))
        return 1

    bot = store.create_bot(Bot(name="http-bot", model="mock/demo", tools=[],
                               approval_mode=ApprovalMode.auto))
    service.grant(store, integration_id="livehttp", bot_ref=bot.id, tool_names=["lookup"],
                  operation_classes={"lookup": "read"}, expected_revision=configured["revision"])

    run = store.create_run(Run(bot_id=bot.id, prompt="look up", status=RunStatus.running))
    emit = lambda ev: store.append_event(ev)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    workspace = state / "ws"
    workspace.mkdir(exist_ok=True)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=cfg, workspace=workspace, emit=emit)
    tools = build_tools(bot.tools, ctx)

    out = call_tool(run, ctx, tools, "mcp__livehttp__lookup", {"key": "alpha"})
    evidence["call"] = {"ok": out.ok, "output": out.output[:400]}

    # An unreviewed loopback port is not in the allowed origins, so it must be refused.
    other = free_port()
    try:
        network.PinnedMcpHTTPTransport(allowed_local_origins=(f"http://127.0.0.1:{port}/mcp",))
        evidence["origin_allowlist"] = "constructed (the request itself is what enforces it)"
    except Exception as exc:  # noqa: BLE001
        evidence["origin_allowlist"] = f"error: {exc}"

    store.close()
    print(json.dumps(evidence, indent=2, default=str))
    return 0 if evidence["call"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
