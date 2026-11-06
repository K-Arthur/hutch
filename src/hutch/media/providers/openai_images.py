"""OpenAI Images adapter (``openai`` package, images.generate / images.edit).

**Protocol-verified, live-unverified.** Tests drive this adapter through the OpenAI SDK with an
injected fake ``httpx`` transport, no network. The first live call against a real account may
still surface drift (model names, size strings, response shapes); every such failure is raised
loudly and lands in the job ledger as ``failed`` with the backend's own error, never as
fabricated media.

The Images API is SYNCHRONOUS: ``images.generate`` returns the finished image in the same call,
so the provider charge happens inside ``submit``. The result is therefore written to the durable
spool (:mod:`hutch.media.spool`) before ``submit`` returns. If the process dies before the media
store commits, the paid image is still on disk and the job can be finalized after a restart; there
is deliberately NO silent re-generation, which would pay twice.

Two defects this module used to have, both found in 2026-11 research (07-MEDIA-SPEECH-SEARCH.md):

* ``response_format`` was sent for every model except the exact string ``gpt-image-1``. GPT Image
  models reject it (``unknown_parameter``) on generations and edits; only DALL-E models take it.
  The parameter is now chosen by model family.
* the size table was DALL-E's (``1792x1024``) and GPT Image rejects those. Sizes are now chosen by
  model family.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Optional

from ..fetch import FetchError, download
from ..spool import MediaSpool, ResultHold, SpoolError
from .base import VERIFICATION_TAG, MediaRefused

_GPT_IMAGE_SIZES = ("1024x1024", "1536x1024", "1024x1536")
_DALLE_SIZES = ("1024x1024", "1792x1024", "1024x1792")
_REFUSAL_CODES = frozenset({"moderation_blocked", "content_policy_violation"})


class OpenAIImagesError(RuntimeError):
    """The backend refused or failed; carries the provider's own message."""


def takes_response_format(model: str) -> bool:
    """Only DALL-E models accept ``response_format``; every GPT Image model rejects it."""
    return str(model or "").lower().startswith("dall-e")


def sizes_for(model: str) -> tuple[str, ...]:
    return _DALLE_SIZES if takes_response_format(model) else _GPT_IMAGE_SIZES


def choose_size(model: str, width: Any, height: Any) -> str:
    """The closest supported size for the requested geometry, square when unspecified."""
    square, wide, tall = (sizes_for(model)[0], sizes_for(model)[1], sizes_for(model)[2])
    if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        return square
    ratio = width / height
    if ratio >= 1.2:
        return wide
    if ratio <= 1 / 1.2:
        return tall
    return square


def refusal_or_error(exc: Exception, action: str) -> Exception:
    """Map an SDK error to a refusal when OpenAI's own error code says the content was declined."""
    code = str(getattr(exc, "code", "") or "")
    body = getattr(exc, "body", None)
    if not code and isinstance(body, dict):
        code = str((body.get("error") or body).get("code") or "")
    if code in _REFUSAL_CODES:
        message = str(getattr(exc, "message", "") or exc)
        return MediaRefused(f"OpenAI declined the request ({code}): {message}")
    return OpenAIImagesError(f"{action} failed: {exc}")


class OpenAIImagesBackend:
    """Adapter around ``openai.OpenAI().images``. ``http_client`` (an ``httpx.Client``) is
    injectable so tests can supply a fake transport; ``spool`` makes results durable."""

    name = "openai-images"

    def __init__(self, api_key: str, *, model: str = "gpt-image-1-mini",
                 base_url: Optional[str] = None, http_client: Any = None,
                 timeout: float = 120.0, spool: Optional[MediaSpool] = None,
                 label: str = ""):
        from openai import OpenAI
        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url
        if http_client is not None:
            kwargs["http_client"] = http_client
        self._client = OpenAI(**kwargs)
        self._model = model
        self._hold = ResultHold(spool)
        self.credential_label = label

    # ---------------------------------------------------------------- protocol

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "kinds": ["image"],
            "output_formats": {"image": ["png", "jpeg", "webp"]},
            "max_width": 1536,
            "max_height": 1536,
            "max_seconds": None,
            "editing": True,
            "partial_previews": False,
            "sizes": list(sizes_for(self._model)),
            "model": self._model,
            "durable_results": self._hold.durable,
            "credential": self.credential_label,
            "verified": VERIFICATION_TAG,
            "note": "the Images API is synchronous; the provider charge happens inside submit(), "
                    "and the result is spooled to disk before submit returns",
        }

    def submit(self, req: dict[str, Any]) -> str:
        """Run the synchronous generation and spool the result. BILLABLE, once per job."""
        prompt = str(req.get("prompt") or "").strip()
        if not prompt:
            raise OpenAIImagesError("the request carries no prompt")
        kwargs: dict[str, Any] = {"model": self._model, "prompt": prompt, "n": 1,
                                  "size": choose_size(self._model, req.get("width"),
                                                      req.get("height"))}
        if takes_response_format(self._model):
            kwargs["response_format"] = "b64_json"
        try:
            response = self._client.images.generate(**kwargs)
        except Exception as exc:  # SDK errors surface with their own text
            raise refusal_or_error(exc, "images.generate") from exc
        return self._keep(response, "images.generate")

    def poll(self, job: dict[str, Any]) -> dict[str, Any]:
        handle = str(job.get("upstream_job_id") or "")
        if not self._hold.has(handle):
            return {"status": "failed",
                    "error": "no held result exists for this upstream job; the Images API is "
                             "synchronous and the result cannot be re-fetched without paying again"}
        return {"status": "succeeded"}

    def can_recover(self, job: dict[str, Any]) -> bool:
        return self._hold.durable and self._hold.has(str(job.get("upstream_job_id") or ""))

    def fetch(self, job: dict[str, Any]) -> bytes:
        handle = str(job.get("upstream_job_id") or "")
        if not self._hold.has(handle):
            raise OpenAIImagesError(
                "no held result for this upstream job; the Images API is synchronous and the "
                "result cannot be re-fetched without paying again")
        try:
            return self._hold.get(handle)
        except SpoolError as exc:
            raise OpenAIImagesError(f"the held result is unusable: {exc}") from exc

    def release(self, job: dict[str, Any]) -> None:
        handle = str(job.get("upstream_job_id") or "")
        if handle:
            self._hold.discard(handle)

    def cancel(self, job: dict[str, Any]) -> Optional[dict[str, Any]]:
        # A synchronous API has nothing left to cancel once submit returned; the charge already
        # happened. Reporting 'confirmed' would be a lie.
        return None

    def edit(self, image: bytes, prompt: str, *, size: Optional[str] = None) -> str:
        """images.edit (capability-flagged editing); same spooling as submit."""
        if not prompt.strip():
            raise OpenAIImagesError("the edit carries no prompt")
        kwargs: dict[str, Any] = {"model": self._model, "prompt": prompt, "n": 1,
                                  "image": ("image.png", image, "image/png"),
                                  "size": size or sizes_for(self._model)[0]}
        if takes_response_format(self._model):
            kwargs["response_format"] = "b64_json"
        try:
            response = self._client.images.edit(**kwargs)
        except Exception as exc:
            raise refusal_or_error(exc, "images.edit") from exc
        return self._keep(response, "images.edit")

    # ---------------------------------------------------------------- helpers

    def _keep(self, response: Any, action: str) -> str:
        items = list(getattr(response, "data", []) or [])
        if not items:
            raise OpenAIImagesError(f"{action} returned no data")
        data = self._decode(items[0])
        try:
            return self._hold.put(data, meta={"backend": self.name, "model": self._model})
        except SpoolError as exc:
            raise OpenAIImagesError(
                f"{action} succeeded but the result could not be held ({exc}); the provider "
                "may have billed this request") from exc

    @staticmethod
    def _decode(item: Any) -> bytes:
        b64, url = getattr(item, "b64_json", None), getattr(item, "url", None)
        if b64:
            try:
                return base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise OpenAIImagesError(f"the returned image was not valid base64 ({exc})") from exc
        if url:
            # Consume the expiring URL now; the URL itself is never the stored result.
            try:
                return download(url)
            except FetchError as exc:
                raise OpenAIImagesError(f"{exc}; the expiring URL was consumed without bytes") from exc
        raise OpenAIImagesError("the response holds neither image bytes nor a URL")

    @classmethod
    def from_env(cls, spool: Optional[MediaSpool] = None,
                 environ: Optional[Any] = None) -> Optional["OpenAIImagesBackend"]:
        """Build from OPENAI_API_KEY; None when unset; an adapter without a key must simply not
        exist, not fail later mid-job. The credential is labeled ambient in every approval."""
        import os
        key = (os.environ if environ is None else environ).get("OPENAI_API_KEY")
        return cls(api_key=key, spool=spool,
                   label="environment variable OPENAI_API_KEY (ambient)") if key else None
