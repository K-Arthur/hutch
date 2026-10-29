"""OpenAI Images adapter (``openai`` package, images.generate / images.edit).

**Protocol-verified, live-unverified.** Tests drive this adapter through the
OpenAI SDK with an injected fake ``httpx`` transport, no network. The first live
call against a real account may still surface drift (model names, size strings,
response shapes); every such failure is raised loudly and lands in the job ledger
as ``failed`` with the backend's own error, never as fabricated media.

The Images API is SYNCHRONOUS: ``images.generate`` returns the finished image in
the same call. There is no upstream job id, so this adapter treats the submit
call as accept+work in one step:

* ``submit`` performs the generation and caches the returned bytes in memory
  under a generated handle. THE PROVIDER CHARGE HAPPENS INSIDE submit().
* ``poll`` reports the cached state; ``fetch`` returns the cached bytes (or
  downloads a returned URL exactly once).
* If the process died between submit and fetch, the bytes are gone. Honest
  handling lives in ``media.jobs.reconcile``: the job is marked with an error
  that says the work may have been billed and the result was never fetched.
  There is deliberately NO silent re-generation, that would pay twice.
"""

from __future__ import annotations

import base64
import binascii
import secrets
from typing import Any, Optional

from .base import VERIFICATION_TAG

_SUPPORTED_SIZES = ("256x256", "512x512", "1024x1024", "1024x1792", "1792x1024")


class OpenAIImagesError(RuntimeError):
    """The backend refused or failed; carries the provider's own message."""


class OpenAIImagesBackend:
    """Adapter around ``openai.OpenAI().images``. ``http_client`` (an
    ``httpx.Client``) is injectable so tests can supply a fake transport."""

    name = "openai-images"

    def __init__(self, api_key: str, *, model: str = "gpt-image-1",
                 base_url: Optional[str] = None, http_client: Any = None,
                 timeout: float = 120.0):
        from openai import OpenAI
        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        if http_client is not None:
            kwargs["http_client"] = http_client
        self._client = OpenAI(**kwargs)
        self._model = model
        self._results: dict[str, tuple[Optional[bytes], Optional[str]]] = {}

    # ---------------------------------------------------------------- protocol

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "kinds": ["image"],
            "output_formats": {"image": ["png", "jpeg", "webp"]},
            "max_width": 1792,
            "max_height": 1792,
            "max_seconds": None,
            "editing": True,
            "partial_previews": False,
            "sizes": list(_SUPPORTED_SIZES),
            "verified": VERIFICATION_TAG,
            "note": "the Images API is synchronous; the provider charge happens "
                    "inside submit()",
        }

    def submit(self, req: dict[str, Any]) -> str:
        """Run the synchronous generation and cache the result bytes."""
        prompt = str(req.get("prompt") or "").strip()
        if not prompt:
            raise OpenAIImagesError("the request carries no prompt")
        size = self._size_for(req)
        try:
            response = self._client.images.generate(
                model=self._model, prompt=prompt, n=1, size=size,
                response_format="b64_json" if self._model != "gpt-image-1" else None,
            )
        except Exception as exc:  # SDK errors surface with their own text
            raise OpenAIImagesError(f"images.generate failed: {exc}") from exc
        items = list(getattr(response, "data", []) or [])
        if not items:
            raise OpenAIImagesError("images.generate returned no data")
        b64 = getattr(items[0], "b64_json", None)
        url = getattr(items[0], "url", None)
        image_bytes: Optional[bytes] = None
        if b64:
            try:
                image_bytes = base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise OpenAIImagesError(f"the returned image was not valid base64 ({exc})") from exc
        handle = f"oai_{secrets.token_hex(12)}"
        self._results[handle] = (image_bytes, url)
        return handle

    def poll(self, job: dict[str, Any]) -> dict[str, Any]:
        handle = str(job.get("upstream_job_id") or "")
        if handle not in self._results:
            return {"status": "failed",
                    "error": "this hutch process has no cached result for the upstream "
                             "job; the Images API is synchronous and the result cannot "
                             "be re-fetched without paying again"}
        image_bytes, url = self._results[handle]
        if image_bytes is None and url:
            return {"status": "succeeded", "note": "result is a URL; fetch consumes it"}
        return {"status": "succeeded"}

    def fetch(self, job: dict[str, Any]) -> bytes:
        handle = str(job.get("upstream_job_id") or "")
        if handle not in self._results:
            raise OpenAIImagesError(
                "no cached result for this upstream job; the Images API is synchronous "
                "and the result cannot be re-fetched without paying again")
        image_bytes, url = self._results[handle]
        if image_bytes is not None:
            return image_bytes
        if url:
            # Consume the expiring URL exactly once; the URL itself is NEVER the
            # stored result, only the bytes are.
            import httpx
            response = httpx.get(url, timeout=60.0,
                                 headers={"User-Agent": "hutch/0.1 media"})
            if response.status_code != 200:
                raise OpenAIImagesError(
                    f"the result URL returned HTTP {response.status_code}; the "
                    "expiring URL was consumed without usable bytes")
            return response.content
        raise OpenAIImagesError("the cached result holds neither bytes nor a URL")

    def cancel(self, job: dict[str, Any]) -> Optional[dict[str, Any]]:
        # A synchronous API has nothing left to cancel once submit returned; the
        # charge already happened. Reporting 'confirmed' would be a lie.
        return None

    def edit(self, image: bytes, prompt: str, *, size: Optional[str] = None) -> str:
        """images.edit (capability-flagged editing); same caching as submit."""
        if not prompt.strip():
            raise OpenAIImagesError("the edit carries no prompt")
        try:
            response = self._client.images.edit(
                model=self._model, image=image, prompt=prompt, n=1,
                size=size or "1024x1024",
            )
        except Exception as exc:
            raise OpenAIImagesError(f"images.edit failed: {exc}") from exc
        items = list(getattr(response, "data", []) or [])
        if not items or not getattr(items[0], "b64_json", None):
            raise OpenAIImagesError("images.edit returned no image data")
        handle = f"oai_{secrets.token_hex(12)}"
        self._results[handle] = (base64.b64decode(items[0]["b64_json"]), None)
        return handle

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _size_for(req: dict[str, Any]) -> str:
        width, height = req.get("width"), req.get("height")
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            landscape = width >= height
            if landscape:
                return "1792x1024" if width >= 1400 else "1024x1024"
            return "1024x1792" if height >= 1400 else "1024x1024"
        return "1024x1024"

    @classmethod
    def from_env(cls) -> Optional["OpenAIImagesBackend"]:
        """Build from OPENAI_API_KEY; None when unset; an adapter without a key
        must simply not exist, not fail later mid-job."""
        import os
        key = os.environ.get("OPENAI_API_KEY")
        return cls(api_key=key) if key else None
