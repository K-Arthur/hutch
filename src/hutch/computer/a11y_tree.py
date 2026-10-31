"""The bounded accessibility tree as Hutch reports it, and validation of the worker's reply.

Split from ``accessibility.py`` on purpose: this module is pure data (no process, no session, no policy), so the same
limits and rendering are testable without a desktop. Every value that reaches a model or a run record passes through
here, which is why the caps live in one place: node count, depth, and the length of names, descriptions, text and action
names. Nothing carries a filesystem path or a raw AT-SPI handle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

MAX_NODES = 240
MAX_NODE_DEPTH = 14
MAX_NAME = 120
MAX_DESCRIPTION = 160
MAX_NODE_TEXT = 400
MAX_ACTION_NAME = 40
MAX_ACTIONS = 4


class AccessibilityError(Exception):
    """The worker refused or failed one request, or its reply was unusable. Safe to show to a person."""


#: Roles that exist to hold other widgets. They are worth listing when they carry a name, text, description or
#: action (a titled panel, a labelled group), and pure noise when they do not: KWrite reports 37 fillers, 24 panels and
#: 59 separators, none of which a model can act on.
STRUCTURAL_ROLES = frozenset({"separator", "filler", "scroll bar", "split pane", "layered pane", "panel", "unknown",
                              "viewport", "drawing area", "redundant object"})


@dataclass(frozen=True)
class Node:
    id: str
    role: str
    name: str
    depth: int
    parent: str = ""
    actions: tuple[str, ...] = ()
    text: str = ""
    redacted: bool = False
    description: str = ""
    bounds: Optional[tuple[int, int, int, int]] = None
    state: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        record: dict[str, Any] = {"id": self.id, "role": self.role, "depth": self.depth}
        if self.name:
            record["name"] = self.name
        if self.actions:
            record["actions"] = list(self.actions)
        if self.text:
            record["text"] = self.text
        if self.redacted:
            record["redacted"] = True
        if self.description:
            record["description"] = self.description
        if self.bounds:
            record["bounds"] = list(self.bounds)
        if self.state:
            record["state"] = list(self.state)
        return record

    def plain_layout(self) -> bool:
        """A container that carries no information and no action: it only holds other widgets."""
        return (self.role in STRUCTURAL_ROLES and not self.name and not self.text and not self.actions
                and not self.description)

    def line(self) -> str:
        """One compact, model-readable line: what the element is and how to act on it."""
        bits = [self.id, self.role]
        if self.name:
            bits.append(json.dumps(self.name, ensure_ascii=False))
        if self.text and self.text.strip() and self.text.strip() != self.name.strip():
            bits.append(f"text={json.dumps(self.text, ensure_ascii=False)}")
        if self.redacted:
            bits.append("(text redacted)")
        if self.actions:
            bits.append("actions=" + ",".join(self.actions))
        if "focused" in self.state:
            bits.append("focused")
        return "  " * min(self.depth, MAX_NODE_DEPTH) + " ".join(bits)


@dataclass(frozen=True)
class ElementSnapshot:
    snapshot_id: str
    app: str
    window: str
    nodes: tuple[Node, ...]
    truncated: bool = False
    subtree: bool = False
    pruned: int = 0

    def by_id(self, element_id: str) -> Optional[Node]:
        for node in self.nodes:
            if node.id == element_id:
                return node
        return None

    def public(self) -> dict[str, Any]:
        return {"schema": 1, "snapshot_id": self.snapshot_id, "app": self.app, "window": self.window,
                "truncated": self.truncated, "subtree": self.subtree, "pruned": self.pruned,
                "nodes": [node.public() for node in self.nodes]}

    def render(self, *, limit: int = 200, compact: bool = True) -> str:
        header = f"accessibility tree of {self.app or 'the application'}"
        if self.window:
            header += f" (window {json.dumps(self.window, ensure_ascii=False)})"
        lines = [f"{header}; {len(self.nodes)} element(s); snapshot {self.snapshot_id}. "
                 f"Act with snapshot_id {self.snapshot_id} and an element id, e.g. activate n12."]
        shown = [node for node in self.nodes if not (compact and node.plain_layout())]
        skipped = len(self.nodes) - len(shown)
        for node in shown[:limit]:
            lines.append(node.line())
        if len(shown) > limit:
            lines.append(f"... {len(shown) - limit} more element(s) not shown")
        if skipped:
            lines.append(f"{skipped} unnamed layout container(s) not listed; pass a root element id to read one subtree.")
        if self.pruned:
            lines.append(f"{self.pruned} closed menu(s) and their items are not listed; "
                         f"open a menu to see its items.")
        if self.truncated:
            lines.append("The tree was truncated to stay bounded; pass a root element id to read one subtree.")
        return "\n".join(lines)


def _as_str(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _as_id(value: Any) -> str:
    text = value if isinstance(value, str) else ""
    if not text.startswith("n") or not text[1:].isdigit() or len(text) > 8:
        return ""
    return text


def _as_depth(value: Any) -> int:
    try:
        depth = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(depth, MAX_NODE_DEPTH))


def _as_bounds(value: Any) -> Optional[tuple[int, int, int, int]]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        numbers = [int(part) for part in value]
    except (TypeError, ValueError):
        return None
    x, y, width, height = numbers
    if width <= 0 or height <= 0 or any(abs(number) > 100_000 for number in numbers):
        return None
    return x, y, width, height


def _as_count(value: Any, limit: int = 100_000) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(count, limit))


def _as_list(value: Any, limit: int, item_limit: int) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[str] = []
    for item in list(value)[:limit]:
        text = _as_str(item, item_limit)
        if text:
            out.append(text)
    return tuple(out)


def parse_snapshot(payload: Mapping[str, Any], snapshot_id: str) -> ElementSnapshot:
    """Validate a worker reply into a snapshot. Raises ``AccessibilityError`` rather than trusting the shape."""
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list):
        raise AccessibilityError("the accessibility worker returned no element list")
    nodes: list[Node] = []
    seen: set[str] = set()
    for entry in raw_nodes[:MAX_NODES]:
        if not isinstance(entry, dict):
            continue
        node_id = _as_id(entry.get("id"))
        role = _as_str(entry.get("role"), 40)
        if not node_id or not role or node_id in seen:
            continue
        seen.add(node_id)
        nodes.append(Node(
            id=node_id, role=role, name=_as_str(entry.get("name"), MAX_NAME), depth=_as_depth(entry.get("depth")),
            parent=_as_id(entry.get("parent")), actions=_as_list(entry.get("actions"), MAX_ACTIONS, MAX_ACTION_NAME),
            text=_as_str(entry.get("text"), MAX_NODE_TEXT), redacted=bool(entry.get("redacted")),
            description=_as_str(entry.get("description"), MAX_DESCRIPTION),
            bounds=_as_bounds(entry.get("bounds")), state=_as_list(entry.get("state"), 4, 12)))
    if not nodes:
        raise AccessibilityError("the accessibility tree was empty")
    return ElementSnapshot(snapshot_id=snapshot_id, app=_as_str(payload.get("app"), MAX_NAME),
                            window=_as_str(payload.get("window"), MAX_NAME), nodes=tuple(nodes),
                            truncated=bool(payload.get("truncated")), subtree=bool(payload.get("subtree")),
                            pruned=_as_count(payload.get("pruned")))
