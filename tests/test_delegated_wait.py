"""Durable parent continuations for delegated child runs."""

import pytest

from hutch.engine import Engine
from hutch.models import Bot, Run, RunStatus, Task
from hutch.lifecycle import LeaseLost


def _parent_and_child(store):
    bot = store.create_bot(Bot(name="parked-delegator", model="mock/demo"))
    parent = store.submit_run(Run(bot_id=bot.id, prompt="coordinate"), Task(bot_id=bot.id, prompt="coordinate"))
    parent = store.claim_run(parent.id, "parent-owner", 60)
    assert parent is not None
    parent = store.transition_run(parent.id, RunStatus.running, fence=parent.fence,
                                  capability_snapshot=Engine.capability_snapshot(bot))
    child, inserted = store.submit_delegated_run(
        parent_run_id=parent.id, parent_fence=parent.fence,
        run=Run(bot_id=bot.id, prompt="inspect one area"),
        task=Task(bot_id=bot.id, kind="delegated", prompt="inspect one area"),
        idem_key="stable-child-call", request_hash="stable-child-input",
    )
    assert inserted
    return parent, child


def test_child_wait_is_fenced_durable_and_resumes_only_after_cleanup(store):
    parent, child = _parent_and_child(store)
    parent_pid = 987653
    worker_pid = 987654
    store.add_proc(parent.id, parent_pid, parent_pid, 1, "worker", "test-boot")
    payload = {
        "version": 1,
        "messages": [{"role": "system", "content": "exact prompt"}],
        "tool_call": {"id": "call-delegate", "name": "delegate_task", "arguments": {"task": "inspect one area"}},
        "plan_hash": "plan-v1",
        "profile_hash": "profile-v1",
    }

    parked = store.transition_run(
        parent.id, RunStatus.waiting_child, fence=parent.fence,
        child_wait=(child.id, payload), event={"reason": "delegated child is running"},
    )
    assert parked.status is RunStatus.waiting_child
    assert parked.lease_owner == ""
    assert store.child_wait_authorizes(parent.id, child.id)
    assert store.promote_child_wait(parent.id) is None
    assert store.claim_run(child.id, "early-child-owner", 60, max_live=2) is None
    store.end_proc(parent.id, parent_pid)

    with pytest.raises(LeaseLost):
        store.transition_run(parent.id, RunStatus.succeeded, fence=parent.fence)

    child = store.claim_run(child.id, "child-owner", 60)
    assert child is not None
    store.add_proc(child.id, worker_pid, worker_pid, 1, "worker", "test-boot")
    child = store.transition_run(child.id, RunStatus.running, fence=child.fence)
    store.transition_run(child.id, RunStatus.succeeded, fence=child.fence, exit_reason="completed")
    assert store.promote_child_wait(parent.id) is None, "a completed child process still owns recorded work"

    store.end_proc(child.id, worker_pid)
    resumed = store.promote_child_wait(parent.id)
    assert resumed is not None and resumed.id == parent.id
    assert resumed.status is RunStatus.pending
    assert resumed.fence > parent.fence
    checkpoint = store.child_wait_continuation(parent.id)
    assert checkpoint is not None and checkpoint["state"] == "ready"
    assert checkpoint["payload"] == payload

    claimed = store.claim_run(parent.id, "resumed-parent", 60)
    assert claimed is not None
    claimed = store.transition_run(claimed.id, RunStatus.running, fence=claimed.fence)
    live_checkpoint = store.child_wait_continuation(parent.id, expected_fence=claimed.fence)
    assert live_checkpoint is not None and live_checkpoint["child_run_id"] == child.id
    assert live_checkpoint["payload"] == payload


def test_stopping_a_parked_parent_waits_for_its_child_then_finishes(store):
    parent, child = _parent_and_child(store)
    store.transition_run(
        parent.id, RunStatus.waiting_child, fence=parent.fence,
        child_wait=(child.id, {"version": 1, "messages": [], "tool_call": {}}),
    )
    cancelled = store.request_cancel_tree(parent.id)
    assert cancelled is not None
    assert store.get_run(parent.id).status is RunStatus.cancelling
    assert store.get_run(child.id).status is RunStatus.stopped

    child = store.get_run(child.id)
    final = store.finalize_child_wait_cancel(parent.id)
    assert final is not None and final.status is RunStatus.stopped
    assert final.finished_at
    checkpoint = store.child_wait_continuation(parent.id)
    assert checkpoint is not None and checkpoint["state"] == "cancelled"


def test_one_slot_dispatch_waits_until_parked_parent_process_is_closed(store):
    parent, child = _parent_and_child(store)
    parent_pid = 987653
    store.add_proc(parent.id, parent_pid, parent_pid, 1, "worker", "test-boot")
    assert store.claim_run(child.id, "one-slot-child", 60, max_live=1) is None

    store.transition_run(
        parent.id, RunStatus.waiting_child, fence=parent.fence,
        child_wait=(child.id, {"version": 1, "messages": [], "tool_call": {}}),
    )
    assert store.claim_run(child.id, "one-slot-child", 60, max_live=1) is None
    store.end_proc(parent.id, parent_pid)
    assert store.claim_run(child.id, "one-slot-child", 60, max_live=1) is not None
