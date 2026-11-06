"""Ollama additions kept out of providers/ollama.py (a frozen file): measured residency, installing and removing models,
and a repair for reasoning the runtime fails to separate from the answer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Optional

from .base import ProviderError


def split_leaked_reasoning(content: str, thinking: str) -> tuple[str, str]:
    """Move reasoning the runtime failed to separate out of the answer.

    Ollama 0.40.13 with a thinking-capable model (qwen3) and ``think: false`` returns the
    model's whole reasoning inside ``message.content``, terminated by a literal
    ``</think>``, with no ``thinking`` field at all. Left alone, that reasoning becomes the
    answer: the person reads raw chain-of-thought and a stray tag, and the transcript
    records it as assistant output.

    Only the unambiguous shape is repaired - a ``</think>`` marker with real text after it,
    and no ``thinking`` already reported. Anything else is left exactly as the runtime sent
    it, because guessing where reasoning ends in free text would corrupt genuine answers.
    """
    if thinking or "</think>" not in content:
        return content, thinking
    head, _, tail = content.rpartition("</think>")
    if not tail.strip():
        return content, thinking        # nothing after the marker: not the shape we can repair
    return tail.lstrip().lstrip("\n"), (head + "</think>").strip()


class OllamaExtras:
    """Mixed into OllamaProvider. Uses its `_http`, `_timeout`, `_error_from_response` and `ps`."""

    def measured_fields(self, model: str) -> dict[str, Optional[int]]:
        """ModelMeta keyword arguments for a model that happens to be resident; None where the runtime reports nothing.

        `/api/ps` is the only honest source for "which window is really in effect" and "is it on the GPU": `size_vram == 0` means
        the whole model is on the CPU, which no arithmetic here can supply.
        """
        live = self.residency(model) or {}
        applied, vram, resident = live.get("context_length"), live.get("size_vram"), live.get("size")
        return {"applied_context": int(applied) if isinstance(applied, (int, float)) and applied > 0 else None,
                "vram_bytes": int(vram) if isinstance(vram, (int, float)) else None,
                "resident_bytes": int(resident) if isinstance(resident, (int, float)) else None}

    def residency(self, model: str) -> Optional[dict[str, Any]]:
        """What the runtime reports about a *loaded* model, or None when it is not resident.

        ``size_vram`` is the only honest answer to "is this on the GPU?"; ``context_length``
        is the window actually in effect, which need not be the one that was requested.
        """
        for m in self.ps():
            if m.get("name") == model or m.get("model") == model:
                return m
        return None

    # ------------------------------------------------------- model lifecycle

    def pull_events(self, model: str, *, should_stop=None) -> Iterator[dict[str, Any]]:
        """Stream ``/api/pull`` progress events. Leaving early aborts the download.

        The runtime verifies each blob against its digest itself and keeps verified blobs,
        so an interrupted or cancelled pull resumes instead of restarting; nothing here
        re-implements resume. Cancellation takes effect at the next progress event, which
        the runtime emits continuously while a blob is moving.
        """
        from .ollama import _httpx
        h = _httpx()
        timeout = h.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)
        with self._http().stream("POST", "/api/pull", json={"model": model, "stream": True},
                                 timeout=timeout) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise self._error_from_response(resp, model)
            for line in resp.iter_lines():
                if should_stop is not None and should_stop():
                    return
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    yield event

    def delete_model(self, model: str) -> None:
        """Remove a model from this runtime (``DELETE /api/delete``)."""
        r = self._http().request("DELETE", "/api/delete", json={"model": model},
                                 timeout=self._timeout(read=60.0))
        if r.status_code == 404:
            raise ProviderError("model_missing", f"{model} is not installed", provider=self.name, status=404)
        if r.status_code >= 400:
            raise self._error_from_response(r, model)

    # ------------------------------------------------------- blob / create (import)

    def blob_exists(self, digest: str) -> bool:
        """Whether the runtime already has a blob, so import does not upload it twice."""
        r = self._http().request("HEAD", f"/api/blobs/{digest}", timeout=self._timeout(read=30.0))
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
        raise self._error_from_response(r, digest)

    def put_blob(self, digest: str, path: Path) -> None:
        """Upload one file as a content-addressed blob; the runtime verifies the digest."""
        size = path.stat().st_size

        def chunks() -> Iterator[bytes]:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(4 * 1024 * 1024)
                    if not chunk:
                        return
                    yield chunk

        r = self._http().post(
            f"/api/blobs/{digest}", content=chunks(),
            headers={"Content-Type": "application/octet-stream", "Content-Length": str(size)},
            timeout=self._timeout(read=900.0))
        if r.status_code not in (200, 201):
            raise self._error_from_response(r, path.name)

    def create_model(self, model: str, files: dict[str, str], *, license_text: str = "",
                     parameters: Optional[dict[str, Any]] = None) -> Iterator[dict[str, Any]]:
        """Stream ``/api/create`` for a model made from already-uploaded blobs."""
        payload: dict[str, Any] = {"model": model, "files": files, "stream": True}
        if license_text:
            payload["license"] = license_text
        if parameters:
            payload["parameters"] = parameters
        yield from self._stream_events("/api/create", payload, read=900.0)

    def _stream_events(self, path: str, payload: dict[str, Any], *, read: float) -> Iterator[dict[str, Any]]:
        from .ollama import _httpx
        h = _httpx()
        timeout = h.Timeout(connect=10.0, read=read, write=900.0, pool=5.0)
        with self._http().stream("POST", path, json=payload, timeout=timeout) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", "replace")
                raise ProviderError("http", f"{path} returned HTTP {resp.status_code}: {body[:300]}",
                                    provider=self.name, status=resp.status_code)
            for line in resp.iter_lines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    yield event
