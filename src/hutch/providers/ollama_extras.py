"""Ollama additions kept out of providers/ollama.py (a frozen file): measured residency, installing and removing models,
and a repair for reasoning the runtime fails to separate from the answer.
"""

from __future__ import annotations

import json
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
