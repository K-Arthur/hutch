"""Local model lifecycle: loading, sleeping and reloading as states, with measured time.

A runtime that is loading is alive and working, not failing. llama.cpp says so on
``/health`` (503 "Loading model"), and a sleeping or evicted model is reloadable rather than
down. Every observation here is a read of the runtime's own signal; the only guessed value
is the poll interval, and the wait is always bounded.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .base import LOADING, NEEDS_KEY, READY, UNREACHABLE, RuntimeState
from .probe import ProbeError, post_json

DEFAULT_LOAD_TIMEOUT = 600.0
LOAD_POLL_SECONDS = 0.25


@dataclass
class LoadObservation:
    state_before: str
    state_after: str
    waited_ms: float = 0.0
    detail: str = ""
    blocked: bool = False
    error_kind: str = ""
    sleeping: bool = False
    state: Optional[RuntimeState] = field(default=None, repr=False)


def _notify(on_loading: Optional[Callable[[bool], None]], loading: bool) -> None:
    if on_loading is not None:
        on_loading(loading)


def observe_load(adapter, model: str, *, timeout: float = DEFAULT_LOAD_TIMEOUT,
                 poll: float = LOAD_POLL_SECONDS, on_loading: Optional[Callable[[bool], None]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> LoadObservation:
    """Wait while the runtime reports ``loading``; return what it reported and how long it took."""
    state = adapter.state()
    sleeping = bool(getattr(state, "sleeping", False))
    if state.state != LOADING:
        detail = (f"{model} is asleep in the runtime; the next request reloads it" if sleeping else "")
        return LoadObservation(state.state, state.state, detail=detail, sleeping=sleeping, state=state)
    _notify(on_loading, True)
    started = clock()
    try:
        while True:
            elapsed_ms = (clock() - started) * 1000.0
            if timeout > 0 and elapsed_ms / 1000.0 >= timeout:
                seconds = f"{timeout:.1f}s" if timeout < 10 else f"{timeout:.0f}s"
                detail = (f"the runtime was still loading {model} after {seconds}; Hutch stopped "
                          "waiting. Check the runtime's log, or use a smaller model or window")
                return LoadObservation(LOADING, state.state, elapsed_ms, detail, blocked=True,
                                       error_kind="timeout", state=state)
            sleep(poll)
            state = adapter.state()
            if state.state != LOADING:
                elapsed_ms = (clock() - started) * 1000.0
                detail = (f"loaded {model} in {elapsed_ms / 1000:.1f}s (cold load)"
                          if elapsed_ms >= 1000 else f"{model} became ready in {elapsed_ms:.0f}ms")
                return LoadObservation(LOADING, state.state, elapsed_ms, detail,
                                       sleeping=bool(getattr(state, "sleeping", False)), state=state)
    finally:
        _notify(on_loading, False)


def load_fixed_runtime(provider_id: str, base_url: str, model: str, context_length: int,
                       credential: str = "", *, timeout: float = DEFAULT_LOAD_TIMEOUT,
                       on_loading: Optional[Callable[[bool], None]] = None) -> LoadObservation:
    """Load a cold fixed-window route: LM Studio's native load, or llama.cpp router load."""
    from . import adapter_for

    adapter = adapter_for(provider_id, base_url, credential)
    if provider_id == "lmstudio":
        _notify(on_loading, True)
        started = time.perf_counter()
        try:
            applied = adapter.load(model, context_length)
        except ProbeError as exc:
            kind = "auth" if exc.kind == "needs_key" else "server"
            return LoadObservation(UNREACHABLE, UNREACHABLE, detail=str(exc), blocked=True,
                                   error_kind=kind, state=adapter.state())
        finally:
            _notify(on_loading, False)
        waited_ms = (time.perf_counter() - started) * 1000.0
        detail = (f"LM Studio loaded {model} at {applied:,} tokens in {waited_ms / 1000:.1f}s"
                  if applied else f"LM Studio loaded {model} in {waited_ms / 1000:.1f}s")
        return LoadObservation(UNREACHABLE, READY, waited_ms, detail, state=adapter.state())
    try:
        response = post_json(adapter.base_url + "/models/load", {"model": model},
                             timeout=min(timeout, 60.0), bearer=credential)
    except ProbeError as exc:
        return LoadObservation(UNREACHABLE, UNREACHABLE, detail=str(exc), blocked=True,
                               error_kind="unreachable", state=adapter.state())
    if response.status in (401, 403):
        detail = "the runtime requires an API key before Hutch can load a model"
        return LoadObservation(UNREACHABLE, NEEDS_KEY, detail=detail, blocked=True,
                               error_kind="auth", state=adapter.state())
    if response.status not in (200, 404):
        detail = f"the runtime refused to load {model} (HTTP {response.status})"
        return LoadObservation(UNREACHABLE, UNREACHABLE, detail=detail, blocked=True,
                               error_kind="server", state=adapter.state())
    return observe_load(adapter, model, timeout=timeout, on_loading=on_loading)
