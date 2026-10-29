"""A3: OpenCode reaches Hutch's reviewed memory only through the run-bound bridge.

The bridge authenticates callers with kernel peer credentials plus recorded
process ancestry, rechecks run/fence/lease/cancellation and memory policy from
SQLite on every call, and dispatches through the same tool objects and receipt
path the built-in runtime uses. No credential ever enters the OpenCode process.
"""

from __future__ import annotations

import json
import os
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


# ---------------------------------------------------------------- live free-model evidence

LIVE_MODEL = os.environ.get("HUTCH_LIVE_OPENCODE_MODEL", "opencode/deepseek-v4.1-flash-free")


def _go_login_available():
    """Use the bounded product inventory; the collection gate never returns a key."""
    from hutch.runtime.opencode_login import LocalLoginError, local_logins
    try:
        return any(row['provider_id'] == 'opencode-go' and row['reusable'] for row in local_logins())
    except LocalLoginError:
        return False


_LIVE_REQUIRED = "live OpenCode free-model evidence: set HUTCH_LIVE_OPENCODE=1 on a host with a selected reusable OpenCode Go login"

requires_live = pytest.mark.skipif(
    not (os.environ.get("HUTCH_LIVE_OPENCODE") == '1' and _go_login_available() and shutil.which("opencode")),
    reason=_LIVE_REQUIRED)


@pytest.fixture()
def live_opencode_auth(config, store):
    """Selected login only, fresh zero-rate qualification, zero-dollar ledger, cleanup."""
    from hutch.connections import ConnectionBook
    from hutch.providers.pricing import PriceBook
    from hutch.runtime.opencode import _model_ref
    from hutch.runtime.opencode_login import reuse_local_login
    from hutch.runtime.opencode_server import OpenCodeServer
    from tests.support.artifacts import artifact_path
    from tests.support.live_models import qualify_free_model

    server = OpenCodeServer(config.state_dir, cwd=config.state_dir)
    try:
        try:
            server.start()
            # Exercise the product's provider-scoped import API; do not copy a
            # personal auth/config file into a version-dependent CLI location.
            reuse_local_login(server, 'opencode-go')
            provider, model = _model_ref(LIVE_MODEL, [])
            if provider != 'opencode':
                pytest.fail('Only the public free route is qualified here; Go entitlement/billing remains separate')
            payload = server.request('GET', '/api/model', timeout=30)
            qualification = qualify_free_model(payload.get('data', []), provider, model)
        finally:
            server.close()
        ConnectionBook(config.state_dir).add('openai-api', 'opencode', account_id='live-evaluation')
        PriceBook(config.state_dir / 'prices.json').set_price(
            LIVE_MODEL, 0, 0, cache_read=0, cache_write=0,
            source='Isolated free evaluation: current native zero-rate metadata at ' + qualification['checked_at'])
        store.set_budget_policy(scope_kind='account', scope_id='live-evaluation', reset='lifetime', ceiling_usd=0)
        out = artifact_path('opencode-free-qualification')
        out.mkdir(parents=True, exist_ok=True)
        (out / 'metadata.json').write_text(json.dumps(qualification, indent=2) + '\n')
        yield
    finally:
        profile = config.state_dir / 'opencode-profile'
        if profile.exists():
            shutil.rmtree(profile)


def _live_owner(store, run):
    claimed = store.claim_run(run.id, "live-free-model-owner", 900)
    assert claimed is not None
    return store.transition_run(run.id, RunStatus.running, fence=claimed.fence)


@requires_live
def test_live_free_model_calls_the_run_bound_memory_bridge(store, config, tmp_path, live_opencode_auth):
    """A real free model, a real private OpenCode server, the real plugin, the real bridge.

    The reviewed fact exists nowhere else: not in the admission context, not in
    the workspace, not in any prompt. The model can only mention the launch
    month by calling `recall` through the run-bound bridge (read-only: it
    records a canonical tool-call event, not an effect receipt), and its
    `remember` call must land as an unreviewed proposal with a done receipt,    never as recallable memory before a human reviews it.
    """
    import time
    from hutch.models import ApprovalMode, EventType, Limits, RuntimeKind
    from hutch.runtime.opencode import OpenCodeRuntime
    from tests.test_runtime_builtin import build, run_it

    ctx, run, _events, _tools = build(
        store, config, tmp_path, model=LIVE_MODEL, tools=["memory"],
        prompt=("Do three things, in order. 1) Call the recall tool with the query 'launch'. "
                "2) Call the remember tool with key 'live-bridge-note' and value "
                "'The live bridge check succeeded.' 3) Then state, in one short sentence, "
                "which month the launch is planned for."),
        runtime=RuntimeKind.opencode, mode=ApprovalMode.auto,
        instructions="You must call the recall tool before answering. Never guess facts you did not recall.",
        limits=Limits(max_steps=10, timeout_seconds=600, daily_token_cap=10_000_000))
    bot = store.get_bot(ctx.bot.id)
    store.upsert_bot(bot.model_copy(update={"memory_enabled": True}), preserve_schedules=True)
    fact = store.remember(ctx.bot.id, "launch-window", "The launch is planned for November.")
    store.review_fact(ctx.bot.id, fact.id, content_hash=fact.content_hash, action="approve", actor="live-fixture")
    _live_owner(store, run)

    started = time.monotonic()
    try:
        answer = run_it(OpenCodeRuntime(), run, ctx, {})
        elapsed = round(time.monotonic() - started, 1)
    except Exception as exc:
        pytest.fail(f"live free-model bridge run failed after {round(time.monotonic() - started, 1)}s: "
                    f"{type(exc).__name__}: {exc}")

    recall_calls = [event for event in store.list_events(run.id)
                    if event.type is EventType.tool_call and event.data.get("tool") == "recall"]
    remember_receipts = [action for action in store.list_actions(run.id)
                         if action["tool"] == "remember" and action["status"] == "done"]
    proposal = store._db.execute("SELECT status FROM memory_facts WHERE bot_id = ? AND key = ?",
                                 (ctx.bot.id, "live-bridge-note")).fetchone()
    submission = store.opencode_submission(run.id)
    print(f"\nLIVE[A3] model={LIVE_MODEL} elapsed={elapsed}s tokens={store.get_run(run.id).tokens} "
          f"recall_events={len(recall_calls)} remember_receipts={len(remember_receipts)} "
          f"proposal={proposal and proposal['status']} submission={submission and submission['state']} "
          f"answer={answer!r}")
    assert recall_calls, "the model must have dispatched recall through the run-bound bridge"
    assert "November" in answer, "the answer must carry the recalled, provenance-bound fact"
    assert remember_receipts, "the remember proposal must be receipt-backed like Builtin's"
    assert proposal is not None and proposal["status"] == "proposed", \
        "the live remember must land as an unreviewed proposal, never as approved memory"


@requires_live
def test_live_free_model_receives_prior_turns_in_a_new_session(store, config, tmp_path, live_opencode_auth):
    """A real free model answers from Hutch's provenance selection, not a native session.

    The bot has no tools at all, so the only way the second run can know the
    colour is the persisted admission selection the adapter delivered into a
    brand-new native session (A1 reconstruction after restart/new session).
    """
    import time
    from hutch.models import ApprovalMode, Limits, RuntimeKind
    from hutch.runtime.opencode import OpenCodeRuntime
    from hutch.tools.base import ToolContext
    from hutch.approvals import ApprovalGate
    from hutch.safety import PolicyEngine
    from tests.test_runtime_builtin import run_it

    bot = store.create_bot(Bot(name="live-continuity-probe", model=LIVE_MODEL, tools=[],
                               approval_mode=ApprovalMode.auto, selfcheck=False,
                               runtime=RuntimeKind.opencode,
                               instructions="Answer briefly and directly.",
                               limits=Limits(max_steps=4, timeout_seconds=600, daily_token_cap=10_000_000)))
    conversation, _ = store.create_conversation(bot.id, "live continuity",
                                                idem_key="live-conv", request_hash="live-conv")
    workspace = tmp_path / "live-ws"
    workspace.mkdir(exist_ok=True)

    def turn(prompt, key):
        run = Run(bot_id=bot.id, prompt=prompt)
        store.submit_conversation_message(conversation["id"], prompt, run,
                                          Task(bot_id=bot.id, prompt=prompt),
                                          idem_key=key, request_hash=key)
        _live_owner(store, run)

        def emit(event):
            store.append_event(event)

        gate = ApprovalGate(store, bot, run, PolicyEngine(), emit, poll_seconds=0.05)
        ctx = ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate,
                          config=config, workspace=workspace, emit=emit)
        started = time.monotonic()
        answer = run_it(OpenCodeRuntime(), run, ctx, {})
        elapsed = round(time.monotonic() - started, 1)
        return run, answer, elapsed

    first_run, first_answer, first_elapsed = turn(
        "My favourite deployment colour is teal. Acknowledge in one word.", "live-first")
    store.flush_events()
    second_run, second_answer, second_elapsed = turn(
        "Without using any tools: which deployment colour did I mention, and what did you answer "
        "the first time? One sentence.", "live-second")
    store.flush_events()
    print(f"\nLIVE[A1] model={LIVE_MODEL} t1={first_elapsed}s/{first_run.tokens}tok "
          f"t2={second_elapsed}s/{second_run.tokens}tok "
          f"first={first_answer!r} second={second_answer!r}")
    assert "teal" in second_answer.lower(), \
        "the second, fresh native session must know the prior turns from Hutch's selection"
    assert second_run.conversation_context, "the second run must carry the persisted admission selection"
