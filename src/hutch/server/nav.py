"""One navigation model for Hutch's app chrome.

The SPA app shell (static/index.html) and every server-rendered page render the
same destinations in the same order. The SPA document still carries its own
list; tests/test_navbar_consistency.py fails when the two drift apart.

Hrefs are absolute (/#/...) because a server page is a different document; the
SPA itself uses the same hash routes without the leading slash.
"""

PRIMARY = (
    ("today", "/#/today", "Today", "check"),
    ("chat", "/#/chat", "Chat", "chat"),
    ("tasks", "/#/tasks", "Tasks", "checklist"),
    ("approvals", "/#/approvals", "Needs you", "shield"),
)

MORE = (
    ("activity", "/#/activity", "Activity", "clock"),
    ("schedules", "/#/schedules", "Scheduled work", "calendar"),
    ("shared", "/#/shared", "Shared", "users"),
    ("catalog", "/#/catalog", "Catalog", "layers"),
    ("models", "/models", "Models", "cpu"),
    ("connectors", "/connectors", "Connectors", "layers"),
    ("usage", "/usage", "Usage", "chart"),
    ("runtime", "/#/runtime", "Runtime", "terminal"),
    ("bots", "/#/bots", "Assistants", "bot"),
)

FOOT = (
    ("connections", "/#/connections", "Apps & AI", "layers"),
    ("settings", "/#/settings", "Settings", "settings"),
)

MORE_KEYS = frozenset(item[0] for item in MORE)

# Page routes whose destination lives under a sidebar row with another key.
# Deletion is an assistant-settings action, not a primary destination.
_ALIASES = {"deletion": "bots"}


def normalize(nav: str) -> str:
    """Return the sidebar destination key for a page's nav value."""
    return _ALIASES.get(nav or "", nav or "")


def more_open(nav: str) -> bool:
    """True when the active destination is inside the collapsed More group."""
    return normalize(nav) in MORE_KEYS
