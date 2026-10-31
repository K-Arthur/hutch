"""Provider-backed media creation, split out of ``tools/media.py``.

``tools/media.py`` is a frozen over-cap module: new behaviour moves into a sibling rather
than growing it. This module owns the billable provider path (image, video and speech), the
backend discovery that feeds it, and the shared media-job helpers the deterministic tools
also use.

Trust story unchanged from the tool it serves: ``create_media`` is OUTWARD and billable for
provider kinds, ``effect()`` is ``"web"``, the approval decision is ask-by-default with
``outward=True`` (sticky grants never cover it, SR-4), and ``ctx.begin_effect()`` brackets
the call. If no backend is configured/capable the caller is told so honestly; nothing is
substituted or fabricated.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from ..media import (MediaJobError, MediaJobService, MediaStorage, MediaUnavailableError,
                     service_status)
from ..media.providers.base import MediaBackend
from ..outputblocks import new_block_id, parse_blocks
from ..safety import Decision, Verdict
from .base import ToolContext, ToolResult, rehearsed

_MEDIA_BACKENDS: Optional[dict[str, MediaBackend]] = None

CREATE_MEDIA_DECISION = Decision(
    verdict=Verdict.ask,
    reason="generating media calls a paid external service and sends the prompt to it",
    sticky_key="",            # outward: never sticky (SR-4)
    rule="media:create",
    risk="medium",
    outward=True,
)


# ------------------------------------------------------------------ backends


def default_backends() -> dict[str, MediaBackend]:
    """Discover configured backends from the environment. An adapter without its
    credentials simply does not exist here, tools then report honest absence."""
    global _MEDIA_BACKENDS
    if _MEDIA_BACKENDS is None:
        from ..media.providers.comfyui import ComfyUIBackend
        from ..media.providers.openai_images import OpenAIImagesBackend
        found: dict[str, MediaBackend] = {}
        openai_backend = OpenAIImagesBackend.from_env()
        if openai_backend is not None:
            found[openai_backend.name] = openai_backend
        comfyui = ComfyUIBackend.from_env()
        if comfyui is not None:
            found[comfyui.name] = comfyui
        _MEDIA_BACKENDS = found
    return _MEDIA_BACKENDS


def speech_backends(ctx: ToolContext) -> dict[str, MediaBackend]:
    """Configured connections that declare a ``speech`` route, keyed by backend name.

    Built per call rather than cached: the state directory and its keys are runtime data,
    while ``default_backends`` caches environment-only discovery. A connection without a
    key simply does not become a backend; absence is then reported honestly, never
    replaced by another account.
    """
    from ..connections import ConnectionBook
    from ..media.providers.speech import SpeechBackend, route_from_template

    book = ConnectionBook(ctx.config.state_dir)
    templates = book.templates()
    found: dict[str, MediaBackend] = {}
    for name, conn in sorted(book.configured().items()):
        try:
            route = route_from_template(templates.get(conn.template))
        except ValueError:
            continue          # a malformed template is Hutch's bug; it is not a backend
        if route is None:
            continue
        key = book.key(name)
        if not key:
            continue
        backend = SpeechBackend(
            connection=name, base_url=conn.base_url, api_key=key, route=route,
            provider=provider_identity(conn), billing=conn.billing,
            headers={"User-Agent": conn.user_agent, **conn.headers})
        found[backend.name] = backend
    return found


def provider_identity(conn) -> str:
    from ..providers.catalog import bundled_catalog

    entry = bundled_catalog().provider_for_template(conn.template)
    return entry.id if entry is not None else conn.name


# ------------------------------------------------------------------ helpers


def service_for(ctx: ToolContext,
                backends: Optional[dict[str, MediaBackend]] = None) -> MediaJobService:
    return MediaJobService(ctx.store, MediaStorage(ctx.config), backends=backends)


def media_idempotency_key(ctx: ToolContext, scope: str, canonical: Any) -> str:
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"{scope}:{ctx.run.id}:{digest[:32]}"


def check_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Belt and braces: blocks leaving a tool must survive the contract's own
    parser. Any error entry here means the tool misbuilt a block."""
    _, errors = parse_blocks(blocks)
    return errors


# ------------------------------------------------------------------ provider path


def run_provider_media(*, ctx: ToolContext, tool_name: str, kind: str, prompt: str,
                       width: Any, height: Any, seconds: Any, backend_hint: Any,
                       voice: Any = None, style: Any = None,
                       backends: Optional[dict[str, MediaBackend]] = None,
                       poll_interval: float = 2.0, max_polls: int = 45) -> ToolResult:
    """Submit one provider media job through the governed ledger, poll, and store the result."""
    if ctx.dry_run:
        return rehearsed(f"create {kind} media from your prompt via a provider",
                         CREATE_MEDIA_DECISION)
    if backends is not None:
        selected = backends
    else:
        selected = dict(default_backends())
        if kind == "audio":
            selected.update(speech_backends(ctx))
    service = service_for(ctx, backends=selected)
    try:
        backend = service.backend_for(kind, str(backend_hint) if backend_hint else None)
    except (MediaUnavailableError, MediaJobError) as exc:
        return ToolResult(ok=False, output=(
            f"error: {exc}. hutch does not substitute stock assets or fabricate "
            "previews — configure a media backend to enable this kind."))
    clean_kwargs: dict[str, Any] = {}
    if kind != "audio":
        if isinstance(width, int):
            clean_kwargs["width"] = width
        if isinstance(height, int):
            clean_kwargs["height"] = height
        if isinstance(seconds, (int, float)):
            clean_kwargs["seconds"] = seconds
    requested_extra: Optional[dict[str, Any]] = None
    clean_voice, clean_style = "", ""
    if kind == "audio":
        clean_voice = str(voice or "").strip()
        offered = backend.capabilities().get("voices") or []
        if clean_voice and clean_voice not in offered:
            return ToolResult(ok=False, output=(
                f"error: voice {clean_voice!r} is not offered by {backend.name} "
                f"(voices: {', '.join(offered) or 'none declared'})"))
        if style is not None and not isinstance(style, str):
            return ToolResult(ok=False, output="error: style must be a string")
        clean_style = " ".join(str(style or "").split())
        if len(clean_style) > 2000:
            return ToolResult(ok=False, output=(
                "error: the style instruction is longer than 2000 characters"))
        requested_extra = {"voice": clean_voice or str(
            backend.capabilities().get("default_voice") or ""), "style": clean_style}
    detail = {"kind": kind, "backend": backend.name, "prompt_chars": len(prompt),
              "note": "provider charges apply; hutch cannot know the cost"}
    describe = getattr(backend, "approval_detail", None)
    if callable(describe):
        detail.update(describe({"prompt": prompt, "voice": clean_voice,
                                "style": clean_style}))
    action = (f"speak {len(prompt)} characters via {backend.name}" if kind == "audio"
              else f"create {kind} media via {backend.name}")
    try:
        ctx.gate.decide("audio_synthesis" if kind == "audio" else "media", action,
                        detail, CREATE_MEDIA_DECISION)
    except Exception as exc:
        return ToolResult(ok=False, output=f"error: {exc}")
    refusal = ctx.begin_effect()
    if refusal:
        return ToolResult(ok=False, output=f"error: the request was not started ({refusal})")
    key = media_idempotency_key(ctx, "create-media",
                                {"kind": kind, "prompt": prompt, **clean_kwargs,
                                 **(requested_extra or {})})
    try:
        row = service.submit(run_id=ctx.run.id, conversation_id=ctx.run.conversation_id,
                             kind=kind, prompt=prompt, idempotency_key=key,
                             backend_hint=backend.name, requested_extra=requested_extra,
                             **clean_kwargs)
    except MediaJobError as exc:
        return ToolResult(ok=False, output=(
            f"error: the media job could not be submitted ({exc}). Nothing new was "
            "billed by this call; a previous submission with the same content may "
            "already exist — check the media job ledger."))
    service_status_value = service_status(row)
    if service_status_value == "submitting":
        return ToolResult(ok=False, output=(
            f"error: the job ({row['id']}) never reached the backend; "
            f"{row.get('error') or 'the submission failed'} — see the media job ledger"))
    polls = 0
    upstream_succeeded = False
    while polls < max_polls:
        observed = str(backend.poll(row).get("status", "running"))
        row = service.poll(row["id"], backend)   # records failed/cancelled honestly
        service_status_value = service_status(row)
        polls += 1
        if observed == "succeeded":
            upstream_succeeded = True
            break
        if service_status_value != "running":
            break
        time.sleep(poll_interval)
    if not upstream_succeeded and service_status_value == "running":
        return ToolResult(ok=False, output=(
            f"the media job {row['id']} is still running upstream after "
            f"{polls} checks; it is recorded in the ledger and may complete and "
            "bill — check its status or cancel it explicitly"))
    if service_status_value == "failed":
        return ToolResult(ok=False, output=(
            f"error: the media job {row['id']} failed upstream "
            f"({row.get('error') or 'unknown reason'}); no media was stored. "
            "Whether the provider charged for the attempt depends on the backend."))
    if service_status_value == "cancel_unconfirmed":
        return ToolResult(ok=False, output=(
            f"error: the media job {row['id']} was asked to cancel but the backend "
            "never confirmed; it may still be running and billing — verify with the "
            "backend. This is recorded honestly in the ledger."))
    if kind == "audio":
        alt_text = f"Speech: {prompt[:200]}"[:600]
    else:
        alt_text = f"Generated {kind} from the prompt: {prompt[:400]}"[:600]
    duration = None
    usage_note = ""
    if kind == "audio":
        probe = getattr(backend, "duration_seconds", None)
        if callable(probe):
            duration = probe(row)
    try:
        payload, final_row = service.finalize(row["id"], alt_text=alt_text,
                                              duration_seconds=duration)
    except MediaJobError as exc:
        return ToolResult(ok=False, output=(
            f"error: the finished media could not be stored ({exc}); the provider "
            "charge may stand"))
    if kind == "audio":
        result_for = getattr(backend, "result_for", None)
        spoken = result_for(row) if callable(result_for) else None
        if spoken is not None:
            try:
                ctx.store.add_usage(
                    ctx.run.id, ctx.bot.id,
                    str(getattr(backend, "provider", backend.name)), spoken.model,
                    spoken.prompt_tokens, spoken.completion_tokens, 0, 0.0,
                    kind="speech", account_id=str(getattr(backend, "connection", "")),
                    cost_source="unpriced")
                ctx.run.prompt_tokens += spoken.prompt_tokens
                ctx.run.completion_tokens += spoken.completion_tokens
                ctx.store.update_run(ctx.run)
                usage_note = (f"; {spoken.prompt_tokens} prompt / "
                              f"{spoken.completion_tokens} completion tokens recorded")
            except Exception as exc:  # noqa: BLE001 - the audio is real and must be returned
                usage_note = f"; usage could not be recorded in the run ledger: {exc}"
    media_block = {
        "v": 1, "id": new_block_id(), "kind": "media", "revision": 1,
        "availability": "ready",
        "text_fallback": (f"Speech: {prompt[:400]}" if kind == "audio"
                          else f"Generated {kind}: {alt_text[:400]}"),
        "provenance": {"run_id": ctx.run.id, "tool": tool_name,
                       "job_id": final_row.get("id", row["id"])},
        "payload": payload,
    }
    errors = check_blocks([media_block])
    warnings = ""
    data: dict[str, Any] = {"media": payload, "job_id": final_row.get("id", row["id"]),
                            "content_url": (f"/api/v1/media/{payload['media_id']}"
                                            f"/versions/{payload['version']}/content")}
    if errors:
        warnings = (" (the block failed its own validation: "
                    + "; ".join(e.get("error", "?") for e in errors)[:300] + ")")
    else:
        data["blocks"] = [media_block]
    return ToolResult(
        ok=True,
        output=(f"created {kind} media via {backend.name} "
                f"({payload['mime']}, sha256 {payload['sha256'][:16]}…); media "
                f"{payload['media_id']} v{payload['version']} is stored and "
                f"verifiable{warnings}; cost: provider charges apply and hutch "
                f"cannot verify the exact amount{usage_note}"),
        data=data)
