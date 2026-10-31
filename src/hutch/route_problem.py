"""Why an assistant cannot run, decided from its saved model route.

One answer for the roster, the composer chip and `/api/bots`. The mock runtime was removed, but
assistants created before that can still point at `mock/...`; they used to look healthy ("Idle", a
chip reading "demo") and only failed when a message was sent. `None` means nothing is known to be wrong
(whether the route is reachable is the model picker's and `hutch doctor`'s job).
"""

from __future__ import annotations

from typing import Optional

from .models import Bot, RuntimeKind


def route_problem(bot: Bot) -> Optional[str]:
    model = (bot.model or "").strip()
    if not model:
        return "no model route is set"
    if bot.runtime is RuntimeKind.mock or model.partition("/")[0].lower() == "mock":
        return "it uses a retired demo route that can no longer run"
    return None
