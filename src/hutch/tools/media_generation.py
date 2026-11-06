"""Provider-backed media creation, split out of ``tools/media.py``.

``tools/media.py`` is a frozen over-cap module: new behaviour moves into a sibling rather
than growing it. This module owns the billable provider path (image, video and speech) and the
shared media-job helpers the deterministic tools also use. Backend discovery lives in
:mod:`hutch.media.backends`.

Trust story unchanged from the tool it serves: ``create_media`` is OUTWARD and billable for
provider kinds, ``effect()`` is ``"web"``, the approval decision is ask-by-default with
``outward=True`` (sticky grants never cover it, SR-4), and ``ctx.begin_effect()`` brackets
the call. If no backend is configured/capable the caller is told so honestly; nothing is
substituted or fabricated. Before the approval the request is validated against the route's
documented limits, and the approval shows who is paid, from which credential, and an estimate
of the cost with its basis (or says the cost is unknown).
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from ..media import (MediaJobError, MediaJobService, MediaStorage, MediaUnavailableError,
                     service_status)
from ..media.backends import build_backends
from ..media.cost import estimate
from ..media.providers.base import MediaBackend
from ..media.resume import default_alt_text
from ..media.spool import MediaSpool
from ..media.usage import measured_usage, record_media_usage
from ..outputblocks import new_block_id, parse_blocks
from ..safety import Decision, Verdict
from .base import ToolContext, ToolResult, rehearsed

CREATE_MEDIA_DECISION = Decision(
    verdict=Verdict.ask,
    reason="generating media calls a paid external service and sends the prompt to it",
    sticky_key="",            # outward: never sticky (SR-4)
    rule="media:create",
    risk="medium",
    outward=True,
)


# ------------------------------------------------------------------ backends


def configured_backends(ctx: ToolContext) -> dict[str, MediaBackend]:
    """Every backend whose credential exists, with durable result holding."""
    spool = MediaSpool(MediaStorage(ctx.config).root)
    return build_backends(ctx.config.state_dir, spool=spool)


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


def _fail(text: str) -> ToolResult:
    return ToolResult(ok=False, output=text)


# ------------------------------------------------------------------ request


def _geometry(kind: str, width: Any, height: Any, seconds: Any) -> dict[str, Any]:
    if kind == "audio":
        return {}
    clean: dict[str, Any] = {}
    if isinstance(width, int):
        clean["width"] = width
    if isinstance(height, int):
        clean["height"] = height
    if isinstance(seconds, (int, float)):
        clean["seconds"] = seconds
    return clean


def _audio_extra(backend: MediaBackend, voice: Any, style: Any) -> tuple[dict[str, Any], str]:
    """The ``voice`` and ``style`` an audio request carries, or an error sentence."""
    chosen = str(voice or "").strip()
    caps = backend.capabilities()
    offered = caps.get("voices") or []
    if chosen and offered and chosen not in offered:
        return {}, (f"error: voice {chosen!r} is not offered by {backend.name} "
                    f"(voices: {', '.join(offered) or 'none declared'})")
    if style is not None and not isinstance(style, str):
        return {}, "error: style must be a string"
    clean_style = " ".join(str(style or "").split())
    if len(clean_style) > 2000:
        return {}, "error: the style instruction is longer than 2000 characters"
    return {"voice": chosen or str(caps.get("default_voice") or ""), "style": clean_style}, ""


def _approval_detail(backend: MediaBackend, kind: str, prompt: str,
                     request: dict[str, Any]) -> dict[str, Any]:
    detail: dict[str, Any] = {"kind": kind, "backend": backend.name, "prompt_chars": len(prompt)}
    describe = getattr(backend, "approval_detail", None)
    if callable(describe):
        detail.update(describe({"prompt": prompt, **request}))
    price_key = getattr(getattr(backend, "route", None), "price", "")
    cost = estimate(price_key, {"prompt": prompt, **request})
    detail["cost"] = cost.sentence()
    detail["cost_basis"] = cost.as_dict()
    return detail


# ------------------------------------------------------------------ waiting


def _wait(service: MediaJobService, backend: MediaBackend, row: dict[str, Any],
          poll_interval: float, max_polls: int) -> tuple[dict[str, Any], bool, int]:
    """Poll until the upstream job reaches a state or the bound is spent."""
    polls = 0
    while polls < max_polls:
        observed = str(backend.poll(row).get("status", "running"))
        row = service.poll(row["id"], backend)   # records failed/cancelled/refused honestly
        polls += 1
        if observed == "succeeded":
            return row, True, polls
        if service_status(row) != "running":
            break
        time.sleep(poll_interval)
    return row, False, polls


def _unfinished(row: dict[str, Any], status: str, polls: int,
                upstream_succeeded: bool) -> Optional[ToolResult]:
    """The result for a job that did not finish cleanly, or None when it can be finalized."""
    if not upstream_succeeded and status == "running":
        return _fail(
            f"the media job {row['id']} is still running upstream after {polls} checks; it is "
            "recorded in the ledger and may complete and bill. It is not lost: check its status, "
            "resume it or cancel it from the media jobs list (POST /api/v1/media/jobs/"
            f"{row['id']}/advance or /cancel)")
    if status == "refused":
        return _fail(
            f"the provider declined media job {row['id']} on content grounds: "
            f"{row.get('error') or 'no reason given'}. This is a refusal, not an outage; "
            "rephrase the request rather than retrying it. See the media job ledger.")
    if status == "failed":
        return _fail(
            f"error: the media job {row['id']} failed upstream "
            f"({row.get('error') or 'unknown reason'}); no media was stored. "
            "Whether the provider charged for the attempt depends on the backend.")
    if status == "cancel_unconfirmed":
        return _fail(
            f"error: the media job {row['id']} was asked to cancel but the backend never "
            "confirmed; it may still be running and billing - verify with the backend. "
            "This is recorded honestly in the ledger.")
    return None


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
    service = service_for(ctx, backends=backends if backends is not None
                          else configured_backends(ctx))
    try:
        backend = service.backend_for(kind, str(backend_hint) if backend_hint else None)
    except (MediaUnavailableError, MediaJobError) as exc:
        return _fail(f"error: {exc}. hutch does not substitute stock assets or fabricate "
                     "previews - configure a media backend to enable this kind.")
    clean = _geometry(kind, width, height, seconds)
    extra: Optional[dict[str, Any]] = None
    if kind == "audio":
        extra, problem = _audio_extra(backend, voice, style)
        if problem:
            return _fail(problem)
    problem = _refuse_before_approval(backend, {"prompt": prompt, **clean, **(extra or {})})
    if problem:
        return _fail(problem)
    detail = _approval_detail(backend, kind, prompt, {**clean, **(extra or {})})
    action = (f"speak {len(prompt)} characters via {backend.name}" if kind == "audio"
              else f"create {kind} media via {backend.name}")
    try:
        ctx.gate.decide("audio_synthesis" if kind == "audio" else "media", action, detail,
                        CREATE_MEDIA_DECISION)
    except Exception as exc:
        return _fail(f"error: {exc}")
    refusal = ctx.begin_effect()
    if refusal:
        return _fail(f"error: the request was not started ({refusal})")
    return _submit_and_finish(ctx, service, backend, tool_name, kind, prompt, clean, extra,
                              detail, poll_interval, max_polls)


def _refuse_before_approval(backend: MediaBackend, request: dict[str, Any]) -> str:
    """The backend's own check of the request against its documented limits, before any prompt."""
    check = getattr(backend, "validate", None)
    if not callable(check):
        return ""
    try:
        check(request)
    except ValueError as exc:
        return f"error: {exc}. Nothing was sent or billed."
    return ""


def _submit_and_finish(ctx: ToolContext, service: MediaJobService, backend: MediaBackend,
                       tool_name: str, kind: str, prompt: str, clean: dict[str, Any],
                       extra: Optional[dict[str, Any]], detail: dict[str, Any],
                       poll_interval: float, max_polls: int) -> ToolResult:
    key = media_idempotency_key(ctx, "create-media",
                                {"kind": kind, "prompt": prompt, **clean, **(extra or {}),
                                 "backend": backend.name})
    try:
        row = service.submit(run_id=ctx.run.id, conversation_id=ctx.run.conversation_id,
                             kind=kind, prompt=prompt, idempotency_key=key,
                             backend_hint=backend.name, requested_extra=extra, **clean)
    except MediaJobError as exc:
        return _fail(f"error: the media job could not be submitted ({exc}). Nothing new was "
                     "billed by this call; a previous submission with the same content may "
                     "already exist - check the media job ledger.")
    status = service_status(row)
    if status == "refused":
        return _unfinished(row, status, 0, False) or _fail("error: refused")
    if status == "submitting":
        return _fail(f"error: the job ({row['id']}) never reached the backend; "
                     f"{row.get('error') or 'the submission failed'} - see the media job ledger")
    row, upstream_succeeded, polls = _wait(service, backend, row, poll_interval, max_polls)
    status = service_status(row)
    stopped = _unfinished(row, status, polls, upstream_succeeded)
    if stopped is not None:
        return stopped
    return _finalize(ctx, service, backend, tool_name, kind, prompt, row, detail)


# ------------------------------------------------------------------ finishing


def _finalize(ctx: ToolContext, service: MediaJobService, backend: MediaBackend,
              tool_name: str, kind: str, prompt: str, row: dict[str, Any],
              detail: dict[str, Any]) -> ToolResult:
    alt_text = default_alt_text(kind, prompt)
    probe = getattr(backend, "duration_seconds", None)
    duration = probe(row) if kind == "audio" and callable(probe) else None
    spoken = measured_usage(backend, kind, row)         # before finalize releases the held copy
    try:
        payload, final_row = service.finalize(row["id"], alt_text=alt_text,
                                              duration_seconds=duration)
    except MediaJobError as exc:
        return _fail(f"error: the finished media could not be stored ({exc}); the provider "
                     "charge may stand")
    if service_status(final_row) in ("failed", "refused"):
        return _unfinished(final_row, service_status(final_row), 0, True) or _fail("error: failed")
    usage_note = _record_usage(ctx, backend, kind, row, detail, spoken)
    return _result(ctx, tool_name, kind, prompt, alt_text, payload, final_row, row, backend,
                   usage_note, detail)


def _record_usage(ctx: ToolContext, backend: MediaBackend, kind: str, row: dict[str, Any],
                  detail: dict[str, Any], spoken: Any) -> str:
    """Write the run-ledger usage row and keep the run's token counters in step."""
    note, prompt_tokens, completion_tokens = record_media_usage(
        ctx.store, run_id=ctx.run.id, bot_id=ctx.bot.id, backend=backend, kind=kind, job=row,
        request=row.get("requested") or {}, detail=detail, spoken=spoken)
    if note:
        return note
    try:
        ctx.run.prompt_tokens += prompt_tokens
        ctx.run.completion_tokens += completion_tokens
        ctx.store.update_run(ctx.run)
    except Exception as exc:  # noqa: BLE001 - the media is real and must be returned
        return f"; run counters could not be updated: {exc}"
    return (f"; {prompt_tokens} prompt / {completion_tokens} completion tokens recorded"
            if prompt_tokens or completion_tokens else "")


def _result(ctx: ToolContext, tool_name: str, kind: str, prompt: str, alt_text: str,
            payload: dict[str, Any], final_row: dict[str, Any], row: dict[str, Any],
            backend: MediaBackend, usage_note: str, detail: dict[str, Any]) -> ToolResult:
    job_id = final_row.get("id", row["id"])
    media_block = {
        "v": 1, "id": new_block_id(), "kind": "media", "revision": 1, "availability": "ready",
        "text_fallback": (f"Speech: {prompt[:400]}" if kind == "audio"
                          else f"Generated {kind}: {alt_text[:400]}"),
        "provenance": {"run_id": ctx.run.id, "tool": tool_name, "job_id": job_id},
        "payload": payload,
    }
    errors = check_blocks([media_block])
    warnings = ("" if not errors else " (the block failed its own validation: "
                + "; ".join(e.get("error", "?") for e in errors)[:300] + ")")
    data: dict[str, Any] = {"media": payload, "job_id": job_id,
                            "content_url": (f"/api/v1/media/{payload['media_id']}"
                                            f"/versions/{payload['version']}/content")}
    if not errors:
        data["blocks"] = [media_block]
    cost = detail.get("cost") or "provider charges apply"
    return ToolResult(
        ok=True,
        output=(f"created {kind} media via {backend.name} "
                f"({payload['mime']}, sha256 {payload['sha256'][:16]}...); media "
                f"{payload['media_id']} v{payload['version']} is stored and "
                f"verifiable{warnings}; cost: {cost}. hutch cannot verify the exact "
                f"amount charged{usage_note}"),
        data=data)
