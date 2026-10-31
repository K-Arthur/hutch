"""Which assistant is the person's main assistant.

The first assistant a person creates becomes the workspace coordinator, the one they talk to first and the only
one that may later suggest specialists (which they approve). This is OpenClaw's rule for team creation: the first
coordinator is the system agent only when none is set, and an existing owner is kept. It is applied where a person
creates an assistant (`POST /api/bots`), not in `Store.create_bot`, which migrations and tests call directly.
"""

from __future__ import annotations

from typing import Any


def ensure_main_assistant(store: Any, bot: Any) -> bool:
    """Make `bot` the coordinator if it is the only assistant and none is chosen. Returns True when it did."""
    if store.workspace_coordinator() is not None or len(store.list_bots()) != 1:
        return False
    store.set_workspace_coordinator(bot.id)
    return True
