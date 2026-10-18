"""ComfyUI adapter (httpx): prompt submit → history polling → /view fetch.

**Protocol-verified, live-unverified.** Tests drive this adapter against
``httpx.MockTransport`` — no network. The endpoint paths follow ComfyUI's public
HTTP API (``POST /prompt``, ``GET /history/{id}``, ``GET /view``,
``POST /interrupt``, ``POST /queue``); a live server may still differ, and any
such drift fails loudly into the job ledger, never into fabricated media.

The caller supplies the ComfyUI workflow graph itself (API-format JSON) in
``req["workflow"]`` — hutch does not synthesize node graphs, so what gets billed
is exactly what the caller asked for.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from .base import VERIFICATION_TAG


class ComfyUIError(RuntimeError):
    """The backend refused or failed; carries the provider's own message."""


class ComfyUIBackend:
    """Adapter to one ComfyUI instance. ``client`` (an ``httpx.Client``) is
    injectable so tests can supply ``httpx.MockTransport``."""

    name = "comfyui"

    def __init__(self, endpoint_url: str, *, client: Optional[Any] = None,
                 timeout: float = 30.0):
        self._endpoint = endpoint_url.rstrip("/")
        if client is not None:
            self._client = client
        else:
            import httpx
            self._client = httpx.Client(timeout=timeout,
                                        headers={"User-Agent": "hutch/0.1 media"})
        self._client_id = f"hutch-{secrets.token_hex(8)}"

    # ---------------------------------------------------------------- protocol

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "kinds": ["image", "video"],
            "output_formats": {"image": ["png", "jpeg", "webp"],
                               "video": ["webm", "mp4"]},
            "max_width": None,      # bounded by the workflow itself, not the API
            "max_height": None,
            "max_seconds": None,
            "editing": True,        # img2img workflows
            "partial_previews": True,   # sampling previews exist (not relayed here)
            "verified": VERIFICATION_TAG,
            "endpoint": self._endpoint,
            "note": "the caller supplies the workflow graph; hutch does not "
                    "synthesize node graphs",
        }

    def submit(self, req: dict[str, Any]) -> str:
        workflow = req.get("workflow")
        if not isinstance(workflow, dict) or not workflow:
            raise ComfyUIError("the request carries no ComfyUI workflow object")
        try:
            response = self._client.post(
                f"{self._endpoint}/prompt",
                json={"prompt": workflow, "client_id": self._client_id})
        except Exception as exc:
            raise ComfyUIError(f"prompt submit failed: {exc}") from exc
        if response.status_code != 200:
            raise ComfyUIError(
                f"prompt submit returned HTTP {response.status_code}: "
                f"{response.text[:300]}")
        payload = self._json(response)
        prompt_id = payload.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyUIError("prompt submit returned no prompt_id")
        return prompt_id

    def poll(self, job: dict[str, Any]) -> dict[str, Any]:
        prompt_id = str(job.get("upstream_job_id") or "")
        if not prompt_id:
            return {"status": "failed", "error": "this job has no ComfyUI prompt id"}
        try:
            response = self._client.get(f"{self._endpoint}/history/{prompt_id}")
        except Exception as exc:
            return {"status": "running", "error": f"history poll failed: {exc}"}
        if response.status_code == 404:
            # Unknown to the server: honest observation, not an invented state.
            return {"status": "failed",
                    "error": "the ComfyUI server has no history for this prompt id "
                             "(it may have been restarted and the queue lost)"}
        if response.status_code != 200:
            return {"status": "running",
                    "error": f"history poll returned HTTP {response.status_code}"}
        entry = self._json(response).get(prompt_id)
        if not isinstance(entry, dict):
            return {"status": "running"}
        status = entry.get("status") or {}
        outputs = entry.get("outputs") or {}
        if str(status.get("status_str", "")).lower() == "error":
            messages = status.get("messages") or []
            return {"status": "failed",
                    "error": f"the workflow reported an error: {str(messages)[:300]}"}
        if status.get("completed") or outputs:
            return {"status": "succeeded"}
        return {"status": "running", "progress": status.get("progress")}

    def fetch(self, job: dict[str, Any]) -> bytes:
        prompt_id = str(job.get("upstream_job_id") or "")
        history = self._client.get(f"{self._endpoint}/history/{prompt_id}")
        if history.status_code != 200:
            raise ComfyUIError(f"history fetch returned HTTP {history.status_code}")
        entry = self._json(history).get(prompt_id)
        outputs = (entry or {}).get("outputs") or {}
        for node_output in outputs.values():
            for image in node_output.get("images") or []:
                params = {"filename": image.get("filename"),
                          "subfolder": image.get("subfolder", ""),
                          "type": image.get("type", "output")}
                view = self._client.get(f"{self._endpoint}/view", params=params)
                if view.status_code != 200:
                    continue
                return view.content
        raise ComfyUIError("the workflow history holds no fetchable output file")

    def cancel(self, job: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Best-effort cancel: /interrupt for the running item, /queue delete for
        a queued one. Returns a confirmation ONLY on an explicit 2xx — otherwise
        None, which the job service turns into honest ``cancel_unconfirmed``."""
        prompt_id = str(job.get("upstream_job_id") or "")
        try:
            queued = self._client.post(f"{self._endpoint}/queue",
                                       json={"delete": [prompt_id]})
            if queued.status_code // 100 == 2:
                return {"cancelled": True, "how": "queue-delete"}
            interrupt = self._client.post(f"{self._endpoint}/interrupt")
            if interrupt.status_code // 100 == 2:
                return {"cancelled": True, "how": "interrupt"}
        except Exception:
            return None
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
    def from_env(cls) -> Optional["ComfyUIBackend"]:
        """Build from HUTCH_COMFYUI_URL; None when unset."""
        import os
        endpoint = os.environ.get("HUTCH_COMFYUI_URL")
        return cls(endpoint) if endpoint else None
