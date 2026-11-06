"""Speech synthesis transport: one connection's declared route as a ``MediaBackend``.

Synthesis is synchronous: ``submit`` performs the work and holds the validated bytes under a
handle. With a spool (:mod:`hutch.media.spool`) the hold is on disk, so a process that dies
between submit and fetch can finalize the job after a restart; without one the bytes are in
memory and reconciliation says the provider may have billed and the audio was never stored.
Nothing is regenerated automatically, because that would pay twice.

The key travels only to the configured endpoint, and redirects are refused because the bearer
token would follow the ``Location`` header to another host.

This is the connection-account-scoped, single-utterance path. It does not replace
``hutch.synthesis.tts``: that subsystem renders a registered multi-segment podcast script
from environment-bound keys. This one submits the text to a provider *account* and hands the
bytes to the governed media-job ledger, so the account that pays is the account the user
selected. The pure route/wire rules live in :mod:`hutch.media.providers.speech_wire`.
"""

from __future__ import annotations

from typing import Any, Optional

from ...connection_endpoints import redirect_refusal
from ..spool import MediaSpool, ResultHold, SpoolError
from .base import VERIFICATION_TAG
from .speech_wire import (MAX_TEXT_CHARS, SpeechError, SpeechResult, SpeechRoute,
                          build_payload, parse_speech_response, route_from_template,
                          wav_duration)

__all__ = ["MAX_TEXT_CHARS", "SpeechBackend", "SpeechError", "SpeechResult", "SpeechRoute",
           "build_payload", "parse_speech_response", "route_from_template", "wav_duration"]

_MAX_ERROR_DETAIL = 400


class SpeechBackend:
    """One connection's speech route, adapted to the ``MediaBackend`` protocol."""

    def __init__(self, *, connection: str, base_url: str, api_key: str, route: SpeechRoute,
                 provider: str = "", billing: str = "",
                 headers: Optional[dict[str, str]] = None, timeout: float = 180.0,
                 http_client: Any = None, spool: Optional[MediaSpool] = None):
        if not connection or not str(connection).strip():
            raise SpeechError("a speech backend needs the connection name it bills to")
        if not str(base_url or "").strip():
            raise SpeechError("this connection has no endpoint to send speech to")
        self.connection = str(connection).strip()
        self.name = f"speech:{self.connection}"
        self.base_url = str(base_url).rstrip("/")
        self.api_key = api_key
        self.route = route
        self.provider = provider or self.connection
        self.billing = billing
        self.headers = dict(headers or {})
        self.timeout = max(5.0, min(float(timeout), 600.0))
        self._http_client = http_client
        self._results: dict[str, SpeechResult] = {}
        self._hold = ResultHold(spool)

    # ---------------------------------------------------------------- protocol

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "kinds": ["audio"],
            "output_formats": [self.route.format],
            "voices": list(self.route.voices),
            "default_voice": self.route.default_voice,
            "max_text_chars": self.route.max_text_chars,
            "connection": self.connection,
            "provider": self.provider,
            "model": self.route.model,
            "billing": self.billing,
            "verified": VERIFICATION_TAG,
        }

    def approval_detail(self, request: dict[str, Any]) -> dict[str, Any]:
        """What the approval prompt shows: who receives the words and who pays."""
        text = str(request.get("prompt") or "")
        style = str(request.get("style") or "")
        return {
            "connection": self.connection,
            "provider": self.provider,
            "endpoint": self.base_url,
            "model": self.route.model,
            "voice": str(request.get("voice") or self.route.default_voice),
            "text_chars": len(text.strip()),
            "style_chars": len(style.strip()),
            "billing": self.billing,
            "note": "the text leaves this machine; the provider's plan may charge for it",
        }

    def submit(self, req: dict[str, Any]) -> str:
        """Perform the synthesis and cache the bytes. BILLABLE, called once per job."""
        payload = build_payload(self.route, str(req.get("prompt") or ""),
                                voice=str(req.get("voice") or ""),
                                style=str(req.get("style") or ""))
        import httpx

        client, owned = self._http_client, False
        if client is None:
            from ...offline import httpx_offline_options

            base_url, transport, trust_env = httpx_offline_options(self.base_url, self.name)
            client = httpx.Client(
                base_url=base_url, trust_env=trust_env, transport=transport,
                timeout=httpx.Timeout(connect=10.0, read=self.timeout, write=60.0, pool=5.0))
            owned = True
        # An injected client (tests) has no base_url of its own; use the configured endpoint
        # verbatim. The client we build has the offline-broker base already applied.
        url = "/chat/completions" if owned else f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", **self.headers}
        try:
            resp = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise SpeechError(
                f"{self.provider} did not answer the speech request within {self.timeout:g}s. "
                "The provider may have received and billed the request; Hutch did not retry "
                "it.") from exc
        except httpx.HTTPError as exc:
            raise SpeechError(
                f"cannot reach the speech endpoint at {self.base_url}: {exc}") from exc
        finally:
            if owned:
                client.close()
        if 300 <= resp.status_code < 400:
            raise SpeechError(str(redirect_refusal(self.provider, resp.headers.get("location"))))
        if resp.status_code >= 400:
            raise SpeechError(self._error_from_response(resp))
        try:
            body = resp.json()
        except ValueError as exc:
            raise SpeechError("the speech endpoint returned a non-JSON body") from exc
        result = parse_speech_response(body, self.route)
        try:
            handle = self._hold.put(result.audio, meta=_result_meta(result))
        except SpoolError as exc:
            raise SpeechError(f"the audio was synthesized but could not be held ({exc}); the "
                              "provider may have billed this request") from exc
        self._results[handle] = result
        return handle

    def poll(self, job: dict[str, Any]) -> dict[str, Any]:
        handle = str(job.get("upstream_job_id") or "")
        if handle and (handle in self._results or self._hold.has(handle)):
            return {"status": "succeeded"}
        return {"status": "failed",
                "error": ("the process that submitted this speech job is gone; the provider "
                          "may have billed the request and the audio was never stored. "
                          "Hutch does not regenerate it automatically")}

    def can_recover(self, job: dict[str, Any]) -> bool:
        return self._hold.durable and self._hold.has(str(job.get("upstream_job_id") or ""))

    def fetch(self, job: dict[str, Any]) -> bytes:
        result = self.result_for(job)
        if result is None:
            raise SpeechError("the synthesized audio is no longer held by this process")
        return result.audio

    def cancel(self, job: dict[str, Any]) -> None:
        # The request completed inside submit(); there is nothing upstream to cancel.
        return None

    # ------------------------------------------------------------------ extras

    def result_for(self, job: dict[str, Any]) -> Optional[SpeechResult]:
        handle = str(job.get("upstream_job_id") or "")
        if handle in self._results:
            return self._results[handle]
        if not self._hold.has(handle):
            return None
        try:
            audio, meta = self._hold.get(handle), self._hold.meta(handle)
        except SpoolError:
            return None
        return _result_from_meta(audio, meta)

    def duration_seconds(self, job: dict[str, Any]) -> Optional[float]:
        result = self.result_for(job)
        return result.duration_seconds if result else None

    # ---------------------------------------------------------------- errors

    def _error_from_response(self, resp: Any) -> str:
        status = resp.status_code
        detail = ""
        try:
            body = resp.json()
            error = body.get("error") if isinstance(body, dict) else None
            detail = error.get("message") if isinstance(error, dict) else (
                str(error) if error else "")
        except ValueError:
            detail = ""
        detail = " ".join(str(detail or f"HTTP {status}").split())[:_MAX_ERROR_DETAIL]
        if status in (401, 403):
            return f"{self.provider} rejected the credential for speech synthesis ({detail})"
        if status == 402:
            return f"{self.provider} has no available credit or quota for speech: {detail}"
        if status == 429:
            return f"{self.provider} rate-limited the speech request: {detail}"
        return f"{self.provider} returned HTTP {status} for speech synthesis: {detail}"


def _result_meta(result: SpeechResult) -> dict[str, Any]:
    return {"model": result.model, "requested_model": result.requested_model,
            "format": result.format, "duration_seconds": result.duration_seconds,
            "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
            "audio_tokens": result.audio_tokens}


def _result_from_meta(audio: bytes, meta: dict[str, Any]) -> SpeechResult:
    return SpeechResult(
        audio=audio, model=str(meta.get("model") or ""),
        requested_model=str(meta.get("requested_model") or ""),
        format=str(meta.get("format") or "wav"), duration_seconds=meta.get("duration_seconds"),
        prompt_tokens=int(meta.get("prompt_tokens") or 0),
        completion_tokens=int(meta.get("completion_tokens") or 0),
        audio_tokens=int(meta.get("audio_tokens") or 0))
