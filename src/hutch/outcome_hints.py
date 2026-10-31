"""Plain guidance for a run that ended because nothing owned it any more (an interruption).

An interrupted run is not a model or tool failure: the process running it stopped under it (a restart, a crash,
a shutdown, or a row left by an earlier version). The generic "open the transcript for the failing step" advice
sends a person looking for a fault that is not there, so the cause and the fix are stated on their own.
"""

from __future__ import annotations

from .models import Run, RunStatus


def interrupted_hint(run: Run) -> tuple[str, str]:
    """(cause, fix) for a run whose process stopped under it."""
    cause = "This job was cut short because the process running it stopped (a restart, a crash or a shutdown)."
    if run.status is RunStatus.outcome_unknown:
        return (cause + " An action was in flight, so it may or may not have happened.",
                "Check the result of that action yourself before asking again; the transcript shows the last step.")
    return cause, "Nothing was lost beyond this run. Send the request again if you still need it; the transcript shows how far it got."
