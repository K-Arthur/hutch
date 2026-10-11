"""The declarative plan schema for dynamic workflows.

A plan is data, never code. It is authored (by a qualified model, an imported file, or
the operator), validated by :mod:`hutch.workflow.compile`, and then executed by the
deterministic interpreter. Every field here is intentionally small, strict and
serializable so a plan can be diffed, reviewed, saved and replayed.

Strictness rules that matter:

* ``extra="forbid"`` everywhere - a typo is an error, never a silently ignored intent.
* A node carries every per-kind field, and ``_check_kind`` rejects a field that does not
  belong to its kind, so a mis-specified node cannot quietly degenerate into a no-op.
* Nothing here coerces a missing argument into a successful default. Required fields are
  required per kind; optional fields mean what their documentation says.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1
MAX_STRING = 20_000
MAX_INSTRUCTION = 8_000
MAX_QUESTION = 2_000

#: Hard operator ceilings. A plan may ask for less; never more. These are not
#: "recommended sizes" - they bound what one workflow can do regardless of author.
CEILINGS = {
    "max_nodes": 2_000,
    "max_model_calls": 500,
    "max_tokens": 1_000_000,
    "max_wall_seconds": 86_400,
    "max_fanout": 100,
    "max_repairs": 5,
    "max_parallel_steps": 4,
    "max_iterations": 20,
    "max_nesting_depth": 3,
    "max_inputs": 32,
    "max_artifacts": 32,
    "max_instruction_chars": MAX_INSTRUCTION,
    "max_input_chars": 200_000,
    "max_agent_steps": 40,
    "max_question_wait_seconds": 604_800,
    "max_command_seconds": 1_800,
    "max_plan_bytes": 512 * 1024,
}

NodeKind = Literal["transform", "tool", "agent", "map", "branch", "repeat", "join",
                   "verify", "ask", "publish", "expand"]
JoinPolicy = Literal["all_required", "all_settled", "first_success"]
FailAction = Literal["stop", "repair", "continue"]
CheckKind = Literal["schema", "artifact", "command", "human", "agent_review"]
ModelBinding = str  # "$bot", "$default", or a concrete route spec validated by qualify

_ID_RE = r"^[a-z][a-z0-9_]{0,63}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Ref(_Strict):
    """A reference into the run's value scope: ``input.<name>``, a node id, or a path.

    Examples: ``{"ref": "collect"}`` (a whole node result), ``{"ref": "collect.files"}``,
    ``{"ref": "scan.items[0].path"}``, ``{"ref": "input.topic"}``.
    Inside a bounded construct, ``item`` and ``index`` are also in scope.
    """

    ref: str = Field(min_length=1, max_length=400)


class Template(_Strict):
    """Bounded text substitution: ``{{ name }}`` replaced from ``values``.

    Values are themselves :data:`Value` objects, so a template may embed any resolved
    reference. Substitution is textual and non-recursive; a rendered result is never
    re-parsed as a template.
    """

    template: str = Field(max_length=MAX_STRING)
    values: dict[str, Any] = Field(default_factory=dict)


class Condition(_Strict):
    """A bounded boolean expression over resolved values.

    Exactly one form is required: ``all``, ``any``, ``not``, or a comparison
    (``ref`` plus ``op``). Comparisons never call Python: the evaluator in
    :mod:`hutch.workflow.expr` interprets them directly.
    """

    all: list["Condition"] = Field(default_factory=list)
    any: list["Condition"] = Field(default_factory=list)
    not_: Optional["Condition"] = Field(default=None, alias="not")
    ref: str = Field(default="", max_length=400)
    op: Literal["", "eq", "ne", "gt", "ge", "lt", "le", "in", "not_in", "contains",
                "matches", "exists", "is_null", "is_empty", "not_empty"] = ""
    value: Any = None

    @model_validator(mode="after")
    def _one_form(self) -> "Condition":
        forms = [bool(self.all), bool(self.any), self.not_ is not None, bool(self.ref)]
        if sum(forms) != 1:
            raise ValueError("a condition must have exactly one of: all, any, not, ref")
        if self.ref and not self.op:
            raise ValueError("a comparison condition needs an op")
        if self.op and not self.ref:
            raise ValueError("an op needs a ref")
        for child in [*self.all, *self.any, *( [self.not_] if self.not_ else [] )]:
            if child is None:
                raise ValueError("empty condition branch")
        return self

    def requires_value(self) -> bool:
        return self.op not in ("exists", "is_null", "is_empty", "not_empty")


class Check(_Strict):
    """One verification criterion with independently observable evidence.

    Only ``schema``, ``artifact``, ``command`` and ``human`` can establish a verified
    outcome. ``agent_review`` is advisory by construction: it may fail or escalate a
    result, never certify it (a second model reading the first model's summary is not
    independent evidence).
    """

    kind: CheckKind
    description: str = Field(default="", max_length=400)

    #: The value under test. ``schema`` checks validate it against ``schema``;
    #: ``artifact`` checks re-read the published artifact it names; ``agent_review``
    #: passes it to the advisory reviewer.
    ref: str = Field(default="", max_length=400)
    schema_: Optional[dict[str, Any]] = Field(default=None, alias="schema")

    # artifact: re-read the recorded bytes and confirm identity/size
    expect_sha256: str = Field(default="", max_length=64)
    min_bytes: Optional[int] = Field(default=None, ge=0)
    max_bytes: Optional[int] = Field(default=None, ge=0)

    # command: a fixed argv, never a shell string
    argv: list[str] = Field(default_factory=list)
    expect_exit: int = 0
    timeout_seconds: int = Field(default=300, ge=1, le=CEILINGS["max_command_seconds"])
    cwd: str = ""

    # human: one durable question bound to its own id
    prompt: str = Field(default="", max_length=MAX_QUESTION)

    # agent_review: an advisory verifier step
    instruction: str = Field(default="", max_length=MAX_INSTRUCTION)
    model: ModelBinding = "$bot"

    @model_validator(mode="after")
    def _per_kind(self) -> "Check":
        if self.kind == "schema" and (self.schema_ is None):
            raise ValueError("a schema check needs a schema")
        if self.kind == "artifact" and not self.ref:
            raise ValueError("an artifact check needs a ref to a published artifact")
        if self.kind == "command" and not self.argv:
            raise ValueError("a command check needs argv")
        if self.kind == "human" and not self.prompt:
            raise ValueError("a human check needs a prompt")
        if self.kind == "agent_review" and not self.instruction:
            raise ValueError("an agent_review check needs an instruction")
        return self


class FailPolicy(_Strict):
    """What happens when verification fails. ``repair`` is bounded and explicit."""

    action: FailAction = "stop"
    rounds: int = Field(default=0, ge=0, le=CEILINGS["max_repairs"])
    instruction: str = Field(default="", max_length=MAX_INSTRUCTION)
    #: A prior node whose full value is replaced by the repair's validated JSON output.
    #: Omitted only for compatibility when checks identify exactly one prior node.
    adopt: str = Field(default="", max_length=200)
    mark_unverified: bool = True

    @model_validator(mode="after")
    def _repair_needs_rounds(self) -> "FailPolicy":
        if self.action == "repair" and self.rounds < 1:
            raise ValueError("a repair policy needs at least one round")
        if self.action != "repair" and self.adopt:
            raise ValueError("an adoption target is only valid with the repair policy")
        return self


class ArtifactSpec(_Strict):
    name: str = Field(min_length=1, max_length=120)
    ref: str = Field(min_length=1, max_length=400)
    media_type: str = Field(default="text/plain", max_length=120)
    primary: bool = False


class Envelope(_Strict):
    """What the workflow may touch. Never widens the Bot's own authority."""

    tools: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    max_parallel_steps: int = Field(default=2, ge=1, le=CEILINGS["max_parallel_steps"])
    network: Literal["inherit", "local_model_only"] = "inherit"


class Budget(_Strict):
    """Root-level allowances. Children and retries can never reset them."""

    max_nodes: int = Field(default=40, ge=1, le=CEILINGS["max_nodes"])
    max_model_calls: int = Field(default=12, ge=0, le=CEILINGS["max_model_calls"])
    max_tokens: int = Field(default=64_000, ge=0, le=CEILINGS["max_tokens"])
    max_wall_seconds: int = Field(default=900, ge=5, le=CEILINGS["max_wall_seconds"])
    max_fanout: int = Field(default=8, ge=1, le=CEILINGS["max_fanout"])
    max_repairs: int = Field(default=2, ge=0, le=CEILINGS["max_repairs"])


class InputSpec(_Strict):
    type: Literal["string", "number", "integer", "boolean", "array", "object"] = "string"
    required: bool = True
    default: Any = None
    description: str = Field(default="", max_length=400)
    max_length: Optional[int] = Field(default=None, ge=1, le=CEILINGS["max_input_chars"])
    max_items: Optional[int] = Field(default=None, ge=0, le=CEILINGS["max_fanout"])


class Node(_Strict):
    """One planned step. A single strict model with per-kind rules.

    ``id`` is the stable site identity within its enclosing scope; ``instance_key`` is
    derived at run time (``item:<key>`` inside a bounded construct, ``once`` otherwise), so a
    repeated call site is never confused with one invocation.
    """

    kind: NodeKind
    id: str = Field(pattern=_ID_RE)
    title: str = Field(default="", max_length=200)
    needs: list[str] = Field(default_factory=list)
    when: Optional[Condition] = None

    # transform
    op: str = Field(default="", max_length=40)
    args: dict[str, Any] = Field(default_factory=dict)

    # tool
    tool: str = Field(default="", max_length=80)
    purpose: str = Field(default="", max_length=400)

    # agent / agent_review
    #: Authoring is a *submission-time* gate, never a node role: a node is bounded work
    #: performed by a worker, or a review performed by a verifier.
    role: Literal["worker", "verifier"] = "worker"
    instruction: str = Field(default="", max_length=CEILINGS["max_instruction_chars"])
    inputs: dict[str, Any] = Field(default_factory=dict)
    output_schema: Optional[dict[str, Any]] = None
    model: ModelBinding = "$bot"
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    max_steps: Optional[int] = Field(default=None, ge=1, le=CEILINGS["max_agent_steps"])

    # map / expand (bounded expansion region)
    over: Optional[Any] = None
    item_key: str = Field(default="", max_length=200)
    concurrency: int = Field(default=1, ge=1, le=CEILINGS["max_parallel_steps"])
    max_items: int = Field(default=20, ge=1, le=CEILINGS["max_fanout"])
    #: What one failed item does to the whole fan-out. ``skip`` keeps the run honest by
    #: reporting the item as skipped and the aggregate as incomplete; ``fail`` stops.
    on_item_failure: Literal["fail", "skip"] = "fail"
    body: list["Node"] = Field(default_factory=list)
    allow_tools: list[str] = Field(default_factory=list)
    allow_models: list[str] = Field(default_factory=list)

    # branch
    condition: Optional[Condition] = None
    then: list["Node"] = Field(default_factory=list)
    else_: list["Node"] = Field(default_factory=list, alias="else")

    # repeat
    until: Optional[Condition] = None
    max_iterations: int = Field(default=5, ge=1, le=CEILINGS["max_iterations"])

    # join
    of: list[str] = Field(default_factory=list)
    policy: JoinPolicy = "all_required"
    require: Optional[int] = Field(default=None, ge=1)

    # verify
    checks: list[Check] = Field(default_factory=list)
    on_fail: FailPolicy = Field(default_factory=FailPolicy)

    # ask
    question: str = Field(default="", max_length=MAX_QUESTION)
    options: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=86_400, ge=1,
                                 le=CEILINGS["max_question_wait_seconds"])

    # publish
    artifacts: list[ArtifactSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_kind(self) -> "Node":
        def reject(field: str, value: Any) -> None:
            if value:
                raise ValueError(f"a {self.kind!r} node must not set {field!r}")

        if self.kind == "transform":
            if not self.op:
                raise ValueError("a transform node needs an op")
            reject("instruction", self.instruction)
            reject("body", self.body)
        elif self.kind == "tool":
            if not self.tool:
                raise ValueError("a tool node needs a tool name")
            reject("body", self.body)
            reject("instruction", self.instruction)
        elif self.kind == "agent":
            if not self.instruction:
                raise ValueError("an agent node needs an instruction")
            reject("body", self.body)
            reject("checks", self.checks)
        elif self.kind in ("map", "expand"):
            if self.over is None:
                raise ValueError("a map node needs 'over'")
            if not self.body:
                raise ValueError("a map node needs a body")
            reject("instruction", self.instruction)
        elif self.kind == "branch":
            if self.condition is None:
                raise ValueError("a branch node needs a condition")
            if not self.then and not self.else_:
                raise ValueError("a branch node needs a then or else body")
            reject("instruction", self.instruction)
        elif self.kind == "repeat":
            if self.until is None:
                raise ValueError("a repeat node needs an 'until' condition")
            if not self.body:
                raise ValueError("a repeat node needs a body")
        elif self.kind == "join":
            if not self.of:
                raise ValueError("a join node needs 'of'")
            reject("body", self.body)
            reject("instruction", self.instruction)
        elif self.kind == "verify":
            if not self.checks:
                raise ValueError("a verify node needs at least one check")
            reject("body", self.body)
            reject("instruction", self.instruction)
        elif self.kind == "ask":
            if not self.question:
                raise ValueError("an ask node needs a question")
        elif self.kind == "publish":
            if not self.artifacts:
                raise ValueError("a publish node needs artifacts")
            reject("body", self.body)
        return self

    def child_bodies(self) -> list[tuple[str, list["Node"]]]:
        """Named bodies this node owns, for scoped walking and id assignment."""
        out: list[tuple[str, list["Node"]]] = []
        if self.body:
            out.append(("body", self.body))
        if self.then:
            out.append(("then", self.then))
        if self.else_:
            out.append(("else", self.else_))
        return out


Node.model_rebuild()
Condition.model_rebuild()


class Plan(_Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    description: str = Field(default="", max_length=1_000)
    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    envelope: Envelope = Field(default_factory=Envelope)
    budget: Budget = Field(default_factory=Budget)
    nodes: list[Node] = Field(min_length=1)
    outputs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _budget_parallelism(self) -> "Plan":
        if len(self.inputs) > CEILINGS["max_inputs"]:
            raise ValueError("too many declared inputs")
        return self
