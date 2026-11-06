"""Service-level job status and the honest wording of a failure.

The store's ``media_jobs.status`` CHECK allows five values, so the richer states a caller needs are
encoded in the ``error`` text's prefix and decoded here:

========================  ========================================================================
service status            store representation
========================  ========================================================================
``submitting``            ``queued`` (no upstream id yet: not accepted)
``cancel_unconfirmed``    ``failed`` + ``cancel_unconfirmed:`` (the upstream job may still bill)
``refused``               ``failed`` + ``refused:`` (the provider's policy declined the request)
========================  ========================================================================

A refusal is not a crash and not a transient error: retrying the same prompt is pointless and, on
some providers, billed. It is reported as its own outcome with the provider's own reason.
"""

from __future__ import annotations

from typing import Any

from .providers.base import MediaRefused

CANCEL_UNCONFIRMED_PREFIX = "cancel_unconfirmed:"
REFUSED_PREFIX = "refused:"


def service_status(row: dict[str, Any]) -> str:
    """The service-level status of a stored job row."""
    status = row.get("status")
    error = row.get("error") or ""
    if status == "queued":
        return "submitting"
    if status == "failed" and error.startswith(CANCEL_UNCONFIRMED_PREFIX):
        return "cancel_unconfirmed"
    if status == "failed" and error.startswith(REFUSED_PREFIX):
        return "refused"
    return str(status)


def failure_text(state: dict[str, Any]) -> str:
    """The ``error`` for an upstream ``failed`` observation, prefixed when it was a refusal."""
    text = str(state.get("error") or "the upstream job failed")
    if state.get("refused") and not text.startswith(REFUSED_PREFIX):
        return f"{REFUSED_PREFIX} {text}"
    return text


def failure_cost_note(state: dict[str, Any], default: str) -> str:
    if state.get("refused"):
        return ("the provider declined this request on content grounds; many providers do not "
                "charge for a refused request, but verify against the account")
    return default


def submit_failure(exc: Exception) -> dict[str, str]:
    """``error`` and ``cost_note`` for a submit that raised."""
    if isinstance(exc, MediaRefused):
        return {"error": f"{REFUSED_PREFIX} {exc}",
                "cost_note": failure_cost_note({"refused": True}, "")}
    return {"error": f"upstream submit failed: {exc}",
            "cost_note": "no upstream job was accepted, so no provider charge should exist "
                         "- verify against the backend account"}
