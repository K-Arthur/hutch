"""Which assistant is the person's main assistant.

There is no setting for it. The first assistant a person creates becomes the main assistant: the one they talk to
first and the only one that may later suggest specialists (which they approve). Grok Bot does the same (its first
Bot is created at onboarding and the person names it) and OpenClaw's rule is the same for a team: the first coordinator
is the system agent only when none is set, and an existing owner is kept. A workspace that predates the idea, or whose
main assistant was removed, gets one the same way: the next assistant created becomes it. A leftover on the retired demo
route is never made the main assistant. This is applied where a person creates an assistant (`POST /api/bots`), not in
`Store.create_bot`, which migrations and tests call directly.
"""

from __future__ import annotations

from typing import Any

from .demo_leftovers import RETIRED_DEMO


def ensure_main_assistant(store: Any, bot: Any) -> bool:
    """Make `bot` the main assistant when there is none. Returns True when it did."""
    if store.workspace_coordinator() is not None or RETIRED_DEMO.match((bot.model or "").strip()):
        return False
    store.set_workspace_coordinator(bot.id)
    return True
