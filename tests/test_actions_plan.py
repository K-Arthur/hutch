"""Action-plan and execution-engine tests with fake executors (no I/O)."""

from __future__ import annotations

import pytest

from hutch.actions.execute import (
    ApprovalMismatch,
    ExecutorResult,
    execute_plan,
    plan_outcome_report,
)
from hutch.actions.plan import (
    ActionPlan,
    PlanTarget,
    approval_scope_hash,
    build_plan,
    plan_review,
)


def _specs():
    return [
        {
            "kind": "local_draft", "title": "Draft the brief",
            "target": {"service": "synthesis", "display": "meeting brief v1"},
            "inputs": {"manifest": "syn_a", "format": "brief"},
        },
        {
            "kind": "cloud_create", "title": "Create the Google Doc",
            "target": {"service": "docs", "account": "gws_aaa", "parent_id": "folder1",
                       "display": "Docs: 'Thursday brief' in folder1"},
            "inputs": {"title": "Thursday brief", "body_markdown": "..."},
            "depends_on": [],
        },
        {
            "kind": "cloud_create", "title": "Create the tracker sheet",
            "target": {"service": "sheets", "account": "gws_aaa", "parent_id": "folder1",
                       "display": "Sheets: 'Tracker' in folder1"},
            "inputs": {"title": "Tracker", "columns": ["name", "value"]},
        },
        {
            "kind": "notify", "title": "Email attendees",
            "target": {"service": "calendar", "account": "gcal_bbb",
                       "display": "invite a@example.com", "audience": "attendees"},
            "inputs": {"emails": ["a@example.com"]},
        },
    ]


def _plan(**kw):
    return build_plan("Prepare Thursday's meeting package", _specs(),
                      conversation_id="conv_1", bot_id="bot_1", **kw)


class _Recorder:
    def __init__(self, results=None):
        self.calls: list[str] = []
        self.results = results or {}

    def executor(self, kind):
        def run(step, plan):
            self.calls.append(f"{kind}:{step.index}")
            outcome = self.results.get(step.index)
            if outcome is not None:
                return outcome
            return ExecutorResult(ok=True, remote_id=f"{kind}-{step.index}",
                                  result={"kind": kind})
        return run


def test_build_plan_validates_and_auto_keys():
    plan = _plan()
    assert [s.status for s in plan.steps] == ["pending"] * 4
    assert plan.steps[0].idempotency_key == ""  # local draft: no remote effect
    assert plan.steps[1].idempotency_key.startswith(plan.id)
    assert plan.steps[2].is_separate_authority is False
    assert plan.steps[3].is_separate_authority is True

    with pytest.raises(ValueError):
        build_plan("x", [])
    bad = _specs()
    bad[1]["depends_on"] = ["stp_missing"]
    with pytest.raises(ValueError):
        build_plan("x", bad)
    a = {"kind": "read", "id": "same", "target": {"service": "docs"}}
    b = {"kind": "read", "id": "same", "target": {"service": "docs"}}
    with pytest.raises(ValueError):
        build_plan("x", [a, b])
    cyc1 = {"kind": "read", "id": "a", "target": {"service": "docs"}, "depends_on": ["b"]}
    cyc2 = {"kind": "read", "id": "b", "target": {"service": "docs"}, "depends_on": ["a"]}
    with pytest.raises(ValueError):
        build_plan("x", [cyc1, cyc2])


def test_review_and_hash_bind_to_content():
    plan = _plan()
    review = plan_review(plan)
    assert review["separate_authority_steps"] == [plan.steps[3].id]
    assert review["approval_scope_hash"] == plan.approval_scope_hash
    original = plan.approval_scope_hash

    plan.steps[1].inputs["title"] = "Thursday brief v2"
    plan.recompute_approval_scope()
    assert plan.approval_scope_hash != original
    # and the old hash no longer matches
    with pytest.raises(ApprovalMismatch):
        execute_plan(plan, store=None, executors={}, approved_hash=original)


def test_execute_happy_path_with_separate_authority(store):
    plan = _plan()
    rec = _Recorder()
    executors = {k: rec.executor(k) for k in
                 ("local_draft", "cloud_create", "notify")}
    result = execute_plan(plan, store=store, executors=executors,
                          approved_hash=plan.approval_scope_hash,
                          separately_approved={plan.steps[3].id})
    assert result.status == "completed"
    assert all(s.status == "succeeded" for s in result.steps)
    assert result.steps[3].remote_id == "notify-3"

    # Journaled steps produced effect rows; the local draft did not.
    effects = store.list_synthesis_effects(plan_id=plan.id)
    kinds = sorted(e["kind"] for e in effects)
    assert kinds == ["cloud_create", "cloud_create", "notify"]
    assert all(e["status"] == "succeeded" for e in effects)

    saved = store.get_action_plan(plan.id)
    assert saved["status"] == "completed" and saved["doc"]["steps"][1]["remote_id"] == "cloud_create-1"

    report = plan_outcome_report(result)
    assert report["counts"]["succeeded"] == 4 and report["remaining"] == []


def test_separate_authority_is_denied_without_its_own_grant(store):
    plan = _plan()
    rec = _Recorder()
    executors = {k: rec.executor(k) for k in ("local_draft", "cloud_create", "notify")}
    result = execute_plan(plan, store=store, executors=executors,
                          approved_hash=plan.approval_scope_hash)
    assert result.status == "partial"
    assert result.steps[3].status == "denied"
    assert "own approval" in result.steps[3].error
    assert "notify:3" not in rec.calls  # the share/notify executor never ran


def test_partial_failure_keeps_successes_and_retry_reruns_only_failed(store):
    plan = _plan()
    rec = _Recorder(results={
        2: ExecutorResult(ok=False, error="quota exceeded"),
    })
    executors = {k: rec.executor(k) for k in ("local_draft", "cloud_create", "notify")}
    result = execute_plan(plan, store=store, executors=executors,
                          approved_hash=plan.approval_scope_hash,
                          separately_approved={plan.steps[3].id})
    assert result.status == "partial"
    assert result.steps[2].status == "failed"
    assert result.steps[1].status == "succeeded"
    first_calls = list(rec.calls)

    rec.results = {}
    again = execute_plan(plan, store=store, executors=executors,
                         approved_hash=plan.approval_scope_hash,
                         separately_approved={plan.steps[3].id}, retry_failed=True)
    assert again.status == "completed"
    # only the previously-failed step ran again; successes were not repeated
    assert rec.calls[len(first_calls):] == ["cloud_create:2"]
    effect = store.find_synthesis_effect(plan.steps[2].idempotency_key)
    assert effect["status"] == "succeeded"


def test_uncertain_outcome_is_never_retried_automatically(store):
    plan = _plan()
    rec = _Recorder(results={
        1: ExecutorResult(ok=False, uncertain=True, error="read timeout after send",
                          remote_id="maybe-doc-1"),
    })
    executors = {k: rec.executor(k) for k in ("local_draft", "cloud_create", "notify")}
    result = execute_plan(plan, store=store, executors=executors,
                          approved_hash=plan.approval_scope_hash,
                          separately_approved={plan.steps[3].id})
    assert result.steps[1].status == "uncertain"
    assert result.steps[1].remote_id == "maybe-doc-1"
    assert result.status == "partial"

    calls_after_first = list(rec.calls)
    second = execute_plan(plan, store=store, executors=executors,
                          approved_hash=plan.approval_scope_hash,
                          separately_approved={plan.steps[3].id})
    assert second.steps[1].status == "uncertain"
    assert rec.calls == calls_after_first  # nothing was re-sent
    assert store.find_synthesis_effect(plan.steps[1].idempotency_key)["status"] == "uncertain"


def test_executor_verification_failure_preserves_remote_id(store):
    plan = _plan()
    rec = _Recorder(results={
        1: ExecutorResult(ok=True, remote_id="doc_123",
                          verification=["expected text not found in tab"]),
    })
    executors = {k: rec.executor(k) for k in ("local_draft", "cloud_create", "notify")}
    result = execute_plan(plan, store=store, executors=executors,
                          approved_hash=plan.approval_scope_hash,
                          separately_approved={plan.steps[3].id})
    step = result.steps[1]
    assert step.status == "failed" and step.remote_id == "doc_123"
    assert "verification failed" in step.error
    effect = store.find_synthesis_effect(step.idempotency_key)
    assert effect["status"] == "failed" and effect["remote_id"] == "doc_123"
    assert effect["result_json"]["verification"] == ["expected text not found in tab"]
    # a dependent of the failed step would be skipped — verify with a plan that has one
    assert result.steps[2].status == "succeeded"


def test_failed_dependency_skips_dependents(store):
    specs = [
        {"kind": "cloud_create", "title": "create doc", "id": "s1",
         "target": {"service": "docs"}, "inputs": {"title": "x"}},
        {"kind": "cloud_edit", "title": "append section", "id": "s2",
         "target": {"service": "docs"}, "inputs": {"text": "y"}, "depends_on": ["s1"]},
    ]
    plan = build_plan("x", specs)
    rec = _Recorder(results={0: ExecutorResult(ok=False, error="nope")})
    executors = {"cloud_create": rec.executor("cloud_create"),
                 "cloud_edit": rec.executor("cloud_edit")}
    result = execute_plan(plan, store=store, executors=executors,
                          approved_hash=plan.approval_scope_hash)
    assert result.steps[0].status == "failed"
    assert result.steps[1].status == "skipped" and "dependency" in result.steps[1].error
    assert "cloud_edit:1" not in rec.calls


def test_missing_executor_is_a_failed_step_not_a_crash(store):
    plan = _plan()
    result = execute_plan(plan, store=store, executors={"local_draft": _Recorder().executor("local_draft")},
                          approved_hash=plan.approval_scope_hash)
    assert result.steps[1].status == "failed"
    assert "no executor" in result.steps[1].error


def test_dry_run_sends_nothing_and_persists_nothing(store):
    plan = _plan()
    rec = _Recorder()
    result = execute_plan(plan, store=store,
                          executors={k: rec.executor(k) for k in ("local_draft", "cloud_create", "notify")},
                          approved_hash=plan.approval_scope_hash, dry_run=True)
    assert result.status == "approved"
    assert rec.calls == []
    assert store.get_action_plan(plan.id) is None
    assert store.list_synthesis_effects(plan_id=plan.id) == []
