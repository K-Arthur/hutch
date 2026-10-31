"""Dispatch-level enforcement for governed integration tools (ADR-0017 S3).

Two rules used to be per-runtime convention:

* argument validation ran in the built-in model loop, so workflow nodes and the OpenCode bridge
  dispatched whatever they were handed;
* approval/authority was whatever the tool itself chose to consult.

For third-party tools that is not acceptable: the schema comes from a server, and the grant that
authorized it can be revoked while a run is in flight. These tests pin the enforcement to the one
dispatch function every caller shares, and they use the real store rows rather than a stub.
"""

from __future__ import annotations

from typing import Any, Optional

from hutch.approvals import ApprovalGate
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.runtime.steps import call_tool
from hutch.safety import PolicyEngine
from hutch.store import Store
from hutch.tools.base import Tool, ToolContext, ToolResult


class CountingTool(Tool):
    """A first-party-shaped tool that records whether it was actually entered."""

    name = "counting"
    description = "Count calls; used to prove a refusal happens before the tool runs."
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "count": {"type": "integer"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        self.calls.append(dict(args))
        return ToolResult(ok=True, output="ran")


class GrantedTool(CountingTool):
    """A tool that claims to act through an integration identity (as an MCP tool would)."""

    name = "mcp__acme__search"
    description = "Search Acme."
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, integration_id: str = "acme", server_tool_name: str = "search") -> None:
        super().__init__()
        self._binding = (integration_id, server_tool_name)

    def integration_binding(self) -> Optional[tuple[str, str]]:
        return self._binding


def make(store: Store, config, tmp_path, *, tools: list[Tool] | None = None):
    bot = store.create_bot(Bot(name="dispatch", model="mock/demo", tools=[], approval_mode=ApprovalMode.auto))
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    emit = lambda ev: store.append_event(ev)  # noqa: E731 - the harness's sink
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config,
                      workspace=ws, emit=emit)
    instances = tools if tools is not None else [CountingTool()]
    return bot, run, ctx, {tool.name: tool for tool in instances}


def _grant(store: Store, bot: Bot, *, enabled: int = 1, state: str = "operation_authorized",
           integration_id: str = "acme", server_tool_name: str = "search") -> None:
    with store._tx() as db:
        db.execute("INSERT INTO integrations(integration_id, revision, title, transport, credential_id, "
                   "state, enabled, created_at) VALUES (?,?,'Acme','mcp_stdio','','%s',?,?) "
                   "ON CONFLICT(integration_id) DO UPDATE SET state=excluded.state, enabled=excluded.enabled"
                   % state,
                   (integration_id, "0" * 64, enabled, "2026-10-30T00:00:00+00:00"))
        db.execute("INSERT INTO integration_tool_grants(integration_id, bot_id, server_tool_name, "
                   "canonical_name, schema_revision, granted_at) VALUES (?,?,?,?,?,?) "
                   "ON CONFLICT(integration_id, bot_id, server_tool_name) DO NOTHING",
                   (integration_id, bot.id, server_tool_name, f"mcp__{integration_id}__{server_tool_name}",
                    "0" * 64, "2026-10-30T00:00:00+00:00"))


def test_invalid_arguments_are_refused_before_the_tool_runs(store, config, tmp_path):
    """The workflow and OpenCode callers get the same check the model loop always had."""
    _bot, run, ctx, tools = make(store, config, tmp_path)
    tool = tools["counting"]

    result = call_tool(run, ctx, tools, "counting", {"count": 3})           # missing required "path"

    assert not result.ok and "rejected" in result.output and "path" in result.output
    assert tool.calls == []
    # the refusal is visible in the transcript, not silently swallowed
    assert any(ev.type.value == "tool_result" and not ev.data.get("ok") for ev in store.list_events(run.id))


def test_wrongly_typed_arguments_are_refused(store, config, tmp_path):
    _bot, run, ctx, tools = make(store, config, tmp_path)
    result = call_tool(run, ctx, tools, "counting", {"path": "a", "count": "three"})
    assert not result.ok and tools["counting"].calls == []


def test_valid_arguments_run_normally(store, config, tmp_path):
    _bot, run, ctx, tools = make(store, config, tmp_path)
    result = call_tool(run, ctx, tools, "counting", {"path": "a"})
    assert result.ok and tools["counting"].calls == [{"path": "a"}]


def test_integration_tool_without_a_grant_is_refused(store, config, tmp_path):
    _bot, run, ctx, tools = make(store, config, tmp_path, tools=[GrantedTool()])
    result = call_tool(run, ctx, tools, "mcp__acme__search", {"query": "cats"})
    assert not result.ok and "no longer granted" in result.output
    assert tools["mcp__acme__search"].calls == []


def test_integration_grant_allows_the_call(store, config, tmp_path):
    bot, run, ctx, tools = make(store, config, tmp_path, tools=[GrantedTool()])
    _grant(store, bot)
    assert store.integration_tool_granted(bot.id, "acme", "search")
    result = call_tool(run, ctx, tools, "mcp__acme__search", {"query": "cats"})
    assert result.ok and tools["mcp__acme__search"].calls == [{"query": "cats"}]


def test_revocation_takes_effect_on_the_next_call_without_rebuilding_tools(store, config, tmp_path):
    """The brief's §8.5 rule: a stale tool dict must not restore revoked authority."""
    bot, run, ctx, tools = make(store, config, tmp_path, tools=[GrantedTool()])
    _grant(store, bot)
    assert call_tool(run, ctx, tools, "mcp__acme__search", {"query": "one"}).ok

    with store._tx() as db:
        db.execute("DELETE FROM integration_tool_grants WHERE bot_id=? AND integration_id='acme'", (bot.id,))

    second = call_tool(run, ctx, tools, "mcp__acme__search", {"query": "two"})
    assert not second.ok and "no longer granted" in second.output
    assert tools["mcp__acme__search"].calls == [{"query": "one"}]


def test_disabling_the_integration_also_refuses_its_tools(store, config, tmp_path):
    bot, run, ctx, tools = make(store, config, tmp_path, tools=[GrantedTool()])
    _grant(store, bot)
    with store._tx() as db:
        db.execute("UPDATE integrations SET enabled=0 WHERE integration_id='acme'")
    result = call_tool(run, ctx, tools, "mcp__acme__search", {"query": "x"})
    assert not result.ok and tools["mcp__acme__search"].calls == []


def test_a_grant_that_was_never_operation_authorized_does_not_count(store, config, tmp_path):
    bot, run, ctx, tools = make(store, config, tmp_path, tools=[GrantedTool()])
    _grant(store, bot, state="capabilities_discovered")
    assert store.integration_tool_names(bot.id) == []
    result = call_tool(run, ctx, tools, "mcp__acme__search", {"query": "x"})
    assert not result.ok and tools["mcp__acme__search"].calls == []


def test_first_party_tools_are_unaffected_by_the_grant_check(store, config, tmp_path):
    """A tool with no binding must not be refused merely because integrations exist."""
    bot, run, ctx, tools = make(store, config, tmp_path, tools=[CountingTool(), GrantedTool()])
    _grant(store, bot)
    assert call_tool(run, ctx, tools, "counting", {"path": "a"}).ok


def test_a_tool_that_lies_about_its_binding_is_refused(store, config, tmp_path):
    """Binding to an integration with no grant row is a refusal, not an implicit authority claim."""
    _bot, run, ctx, tools = make(store, config, tmp_path, tools=[GrantedTool(integration_id="other")])
    result = call_tool(run, ctx, tools, "mcp__acme__search", {"query": "x"})
    assert not result.ok
    assert tools["mcp__acme__search"].calls == []
