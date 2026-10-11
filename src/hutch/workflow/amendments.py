"""Read-only workflow amendment previews.

The preview deliberately errs toward invalidating results when the runtime cannot prove
that a binding or execution profile was recorded. Adoption is a separate, fenced action;
this module never changes a workflow run or saves a new revision.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import persistence as wstore
from .compile import CompiledNode, compile_plan
from .submit import PlanNotSubmittable, check_authority, validate_inputs


class AmendmentConflict(ValueError):
    """The preview was based on a stale workflow revision or owner generation."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _node_payload(node: CompiledNode) -> dict[str, Any]:
    return node.node.model_dump(by_alias=True, exclude_none=True, mode="json")


def _node_signature(node: CompiledNode) -> str:
    return _digest({
        "node": _node_payload(node),
        "deps": sorted(node.deps),
        "control_deps": sorted(node.control_deps),
        "body_of": node.body_of,
        "body_name": node.body_name,
        "instances": node.instances,
    })


def _field_diff(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"field": key, "old": old.get(key), "new": new.get(key)}
            for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)]


def preview(store: Any, *, workflow_run_id: str, plan: dict[str, Any],
            expected_revision_id: str, expected_generation: str,
            inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare a candidate plan with one current workflow generation, without mutation.

    ``generation_id`` is the active orchestration attempt ID. It changes whenever the
    supervisor replaces that attempt, which makes an old preview fail closed even when
    the immutable plan revision itself did not change.
    """
    workflow = wstore.workflow_run(store, workflow_run_id)
    if workflow is None:
        raise KeyError(workflow_run_id)
    generation_id = str(workflow.get("attempt_run_id") or "")
    revision_id = str(workflow.get("revision_id") or "")
    if revision_id != expected_revision_id:
        raise AmendmentConflict("the workflow revision changed; refresh before previewing an amendment")
    if not generation_id or generation_id != expected_generation:
        raise AmendmentConflict("the workflow generation changed; refresh before previewing an amendment")

    current_revision = wstore.revision(store, revision_id)
    if current_revision is None:
        raise AmendmentConflict("the current workflow revision is unavailable")
    current = compile_plan(current_revision["plan"])
    candidate = compile_plan(plan)
    saved_inputs = dict(workflow.get("inputs") or {})
    effective_inputs = validate_inputs(candidate.plan, saved_inputs if inputs is None else inputs)
    bot = store.get_bot(str(workflow["bot_id"]))
    blocked_reasons: list[str] = []
    roles: list[dict[str, Any]] = []
    if bot is None:
        blocked_reasons.append("the workflow's assistant is unavailable")
    else:
        try:
            roles = check_authority(candidate, bot, store=store)
        except PlanNotSubmittable as exc:
            blocked_reasons.append(str(exc))

    old_sites = {node.site_id: node for node in current.nodes}
    new_sites = {node.site_id: node for node in candidate.nodes}
    old_signatures = {site: _node_signature(node) for site, node in old_sites.items()}
    new_signatures = {site: _node_signature(node) for site, node in new_sites.items()}
    added_sites = sorted(set(new_sites) - set(old_sites))
    removed_sites = sorted(set(old_sites) - set(new_sites))
    changed_sites = sorted(site for site in set(old_sites) & set(new_sites)
                           if old_signatures[site] != new_signatures[site])

    # An input value or capability-envelope change can affect otherwise identical code.
    # Until per-node integration bindings and evidence are fully snapshotted, neither is
    # considered safe for result reuse.
    inputs_changed = _canonical(saved_inputs) != _canonical(effective_inputs)
    envelope_changed = _canonical(current.plan.envelope.model_dump(mode="json")) != _canonical(
        candidate.plan.envelope.model_dump(mode="json"))
    globally_invalidated = inputs_changed or envelope_changed
    global_reason = "inputs_changed" if inputs_changed else "envelope_changed" if envelope_changed else ""

    invalid_sites = set(added_sites) | set(removed_sites) | set(changed_sites)
    # A child change invalidates its containers; a dependency or control-flow change
    # invalidates downstream consumers. Iterate to a fixed point for nested plans.
    changed = True
    while changed:
        before = len(invalid_sites)
        for site, compiled in new_sites.items():
            dependencies = set(compiled.deps) | set(compiled.control_deps)
            if compiled.body_of:
                dependencies.add(compiled.body_of)
            child_sites = {child.site_id for child in new_sites.values() if child.body_of == site}
            if dependencies & invalid_sites or child_sites & invalid_sites:
                invalid_sites.add(site)
        changed = len(invalid_sites) != before

    current_payload = current.plan.model_dump(by_alias=True, exclude_none=True, mode="json")
    candidate_payload = candidate.plan.model_dump(by_alias=True, exclude_none=True, mode="json")
    current_payload.pop("nodes", None)
    candidate_payload.pop("nodes", None)
    changed_fields = _field_diff(current_payload, candidate_payload)
    node_diffs: list[dict[str, Any]] = []
    for site in sorted(set(old_sites) | set(new_sites)):
        old_node, new_node = old_sites.get(site), new_sites.get(site)
        if old_node is None:
            node_diffs.append({"site_id": site, "change": "added",
                               "fields": _field_diff({}, _node_payload(new_node))})
        elif new_node is None:
            node_diffs.append({"site_id": site, "change": "removed",
                               "fields": _field_diff(_node_payload(old_node), {})})
        else:
            fields = _field_diff(_node_payload(old_node), _node_payload(new_node))
            if old_signatures[site] != new_signatures[site]:
                node_diffs.append({"site_id": site, "change": "changed", "fields": fields,
                                   "dependencies_changed": (sorted(old_node.deps) != sorted(new_node.deps)
                                                            or sorted(old_node.control_deps) != sorted(new_node.control_deps))})

    reuse: list[dict[str, Any]] = []
    invalidation: list[dict[str, Any]] = []
    evidence_sensitive = {"tool", "agent", "verify", "publish", "ask"}
    rows = wstore.nodes(store, workflow_run_id)
    unsafe_sites = set(invalid_sites)
    base_reasons: dict[tuple[str, str], str] = {}
    for row in rows:
        site = str(row.get("site_id") or "")
        status = str(row.get("status") or "")
        instance_key = str(row.get("instance_key") or "")
        reason = ""
        if globally_invalidated:
            reason = global_reason
        elif site not in new_sites:
            reason = "site_removed"
        elif site in invalid_sites:
            reason = "node_or_dependency_changed"
        elif status in ("pending", "running", "waiting"):
            reason = "not_settled"
        elif status not in ("succeeded", "skipped"):
            reason = "terminal_result_not_reusable"
        elif not str(row.get("input_hash") or ""):
            reason = "resolved_inputs_not_recorded"
        elif new_sites[site].kind in evidence_sensitive:
            # Current storage does not preserve the route/account/evidence snapshot needed
            # to prove these results remain applicable to a new revision.
            reason = "execution_binding_or_evidence_not_snapshotted"
        elif new_sites[site].kind != "transform":
            # Until control/container result provenance is recorded, it may include child
            # outputs whose own route, effect, or evidence bindings cannot be reused.
            reason = "result_semantics_not_snapshotted"
        if reason:
            base_reasons[(site, instance_key)] = reason
            unsafe_sites.add(site)

    # A result is not reusable when any dependency (or a nested child/parent result) is
    # unsafe to reuse, even if the dependent node itself is a deterministic transform.
    changed = True
    while changed:
        before = len(unsafe_sites)
        for site, compiled in new_sites.items():
            dependencies = set(compiled.deps) | set(compiled.control_deps)
            if compiled.body_of:
                dependencies.add(compiled.body_of)
            child_sites = {child.site_id for child in new_sites.values() if child.body_of == site}
            if dependencies & unsafe_sites or child_sites & unsafe_sites:
                unsafe_sites.add(site)
        changed = len(unsafe_sites) != before

    for row in rows:
        site = str(row.get("site_id") or "")
        instance_key = str(row.get("instance_key") or "")
        status = str(row.get("status") or "")
        reason = base_reasons.get((site, instance_key), "")
        if not reason and site in unsafe_sites:
            reason = "dependency_result_not_reusable"
        if reason:
            invalidation.append({"site_id": site, "instance_key": instance_key,
                                 "status": status, "reason": reason})
        else:
            reuse.append({"site_id": site, "instance_key": instance_key,
                          "status": status, "input_hash": str(row["input_hash"])})

    active_nodes = [{"site_id": str(row.get("site_id") or ""),
                     "instance_key": str(row.get("instance_key") or ""),
                     "status": str(row.get("status") or "")}
                    for row in rows if str(row.get("status") or "") in ("pending", "running", "waiting")]
    pending_questions = [str(row["id"]) for row in wstore.questions(store, workflow_run_id)
                         if row.get("status") == "pending"]
    budgets = {}
    old_budget = dict(workflow.get("budget") or {})
    new_budget = candidate.plan.budget.model_dump(mode="json")
    for key, proposed in new_budget.items():
        current_limit = old_budget.get(key)
        if isinstance(current_limit, int) and isinstance(proposed, int):
            ledger_key = {"max_nodes": "nodes", "max_model_calls": "model_calls",
                          "max_tokens": "model_tokens", "max_repairs": "repairs"}.get(key)
            used = int((workflow.get("ledger") or {}).get(ledger_key, 0) or 0) if ledger_key else None
            budgets[key] = {"current": current_limit, "proposed": proposed,
                            "effective_if_adopted": min(current_limit, proposed),
                            **({"used": used, "remaining_now": max(0, min(current_limit, proposed) - used)}
                               if used is not None else {})}
            if proposed > current_limit:
                blocked_reasons.append(f"the amendment cannot increase the root {key} allowance")
        else:
            budgets[key] = {"current": current_limit, "proposed": proposed,
                            "effective_if_adopted": proposed}

    return {
        "workflow_run_id": workflow_run_id,
        "current_revision_id": revision_id,
        "current_generation": generation_id,
        "current_plan_hash": str(workflow.get("plan_hash") or ""),
        "candidate_plan_hash": candidate.plan_hash,
        "candidate_inputs": effective_inputs,
        "plan_changed": candidate.plan_hash != str(workflow.get("plan_hash") or ""),
        "changed_fields": changed_fields,
        "nodes": node_diffs,
        "added_sites": added_sites,
        "removed_sites": removed_sites,
        "changed_sites": changed_sites,
        "reuse": reuse,
        "invalidate": invalidation,
        "budgets": budgets,
        "roles": roles,
        "blocked_reasons": sorted(set(blocked_reasons)),
        "eligible": not blocked_reasons,
        "quiescence": {
            "workflow_status": str(workflow.get("status") or ""),
            "active_nodes": active_nodes,
            "pending_question_ids": pending_questions,
            "required": bool(active_nodes or pending_questions or workflow.get("status") in ("pending", "running", "waiting")),
        },
    }
