"""Media backend protocol and shared vocabulary.

A MediaBackend is hutch's adapter to ONE external media service. The protocol is
deliberately small: capabilities, submit, poll, fetch, cancel. Every adapter in
this package is honest about its verification status:

    **protocol-verified, live-unverified** — the adapter's request/response
    handling is exercised against in-process fakes (``openai`` with a fake
    transport, ``httpx.MockTransport``), so the protocol usage is tested; no LIVE
    provider account was exercised, so real-world drift (endpoints, auth, payload
    quirks) remains possible and is expected to surface as a loud failure, never
    as fabricated output.

Billing rule (see ``docs/research/outputs-failures-2026-10-10.md`` A.2): submit()
is the only method that can create a billable upstream job, and it is called
exactly once per media job row — idempotency is enforced one layer up in
``media.jobs.MediaJobService``, and there is deliberately no generic retry that
could double-spend.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

#: Verification status every adapter reports in capabilities()["verified"].
VERIFICATION_TAG = "protocol-verified, live-unverified"


@runtime_checkable
class MediaBackend(Protocol):
    """The five calls MediaJobService may make. ``submit`` is billable; every
    other call is an observation or a cancellation request."""

    name: str

    def capabilities(self) -> dict[str, Any]:
        """Declare what this backend can do, honestly:
        ``{"backend", "kinds", "output_formats", "max_width", "max_height",
        "max_seconds", "editing", "partial_previews", "verified", ...}``."""
        ...

    def submit(self, req: dict[str, Any]) -> str:
        """Ask the backend to start the work; returns its upstream job id.

        BILLABLE. Called at most once per media job (idempotency is enforced in
        MediaJobService; a retried submit with the same key never reaches here).
        """
        ...

    def poll(self, job: dict[str, Any]) -> dict[str, Any]:
        """Observe progress. Returns ``{"status": queued|running|succeeded|failed|
        cancelled, "error"?: str, "progress"?: float}``."""
        ...

    def fetch(self, job: dict[str, Any]) -> bytes:
        """Download the finished bytes. Expiring URLs are consumed HERE and now —
        the service stores only the fetched bytes, never a URL."""
        ...

    def cancel(self, job: dict[str, Any]) -> dict[str, Any] | None:
        """Request cancellation. Returns a confirmation dict when the backend
        ACKNOWLEDGED the cancel, or None when it did not — the service turns
        None into the honest ``cancel_unconfirmed`` state, never 'cancelled'."""
        ...
