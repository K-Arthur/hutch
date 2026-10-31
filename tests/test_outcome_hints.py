"""An interrupted run says it was cut short, not that a step failed."""

from __future__ import annotations

import pytest

from hutch.models import Bot, Run, RunStatus
from hutch.views import explain_outcome


def _run(status, reason, error="the process running this job (4242) exited before it finished"):
    return Run(bot_id="b", prompt="Draft the release notes", status=status, exit_reason=reason, error=error)


def test_an_interrupted_run_is_explained_as_cut_short_with_an_honest_next_step():
    wait = explain_outcome(_run(RunStatus.failed, "interrupted"), Bot(name="scribe", tools=[]))
    assert "cut short" in wait.cause and "process running it stopped" in wait.cause
    assert "Send the request again" in wait.fix and "Nothing was lost beyond this run" in wait.fix
    assert "failing step" not in wait.fix and wait.kind == "error"


def test_an_interruption_with_an_action_in_flight_warns_it_may_have_happened():
    wait = explain_outcome(_run(RunStatus.outcome_unknown, "interrupted", "an action was in flight"), None)
    assert "may or may not have happened" in wait.cause and "Check the result of that action yourself" in wait.fix
    assert "Send the request again" not in wait.fix, "asking again could repeat a side effect"


@pytest.mark.parametrize("reason,error,expected", [
    ("error", "model blew up", "Open the transcript for the failing step."),
    ("timeout", "", "Raise timeout_seconds"),
])
def test_other_failures_keep_their_own_guidance(reason, error, expected):
    wait = explain_outcome(_run(RunStatus.failed, reason, error), Bot(name="x", tools=[]))
    assert expected in wait.fix
