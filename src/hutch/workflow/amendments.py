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
from . import qualify
from .compile import CompiledNode, compile_plan
from .expr import Scope, resolve_value
from .submit import PlanNotSubmittable, check_authority, step_budget, validate_inputs


class AmendmentConflict(ValueError):
    """The preview was based on a stale workflow revision or owner generation."""


def adopt(store: Any, *, workflow_run_id: str, plan: dict[str, Any],
          expected_revision_id: str, expected_generation: str,
          inputs: dict[str, Any] | None, cancel_pending_questions: bool,
          idem_key: str, request_hash: str) -> dict[str, Any]:
    """Adopt one reviewed candidate while its current workflow is safely parked."""
    candidate = compile_plan(plan)
    current_preview = preview(
        store, workflow_run_id=workflow_run_id, plan=plan,
        expected_revision_id=expected_revision_id, expected_generation=expected_generation,
        inputs=inputs)
    if not current_preview["eligible"]:
        raise PlanNotSubmittable("the candidate is not eligible: "
                                 + "; ".join(current_preview["blocked_reasons"]))
    workflow = wstore.workflow_run(store, workflow_run_id)
    if workflow is None:
        raise KeyError(workflow_run_id)

    def authorize() -> list[dict[str, Any]]:
        bot = store.get_bot(str(workflow["bot_id"]))
        if bot is None:
            raise PlanNotSubmittable("the workflow's assistant is unavailable")
        roles = check_authority(candidate, bot, store=store)
        connections = qualify.connections_for_store(store)
        for item in current_preview["quiescence"].get("carry_active_nodes", []):
            compiled_node = candidate.by_site.get(str(item.get("site_id") or ""))
            if compiled_node is None:
                raise PlanNotSubmittable("a carried worker is absent from the reviewed candidate")
            spec = (str(bot.model) if compiled_node.node.model in ("", "$bot", "$default")
                    else str(compiled_node.node.model))
            budget = step_budget(candidate)
            max_steps = min(int(compiled_node.node.max_steps or 12),
                            int(budget.get("max_steps_per_node") or 12))
            timeout_seconds = min(600, int(budget.get("max_step_seconds") or 600))
            fingerprint = qualify.step_binding_fingerprint(
                bot, spec=spec, role=compiled_node.node.role, tools=[], skills=[],
                output_schema=compiled_node.node.output_schema or None,
                max_steps=max_steps, timeout_seconds=timeout_seconds,
                connections=connections)
            verdict = qualify.assess(
                "worker", spec=spec, store=store, connections=connections,
                base_url=getattr(bot, "base_url", None) or None,
                requires_structured_output=compiled_node.node.output_schema is not None)
            if (not verdict.allowed or fingerprint != item.get("binding_fingerprint")
                    or verdict.state != item.get("role_state")):
                raise PlanNotSubmittable("a carried worker's current model authority or execution binding changed")
        return roles

    return wstore.adopt_workflow_amendment(
        store, wf_id=workflow_run_id, expected_revision_id=expected_revision_id,
        expected_generation=expected_generation,
        plan=candidate.plan.model_dump(by_alias=True, exclude_none=True, mode="json"),
        plan_hash=candidate.plan_hash,
        inputs=current_preview["candidate_inputs"],
        budget=step_budget(candidate), preview=current_preview,
        cancel_pending_questions=cancel_pending_questions,
        authorize=authorize, idem_key=idem_key, request_hash=request_hash)


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


def _carryable_active_worker(store: Any, *, workflow: dict[str, Any],
                             revision_id: str, generation_id: str,
                             row: dict[str, Any], compiled: CompiledNode,
                             candidate_scope: dict[str, Any],
                             reusable_transform_sites: set[str],
                             invalid_sites: set[str], inputs_changed: bool,
                             envelope_changed: bool, budget_changed: bool,
                             append_only: bool, old_order: list[str],
                             new_order: list[str], bot: Any
                             ) -> dict[str, Any] | None:
    """Prove one in-flight worker step is unchanged and safe to drain after adoption."""
    site = str(row.get("site_id") or "")
    instance_key = str(row.get("instance_key") or "")
    if (compiled.kind != "agent" or compiled.body_of or instance_key != "once"
            or compiled.node.when is not None or compiled.node.role != "worker"
            or compiled.node.tools or compiled.node.skills
            or row.get("kind") != "step" or row.get("status") not in ("running", "waiting")
            or site in invalid_sites or inputs_changed or envelope_changed or budget_changed
            or not append_only):
        return None
    dependencies = set(compiled.deps) | set(compiled.control_deps)
    if dependencies - reusable_transform_sites:
        return None
    try:
        old_index = old_order.index(site)
        new_index = new_order.index(site)
    except ValueError:
        return None
    if (old_index != new_index or old_order[:old_index] != new_order[:new_index]
            or new_order[:len(old_order)] != old_order):
        return None

    try:
        resolved_inputs = {name: resolve_value(value, Scope(candidate_scope))
                           for name, value in compiled.node.inputs.items()}
    except (TypeError, ValueError):
        return None
    expected_input = {
        "instruction": compiled.node.instruction,
        "inputs": resolved_inputs,
        "output_schema": compiled.node.output_schema,
        "role": compiled.node.role,
    }
    if (row.get("input") != expected_input
            or str(row.get("input_hash") or "") != _digest(expected_input)):
        return None

    run_id = str(row.get("run_id") or "")
    child = store.get_run(run_id) if run_id else None
    attempt = store.get_run(generation_id)
    contract = child.workflow_step if child is not None else None
    parent_fence = contract.get("parent_fence") if isinstance(contract, dict) else None
    # Persisted run documents are a trust boundary. A malformed or legacy fence must
    # make the carry proof fail closed, not turn an amendment preview into a 500.
    if type(parent_fence) is not int:
        return None
    if (child is None or child.parent_run_id != generation_id or attempt is None
            or store.run_kind(run_id) != "step" or not isinstance(contract, dict)
            or contract.get("workflow_run_id") != str(workflow["id"])
            or contract.get("revision_id") != revision_id
            or contract.get("site_id") != site
            or contract.get("instance_key") != instance_key
            or parent_fence != attempt.fence
            or contract.get("tools") != [] or contract.get("skills") != []):
        return None

    spec = (str(bot.model) if compiled.node.model in ("", "$bot", "$default")
            else str(compiled.node.model))
    max_steps = min(int(compiled.node.max_steps or 12),
                    int((workflow.get("budget") or {}).get("max_steps_per_node") or 12))
    timeout_seconds = min(600, int((workflow.get("budget") or {}).get("max_step_seconds") or 600))
    connections = qualify.connections_for_store(store)
    binding_fingerprint = qualify.step_binding_fingerprint(
        bot, spec=spec, role=compiled.node.role, tools=[], skills=[],
        output_schema=compiled.node.output_schema or None,
        max_steps=max_steps, timeout_seconds=timeout_seconds,
        connections=connections)
    instruction_hash = _digest({"instruction": compiled.node.instruction, "inputs": resolved_inputs})
    verdict = qualify.assess("worker", spec=spec, store=store,
                             connections=connections,
                             base_url=getattr(bot, "base_url", None) or None,
                             requires_structured_output=compiled.node.output_schema is not None)
    if (not verdict.allowed or contract.get("role_state") != verdict.state
            or contract.get("model") != spec or contract.get("role") != compiled.node.role
            or contract.get("output_schema") != (compiled.node.output_schema or None)
            or contract.get("max_steps") != max_steps
            or contract.get("timeout_seconds") != timeout_seconds
            or contract.get("binding_fingerprint") != binding_fingerprint
            or contract.get("instruction_hash") != instruction_hash):
        return None
    return {"site_id": site, "instance_key": instance_key,
            "status": str(row.get("status") or ""), "run_id": run_id,
            "input_hash": str(row.get("input_hash") or ""),
            "model": spec, "role": compiled.node.role, "role_state": verdict.state,
            "binding_fingerprint": binding_fingerprint,
            "instruction_hash": instruction_hash,
            "output_schema": compiled.node.output_schema or None,
            "max_steps": max_steps, "timeout_seconds": timeout_seconds,
            "reason": "unchanged top-level tool-free worker contract"}


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

    # Input changes invalidate work whose resolved inputs changed. Integration and
    # capability changes remain conservative for non-transform nodes because their
    # execution bindings and evidence are not snapshotted per node.
    inputs_changed = _canonical(saved_inputs) != _canonical(effective_inputs)
    envelope_changed = _canonical(current.plan.envelope.model_dump(mode="json")) != _canonical(
        candidate.plan.envelope.model_dump(mode="json"))
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
    rows_by_key = {(str(row.get("site_id") or ""), str(row.get("instance_key") or "")): row
                   for row in rows}
    for row in rows:
        site = str(row.get("site_id") or "")
        status = str(row.get("status") or "")
        instance_key = str(row.get("instance_key") or "")
        compiled = new_sites.get(site)
        reason = ""
        if compiled is None:
            reason = "site_removed"
        elif site in invalid_sites:
            reason = "node_or_dependency_changed"
        elif status in ("pending", "running", "waiting"):
            reason = "not_settled"
        elif status not in ("succeeded", "skipped"):
            reason = "terminal_result_not_reusable"
        elif not str(row.get("input_hash") or ""):
            reason = "resolved_inputs_not_recorded"
        elif global_reason and compiled.kind != "transform":
            reason = global_reason
        elif compiled.kind in evidence_sensitive:
            # Current storage does not preserve the route/account/evidence snapshot needed
            # to prove these results remain applicable to a new revision.
            reason = "execution_binding_or_evidence_not_snapshotted"
        elif compiled.kind != "transform":
            # Until control/container result provenance is recorded, it may include child
            # outputs whose own route, effect, or evidence bindings cannot be reused.
            reason = "result_semantics_not_snapshotted"
        elif global_reason and (compiled.body_of or instance_key != "once"
                                or compiled.node.when is not None):
            reason = global_reason
        if reason:
            base_reasons[(site, instance_key)] = reason
            unsafe_sites.add(site)

    # Replay candidate values in declaration order, but expose a prior result to later
    # transforms only after proving that exact result reusable. This prevents an input
    # change upstream from being hidden by resolving against stale values.
    reusable_transform_sites: set[str] = set()
    candidate_scope: dict[str, Any] = {"input": effective_inputs}
    for compiled in candidate.top_level():
        site = compiled.site_id
        key = (site, "once")
        row = rows_by_key.get(key)
        if compiled.kind != "transform" or compiled.body_of or compiled.node.when is not None:
            continue
        if row is None or key in base_reasons:
            continue
        dependencies = set(compiled.deps) | set(compiled.control_deps)
        if dependencies - reusable_transform_sites:
            base_reasons[key] = "dependency_result_not_reusable"
            unsafe_sites.add(site)
            continue
        try:
            resolved_args = {name: resolve_value(value, Scope(candidate_scope))
                             for name, value in compiled.node.args.items()}
        except (ValueError, TypeError):
            base_reasons[key] = "resolved_inputs_not_recorded"
            unsafe_sites.add(site)
            continue
        identity = {"resolved_args_sha256": _digest(resolved_args)}
        recorded_identity = row.get("input")
        if recorded_identity != identity:
            reason = ("inputs_changed" if isinstance(recorded_identity, dict)
                      and "resolved_args_sha256" in recorded_identity else "resolved_inputs_not_recorded")
            base_reasons[key] = reason
            unsafe_sites.add(site)
            continue
        if str(row.get("input_hash") or "") != _digest(identity):
            base_reasons[key] = "resolved_inputs_not_recorded"
            unsafe_sites.add(site)
            continue
        reusable_transform_sites.add(site)
        candidate_scope[site] = row.get("result")

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

    active_rows = [row for row in rows
                   if str(row.get("status") or "") in ("pending", "running", "waiting")]
    old_budget = dict(workflow.get("budget") or {})
    budget_changed = _canonical(old_budget) != _canonical(step_budget(candidate))
    old_order = [node.site_id for node in current.top_level()]
    new_order = [node.site_id for node in candidate.top_level()]
    append_only = (not removed_sites and not changed_sites
                   and new_order[:len(old_order)] == old_order
                   and set(added_sites).issubset(new_order[len(old_order):]))
    carried: list[dict[str, Any]] = []
    if bot is not None:
        for row in active_rows:
            site = str(row.get("site_id") or "")
            compiled = new_sites.get(site)
            if compiled is None:
                continue
            carry = _carryable_active_worker(
                store, workflow=workflow, revision_id=revision_id,
                generation_id=generation_id, row=row, compiled=compiled,
                candidate_scope=candidate_scope,
                reusable_transform_sites=reusable_transform_sites,
                invalid_sites=invalid_sites, inputs_changed=inputs_changed,
                envelope_changed=envelope_changed, budget_changed=budget_changed,
                append_only=append_only, old_order=old_order,
                new_order=new_order, bot=bot)
            if carry is not None:
                carried.append(carry)
    # This slice carries one live worker only. Parallel races and fan-out stay on the
    # ordinary quiet-drain path until each multi-child shape has its own evidence.
    if len(carried) != 1:
        carried = []
    carry_keys = {(item["site_id"], item["instance_key"]) for item in carried}

    for row in rows:
        site = str(row.get("site_id") or "")
        instance_key = str(row.get("instance_key") or "")
        status = str(row.get("status") or "")
        reason = base_reasons.get((site, instance_key), "")
        if (site, instance_key) in carry_keys:
            continue
        if not reason and site in unsafe_sites:
            reason = "dependency_result_not_reusable"
        if reason:
            invalidation.append({"site_id": site, "instance_key": instance_key,
                                 "status": status, "reason": reason})
        else:
            reuse.append({"site_id": site, "instance_key": instance_key,
                          "status": status, "input_hash": str(row["input_hash"])})

    owner_attempt = store.get_run(generation_id)
    drained: list[dict[str, Any]] = []
    drainable: list[dict[str, Any]] = []
    for row in active_rows:
        if (str(row.get("kind") or "") != "step"
                or str(row.get("status") or "") not in ("running", "waiting")):
            continue
        run_id = str(row.get("run_id") or "")
        child = store.get_run(run_id) if run_id else None
        contract = child.workflow_step if child is not None else None
        parent_fence = contract.get("parent_fence") if isinstance(contract, dict) else None
        if (child is None or not child.terminal or not child.cancel_requested
                or store.run_kind(run_id) != "step" or child.parent_run_id != generation_id
                or not isinstance(contract, dict)
                or contract.get("workflow_run_id") != workflow_run_id
                or contract.get("revision_id") != revision_id
                or contract.get("site_id") != str(row.get("site_id") or "")
                or contract.get("instance_key") != str(row.get("instance_key") or "")
                or type(parent_fence) is not int or owner_attempt is None
                or parent_fence != owner_attempt.fence
                or contract.get("tools") != [] or contract.get("skills") != []):
            continue
        with store._lock:
            owned_process = store._db.execute(
                "SELECT 1 FROM run_procs WHERE run_id = ? AND ended_at IS NULL "
                "AND detached_at IS NULL LIMIT 1", (run_id,)).fetchone()
        if owned_process:
            continue
        drained.append({"site_id": str(row.get("site_id") or ""),
                        "instance_key": str(row.get("instance_key") or ""),
                        "run_id": run_id, "status": str(child.status.value),
                        "reason": "tool-free step cancellation is terminal"})

    for row in active_rows:
        key = (str(row.get("site_id") or ""), str(row.get("instance_key") or ""))
        if (key in carry_keys or str(row.get("kind") or "") != "step"
                or str(row.get("status") or "") not in ("running", "waiting")):
            continue
        run_id = str(row.get("run_id") or "")
        child = store.get_run(run_id) if run_id else None
        contract = child.workflow_step if child is not None else None
        parent_fence = contract.get("parent_fence") if isinstance(contract, dict) else None
        if (child is None or child.terminal or store.run_kind(run_id) != "step"
                or child.parent_run_id != generation_id or not isinstance(contract, dict)
                or contract.get("workflow_run_id") != workflow_run_id
                or contract.get("revision_id") != revision_id
                or contract.get("site_id") != key[0]
                or contract.get("instance_key") != key[1]
                or type(parent_fence) is not int or owner_attempt is None
                or parent_fence != owner_attempt.fence
                or contract.get("tools") != [] or contract.get("skills") != []):
            continue
        with store._lock:
            descendants = store._db.execute(
                "SELECT 1 FROM runs WHERE parent_run_id = ? LIMIT 1", (run_id,)).fetchone()
        if descendants:
            continue
        drainable.append({"site_id": key[0], "instance_key": key[1], "run_id": run_id,
                          "status": str(row.get("status") or ""),
                          "cancel_requested": bool(child.cancel_requested),
                          "reason": "tool-free child with no owned descendants"})

    active_nodes = [{"site_id": str(row.get("site_id") or ""),
                     "instance_key": str(row.get("instance_key") or ""),
                     "status": str(row.get("status") or "")}
                    for row in active_rows]
    pending_questions = [str(row["id"]) for row in wstore.questions(store, workflow_run_id)
                         if row.get("status") == "pending"]
    attempt_quiescence = wstore.workflow_attempt_quiescence(
        store, generation_id, carry_run_ids={str(item["run_id"]) for item in carried})
    attempt_quiescence["carry_active_nodes"] = carried
    attempt_quiescence["drainable_active_nodes"] = drainable
    attempt_quiescence["drained_active_nodes"] = drained
    budgets = {}
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
            **attempt_quiescence,
            "active_nodes": active_nodes,
            "pending_question_ids": pending_questions,
            "required": bool(active_nodes or pending_questions or workflow.get("status") in ("pending", "running", "waiting")),
        },
    }


def drain_affected(store: Any, *, workflow_run_id: str, plan: dict[str, Any],
                   expected_revision_id: str, expected_generation: str,
                   inputs: dict[str, Any] | None, idem_key: str,
                   request_hash: str) -> dict[str, Any]:
    """Stop only affected, tool-free model steps after an owner has parked the run."""
    current_preview = preview(
        store, workflow_run_id=workflow_run_id, plan=plan,
        expected_revision_id=expected_revision_id, expected_generation=expected_generation,
        inputs=inputs)
    if not current_preview["eligible"]:
        raise PlanNotSubmittable("the candidate is not eligible: "
                                 + "; ".join(current_preview["blocked_reasons"]))
    workflow = wstore.workflow_run(store, workflow_run_id)
    if workflow is None:
        raise KeyError(workflow_run_id)
    if (workflow.get("status") != "waiting" or not workflow.get("pause_requested")
            or not current_preview["quiescence"].get("attempt_parked")):
        raise ValueError("draining affected steps requires a paused, parked workflow")

    carry = {(str(item["site_id"]), str(item["instance_key"]))
             for item in current_preview["quiescence"].get("carry_active_nodes", [])}
    pending_questions = {(str(item["site_id"]), str(item["instance_key"]))
                         for item in wstore.questions(store, workflow_run_id)
                         if item.get("status") == "pending"}
    owner_attempt = store.get_run(expected_generation)
    if owner_attempt is None:
        raise ValueError("the current workflow attempt is unavailable; refresh the preview")
    requested: list[dict[str, str]] = []
    cancellation_targets: list[tuple[tuple[str, str], str, str, str]] = []
    for row in wstore.nodes(store, workflow_run_id):
        key = (str(row.get("site_id") or ""), str(row.get("instance_key") or ""))
        if str(row.get("status") or "") not in ("pending", "running", "waiting"):
            continue
        if key in carry or (str(row.get("kind") or "") == "ask" and key in pending_questions):
            continue
        if (str(row.get("kind") or "") != "step"
                or str(row.get("status") or "") not in ("running", "waiting")
                or not str(row.get("run_id") or "")):
            raise ValueError("the candidate has affected active work that cannot be safely drained")
        run_id = str(row["run_id"])
        child = store.get_run(run_id)
        contract = child.workflow_step if child is not None else None
        parent_fence = contract.get("parent_fence") if isinstance(contract, dict) else None
        if (child is None or store.run_kind(run_id) != "step"
                or child.parent_run_id != expected_generation
                or not isinstance(contract, dict)
                or contract.get("workflow_run_id") != workflow_run_id
                or contract.get("revision_id") != expected_revision_id
                or contract.get("site_id") != key[0]
                or contract.get("instance_key") != key[1]
                or type(parent_fence) is not int or parent_fence != owner_attempt.fence
                or contract.get("tools") != [] or contract.get("skills") != []):
            raise ValueError("only the exact tool-free child step proven by the current run can be drained")
        with store._lock:
            descendants = store._db.execute(
                "SELECT 1 FROM runs WHERE parent_run_id = ? LIMIT 1", (run_id,)).fetchone()
        if descendants:
            raise ValueError("a step with owned child work cannot be safely drained by amendment")
        if child.terminal and child.cancel_requested:
            requested.append({"site_id": key[0], "instance_key": key[1], "run_id": run_id,
                              "status": child.status.value})
            continue
        if child.terminal:
            raise ValueError("an affected step finished before it could be drained; refresh the preview")
        child_key = "wf-amend-drain-" + hashlib.sha256(
            f"{workflow_run_id}:{expected_generation}:{idem_key}:{run_id}".encode()).hexdigest()[:40]
        child_hash = _digest({"workflow_run_id": workflow_run_id,
                              "expected_revision_id": expected_revision_id,
                              "expected_generation": expected_generation,
                              "plan_hash": current_preview["candidate_plan_hash"],
                              "run_id": run_id})
        cancellation_targets.append((key, run_id, child_key, child_hash))

    # Validate every affected active node before the first stop request. A mixed
    # safe/unsafe set must fail without partially cancelling its safe members.
    for key, run_id, child_key, child_hash in cancellation_targets:
        stopped = store.request_cancel_tree(run_id, idem_key=child_key, request_hash=child_hash)
        if stopped is None:
            raise ValueError("the affected step disappeared while draining; refresh the preview")
        fresh = store.get_run(run_id)
        requested.append({"site_id": key[0], "instance_key": key[1], "run_id": run_id,
                          "status": fresh.status.value if fresh else "unavailable"})

    if not requested:
        raise ValueError("there are no affected tool-free active steps to drain")
    store.bus.notify("work", "workflows", f"workflow:{workflow_run_id}")
    return {"workflow_run_id": workflow_run_id,
            "revision_id": expected_revision_id,
            "attempt_run_id": expected_generation,
            "requested": requested,
            "message": "Affected step stop requested; wait for verified cleanup before previewing adoption."}
