"""Why an assistant cannot run, decided from its saved model route.

One answer for the roster, the composer chip, settings and `/api/bots`. The demo runtime was removed, but
assistants created before that can still point at its route; older demo-era rows may also carry a model
that is not a route at all (for example `demo`). Both used to look healthy ("Idle", a chip reading "demo")
and only failed when a message was sent. `None` means nothing is known to be wrong at the route's shape
level; whether the route is reachable and configured is the model picker's and `hutch doctor`'s job.

The shape rules mirror `modelchoices.validate_override`, which refuses a route at send time: a provider and
a model separated by a slash, and an OpenCode assistant only accepts `opencode/provider/model`. The answer
must not depend on who asks or whether a server is running, so it stays a pure function of the saved bot.
"""

from __future__ import annotations

from typing import Optional

from .models import Bot, Run, RunStatus, RuntimeKind

LEGACY_ERROR_MARKERS = ("mock runtime was removed", "retired demo route", "retired demo runtime")


def model_route_problem(model: str, runtime: RuntimeKind = RuntimeKind.builtin) -> Optional[str]:
    """The same shape answer for a saved route string that may not be attached to an assistant yet."""
    model = (model or "").strip()
    if runtime is RuntimeKind.mock:
        return "it uses a retired demo runtime that can no longer run"
    if runtime not in (RuntimeKind.builtin, RuntimeKind.opencode):
        # These runtimes choose their own model; a saved route is not the thing that makes them runnable.
        return None
    if not model:
        return "no model route is set"
    parts = model.split("/")
    provider, remaining = parts[0].strip(), "/".join(parts[1:]).strip()
    if not provider or not remaining or not all(part.strip() for part in parts):
        return "its saved model route is not a provider/model route, so it cannot run"
    if provider.lower() == "mock":
        return "it uses a retired demo route that can no longer run"
    if runtime is RuntimeKind.opencode:
        if provider.lower() != "opencode" or len(parts) != 3:
            return "its saved model route is not an OpenCode route, so it cannot run"
    elif provider.lower() == "opencode":
        return "its saved model route belongs to the OpenCode runtime, but this assistant uses the Hutch built-in runtime"
    return None


def route_problem(bot: Bot) -> Optional[str]:
    return model_route_problem(bot.model, bot.runtime)


def run_is_legacy(run: Run, bot: Optional[Bot] = None) -> bool:
    """True for a finished failure caused by a retired demo runtime or an unusable saved route.

    Legacy failures are history, not current work: Activity keeps them out of "Needs you", History labels
    them, and the installation review counts them. Computed on read; nothing is rewritten.
    """
    if run.status is not RunStatus.failed:
        return False
    if bot is not None and route_problem(bot):
        return True
    error = (run.error or "").lower()
    return any(marker in error for marker in LEGACY_ERROR_MARKERS)
