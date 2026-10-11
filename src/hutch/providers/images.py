"""Turn tool-result image references into what a model route can actually receive.

Internal convention: a tool message may carry ``images``, a list of ``ImageRef.internal()`` dicts. That key must never reach a
provider (several providers send ``messages`` verbatim), so ``prepare_messages`` is applied exactly once, right before a
``ChatRequest`` is built, and returns a *copy* in which:

* every ``images`` key is removed;
* the newest ``keep_latest`` frames are delivered, as an OpenAI-shaped ``image_url`` data-URI part in a user message placed
  directly after the contiguous tool-result block (tool messages must stay adjacent to the assistant call that produced
  them), and only when the route's model really accepts images (``vision``);
* every other frame is replaced by an explicit text note, so a model is told that a frame existed and why it is not
  present, instead of silently losing it.

Frames are re-read from disk and verified for each request, so the persistent message list never holds image bytes and the
context cannot grow with the number of screenshots. Provider adapters translate the OpenAI-shaped part to their wire format
(``providers/claude.py``, ``providers/ollama.py``); a route that cannot do so reports ``supports_vision() == False``.
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from ..computer.frames import FrameError, FrameStore, ImageRef

DEFAULT_KEEP_LATEST = 1
MAX_PAYLOAD_BYTES = 3_000_000       # base64 characters of images in one request


def _refs(message: dict[str, Any]) -> list[ImageRef]:
    refs: list[ImageRef] = []
    for item in message.get("images") or ():
        try:
            refs.append(ImageRef.from_internal(item))
        except FrameError:
            continue
    return refs


def has_images(messages: list[dict[str, Any]]) -> bool:
    return any(m.get("images") for m in messages)


def prepare_messages(messages: list[dict[str, Any]], *, vision: bool, frames: Optional[FrameStore],
                     keep_latest: int = DEFAULT_KEEP_LATEST,
                     max_payload_bytes: int = MAX_PAYLOAD_BYTES) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return ``(messages_for_the_provider, report)``. ``messages`` is never modified.

    ``report`` is ``{"delivered": [frame ids], "omitted": [{"frame_id", "reason"}]}`` for run events and tests.
    """
    report: dict[str, Any] = {"delivered": [], "omitted": []}
    if not has_images(messages):
        return messages, report

    ordered: list[ImageRef] = [ref for m in messages for ref in _refs(m)]
    live_ids = {ref.frame_id for ref in ordered[-max(keep_latest, 0):]} if keep_latest > 0 else set()

    out: list[dict[str, Any]] = []
    pending: list[tuple[ImageRef, str]] = []        # frames to attach after the current tool-result block
    payload = 0

    def flush() -> None:
        if not pending:
            return
        parts: list[dict[str, Any]] = [{"type": "text", "text": "Observation image from the tool call above "
                                        "(the most recent frame; earlier frames are not repeated):"}]
        for ref, b64 in pending:
            parts.append({"type": "image_url", "image_url": {"url": f"data:{ref.media_type};base64,{b64}"}})
        out.append({"role": "user", "content": parts})
        pending.clear()

    for message in messages:
        if message.get("role") != "tool":
            flush()
        refs = _refs(message)
        if not refs and "images" not in message:
            out.append(message)
            continue
        notes: list[str] = []
        for ref in refs:
            if ref.frame_id not in live_ids:
                notes.append(f"[frame {ref.frame_id} omitted: superseded by a newer observation]")
                report["omitted"].append({"frame_id": ref.frame_id, "reason": "superseded"})
            elif not vision:
                notes.append(f"[frame {ref.frame_id} not delivered: the selected model cannot receive images; use the "
                             "text observation or semantic browser actions]")
                report["omitted"].append({"frame_id": ref.frame_id, "reason": "model_has_no_vision"})
            elif frames is None:
                notes.append(f"[frame {ref.frame_id} unavailable: no frame store for this run]")
                report["omitted"].append({"frame_id": ref.frame_id, "reason": "no_store"})
            else:
                try:
                    data = frames.load(ref)
                except FrameError as exc:
                    notes.append(f"[frame {ref.frame_id} unavailable: {exc}]")
                    report["omitted"].append({"frame_id": ref.frame_id, "reason": "unavailable"})
                    continue
                b64 = base64.b64encode(data).decode("ascii")
                if payload + len(b64) > max_payload_bytes:
                    notes.append(f"[frame {ref.frame_id} omitted: the request image budget was reached]")
                    report["omitted"].append({"frame_id": ref.frame_id, "reason": "payload_budget"})
                    continue
                payload += len(b64)
                pending.append((ref, b64))
                report["delivered"].append(ref.frame_id)
                notes.append(f"[frame {ref.frame_id} attached: {ref.width}x{ref.height}]")
        clean = {k: v for k, v in message.items() if k != "images"}
        if notes:
            base = str(clean.get("content") or "")
            clean["content"] = (base + "\n" if base else "") + "\n".join(notes)
        out.append(clean)
    flush()
    return out, report
