"""Write one run-ledger usage row for finished media.

Shared by the tool path and the resume path so both record the same facts: measured tokens when the
backend reports them (chat-speech does), else the dated price estimate labeled ``estimated``, else
an explicit ``unpriced`` row with no number. Recording never fails the media the user already paid
for; the caller gets back a sentence to append instead.
"""

from __future__ import annotations

from typing import Any, Optional

from .cost import estimate


def measured_usage(backend: Any, kind: str, job: dict[str, Any]) -> Any:
    """What the backend measured for this job (tokens, the answering model), or None.

    Read it BEFORE ``MediaJobService.finalize``: finalizing releases the backend's held copy, and
    the measurement lives with it."""
    result_for = getattr(backend, "result_for", None)
    return result_for(job) if kind == "audio" and callable(result_for) else None


def record_media_usage(store: Any, *, run_id: str, bot_id: str, backend: Any, kind: str,
                       job: dict[str, Any], request: dict[str, Any],
                       detail: Optional[dict[str, Any]] = None,
                       spoken: Any = None) -> tuple[str, int, int]:
    """Returns ``(note, prompt_tokens, completion_tokens)``; ``note`` is empty on success."""
    basis = (detail or {}).get("cost_basis") or _basis_for(backend, request)
    prompt_tokens = spoken.prompt_tokens if spoken else 0
    completion_tokens = spoken.completion_tokens if spoken else 0
    usd = float(basis["usd"]) if basis.get("priced") else 0.0
    model = spoken.model if spoken else str(
        getattr(getattr(backend, "route", None), "model", "") or backend.name)
    try:
        store.add_usage(
            run_id, bot_id, str(getattr(backend, "provider", backend.name)), model,
            prompt_tokens, completion_tokens, 0, usd, kind="speech" if kind == "audio" else "media",
            account_id=str(getattr(backend, "connection", "") or ""),
            cost_source="estimated" if basis.get("priced") else "unpriced")
    except Exception as exc:  # noqa: BLE001 - the media is real and must be returned
        return f"; usage could not be recorded in the run ledger: {exc}", prompt_tokens, completion_tokens
    return "", prompt_tokens, completion_tokens


def _basis_for(backend: Any, request: dict[str, Any]) -> dict[str, Any]:
    key = getattr(getattr(backend, "route", None), "price", "")
    return estimate(key, request).as_dict()
