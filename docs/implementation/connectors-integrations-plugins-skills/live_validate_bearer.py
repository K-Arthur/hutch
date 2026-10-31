"""Live validation: bearer authentication and cross-origin refusal, against real servers.

Two branches of the remote connector path had only unit coverage:

* a `bearer` credential: the token is read from an environment variable at connect time and sent
  in an `Authorization` header. Nothing had ever checked that a server receives it, or that a
  missing variable fails closed with a message naming it.
* a cross-origin redirect: the pinned transport screens every request against the reviewed origin
  list, so a server that redirects to another port on the same machine must not be followed.

Both are exercised here with real HTTP servers on loopback. Loopback is the strictest case for the
origin rule, because a local endpoint must match the reviewed origin exactly. What this does *not*
show is a third-party service accepting a token: no such endpoint and credential were available,
and the record says so.

Run:
    uv run --frozen --no-sync python docs/implementation/connectors-integrations-plugins-skills/live_validate_bearer.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pathlib
import socket
import tempfile
import threading
import time

TOKEN = "live-validation-token-7f3a91"
TOKEN_ENV = "HUTCH_LIVE_MCP_TOKEN"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_ready(port: int, seconds: float = 20.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise SystemExit(f"no listener on 127.0.0.1:{port}")


class _BearerGuard:
    """ASGI wrapper that requires the exact bearer token and records what it saw.

    The token is recorded as a digest and a length, never as text: this log is evidence, and
    evidence should not contain the credential it proves was accepted.
    """

    def __init__(self, app, *, expected: str, seen: list[dict]):
        self.app = app
        self.expected = expected
        self.seen = seen

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1")
                   for key, value in scope.get("headers", [])}
        presented = headers.get("authorization", "")
        ok = presented == f"Bearer {self.expected}"
        self.seen.append({"path": scope.get("path", ""), "authorized": ok,
                          "presented_length": len(presented),
                          "presented_sha256": hashlib.sha256(presented.encode()).hexdigest()[:16]})
        if ok:
            await self.app(scope, receive, send)
            return
        body = b'{"error":"unauthorized"}'
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def start_authenticated_server(port: int, seen: list[dict]) -> threading.Thread:
    from mcp.server import MCPServer

    server = MCPServer(name="hutch-live-bearer", version="1.0.0")

    @server.tool(name="whoami", description="Report what the server received.")
    async def whoami() -> str:
        return json.dumps({"authenticated": True, "server": "hutch-live-bearer"})

    app = _BearerGuard(server.streamable_http_app(streamable_http_path="/mcp"),
                       expected=TOKEN, seen=seen)

    def run() -> None:
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

    thread = threading.Thread(target=run, name="live-mcp-bearer", daemon=True)
    thread.start()
    wait_ready(port)
    return thread


def start_sink(port: int, hits: list[dict]) -> threading.Thread:
    """A server that records every request. Used as the redirect *target*.

    The assertion that matters is that this receives nothing: a redirect to an origin the owner
    never reviewed must not be followed, so the target is never contacted at all.
    """
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):                                  # noqa: N802 - stdlib naming
            hits.append({"path": self.path, "method": "POST"})
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        do_GET = do_POST                                    # noqa: N815 - same handler

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    wait_ready(port)
    return server


def start_redirector(port: int, target: str, seen: list[dict]) -> threading.Thread:
    """A plain HTTP server that redirects every request somewhere else."""
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):                                  # noqa: N802 - stdlib naming
            seen.append({"path": self.path, "method": "POST"})
            self.send_response(307)
            self.send_header("location", target)
            self.send_header("content-length", "0")
            self.end_headers()

        do_GET = do_POST                                    # noqa: N815 - same handler

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    wait_ready(port)
    return server


def main() -> int:
    evidence: dict[str, object] = {}

    state = pathlib.Path(tempfile.mkdtemp(prefix="mcp-bearer-live-", dir=pathlib.Path.home() / ".hutch-tmp"))
    os.environ["HUTCH_STATE_DIR"] = str(state)

    from hutch.config import get_config
    from hutch.integrations.mcp import config, service
    from hutch.integrations.mcp.config import McpConfigurationError
    from hutch.models import ApprovalMode, Bot, Run, RunStatus
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine
    from hutch.store import Store
    from hutch.tools import build_tools
    from hutch.tools.base import ToolContext
    from hutch.runtime.steps import call_tool

    seen: list[dict] = []
    port = free_port()
    start_authenticated_server(port, seen)
    cfg = get_config()
    cfg.ensure()
    store = Store(cfg)
    url = f"http://127.0.0.1:{port}/mcp"
    definition = {"transport": "mcp_http", "url": url,
                  "auth": {"type": "bearer", "from_env": TOKEN_ENV}}
    service.configure(store, integration_id="bearer", title="Bearer connector",
                      raw_definition=definition)

    # 1. With the variable unset, the connector must fail closed and name the variable.
    os.environ.pop(TOKEN_ENV, None)
    try:
        service.discover(store, integration_id="bearer")
        evidence["missing_variable"] = "NOT REFUSED"
    except McpConfigurationError as exc:
        evidence["missing_variable"] = {"refused": True, "message": str(exc)[:200]}

    # 2. With the variable set, discovery and a call must succeed, and the server must see it.
    os.environ[TOKEN_ENV] = TOKEN
    discovered = service.discover(store, integration_id="bearer")
    evidence["discovery"] = {"tools": [tool["server_tool_name"] for tool in discovered["catalog"]]}

    revision = service.detail(store, "bearer")["revision"]
    bot = store.create_bot(Bot(name="bearer-bot", model="mock/demo", tools=[],
                               approval_mode=ApprovalMode.auto))
    service.grant(store, integration_id="bearer", bot_ref=bot.id, tool_names=["whoami"],
                  operation_classes={"whoami": "read"}, expected_revision=revision)
    run = store.create_run(Run(bot_id=bot.id, prompt="who am i", status=RunStatus.running))
    emit = lambda ev: store.append_event(ev)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    workspace = state / "ws"
    workspace.mkdir(exist_ok=True)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=cfg, workspace=workspace, emit=emit)
    out = call_tool(run, ctx, build_tools(bot.tools, ctx), "mcp__bearer__whoami", {})
    evidence["call"] = {"ok": out.ok, "output": out.output[:200]}
    evidence["server_saw"] = {"requests": len(seen), "authorized": [s["authorized"] for s in seen],
                              "token_never_sent_as_text": TOKEN not in json.dumps(seen)}

    # 3. A wrong token must be refused, and the refusal must not echo the token.
    os.environ[TOKEN_ENV] = TOKEN + "-wrong"
    before = len(seen)
    try:
        service.discover(store, integration_id="bearer")
        evidence["wrong_token"] = "ACCEPTED"
    except McpConfigurationError as exc:
        message = str(exc)
        evidence["wrong_token"] = {"refused": True, "message": message[:160],
                                   "echoed_the_token": TOKEN in message,
                                   "requests": len(seen) - before}

    # 4. A cross-origin redirect must not be followed: the target origin is never reviewed.
    redirect_seen: list[dict] = []
    redirect_port = free_port()          # its own port: the bearer server still holds ``port``
    target_port = free_port()
    redirect_url = f"http://127.0.0.1:{redirect_port}/mcp"
    target_url = f"http://127.0.0.1:{target_port}/mcp"
    target_hits: list[dict] = []
    start_sink(target_port, target_hits)
    start_redirector(redirect_port, target_url, redirect_seen)
    redirect_definition = {"transport": "mcp_http", "url": redirect_url, "auth": {"type": "none"}}
    service.configure(store, integration_id="redirect", title="Redirecting connector",
                      raw_definition=redirect_definition)
    os.environ.pop(TOKEN_ENV, None)
    try:
        service.discover(store, integration_id="redirect")
        evidence["cross_origin_redirect"] = "FOLLOWED"
    except McpConfigurationError as exc:
        evidence["cross_origin_redirect"] = {
            "refused": True, "message": str(exc)[:160],
            "redirector_saw_requests": len(redirect_seen),
            "target_received_requests": len(target_hits)}

    os.environ.pop(TOKEN_ENV, None)
    store.close()
    print(json.dumps(evidence, indent=2, default=str))
    ok = (evidence["call"]["ok"] and evidence["missing_variable"] != "NOT REFUSED"
          and evidence["wrong_token"] != "ACCEPTED"
          and evidence["cross_origin_redirect"] != "FOLLOWED"
          and not target_hits)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
