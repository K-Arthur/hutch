"""The guarantees a connector call makes, asserted rather than documented.

Each test here exists because an independent review found the code claimed something it did not
enforce: an effect receipt for non-read calls, a fresh approval for every non-read call, a check
that the owner's effect class has not changed under a running assistant, and a credential that
never reaches argv or the definition.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import pytest

from hutch.approvals import ApprovalGate, resolve_approval
from hutch.integrations.mcp import config, persistence, service
from hutch.integrations.mcp.tool import McpToolAdapter
from hutch.models import ApprovalMode, Bot, Run, RunStatus
from hutch.runtime.steps import call_tool
from hutch.safety import PolicyEngine
from hutch.tools.base import ToolContext

DEFINITION = {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": [], "env": {},
              "read_only_paths": [], "command_sha256": "0" * 64, "read_only_fingerprints": {}}


class RecordingAdapter(McpToolAdapter):
    """An adapter whose transport is replaced, so the governed path can be tested without a server."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls: list[dict[str, Any]] = []

    def _call(self, args: dict[str, Any], ctx: ToolContext):
        from hutch.tools.base import ToolResult
        self.calls.append(dict(args))
        return ToolResult(True, json.dumps({"ok": True}))


def _setup(store, *, operation_class: str, approval_mode=ApprovalMode.auto):
    bot = store.create_bot(Bot(name="connector-bot", model="mock/demo", tools=[], approval_mode=approval_mode))
    revision = config.definition_revision(DEFINITION)
    with store._tx() as db:
        persistence.save_definition(db, integration_id="acme", title="Acme",
                                    definition=DEFINITION, revision=revision)
        from hutch.integrations.mcp import discovery
        [tool_row] = discovery.normalize_mcp_tools("acme", [{
            "name": "search", "description": "Search",
            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}])
        persistence.save_catalog(db, "acme", [tool_row])
        persistence.grant_tools(db, integration_id="acme", bot_id=bot.id, tool_names=["search"],
                                operation_classes={"search": operation_class}, expected_revision=revision)
    adapter = RecordingAdapter(integration_id="acme", server_tool_name="search",
                               canonical_name="mcp__acme__search",
                               schema_revision=tool_row["schema_revision"],
                               input_schema=tool_row["input_schema"], description="Search",
                               operation_class=operation_class, definition=DEFINITION)
    run = store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running))
    emit = lambda ev: store.append_event(ev)  # noqa: E731
    gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.01)
    ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                      config=store.config, workspace=store.config.state_dir, emit=emit)
    return bot, run, ctx, adapter


def _approve_while_waiting(store, runner, *, approve=True):
    """Run a blocking call in a thread and resolve its approval card, returning the result."""
    import threading
    import time
    out: dict[str, Any] = {}
    thread = threading.Thread(target=lambda: out.update(result=runner()))
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline and not store.pending_approvals():
        time.sleep(0.02)
    pending = store.pending_approvals()
    assert pending, "a non-read connector call must ask the owner"
    resolve_approval(store, pending[0].id, approve=approve, by="test")
    thread.join(10)
    assert not thread.is_alive()
    return out["result"], pending[0]


def test_a_read_call_is_silent_and_leaves_no_receipt(store):
    _bot, run, ctx, adapter = _setup(store, operation_class="read")
    result = call_tool(run, ctx, {adapter.name: adapter}, adapter.name, {"q": "cats"})
    assert result.ok and adapter.calls == [{"q": "cats"}]
    assert store.list_actions(run.id) == []


def test_a_write_call_leaves_a_receipt_with_the_effect_bracketed(store):
    """The review found the adapter declared an effect but never began one, so no receipt existed."""
    _bot, run, ctx, adapter = _setup(store, operation_class="write")
    result, _approval = _approve_while_waiting(
        store, lambda: call_tool(run, ctx, {adapter.name: adapter}, adapter.name, {"q": "cats"}))
    assert result.ok, result.output
    actions = store.list_actions(run.id)
    assert len(actions) == 1
    assert actions[0]["tool"] == adapter.name
    assert actions[0]["status"] == "done"
    assert actions[0]["effect"] == "process"


def test_a_write_call_asks_every_time_even_after_always_allow(store):
    """A standing 'always allow' must not cover a connector call the owner did not classify as read.

    The owner may have allowed this tool name once for a native tool, so every sticky key that could
    plausibly match is planted before the call.
    """
    import threading
    import time

    bot, run, ctx, adapter = _setup(store, operation_class="write")
    for key in (f"{adapter.name}:*", adapter.name, f"{adapter.name}:write"):
        store.allow_sticky(bot.id, key)
    assert store.list_sticky_allows(bot.id)

    out: dict[str, Any] = {}
    thread = threading.Thread(target=lambda: out.update(
        result=call_tool(run, ctx, {adapter.name: adapter}, adapter.name, {"q": "first"})))
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline and not store.pending_approvals():
        time.sleep(0.02)
    assert store.pending_approvals(), "a write-class connector call must still ask"
    resolve_approval(store, store.pending_approvals()[0].id, approve=True, by="test")
    thread.join(10)
    assert out["result"].ok and adapter.calls == [{"q": "first"}]


def test_a_denied_write_call_reaches_no_transport(store):
    _bot, run, ctx, adapter = _setup(store, operation_class="write")
    result, _approval = _approve_while_waiting(
        store, lambda: call_tool(run, ctx, {adapter.name: adapter}, adapter.name, {"q": "cats"}),
        approve=False)
    assert not result.ok and adapter.calls == []
    assert store.list_actions(run.id) == []


def test_a_reclassified_tool_is_refused_without_a_new_run(store):
    """The review found only the schema revision was re-checked, not the owner's effect class."""
    bot, run, ctx, adapter = _setup(store, operation_class="read")
    with store._tx() as db:
        db.execute("UPDATE integration_tool_grants SET operation_class='destructive' "
                   "WHERE bot_id=? AND integration_id='acme'", (bot.id,))
    result = call_tool(run, ctx, {adapter.name: adapter}, adapter.name, {"q": "cats"})
    assert not result.ok and "effect class changed" in result.output
    assert adapter.calls == []


# --------------------------------------------------------------------------- credential screening


@pytest.mark.parametrize("value", [
    "postgres://user:secret@db.internal/app",
    "password=hunter2",
    "sk-live-abcdef123456",
    "ghp_0123456789abcdef",
])
def test_a_credential_shaped_literal_environment_value_is_refused(value):
    with pytest.raises(config.McpConfigurationError) as exc:
        config.validate_stdio_definition(
            {"transport": "mcp_stdio", "command": "/usr/bin/python3", "env": {"SETTINGS": value}})
    assert "from_env" in str(exc.value)


def test_a_credential_shaped_positional_argument_is_refused():
    with pytest.raises(config.McpConfigurationError) as exc:
        config.validate_stdio_definition(
            {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": ["sk-live-abcdef123456"]})
    assert "positional argument" in str(exc.value)


def test_ordinary_configuration_values_are_still_accepted():
    normalized = config.validate_stdio_definition(
        {"transport": "mcp_stdio", "command": "/usr/bin/python3",
         "args": ["--log-level", "debug"], "env": {"LOG_LEVEL": "debug", "TZ": "UTC"}})
    assert normalized["env"] == {"LOG_LEVEL": "literal:debug", "TZ": "literal:UTC"}


def test_a_resolved_reference_never_appears_in_the_launch_argv(monkeypatch):
    """A credential handed to bwrap with --setenv is readable from /proc by the same user."""
    monkeypatch.setenv("HUTCH_TEST_CONNECTOR_TOKEN", "super-secret-value")
    definition = config.validate_stdio_definition({
        "transport": "mcp_stdio", "command": "/usr/bin/python3",
        "env": {"SERVICE_TOKEN": {"from_env": "HUTCH_TEST_CONNECTOR_TOKEN"}}})
    if not __import__("shutil").which("bwrap"):
        pytest.skip("the contained launcher needs bubblewrap")
    argv = __import__("hutch.integrations.mcp.transport", fromlist=["stdio_launch_argv"]).stdio_launch_argv(
        definition, store_workspace())
    assert "super-secret-value" not in " ".join(argv)
    assert "SERVICE_TOKEN" not in " ".join(argv)
    # ...and it is present in the environment the supervisor passes instead.
    from hutch.integrations.mcp.transport import child_environment
    assert child_environment(definition)["SERVICE_TOKEN"] == "super-secret-value"


def store_workspace():
    import tempfile
    from pathlib import Path
    return Path(tempfile.mkdtemp(prefix="mcp-env-", dir=Path.home() / ".hutch-tmp"))
