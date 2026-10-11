"""The owned orchestration attempt.

An attempt is an ordinary ``runs`` row (``kind='workflow'``) executed by the existing
worker/supervisor machinery, so it inherits one owned process, a lease and fence, honest
terminal states, cancellation and the transcript. What runs inside it is the deterministic
interpreter: it decides node by node, dispatches model work as child step runs, waits for
them without holding an inference seat, and settles the instance when the plan is done.

Recovery is a *continuation*, never a replay: if the attempt process dies, the supervisor
admits a new attempt for the same instance; the interpreter then skips every settled node
record and only does what is genuinely outstanding. Effects already receipted are never
repeated, and a plan revision change is an amendment (a new instance), not a resume.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from ..models import Event, EventType, Run, RunStatus
from ..runtime.base import RunAborted
from . import persistence as wstore
from .compile import compile_plan
from .engine import Advance, Interpreter

class WorkflowRuntime:
    """Adapter so ``Engine._execute`` can run a workflow attempt like any other runtime."""

    kind = "workflow"

    def __init__(self, engine: Any):
        self.engine = engine

    def execute(self, run: Run, ctx: Any, tools: dict[str, Any], stop: Any) -> str:
        return run_attempt(self.engine, ctx, run, tools, stop)


def run_attempt(engine: Any, ctx: Any, run: Run, tools: dict[str, Any], stop: Any) -> str:
    store = engine.store
    workflow = wstore.workflow_run_by_attempt(store, run.id)
    if workflow is None:
        raise RunAborted("error", "this attempt has no workflow instance; nothing can be executed")
    wf_id = str(workflow["id"])
    revision_id = str(workflow["revision_id"])
    if not wstore.claim_workflow_attempt(store, wf_id, run.id,
                                         owner_fence=run.fence, revision_id=revision_id):
        raise RunAborted("stopped", "the workflow instance is stopped or owned by another attempt")

    revision = wstore.revision(store, str(workflow["revision_id"]))
    if revision is None:
        _settle(store, wf_id, run, revision_id=revision_id,
                status="failed", reason="the plan revision is missing")
        raise RunAborted("error", "the workflow's plan revision no longer exists")
    compiled = compile_plan(revision["plan"])  # the stored revision is immutable: recompile is exact
    budget = dict(workflow.get("budget") or {})
    interp = Interpreter(engine=engine, ctx=ctx, run=run, compiled=compiled, workflow=workflow,
                         tools=tools, budget=budget)

    # The wall-clock allowance belongs to the *instance*: a continuation gets what is left,
    # never a fresh allowance (a repeated crash must not extend it without bound).
    deadline = _instance_deadline(workflow, budget)
    ctx.emit(Event(run_id=run.id, type=EventType.log,
                   data={"workflow": wf_id, "plan": compiled.plan.name,
                         "plan_hash": compiled.plan_hash, "revision": revision["revision"],
                         "budget": budget, "attempt": run.id,
                         "nodes": len(compiled.nodes)}))
    while True:
        if stop():
            raise RunAborted("stopped", "the workflow attempt was stopped")
        if time.monotonic() > deadline:
            _settle(store, wf_id, run, revision_id=revision_id,
                    status="failed", reason="the workflow exceeded its wall-clock budget")
            raise RunAborted("error", "the workflow exceeded its wall-clock budget")
        fresh = wstore.workflow_run(store, wf_id)
        if fresh is None:
            raise RunAborted("error", "the workflow instance disappeared")
        if fresh.get("stop_requested"):
            raise RunAborted("stopped", "a stop was requested for this workflow")
        interp.workflow = fresh

        advance: Advance = interp.advance()
        if advance.kind == "wait":
            pending = [q for q in wstore.questions(store, wf_id, status="pending")]
            reason = f"waiting for {len(pending)} answer(s)" if pending else "waiting for child workflow work"
            wstore.update_workflow_run(store, wf_id, attempt_run_id=run.id,
                                       owner_fence=run.fence, revision_id=revision_id,
                                       status="waiting",
                                       reason=reason)
            raise RunAborted("workflow_wait", reason)
        if advance.kind == "failed":
            _settle(store, wf_id, run, revision_id=revision_id,
                    status="failed", reason=advance.detail)
            ctx.emit(Event(run_id=run.id, type=EventType.error, data={"error": advance.detail}))
            raise RunAborted("error", f"the workflow failed: {advance.detail}")

        digest = _digest(compiled, interp, advance)
        _settle(store, wf_id, run, revision_id=revision_id,
                status="succeeded", reason="")
        return digest["text"]


def _instance_deadline(workflow: dict[str, Any], budget: dict[str, Any]) -> float:
    from datetime import datetime, timezone

    allowance = float(budget.get("max_wall_seconds") or 3_600)
    created = str(workflow.get("created_at") or "")
    try:
        started = datetime.fromisoformat(created)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    except (TypeError, ValueError):
        elapsed = 0.0
    return time.monotonic() + max(0.0, allowance - max(0.0, elapsed))


def _artifact_list(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        if node["status"] != "succeeded":
            continue
        result = node.get("result")
        if isinstance(result, dict):
            out.extend(item for item in (result.get("artifacts") or []) if isinstance(item, dict))
    return out


def _settle(store: Any, wf_id: str, run: Run, *, revision_id: str,
            status: str, reason: str) -> None:
    nodes = wstore.nodes(store, wf_id)
    counts: dict[str, int] = {}
    for node in nodes:
        counts[node["status"]] = counts.get(node["status"], 0) + 1
    result = {"counts": counts, "artifacts": _artifact_list(nodes)}
    wstore.update_workflow_run(
        store, wf_id, attempt_run_id=run.id, owner_fence=run.fence,
        revision_id=revision_id,
        status=status, reason=reason[:500], result=result, finished=True)
    if status != "succeeded":
        wstore.cancel_questions(store, wf_id)


def _digest(compiled: Any, interp: Interpreter, advance: Advance) -> dict[str, Any]:
    """A short, human-readable completion summary - built from engine records, not claims."""
    nodes = wstore.nodes(interp.store, interp.wf_id)
    counts: dict[str, int] = {}
    for node in nodes:
        counts[node["status"]] = counts.get(node["status"], 0) + 1
    published = _artifact_list(nodes)
    lines = [f"Workflow {compiled.plan.name!r} finished.",
             f"Nodes: " + ", ".join(f"{state} {count}" for state, count in sorted(counts.items())) or "none"]
    if published:
        lines.append("Published artifacts:")
        lines.extend(f"- {item['name']} ({item['bytes']} bytes, sha256 {item['sha256'][:12]}…)"
                     for item in published)
    if advance.verified is True:
        lines.append("Verification: passed with independent evidence.")
    elif advance.verified is False:
        lines.append("Verification: NOT established (the plan continued with an unverified result).")
    outputs = advance.result.get("outputs") or {}
    for site, value in outputs.items():
        text = value if isinstance(value, str) else str(value)
        lines.append(f"Output {site}: {text[:600]}")
    return {"text": "\n".join(lines)[:8_000]}
