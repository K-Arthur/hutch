"""Vision capability for a local OpenAI-compatible route, from the runtime's own signal.

LM Studio reports ``capabilities.vision`` in ``/api/v1/models``; llama.cpp reports
``modalities.vision`` in ``/props`` and input modalities in ``/v1/models``. Neither is a
model-name guess, and neither endpoint needs a credential to answer the capability
question, so admission and the runtime gate can ask the same source.

The resolver returns ``None`` for a provider it does not own, so a custom or hosted
endpoint keeps its existing rule. An unreadable runtime returns ``False``: a route that
cannot state the capability must not be promised image input.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

#: The providers whose adapter exposes a vision signal. vLLM/SGLang report none over
#: /v1/models, so they fall through to the caller's false and the refusal says so.
LOCAL_VISION_PROVIDERS = frozenset({"llamacpp", "llama.cpp", "lmstudio"})


def local_vision_supported(provider_id: str, base_url: str, model: str, credential: str = "",
                           *, timeout: float = 3.0,
                           http: Optional[Callable[..., Any]] = None) -> Optional[bool]:
    """True/False from the runtime, or None when this is not a local provider Hutch owns."""
    if provider_id not in LOCAL_VISION_PROVIDERS:
        return None
    if not model or not base_url:
        return False
    from . import adapter_for

    try:
        options = {"timeout": timeout}
        if http is not None:
            options["http"] = http
        capabilities = adapter_for(provider_id, base_url, credential, **options).capabilities(model)
    except Exception:
        return False
    return "vision" in capabilities
