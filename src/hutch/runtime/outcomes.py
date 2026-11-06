"""How a provider failure ends or continues a run.

Kept out of the run loop so the same classification serves the transcript, the doctor and
tests. Only facts the runtime or the provider actually reported are used; text patterns are
limited to the wrappers a runtime is known to emit (R29).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..providers.base import ProviderError
from ..providers.locality import LOCAL_PROVIDERS as _NAME_LOCAL_PROVIDERS

LOCAL_PROVIDERS = frozenset(_NAME_LOCAL_PROVIDERS | {"sglang"})
OOM_MARKERS = ("signal: killed", "out of memory", "unable to allocate", "failed to allocate",
               "not enough memory", "outofmemory")
STOPPED_MARKERS = ("runner process has terminated", "llama runner process has terminated",
                   "the stream ended before", "connection reset", "server disconnected",
                   "remote protocol error", "the response stream broke")


@dataclass(frozen=True)
class Failure:
    kind: str
    action: str            # reload | stop
    message: str = ""


def exit_reason(exc: ProviderError) -> str:
    if getattr(exc, "cost_cap", False):
        return "cost_cap"
    return {"context": "context", "refused": "refused"}.get(exc.kind, "error")


def _oom_message(partial: bool) -> str:
    if partial:
        return ("The text already produced is kept and marked incomplete. The model process was killed, "
                "most often because it ran out of memory. Hutch stopped this turn; choose a smaller model "
                "or window, free memory, then try again")
    return ("The model process was killed, most often because it ran out of memory. Hutch reloads the "
            "model once; if it dies again, choose a smaller model or window, or free memory")


def _stopped_message(partial: bool) -> str:
    if partial:
        return ("The text already produced is kept and marked incomplete. The local runtime stopped "
                "answering mid-turn, which usually means it restarted or its model process exited. "
                "Hutch stopped this turn; start the runtime and retry")
    return ("The local runtime stopped answering mid-turn, which usually means it restarted or its "
            "model process exited. Hutch reloads the model once; if it stops again, start the runtime "
            "and retry, or use a model that fits this machine")


def classify_local_failure(exc: ProviderError, provider_id: str, *, partial: bool = False) -> Failure:
    """Map one local-route failure to a recovery action and a sentence the user can act on."""
    if provider_id not in LOCAL_PROVIDERS:
        return Failure(exc.kind, "stop")
    text = str(exc).casefold()
    if exc.kind == "oom" or any(marker in text for marker in OOM_MARKERS):
        return Failure("oom", "stop" if partial else "reload", _oom_message(partial))
    if exc.kind in ("unreachable", "stream") or any(marker in text for marker in STOPPED_MARKERS):
        return Failure(exc.kind, "stop" if partial else "reload", _stopped_message(partial))
    if exc.kind == "server" and "loading model" in text:
        return Failure("server", "reload", "the runtime is still loading the model; Hutch waits once, then retries")
    return Failure(exc.kind, "stop", "")
