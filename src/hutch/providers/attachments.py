"""Chat message image attachments: validation, capability gates, and wire parts.

User-attached images are **message content**, not computer observations, so the
existing ``observation_to_hosted`` gate keeps its scope; the runtime still records
what actually reached the model, per Hutch's honest-outcome rules.

Every check in this module touches only local workspace paths and in-memory rows —
never HTTP — so admission can run all of it without a network request. Model-level
vision checks that would need a live ``/api/show`` (Ollama) are deferred to the
runtime by passing ``verify_model=False`` at admission.

Layering: imported by the admission path (server), the builtin runtime, and tests.
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from typing import Any, Optional

from ..workspace.manager import workspace_dir_for

#: One message carries at most this many images (mirrors the inspect_media cap).
MAX_IMAGES_PER_MESSAGE = 4
#: Per-image byte ceiling before base64 (mirrors the frame path's 1.5 MB cap).
MAX_IMAGE_BYTES = 1_500_000
#: The upload intake's image kinds; a stored upload must be one of these.
IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})

_IMAGE_NAME_RE = re.compile(r"\.(png|jpe?g|webp)$", re.IGNORECASE)


class ImageAttachmentError(ValueError):
    """One attachment cannot be sent: the message must not go out without it."""


def is_image_upload(upload: Any) -> bool:
    """True for a stored upload (or a chat chip record) that is a sendable image.

    Older chips predate the ``mime`` field; fall back to the filename extension
    so a legacy image is still recognised rather than silently treated as text.
    """
    if not isinstance(upload, dict):
        return False
    mime = str(upload.get("mime") or "").lower()
    if mime:
        return mime in IMAGE_MIMES
    return bool(_IMAGE_NAME_RE.search(str(upload.get("filename") or "")))


def human_size(size: int) -> str:
    size = int(size)
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def image_limit_label() -> str:
    """The send-side image limit in decimal MB — file sizes shown on chips stay
    binary (existing behaviour), but limits read like the intake's “25 MB”."""
    return f"{MAX_IMAGE_BYTES / 1_000_000:.1f} MB"


def validate_image_rows(requested: list[str], rows: list[Optional[dict]], *,
                        conversation_id: str) -> tuple[list[dict], list[str]]:
    """Validate admission-time attachment references. Returns ``(rows, problems)``.

    ``rows`` is the parallel result of ``store.get_upload`` for each requested id
    (``None`` when the id is unknown). ``problems`` holds precise, user-facing
    reasons; a non-empty problem list means the message must not be admitted.
    """
    problems: list[str] = []
    if len(requested) > MAX_IMAGES_PER_MESSAGE:
        problems.append(f"a message can carry at most {MAX_IMAGES_PER_MESSAGE} images; "
                        f"{len(requested)} were attached")
    validated: list[dict] = []
    for upload_id, row in zip(requested, rows):
        if not isinstance(row, dict):
            problems.append(f"attached image {upload_id} is no longer available")
            continue
        if str(row.get("conversation_id") or "") != conversation_id:
            # Never let another chat's upload ride along with this message.
            problems.append(f"attached image {upload_id} belongs to another chat")
            continue
        filename = str(row.get("filename") or upload_id)
        state = str(row.get("state") or "")
        if state != "ready":
            problems.append(f"attached image {filename} is {state or 'not available'} and cannot be sent")
            continue
        if not is_image_upload(dict(row)):
            problems.append(f"{filename} is not a supported image (accepted: PNG, JPEG, WebP)")
            continue
        byte_size = int(row.get("byte_size") or 0)
        if byte_size > MAX_IMAGE_BYTES:
            problems.append(f"{filename} is too large to send as an image "
                            f"({human_size(byte_size)}; the limit is {image_limit_label()})")
            continue
        # The run's admission snapshot carries every field the runtime re-verifies
        # against disk, so the message does not depend on a later DB read.
        validated.append({"id": str(row.get("id") or upload_id),
                          "conversation_id": conversation_id,
                          "filename": filename,
                          "mime": str(row.get("mime") or ""),
                          "byte_size": byte_size,
                          "sha256": str(row.get("sha256") or ""),
                          "state": "ready"})
    return validated, problems


def image_route_refusal(provider: Any, model: str, *, verify_model: bool = True) -> Optional[str]:
    """Why this route cannot receive the attached images, or ``None`` when it can.

    Wire-level support (``supports_media_input``) is always checked.
    ``verify_model=False`` skips the per-model check for callers that must not
    make a network request (admission on Ollama routes queries ``/api/show``);
    the runtime re-checks with ``verify_model=True`` after the model is online.
    """
    if not getattr(provider, "supports_media_input", False):
        return "the selected model route cannot receive image input"
    if verify_model and not provider.supports_vision(model):
        return f"the model '{model}' does not accept image input"
    return None


def read_image_upload(state_dir: Any, conversation_id: str, row: dict) -> tuple[bytes, str]:
    """Verified bytes for one stored image upload: ``(data, mime)``.

    The stored name is found by its unique ``upl_<hex>`` prefix, so this never
    re-implements the intake's filename sanitisation. The recorded SHA-256 is
    re-verified before the bytes are used — a tampered file is a refusal, never
    a silently altered attachment.
    """
    upload_id = str(row.get("id") or "")
    if not upload_id:
        raise ImageAttachmentError("an attached image has no identifier; nothing was sent")
    if str(row.get("conversation_id") or "") != conversation_id:
        raise ImageAttachmentError(f"attached image {upload_id} belongs to another chat; nothing was sent")
    if str(row.get("state") or "") != "ready":
        raise ImageAttachmentError(f"attached image {row.get('filename') or upload_id} is "
                                   f"{row.get('state') or 'unavailable'}; nothing was sent")
    byte_size = int(row.get("byte_size") or 0)
    if byte_size > MAX_IMAGE_BYTES:
        raise ImageAttachmentError(f"attached image {row.get('filename') or upload_id} exceeds the "
                                   f"{image_limit_label()} image limit; nothing was sent")
    workspace = workspace_dir_for(state_dir, conversation_id)
    try:
        matches = [p for p in workspace.glob(f"{upload_id}-*") if p.is_file() and not p.is_symlink()]
    except OSError as exc:
        raise ImageAttachmentError(f"attached image {row.get('filename') or upload_id} could not be "
                                   f"read ({exc}); nothing was sent") from exc
    if len(matches) != 1:
        raise ImageAttachmentError(f"attached image {row.get('filename') or upload_id} is missing from this "
                                   "chat's workspace; nothing was sent")
    path = matches[0]
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ImageAttachmentError(f"attached image {row.get('filename') or upload_id} exceeds the "
                                   f"{image_limit_label()} image limit; nothing was sent")
    data = path.read_bytes()
    recorded = str(row.get("sha256") or "")
    if recorded and hashlib.sha256(data).hexdigest() != recorded:
        raise ImageAttachmentError(f"attached image {row.get('filename') or upload_id} does not match its "
                                   "recorded digest; nothing was sent")
    return data, str(row.get("mime") or "")


def chat_image_parts(rows: list[dict], *, state_dir: Any, conversation_id: str) -> tuple[list[dict], list[str]]:
    """OpenAI-shaped content parts for the message's images, or precise problems.

    Each image is preceded by a short text label so a model can tell files apart
    and an image-only message still carries a text part. Any read/verification
    problem is returned instead of a partial part list: a message never goes out
    missing an image the composer still shows.
    """
    parts: list[dict[str, Any]] = []
    problems: list[str] = []
    for row in rows:
        filename = str(row.get("filename") or "image")
        try:
            data, mime = read_image_upload(state_dir, conversation_id, row)
        except ImageAttachmentError as exc:
            problems.append(str(exc))
            continue
        if not mime or mime not in IMAGE_MIMES:
            problems.append(f"{filename} is not a supported image (accepted: PNG, JPEG, WebP); nothing was sent")
            continue
        parts.append({"type": "text", "text": f"Image: {filename}"})
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}})
    return parts, problems
