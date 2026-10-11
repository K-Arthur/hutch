"""When a workflow is the right route - and who is allowed to decide.

Three modes, all explicit and reviewable:

``off``      the default. Hutch never proposes or starts a workflow for this Bot.
``suggest``  Hutch may *describe* a candidate route in the conversation (a plan draft with
             its bounds and the simpler alternatives), but starting one is the person's
             action.
``auto``     Hutch may start a workflow without a fresh confirmation, but only inside the
             operator's preauthorized scope: an activated saved definition, the Bot's
             configured node/model/wall allowances, and no widening of tools, skills or
             accounts. Consequential actions inside the run still use their own approval
             boundaries, and the person can stop the instance at any time.

Recommendations come from explainable rules over task *structure* - not message length,
slang, a model family or the mere presence of verbs. Every recommendation carries its
reason, its estimated bounds, and at least one simpler alternative when one exists. The
rules are deliberately small: a workflow is proposed only when a fixed sequence, a
fan-out over discovered items, or a verify/repair loop is actually the cheaper route.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

MODES = ("off", "suggest", "auto")

#: The budget keys an auto scope may cap, with the same bounds the plan schema enforces.
#: Derived from the compiler's ceilings so raising one cannot leave this validator stale.
AUTO_CAPS = ("max_nodes", "max_model_calls", "max_wall_seconds", "max_fanout")


def _cap_bounds(key: str) -> tuple[int, int]:
    from .plan import CEILINGS

    low = 0 if key == "max_model_calls" else 1
    return low, int(CEILINGS[key])


@dataclass(frozen=True)
class Recommendation:
    route: str                     # direct | saved_workflow | bounded_fanout | dynamic_branch | verify_loop | clarify
    why: str
    simpler: str = ""
    bounds: dict[str, Any] = field(default_factory=dict)
    suggested_plan_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"route": self.route, "why": self.why, "simpler": self.simpler,
                "bounds": self.bounds, "suggested_plan_name": self.suggested_plan_name}


def recommend(*, signals: dict[str, Any], saved_workflow: str = "") -> Recommendation:
    """The application's routing policy: deterministic, explainable, abstaining by default."""
    def on(name: str) -> bool:
        return bool(signals.get(name))

    if on("conversational") or on("single_step"):
        return Recommendation("direct", "this looks like one answer or one bounded tool step",
                              simpler="answer it directly")
    if on("repeatable_procedure") and saved_workflow:
        return Recommendation("saved_workflow",
                              f"a reviewed method already exists for this: {saved_workflow!r}",
                              simpler="run it directly with hutch workflow run",
                              suggested_plan_name=saved_workflow)
    if on("needs_verification") and (on("depends_on_results") or on("repeatable_procedure")):
        return Recommendation("verify_loop",
                              "the result has to hold against a check, and a failure should be repaired "
                              "within a bounded number of rounds",
                              simpler="ask for the check to be run once, without a repair loop",
                              bounds={"max_repairs": 2})
    if on("depends_on_results") and on("independent_items"):
        return Recommendation("dynamic_branch",
                              "later work depends on what earlier steps find, so the shape cannot be "
                              "fixed in advance",
                              simpler="one fan-out with a fixed list, if the items are already known",
                              bounds={"max_fanout": 20})
    if on("independent_items") and on("known_inputs"):
        return Recommendation("bounded_fanout",
                              "several independent items can be processed in one bounded fan-out and joined",
                              simpler="a handful of direct tool calls, if there are only a few items",
                              bounds={"max_fanout": 20})
    workflow_shaped = any(on(name) for name in
                          ("independent_items", "needs_verification", "repeatable_procedure",
                           "depends_on_results"))
    if workflow_shaped and not on("known_inputs"):
        return Recommendation("clarify",
                              "the inputs or the acceptance criterion are not established yet; a plan "
                              "built now would be guesswork",
                              simpler="answer the open question first, or prepare a draft")
    return Recommendation("direct", "no workflow shape is clearly cheaper than doing this directly",
                          simpler="do it directly")


def auto_scope(bot: Any) -> dict[str, Any]:
    """The operator's preauthorized auto scope, read from the Bot's own settings."""
    scope = getattr(bot, "workflow_limits", None)
    return dict(scope) if isinstance(scope, dict) else {}


def check_auto(*, bot: Any, definition: Optional[dict[str, Any]], budget: dict[str, Any],
               plan_name: str = "") -> tuple[bool, str]:
    """Whether ``auto`` may start this plan without a fresh confirmation, and why."""
    mode = getattr(bot, "workflow_mode", "off")
    if mode != "auto":
        return False, f"this Bot's workflow mode is {mode!r}, so nothing is started automatically"
    scope = auto_scope(bot)
    allowed_names = scope.get("definitions")
    if allowed_names is not None:
        if not isinstance(allowed_names, list) or not all(isinstance(name, str) for name in allowed_names):
            return False, "the Bot's auto scope is malformed; fix it in Bot settings"
        if plan_name and plan_name not in allowed_names:
            return False, f"{plan_name!r} is not in this Bot's preauthorized definitions"
    if definition is not None and not definition.get("active"):
        return False, "that saved workflow is not activated, so auto may not start it"
    for key in AUTO_CAPS:
        low, high = _cap_bounds(key)
        limit = scope.get(key)
        if limit is None:
            continue
        if not isinstance(limit, int) or isinstance(limit, bool) or not low <= limit <= high:
            return False, f"the Bot's auto scope has an invalid {key}"
        if int(budget.get(key, 0) or 0) > limit:
            return False, (f"this plan asks for {key}={budget.get(key)} which exceeds the Bot's "
                           f"preauthorized {key}={limit}")
    return True, "within this Bot's preauthorized workflow scope"


def explain_block(bot: Any, verdicts: list[dict[str, Any]]) -> list[str]:
    """Precise options for a blocked role, in the words the UI can show as-is."""
    lines: list[str] = []
    for verdict in verdicts:
        if verdict.get("allowed"):
            continue
        spec = (verdict.get("route") or {}).get("spec") or "this route"
        lines.append(f"{verdict['role']} on {spec} is blocked: {'; '.join(verdict.get('reasons') or [])}. "
                     "Options: choose an installed qualified route for this Bot, run a compatible saved "
                     "plan instead, restrict the node to a bounded worker role, or finish the safe direct work.")
    return lines
