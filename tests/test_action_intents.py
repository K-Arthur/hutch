"""Immutable intent, fencing, atomic uncertainty and independent operator reconciliation."""
from datetime import timedelta
from pathlib import Path
import json
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from hutch.action_receipts import ActionConflict
from hutch.engine import Engine
from hutch.lifecycle import LeaseLost
from hutch.models import ApprovalMode, Bot, Run, RunStatus, Task, iso, utcnow
from hutch.server.app import create_app
from hutch.store import IdempotencyConflict, Store


def owned(store, *, conversation=None):
    bot = store.get_bot("intent-fixture") or store.create_bot(Bot(name="intent-fixture", model="mock/demo", tools=[]))
    run = Run(bot_id=bot.id, prompt="fixture")
    if conversation:
        store.submit_conversation_message(conversation["id"], run.prompt, run, Task(bot_id=bot.id, prompt=run.prompt),
                                         idem_key=run.id, request_hash=run.id)
    else:
        store.create_run(run)
    run = store.claim_run(run.id, "intent-owner", 30)
    store.transition_run(run.id, RunStatus.running, fence=run.fence)
    return bot, run


def begin(store, run, **kw):
    return store.begin_action(run.id, "shell", "fixture-key", "process", "$ ./ship.sh", fence=run.fence,
                              arguments={"command": "./ship.sh"}, scope={"workspace": "/fixture"}, **kw)


def reconcile(store, action, *, key="record", outcome="not_applied", evidence="Verified destination has no effect", by="operator"):
    return store.reconcile_action(action["id"], intent_hash=action["intent_hash"], outcome=outcome, evidence=evidence,
                                  by=by, idem_key=key, request_hash=json.dumps([outcome, evidence]))


def test_intent_retains_private_snapshot_and_is_immutable(store):
    _, run = owned(store)
    args = {"command": "./ship.sh", "nested": {"destination": "fixture"}}
    action_id = store.begin_action(run.id, "shell", "key", "process", fence=run.fence, arguments=args)
    args["nested"]["destination"] = "changed"
    action = store.get_action(action_id)
    assert action["intent_valid"] and not action["legacy"]
    assert action["intent"]["arguments"]["nested"] == {"destination": "fixture"}
    for field, value in (("intent_json", "{}"), ("run_id", "other"), ("summary", "different")):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with store._tx() as db:
                db.execute(f"UPDATE tool_actions SET {field} = ? WHERE id = ?", (value, action_id))
    store.finish_action(action_id, "done", "digest", expected_fence=run.fence)
    with pytest.raises(sqlite3.IntegrityError, match="sealed"):
        with store._tx() as db:
            db.execute("UPDATE tool_actions SET status = 'unknown' WHERE id = ?", (action_id,))
    assert store.get_action(action_id)["status"] == "done"


def test_fence_omission_cannot_bypass_owned_action_writes(store):
    _, run = owned(store)
    with pytest.raises(LeaseLost, match="fence is required"):
        store.begin_action(run.id, "shell", "key", "process", arguments={})
    action = begin(store, run)
    with pytest.raises(LeaseLost, match="fence is required"):
        store.finish_action(action, "done")
    with pytest.raises(LeaseLost, match="fence is required"):
        store.mark_actions_unknown(run.id)
    with store._tx() as db:
        db.execute("UPDATE runs SET lease_expires_at = ? WHERE id = ?", (iso(utcnow()-timedelta(seconds=1)), run.id))
    with pytest.raises(LeaseLost, match="expired"):
        store.finish_action(action, "done", expected_fence=run.fence)
    assert store.get_action(action)["status"] == "started"


def test_completion_seals_uncertain_receipt_status_and_event_atomically(store, config, monkeypatch):
    _, run = owned(store)
    action_id = begin(store, run)
    observer = sqlite3.connect(config.db_path)
    original = store._insert_events
    seen = []
    def observe(db, run_id, events):
        seen.append((observer.execute("SELECT status FROM runs WHERE id = ?", (run.id,)).fetchone()[0],
                     observer.execute("SELECT status FROM tool_actions WHERE id = ?", (action_id,)).fetchone()[0]))
        original(db, run_id, events)
    monkeypatch.setattr(store, "_insert_events", observe)
    try:
        done = store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
        assert seen == [("running", "started")]
        assert done.status is RunStatus.outcome_unknown and done.exit_reason == "action_receipt_missing"
        assert store.get_action(action_id)["status"] == "unknown"
        assert store.list_events(run.id)[-1].data["status"] == "outcome_unknown"
        with pytest.raises(LeaseLost):
            store.finish_action(action_id, "done", expected_fence=run.fence)
    finally:
        observer.close()


def test_receipt_storage_failure_after_file_effect_cannot_report_done(store, config, monkeypatch):
    bot = store.create_bot(Bot(name="receipt-loss", model="mock/demo", tools=["files"], approval_mode=ApprovalMode.auto))
    engine = Engine(config, store)
    monkeypatch.setattr(store, "finish_action", lambda *a, **kw: (_ for _ in ()).throw(OSError("fixture receipt failure")))
    try:
        run = engine.run_blocking(bot, "write a report")
        assert run.status is RunStatus.outcome_unknown
        assert (Path(run.workspace) / "report.md").exists()
        [action] = store.list_actions(run.id)
        detail = store.get_action(action["id"])
        assert action["status"] == "unknown" and action["finished_at"] is None
        assert detail["intent"]["arguments"]["path"] == "report.md"
        assert detail["intent"]["authority"]["detail"]["revision"]
    finally:
        engine.shutdown()


def test_exception_after_effect_does_not_invent_a_failed_receipt(store, config, monkeypatch):
    from hutch.tools.files import FilesWriteTool
    original = FilesWriteTool.run
    def interrupted(tool, args, ctx):
        result = original(tool, args, ctx)
        assert result.ok
        raise RuntimeError('fixture crash after file effect')
    monkeypatch.setattr(FilesWriteTool, 'run', interrupted)
    bot = store.create_bot(Bot(name='exception-after-effect',model='mock/demo',tools=['files'],approval_mode=ApprovalMode.auto))
    engine = Engine(config,store)
    try:
        run = engine.run_blocking(bot,'write a report')
        assert run.status is RunStatus.outcome_unknown
        assert (Path(run.workspace)/'report.md').exists()
        [action] = store.list_actions(run.id)
        assert action['status'] == 'unknown' and not action['finished_at'] and not action['result_digest']
    finally:
        engine.shutdown()


def test_browser_exception_after_effect_keeps_receipt_unresolved(store, config, tmp_path, monkeypatch):
    from hutch.runtime.steps import call_tool
    from hutch.runtime.base import RunAborted
    from hutch.tools.browser import BrowserTool
    from tests.test_receipts import make

    run, ctx, _ = make(store, config, tmp_path, mode=ApprovalMode.auto, tools=("browser",))
    tool = BrowserTool()

    def click_then_timeout(action, args, context, decision):
        assert context.begin_effect() is None
        raise RuntimeError("fixture timeout after click dispatch")

    monkeypatch.setattr(tool, "_run_locked", click_then_timeout)
    with pytest.raises(RunAborted, match="may have been dispatched"):
        call_tool(run, ctx, {"browser": tool}, "browser", {"action": "click", "selector": "button"})

    [action] = store.list_actions(run.id)
    assert action["status"] == "started"
    sealed = store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
    assert sealed.status is RunStatus.outcome_unknown
    assert store.get_action(action["id"])["status"] == "unknown"


def test_browser_unverified_dispatch_result_keeps_receipt_unresolved(store, config, tmp_path, monkeypatch):
    from hutch.runtime.steps import call_tool
    from hutch.runtime.base import RunAborted
    from hutch.tools.base import ToolResult
    from hutch.tools.browser import BrowserTool
    from tests.test_receipts import make

    run, ctx, _ = make(store, config, tmp_path, mode=ApprovalMode.auto, tools=("browser",))
    tool = BrowserTool()

    def click_not_verified(action, args, context, decision):
        assert context.begin_effect() is None
        return ToolResult(False, "dispatch could not be verified", {"outcome": "unknown"})

    monkeypatch.setattr(tool, "_run_locked", click_not_verified)
    with pytest.raises(RunAborted, match="may have happened"):
        call_tool(run, ctx, {"browser": tool}, "browser", {"action": "click", "selector": "button"})

    [action] = store.list_actions(run.id)
    assert action["status"] == "started"
    sealed = store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
    assert sealed.status is RunStatus.outcome_unknown
    assert store.get_action(action["id"])["status"] == "unknown"


def test_reconciliation_is_once_and_does_not_rewrite_execution_history(store, config):
    _, run = owned(store)
    action_id = begin(store, run)
    store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
    action = store.get_action(action_id)
    before_run, before_events = store.get_run(run.id).model_dump(), store.list_events(run.id)
    recorded, created = reconcile(store, action)
    assert created and recorded["reconciliation"]["outcome"] == "not_applied"
    assert recorded["status"] == "unknown" and recorded["result_digest"] == ""
    assert store.actions_in_doubt(run.id) == []
    replay, created = reconcile(store, action)
    assert not created and replay == recorded
    with pytest.raises(IdempotencyConflict):
        reconcile(store, action, outcome="confirmed_done")
    with pytest.raises(ActionConflict, match="already recorded"):
        reconcile(store, action, key="second", by="other")
    assert store.get_run(run.id).model_dump() == before_run
    assert store.list_events(run.id) == before_events
    assert store.verify_chain(run.id)["ok"]
    other = Store(config)
    try:
        assert other.get_action(action_id)["reconciliation"] == recorded["reconciliation"]
    finally:
        other.close()


def test_uncertain_repeat_requires_reconciliation_without_crossing_private_conversations(store):
    bot = store.create_bot(Bot(name="intent-fixture", model="mock/demo", tools=[]))
    conv, _ = store.create_conversation(bot.id, "scope", idem_key="create", request_hash="create")
    _, first = owned(store, conversation=conv)
    action_id = begin(store, first)
    store.transition_run(first.id, RunStatus.succeeded, fence=first.fence)
    _, retry = owned(store, conversation=conv)
    with pytest.raises(ActionConflict, match="before repeating"):
        begin(store, retry)
    store.transition_run(retry.id, RunStatus.failed, fence=retry.fence)
    private, _ = store.create_conversation(bot.id, "separate", idem_key="separate", request_hash="separate")
    _, separate = owned(store, conversation=private)
    assert begin(store, separate)
    store.transition_run(separate.id, RunStatus.failed, fence=separate.fence)
    reconcile(store, store.get_action(action_id))
    _, retry = owned(store, conversation=conv)
    assert begin(store, retry)


def test_two_clients_cannot_record_different_outcomes(store, config):
    _, run = owned(store)
    action_id = begin(store, run)
    store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
    action = store.get_action(action_id)
    ready = threading.Barrier(2)
    results = []
    def record(outcome):
        client = Store(config)
        try:
            ready.wait(timeout=5)
            try:
                result, created = reconcile(client, action, key=outcome, outcome=outcome)
                results.append((result["reconciliation"]["outcome"], created))
            except ActionConflict:
                results.append(("conflict", False))
        finally:
            client.close()
    threads = [threading.Thread(target=record, args=(outcome,)) for outcome in ("not_applied", "confirmed_done")]
    for t in threads: t.start()
    for t in threads: t.join(10); assert not t.is_alive()
    assert len([r for r in results if r[1]]) == 1 and ("conflict", False) in results


def test_receipt_api_requires_reviewed_hash_evidence_and_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path/"state"))
    app = create_app()
    with TestClient(app) as client:
        store = app.state.store
        _, run = owned(store)
        action_id = begin(store, run)
        store.transition_run(run.id, RunStatus.succeeded, fence=run.fence)
        action = client.get(f"/api/v1/actions/receipts/{action_id}").json()
        assert action["intent_valid"] and action["intent"]["arguments"] == {"command": "./ship.sh"}
        summaries = client.get("/api/v1/actions/receipts?unresolved=true&limit=1").json()
        assert len(summaries) == 1 and "intent" not in summaries[0]
        url = f"/api/v1/actions/receipts/{action_id}/reconcile"
        body = {"intent_hash": action["intent_hash"], "outcome": "not_applied", "evidence": "Checked fixture destination"}
        assert client.post(url,json=body).status_code == 428
        headers = {"Idempotency-Key": "fixture-record"}
        assert client.post(url,json={**body,"intent_hash":"0"*64},headers=headers).status_code == 409
        assert client.post(url,json={**body,"evidence":" "},headers=headers).status_code == 422
        assert client.post(url,json={**body,"by":"invented verifier"},headers=headers).status_code == 422
        malformed = client.post(url, content=json.dumps({**body,'evidence':'private input\ud800'}),
                                headers={**headers,'Content-Type':'application/json'})
        assert malformed.status_code == 422
        assert 'private input' not in malformed.text and '"input"' not in malformed.text
        result = client.post(url,json=body,headers=headers)
        assert result.status_code == 201 and result.json()["reconciliation"]["recorded_by"] == "operator"
        assert client.post(url,json=body,headers=headers).status_code == 200
        assert client.post(url,json={**body,"outcome":"confirmed_done"},headers=headers).status_code == 409
        assert client.get("/api/v1/actions/receipts?unresolved=true").json() == []


def test_review_wait_freezes_executed_arguments_and_receipt_authority(store, config, tmp_path, monkeypatch):
    from hutch.approvals import resolve_approval_ex
    from hutch.runtime.steps import call_tool
    from tests.test_receipts import make
    run, ctx, tools = make(store, config, tmp_path)
    args = {"path": "reviewed.txt", "content": "reviewed content"}
    wait = ctx.gate._wait
    def human(req, action, **kw):
        args.update(path="unexpected.txt", content="unexpected")
        assert resolve_approval_ex(store, req.id, True, expected_hash=req.action_hash).won
        return wait(req, action, **kw)
    monkeypatch.setattr(ctx.gate, "_wait", human)
    assert call_tool(run, ctx, tools, "write_file", args).ok
    [receipt] = store.list_actions(run.id)
    intent = store.get_action(receipt["id"])["intent"]
    assert intent["arguments"] == {"path": "reviewed.txt", "content": "reviewed content"}
    assert intent["authority"]["source"] == "reviewed_once"
    assert intent["authority"]["detail"]["content"] == "reviewed content"
    assert (ctx.workspace/"reviewed.txt").read_text() == "reviewed content"
    assert not (ctx.workspace/"unexpected.txt").exists()


def test_expired_or_changed_review_cannot_start_an_effect(store, config, tmp_path, monkeypatch):
    from hutch.approvals import resolve_approval_ex
    from hutch.runtime.steps import call_tool
    from tests.test_receipts import make
    run, ctx, tools = make(store, config, tmp_path)
    wait = ctx.gate._wait
    def human(req, action, **kw):
        assert resolve_approval_ex(store, req.id, True, expected_hash=req.action_hash).won
        result = wait(req, action, **kw)
        with store._tx() as db:
            db.execute("UPDATE approvals SET expires_at = ? WHERE id = ?", (iso(utcnow()-timedelta(seconds=1)), req.id))
        return result
    monkeypatch.setattr(ctx.gate, "_wait", human)
    result = call_tool(run, ctx, tools, "write_file", {"path": "expired.txt", "content": "x"})
    assert not result.ok and "expired" in result.output
    assert store.list_actions(run.id) == [] and not (ctx.workspace/"expired.txt").exists()


def test_queued_turn_reads_current_receipt_guidance_and_does_not_share_private_arguments(store):
    bot = store.create_bot(Bot(name="intent-fixture", model="mock/demo", tools=[]))
    conv, _ = store.create_conversation(bot.id, "scope", idem_key="create", request_hash="create")
    _, first = owned(store, conversation=conv)
    queued = Run(bot_id=bot.id, prompt="Follow up")
    store.submit_conversation_message(conv["id"], queued.prompt, queued, Task(bot_id=bot.id, prompt=queued.prompt),
                                     idem_key="queued", request_hash="queued")
    assert not store.action_context(queued.id)
    action_id = store.begin_action(first.id, "shell", "private-key", "process", "private summary", fence=first.fence,
                                   arguments={"command": "sensitive destination"})
    store.transition_run(first.id, RunStatus.succeeded, fence=first.fence)
    guidance = store.action_context(queued.id)
    assert action_id in guidance and "unresolved" in guidance
    assert "sensitive destination" not in guidance and "private summary" not in guidance
    reconcile(store, store.get_action(action_id), evidence="private evidence")
    guidance = store.action_context(queued.id)
    assert "not_applied" in guidance and "private evidence" not in guidance
    other = Run(bot_id=bot.id, prompt="separate"); store.create_run(other)
    assert not store.action_context(other.id)


def test_real_process_crash_after_effect_preserves_intent_and_never_replays(store, config, tmp_path):
    from tests.test_cancel import spawn
    import os
    bot = store.create_bot(Bot(name="intent-crash", model="mock/demo", tools=[]))
    proc = spawn(config, f'''
        import os
        from pathlib import Path
        from hutch.config import get_config
        from hutch.store import Store
        from hutch.models import Run, RunStatus
        st = Store(get_config()); bot = st.get_bot("intent-crash")
        r = Run(bot_id=bot.id, prompt="effect fixture"); st.create_run(r)
        r = st.claim_run(r.id, "crashed-owner", 30)
        st.transition_run(r.id, RunStatus.running, fence=r.fence)
        a = st.begin_action(r.id, "write_file", "crash", "fs", fence=r.fence,
            arguments={{"path":"{tmp_path}/effect.txt","content":"one effect"}})
        with open("{tmp_path}/effect.txt", "w") as f:
            f.write("one effect"); f.flush(); os.fsync(f.fileno())
        print(r.id, a, flush=True)
        os._exit(23)
    ''')
    try:
        stdout, stderr = proc.communicate(timeout=10)
        assert proc.returncode == 23, stderr
        run_id, action_id = stdout.strip().split()
        with store._tx() as db:
            db.execute("UPDATE runs SET lease_expires_at = ? WHERE id = ?", (iso(utcnow()-timedelta(seconds=1)),run_id))
        engine = Engine(config, store)
        try:
            assert [r.id for r in engine.recover_orphans()] == [run_id]
            assert store.get_run(run_id).status is RunStatus.outcome_unknown
            assert store.get_action(action_id)["intent"]["arguments"]["content"] == "one effect"
            assert store.get_action(action_id)["status"] == "unknown"
            assert engine.recover_orphans() == []
            assert (tmp_path/"effect.txt").read_text() == "one effect"
        finally:
            engine.shutdown()
    finally:
        if proc.poll() is None: proc.kill(); proc.wait(timeout=5)


def test_actual_v12_upgrade_keeps_unknown_legacy_arguments_and_original_success(config):
    """Fixture made by git archive 4bdd936, not the current migration code."""
    import shutil
    fixture = Path(__file__).parent/'fixtures/state_v12_receipt.db.fixture'
    source = sqlite3.connect(fixture)
    try:
        assert source.execute('PRAGMA user_version').fetchone()[0] == 12
        before = source.execute("SELECT doc FROM runs WHERE id='run_legacy_receipt'").fetchone()[0]
        historic = source.execute("SELECT seq, hash FROM events WHERE run_id='run_legacy_receipt' ORDER BY seq").fetchall()
    finally:
        source.close()
    config.ensure(); shutil.copyfile(fixture, config.db_path)
    migrated = Store(config)
    try:
        [summary] = migrated.list_actions('run_legacy_receipt', unresolved=True)
        action = migrated.get_action(summary['id'])
        assert action['legacy'] and action['intent_valid'] and action['intent']['arguments'] is None
        assert migrated.count_unresolved_actions() == 1
        assert migrated.get_run('run_legacy_receipt').status is RunStatus.succeeded
        assert migrated._db.execute("SELECT doc FROM runs WHERE id='run_legacy_receipt'").fetchone()[0] == before
        assert [tuple(row) for row in migrated._db.execute("SELECT seq, hash FROM events WHERE run_id='run_legacy_receipt' ORDER BY seq")] == historic
        assert migrated.verify_chain('run_legacy_receipt')['ok']
        reconcile(migrated, action, outcome='confirmed_done', evidence='Checked sanitized historical destination')
        assert migrated.count_unresolved_actions() == 0
        assert migrated.get_action(action['id'])['status'] == 'started'
    finally:
        migrated.close()
    backup = sqlite3.connect(config.state_dir/'hutch.db.bak-v12')
    try:
        assert backup.execute('PRAGMA user_version').fetchone()[0] == 12
        assert backup.execute('SELECT status FROM tool_actions').fetchone()[0] == 'started'
    finally:
        backup.close()
