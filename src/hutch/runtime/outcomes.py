"""How a provider failure ends or continues a run.

Kept out of the run loop so the same classification serves the transcript, the doctor and
tests. Only facts the runtime or the provider actually reported are used; text patterns are
limited to the wrappers a runtime is known to emit (R29).
"""

from __future__ import annotations

from ..providers.base import ProviderError


def exit_reason(exc: ProviderError) -> str:
    if getattr(exc, "cost_cap", False):
        return "cost_cap"
    return {"context": "context", "refused": "refused"}.get(exc.kind, "error")
