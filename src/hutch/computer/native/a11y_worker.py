"""Out-of-process AT-SPI worker: read and act on a private session's accessibility tree.

Runs under an interpreter that has PyGObject and the Atspi typelib (``HUTCH_GI_PYTHON``, ``/usr/bin/python3``), exactly like
``eis_worker.py``, because Hutch's own environment has no GTK bindings. One JSON object per stdin line in, one per stdout
line out; the parent (``computer/accessibility.py``) owns deadlines, policy and reporting.

The worker is trusted-but-narrow:
* it talks only to the accessibility bus named by ``AT_SPI_BUS_ADDRESS``, which the session owns; it never discovers the
  personal desktop's bus;
* it never returns bytes it did not bound: node count, depth and every string are capped in ``a11y_read``;
* password and protected text is never returned, only ``redacted: true``;
* node ids are valid only for the snapshot that issued them, so a stale id cannot act on a tree that has moved on;
* a request that raises answers with an error string and keeps serving; it never crashes the session.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Optional

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

try:  # package import (tests, type checkers)
    from . import a11y_read
except ImportError:  # pragma: no cover - the worker is also executed directly as a script
    import a11y_read  # type: ignore[no-redef]

MAX_NODES = 400
DEFAULT_NODES = 240
MAX_DEPTH = a11y_read.MAX_NODE_DEPTH
MAX_NAME = a11y_read.MAX_NAME
MAX_TOTAL_TEXT = 6000
MAX_TEXT_INPUT = 2000
MAX_APPS = 64
MAX_CHILDREN = 60





class Snapshot:
    """One bounded view of an application's tree, with ids valid only until the next snapshot."""

    def __init__(self, app: Any):
        self.app = app
        self.nodes: dict[str, tuple[dict[str, Any], Any]] = {}
        self.count = 0
        self.text_budget = MAX_TOTAL_TEXT
        self.truncated = False
        self.pruned = 0

    def add(self, node: Any, depth: int, parent: str = "") -> None:
        self.count += 1
        node_id = f"n{self.count}"
        role = a11y_read.safe(node.get_role_name, "unknown")
        name = a11y_read.text(a11y_read.safe(node.get_name, ""), MAX_NAME)
        record: dict[str, Any] = {"id": node_id, "role": role, "depth": depth}
        if name:
            record["name"] = name
        if parent:
            record["parent"] = parent
        description = a11y_read.text(a11y_read.safe(node.get_description, ""), a11y_read.MAX_DESCRIPTION)
        if description:
            record["description"] = description
        actions = a11y_read.action_names(node)
        if actions:
            record["actions"] = actions
        if a11y_read.is_secret(node, role, name):
            record["redacted"] = True
        else:
            body = a11y_read.node_text(node, self.text_budget)
            if body:
                record["text"] = body
                self.text_budget -= len(body)
        located = a11y_read.bounds(node)
        if located is not None:
            record["bounds"] = located
        state = a11y_read.states(node)
        if state:
            record["state"] = state
        self.nodes[node_id] = (record, node)
    def public(self) -> list[dict[str, Any]]:
        return [record for record, _ in self.nodes.values()]


# ------------------------------------------------------------------ picking


def _apps() -> list[Any]:
    desktop = Atspi.get_desktop(0)
    found = []
    for index in range(min(desktop.get_child_count(), MAX_APPS)):
        try:
            app = desktop.get_child_at_index(index)
        except Exception:
            continue
        if app is not None:
            found.append(app)
    return found


def _frames(app: Any) -> list[Any]:
    found = []
    for index in range(min(app.get_child_count(), 32)):
        try:
            child = app.get_child_at_index(index)
        except Exception:
            continue
        if child is not None and a11y_read.safe(child.get_role_name, "") == "frame":
            found.append(child)
    return found


def _active_app() -> tuple[Any, str]:
    """The application a person would call foreground: an active frame, else the last app with a frame."""
    candidates: list[tuple[bool, Any, str]] = []
    for app in _apps():
        for frame in _frames(app):
            active = False
            try:
                state_set = Atspi.Accessible.get_state_set(frame)
                active = bool(state_set.contains(Atspi.StateType.ACTIVE))
                if not active:
                    active = bool(state_set.contains(Atspi.StateType.FOCUSED))
            except Exception:
                active = False
            candidates.append((active, app, a11y_read.text(a11y_read.safe(frame.get_name, ""), MAX_NAME)))
    if not candidates:
        raise LookupError("no application window is present in the accessibility tree")
    for active, app, title in candidates:
        if active:
            return app, title
    return candidates[-1][1], candidates[-1][2]


# ------------------------------------------------------------------ reading


def _is_showing(node: Any) -> Optional[bool]:
    """Whether the toolkit reports this node as mapped, or ``None`` when it does not answer.

    Tri-state on purpose: a toolkit that raises cannot be treated as "hidden", or the whole tree would vanish.
    """
    try:
        state_set = Atspi.Accessible.get_state_set(node)
        return bool(state_set.contains(Atspi.StateType.SHOWING))
    except Exception:
        return None


def _walk(snapshot: Snapshot, node: Any, depth: int, parent: str, max_nodes: int) -> None:
    if snapshot.count >= max_nodes:
        snapshot.truncated = True
        return
    snapshot.add(node, depth, parent)
    node_id = f"n{snapshot.count}"
    if depth >= MAX_DEPTH:
        try:
            if node.get_child_count() > 0:
                snapshot.truncated = True
        except Exception:
            pass
        return
    try:
        total = min(node.get_child_count(), MAX_CHILDREN)
    except Exception:
        return
    for index in range(total):
        if snapshot.count >= max_nodes:
            snapshot.truncated = True
            return
        try:
            child = node.get_child_at_index(index)
        except Exception:
            continue
        if child is None:
            continue
        if _collapsed(child):
            snapshot.pruned += 1
            continue
        _walk(snapshot, child, depth + 1, node_id, max_nodes)


def _walk_unpruned(snapshot: Snapshot, node: Any, depth: int, parent: str, max_nodes: int) -> None:
    """The same walk with pruning disabled, for toolkits that report no visibility state."""
    if snapshot.count >= max_nodes:
        snapshot.truncated = True
        return
    snapshot.add(node, depth, parent)
    node_id = f"n{snapshot.count}"
    if depth >= MAX_DEPTH:
        return
    try:
        total = min(node.get_child_count(), MAX_CHILDREN)
    except Exception:
        return
    for index in range(total):
        if snapshot.count >= max_nodes:
            snapshot.truncated = True
            return
        try:
            child = node.get_child_at_index(index)
        except Exception:
            continue
        if child is not None:
            _walk_unpruned(snapshot, child, depth + 1, node_id, max_nodes)


def _collapsed(node: Any) -> bool:
    """A menu that exists but is not on screen, and its contents.

    Every KDE/Qt application builds its complete menu hierarchy up front, so an unpruned read is dominated by hundreds
    of menu items for menus nobody opened: in KWrite that is 382 of 668 nodes. Removing them is not a guess about what
    matters. It only drops a ``popup menu`` the toolkit itself reports as not showing, which cannot be clicked until it
    opens, and the tree says it was pruned so nobody is misled about what exists.
    """
    try:
        if a11y_read.safe(node.get_role_name, "") != "popup menu":
            return False
    except Exception:
        return False
    return _is_showing(node) is False


def _descendants(snapshot: Snapshot, root_id: str) -> list[str]:
    """Ids of a subtree, in traversal order, from an existing snapshot (no accessibility calls)."""
    children: dict[str, list[str]] = {}
    for node_id, (record, _node) in snapshot.nodes.items():
        parent = record.get("parent") or ""
        if parent:
            children.setdefault(parent, []).append(node_id)
    ordered: list[str] = []
    stack = [root_id]
    while stack:
        node_id = stack.pop()
        ordered.append(node_id)
        stack.extend(reversed(children.get(node_id, [])))
    return ordered


class Service:
    def __init__(self) -> None:
        self.current: Optional[Snapshot] = None
        self.started = time.monotonic()

    def snapshot(self, request: dict[str, Any]) -> dict[str, Any]:
        max_nodes = max(1, min(int(request.get("max_nodes") or DEFAULT_NODES), MAX_NODES))
        root_id = str(request.get("root") or "")
        if root_id:
            # A subtree read narrows the CURRENT snapshot: the caller's ids keep their meaning.
            current = self.current
            if current is None:
                raise LookupError("there is no current snapshot; read the tree without a root element first")
            if root_id not in current.nodes:
                raise LookupError(f"element {root_id} is not in the current snapshot; read the tree again")
            keep = _descendants(current, root_id)
            kept = set(keep[:max_nodes])
            base = int(current.nodes[root_id][0]["depth"])
            nodes = [{**record, "depth": max(0, int(record["depth"]) - base)}
                     for node_id, (record, _node) in current.nodes.items() if node_id in kept]
            return {"ok": True, "app": a11y_read.safe(current.app.get_name, ""), "window": "", "nodes": nodes,
                    "truncated": len(keep) > len(kept), "total": len(kept), "subtree": True}
        node, title = _active_app()
        fresh = Snapshot(node)
        _walk(fresh, node, 0, "", max_nodes)
        if fresh.count <= 1:
            # Pruning removed (almost) everything: some toolkits do not report visibility at all. Prefer a bigger,
            # complete tree to an authoritative-looking empty one.
            fresh = Snapshot(node)
            _walk_unpruned(fresh, node, 0, "", max_nodes)
        self.current = fresh
        return {"ok": True, "app": a11y_read.safe(node.get_name, ""), "window": title, "nodes": fresh.public(),
                "truncated": fresh.truncated, "total": fresh.count, "pruned": fresh.pruned}

    def _element(self, request: dict[str, Any]):
        element_id = str(request.get("element") or "")
        if self.current is None:
            raise LookupError("there is no current snapshot; read the element tree first")
        entry = self.current.nodes.get(element_id)
        if entry is None:
            raise LookupError(f"element {element_id or '(none)'} is not in the current snapshot; read the tree again")
        return entry[1], entry[0]

    def activate(self, request: dict[str, Any]) -> dict[str, Any]:
        node, _record = self._element(request)
        chosen = a11y_read.preferred_action(node)
        if chosen is not None:
            name, index = chosen
            done = Atspi.Action.do_action(node, index)
            return {"ok": True, "action": name[:40], "dispatched": bool(done)}
        try:
            focused = bool(Atspi.Component.grab_focus(node))
        except Exception:
            focused = False
        if not focused:
            raise LookupError("the element offers no action and cannot take focus")
        return {"ok": True, "action": "focus", "dispatched": True}

    def set_text(self, request: dict[str, Any]) -> dict[str, Any]:
        node, record = self._element(request)
        body = request.get("text")
        if not isinstance(body, str) or not body:
            raise ValueError("text is required")
        if len(body) > MAX_TEXT_INPUT:
            raise ValueError(f"at most {MAX_TEXT_INPUT} characters per call")
        replaced = bool(Atspi.EditableText.set_text_contents(node, body))
        if record.get("redacted"):
            # Writing a credential is allowed; echoing it back is not.
            return {"ok": True, "chars": len(body), "redacted": True, "verified": replaced}
        time.sleep(0.12)
        # Read back enough to compare with what was set. The read-back is only compared, never shown to a model, so it
        # is bounded by the same limit as the input rather than by the per-node text bound.
        want = min(len(body) + 20, MAX_TEXT_INPUT)
        try:
            readback = Atspi.Text.get_text(node, 0, want)
        except Exception:
            readback = ""
        try:
            available = int(Atspi.Text.get_character_count(node))
        except Exception:
            available = len(readback or "")
        return {"ok": True, "chars": len(body), "redacted": False, "verified": replaced,
                "readback": a11y_read.text(readback, MAX_TEXT_INPUT),
                "readback_truncated": available > want}


def _reply(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    service = Service()
    try:
        _reply({"ready": True, "apps": len(_apps())})
    except Exception as exc:  # noqa: BLE001 - the parent turns this into a clear refusal
        _reply({"ready": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
        return 2
    handlers = {"snapshot": service.snapshot, "activate": service.activate, "set_text": service.set_text}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            op = str(request.get("op") or "")
            handler = handlers.get(op)
            if handler is None:
                raise ValueError(f"unknown operation {op!r}")
            _reply(handler(request))
        except Exception as exc:  # noqa: BLE001 - one bad request must not end the session
            _reply({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
