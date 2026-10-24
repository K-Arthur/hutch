"""A3: OpenCode reaches Hutch's reviewed memory only through the run-bound bridge.

The bridge authenticates callers with kernel peer credentials plus recorded
process ancestry, rechecks run/fence/lease/cancellation and memory policy from
SQLite on every call, and dispatches through the same tool objects and receipt
path the built-in runtime uses. No credential ever enters the OpenCode process.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from hutch.models import Bot, Run, RunStatus, Task
from hutch.runtime.opencode_memory import MemoryBridge, write_memory_plugin


CLIENT_SOURCE = r'''import socket
import subprocess
import sys

mode, name, payload = sys.argv[1], sys.argv[2], sys.argv[3]

if mode == "relay":
    sys.stdout.write("ready\n")
    sys.stdout.flush()
    input()
    child = subprocess.Popen(
        [sys.executable, __file__, "connect-now", name, payload],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = child.communicate(timeout=20)
    sys.stdout.write(out)
    sys.stdout.flush()
    raise SystemExit(0)

if mode == "connect":
    sys.stdout.write("ready\n")
    sys.stdout.flush()
    input()

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(8)
try:
    sock.connect("\0" + name)
    try:
        sock.sendall(payload.encode("utf-8") + b"\n")
    except OSError:
        pass                              # server may bound the request first
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    sys.stdout.write("RESP " + data.decode("utf-8", "replace").strip() + "\n")
except Exception as exc:
    sys.stdout.write("ERR " + type(exc).__name__ + "\n")
finally:
    sock.close()
    sys.stdout.flush()
'''


def _runnable(store, *, tools=("memory",), memory_enabled=True, name="bridge-bot"):
    bot = store.create_bot(Bot(name=name, model="mock/demo", tools=list(tools),
                               memory_enabled=memory_enabled))
    conversation, _ = store.create_conversation(bot.id, "bridge chat", idem_key=f"{name}-conv",
                                                request_hash=f"{name}-conv")
    run = Run(bot_id=bot.id, prompt="remember the launch window")
    store.submit_conversation_message(conversation["id"], run.prompt, run,
                                      Task(bot_id=bot.id, prompt=run.prompt),
                                      idem_key=f"{name}-run", request_hash=f"{name}-run")
    claimed = store.claim_run(run.id, "bridge-owner", 120)
    assert claimed is not None
    store.transition_run(run.id, RunStatus.running, fence=claimed.fence)
    return bot, conversation, store.get_run(run.id)


def _bridge(store, run, config, tmp_path, allowed=("recall", "remember")):
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    bridge = MemoryBridge(store, run, workspace=workspace, config=config,
                          allowed_tools=frozenset(allowed))
    bridge.start()
    return bridge


def _exchange(bridge, tmp_path, payload, *, mode="connect", trust=True, relay=False):
    script = tmp_path / "bridge_client.py"
    if not script.exists():
        script.write_text(CLIENT_SOURCE, encoding="utf-8")
    effective_mode = "relay" if relay else mode
    proc = subprocess.Popen([sys.executable, str(script), effective_mode, bridge.socket_name, payload],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    ready = proc.stdout.readline().strip()
    assert ready == "ready", f"client handshake failed: {ready}"
    if trust:
        assert bridge.trust_process(proc.pid), "could not record the test client identity"
    proc.stdin.write("go\n")
    proc.stdin.flush()
    out = proc.stdout.read()
    proc.wait(timeout=25)
    assert proc.returncode == 0, out
    line = out.strip().splitlines()[-1] if out.strip() else ""
    if line.startswith("RESP "):
        body = line[len("RESP "):].strip()
        try:
            return json.loads(body) if body else {"ok": False, "output": "empty response"}
        except ValueError:
            return {"ok": False, "output": f"invalid response line: {body[:200]}"}
    return {"ok": False, "output": f"transport failure: {line or 'no output'}"}


def test_bridge_admits_only_memory_tools_in_its_constructor(store, config, tmp_path):
    _bot, _conversation, run = _runnable(store, name="constructor-guard")
    with pytest.raises(ValueError, match="memory tools"):
        MemoryBridge(store, run, workspace=tmp_path, config=config, allowed_tools=frozenset({"shell"}))
    with pytest.raises(ValueError, match="memory tools"):
        MemoryBridge(store, run, workspace=tmp_path, config=config, allowed_tools=frozenset())


def test_bridge_authorizes_only_the_recorded_process_tree(store, config, tmp_path):
    _bot, _conversation, run = _runnable(store, name="tree-auth")
    bridge = _bridge(store, run, config, tmp_path)
    try:
        # Direct descendant of the recorded process: authorized.
        direct = _exchange(bridge, tmp_path, json.dumps({"tool": "recall", "args": {"query": "launch"}}))
        assert direct["ok"] is True
        # A grandchild of the recorded process: authorized through ancestry.
        grandchild = _exchange(bridge, tmp_path, json.dumps({"tool": "recall", "args": {"query": "launch"}}),
                               relay=True)
        assert grandchild["ok"] is True
        # This test process is the recorded process's PARENT, not its tree: refused.
        unrelated = _exchange(bridge, tmp_path, json.dumps({"tool": "recall", "args": {"query": "launch"}}),
                              trust=False)
        assert unrelated["ok"] is False and "not authorized" in unrelated["output"]
        assert bridge.refusals >= 1
    finally:
        bridge.close()


def test_bridge_refuses_when_no_process_was_ever_recorded(store, config, tmp_path):
    """A fake OpenCode server owns no process: the bridge must refuse everyone."""
    _bot, _conversation, run = _runnable(store, name="refuse-all")
    bridge = _bridge(store, run, config, tmp_path)
    try:
        # The adapter never records a process for a fake server, so this client
        # stays unrecorded exactly as any ambient caller would.
        result = _exchange(bridge, tmp_path, json.dumps({"tool": "recall", "args": {}}), trust=False)
        assert result["ok"] is False and "not authorized" in result["output"]
    finally:
        bridge.close()


@pytest.mark.parametrize("scenario", ["cancel", "stale-fence", "expired-lease"])
def test_bridge_refuses_non_live_or_stale_run_authority(store, config, tmp_path, scenario):
    _bot, _conversation, run = _runnable(store, name=f"authority-{scenario}")
    bridge = _bridge(store, run, config, tmp_path)
    try:
        payload = json.dumps({"tool": "recall", "args": {"query": "x"}})
        if scenario == "cancel":
            store.request_cancel_tree(run.id)
            expect = "no longer live"
        elif scenario == "stale-fence":
            # Models a recovery takeover: the DB fence advances past the bridge's.
            with store._tx() as db:
                db.execute("UPDATE runs SET fence = fence + 1 WHERE id = ?", (run.id,))
            expect = "fence changed"
        else:
            with store._tx() as db:
                db.execute("UPDATE runs SET lease_expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                           (run.id,))
            expect = "lease has expired"
        result = _exchange(bridge, tmp_path, payload)
        assert result["ok"] is False and expect in result["output"]
    finally:
        bridge.close()


def test_bridge_honors_memory_off_and_stale_tool_lists_live(store, config, tmp_path):
    bot, _conversation, run = _runnable(store, name="memory-toggle")
    bridge = _bridge(store, run, config, tmp_path)
    try:
        payload = json.dumps({"tool": "recall", "args": {"query": "x"}})
        assert _exchange(bridge, tmp_path, payload)["ok"] is True
        bot.memory_enabled = False
        store.upsert_bot(bot, preserve_schedules=True)
        off = _exchange(bridge, tmp_path, payload)
        assert off["ok"] is False and "disabled" in off["output"]
        bot.memory_enabled = True
        bot.tools = []
        store.upsert_bot(bot, preserve_schedules=True)
        stale = _exchange(bridge, tmp_path, payload)
        assert stale["ok"] is False and "no longer enabled" in stale["output"]
    finally:
        bridge.close()


def test_bridge_recall_is_conversation_scoped_with_exact_revision_and_provenance(
        store, config, tmp_path):
    bot, conversation, run = _runnable(store, name="scoped-recall")
    here = store.remember(bot.id, "launch-window", "The launch is planned for November.",
                          conversation_id=conversation["id"])
    store.review_fact(bot.id, here.id, content_hash=here.content_hash, action="approve", actor="fixture")
    other_chat, _ = store.create_conversation(bot.id, "other chat", idem_key="other-chat",
                                              request_hash="other-chat")
    secret = store.remember(bot.id, "private-note", "Only for the other chat.",
                            conversation_id=other_chat["id"])
    store.review_fact(bot.id, secret.id, content_hash=secret.content_hash, action="approve", actor="fixture")
    bridge = _bridge(store, run, config, tmp_path)
    try:
        result = _exchange(bridge, tmp_path, json.dumps({"tool": "recall", "args": {"query": "launch"}}))
        assert result["ok"] is True
        assert "November" in result["output"]
        assert "Only for the other chat." not in result["output"]
        items = json.loads(result["output"].split("\n", 1)[1])
        match = next(item for item in items if item["key"] == "launch-window")
        assert match["revision"] == here.revision and match["scope_kind"] == "conversation"
        # Source update: a newer approved revision replaces the old value.
        updated = store.remember(bot.id, "launch-window", "The launch moved to December.",
                                 conversation_id=conversation["id"])
        store.review_fact(bot.id, updated.id, content_hash=updated.content_hash,
                          action="approve", actor="fixture")
        revised = _exchange(bridge, tmp_path, json.dumps({"tool": "recall", "args": {"query": "launch"}}))
        assert "December" in revised["output"] and "November" not in revised["output"]
        # Revocation: an archived fact leaves recall entirely.
        store.review_fact(bot.id, updated.id, content_hash=updated.content_hash,
                          action="archive", actor="fixture")
        revoked = _exchange(bridge, tmp_path, json.dumps({"tool": "recall", "args": {"query": "launch"}}))
        items = json.loads(revoked["output"].split("\n", 1)[1])
        assert not [item for item in items if item["key"] == "launch-window"]
    finally:
        bridge.close()


def test_bridge_remember_creates_a_review_proposal_with_a_done_receipt(
        store, config, tmp_path):
    bot, _conversation, run = _runnable(store, name="bridge-propose")
    bridge = _bridge(store, run, config, tmp_path)
    try:
        result = _exchange(bridge, tmp_path, json.dumps(
            {"tool": "remember", "args": {"key": "preferred-format", "value": "Use tables."}}))
        assert result["ok"] is True
        assert result["data"]["status"] == "proposed"
        row = store._db.execute("SELECT status, scope_kind FROM memory_facts WHERE bot_id = ? AND key = ?",
                                (bot.id, "preferred-format")).fetchone()
        # Proposals inherit their conversation run's chat scope (ADR-0008).
        assert row is not None and row["status"] == "proposed" and row["scope_kind"] == "conversation"
        [action] = store.list_actions(run.id)
        assert action["tool"] == "remember" and action["status"] == "done"
        # Proposals are not recallable until a human reviews them.
        recall = _exchange(bridge, tmp_path, json.dumps({"tool": "recall", "args": {"query": "tables"}}))
        items = json.loads(recall["output"].split("\n", 1)[1])
        assert not [item for item in items if item["key"] == "preferred-format"]
    finally:
        bridge.close()


def test_bridge_refuses_hostile_and_out_of_scope_requests(store, config, tmp_path):
    _bot, _conversation, run = _runnable(store, name="hostile")
    bridge = _bridge(store, run, config, tmp_path)
    try:
        cases = [
            ({"tool": "shell", "args": {"command": "id"}}, "not admitted"),
            ({"tool": "recall", "args": {"query": ["not", "a", "string"]}}, "must be a string"),
            ({"tool": "remember", "args": {"key": 7, "value": "x"}}, "key must be a string"),
            ({"tool": "recall", "args": ["list-not-dict"]}, "JSON-object arguments"),
            ({"tool": "recall"}, "JSON-object arguments"),
            ("not-json-at-all", "not valid JSON"),
        ]
        for request, expected in cases:
            payload = request if isinstance(request, str) else json.dumps(request)
            result = _exchange(bridge, tmp_path, payload)
            assert result["ok"] is False and expected in result["output"], (request, result)
        oversized = json.dumps({"tool": "recall", "args": {"query": "x" * 9_000}})
        bounded = _exchange(bridge, tmp_path, oversized)
        assert bounded["ok"] is False and "bound" in bounded["output"]
    finally:
        bridge.close()


@pytest.mark.skipif(shutil.which("opencode") is None, reason="the opencode CLI is not installed")
def test_real_opencode_executes_bridge_memory_ops_through_the_plugin(store, config, tmp_path):
    """Live installed-CLI verification (no model call): plugin → socket → Hutch tools.

    Uses the RPC surface the plugin registers, which calls the exact same
    ``bridgeCall`` the model-facing tools use, so this exercises the whole
    supported path except a model choosing to invoke the tool.
    """
    from hutch.code_handoff import opencode_profile_paths
    from hutch.runtime.opencode import _agent_definition
    from hutch.runtime.opencode_memory import write_memory_plugin
    from hutch.runtime.opencode_server import OpenCodeServer, OpenCodeServerError

    bot, conversation, run = _runnable(store, name="live-bridge")
    fact = store.remember(bot.id, "launch-window", "The launch is planned for November.",
                          conversation_id=conversation["id"])
    store.review_fact(bot.id, fact.id, content_hash=fact.content_hash, action="approve", actor="live")
    bridge = _bridge(store, run, config, tmp_path)
    agent_id, agent = _agent_definition(bot.id, title="Live bridge probe", instructions="probe",
                                        provider_id="test", model_id="model",
                                        tool_names={"recall", "remember"},
                                        workspace=str(tmp_path / "ws"))
    plugin_dir = write_memory_plugin(opencode_profile_paths(config.state_dir)["root"],
                                     bridge.socket_name)
    server = OpenCodeServer(config.state_dir, cwd=tmp_path / "ws", agents={agent_id: agent},
                            plugins=[{"package": str(plugin_dir.parent),
                                      "options": {"socket": bridge.socket_name}}],
                            startup_timeout=45)
    try:
        server.start()
        assert server.process is not None
        assert bridge.trust_process(server.process.pid), "could not record the live opencode process"
        log = opencode_profile_paths(config.state_dir)["root"] / "xdg-data" / "opencode" / "log" / "opencode.log"
        if log.exists():
            failures = [line for line in log.read_text(errors="replace").splitlines()
                        if "failed to load plugin" in line]
            assert not failures, failures

        recall = server.request("POST", "/api/rpc/hutch-memory-bridge/recall",
                                json_body={"input": {"query": "launch"}}, timeout=20)
        output = recall["output"]
        assert output["ok"] is True and "November" in output["output"]
        assert '"revision": 1' in output["output"]

        remember = server.request("POST", "/api/rpc/hutch-memory-bridge/remember",
                                  json_body={"input": {"key": "live-key", "value": "Through the live bridge."}},
                                  timeout=20)
        assert remember["output"]["ok"] is True
        row = store._db.execute("SELECT status FROM memory_facts WHERE bot_id = ? AND key = ?",
                                (bot.id, "live-key")).fetchone()
        assert row is not None and row["status"] == "proposed"
        assert [a for a in store.list_actions(run.id) if a["tool"] == "remember"
                and a["status"] == "done"]

        # Hostile input never reaches the socket: the plugin's input schema rejects it.
        with pytest.raises(OpenCodeServerError, match="invalid_input"):
            server.request("POST", "/api/rpc/hutch-memory-bridge/remember",
                           json_body={"input": {"key": 123, "value": "x"}}, timeout=20)

        # Per-call authority recheck through the real path: cancellation lands live.
        store.request_cancel_tree(run.id)
        refused = server.request("POST", "/api/rpc/hutch-memory-bridge/recall",
                                 json_body={"input": {"query": "launch"}}, timeout=20)
        assert refused["output"]["ok"] is False and "no longer live" in refused["output"]["output"]
    finally:
        server.close()
        bridge.close()


def test_adapter_writes_the_memory_plugin_and_socket_when_memory_is_admitted(
        store, config, tmp_path, monkeypatch):
    from hutch.models import ApprovalMode, Limits, RuntimeKind
    from hutch.runtime.opencode import OpenCodeRuntime
    from tests.test_runtime_builtin import build, run_it
    from tests.test_runtime_opencode import FakeOpenCodeServer, completed_assistant

    ctx, run, _events, _tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=["memory"],
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.assistant = completed_assistant("ok")
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer",
                        lambda *a, **k: (fake.init_kwargs.update(k), fake)[1])
    assert run_it(OpenCodeRuntime(), run, ctx, {}) == "ok"
    plugins = fake.init_kwargs.get("plugins")
    assert plugins and len(plugins) == 1
    entry = plugins[0]
    assert entry["options"]["socket"].startswith("hutch-mb-")
    plugin_dir = Path(entry["package"])
    source = (plugin_dir / "index.ts").read_text(encoding="utf-8")
    assert 'name: "recall"' in source and 'name: "remember"' in source
    assert "bridgeCall" in source and "node:net" in source
    # v2.1.4 crashes Rpc.define without an explicit events map; guard the shape.
    assert "events: {}" in source
    # The bridge is closed with the run: its abstract socket no longer accepts.
    probe = __import__("socket").socket(__import__("socket").AF_UNIX, __import__("socket").SOCK_STREAM)
    probe.settimeout(1)
    try:
        probe.connect("\0" + entry["options"]["socket"])
        raised = False
    except OSError:
        raised = True
    finally:
        probe.close()
    assert raised, "the per-run socket must be gone after the run ends"


def test_adapter_omits_the_memory_plugin_when_memory_is_disabled(
        store, config, tmp_path, monkeypatch):
    from hutch.models import ApprovalMode, Limits, RuntimeKind
    from hutch.runtime.opencode import OpenCodeRuntime
    from tests.test_runtime_builtin import build, run_it
    from tests.test_runtime_opencode import FakeOpenCodeServer, completed_assistant

    ctx, run, _events, _tools = build(
        store, config, tmp_path, model="opencode/test/model", tools=["memory"], memory_enabled=False,
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        limits=Limits(max_steps=3, timeout_seconds=60, daily_token_cap=200_000))
    fake = FakeOpenCodeServer()
    fake.assistant = completed_assistant("ok")
    monkeypatch.setattr("hutch.runtime.opencode.OpenCodeServer",
                        lambda *a, **k: (fake.init_kwargs.update(k), fake)[1])
    assert run_it(OpenCodeRuntime(), run, ctx, {}) == "ok"
    assert fake.init_kwargs.get("plugins") == []
