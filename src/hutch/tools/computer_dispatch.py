"""The ``computer`` tool's action table, and its action accounting.

Split from ``computer.py`` so the execution path there reads as policy (authority, budget, thread affinity, dispatch) and
this module is the plain routing of one validated action to one session method. Nothing here decides whether an action may
run: the tool has already checked authority, the control lease and the action budget by the time these run.

Keeping the table out of the tool also keeps the file inside the repository's size budget, which is the same reason the
contract lives in ``computer_contract.py``.
"""

from __future__ import annotations

import time
from typing import Any

from ..computer.desktop import DesktopSession
from ..computer.limits import ActionBudget, fingerprint_of
from .base import ToolContext, ToolResult
from .computer_contract import STATEFUL


def dispatch(tool: Any, action: str, args: dict[str, Any], ctx: ToolContext,
             session: DesktopSession) -> ToolResult:
    """Route one validated action. ``tool`` supplies launch and result wrapping."""
    if action == "launch":
        return tool._launch(args, ctx, session)
    if action == "elements":
        return _result(session.elements(root=str(args.get("root") or "")))
    if action == "activate":
        return _result(session.activate(str(args.get("snapshot_id") or ""), str(args.get("element_id") or "")))
    if action == "set_text":
        return _result(session.set_element_text(str(args.get("snapshot_id") or ""), str(args.get("element_id") or ""),
                                                args.get("text") or ""))
    if action == "observe":
        return _result(session.observe())
    if action == "wait":
        time.sleep(min(max(float(args.get("seconds") or 1), 0.0), 10.0))
        return _result(session.observe())
    frame_id = str(args.get("frame_id") or "")
    if action == "click":
        return _result(session.click(frame_id, args.get("x"), args.get("y"),
                                     button=str(args.get("button") or "left"),
                                     count=int(args.get("count") or 1)))
    if action == "type":
        return _result(session.type_text(frame_id, args.get("text") or ""))
    if action == "key":
        return _result(session.key(frame_id, str(args.get("keys") or "")))
    return ToolResult(False, f"unhandled action {action}")  # pragma: no cover


def account(budget: ActionBudget, action: str, result: ToolResult) -> ToolResult:
    """Tell the budget what the action did, so the next call can be judged against it."""
    data = result.data if isinstance(result.data, dict) else {}
    budget.note(stateful=action in STATEFUL, changed=bool(data.get("visual_change")),
                fingerprint=fingerprint_of(data),
                verified=str(data.get("outcome") or "") == "effect_verified")
    data["limits"] = budget.state()
    return result


def _result(res) -> ToolResult:
    return ToolResult(res.ok, res.output, dict(res.data))
