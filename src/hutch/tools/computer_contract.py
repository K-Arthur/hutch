"""The model-facing contract of the ``computer`` tool: its actions, descriptions and JSON Schema.

Kept apart from ``computer.py`` so the execution path stays readable and the contract can be audited on its own. The schema
is the execution contract (see ``docs/realignment/tool-calling.md``): every call is validated against it before dispatch.
"""

from __future__ import annotations

from .base import _schema

ACTIONS = {
    "launch": "Start an allowed application in the isolated desktop (optionally opening a file in the workspace).",
    "elements": "Read the accessibility tree of the foreground application: element ids, roles, names, text and actions. "
                "Prefer this over pixels when it is available.",
    "activate": "Do the element's own action (press a named button, choose a menu item) or focus it. Needs the latest "
                "snapshot_id and an element id; no coordinates.",
    "set_text": "Replace the contents of an editable element through its accessibility interface, then read it back. "
                "Needs the latest snapshot_id and an element id.",
    "observe": "Capture the screen as an image frame; returns a frame_id that input actions must quote.",
    "click": "Click at pixel (x, y) of the latest frame. Needs that frame_id; refused if it is not the latest.",
    "type": "Type text into the focused control. Needs the latest frame_id.",
    "key": "Press a key or chord such as enter, escape, ctrl+s. Needs the latest frame_id.",
    "wait": "Wait up to 10 seconds, then capture a new frame.",
    "close": "End the isolated desktop session and everything started in it.",
}

#: Actions that change the session or application state; observations and `wait`/`close` do not.
STATEFUL = ("launch", "click", "type", "key", "activate", "set_text")

DESCRIPTION = (
    "Operate native desktop applications in an isolated desktop session. Prefer the accessibility tree: "
    "`elements` then `activate`/`set_text` by element id (no coordinates, no vision), and fall back to "
    "`observe` plus `click`/`type`/`key` only when no tree is available or the target has no semantic element. "
    "Actions: " + "; ".join(f"{name} — {summary}" for name, summary in ACTIONS.items()))

PARAMETERS = _schema(["action"], {
    "action": {"type": "string", "enum": list(ACTIONS)},
    "app": {"type": "string", "description": "for launch: an allowed application name"},
    "path": {"type": "string", "description": "for launch: a file inside the workspace to open"},
    "snapshot_id": {"type": "string", "description": "for activate/set_text: the snapshot_id of the latest elements read"},
    "element_id": {"type": "string", "description": "for activate/set_text: an element id from that snapshot"},
    "root": {"type": "string", "description": "for elements: read only this element's subtree"},
    "frame_id": {"type": "string", "description": "for click/type/key: the latest frame_id"},
    "x": {"type": "number", "description": "for click: horizontal pixel of the frame"},
    "y": {"type": "number", "description": "for click: vertical pixel of the frame"},
    "button": {"type": "string", "enum": ["left", "right", "middle"]},
    "count": {"type": "integer", "description": "for click: 1 or 2 (double click)"},
    "text": {"type": "string", "description": "for type: text to enter (printable ASCII); for set_text: the replacement "
                                              "contents, at most 2000 characters"},
    "keys": {"type": "string", "description": "for key: e.g. enter, ctrl+s, ctrl+shift+z"},
    "seconds": {"type": "number", "description": "for wait"},
})
