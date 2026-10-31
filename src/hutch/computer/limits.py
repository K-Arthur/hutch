"""How much work one run may spend driving a computer, and when it is visibly stuck.

The two failures reported most often for computer-use agents are not bad grounding: they are agents that keep acting after
they have stopped making progress, and runs whose cost nobody bounded. Both are harness problems, so both are handled here:

* **A hard cap on actions per run.** Every observation and every stateful action spends one unit. At the cap the tool
  refuses instead of looping, and says what to report. This is deliberately generous: it exists to stop a runaway, not to
  ration ordinary work.
* **No-progress detection.** After a stateful action the tool knows whether the screen changed. Three in a row that changed
  nothing, with the same frame fingerprint, means the agent is repeating an action that does not work. Further stateful
  actions are refused until something changes, with the evidence quoted back.

Neither rule guesses at intent, and neither can end a run: they refuse one call and hand the decision back to the model and
the person. A refusal is a `not_dispatched` outcome, so nothing is half-done.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Observations plus stateful actions in one run. A long legitimate session uses tens, not hundreds.
MAX_RUN_ACTIONS = 200
#: Consecutive stateful actions that leave the screen byte-identical before further actions are refused.
STALL_LIMIT = 3
#: Refusals quote at most this much of the caller's context back.
_SHORT = 120


@dataclass(frozen=True)
class Refusal:
    reason: str
    kind: str          # "budget" | "stalled"
    action: int
    limit: int

    def message(self) -> str:
        if self.kind == "stalled":
            return (f"{self.reason}. Nothing further will be dispatched: report what you can see and stop, or try a "
                    f"different element or action")
        return (f"{self.reason}. Nothing was dispatched. Stop this task and report what you completed: {self.action} of "
                f"{self.limit} computer actions were used")


class ActionBudget:
    """Per-run action accounting with a no-progress detector. One instance per computer session."""

    def __init__(self, *, max_actions: int = MAX_RUN_ACTIONS, stall_limit: int = STALL_LIMIT):
        self.max_actions = max(1, int(max_actions))
        self.stall_limit = max(1, int(stall_limit))
        self.actions = 0
        self.refusals = 0
        self._fingerprint = ""
        self._unchanged = 0
        self._stalled = False

    # ------------------------------------------------------------- spending

    def spend(self, action: str, *, stateful: bool) -> Refusal | None:
        """Account for one call before it is dispatched. Returns a refusal when it may not run."""
        if self.actions >= self.max_actions:
            self.refusals += 1
            return Refusal(f"this run has used its whole computer action budget ({self.max_actions})",
                           "budget", self.actions, self.max_actions)
        if stateful and self._stalled:
            self.refusals += 1
            return Refusal(f"the last {self._unchanged} {action} actions changed nothing on screen",
                           "stalled", self.actions, self.max_actions)
        self.actions += 1
        return None

    # ------------------------------------------------------------ progress

    def note(self, *, stateful: bool, changed: bool, fingerprint: str, verified: bool = False) -> None:
        """Record what a dispatched action did, so the next one can be judged against it."""
        if not stateful:
            return
        if verified or changed:
            self._unchanged = 0
            self._stalled = False
            self._fingerprint = fingerprint or self._fingerprint
            return
        if fingerprint and fingerprint == self._fingerprint:
            self._unchanged += 1
        else:
            self._unchanged = 1 if fingerprint else self._unchanged
            self._fingerprint = fingerprint or self._fingerprint
        self._stalled = self._unchanged >= self.stall_limit

    def state(self) -> dict:
        """What the run panel and the refusal record can show."""
        return {"actions": self.actions, "limit": self.max_actions, "unchanged_actions": self._unchanged,
                "stalled": self._stalled, "refusals": self.refusals}


def fingerprint_of(data: dict) -> str:
    """The screen an action left behind, or "" when the action returned no observation."""
    observation = data.get("observation") if isinstance(data, dict) else None
    if isinstance(observation, dict):
        image = observation.get("image")
        if isinstance(image, dict) and isinstance(image.get("sha256"), str):
            return image["sha256"][:_SHORT]
    return ""
