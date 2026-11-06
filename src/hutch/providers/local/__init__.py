"""Per-runtime adapters behind one narrow protocol.

Adding a runtime means adding one small adapter class and one table row, not a branch in the
discovery, admission or choice code. Unknown OpenAI-compatible servers get the generic adapter,
which refuses to name itself without a response signal.
"""

from __future__ import annotations

from typing import Any, Callable

from .base import (
    Identity,
    Loaded,
    LocalRuntime,
    RuntimeState,
    Slot,
    LOADING,
    NEEDS_KEY,
    READY,
    UNKNOWN,
    UNREACHABLE,
)
from .llamacpp import LlamaCppRuntime
from .lmstudio import LMStudioRuntime
from .openai_generic import OpenAIGenericRuntime
from .probe import (
    DEFAULT_TIMEOUT,
    HttpResult,
    ProbeError,
    get_json,
    origin,
    post_json,
    verified_loopback_url,
)

_ADAPTERS: dict[str, Callable[..., LocalRuntime]] = {
    "llamacpp": LlamaCppRuntime,
    "llama.cpp": LlamaCppRuntime,
    "lmstudio": LMStudioRuntime,
}

__all__ = [
    "Identity",
    "Loaded",
    "LocalRuntime",
    "RuntimeState",
    "Slot",
    "LOADING",
    "NEEDS_KEY",
    "READY",
    "UNKNOWN",
    "UNREACHABLE",
    "HttpResult",
    "ProbeError",
    "adapter_for",
    "get_json",
    "introspect",
    "origin",
    "post_json",
    "verified_loopback_url",
]


def adapter_for(provider_id: str, base_url: str, credential: str = "", *,
                timeout: float = DEFAULT_TIMEOUT, http: Callable[..., Any] = get_json,
                post: Callable[..., Any] = post_json) -> LocalRuntime:
    factory = _ADAPTERS.get(provider_id)
    if factory is LlamaCppRuntime:
        return LlamaCppRuntime(base_url, credential, timeout=timeout, http=http)
    if factory is LMStudioRuntime:
        return LMStudioRuntime(base_url, credential, timeout=timeout, http=http, post=post)
    return OpenAIGenericRuntime(provider_id, base_url, credential, timeout=timeout, http=http)


def introspect(provider_id: str, base_url: str, credential: str = "", *,
               timeout: float = DEFAULT_TIMEOUT, http: Callable[..., Any] = get_json) -> RuntimeState:
    return adapter_for(provider_id, base_url, credential, timeout=timeout, http=http).state()
