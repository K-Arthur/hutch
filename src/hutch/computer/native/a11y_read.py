"""Bounded, secret-aware reads from one AT-SPI node.

These are the only places the worker asks an application for a value, so the limits live here rather than being spread
through the request handlers: names, descriptions, text and action names are all clamped, and password or protected text
is reported as redacted instead of returned. Nothing here decides *what* to read (that is the worker's job) or talks to a
process (that is the parent's).

Imported both as part of the package and as a sibling module when the worker runs as a script.
"""

from __future__ import annotations

from typing import Any, Optional

from gi.repository import Atspi

MAX_NAME = 120
MAX_DESCRIPTION = 160
MAX_NODE_TEXT = 400
MAX_ACTIONS = 4
MAX_NODE_DEPTH = 14

#: Text is never read from these roles. ``password text`` is the AT-SPI role for a secret entry field.
SECRET_ROLES = {"password text"}
SECRET_HINTS = ("password", "passwd", "secret", "pin")

#: Action names worth trying first, most specific first, when an element exposes several.
PREFERRED_ACTIONS = ("press", "click", "activate", "invoke", "open", "select")


def safe(getter, default):
    try:
        value = getter()
    except Exception:
        return default
    return default if value is None else value


def text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def attributes(node: Any) -> dict[str, str]:
    try:
        attrs = Atspi.Accessible.get_attributes(node)
    except Exception:
        return {}
    if not attrs:
        return {}
    return {str(key): str(value) for key, value in dict(attrs).items()}


def is_secret(node: Any, role: str, name: str) -> bool:
    """Whether this element's contents must not be returned. Best-effort, and biased towards withholding."""
    if role.lower() in SECRET_ROLES:
        return True
    attrs = attributes(node)
    if attrs.get("protected", "").lower() in ("true", "1"):
        return True
    if attrs.get("text-model", "").lower() == "password":
        return True
    # A label is not a secret, but a text field whose name says password is.
    if role.lower() in ("text", "entry", "password text", "terminal"):
        joined = f"{name} {attrs.get('label', '')}".lower()
        return any(hint in joined for hint in SECRET_HINTS)
    return False


def node_text(node: Any, budget: int) -> str:
    """Up to ``budget`` characters of the node's text, if it has any."""
    if budget <= 0:
        return ""
    try:
        count = Atspi.Text.get_character_count(node)
    except Exception:
        return ""
    if not isinstance(count, int) or count <= 0:
        return ""
    limit = min(count, MAX_NODE_TEXT, budget)
    try:
        return text(Atspi.Text.get_text(node, 0, limit), limit)
    except Exception:
        return ""


def action_names(node: Any) -> list[str]:
    try:
        total = Atspi.Action.get_n_actions(node)
    except Exception:
        return []
    names: list[str] = []
    for index in range(min(int(total or 0), MAX_ACTIONS)):
        try:
            name = Atspi.Action.get_action_name(node, index)
        except Exception:
            continue
        if name:
            names.append(str(name)[:40])
    return names


def preferred_action(node: Any) -> Optional[tuple[str, int]]:
    """The action to invoke: the first preferred name present, else the first one the element offers."""
    try:
        total = int(Atspi.Action.get_n_actions(node) or 0)
    except Exception:
        return None
    if not total:
        return None
    names: list[tuple[str, int]] = []
    for index in range(total):
        try:
            names.append((str(Atspi.Action.get_action_name(node, index) or ""), index))
        except Exception:
            continue
    for wanted in PREFERRED_ACTIONS:
        for name, index in names:
            if name.strip().lower() == wanted:
                return name, index
    return names[0] if names else None


def bounds(node: Any) -> Optional[list[int]]:
    try:
        ext = Atspi.Component.get_extents(node, Atspi.CoordType.SCREEN)
    except Exception:
        return None
    if ext is None or ext.width <= 0 or ext.height <= 0:
        return None
    return [int(ext.x), int(ext.y), int(ext.width), int(ext.height)]


def states(node: Any) -> list[str]:
    try:
        state_set = Atspi.Accessible.get_state_set(node)
    except Exception:
        return []
    found = []
    for name in ("focused", "editable", "enabled"):
        try:
            if state_set.contains(getattr(Atspi.StateType, name.upper())):
                found.append(name)
        except Exception:
            continue
    return found
