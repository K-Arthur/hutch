"""The contained stdio transport, exercised against a real MCP server process.

These tests launch the actual fixture through Hutch's sandbox and speak the protocol to it. A
unit test cannot catch a launcher that stopped working; these can. They also assert the
launcher's security promise: no ambient credentials and no host network inside the child.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hutch.approvals import ApprovalGate
from hutch.integrations.mcp import config, discovery, persistence, service
from hutch.integrations.mcp.tool import construct_mcp_tools
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.runtime.steps import call_tool
from hutch.safety import PolicyEngine
from hutch.tools.base import ToolContext

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_stdio_server.py"

needs_sandbox = pytest.mark.skipif(
    not shutil.which("bwrap") or not shutil.which("systemd-run") or not Path("/usr/bin/python3").is_file(),
    reason="the contained stdio transport needs bubblewrap, systemd-run and the system Python")


def _context(store, bot, run, workspace):
    emit = lambda ev: store.append_event(ev)  # noqa: E731 - the harness's sink
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    return ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                       config=store.config, workspace=workspace, emit=emit)


@needs_sandbox
def test_a_real_contained_server_is_discovered_and_called(store, tmp_path):
    """Launch the fixture through the sandbox, page its catalog, then call it with the grant."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello from the workspace")
    server = workspace / "server.py"
    shutil.copyfile(FIXTURE, server)

    definition = config.validate_stdio_definition({
        "transport": "mcp_stdio", "command": "/usr/bin/python3", "args": ["/workspace/server.py"]})
    revision = config.definition_revision(definition)
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)

    result = service.discover(store, integration_id="acme", workspace=workspace)
    names = {tool["server_tool_name"] for tool in result["catalog"]}
    assert names == {"read_workspace", "write_workspace", "inspect_process", "wait_for_cancel"}
    assert all(tool["supported"] for tool in result["catalog"])

    bot = store.create_bot(Bot(name="reader", model="mock/demo", tools=[], approval_mode=ApprovalMode.auto))
    service.grant(store, integration_id="acme", bot_ref=bot.id, tool_names=["read_workspace"],
                  operation_classes={"read_workspace": "read"}, expected_revision=revision)

    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))
    ctx = _context(store, bot, run, workspace)
    tools = construct_mcp_tools(store, bot, run)
    assert set(tools) == {"mcp__acme__read_workspace"}

    out = call_tool(run, ctx, tools, "mcp__acme__read_workspace", {"path": "/workspace/note.txt"})
    assert out.ok, out.output
    assert "hello from the workspace" in out.output


@needs_sandbox
def test_a_contained_server_has_no_ambient_credentials_or_network(store, tmp_path, monkeypatch):
    """The launcher's promise: a cleared environment, no host credentials, no host network."""
    monkeypatch.setenv("HUTCH_TEST_SECRET", "must-not-be-inherited")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    shutil.copyfile(FIXTURE, workspace / "server.py")
    definition = config.validate_stdio_definition({
        "transport": "mcp_stdio", "command": "/usr/bin/python3", "args": ["/workspace/server.py"]})
    revision = config.definition_revision(definition)
    bot = store.create_bot(Bot(name="prober", model="mock/demo", tools=[], approval_mode=ApprovalMode.auto))
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=definition, revision=revision)
        [inspect] = discovery.normalize_mcp_tools("acme", [
            {"name": "inspect_process", "description": "probe", "inputSchema": {
                "type": "object", "properties": {"port": {"type": "integer"}},
                "required": ["port"]}}])
        persistence.save_catalog(db, "acme", [inspect])
        persistence.grant_tools(db, integration_id="acme", bot_id=bot.id,
                                tool_names=["inspect_process"],
                                operation_classes={"inspect_process": "read"},
                                expected_revision=revision)

    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))
    ctx = _context(store, bot, run, workspace)
    out = call_tool(run, ctx, construct_mcp_tools(store, bot, run), "mcp__acme__inspect_process",
                    {"port": 9})
    assert out.ok, out.output
    observed = json.loads(out.output)
    assert observed["secret_env"] is None          # Hutch's own environment was not inherited
    assert observed["home"] == "/tmp/hutch-home"   # not the user's home
    assert observed["network"] == "isolated"       # no host network in the sandbox
