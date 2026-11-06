"""Local model lifecycle: loading, sleeping and reloading as states, with measured time.

A runtime that is loading is alive and working, not failing. llama.cpp says so on
``/health`` (503 "Loading model"), and a sleeping or evicted model is reloadable rather than
down. Every observation here is a read of the runtime's own signal; the only guessed value
is the poll interval, and the wait is always bounded.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ...context import plan_context
from ..base import ProviderError
from ..locality import LOCAL_PROVIDERS
from .base import LOADING, NEEDS_KEY, READY, UNKNOWN, UNREACHABLE, RuntimeState
from .probe import ProbeError, post_json

DEFAULT_LOAD_TIMEOUT = 600.0
LOAD_POLL_SECONDS = 0.25
#: sglang is discoverable but not in the name-level locality set; it still has no load endpoint.
REFRESH_PROVIDERS = frozenset(LOCAL_PROVIDERS | {"sglang"})


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


def _state(adapter) -> RuntimeState:
    try:
        return adapter.state()
    except ValueError as exc:
        return RuntimeState("", state=UNKNOWN, detail=str(exc))


def observe_load(adapter, model: str, *, timeout: float = DEFAULT_LOAD_TIMEOUT,
                 poll: float = LOAD_POLL_SECONDS, on_loading: Optional[Callable[[bool], None]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> LoadObservation:
    """Wait while the runtime reports ``loading``; return what it reported and how long it took."""
    try:
        state = adapter.state()
    except ValueError as exc:
        return LoadObservation(UNKNOWN, UNKNOWN, detail=str(exc), blocked=True,
                               error_kind="bad_request")
    sleeping = bool(getattr(state, "sleeping", False))
    if state.state != LOADING:
        if not state.reachable:
            detail = state.detail
        else:
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
            state = _state(adapter)
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
                                   error_kind=kind, state=_state(adapter))
        except ValueError as exc:
            return LoadObservation(UNREACHABLE, UNREACHABLE, detail=str(exc), blocked=True,
                                   error_kind="bad_request", state=_state(adapter))
        finally:
            _notify(on_loading, False)
        waited_ms = (time.perf_counter() - started) * 1000.0
        detail = (f"LM Studio loaded {model} at {applied:,} tokens in {waited_ms / 1000:.1f}s"
                  if applied else f"LM Studio loaded {model} in {waited_ms / 1000:.1f}s")
        return LoadObservation(UNREACHABLE, READY, waited_ms, detail, state=_state(adapter))
    try:
        response = post_json(adapter.base_url + "/models/load", {"model": model},
                             timeout=min(timeout, 60.0), bearer=credential)
    except ProbeError as exc:
        return LoadObservation(UNREACHABLE, UNREACHABLE, detail=str(exc), blocked=True,
                               error_kind="unreachable", state=_state(adapter))
    except ValueError as exc:
        return LoadObservation(UNREACHABLE, UNREACHABLE, detail=str(exc), blocked=True,
                               error_kind="bad_request", state=_state(adapter))
    if response.status in (401, 403):
        detail = "the runtime requires an API key before Hutch can load a model"
        return LoadObservation(UNREACHABLE, NEEDS_KEY, detail=detail, blocked=True,
                               error_kind="auth", state=_state(adapter))
    if response.status not in (200, 404):
        detail = f"the runtime refused to load {model} (HTTP {response.status})"
        return LoadObservation(UNREACHABLE, UNREACHABLE, detail=detail, blocked=True,
                               error_kind="server", state=_state(adapter))
    return observe_load(adapter, model, timeout=timeout, on_loading=on_loading)


def admission_memory(hardware: Any, provider: Any, model: str) -> tuple[Any, bool]:
    """Current headroom for an Ollama model, with only its own measured allocation credited."""
    hw = copy.deepcopy(hardware)
    if hw.ram_total_gb <= 0 or hw.ram_available_gb <= 0:
        raise ProviderError("oom", "available RAM could not be measured or is exhausted; no model request was sent")
    cards = [g for g in hw.gpus if not g.integrated and g.vendor in ("nvidia", "amd") and g.vram_gb]
    if hw.accelerator == "gpu" and not any(g.free_gb is not None for g in cards):
        raise ProviderError("oom", "free GPU memory could not be measured; repair the hardware probe before inference")
    # A loaded model's allocation is already deducted from physical free memory. Credit only
    # this model's reported allocation, capped by totals; multi-GPU placement is unknown, so
    # no per-card credit is invented.
    loaded = next((m for m in provider.ps() if m.get("name") == model or m.get("model") == model), None)
    if loaded:
        size, vram = loaded.get("size", 0), loaded.get("size_vram", 0)
        if isinstance(size, (int, float)) and isinstance(vram, (int, float)) and 0 <= vram <= size:
            hw.ram_available_gb = min(hw.ram_total_gb, hw.ram_available_gb + (size - vram) / 1024 ** 3)
            if len(cards) == 1 and cards[0].free_gb is not None:
                cards[0].free_gb = min(cards[0].vram_gb, cards[0].free_gb + vram / 1024 ** 3)
    return hw, loaded is not None


def ensure_loaded(provider_id: str, *, provider: Any = None, base_url: str = "", model: str,
                  num_ctx: int = 0, credential: str = "",
                  on_loading: Optional[Callable[[bool], None]] = None,
                  timeout: float = DEFAULT_LOAD_TIMEOUT) -> LoadObservation:
    """Make a local route ready before a request; a load is measured, never assumed."""
    if provider_id == "ollama":
        if provider is None or not hasattr(provider, "preload"):
            return LoadObservation(UNKNOWN, UNKNOWN, detail="no Ollama provider is available",
                                   blocked=True, error_kind="unreachable")
        if provider.is_loaded(model):
            return LoadObservation(READY, READY, detail=f"{model} is already loaded")
        _notify(on_loading, True)
        try:
            ms = provider.preload(model, "10m")
        except ProviderError as exc:
            return LoadObservation(UNKNOWN, UNKNOWN, detail=str(exc), blocked=True,
                                   error_kind=exc.kind)
        finally:
            _notify(on_loading, False)
        return LoadObservation(UNKNOWN, READY, float(ms or 0),
                               f"loaded {model} in {(ms or 0) / 1000:.1f}s (cold load)")
    from . import adapter_for

    adapter = adapter_for(provider_id, base_url, credential)
    observed = observe_load(adapter, model, timeout=timeout, on_loading=on_loading)
    if observed.blocked:
        return observed
    state = observed.state
    if state.state == NEEDS_KEY:
        return LoadObservation(observed.state_after, NEEDS_KEY, detail=state.detail, blocked=True,
                               error_kind="auth", state=state)
    if not state.reachable:
        detail = f"{provider_id} did not answer its native endpoint; the request's own error decides"
        return LoadObservation(observed.state_after, UNREACHABLE, detail=detail, state=state)
    names = [row.name for row in state.models]
    if names and model not in names:
        detail = f"model '{model}' is not listed by {provider_id} (it lists: {', '.join(names[:4])})"
        return LoadObservation(observed.state_after, observed.state_after, detail=detail, blocked=True,
                               error_kind="model_missing", state=state)
    if model in state.loaded:
        return observed
    if provider_id == "lmstudio" and not num_ctx:
        detail = ("LM Studio did not report a fitted window, so Hutch will not pre-load; the request's "
                  "own just-in-time load decides")
        return LoadObservation(observed.state_after, observed.state_after, detail=detail, state=state)
    if provider_id not in ("lmstudio", "llamacpp"):
        detail = f"{provider_id} has no native load endpoint; the request decides whether the model is resident"
        return LoadObservation(observed.state_after, observed.state_after, detail=detail, state=state)
    return load_fixed_runtime(provider_id, base_url, model, num_ctx, credential,
                              timeout=timeout, on_loading=on_loading)


def _refresh_ollama(provider: Any, model: str, num_ctx: int, hardware: Any, *,
                    expected_digest: str = "",
                    on_loading: Optional[Callable[[bool], None]] = None,
                    log: Optional[Callable[..., None]] = None) -> None:
    if provider is None or not num_ctx:
        return
    current = provider.show(model)
    if current is None:
        raise ProviderError("model_missing", f"model '{model}' is no longer installed", provider="ollama")
    if expected_digest and current.digest != expected_digest:
        raise ProviderError("bad_request", "the local model build changed during this run; start a new turn",
                            provider="ollama")
    hw, loaded = admission_memory(hardware, provider, model)
    plan = plan_context(current, hw, num_ctx, num_ctx, local=True)
    if plan.blocked:
        raise ProviderError("oom", f"insufficient current memory headroom for ollama/{model}: {plan.note}",
                            provider="ollama")
    if loaded:
        return
    _notify(on_loading, True)
    try:
        elapsed = provider.preload(model, "10m")
    finally:
        _notify(on_loading, False)
    if log is not None:
        log("load", f"reloaded {model} after another model used inference", load_ms=elapsed)


def refresh_local_route(provider_id: str, provider: Any, model: str, num_ctx: Optional[int],
                        hardware: Any, *, credential: str = "", expected_digest: str = "",
                        on_loading: Optional[Callable[[bool], None]] = None,
                        log: Optional[Callable[..., None]] = None) -> None:
    """Re-read the route before a provider call; reload once when the model went away."""
    if provider_id not in REFRESH_PROVIDERS:
        return
    if provider_id == "ollama":
        _refresh_ollama(provider, model, num_ctx or 0, hardware, expected_digest=expected_digest,
                        on_loading=on_loading, log=log)
        return
    observed = ensure_loaded(provider_id, provider=provider, base_url=getattr(provider, "base_url", ""),
                             model=model, num_ctx=num_ctx or 0, credential=credential,
                             on_loading=on_loading)
    if observed.blocked:
        raise ProviderError(observed.error_kind or "server", observed.detail, provider=provider_id)
    if observed.waited_ms and log is not None:
        log("load", observed.detail, load_ms=observed.waited_ms)
