"""Canonical effects, revocation and the generated OpenCode plugin contract."""

import json
import shutil
import threading
import time

import pytest

from hutch.models import ApprovalMode
from hutch.runtime.opencode_memory import RunToolBridge, write_tool_plugin
from tests.test_opencode_memory_bridge import _exchange, _runnable


def _files_bridge(store, config, tmp_path, *, mode=ApprovalMode.auto, max_steps=None):
    bot, _conversation, run = _runnable(store, tools=("files",), name="canonical-tools")
    changes = {"approval_mode": mode}
    if max_steps is not None:
        changes["limits"] = bot.limits.model_copy(update={"max_steps": max_steps})
    store.upsert_bot(bot.model_copy(update=changes), preserve_schedules=True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    bridge = RunToolBridge(store, run, workspace=workspace, config=config,
                           allowed_tools=frozenset({"write_file", "read_file"}))
    bridge.start()
    return store.get_bot(bot.id), run, bridge


def test_canonical_bridge_writes_receipts_and_rechecks_tool_revocation(store, config, tmp_path):
    bot, run, bridge = _files_bridge(store, config, tmp_path)
    store.upsert_bot(store.get_bot(bot.id).model_copy(update={"memory_enabled": False}), preserve_schedules=True)
    try:
        for path in ("first.txt", "second.txt"):
            result = _exchange(bridge, tmp_path, json.dumps({"tool": "write_file",
                "args": {"path": path, "content": "verified"}}))
            assert result["ok"], result
            assert (bridge.workspace / path).read_text() == "verified"
        receipts = [action for action in store.list_actions(run.id)
                    if action["tool"] == "write_file" and action["status"] == "done"]
        assert len(receipts) == 2
        store.upsert_bot(bot.model_copy(update={"tools": []}), preserve_schedules=True)
        result = _exchange(bridge, tmp_path, json.dumps({"tool": "write_file",
            "args": {"path": "revoked.txt", "content": "must not exist"}}))
        assert not result["ok"] and "no longer enabled" in result["output"]
        assert not (bridge.workspace / "revoked.txt").exists()
    finally:
        bridge.close()


def test_closing_bridge_releases_approval_wait_without_starting_effect(store, config, tmp_path):
    bot, run, bridge = _files_bridge(store, config, tmp_path, mode=ApprovalMode.ask)
    result = {}
    thread = threading.Thread(target=lambda: result.update(bridge._dispatch("write_file", {
        "path": "waiting.txt", "content": "must not be written"})))
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not store.pending_approvals() and time.monotonic() < deadline:
            time.sleep(.02)
        assert store.pending_approvals()
        bridge.close()
        thread.join(timeout=3)
        assert not thread.is_alive() and not result["ok"]
        assert not (bridge.workspace / "waiting.txt").exists()
        assert not store.list_actions(run.id)
    finally:
        bridge.close()
        thread.join(timeout=3)


def test_bridge_enforces_a_bounded_number_of_calls(store, config, tmp_path):
    bot, run, bridge = _files_bridge(store, config, tmp_path, max_steps=1)
    try:
        assert bridge._dispatch("write_file", {"path": "one.txt", "content": "one"})["ok"]
        result = bridge._dispatch("write_file", {"path": "two.txt", "content": "two"})
        assert not result["ok"] and "limit" in result["output"]
        assert not (bridge.workspace / "two.txt").exists()
    finally:
        bridge.close()


def test_policy_change_cannot_expand_a_running_bridges_authority(store, config, tmp_path):
    bot, run, bridge = _files_bridge(store, config, tmp_path)
    current = store.get_bot(bot.id)
    store.upsert_bot(current.model_copy(update={"risk_tier": type(current.risk_tier).trusted}),
                     preserve_schedules=True)
    try:
        result = bridge._dispatch("write_file", {"path": "changed.txt", "content": "must not exist"})
        assert not result["ok"] and "policy changed" in result["output"]
        assert not (bridge.workspace / "changed.txt").exists()
    finally:
        bridge.close()


def test_captured_narrower_execution_scope_is_preserved(store, config, tmp_path):
    from hutch.safety import PolicyEngine
    from hutch.approvals import ApprovalGate
    from hutch.tools.base import ToolContext
    bot, run, bridge = _files_bridge(store, config, tmp_path)
    bridge.close()
    captured = store.get_bot(bot.id).model_copy(update={"tools": ["read_file"]})
    policy = PolicyEngine(captured.risk_tier, captured.command_rules)
    context = ToolContext(bot=captured, run=run, store=store, config=config, workspace=bridge.workspace,
                          policy=policy, gate=ApprovalGate(store, captured, run, policy, lambda event: None))
    bridge = RunToolBridge(store, run, workspace=bridge.workspace, config=config,
                          allowed_tools=frozenset({"write_file"}), context=context)
    try:
        result = bridge._dispatch("write_file", {"path": "scope.txt", "content": "must not exist"})
        assert not result["ok"] and "no longer enabled" in result["output"]
        assert not (bridge.workspace / "scope.txt").exists()
    finally:
        bridge.close()


def test_canonical_bridge_does_not_grant_native_computer_or_unmanaged_delegation(store, config, tmp_path):
    _bot, _conversation, run = _runnable(store)
    for name in ("computer", "delegate_task", "invented_tool"):
        with pytest.raises(ValueError, match="canonical tools"):
            RunToolBridge(store, run, workspace=tmp_path, config=config, allowed_tools=frozenset({name}))


@pytest.mark.skipif(shutil.which("opencode") is None, reason="OpenCode CLI not installed")
def test_real_opencode_plugin_calls_the_canonical_file_pipeline(store, config, tmp_path):
    from hutch.code_handoff import opencode_profile_paths
    from hutch.runtime.opencode import _agent_definition
    from hutch.runtime.opencode_server import OpenCodeServer
    from hutch.tools import build_tools
    from hutch.tools.base import ToolContext
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine

    bot, run, bridge = _files_bridge(store, config, tmp_path)
    bot = store.get_bot(bot.id)
    policy = PolicyEngine(bot.risk_tier, bot.command_rules)
    ctx = ToolContext(bot=bot, run=run, store=store, config=config, workspace=bridge.workspace,
                      policy=policy, gate=ApprovalGate(store, bot, run, policy, lambda event: None))
    tools = build_tools(list(bridge.allowed_tools), ctx)
    plugin = write_tool_plugin(opencode_profile_paths(config.state_dir)["root"])
    agent_id, agent = _agent_definition(bot.id, title="Canonical RPC test", instructions="probe",
        provider_id="test", model_id="model", tool_names=set(), workspace=str(bridge.workspace))
    server = OpenCodeServer(config.state_dir, cwd=bridge.workspace, agents={agent_id: agent}, plugins=[{
        "package": str(plugin.parent), "options": {"socket": bridge.socket_name,
            "tools": [{"name": name, "description": tool.description, "input": tool.parameters}
                      for name, tool in tools.items()]}}])
    try:
        server.start()
        assert bridge.trust_process(server.process.pid)
        reply = server.request("POST", "/api/rpc/hutch-tool-bridge/write_file", json_body={"input": {
            "path": "plugin-proof.txt", "content": "canonical plugin pipeline"}}, timeout=20)
        assert reply["output"]["ok"], reply
        assert (bridge.workspace / "plugin-proof.txt").read_text() == "canonical plugin pipeline"
    finally:
        server.close()
        bridge.close()
