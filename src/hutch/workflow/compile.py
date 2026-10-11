"""Plan validation and lowering to a canonical, executable representation.

A plan is compiled before it is admitted, and again whenever it changes. Compilation is
pure: it reads the plan and nothing else (no store, no model, no disk), which is what
lets the same function check an imported file, a model-submitted plan and an amendment.

What compilation decides:

* **identity** - every node gets a stable site id (``parent.child`` inside a bounded
  construct); a site id never depends on the order items arrive in.
* **references** - every ``{"ref": ...}`` resolves to a declared input, a map local, or a
  node that runs *before* it. A forward or cross-container reference is an error, not a
  hopeful runtime lookup.
* **structure** - cycles exist only through ``repeat`` with a bound; nesting is bounded;
  branches and joins are explicit; a ``publish`` primary artifact is unique.
* **envelopes** - tools, models and skills a node asks for must be inside the workflow's
  declared envelope, and the envelope itself is bounded by operator ceilings.
* **cardinality** - the worst-case node count from nested fan-out and loops must fit the
  declared ``budget.max_nodes`` (nested budget expansion, checked statically).

Diagnostics are precise (JSON path + code). A plan with any error never reaches
admission: the compiler raises :class:`PlanInvalid` carrying every diagnostic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from .expr import is_ref, is_template
from .plan import CEILINGS, ArtifactSpec, Check, Condition, Node, Plan

#: The deterministic operation table lives with the operations themselves, so the plan
#: schema and the interpreter cannot disagree about what exists or what it accepts.
from .ops import TRANSFORM_OPS  # noqa: E402  (imported after the module docstring block)

CHECK_KINDS = {"schema", "artifact", "command", "human", "agent_review"}
#: Checks that can establish a verified outcome on their own.
INDEPENDENT_CHECKS = {"schema", "artifact", "command", "human"}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    path: str
    message: str
    severity: str = "error"

    def render(self) -> str:
        return f"{self.path or '$'}: {self.code} {self.message}"


class PlanInvalid(ValueError):
    def __init__(self, diagnostics: Sequence[Diagnostic]):
        self.diagnostics = [d for d in diagnostics if d.severity == "error"]
        super().__init__("; ".join(d.render() for d in self.diagnostics[:8]) or "invalid plan")


@dataclass
class CompiledNode:
    site_id: str
    node: Node
    order: int
    depth: int
    body_of: Optional[str]          # enclosing container's site id
    body_name: str                  # "body" | "then" | "else" | ""
    scope_path: str                 # diagnostic path, e.g. "nodes[0].body[1]"
    deps: tuple[str, ...]           # data dependencies (site ids)
    control_deps: tuple[str, ...]   # explicit `needs`
    instances: int                  # worst-case instances of this site

    @property
    def kind(self) -> str:
        return self.node.kind

    @property
    def is_step_run(self) -> bool:
        """Whether this site executes as an isolated run rather than in-process."""
        return self.node.kind == "agent"


@dataclass
class CompiledPlan:
    plan: Plan
    plan_hash: str
    nodes: list[CompiledNode]
    by_site: dict[str, CompiledNode]
    warnings: list[Diagnostic] = field(default_factory=list)

    def top_level(self) -> list[CompiledNode]:
        return [n for n in self.nodes if n.body_of is None]

    def children_of(self, site_id: str, body_name: str = "") -> list[CompiledNode]:
        out = [n for n in self.nodes if n.body_of == site_id]
        if body_name:
            out = [n for n in out if n.body_name == body_name]
        return out


def plan_structure(plan: dict[str, Any] | Plan) -> list[dict[str, Any]]:
    """The planned shape, flattened for a compact list view (the CLI, the API and the tool).

    This is *planned* structure only: a bounded construct appears as one entry with its body
    nested. Runtime instances come from the engine's node records, never from here.
    """
    payload = plan.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(plan, Plan) else plan
    out: list[dict[str, Any]] = []

    def walk(nodes: list[Any], parent: str, depth: int) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            site = f"{parent}.{node.get('id')}" if parent else str(node.get("id"))
            out.append({"site_id": site, "kind": node.get("kind"), "title": node.get("title") or "",
                        "parent": parent or None, "depth": depth,
                        "bounded": node.get("kind") in ("map", "expand", "branch", "repeat")})
            for body in ("body", "then", "else"):
                children = node.get(body)
                if isinstance(children, list) and children:
                    walk(children, site, depth + 1)

    nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if isinstance(nodes, list):
        walk(nodes, "", 0)
    return out


def plan_hash(plan: Plan) -> str:
    payload = plan.model_dump(by_alias=True, exclude_none=True, mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compile_plan(raw: Plan | dict[str, Any]) -> CompiledPlan:
    """Validate a plan and lower it. Raises :class:`PlanInvalid` on any error."""
    diagnostics: list[Diagnostic] = []
    plan = raw if isinstance(raw, Plan) else _parse(raw, diagnostics)
    if plan is None:
        raise PlanInvalid(diagnostics)

    compiler = _Compiler(plan, diagnostics)
    compiler.run()
    if any(d.severity == "error" for d in diagnostics):
        raise PlanInvalid(diagnostics)
    return compiler.finish()


def _parse(raw: Any, diagnostics: list[Diagnostic]) -> Optional[Plan]:
    try:
        return Plan.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError and friends
        for item in getattr(exc, "errors", lambda: [])():
            loc = ".".join(str(part) for part in item.get("loc", ()))
            diagnostics.append(Diagnostic("PLAN_SCHEMA", loc, str(item.get("msg", "invalid"))))
        if not diagnostics:
            diagnostics.append(Diagnostic("PLAN_SCHEMA", "", str(exc)[:400]))
        return None


class _Compiler:
    def __init__(self, plan: Plan, diagnostics: list[Diagnostic]):
        self.plan = plan
        self.diagnostics = diagnostics
        self.warnings: list[Diagnostic] = []
        self.nodes: list[CompiledNode] = []
        self.by_site: dict[str, CompiledNode] = {}
        self._order = 0
        self._seen_ids: set[str] = set()

    # -- public -----------------------------------------------------------------
    def run(self) -> None:
        self._check_inputs()
        self._check_envelope()
        self._walk(self.plan.nodes, scope=set(self.plan.inputs), depth=0, parent=None,
                   body_name="", path="nodes", instance_template=("once",))
        self._check_outputs()
        self._check_artifacts()
        self._check_budget()

    def finish(self) -> CompiledPlan:
        return CompiledPlan(plan=self.plan, plan_hash=plan_hash(self.plan),
                            nodes=list(self.nodes), by_site=dict(self.by_site),
                            warnings=list(self.warnings))

    # -- helpers ----------------------------------------------------------------
    def error(self, code: str, path: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.warnings.append(Diagnostic(code, path, message, severity="warning"))

    def _check_inputs(self) -> None:
        if len(self.plan.inputs) > CEILINGS["max_inputs"]:
            self.error("INPUTS_TOO_MANY", "inputs", "too many declared inputs")
        for name, spec in self.plan.inputs.items():
            if not name.isidentifier():
                self.error("INPUT_NAME", f"inputs.{name}", "input names must be identifiers")
            if spec.default is not None and spec.required:
                self.warn("INPUT_DEFAULT_UNUSED", f"inputs.{name}",
                          "a required input's default is never used")

    def _check_envelope(self) -> None:
        env = self.plan.envelope
        if env.max_parallel_steps > CEILINGS["max_parallel_steps"]:
            self.error("ENVELOPE_CEILING", "envelope.max_parallel_steps",
                       "exceeds the operator ceiling")
        if len(env.tools) > 64:
            self.error("ENVELOPE_TOOLS", "envelope.tools", "too many allowed tools")
        for name in env.tools:
            if not isinstance(name, str) or not name:
                self.error("ENVELOPE_TOOLS", "envelope.tools", "tool names must be strings")
        for model in env.models:
            if not model:
                self.error("ENVELOPE_MODELS", "envelope.models", "model bindings must be strings")

    def _walk(self, body: list[Node], *, scope: set[str], depth: int, parent: Optional[str],
              body_name: str, path: str, instance_template: tuple[str, ...],
              id_prefix: Optional[str] = None) -> None:
        if depth > CEILINGS["max_nesting_depth"]:
            self.error("NESTING_TOO_DEEP", path, "bounded constructs nest too deeply")
            return
        local_scope = set(scope)
        base = id_prefix if id_prefix is not None else parent
        for index, node in enumerate(body):
            site = node.id if base is None else f"{base}.{node.id}"
            node_path = f"{path}[{index}]"
            if site in self._seen_ids:
                self.error("NODE_ID_DUPLICATE", node_path, f"duplicate site id {site!r}")
                continue
            self._seen_ids.add(site)
            self._order += 1

            deps = self._collect_deps(node, local_scope, node_path)
            control = self._check_needs(node, local_scope, node_path)
            if node.kind == "join":
                control |= self._check_join_targets(node, local_scope, node_path)
            self._check_node(node, node_path, depth)

            compiled = CompiledNode(site_id=site, node=node, order=self._order, depth=depth,
                                    body_of=parent, body_name=body_name, scope_path=node_path,
                                    deps=tuple(sorted(deps)), control_deps=tuple(sorted(control)),
                                    instances=self._instances(node, depth))
            self.nodes.append(compiled)
            self.by_site[site] = compiled
            local_scope.add(site)

            if node.kind in ("map", "expand"):
                if node.kind == "expand" and not (node.allow_tools or node.allow_models):
                    self.error("EXPAND_ENVELOPE", node_path,
                               "an expand node must declare allow_tools or allow_models")
                self._walk(node.body, scope=local_scope | {"item", "index"}, depth=depth + 1,
                           parent=site, body_name="body", path=f"{node_path}.body",
                           instance_template=instance_template + (f"{site}[{{item_key}}]",))
            elif node.kind == "branch":
                self._walk(node.then, scope=local_scope, depth=depth + 1, parent=site,
                           body_name="then", path=f"{node_path}.then",
                           instance_template=instance_template + (f"{site}.then",),
                           id_prefix=f"{site}.then")
                self._walk(node.else_, scope=local_scope, depth=depth + 1, parent=site,
                           body_name="else", path=f"{node_path}.else",
                           instance_template=instance_template + (f"{site}.else",),
                           id_prefix=f"{site}.else")
            elif node.kind == "repeat":
                # The runtime exposes the current iteration to the body, so the compiler must too.
                self._walk(node.body, scope=local_scope | {"iteration"}, depth=depth + 1, parent=site,
                           body_name="body", path=f"{node_path}.body",
                           instance_template=instance_template + (f"{site}.iter",))

    # -- per-node checks --------------------------------------------------------
    def _check_node(self, node: Node, path: str, depth: int) -> None:
        if node.kind == "transform":
            ops = TRANSFORM_OPS.get(node.op)
            if ops is None:
                self.error("UNKNOWN_OP", f"{path}.op", f"unknown transform op {node.op!r}")
            else:
                unknown = set(node.args) - ops
                if unknown:
                    self.error("OP_ARGS", f"{path}.args",
                               f"unsupported arguments for {node.op}: {sorted(unknown)}")
        if node.kind == "tool" and node.tool not in set(self.plan.envelope.tools):
            self.error("TOOL_ENVELOPE", f"{path}.tool",
                       f"tool {node.tool!r} is outside the workflow envelope")
        if node.kind in ("map", "expand"):
            if node.concurrency > self.plan.envelope.max_parallel_steps:
                self.error("MAP_CONCURRENCY", f"{path}.concurrency",
                           "map concurrency exceeds the workflow envelope")
            if node.max_items > self.plan.budget.max_fanout:
                self.error("MAP_FANOUT", f"{path}.max_items",
                           "map max_items exceeds the declared budget.max_fanout")
            if not node.item_key:
                self.warn("MAP_NO_ITEM_KEY", path,
                          "no item_key: item identity falls back to arrival order, which is not "
                          "stable across reordering")
            for name in node.allow_tools:
                if name not in self.plan.envelope.tools:
                    self.error("EXPAND_TOOLS", f"{path}.allow_tools",
                               f"tool {name!r} is outside the workflow envelope")
            for name in node.allow_models:
                if name not in self.plan.envelope.models and name not in ("$bot", "$default"):
                    self.error("EXPAND_MODELS", f"{path}.allow_models",
                               f"model {name!r} is outside the workflow envelope")
        if node.kind == "agent":
            self._check_agent(node, path)
            self._check_instruction_placeholders(node, path)
        if node.kind == "verify":
            independent = [c for c in node.checks if c.kind in INDEPENDENT_CHECKS]
            if not independent:
                self.error("VERIFY_NO_EVIDENCE", f"{path}.checks",
                           "a verify node needs at least one independent check "
                           "(schema, artifact, command or human); agent_review is advisory")
            for index, check in enumerate(node.checks):
                self._check_check(check, f"{path}.checks[{index}]")
            if node.on_fail.action == "repair" and node.on_fail.rounds > self.plan.budget.max_repairs:
                self.error("REPAIR_BUDGET", f"{path}.on_fail.rounds",
                           "repair rounds exceed the declared budget.max_repairs")
        if node.kind == "join":
            if node.policy == "all_required" and node.require is not None:
                self.warn("JOIN_REQUIRE_IGNORED", f"{path}.require",
                          "all_required ignores require")
            if node.require is not None and node.require > len(node.of):
                self.error("JOIN_REQUIRE", f"{path}.require",
                           "require exceeds the number of joined nodes")

        if node.kind in ("ask",) and node.timeout_seconds > CEILINGS["max_question_wait_seconds"]:
            self.error("ASK_TIMEOUT", f"{path}.timeout_seconds", "timeout exceeds the ceiling")
        if node.kind == "publish":
            for index, art in enumerate(node.artifacts):
                if not art.name or any(ch not in _ARTIFACT_CHARS for ch in art.name):
                    self.error("ARTIFACT_NAME", f"{path}.artifacts[{index}].name",
                               "artifact names use letters, digits, dot, dash and underscore")

    def _check_agent(self, node: Node, path: str) -> None:
        if node.output_schema is not None:
            from hutch.toolcalling.validate import analyze_schema

            report = analyze_schema(node.output_schema)
            if not report.certifiable:
                detail = ", ".join(sorted(getattr(report, "unsupported", ()) or ())) or "unsupported keywords"
                self.error("OUTPUT_SCHEMA_UNCERTIFIABLE", f"{path}.output_schema",
                           f"the output schema cannot be certified locally ({detail})")
        allowed = set(self.plan.envelope.tools)
        for name in node.tools:
            if name not in allowed:
                self.error("AGENT_TOOLS", f"{path}.tools",
                           f"tool {name!r} is outside the workflow envelope")
        for name in node.skills:
            if name not in set(self.plan.envelope.skills):
                self.error("AGENT_SKILLS", f"{path}.skills",
                           f"skill {name!r} is outside the workflow envelope")
        if node.model not in ("$bot", "$default") and node.model not in set(self.plan.envelope.models):
            self.error("AGENT_MODEL", f"{path}.model",
                       f"model {node.model!r} is outside the workflow envelope")

    def _check_instruction_placeholders(self, node: Node, path: str) -> None:
        """Every ``{{ name }}`` in an instruction must be a declared input."""
        import re as _re

        for match in _re.finditer(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", node.instruction):
            if match.group(1) not in node.inputs:
                self.error("INSTRUCTION_PLACEHOLDER", f"{path}.instruction",
                           f"placeholder {match.group(1)!r} has no matching entry in inputs")

    def _check_check(self, check: Check, path: str) -> None:
        if check.kind == "command":
            if not check.argv or not all(isinstance(part, str) and part for part in check.argv):
                self.error("CHECK_ARGV", f"{path}.argv", "command argv entries must be non-empty strings")
            if check.cwd:
                self.error("CHECK_CWD", f"{path}.cwd",
                           "a command check always runs in the run workspace; a different working "
                           "directory is not supported yet, so this plan must not declare one")
        if check.kind == "artifact" and check.expect_sha256:
            if len(check.expect_sha256) != 64 or any(c not in "0123456789abcdef" for c in check.expect_sha256):
                self.error("CHECK_SHA", f"{path}.expect_sha256", "expects a lowercase hex sha256")

    # -- references and dependencies -------------------------------------------
    def _collect_deps(self, node: Node, scope: set[str], path: str) -> set[str]:
        deps: set[str] = set()
        for value_path, value in self._node_values(node):
            for ref in _iter_refs(value):
                head = _ref_head(ref)
                if head is None:
                    self.error("REF_SYNTAX", f"{path}.{value_path}", f"invalid reference {ref!r}")
                    continue
                if head == "input":
                    name = ref.split(".", 1)[1] if "." in ref else ""
                    if name not in self.plan.inputs:
                        self.error("REF_INPUT", f"{path}.{value_path}",
                                   f"reference to undeclared input {name!r}")
                elif head in ("item", "index"):
                    if head not in scope:
                        self.error("REF_LOCAL", f"{path}.{value_path}",
                                   f"{head!r} is only available inside a bounded construct")
                elif head in scope:
                    dep = self._longest_site(ref, scope) or head
                    deps.add(dep)
                    if self._traverses_container(head, ref, scope):
                        self.error("REF_CONTAINER_PATH", f"{path}.{value_path}",
                                   f"a reference may not reach inside the bounded construct "
                                   f"{head!r}; its own result is the join of its items")
                else:
                    self.error("REF_UNKNOWN", f"{path}.{value_path}",
                               f"reference to unknown or not-yet-run node {head!r}")
        return deps

    @staticmethod
    def _longest_site(ref: str, scope: set[str]) -> Optional[str]:
        """The longest dotted prefix of ``ref`` that names an in-scope site (or None)."""
        parts = ref.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            candidate = ".".join(parts[:cut])
            if candidate in scope:
                return candidate
        return None

    def _traverses_container(self, head: str, ref: str, scope: set[str]) -> bool:
        """True when a reference path reaches *into* a bounded construct from outside it.

        Only the container's own aggregate is addressable from outside (``map.keys``,
        ``branch.result``, ``repeat.result``). Inside a body, a sibling is addressed by its
        full site id and that is fine - the check therefore first asks whether a longer
        prefix of the path is itself an in-scope site.
        """
        parts = ref.split(".")
        for cut in range(len(parts), 1, -1):
            if ".".join(parts[:cut]) in scope:
                return False
        compiled = self.by_site.get(head)
        if compiled is None or compiled.kind not in ("map", "expand", "branch", "repeat"):
            return False
        remainder = ref.split(".", 1)[1] if "." in ref else ""
        if not remainder:
            return False
        first = remainder.split(".", 1)[0].split("[", 1)[0]
        if first in ("then", "else", "body"):
            return True
        return any(child.node.id == first for child in self.nodes if child.body_of == head)

    def _check_needs(self, node: Node, scope: set[str], path: str) -> set[str]:
        control: set[str] = set()
        for index, need in enumerate(node.needs):
            if need not in scope:
                self.error("NEED_UNKNOWN", f"{path}.needs[{index}]",
                           f"needs an unknown or not-yet-run node {need!r}")
            else:
                control.add(need)
        return control

    def _check_join_targets(self, node: Node, scope: set[str], path: str) -> set[str]:
        """Every joined site must be visible *and* have a value in this scope.

        A node inside a bounded construct settles per item and its value lives in the item's
        scope, so joining it from outside would fabricate ``None``. That is a compile error.
        """
        joined: set[str] = set()
        for index, target in enumerate(node.of):
            if target not in scope:
                self.error("JOIN_TARGET", f"{path}.of[{index}]",
                           f"joins an unknown or not-yet-run node {target!r}")
                continue
            compiled = self.by_site.get(target)
            if compiled is not None and compiled.body_of is not None:
                self.error("JOIN_TARGET", f"{path}.of[{index}]",
                           f"{target!r} lives inside a bounded construct; join its container or "
                           f"the container's own result instead")
                continue
            joined.add(target)
        return joined

    def _node_values(self, node: Node) -> Iterable[tuple[str, Any]]:
        yield "args", node.args
        yield "inputs", node.inputs
        yield "instruction", {"template": node.instruction, "values": node.inputs} if node.instruction else None
        if node.over is not None:
            yield "over", node.over
        if node.condition is not None:
            for condition_path, condition in _iter_conditions(node.condition):
                yield "condition" + condition_path, condition
        if node.when is not None:
            for condition_path, condition in _iter_conditions(node.when):
                yield "when" + condition_path, condition
        if node.kind == "verify":
            yield "checks", [{"ref": c.ref} if c.ref else None for c in node.checks]
            yield "check_schemas", [c.schema_ for c in node.checks if c.schema_ is not None]
        if node.kind == "publish":
            yield "artifacts", [{"ref": a.ref} for a in node.artifacts]

    # -- structural totals ------------------------------------------------------
    def _instances(self, node: Node, depth: int) -> int:
        """Worst-case instance count for this site and its body (upper bound)."""
        if node.kind in ("map", "expand"):
            body = sum(self._body_instances(child) for child in node.body)
            return 1 + body * max(1, node.max_items)
        if node.kind == "branch":
            biggest = max([sum(self._body_instances(c) for c in node.then),
                           sum(self._body_instances(c) for c in node.else_)], default=0)
            return 1 + biggest
        if node.kind == "repeat":
            body = sum(self._body_instances(child) for child in node.body)
            return 1 + body * max(1, node.max_iterations)
        return 1

    def _body_instances(self, node: Node) -> int:
        return self._instances(node, 0)

    def _check_outputs(self) -> None:
        for index, ref in enumerate(self.plan.outputs):
            head = _ref_head(ref)
            if head is None or head not in self.by_site:
                self.error("OUTPUT_REF", f"outputs[{index}]",
                           f"output references unknown node {ref!r}")
            elif self.by_site[head].body_of is not None:
                self.error("OUTPUT_REF", f"outputs[{index}]",
                           "outputs must name a top-level node")

    def _check_artifacts(self) -> None:
        primaries = [n.site_id for n in self.nodes
                     if n.kind == "publish" and any(a.primary for a in n.node.artifacts)]
        if len(primaries) > 1:
            self.error("ARTIFACT_PRIMARY", "nodes",
                       f"more than one publish node declares a primary artifact: {primaries}")
        total = sum(len(n.node.artifacts) for n in self.nodes if n.kind == "publish")
        if total > CEILINGS["max_artifacts"]:
            self.error("ARTIFACT_COUNT", "nodes", "too many published artifacts")

    def _check_budget(self) -> None:
        estimate = sum(child.instances for child in self.nodes if child.body_of is None)
        if estimate > self.plan.budget.max_nodes:
            self.error("BUDGET_NODES", "budget.max_nodes",
                       f"worst-case node instances ({estimate}) exceed budget.max_nodes "
                       f"({self.plan.budget.max_nodes})")


_ARTIFACT_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def _ref_head(ref: str) -> Optional[str]:
    if not ref:
        return None
    head = ref.split(".", 1)[0].split("[", 1)[0]
    return head if head.isidentifier() else None


def _iter_refs(value: Any) -> Iterable[str]:
    if value is None:
        return
    if is_ref(value):
        yield value["ref"]
        return
    if is_template(value):
        yield from _iter_refs(value.get("values") or {})
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_refs(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_refs(item)


def _iter_conditions(condition: Condition, path: str = "") -> Iterable[tuple[str, Any]]:
    """Yield ``(path, ref-or-value)`` pairs so every condition's refs are validated."""
    if condition.all:
        for index, child in enumerate(condition.all):
            yield from _iter_conditions(child, f".all[{index}]")
    if condition.any:
        for index, child in enumerate(condition.any):
            yield from _iter_conditions(child, f".any[{index}]")
    if condition.not_ is not None:
        yield from _iter_conditions(condition.not_, ".not")
    if condition.ref:
        yield path + ".ref", {"ref": condition.ref}
    if condition.requires_value() and condition.value is not None:
        yield path + ".value", condition.value
