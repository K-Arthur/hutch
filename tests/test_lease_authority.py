"""A paused owner loses authority at expiry, even before a recoverer runs."""
from datetime import timedelta

import pytest

from hutch.lifecycle import LeaseLost
from hutch.models import ApprovalRequest, Bot, Event, EventType, Run, RunStatus, Task, iso, utcnow


def owned(store):
    bot = store.create_bot(Bot(name="lease-authority", model="mock/demo"))
    queued = store.create_run(Run(bot_id=bot.id, prompt="fixture"))
    run = store.claim_run(queued.id, "paused-owner", 30)
    store.transition_run(run.id, RunStatus.running, fence=run.fence)
    return bot, run


def expire(store, run):
    with store._tx() as db:
        db.execute("UPDATE runs SET lease_expires_at = ? WHERE id = ?", (iso(utcnow() - timedelta(seconds=1)), run.id))


@pytest.mark.parametrize("operation", ["action", "approval", "usage", "progress", "state", "pgid"])
def test_expiry_refuses_owned_mutations_before_any_takeover(store, operation):
    bot, run = owned(store)
    expire(store, run)
    run.steps = 100
    calls = {
        "action": lambda: store.begin_action(run.id, "files", "key", "fs", fence=run.fence),
        "approval": lambda: store.create_approval(ApprovalRequest(run_id=run.id, bot_id=bot.id, tool="files", action="fixture"),
                                                  expected_fence=run.fence),
        "usage": lambda: store.reserve_usage(run_id=run.id, bot_id=bot.id, provider="mock", account_id="fixture", model="demo",
                                               reserved_tokens=5, reserved_cost_usd=0, expected_fence=run.fence),
        "progress": lambda: store.update_run(run),
        "state": lambda: store.transition_run(run.id, RunStatus.succeeded, fence=run.fence),
        "pgid": lambda: store.set_pgid(run.id, run.fence, 12345),
    }
    with pytest.raises(LeaseLost, match="expired"):
        calls[operation]()
    after = store.get_run(run.id)
    assert after.fence == run.fence and after.status is RunStatus.running and after.steps == 0 and after.pgid == 0
    assert store.list_actions(run.id) == [] and store.pending_approvals() == []
    with store._lock:
        assert store._db.execute("SELECT COUNT(*) FROM usage_reservations WHERE run_id = ?", (run.id,)).fetchone()[0] == 0


def test_heartbeat_cannot_revive_expired_ownership_and_recovery_can_take_it(store):
    _, run = owned(store)
    before = store.get_run(run.id)
    future = utcnow() + timedelta(seconds=31)
    assert store.renew_leases(run.lease_owner, 30, now=future) == []
    expired = store.get_run(run.id)
    assert expired.lease_expires_at == before.lease_expires_at
    recovered = store.claim_recovery(expired, "new-supervisor", 30, now=future)
    assert recovered and recovered.fence == run.fence + 1
    assert store.renew_leases(run.lease_owner, 30, now=future) == []


def test_late_receipt_cannot_replace_recovered_unknown_outcome(store):
    _, run = owned(store)
    action = store.begin_action(run.id, "files", "fixture", "fs", fence=run.fence)
    expire(store, run)
    recovery = store.claim_recovery(store.get_run(run.id), "recoverer", 30)
    store.mark_actions_unknown(run.id)
    with pytest.raises(LeaseLost):
        store.finish_action(action, "done", "late-result", expected_fence=run.fence)
    store.transition_run(run.id, RunStatus.outcome_unknown, fence=recovery.fence)
    assert store.actions_in_doubt(run.id)[0]["id"] == action
    assert store.list_actions(run.id)[0]["status"] == "unknown"
    assert store.list_actions(run.id)[0]["result_digest"] == ""


@pytest.mark.parametrize("commit_path", ["writer", "recovery_transition"])
def test_expired_buffered_reply_cannot_enter_canonical_history(store, commit_path):
    bot = store.create_bot(Bot(name="expired-reply", model="mock/demo"))
    conv, _ = store.create_conversation(bot.id, "fixture", idem_key="create", request_hash="fixture")
    run = Run(bot_id=bot.id, prompt="fixture")
    store.submit_conversation_message(conv["id"], "fixture", run, Task(bot_id=bot.id, prompt="fixture"),
                                      idem_key="send", request_hash="fixture")
    run = store.claim_run(run.id, "paused-owner", 30)
    store.transition_run(run.id, RunStatus.running, fence=run.fence)
    # Hold the writer so the event is queued while authority is still valid,
    # then lapse ownership before either commit path can observe the batch.
    with store._buf_cv:
        store.append_event(Event(run_id=run.id, type=EventType.message,
                                 data={"role": "assistant", "content": "stale reply"}, owner_fence=run.fence))
        expire(store, run)
        if commit_path == "recovery_transition":
            recovery = store.claim_recovery(store.get_run(run.id), "new-supervisor", 30)
            store.transition_run(run.id, RunStatus.failed, fence=recovery.fence, event={"reason": "interrupted"})
    store.flush_events()
    assert not any(e.data.get("content") == "stale reply" for e in store.list_events(run.id))
    assert [m["role"] for m in store.list_conversation_messages(conv["id"])] == ["user"]
    assert store.dropped_events == 1 and store.verify_chain(run.id)["ok"]
