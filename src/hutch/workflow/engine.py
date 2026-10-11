"""The deterministic interpreter for compiled workflow plans.

This module is the *only* place a plan's control flow is decided. It is deterministic:
given the same plan and the same durable node records it makes the same decisions, which
is what makes crash recovery a continuation rather than a replay.

Rules it enforces:

* **One identity per invocation.** A node instance is keyed ``(site_id, instance_key)``.
  Inside a bounded construct the key comes from the declared ``item_key`` (so a reordered
  collection cannot alias two items), otherwise from the iteration ordinal. A repeated
  call site is never one invocation.
* **Recorded results are the answer.** A settled instance is reused; it is never
  re-executed. Effects therefore happen once, even across a crash or a continuation.
* **Caps fail loudly.** A fan-out over more items than the node or budget allows is a
  failure naming the count, not a truncated partial view.
* **No fabricated values.** A missing reference, a failed tool, an unparseable model
  result and an expired question all fail or wait - they never become ``0``/``""``/False.
* **Model work is isolated.** Agent nodes become ordinary step runs (their own process,
  workspace, transcript, approvals and receipts); everything else runs here through the
  canonical tool seam.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from ..models import Event, EventType, Run, Task, iso, utcnow
from ..runtime import steps
from ..runtime.base import RunAborted
from . import persistence as wstore
from . import qualify
from .compile import CompiledNode, CompiledPlan
from .expr import EvalError, Scope, evaluate, resolve_value
from .plan import Node

#: Bounds for values that cross a node boundary. Larger results belong in an artifact.
MAX_RESULT_BYTES = 64 * 1024
MAX_INPUT_BUNDLE = 16_000
MAX_STEP_PROMPT = 4_000
MAX_STEP_CONTEXT = 16_000
MAX_TOOL_OUTPUT_IN_RESULT = 8_000

_VERIFIER_SCHEMA = {
    "type": "object",
    "required": ["pass", "reason"],
    "properties": {
        "pass": {"type": "boolean"},
        "reason": {"type": "string", "maxLength": 2000},
    },
    "additionalProperties": False,
}
_REPAIR_SCHEMA = {
    "type": "object",
    "required": ["replacement"],
    "properties": {"replacement": {}},
    "additionalProperties": False,
}


class WorkflowFailed(RuntimeError):
    """A node failed in a way the plan did not ask to tolerate."""

    def __init__(self, site_id: str, message: str):
        self.site_id = site_id
        super().__init__(f"{site_id}: {message}")


class _Wait(Exception):
    """Raised to unwind the walk until something settles."""


_JOIN_SKIPPED = object()


@dataclass
class Advance:
    kind: str                      # "wait" | "done" | "failed"
    detail: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    verified: Optional[bool] = None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bounded(value: Any, cap: int = MAX_RESULT_BYTES) -> Any:
    text = _canonical(value)
    if len(text) <= cap:
        return value
    return {"truncated": True, "bytes": len(text),
            "preview": text[: max(0, cap - 200)]}


class Interpreter:
    """Walks a compiled plan against durable state, one ``advance()`` at a time."""

    def __init__(self, *, engine: Any, ctx: Any, run: Run, compiled: CompiledPlan,
                 workflow: dict[str, Any], tools: dict[str, Any], budget: dict[str, Any]):
        self.engine = engine
        self.store = engine.store
        self.ctx = ctx
        self.run = run
        self.compiled = compiled
        self.workflow = workflow
        self.tools = tools
        self.budget = budget
        self.wf_id = str(workflow["id"])
        self.revision_id = str(workflow["revision_id"])
        self.nodes: dict[tuple[str, str], dict[str, Any]] = {}
        self.questions: dict[tuple[str, str], dict[str, Any]] = {}
        self.scope: dict[str, Any] = {}
        self.ledger: dict[str, Any] = {}
        self.events: list[str] = []
        self.verified: Optional[bool] = None
        self.pending_questions_seen = False
        self.join_targets = {
            target for candidate in compiled.nodes if candidate.kind == "join"
            for target in candidate.node.of
        }
        self.all_settled_targets = {
            target for candidate in compiled.nodes
            if candidate.kind == "join" and candidate.node.policy == "all_settled"
            for target in candidate.node.of
        }
        self.opened_steps: set[tuple[str, str]] = set()
        self._suffix_stack: list[str] = []

    # -------------------------------------------------------------- identities

    @property
    def _instance_key(self) -> str:
        """The identity of the current invocation: composed from every enclosing construct.

        This is what keeps a repeated call site from aliasing: the second item of a map, or
        the third round of a loop, is a different invocation with a different key - and a
        reordered collection produces the same keys because map keys come from ``item_key``.
        """
        return "|".join(self._suffix_stack) or "once"

    @contextlib.contextmanager
    def _within(self, suffix: str):
        self._suffix_stack.append(suffix)
        try:
            yield
        finally:
            self._suffix_stack.pop()

    # ------------------------------------------------------------------ driver

    def advance(self) -> Advance:
        """One deterministic pass. Returns wait / done / failed."""
        self.nodes = {(n["site_id"], n["instance_key"]): n
                      for n in wstore.nodes(self.store, self.wf_id)}
        self.questions = {(q["site_id"], q["instance_key"]): q
                          for q in wstore.questions(self.store, self.wf_id)}
        self.ledger = dict(self.workflow.get("ledger") or {})
        self.scope = {"input": dict(self.workflow.get("inputs") or {})}
        self.opened_steps = set()
        self.pending_questions_seen = False
        try:
            value = self._walk(self.compiled.top_level(), self.scope,
                               collect_independent_questions=True)
        except _Wait:
            return Advance("wait")
        except WorkflowFailed as exc:
            return Advance("failed", detail=str(exc))
        except EvalError as exc:
            return Advance("failed", detail=f"evaluation error: {exc}")
        except qualify.QualificationBlocked as exc:
            return Advance("failed", detail=exc.verdict.summary())
        except RunAborted:
            raise
        except Exception as exc:  # noqa: BLE001 - an interpreter bug must fail the run honestly
            return Advance("failed", detail=f"{type(exc).__name__}: {exc}")
        if self.pending_questions_seen:
            return Advance("wait")
        result = {"outputs": {site: self.scope.get(site) for site in self.compiled.plan.outputs
                              if self.scope.get(site) is not _JOIN_SKIPPED},
                  "value": value}
        return Advance("done", result=_bounded(result), verified=self.verified)

    # ------------------------------------------------------------------ walking

    def _walk(self, nodes: list[CompiledNode], scope: dict[str, Any], *,
              collect_independent_questions: bool = False) -> Any:
        value: Any = None
        deferred_sites: set[str] = set()
        for cnode in nodes:
            if wstore.workflow_pause_requested(self.store, self.wf_id):
                raise _Wait()
            dependencies = set(cnode.deps) | set(cnode.control_deps)
            if collect_independent_questions and (
                    dependencies & deferred_sites or
                    self.pending_questions_seen and cnode.kind != "ask"):
                deferred_sites.add(cnode.site_id)
                continue
            blocked = [dep for dep in cnode.deps if scope.get(dep) is _JOIN_SKIPPED]
            if blocked and cnode.kind != "join":
                if cnode.site_id in self.all_settled_targets:
                    scope[cnode.site_id] = _JOIN_SKIPPED
                    continue
                raise WorkflowFailed(cnode.site_id,
                                     f"input depends on failed or skipped node(s): {sorted(blocked)}")
            if cnode.node.when is not None and not evaluate(cnode.node.when, Scope(scope)):
                self._mark_skipped(cnode, self._instance_key, "condition was false")
                if cnode.site_id in self.join_targets:
                    scope[cnode.site_id] = _JOIN_SKIPPED
                continue
            try:
                value = self._visit(cnode, scope)
            except _Wait:
                question = self.questions.get((cnode.site_id, self._instance_key))
                if (collect_independent_questions and cnode.kind == "ask"
                        and question is not None and question["status"] == "pending"):
                    self.pending_questions_seen = True
                    deferred_sites.add(cnode.site_id)
                    continue
                raise
            except WorkflowFailed:
                if cnode.site_id not in self.all_settled_targets:
                    raise
                # An all_settled join explicitly owns failures from these earlier sites.
                # The durable failed node remains the source of its reason; this private
                # sentinel only keeps the failed value out of later reference resolution.
                scope[cnode.site_id] = _JOIN_SKIPPED
                continue
            scope[cnode.site_id] = value
        return value

    def _visit(self, cnode: CompiledNode, scope: dict[str, Any]) -> Any:
        node = cnode.node
        kind = node.kind
        if kind == "transform":
            return self._inline(cnode, self._instance_key, scope, self._transform, node)
        if kind == "tool":
            return self._inline(cnode, self._instance_key, scope,
                                lambda item, values: self._tool(cnode, item, values), node)
        if kind == "join":
            return self._inline(cnode, self._instance_key, scope, self._join, node)
        if kind == "publish":
            return self._inline(cnode, self._instance_key, scope, self._publish, node)
        if kind == "ask":
            return self._ask(cnode, scope)
        if kind == "branch":
            taken = "then" if evaluate(node.condition, Scope(scope)) else "else"
            body = self.compiled.children_of(cnode.site_id, taken)
            value = self._walk(body, scope) if body else None
            result = {"taken": taken, "result": value}
            self._record_container(cnode, result)
            return result
        if kind == "repeat":
            return self._repeat(cnode, scope)
        if kind in ("map", "expand"):
            return self._map(cnode, scope)
        if kind == "verify":
            return self._verify(cnode, scope)
        if kind == "agent":
            return self._agent(cnode, scope)
        raise WorkflowFailed(cnode.site_id, f"unsupported node kind {kind!r}")

    # ------------------------------------------------------------- inline nodes

    def _inline(self, cnode: CompiledNode, instance_key: str, scope: dict[str, Any],
                fn: Any, node: Node) -> Any:
        record = self.nodes.get((cnode.site_id, instance_key))
        if record is not None and record["status"] in ("succeeded", "skipped"):
            return record["result"]
        if record is not None and record["status"] in ("failed", "cancelled"):
            raise WorkflowFailed(cnode.site_id, record["error"].get("reason") or "node failed")
        input_value = self._resolve_inputs(node, scope)
        if record is None:
            self._start_node(cnode, instance_key, node.kind, input_value)
            self._emit(EventType.step, {"node": cnode.site_id, "instance": instance_key,
                                        "kind": node.kind, "title": node.title,
                                        "phase": "started"})
        try:
            result = fn(node, scope)
        except WorkflowFailed as exc:
            self._settle(cnode, instance_key, "failed", {}, str(exc))
            if exc.site_id != cnode.site_id:
                # Name the full site so a failure inside a fan-out identifies the instance's node.
                raise WorkflowFailed(cnode.site_id, str(exc).split(":", 1)[-1].strip()) from None
            raise
        except (EvalError, ValueError, OSError) as exc:
            self._settle(cnode, instance_key, "failed", {}, f"{type(exc).__name__}: {exc}")
            raise WorkflowFailed(cnode.site_id, str(exc)) from None
        self._settle(cnode, instance_key, "succeeded", result, "")
        self._emit(EventType.step, {"node": cnode.site_id, "instance": instance_key,
                                    "kind": node.kind, "phase": "succeeded",
                                    "summary": self._summary(result)})
        return result

    def _transform(self, node: Node, scope: dict[str, Any]) -> Any:
        from .ops import apply_op

        args = {key: resolve_value(value, Scope(scope)) for key, value in node.args.items()}
        return apply_op(node.op, args)

    def _tool(self, cnode: CompiledNode, node: Node, scope: dict[str, Any]) -> Any:
        if node.tool not in self.tools:
            raise WorkflowFailed(node.id, f"tool {node.tool!r} is not available in this workflow's envelope")
        args = {key: resolve_value(value, Scope(scope)) for key, value in node.args.items()}
        with self._effect_identity(cnode.site_id, self._instance_key, "tool"):
            result = steps.call_tool(self.run, self.ctx, self.tools, node.tool, args)
        if not result.ok:
            raise WorkflowFailed(node.id, f"tool {node.tool} failed: {str(result.output)[:400]}")
        data = result.data if isinstance(result.data, dict) else {}
        return {"ok": True, "output": str(result.output)[:MAX_TOOL_OUTPUT_IN_RESULT],
                "data": _bounded(data, 16 * 1024)}

    def _join(self, node: Node, scope: dict[str, Any]) -> Any:
        items: dict[str, Any] = {}
        missing: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        pending = False
        for target in node.of:
            record = self._site_state(target)
            if record == "settled":
                if target not in scope:
                    raise WorkflowFailed(node.id, f"join target {target!r} has no value in this scope")
                if scope.get(target) is _JOIN_SKIPPED:
                    skipped.append(target)
                else:
                    items[target] = scope.get(target)
            elif record == "pending":
                pending = True
            elif record == "failed":
                failed.append(target)
            else:
                missing.append(target)
        if pending:
            raise _Wait()
        if node.policy == "all_required" and (missing or failed or skipped):
            raise WorkflowFailed(node.id,
                                 f"required inputs are missing: {sorted(set(missing + failed + skipped))}")
        if node.policy == "first_success":
            raise WorkflowFailed(node.id,
                                 "first_success requires concurrent execution with cancellation and draining")
        required = node.require if node.require is not None else len(node.of)
        complete = len(items) == len(node.of) and not (missing or failed or skipped)
        return {"complete": complete, "policy": node.policy, "items": items,
                "accepted": len(items) >= required,
                "missing": missing, "failed": failed, "skipped": skipped,
                "settled": len(items), "required": required}

    def _publish(self, node: Node, scope: dict[str, Any]) -> Any:
        published = []
        for spec in node.artifacts:
            value = resolve_value({"ref": spec.ref}, Scope(scope))
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, default=str)
            path, digest, byte_size = steps.save_artifact(self.ctx, spec.name, text)
            record = {"tool": "publish_artifact", "ok": True, "name": spec.name,
                      "artifact": path, "artifact_sha256": digest, "artifact_bytes": byte_size,
                      "media_type": spec.media_type, "run_id": self.run.id, "output": text[:2_000]}
            self.ctx.emit(Event(run_id=self.run.id, type=EventType.tool_result, data=record))
            published.append({"name": spec.name, "artifact": path, "sha256": digest,
                              "bytes": byte_size, "primary": spec.primary,
                              "media_type": spec.media_type, "run_id": self.run.id})
        return {"artifacts": published}

    def _ask(self, cnode: CompiledNode, scope: dict[str, Any]) -> Any:
        node = cnode.node
        key = self._instance_key
        record = self.nodes.get((cnode.site_id, key))
        if record is not None and record["status"] == "succeeded":
            return record["result"]
        if record is not None and record["status"] in ("failed", "cancelled"):
            raise WorkflowFailed(cnode.site_id, record["error"].get("reason") or "question failed")
        question = self.questions.get((cnode.site_id, key))
        rendered = self._render(node.question, self._resolve_inputs(node, scope))
        identity = {"question": rendered, "options": list(node.options)}
        if record is None:
            self._start_node(cnode, key, "ask", identity)
        elif record.get("input_hash") != _hash(identity):
            raise WorkflowFailed(cnode.site_id, "the persisted question inputs changed during continuation")

        if question is None:
            expires = _expiry(node.timeout_seconds)
            question = self._persist_question(cnode.site_id, key, rendered, node.options, expires)
            self.questions[(cnode.site_id, key)] = question
            self._emit(EventType.human_needed, {"node": cnode.site_id, "kind": "question",
                                                "instance": key, "question": rendered,
                                                "options": list(node.options),
                                                "expires_at": expires})
            raise _Wait()
        if question["status"] == "pending":
            # Older interrupted runs may have a question without its node record. Re-assert
            # the paired waiting state atomically, while keeping the existing question ID.
            if record is None or record.get("status") != "waiting":
                question = self._persist_question(cnode.site_id, key, rendered, node.options,
                                                  str(question["expires_at"]))
                self.questions[(cnode.site_id, key)] = question
            raise _Wait()
        if question["status"] == "answered":
            result = {"answer": question["answer"], "question_id": question["id"]}
            self._settle(cnode, key, "succeeded", result, "")
            return result
        self._settle(cnode, key, "failed", {}, f"question {question['status']}")
        raise WorkflowFailed(cnode.site_id, f"the question {question['status']} before an answer arrived")

    # ------------------------------------------------------- bounded constructs

    def _map(self, cnode: CompiledNode, scope: dict[str, Any]) -> Any:
        node = cnode.node
        over = resolve_value(node.over, Scope(scope))
        if not isinstance(over, list):
            raise WorkflowFailed(cnode.site_id, f"'over' must resolve to a list, got {type(over).__name__}")
        cap = min(node.max_items, int(self.budget.get("max_fanout") or node.max_items))
        if len(over) > cap:
            raise WorkflowFailed(cnode.site_id,
                                 f"fan-out over {len(over)} items exceeds the allowed {cap}; "
                                 f"raise max_items/max_fanout deliberately or narrow the input")
        body = self.compiled.children_of(cnode.site_id, "body")
        keys: list[str] = []
        items: list[Any] = []
        skipped: list[str] = []
        unsettled = 0
        for index, item in enumerate(over):
            item_scope = dict(scope)
            item_scope["item"] = item
            item_scope["index"] = index
            key = _escape_key(self._item_key(node, item, item_scope, index))
            keys.append(key)
            if keys.count(key) > 1:
                raise WorkflowFailed(cnode.site_id, f"duplicate item key {key!r}; item keys must be unique")
            item_prefix = ""
            interrupted = False
            try:
                with self._within(f"item:{key}"):
                    item_prefix = self._instance_key
                    value = self._walk(body, item_scope, collect_independent_questions=True)
            except _Wait:
                interrupted = True
                value = None
            except WorkflowFailed as exc:
                if node.on_item_failure == "skip":
                    skipped.append(key)
                    self._emit(EventType.log, {"node": cnode.site_id, "item": key,
                                               "note": f"item skipped: {exc}"})
                    continue
                raise
            pending_for_item = bool(item_prefix) and any(
                question["status"] == "pending"
                and (question["instance_key"] == item_prefix
                     or question["instance_key"].startswith(f"{item_prefix}|"))
                for question in self.questions.values())
            if interrupted and not pending_for_item:
                raise _Wait()
            if pending_for_item:
                unsettled += 1
                if unsettled >= max(1, node.concurrency):
                    raise _Wait()
                continue
            items.append(value)
        if unsettled:
            raise _Wait()
        complete = not skipped and len(items) == len(over)
        result = {"keys": keys, "items": items, "skipped": skipped, "complete": complete,
                  "count": len(items), "expected": len(over)}
        self._record_container(cnode, result)
        return result

    def _item_key(self, node: Node, item: Any, item_scope: dict[str, Any], index: int) -> str:
        if not node.item_key:
            return f"#{index}"
        value = resolve_value({"ref": f"item.{node.item_key}"}, Scope(item_scope))
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            text = str(value)
            if len(text) > 200:
                raise WorkflowFailed(node.id, "item_key resolves to a value longer than 200 characters")
            return text
        raise WorkflowFailed(node.id, f"item_key must resolve to a string or number, got {type(value).__name__}")

    def _repeat(self, cnode: CompiledNode, scope: dict[str, Any]) -> Any:
        node = cnode.node
        body = self.compiled.children_of(cnode.site_id, "body")
        results: list[Any] = []
        iteration = 0
        while iteration < node.max_iterations:
            iteration += 1
            scope_with_iter = dict(scope)
            scope_with_iter["iteration"] = iteration
            with self._within(f"iter:{iteration}"):
                value = self._walk(body, scope_with_iter)
            results.append(value)
            scope[cnode.site_id] = {"iteration": iteration, "result": value}
            if evaluate(node.until, Scope(scope)):
                break
        else:
            # The loop ended by exhausting its bound: honest, explicit, not an error.
            self._emit(EventType.log, {"node": cnode.site_id,
                                       "note": f"repeat ended at its bound ({node.max_iterations}) without the until condition holding"})
        result = {"iterations": iteration, "results": results, "result": results[-1] if results else None}
        self._record_container(cnode, result)
        return result

    # ------------------------------------------------------------------ verify

    def _verify(self, cnode: CompiledNode, scope: dict[str, Any]) -> Any:
        node = cnode.node
        # Count only exact verifier round records. Check memo keys such as ``|r1:c0``
        # must not be mistaken for another verifier round.
        prefix = f"{self._instance_key}|r"
        round_numbers = [int(key[len(prefix):]) for site, key in self.nodes
                         if site == cnode.site_id and key.startswith(prefix)
                         and key[len(prefix):].isdigit()]
        rounds = max(round_numbers, default=0)
        target = cnode.repair_target

        # Scope itself is reconstructed from settled producers on every attempt. Replay
        # each durable repair result before reading a later verification round, so a crash
        # after adoption cannot restore the pre-repair value.
        if rounds:
            if target is None:
                raise WorkflowFailed(cnode.site_id, "the saved repair round has no adoption target")
            for prior_round in range(1, rounds + 1):
                repair_key = f"{self._instance_key}|repair:{prior_round}"
                repair_record = self.nodes.get((cnode.site_id, repair_key))
                if repair_record is None or repair_record["status"] != "succeeded":
                    raise WorkflowFailed(cnode.site_id,
                                         f"repair round {prior_round} has no settled replacement to recheck")
                replacement = self._replacement(cnode, repair_record.get("result"), prior_round)
                self._adopt_replacement(cnode, scope, target, replacement, prior_round)

        while True:
            instance = self._instance_key if rounds == 0 else f"{self._instance_key}|r{rounds}"
            record = self.nodes.get((cnode.site_id, instance))
            if record is not None and record["status"] in ("failed", "cancelled"):
                raise WorkflowFailed(cnode.site_id, record["error"].get("reason") or "verification failed")
            if record is not None and record["status"] == "succeeded":
                result = record.get("result") if isinstance(record.get("result"), dict) else {}
                if result.get("ok") is True:
                    self._apply_verification_result(result.get("verified") is True)
                    return result
                if result.get("ok") is not False:
                    raise WorkflowFailed(cnode.site_id, "the saved verification result is malformed")
                # A failed check round is completed work. Reuse its durable findings
                # rather than rerunning a command or asking the same question again.
                checks = list(result.get("checks") or [])
                advisory = list(result.get("advisory") or [])
            else:
                if record is None:
                    self._start_node(cnode, instance, "verify", {"round": rounds})
                    self._emit(EventType.step, {"node": cnode.site_id, "instance": instance,
                                                "kind": "verify", "phase": "started"})
                checks, advisory = self._run_checks(cnode, scope, instance)
            independent = [c for c in checks if c["kind"] in ("schema", "artifact", "command", "human")]
            failed = [c for c in independent if not c["ok"]]
            passed = [c for c in independent if c["ok"]]
            advisory_failed = [c for c in advisory if not c["ok"]]
            if not failed and not advisory_failed:
                # "Verified" means: independent evidence passed and nothing failed - an
                # advisory reviewer's objection counts as a failure here too.
                verified = bool(passed)
                result = {"ok": True, "checks": checks, "advisory": advisory,
                          "verified": verified, "rounds": rounds}
                self._apply_verification_result(verified)
                self._settle(cnode, instance, "succeeded", result, "")
                return result
            # Failure: apply the declared policy.
            policy = node.on_fail
            detail = "; ".join(f"{c['kind']}: {c['detail']}" for c in failed + advisory_failed)
            if policy.action == "continue":
                result = {"ok": False, "checks": checks, "advisory": advisory,
                          "verified": False, "rounds": rounds,
                          "note": "the plan chose to continue with an unverified result"}
                self._apply_verification_result(False)
                self._settle(cnode, instance, "succeeded", result, "")
                return result
            if policy.action == "repair" and rounds < min(policy.rounds, int(self.budget.get("max_repairs") or 0)):
                if target is None:
                    raise WorkflowFailed(cnode.site_id, "the repair policy has no validated adoption target")
                next_round = rounds + 1
                round_result = {"ok": False, "checks": checks, "advisory": advisory,
                                "verified": False, "rounds": rounds,
                                "repair": {"target": target, "round": next_round}}
                if record is None or record["status"] != "succeeded":
                    self._settle(cnode, instance, "succeeded", round_result, "")
                repair_key = f"{self._instance_key}|repair:{next_round}"
                if (cnode.site_id, repair_key) not in self.nodes:
                    self._spend(cnode.site_id, "repairs")
                repair_result = self._repair_step(cnode, scope, repair_key, policy.instruction, detail)
                replacement = self._replacement(cnode, repair_result, next_round)
                self._adopt_replacement(cnode, scope, target, replacement, next_round)
                rounds = next_round
                continue
            self._apply_verification_result(False)
            result = {"ok": False, "checks": checks, "advisory": advisory,
                      "verified": False, "rounds": rounds}
            self._settle(cnode, instance, "failed", result, detail)
            raise WorkflowFailed(cnode.site_id, f"verification failed: {detail}")

    def _apply_verification_result(self, verified: bool) -> None:
        """Keep the workflow-level summary false after any final failed criterion."""
        if verified:
            self.verified = True if self.verified is None else self.verified
        else:
            self.verified = False

    def _run_checks(self, cnode: CompiledNode, scope: dict[str, Any],
                    instance: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        independent: list[dict[str, Any]] = []
        advisory: list[dict[str, Any]] = []
        for index, check in enumerate(cnode.node.checks):
            try:
                value = resolve_value({"ref": check.ref}, Scope(scope)) if check.ref else None
            except EvalError as exc:
                independent.append({"kind": check.kind, "ok": False, "detail": str(exc),
                                    **({"ref": check.ref} if check.ref else {})})
                continue
            if check.kind == "schema":
                from ..toolcalling.validate import validate_value

                problems = validate_value(check.schema_, value)
                outcome = {"kind": "schema", "ok": not problems,
                           "detail": "; ".join(problems[:4]) if problems else "schema matched"}
            elif check.kind == "artifact":
                outcome = self._check_artifact(check, value, scope)
            elif check.kind == "command":
                outcome = self._check_command(cnode, check, instance, index)
            elif check.kind == "human":
                outcome = self._check_human(cnode, check, instance, index)
            elif check.kind == "agent_review":
                advisory.append(self._check_review(cnode, check, scope, instance, index, value))
                continue
            if check.ref:
                outcome["ref"] = check.ref
            independent.append(outcome)
        return independent, advisory

    def _check_artifact(self, check: Any, value: Any, scope: dict[str, Any]) -> dict[str, Any]:
        """Re-read the published bytes and confirm identity; never trust the reference alone."""
        record = value if isinstance(value, dict) else {}
        path = record.get("artifact") or (record.get("workspace_file") or {}).get("artifact", "")
        digest = record.get("sha256") or (record.get("workspace_file") or {}).get("sha256", "")
        if not path or not digest:
            return {"kind": "artifact", "ok": False, "detail": "the reference is not a published artifact record"}
        if check.expect_sha256 and check.expect_sha256 != digest:
            return {"kind": "artifact", "ok": False,
                    "detail": f"recorded sha256 {digest[:12]}… does not match the expected {check.expect_sha256[:12]}…"}
        owner_run = str(record.get("run_id") or self.run.id)
        content = _read_published_artifact(self.ctx, owner_run, str(path))
        if content is None:
            return {"kind": "artifact", "ok": False,
                    "detail": "the artifact file is missing, unreadable or not a regular file"}
        actual = hashlib.sha256(content).hexdigest()
        if actual != digest:
            return {"kind": "artifact", "ok": False,
                    "detail": "the artifact bytes no longer match their recorded hash"}
        size = len(content)
        if check.min_bytes is not None and size < check.min_bytes:
            return {"kind": "artifact", "ok": False, "detail": f"{size} bytes is below the required minimum"}
        if check.max_bytes is not None and size > check.max_bytes:
            return {"kind": "artifact", "ok": False, "detail": f"{size} bytes exceeds the allowed maximum"}
        return {"kind": "artifact", "ok": True, "detail": f"verified {size} bytes against sha256"}

    def _check_command(self, cnode: CompiledNode, check: Any, instance: str,
                       index: int) -> dict[str, Any]:
        """A fixed argv through the governed shell tool, executed once per verify attempt.

        The result is memoized in the node record so re-entering the interpreter while a
        sibling check waits (a human answer, a reviewer step) can never re-run the command:
        an effect is executed once, and its recorded outcome is what later passes read.
        """
        memo_key = f"{instance}:c{index}"
        record = self.nodes.get((cnode.site_id, memo_key))
        if record is not None and record["status"] in ("succeeded", "failed"):
            return dict(record["result"] or {"kind": "command", "ok": False, "detail": "no recorded outcome"})
        self._ensure_open(cnode, memo_key, "verify", {"check": index, "of": instance})
        outcome = self._run_command(cnode, check, instance, index)
        try:
            self._persist_settle(cnode.site_id, memo_key,
                                 status="succeeded" if outcome.get("ok") else "failed", result=outcome)
        except ValueError:
            pass
        self.nodes[(cnode.site_id, memo_key)] = {
            "site_id": cnode.site_id, "instance_key": memo_key,
            "status": "succeeded" if outcome.get("ok") else "failed", "result": outcome,
            "error": {}, "run_id": None}
        return outcome

    def _run_command(self, cnode: CompiledNode, check: Any, instance: str,
                      index: int) -> dict[str, Any]:
        """Run the fixed argv exactly once through the governed shell tool."""
        if "shell" not in self.tools:
            return {"kind": "command", "ok": False,
                    "detail": "this workflow has no shell tool, so a command check cannot run"}
        command = " ".join(_quote(part) for part in check.argv)
        with self._effect_identity(cnode.site_id, f"{instance}:c{index}", "command"):
            result = steps.call_tool(self.run, self.ctx, self.tools, "shell",
                                     {"command": command, "timeout": check.timeout_seconds})
        if not result.ok:
            return {"kind": "command", "ok": False, "detail": f"the command could not run: {str(result.output)[:300]}"}
        exit_code = int((result.data or {}).get("exit_code", 0)) if isinstance(result.data, dict) else 0
        ok = exit_code == check.expect_exit
        return {"kind": "command", "ok": ok,
                "detail": f"exit {exit_code} (expected {check.expect_exit})",
                "output": str(result.output)[:1_000]}

    @contextlib.contextmanager
    def _effect_identity(self, site_id: str, instance_key: str, slot: str):
        previous = self.ctx.workflow_action_identity
        self.ctx.workflow_action_identity = {
            "workflow_run_id": self.wf_id, "revision_id": self.revision_id,
            "site_id": site_id, "instance_key": instance_key, "slot": slot,
        }
        try:
            yield
        finally:
            self.ctx.workflow_action_identity = previous

    def _check_human(self, cnode: CompiledNode, check: Any, instance: str, index: int) -> dict[str, Any]:
        key = f"{instance}:h{index}"
        human_site = f"{cnode.site_id}-human-{index + 1}"
        human_node = replace(cnode, site_id=human_site)
        prompt = f"{check.prompt} (answer yes or no)"
        identity = {"question": prompt, "options": ["yes", "no"]}
        record = self.nodes.get((human_site, key))
        if record is None:
            # A human verification is a durable ask too. Give it its own instance so
            # create_question can atomically persist the question and waiting node.
            self._start_node(human_node, key, "ask", identity)
        elif record.get("input_hash") != _hash(identity):
            raise WorkflowFailed(cnode.site_id, "the persisted human check inputs changed during continuation")

        question = self.questions.get((human_site, key))
        if question is None:
            expires = _expiry(check.timeout_seconds)
            self._persist_question(human_site, key, prompt, ["yes", "no"], expires)
            self._emit(EventType.human_needed, {"node": human_site, "verify_node": cnode.site_id,
                                                "kind": "human_check",
                                                "question": prompt, "expires_at": expires})
            raise _Wait()
        if question["status"] == "pending":
            if record is None or record.get("status") != "waiting":
                self._persist_question(human_site, key, prompt, ["yes", "no"],
                                       str(question["expires_at"]))
            raise _Wait()

        if question["status"] == "answered":
            result = {"answer": question["answer"], "question_id": question["id"]}
            if record is None or record.get("status") not in ("succeeded", "failed", "cancelled", "skipped"):
                self._settle(human_node, key, "succeeded", result, "")
        else:
            reason = f"the review {question['status']} before it was answered"
            terminal = "cancelled" if question["status"] == "cancelled" else "failed"
            if record is None or record.get("status") not in ("succeeded", "failed", "cancelled", "skipped"):
                self._settle(human_node, key, terminal, {}, reason)
            return {"kind": "human", "ok": False, "detail": reason}

        answer = str(question["answer"]).strip().lower()
        ok = answer in ("yes", "y", "true", "approve", "approved", "ok", "pass")
        return {"kind": "human", "ok": ok, "detail": f"a person answered {answer[:60]!r}"}

    def _check_review(self, cnode: CompiledNode, check: Any, scope: dict[str, Any], instance: str,
                      index: int, value: Any) -> dict[str, Any]:
        """An advisory second opinion. It can fail a result, never certify one."""
        key = f"{instance}:v{index}"
        record = self.nodes.get((cnode.site_id, key))
        if record is not None and record["status"] in ("succeeded", "failed"):
            result = record.get("result") if record["status"] == "succeeded" else {}
            verdict = result.get("output") if isinstance(result, dict) else None
            if not isinstance(verdict, dict):
                verdict = {}
            if record["status"] == "failed":
                return {"kind": "agent_review", "ok": False,
                        "detail": record["error"].get("reason") or "the reviewer step failed"}
            return {"kind": "agent_review", "ok": verdict.get("pass") is True,
                    "detail": str(verdict.get("reason") or "")[:600], "advisory": True}
        self._dispatch_step(cnode, key, scope, instruction=check.instruction,
                            model=check.model, role="verifier", subject=value,
                            output_schema=_VERIFIER_SCHEMA, tools=[], skills=[])
        raise _Wait()

    def _repair_step(self, cnode: CompiledNode, scope: dict[str, Any], key: str,
                     instruction: str, detail: str) -> dict[str, Any]:
        text = instruction or "Repair the failed value using the verifier's findings."
        text += " Return exactly one JSON object with a replacement field containing the complete replacement value."
        result = self._dispatch_step(cnode, key, scope, instruction=text, model="$bot", role="worker",
                                     subject={"failure": detail,
                                              "target": cnode.repair_target,
                                              "previous": self._previous_results(scope)},
                                     output_schema=_REPAIR_SCHEMA,
                                     tools=list(self.compiled.plan.envelope.tools),
                                     skills=list(self.compiled.plan.envelope.skills))
        if not isinstance(result, dict):
            raise WorkflowFailed(cnode.site_id, "the repair step has no validated result")
        return result

    def _replacement(self, cnode: CompiledNode, result: Any, round_number: int) -> Any:
        if not isinstance(result, dict) or not isinstance(result.get("output"), dict) \
                or "replacement" not in result["output"]:
            raise WorkflowFailed(cnode.site_id,
                                 f"repair round {round_number} did not return a replacement value")
        replacement = result["output"]["replacement"]
        if len(_canonical(replacement).encode("utf-8")) > MAX_RESULT_BYTES:
            raise WorkflowFailed(cnode.site_id,
                                 f"repair round {round_number} replacement exceeds {MAX_RESULT_BYTES} bytes")
        return replacement

    def _adopt_replacement(self, cnode: CompiledNode, scope: dict[str, Any], target: str,
                           replacement: Any, round_number: int) -> None:
        previous = scope.get(target)
        if _canonical(previous) == _canonical(replacement):
            raise WorkflowFailed(cnode.site_id,
                                 f"repair round {round_number} made no progress for {target!r}")
        scope[target] = replacement

    def _previous_results(self, scope: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for site_id, value in scope.items():
            if site_id in ("input", "item", "index", "iteration"):
                continue
            if value is _JOIN_SKIPPED:
                continue
            out[site_id] = _bounded(value, 4_000)
        return out

    # ------------------------------------------------------------------- agent

    def _agent(self, cnode: CompiledNode, scope: dict[str, Any]) -> Any:
        key = self._instance_key
        record = self.nodes.get((cnode.site_id, key))
        if record is not None and record["status"] in ("succeeded", "skipped"):
            return record["result"]
        if record is not None and record["status"] in ("failed", "cancelled"):
            raise WorkflowFailed(cnode.site_id, record["error"].get("reason") or "the step failed")
        self._dispatch_step(cnode, key, scope, instruction=cnode.node.instruction,
                            model=cnode.node.model, role=cnode.node.role, subject=None,
                            output_schema=cnode.node.output_schema, tools=cnode.node.tools,
                            skills=cnode.node.skills)
        raise _Wait()

    def _dispatch_step(self, cnode: CompiledNode, instance_key: str, scope: dict[str, Any], *,
                       instruction: str, model: str, role: str, subject: Any,
                       output_schema: Optional[dict[str, Any]], tools: list[str],
                       skills: list[str]) -> Optional[dict[str, Any]]:
        node = cnode.node
        record = self.nodes.get((cnode.site_id, instance_key))
        if record is not None and record["status"] == "succeeded":
            result = record.get("result")
            return result if isinstance(result, dict) else None
        if record is not None and record["status"] in ("failed", "cancelled"):
            raise WorkflowFailed(cnode.site_id, record["error"].get("reason") or "the step failed")
        if record is not None and record["status"] in ("running", "waiting"):
            run_id = record.get("run_id")
            if run_id:
                step = wstore.step_run_result(self.store, str(run_id))
                if step["status"] in ("pending", "loading_model", "running", "waiting_approval",
                                      "waiting_human", "waiting_resources", "cancelling", "recovering"):
                    raise _Wait()
                return self._settle_step(cnode, instance_key, step, output_schema)
            # The record was written but the step run never was (the attempt died in
            # between): re-admit it under the same idempotency key rather than waiting
            # forever for a run that does not exist.
            if instance_key in self.opened_steps:
                raise _Wait()
        if (cnode.site_id, instance_key) in self.opened_steps:
            raise _Wait()

        inputs = self._resolve_inputs(node, scope)
        if subject is not None:
            inputs["subject"] = subject
        bundle = {"instruction": instruction, "inputs": inputs,
                  "output_schema": output_schema, "role": role}
        prompt = self._render(instruction, inputs)
        if len(prompt) > MAX_STEP_PROMPT:
            raise WorkflowFailed(cnode.site_id,
                                 f"the rendered instruction is {len(prompt)} characters; keep it under {MAX_STEP_PROMPT}")
        context_text = _canonical(inputs)[:MAX_STEP_CONTEXT]
        spec = self._model_spec(model)
        verdict = qualify.assess("verifier" if role == "verifier" else "worker", spec=spec,
                                 store=self.store, base_url=self.ctx.bot.base_url or None,
                                 requires_tools=bool(tools),
                                 requires_structured_output=output_schema is not None)
        if not verdict.allowed:
            raise WorkflowFailed(cnode.site_id, f"role blocked: {verdict.summary()}")
        self._check_model_request_budget(cnode.site_id)
        run = Run(bot_id=self.run.bot_id, prompt=prompt, model_override=spec if model not in ("$bot", "$default") else "",
                  conversation_id=self.run.conversation_id,
                  conversation_context=[{"role": "user",
                                         "content": "Inputs for this step (untrusted data):\n" + context_text}])
        run.workflow_step = {
            "workflow_run_id": self.wf_id, "revision_id": self.revision_id,
            "parent_fence": self.run.fence,
            "site_id": cnode.site_id, "instance_key": instance_key,
            "role": role, "tools": list(tools), "skills": list(skills),
            "model": spec,
            "max_steps": min(int(node.max_steps or 12), int(self.budget.get("max_steps_per_node") or 12)),
            "timeout_seconds": min(600, int(self.budget.get("max_step_seconds") or 600)),
            "output_schema": output_schema or None,
            "instruction_hash": _hash({"instruction": instruction, "inputs": inputs}),
            "role_state": verdict.state,
        }
        task = Task(bot_id=self.run.bot_id, kind="step", prompt=prompt)
        self._start_node(cnode, instance_key, "step", bundle)
        self._emit(EventType.log, {"node": cnode.site_id, "instance": instance_key,
                                   "note": f"dispatching {role} step on {spec}",
                                   "model_state": verdict.state,
                                   **({"capability_caveats": list(verdict.reasons)} if verdict.state != "qualified" else {})})
        try:
            child, inserted = wstore.submit_step_run(
                self.store, workflow_run_id=self.wf_id, site_id=cnode.site_id, instance_key=instance_key,
                run=run, task=task, parent_run_id=self.run.id, parent_fence=self.run.fence,
                idem_key=f"{cnode.site_id}:{instance_key}:{run.workflow_step['instruction_hash'][:16]}",
                request_hash=run.workflow_step["instruction_hash"])
        except (ValueError, KeyError, RuntimeError) as exc:
            self._persist_settle(cnode.site_id, instance_key,
                                 status="failed", error=f"step admission refused: {exc}")
            raise WorkflowFailed(cnode.site_id, f"step admission refused: {exc}") from None
        if inserted:
            self.store.bus.notify("work")
        self.opened_steps.add((cnode.site_id, instance_key))
        raise _Wait()

    def _settle_step(self, cnode: CompiledNode, instance_key: str, step: dict[str, Any],
                     output_schema: Optional[dict[str, Any]]) -> dict[str, Any]:
        text = str(step.get("text") or "")
        if step["status"] != "succeeded":
            if step["status"] == "outcome_unknown":
                raise RunAborted("outcome_unknown", f"the {cnode.site_id} step has an unresolved effect; reconcile it before retrying")
            reason = f"the step ended as {step['status']}"
            if step.get("exit_reason"):
                reason += f" ({step['exit_reason']})"
            if step.get("error"):
                reason += f": {str(step['error'])[:300]}"
            self._persist_settle(cnode.site_id, instance_key,
                                 status="failed", error=reason, run_id=None)
            raise WorkflowFailed(cnode.site_id, reason)
        value: Any = {"text": text[:MAX_RESULT_BYTES]}
        if output_schema is not None:
            parsed, problems = _parse_structured(text, output_schema)
            if problems:
                self._persist_settle(
                    cnode.site_id, instance_key, status="failed",
                    error="the step's answer did not satisfy its output contract: " + problems,
                    run_id=None)
                raise WorkflowFailed(cnode.site_id,
                                     "the step's answer did not satisfy its output contract: " + problems)
            value["output"] = parsed
        value["steps"] = step.get("steps")
        value["tokens"] = step.get("tokens")
        self._persist_settle(cnode.site_id, instance_key, status="succeeded", result=value)
        self.nodes[(cnode.site_id, instance_key)] = {
            "site_id": cnode.site_id, "instance_key": instance_key, "status": "succeeded",
            "result": value, "error": {}, "run_id": None}
        self._emit(EventType.step, {"node": cnode.site_id, "instance": instance_key,
                                    "kind": "step", "phase": "succeeded",
                                    "summary": str(text)[:300]})
        return value

    # ---------------------------------------------------------------- utilities

    def _site_state(self, site_id: str) -> str:
        records = [r for (site, _key), r in self.nodes.items() if site == site_id]
        if not records:
            return "missing"
        statuses = {r["status"] for r in records}
        if statuses & {"running", "waiting", "pending"}:
            return "pending"
        if "failed" in statuses or "cancelled" in statuses:
            return "failed"
        if statuses <= {"succeeded", "skipped"}:
            return "settled"
        return "pending"

    def _resolve_inputs(self, node: Node, scope: dict[str, Any]) -> dict[str, Any]:
        return {key: resolve_value(value, Scope(scope)) for key, value in node.inputs.items()}

    def _render(self, text: str, inputs: dict[str, Any]) -> str:
        from .expr import render_template

        if "{{" not in text:
            return text
        return render_template(text, {key: _as_text(value) for key, value in inputs.items()})

    def _model_spec(self, model: str) -> str:
        if model in ("", "$bot", "$default"):
            return self.ctx.bot.model
        return model

    def _spend(self, site_id: str, key: str) -> None:
        """Charge one deterministic unit against a root-level allowance.

        Provider requests are charged at the durable usage-reservation boundary, not when
        a worker node is admitted. A declared zero model-call limit is checked before
        dispatch here and enforced transactionally again for every actual request.
        """
        limit_key = {"nodes": "max_nodes", "repairs": "max_repairs"}[key]
        used = int(self.ledger.get(key, 0)) + 1
        limit = self.budget.get(limit_key)
        if limit is not None and used > int(limit):
            raise WorkflowFailed(site_id, f"the workflow's {limit_key} budget is exhausted ({limit})")
        self.ledger[key] = used
        wstore.update_workflow_run(self.store, self.wf_id, attempt_run_id=self.run.id,
                                   owner_fence=self.run.fence, revision_id=self.revision_id,
                                   ledger=self.ledger)

    def _check_model_request_budget(self, site_id: str) -> None:
        """Avoid launching a worker when no request remains; reservations are the race-safe gate."""
        limit = int(self.budget.get("max_model_calls", 12))
        used = int(self.ledger.get("model_calls", 0))
        if used >= limit:
            raise WorkflowFailed(site_id,
                                 f"the workflow's max_model_calls budget is exhausted ({limit} actual requests; "
                                 f"{used} already started)")

    def _record_container(self, cnode: CompiledNode, result: Any) -> None:
        """Record a bounded construct's own aggregate, so the plan view shows real state."""
        key = (cnode.site_id, self._instance_key)
        record = self.nodes.get(key)
        if record is None:
            self._start_node(cnode, key[1], cnode.node.kind, {"container": True})
            record = self.nodes[key]
        if record["status"] in ("running", "waiting"):
            try:
                self._persist_settle(cnode.site_id, key[1], status="succeeded", result=result)
            except ValueError:
                pass
            record["status"] = "succeeded"
            record["result"] = result

    def _ensure_open(self, cnode: CompiledNode, instance_key: str, kind: str,
                     input_value: Any) -> None:
        """Write the node record before the node does anything (crash-safe identity)."""
        try:
            wstore.open_node(self.store, self.wf_id, owner_run_id=self.run.id,
                             owner_fence=self.run.fence, revision_id=self.revision_id,
                             site_id=cnode.site_id, instance_key=instance_key, kind=kind,
                             input_value=input_value, input_hash=_hash(input_value))
        except wstore.WorkflowPauseRequested:
            raise _Wait() from None
        except ValueError as exc:
            raise WorkflowFailed(cnode.site_id, str(exc)) from None
        self.nodes[(cnode.site_id, instance_key)] = {
            "site_id": cnode.site_id, "instance_key": instance_key, "status": "running",
            "result": {}, "error": {}, "run_id": None}

    def _start_node(self, cnode: CompiledNode, instance_key: str, kind: str,
                    input_value: Any) -> None:
        """Charge and open a new node atomically with the pause-request check."""
        with self.store._lock:
            if wstore.workflow_pause_requested(self.store, self.wf_id):
                raise _Wait()
            self._spend(cnode.site_id, "nodes")
            self._ensure_open(cnode, instance_key, kind, input_value)

    def _settle(self, cnode: CompiledNode, instance_key: str, status: str, result: Any, error: str) -> None:
        try:
            self._persist_settle(cnode.site_id, instance_key,
                                 status=status, result=result, error=error)
        except ValueError:
            # Another owner settled it first (a stale interpreter pass); the record wins.
            pass
        self.nodes[(cnode.site_id, instance_key)] = {
            "site_id": cnode.site_id, "instance_key": instance_key, "status": status,
            "result": result, "error": {"reason": error} if error else {}}

    def _mark_skipped(self, cnode: CompiledNode, instance_key: str, reason: str) -> None:
        record = self.nodes.get((cnode.site_id, instance_key))
        if record is not None:
            return
        self._ensure_open(cnode, instance_key, cnode.node.kind, {"skipped": reason})
        self._persist_settle(cnode.site_id, instance_key,
                             status="skipped", result={}, error=reason)
        self.nodes[(cnode.site_id, instance_key)] = {
            "site_id": cnode.site_id, "instance_key": instance_key, "status": "skipped",
            "result": {}, "error": {"reason": reason}}

    def _emit(self, kind: EventType, data: dict[str, Any]) -> None:
        self.ctx.emit(Event(run_id=self.run.id, type=kind, data=data))

    def _persist_settle(self, site_id: str, instance_key: str, **values: Any) -> None:
        wstore.settle_node(
            self.store, self.wf_id, site_id, instance_key,
            owner_run_id=self.run.id, owner_fence=self.run.fence, revision_id=self.revision_id,
            **values)

    def _persist_question(self, site_id: str, instance_key: str, question: str,
                          options: Any, expires_at: str) -> dict[str, Any]:
        return wstore.create_question(
            self.store, wf_id=self.wf_id, owner_run_id=self.run.id,
            owner_fence=self.run.fence, revision_id=self.revision_id,
            site_id=site_id, instance_key=instance_key, question=question,
            options=options, expires_at=expires_at)

    def _summary(self, value: Any) -> str:
        return _canonical(value)[:200]


def _read_published_artifact(ctx: Any, run_id: str, rel_path: str) -> Optional[bytes]:
    """Read one published artifact with the same safety rules the server uses: no symlinks,
    a bounded size, and only the ``artifacts/NNN-slug.txt`` shape."""
    import re
    from pathlib import Path

    if not re.fullmatch(r"artifacts/\d{3,6}-[a-z0-9_-]{1,40}\.txt", rel_path or ""):
        return None
    try:
        root = Path(ctx.config.run_dir(ctx.bot.name, run_id)).resolve()
    except Exception:  # noqa: BLE001 - an unresolvable run dir is simply unreadable
        return None
    current = root
    for part in Path(rel_path).parts:
        current = current / part
        try:
            if current.is_symlink():
                return None
        except OSError:
            return None
    try:
        if not current.is_file():
            return None
        if current.stat().st_size > 4_000_000:
            return None
        return current.read_bytes()
    except OSError:
        return None


def _as_text(value: Any) -> str:
    from .expr import to_text

    return to_text(value)


def _quote(part: str) -> str:
    """Quote one argv entry for the shell tool, which takes a command string."""
    import shlex

    return shlex.quote(part)


def _escape_key(key: str) -> str:
    """Escape the instance-key separator so nested keys can never alias.

    ``a|item:b`` inside a nested map must not compose to the same identity as ``a`` with
    item ``b``; a backslash escape keeps the key readable and unambiguous.
    """
    return key.replace("\\", "\\\\").replace("|", "\\|")


def _expiry(seconds: int) -> str:
    from datetime import timedelta

    return iso(utcnow() + timedelta(seconds=max(1, int(seconds))))


def _parse_structured(text: str, schema: dict[str, Any]) -> tuple[Any, str]:
    """Extract and validate a structured result. Returns (value, problems)."""
    from ..toolcalling.validate import validate_value

    candidate: Any = None
    stripped = text.strip()
    if stripped:
        try:
            candidate = json.loads(stripped)
        except json.JSONDecodeError:
            candidate = None
        if candidate is None:
            start, end = stripped.find("{"), stripped.rfind("}")
            if 0 <= start < end:
                try:
                    candidate = json.loads(stripped[start:end + 1])
                except json.JSONDecodeError:
                    candidate = None
    if candidate is None:
        return None, "no JSON object was found in the answer"
    problems = validate_value(schema, candidate)
    if problems:
        return None, "; ".join(problems[:4])
    return candidate, ""
