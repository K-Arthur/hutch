"""ComfyUI adapter (httpx): prompt submit, history polling, /view fetch, queue-aware cancel.

**Protocol-verified, live-unverified.** Tests drive this adapter against ``httpx.MockTransport``
and a stand-in server; no real ComfyUI was available. The endpoint paths follow ComfyUI's public
HTTP API (``POST /prompt``, ``GET /history/{id}``, ``GET /view``, ``GET /queue``,
``POST /queue``, ``POST /interrupt``); a live server may still differ, and any such drift fails
loudly into the job ledger, never into fabricated media.

The caller supplies the ComfyUI workflow graph itself (API-format JSON) in ``req["workflow"]``:
hutch does not synthesize node graphs, so what gets billed is exactly what the caller asked for.

Changes made in 2026-11 after reading ComfyUI issues #2566 and #7513 and the OpenClaw page:

* **Cancel is queue-aware.** ``POST /queue {"delete": [id]}`` answers 200 for an id that is not
  pending, so a 200 proves nothing. The adapter reads ``GET /queue`` first: a pending prompt is
  deleted and the queue re-read to confirm; a running prompt is interrupted (a body-less
  ``/interrupt`` stops whatever runs, so it is sent only after the queue shows OUR prompt is the
  one running) and the queue re-read; a prompt in neither list is not cancelled. Confirmation is
  returned only when the re-read shows it gone.
* **Outputs are found in every list** a node writes (``images``, ``gifs``, ``videos``, ``audio``),
  so a video workflow's file is no longer invisible.
* **Downloads are bounded** and the client goes through the address-pinning transport.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from ..fetch import FetchError, read_bounded
from ..storage import MAX_MEDIA_BYTES
from .base import VERIFICATION_TAG

_OUTPUT_LISTS = ("videos", "gifs", "images", "audio")
_PREFERRED = {"video": (".mp4", ".webm"), "image": (".png", ".jpg", ".jpeg", ".webp")}


class ComfyUIError(RuntimeError):
    """The backend refused or failed; carries the provider's own message."""


class ComfyUIBackend:
    """Adapter to one ComfyUI instance. ``client`` (an ``httpx.Client``) is injectable so
    tests can supply ``httpx.MockTransport``."""

    name = "comfyui"

    def __init__(self, endpoint_url: str, *, client: Optional[Any] = None, timeout: float = 30.0):
        self._endpoint = endpoint_url.rstrip("/")
        self._owned = client is None
        self._client = client if client is not None else self._pinned_client(timeout)
        self._client_id = f"hutch-{secrets.token_hex(8)}"

    def _pinned_client(self, timeout: float) -> Any:
        import httpx

        from ...offline import httpx_offline_options

        base, transport, trust_env = httpx_offline_options(self._endpoint, "comfyui")
        return httpx.Client(base_url=base, transport=transport, trust_env=trust_env,
                            timeout=timeout, headers={"User-Agent": "hutch/0.1 media"})

    def _url(self, path: str) -> str:
        return path if self._owned else f"{self._endpoint}{path}"

    # ---------------------------------------------------------------- protocol

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "kinds": ["image", "video"],
            "output_formats": {"image": ["png", "jpeg", "webp"], "video": ["webm", "mp4"]},
            "max_width": None,      # bounded by the workflow itself, not the API
            "max_height": None,
            "max_seconds": None,
            "editing": True,        # img2img workflows
            "partial_previews": True,   # sampling previews exist (not relayed here)
            "verified": VERIFICATION_TAG,
            "endpoint": self._endpoint,
            "credential": "none (a local or self-hosted server)",
            "note": "the caller supplies the workflow graph; hutch does not "
                    "synthesize node graphs",
        }

    def submit(self, req: dict[str, Any]) -> str:
        workflow = req.get("workflow")
        if not isinstance(workflow, dict) or not workflow:
            raise ComfyUIError("the request carries no ComfyUI workflow object")
        try:
            response = self._client.post(
                self._url("/prompt"), json={"prompt": workflow, "client_id": self._client_id})
        except Exception as exc:
            raise ComfyUIError(f"prompt submit failed: {exc}") from exc
        if response.status_code != 200:
            raise ComfyUIError(
                f"prompt submit returned HTTP {response.status_code}: {response.text[:300]}")
        prompt_id = self._json(response).get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyUIError("prompt submit returned no prompt_id")
        return prompt_id

    def poll(self, job: dict[str, Any]) -> dict[str, Any]:
        prompt_id = str(job.get("upstream_job_id") or "")
        if not prompt_id:
            return {"status": "failed", "error": "this job has no ComfyUI prompt id"}
        try:
            response = self._client.get(self._url(f"/history/{prompt_id}"))
        except Exception as exc:
            return {"status": "running", "note": f"history poll failed: {exc}"}
        if response.status_code == 404:
            # Unknown to the server: honest observation, not an invented state.
            return {"status": "failed",
                    "error": "the ComfyUI server has no history for this prompt id "
                             "(it may have been restarted and the queue lost)"}
        if response.status_code != 200:
            return {"status": "running", "note": f"history poll returned HTTP {response.status_code}"}
        entry = self._json(response).get(prompt_id)
        if not isinstance(entry, dict):
            return {"status": "running"}
        status = entry.get("status") or {}
        if str(status.get("status_str", "")).lower() == "error":
            messages = str(status.get("messages") or [])[:300]
            return {"status": "failed", "error": f"the workflow reported an error: {messages}"}
        if status.get("completed") or entry.get("outputs"):
            return {"status": "succeeded"}
        return {"status": "running", "progress": status.get("progress")}

    def fetch(self, job: dict[str, Any]) -> bytes:
        prompt_id = str(job.get("upstream_job_id") or "")
        history = self._client.get(self._url(f"/history/{prompt_id}"))
        if history.status_code != 200:
            raise ComfyUIError(f"history fetch returned HTTP {history.status_code}")
        entry = self._json(history).get(prompt_id) or {}
        for item in self._files(entry.get("outputs") or {}, str(job.get("kind") or "image")):
            data = self._view(item)
            if data:
                return data
        raise ComfyUIError("the workflow history holds no fetchable output file")

    # ---------------------------------------------------------------- outputs

    @staticmethod
    def _files(outputs: dict[str, Any], wanted: str) -> list[dict[str, Any]]:
        """Every output file, the wanted kind first and permanent files before temporary ones."""
        found = [f for node in outputs.values() if isinstance(node, dict)
                 for key in _OUTPUT_LISTS for f in node.get(key) or [] if isinstance(f, dict)]
        exts = _PREFERRED.get(wanted, ())

        def rank(item: dict[str, Any]) -> tuple[int, int]:
            name = str(item.get("filename", "")).lower()
            return (0 if name.endswith(exts) else 1, 1 if item.get("type") == "temp" else 0)

        return sorted(found, key=rank)

    def _view(self, item: dict[str, Any]) -> Optional[bytes]:
        params = {"filename": item.get("filename"), "subfolder": item.get("subfolder", ""),
                  "type": item.get("type", "output")}
        try:
            with self._client.stream("GET", self._url("/view"), params=params) as response:
                if response.status_code != 200:
                    return None
                return read_bounded(response, MAX_MEDIA_BYTES)
        except FetchError as exc:
            raise ComfyUIError(f"the output file was refused: {exc}") from exc

    # ---------------------------------------------------------------- cancel

    def cancel(self, job: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Cancel only what the queue shows is ours, and confirm only by reading the queue again.

        Returns a confirmation when the re-read shows the prompt gone; otherwise None, which the
        job service turns into the honest ``cancel_unconfirmed``."""
        prompt_id = str(job.get("upstream_job_id") or "")
        try:
            where = self._where(prompt_id)
            if where == "pending":
                self._client.post(self._url("/queue"), json={"delete": [prompt_id]})
                how = "queue-delete"
            elif where == "running":
                self._client.post(self._url("/interrupt"), json={"prompt_id": prompt_id})
                how = "interrupt"
            else:
                return None
            return {"cancelled": True, "how": how} if self._where(prompt_id) is None else None
        except Exception:
            return None

    def _where(self, prompt_id: str) -> Optional[str]:
        """``pending``, ``running`` or None, read from ``GET /queue``; raises when unreadable."""
        response = self._client.get(self._url("/queue"))
        if response.status_code != 200:
            raise ComfyUIError(f"queue read returned HTTP {response.status_code}")
        queue = self._json(response)
        for label, key in (("running", "queue_running"), ("pending", "queue_pending")):
            if any(isinstance(row, (list, tuple)) and len(row) > 1 and row[1] == prompt_id
                   for row in queue.get(key) or []):
                return label
        return None

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _json(response: Any) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise ComfyUIError(f"the server returned non-JSON content ({exc})") from exc
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def from_env(cls, environ: Optional[Any] = None) -> Optional["ComfyUIBackend"]:
        """Build from HUTCH_COMFYUI_URL; None when unset."""
        import os
        endpoint = (os.environ if environ is None else environ).get("HUTCH_COMFYUI_URL")
        return cls(endpoint) if endpoint else None
