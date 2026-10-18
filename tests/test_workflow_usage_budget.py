"""Root workflow budgets count durable provider requests and token commitments."""
from __future__ import annotations

import pytest

from hutch.engine import Engine
from hutch.models import RunStatus
from hutch.store import UsageBudgetRefusal
from hutch.workflow import persistence as wstore
from hutch.workflow import submit as wfsubmit
from tests.fakes import FakeOllama, agent_script
from tests.test_workflow_engine import drive, make_bot


@pytest.fixture()
def ollama(monkeypatch):
    server = FakeOllama({"tiny:1b": {"params": "1.0B", "size": 800_000_000, "ctx": 8192}})
    server.script = agent_script([
        {"content": "", "tool_calls": [{"name": "list_files", "arguments": {"path": "."}}]},
        {"content": "done"},
    ])
    monkeypatch.setenv("OLLAMA_HOST", server.url)
    yield server
    server.close()


def _active_workflow(store, *, name: str, max_calls: int, max_tokens: int):
    bot = make_bot(store, name=name, model="ollama/tiny:1b", tools=[], selfcheck=False)
    plan = {
        "name": name,
        "envelope": {"tools": [], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 8, "max_model_calls": max_calls, "max_tokens": max_tokens,
                   "max_wall_seconds": 120},
        "nodes": [{"kind": "transform", "id": "done", "op": "constant", "args": {"value": True}}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    owner = f"usage-owner-{name}"
    run = store.claim_run(submission.attempt_run_id, owner, 120)
    assert run is not None
    run = store.transition_run(run.id, RunStatus.running, fence=run.fence)
    workflow = wstore.workflow_run(store, submission.workflow_run_id)
    assert workflow is not None
    assert wstore.claim_workflow_attempt(store, submission.workflow_run_id,
                                         owner_fence=run.fence,
                                         revision_id=workflow["revision_id"],
                                         attempt_run_id=run.id)
    return bot, run, workflow


def _reserve(store, bot, run, tokens: int) -> str:
    return store.reserve_usage(run_id=run.id, bot_id=bot.id, provider="ollama",
                              account_id="local-test", model="tiny:1b",
                              reserved_tokens=tokens, reserved_cost_usd=0,
                              expected_fence=run.fence)


def test_retries_and_uncertain_requests_charge_the_same_root_budget(store):
    bot, run, workflow = _active_workflow(store, name="usage-retries", max_calls=2, max_tokens=60)

    first = _reserve(store, bot, run, 30)
    assert store.start_usage_request(first, expected_fence=run.fence)
    assert store.mark_usage_uncertain(first, "provider timed out after dispatch", expected_fence=run.fence)
    view = wstore.workflow_run(store, workflow["id"])
    assert view["ledger"]["model_calls"] == 1
    assert view["ledger"]["model_tokens"] == 30

    retry = _reserve(store, bot, run, 25)
    assert store.start_usage_request(retry, expected_fence=run.fence)
    store.add_usage(run.id, bot.id, "ollama", "tiny:1b", 10, 8,
                    reservation_id=retry, expected_fence=run.fence)
    view = wstore.workflow_run(store, workflow["id"])
    assert view["ledger"]["model_calls"] == 2
    assert view["ledger"]["model_tokens"] == 48  # uncertain estimate + reported retry usage

    with pytest.raises(UsageBudgetRefusal, match="max_model_calls"):
        _reserve(store, bot, run, 1)


def test_unstarted_reservations_release_and_reported_tokens_bound_retries(store):
    bot, run, workflow = _active_workflow(store, name="usage-tokens", max_calls=4, max_tokens=40)

    unused = _reserve(store, bot, run, 30)
    assert store.release_usage_reservation(unused, "stopped before dispatch", expected_fence=run.fence)
    assert wstore.workflow_run(store, workflow["id"])["ledger"].get("model_calls", 0) == 0

    first = _reserve(store, bot, run, 30)
    assert store.start_usage_request(first, expected_fence=run.fence)
    store.add_usage(run.id, bot.id, "ollama", "tiny:1b", 14, 10,
                    reservation_id=first, expected_fence=run.fence)
    # The first request settles to its reported 24 tokens; the second uses an estimate
    # because that is all Hutch can know before sending it.
    with pytest.raises(UsageBudgetRefusal, match="max_tokens"):
        _reserve(store, bot, run, 17)
    assert wstore.workflow_run(store, workflow["id"])["ledger"]["model_tokens"] == 24


def test_each_provider_reservation_can_cross_dispatch_boundary_only_once(store):
    bot, run, _workflow = _active_workflow(store, name="usage-one-start", max_calls=2, max_tokens=100)
    reservation = _reserve(store, bot, run, 20)
    assert store.start_usage_request(reservation, expected_fence=run.fence) is True
    assert store.start_usage_request(reservation, expected_fence=run.fence) is False
    with pytest.raises(ValueError, match="started provider request"):
        store.release_usage_reservation(reservation, "try to release", expected_fence=run.fence)


def test_actual_multi_turn_worker_requests_are_counted_in_the_root_ledger(store, config, ollama):
    bot = make_bot(store, name="usage-worker", model="ollama/tiny:1b", tools=["files"], selfcheck=False)
    engine = Engine(config, store)
    plan = {
        "name": "usage-worker",
        "envelope": {"tools": ["list_files"], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 8, "max_model_calls": 2, "max_tokens": 64_000,
                   "max_wall_seconds": 120},
        "nodes": [{"kind": "agent", "id": "answer", "model": "ollama/tiny:1b",
                   "instruction": "List files, then answer.", "tools": ["list_files"], "max_steps": 3}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    drive(engine, store, submission.attempt_run_id, timeout=120)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert view["workflow"]["ledger"]["model_calls"] == 2
    assert view["workflow"]["ledger"]["model_tokens"] > 0
    assert len(ollama.of("/api/chat")) == 2


def test_uncached_local_selfcheck_is_charged_to_the_workflow_root(store, config, ollama):
    bot = make_bot(store, name="usage-selfcheck", model="ollama/tiny:1b", tools=["files"],
                   selfcheck=True, num_ctx=8192)
    engine = Engine(config, store)
    plan = {
        "name": "usage-selfcheck",
        "envelope": {"tools": ["list_files"], "models": ["ollama/tiny:1b"]},
        "budget": {"max_nodes": 8, "max_model_calls": 3, "max_tokens": 64_000,
                   "max_wall_seconds": 120},
        "nodes": [{"kind": "agent", "id": "answer", "model": "ollama/tiny:1b",
                   "instruction": "List files, then answer.", "tools": ["list_files"], "max_steps": 3}],
    }
    submission = wfsubmit.submit_workflow(store, bot=bot, plan=plan)
    drive(engine, store, submission.attempt_run_id, timeout=120)
    view = wfsubmit.status(store, submission.workflow_run_id)
    assert view["workflow"]["status"] == "succeeded", view["workflow"]["reason"]
    assert view["workflow"]["ledger"]["model_calls"] == 3
    assert len(ollama.of("/api/chat")) == 3


def test_nested_delegated_model_request_inherits_workflow_budget_and_owner(store):
    bot, root, workflow = _active_workflow(store, name="usage-delegation", max_calls=2, max_tokens=100)
    wstore.open_node(store, workflow["id"], owner_run_id=root.id, owner_fence=root.fence,
                     revision_id=workflow["revision_id"], site_id="done", instance_key="once",
                     kind="agent", input_value={}, input_hash="c" * 64)

    from hutch.engine import Engine
    from hutch.models import Run, Task

    step = Run(bot_id=bot.id, prompt="bounded workflow node")
    step.workflow_step = {
        "workflow_run_id": workflow["id"], "revision_id": workflow["revision_id"],
        "parent_fence": root.fence, "site_id": "done", "instance_key": "once",
        "role": "worker", "tools": [], "skills": [], "model": bot.model,
        "max_steps": 2, "timeout_seconds": 60, "instruction_hash": "d" * 64,
    }
    step, inserted = wstore.submit_step_run(
        store, workflow_run_id=workflow["id"], site_id="done", instance_key="once", run=step,
        task=Task(bot_id=bot.id, kind="step", prompt=step.prompt), parent_run_id=root.id,
        parent_fence=root.fence, idem_key="usage-step", request_hash="step-input")
    assert inserted
    step = store.claim_run(step.id, "usage-step-owner", 60)
    assert step is not None
    step = store.transition_run(step.id, RunStatus.running, fence=step.fence,
                                capability_snapshot=Engine.capability_snapshot(bot))

    child = Run(bot_id=bot.id, prompt="delegated model request",
                workflow_run_id=workflow["id"], workflow_context=step.workflow_step)
    child, inserted = store.submit_delegated_run(
        parent_run_id=step.id, parent_fence=step.fence, run=child,
        task=Task(bot_id=bot.id, kind="delegated", prompt=child.prompt),
        idem_key="usage-delegated", request_hash="delegated-input")
    assert inserted and child.workflow_run_id == workflow["id"]
    assert child.workflow_context["site_id"] == "done"
    child = store.claim_run(child.id, "usage-delegated-owner", 60)
    assert child is not None
    child = store.transition_run(child.id, RunStatus.running, fence=child.fence)

    reservation = _reserve(store, bot, child, 20)
    assert store.start_usage_request(reservation, expected_fence=child.fence)
    assert wstore.workflow_run(store, workflow["id"])["ledger"]["model_calls"] == 1
