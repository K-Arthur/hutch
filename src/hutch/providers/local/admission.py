"""Admission for local rungs: what window will this runtime actually give this model?

Ollama can be told a window per request. llama.cpp fixes it at launch and reports the per-slot
value; LM Studio fixes it at load and reports the applied value; vLLM and SGLang fix it at launch and
report it as max_model_len when their own owned_by says who they are. This module returns one shape for
all of them and never substitutes a wanted window for a measured one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ...context import plan_context
from ...hardware import Hardware
from ..base import ModelMeta, Provider
from . import adapter_for
from .base import LOADING, NEEDS_KEY, READY, UNKNOWN
from .lifecycle import observe_load
from .probe import ProbeError


@dataclass
class LocalAdmission:
    meta: Optional[ModelMeta]
    num_ctx: Optional[int]
    wanted: int
    applied: Optional[int] = None
    slots: Optional[int] = None
    state: str = READY
    note: str = ""
    blocked: bool = False
    error_kind: str = ""
    reason: str = ""
    fit_status: str = ""
    estimated: bool = False
    load_ms: float = 0.0
    sleeping: bool = False


def admit_local(provider_id: str, *, provider: Optional[Provider], base_url: str, model: str,
                want: int, min_ctx: int, hardware: Hardware, credential: str = "",
                on_loading: Optional[Callable[[bool], None]] = None) -> LocalAdmission:
    if provider_id == "ollama" and provider is not None:
        return _admit_ollama(provider, model, want, min_ctx, hardware)
    return _admit_fixed(provider_id, base_url, model, want, min_ctx, hardware, credential,
                        on_loading=on_loading)


def _missing(model: str, available: list[str]) -> LocalAdmission:
    listed = ", ".join(available[:4]) if available else "none"
    reason = f"model '{model}' is not listed by the runtime (it lists: {listed})"
    return LocalAdmission(None, None, 0, state="missing", note=reason, blocked=True,
                          error_kind="model_missing", reason=reason)


def _blocked(kind: str, reason: str, state: str = UNKNOWN) -> LocalAdmission:
    return LocalAdmission(None, None, 0, state=state, note=reason, blocked=True,
                          error_kind=kind, reason=reason)


def _admit_ollama(provider: Provider, model: str, want: int, min_ctx: int,
                  hardware: Hardware) -> LocalAdmission:
    meta = provider.show(model)
    if meta is None:
        health = provider.health()
        if not health.ok:
            return _blocked("unreachable", health.detail, "unreachable")
        return LocalAdmission(None, None, want, state="missing", blocked=True, error_kind="model_missing",
                              note=f"model '{model}' is not installed - `ollama pull {model}`",
                              reason=f"model '{model}' is not installed - `ollama pull {model}`")
    plan = plan_context(meta, hardware, want, min_ctx, local=True)
    if plan.blocked or not plan.num_ctx:
        return LocalAdmission(meta, None, want, state="wont_fit", note=plan.note, blocked=True,
                              error_kind="oom", reason=f"{model} does not fit this machine: {plan.note}",
                              fit_status=plan.fit.status if plan.fit else "unknown",
                              estimated=bool(plan.fit and plan.fit.estimated))
    return LocalAdmission(meta, plan.num_ctx, want, state=READY, note=plan.note,
                          fit_status=plan.fit.status if plan.fit else "unknown",
                          estimated=bool(plan.fit and plan.fit.estimated))


def _admit_fixed(provider_id: str, base_url: str, model: str, want: int, min_ctx: int,
                 hardware: Hardware, credential: str,
                 on_loading: Optional[Callable[[bool], None]] = None) -> LocalAdmission:
    adapter = adapter_for(provider_id, base_url, credential)
    observed = observe_load(adapter, model, on_loading=on_loading)
    state = observed.state
    load_ms = observed.waited_ms
    if observed.blocked:
        return _blocked(observed.error_kind or "server", observed.detail, observed.state_after)
    if state.state == NEEDS_KEY:
        return _blocked("auth", state.detail, NEEDS_KEY)
    if not state.reachable:
        note = (f"{provider_id} did not answer its native endpoint ({state.detail or 'no response'}); "
                "the request will be attempted and its own error decides")
        return LocalAdmission(None, None, want, state="unreachable", note=note)
    names = [row.name for row in state.models]
    if names and model not in names:
        return _missing(model, names)
    if state.state == LOADING:
        return _blocked("server", f"{provider_id} is still loading the model: {state.detail}", LOADING)
    meta = next((row for row in state.models if row.name == model), None)
    loaded = state.loaded.get(model)
    if loaded is not None and loaded.applied_context:
        # llama.cpp reports one n_ctx per slot. LM Studio's `parallel` is a concurrency setting;
        # with unified KV it does not divide the window, so do not claim that it does.
        if loaded.slots and loaded.parallel and loaded.parallel > 1:
            slots_note = f" per request across {loaded.parallel} slots"
        elif loaded.parallel and loaded.parallel > 1:
            slots_note = f" (parallel {loaded.parallel})"
        else:
            slots_note = ""
        runtime = f"{provider_id} {state.version}".strip()
        note = (f"{runtime} reports {loaded.applied_context:,} tokens applied{slots_note}"
                + (f" (wanted {want:,}; a fixed window cannot be changed per request)" if want != loaded.applied_context else ""))
        if meta is not None:
            meta.applied_context = loaded.applied_context
        return LocalAdmission(meta, loaded.applied_context, want, applied=loaded.applied_context,
                              slots=loaded.parallel, state=READY, note=note, load_ms=load_ms,
                              sleeping=observed.sleeping)
    if meta is None:
        note = (f"{provider_id} did not report its models or its window; Hutch will not assume either "
                f"(wanted {want:,})")
        return LocalAdmission(None, None, want, state=UNKNOWN, note=note, load_ms=load_ms,
                              sleeping=observed.sleeping)
    if observed.sleeping:
        note = (f"{provider_id} reports {model} asleep; the next request reloads it, and Hutch will size "
                f"the run only after the runtime reports the applied window (wanted {want:,})")
        return LocalAdmission(meta, None, want, state=UNKNOWN, note=note, load_ms=load_ms,
                              sleeping=True)
    if provider_id == "lmstudio":
        return _load_lmstudio(adapter, meta, model, want, min_ctx, hardware, on_loading=on_loading)
    note = (f"{provider_id} does not report the window it serves over its model list; Hutch cannot size this "
            f"run to it (wanted {want:,})")
    return LocalAdmission(meta, None, want, state=UNKNOWN, note=note, load_ms=load_ms)


def _load_lmstudio(adapter: Any, meta: Optional[ModelMeta], model: str, want: int, min_ctx: int,
                   hardware: Hardware,
                   on_loading: Optional[Callable[[bool], None]] = None) -> LocalAdmission:
    if meta is None:
        return _missing(model, [])
    wanted = min(want, meta.max_context) if meta.max_context else want
    plan = plan_context(meta, hardware, wanted, min_ctx, local=True)
    if plan.blocked or not plan.num_ctx:
        return LocalAdmission(meta, None, want, state="wont_fit", note=plan.note, blocked=True,
                              error_kind="oom", reason=f"{model} does not fit this machine: {plan.note}",
                              fit_status=plan.fit.status if plan.fit else "unknown",
                              estimated=bool(plan.fit and plan.fit.estimated))
    if on_loading is not None:
        on_loading(True)
    started = time.perf_counter()
    try:
        applied = adapter.load(model, plan.num_ctx)
    except ProbeError as exc:
        kind = "auth" if exc.kind == "needs_key" else "server"
        return _blocked(kind, str(exc))
    finally:
        if on_loading is not None:
            on_loading(False)
    load_ms = (time.perf_counter() - started) * 1000.0
    if applied:
        meta.applied_context = applied
        note = (f"LM Studio loaded {model} at {applied:,} tokens in {load_ms / 1000:.1f}s"
                + (f" (wanted {want:,})" if want != applied else ""))
        return LocalAdmission(meta, applied, want, applied=applied, state=READY, note=note,
                              fit_status=plan.fit.status if plan.fit else "unknown",
                              estimated=bool(plan.fit and plan.fit.estimated), load_ms=load_ms)
    note = (f"LM Studio did not report the applied window for {model}; Hutch will not assume "
            f"the requested {plan.num_ctx:,} took effect")
    return LocalAdmission(meta, None, want, state=UNKNOWN, note=note, load_ms=load_ms)
