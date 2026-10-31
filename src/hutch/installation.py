"""Installation review: state this Hutch holds that the person has not reviewed yet.

Computed on read from the existing store (nothing rewritten, nothing deleted). The review exists because a
real installation can carry assistants, runs and live rows from earlier demo-era versions: the app must say
so and offer the real actions instead of silently looking normal. A review marker records that the person
saw the current set, so a new issue appears once; already-acknowledged issues stay visible in the roster with
their truthful status but stop nagging.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .models import iso, utcnow
from .route_problem import route_problem, run_is_legacy

MARKER_KEY = "installation:review:v1"
STATE_VERSION = 1


def _marker(store) -> dict[str, Any]:
    raw = store.kv_get(MARKER_KEY)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _bot_issue(bot) -> Optional[dict[str, Any]]:
    problem = route_problem(bot)
    if not problem:
        return None
    return {"kind": "assistant", "key": f"assistant:{bot.id}", "bot": bot.name,
            "display_name": bot.display_name or bot.name, "model": bot.model,
            "runtime": bot.runtime.value, "reason": problem,
            "fix": "Choose a model route in this assistant's settings, or remove the assistant.",
            "href": f"#/bot/{bot.name}", "remove_href": f"/bots/{bot.name}/delete"}


def installation_issues(store) -> list[dict[str, Any]]:
    """The bounded, real issues that make this installation need a review. Read-only."""
    bots = store.list_bots()
    issues = [issue for issue in (_bot_issue(bot) for bot in bots) if issue]
    legacy = sum(1 for bot in bots
                 if (run := store.latest_finished_run(bot.id)) is not None and run_is_legacy(run, bot))
    if legacy:
        issues.append({"kind": "legacy_runs", "key": "legacy-runs", "count": legacy,
                       "reason": f"{legacy} failed run(s) were recorded by the removed demo runtime.",
                       "fix": "They are history, kept in Activity with a Legacy badge. Nothing to do unless you want to remove the assistant.",
                       "href": "#/activity/history"})
    ghosts = len(store.expired_runs()) + len(store.legacy_live_runs())
    if ghosts:
        issues.append({"kind": "ghost_runs", "key": "ghost-runs", "count": ghosts,
                       "reason": f"{ghosts} run(s) were left in a live state by an earlier version.",
                       "fix": "Hutch marks them stopped or interrupted on the next supervisor beat; Stop all does not clear them.",
                       "href": "#/activity"})
    if bots and store.workspace_coordinator_id() is None:
        issues.append({"kind": "no_main_assistant", "key": "no-main-assistant",
                       "reason": "No main assistant is set, so the app has no default conversation.",
                       "fix": "Open an assistant's menu in the sidebar (the three dots) and choose Make main assistant.",
                       "href": "#/chat"})
    return issues


def installation_state(store) -> dict[str, Any]:
    issues = installation_issues(store)
    marker = _marker(store)
    acknowledged = set(marker.get("acknowledged") or [])
    open_issues = [issue for issue in issues if issue["key"] not in acknowledged]
    bots = store.list_bots()
    if not bots and not issues:
        state = "fresh"                     # existing first-run onboarding owns this case
    elif open_issues:
        state = "needs_review"
    else:
        state = "ready"
    return {"version": STATE_VERSION, "state": state, "review_required": bool(open_issues),
            "issues": issues, "open_issues": open_issues, "assistant_count": len(bots),
            "reviewed_at": marker.get("reviewed_at"), "reviewed_count": len(acknowledged)}


def record_review(store) -> dict[str, Any]:
    """Acknowledge the current issue set. No assistant, run or file is created, changed or deleted."""
    issues = installation_issues(store)
    marker = {"version": STATE_VERSION, "reviewed_at": iso(utcnow()),
              "acknowledged": sorted(issue["key"] for issue in issues)}
    store.kv_set(MARKER_KEY, json.dumps(marker, sort_keys=True))
    return installation_state(store)
