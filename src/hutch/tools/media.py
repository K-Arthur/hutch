"""Media tools: deterministic diagram/animation rendering and provider media.

Two tools, two trust stories:

* ``render_diagram``: the VERIFIED path. A pure deterministic renderer produces
  an SVG flowchart from typed nodes/edges; the bytes are validated, stored in the
  media store, and presented as a ``media`` block alongside the ``flowchart``
  block. ``effect()`` is ``""`` (nothing leaves the machine and nothing is
  billable; the durable artifact is the block data itself, like a saved artifact).
  An invalid graph NEVER loses the source: the rejection text carries the
  problems and the caller's structure (open-webui #14541).
* ``create_media``: provider path for image/video is OUTWARD and billable:
  ``effect()`` is ``"web"``, the approval decision is ask-by-default with
  ``outward=True`` (sticky grants never cover it, SR-4), ``ctx.begin_effect()``
  brackets the billable call, and the output reports that hutch cannot know the
  cost. If no backend is configured/capable the tool says so honestly, it NEVER
  substitutes stock assets or fabricates previews. The ``animation`` kind is
  deterministic (same engine as render_diagram, no approval, no billing).
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from ..media import (AnimationInvalid, GraphInvalid, MediaJobError, MediaJobService,
                     MediaStorage, MediaUnavailableError, render_animation,
                     render_flowchart, service_status, validate_animation,
                     validate_flowchart)
from ..media.providers.base import MediaBackend
from ..outputblocks import new_block_id, parse_blocks
from ..safety import Decision, Verdict
from .base import Tool, ToolContext, ToolResult, _schema, rehearsed

_MEDIA_BACKENDS: Optional[dict[str, MediaBackend]] = None

_CREATE_MEDIA_DECISION = Decision(
    verdict=Verdict.ask,
    reason="generating media calls a paid external service and sends the prompt to it",
    sticky_key="",            # outward: never sticky (SR-4)
    rule="media:create",
    risk="medium",
    outward=True,
)


def _default_backends() -> dict[str, MediaBackend]:
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


def _service(ctx: ToolContext, backends: Optional[dict[str, MediaBackend]] = None) -> MediaJobService:
    return MediaJobService(ctx.store, MediaStorage(ctx.config), backends=backends)


def _idempotency_key(ctx: ToolContext, scope: str, canonical: Any) -> str:
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"{scope}:{ctx.run.id}:{digest[:32]}"


def _check_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Belt and braces: blocks leaving a tool must survive the contract's own
    parser. Any error entry here means the tool misbuilt a block."""
    _, errors = parse_blocks(blocks)
    return errors


def _flowchart_alt_text(title: str, payload: dict[str, Any]) -> str:
    direction = "left to right" if payload.get("direction", "LR") == "LR" else "top to bottom"
    nodes = ", ".join(node["label"] for node in payload["nodes"])[:300]
    text = (f"Flowchart '{title}' ({direction}): {nodes}. "
            f"{len(payload['nodes'])} nodes, {len(payload['edges'])} connections.")
    return text[:600].strip() or "flowchart"


def _flowchart_fallback(title: str, payload: dict[str, Any]) -> str:
    lines = [f"Diagram '{title}':"]
    for node in payload["nodes"][:40]:
        line = f"- {node['label']}"
        if node.get("detail"):
            line += f" — {str(node['detail'])[:100]}"
        lines.append(line)
    edges = payload.get("edges") or []
    arrow_lines = [f"- {e['from']} -> {e['to']}"
                   + (f" ({e['label']})" if e.get("label") else "")
                   for e in edges[:40]]
    if arrow_lines:
        lines.append("Flow:")
        lines.extend(arrow_lines)
    if payload.get("assumptions_note"):
        lines.append(f"Assumption: {payload['assumptions_note']}")
    return "\n".join(lines)[:4000]


class RenderDiagramTool(Tool):
    name = "render_diagram"
    description = (
        "Render a deterministic SVG flowchart from typed nodes and edges. Validated, "
        "stored durably, and presented as media + flowchart blocks. Invalid graphs are "
        "refused with their source preserved — nothing is invented.")
    parameters = _schema(
        ["title", "nodes", "edges"],
        {
            "title": {"type": "string", "description": "Human title for the diagram (1–200 chars)"},
            "nodes": {"type": "array", "description":
                      "Nodes: [{id, label, group?, detail?}] — ids unique, at most 64"},
            "edges": {"type": "array", "description":
                      "Edges: [{from, to, label?}] — endpoints must name declared nodes; "
                      "cycles are allowed, dangling edges are not; at most 128"},
            "direction": {"type": "string", "enum": ["LR", "TB"],
                          "description": "Layout direction (default LR)"},
            "assumptions_note": {"type": "string", "description":
                                 "Ordering assumption shown under the diagram (≤1000 chars)"},
        },
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return ""    # deterministic, local, billable to no one

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        nodes = args.get("nodes") if isinstance(args.get("nodes"), list) else []
        edges = args.get("edges") if isinstance(args.get("edges"), list) else []
        return {"title": str(args.get("title", ""))[:200],
                "node_count": len(nodes), "edge_count": len(edges),
                "direction": args.get("direction", "LR")}

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        title = str(args.get("title", "")).strip()
        if not title or len(title) > 200:
            return ToolResult(ok=False, output="error: provide a title of 1–200 characters")
        payload: dict[str, Any] = {
            "nodes": args.get("nodes"),
            "edges": args.get("edges"),
            "direction": args.get("direction", "LR"),
        }
        if args.get("assumptions_note") is not None:
            payload["assumptions_note"] = args.get("assumptions_note")
        try:
            clean = validate_flowchart(payload)     # raises GraphInvalid(source=payload)
        except GraphInvalid as exc:
            source = json.dumps(payload, ensure_ascii=False, default=str)[:4000]
            return ToolResult(ok=False, output=(
                "error: the diagram was refused before anything was stored "
                f"({exc}). The source is preserved — fix these problems and re-render. "
                f"Source: {source}"))
        try:
            svg = render_flowchart(clean)
        except GraphInvalid as exc:      # unreachable after validate; kept honest
            return ToolResult(ok=False, output=f"error: {exc}")
        service = _service(ctx)
        try:
            row = service.record_local(
                run_id=ctx.run.id, conversation_id=ctx.run.conversation_id,
                kind="image", idempotency_key=_idempotency_key(ctx, "render-diagram", clean),
                requested={"kind": "image", "diagram": title,
                           "nodes": len(clean["nodes"]), "edges": len(clean["edges"])},
                produce=lambda: (svg.encode("utf-8"),
                                 {"format": "svg+xml", "width": _svg_width(svg),
                                  "height": _svg_height(svg),
                                  "alt_text": _flowchart_alt_text(title, clean)}))
        except MediaJobError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        result = row.get("result") or {}
        if row.get("status") != "succeeded" or not result:
            return ToolResult(ok=False,
                              output=f"error: the render could not be stored ({row.get('error')})")
        media_block = {
            "v": 1, "id": new_block_id(), "kind": "media", "revision": 1,
            "availability": "ready",
            "text_fallback": f"Diagram '{title}': {_flowchart_alt_text(title, clean)[:450]}",
            "provenance": {"run_id": ctx.run.id, "tool": self.name, "job_id": row["id"]},
            "payload": result,
        }
        flowchart_block = {
            "v": 1, "id": new_block_id(), "kind": "flowchart", "revision": 1,
            "availability": "ready",
            "text_fallback": _flowchart_fallback(title, clean),
            "provenance": {"run_id": ctx.run.id, "tool": self.name, "job_id": row["id"]},
            "payload": clean,
        }
        errors = _check_blocks([media_block, flowchart_block])
        warnings = ""
        if errors:
            # The stored diagram stays downloadable; only the presentation failed.
            warnings = (" (the blocks failed their own validation: "
                        + "; ".join(e.get("error", "?") for e in errors)[:300] + ")")
        data: dict[str, Any] = {"media": result, "job_id": row["id"],
                                "content_url": (f"/api/v1/media/{result['media_id']}"
                                                f"/versions/{result['version']}/content")}
        if not errors:
            data["blocks"] = [media_block, flowchart_block]
        return ToolResult(ok=True,
                          output=(f"rendered '{title}' as deterministic SVG "
                                  f"({len(clean['nodes'])} nodes, {len(clean['edges'])} edges, "
                                  f"sha256 {result['sha256'][:16]}…); media {result['media_id']} "
                                  f"v{result['version']} is stored and verifiable{warnings}"),
                          data=data)


def _svg_width(svg: str) -> int:
    marker = "width=\""
    start = svg.find(marker)
    if start < 0:
        return 640
    end = svg.find("\"", start + len(marker))
    try:
        return int(float(svg[start + len(marker):end]))
    except ValueError:
        return 640


def _svg_height(svg: str) -> int:
    marker = "height=\""
    start = svg.find(marker)
    if start < 0:
        return 400
    end = svg.find("\"", start + len(marker))
    try:
        return int(float(svg[start + len(marker):end]))
    except ValueError:
        return 400


class CreateMediaTool(Tool):
    name = "create_media"
    description = (
        "Create media: 'animation' renders deterministically (SVG, no external calls); "
        "'image'/'video' submit to a configured provider — those are billable, "
        "approval-gated, and report uncertain cost. No backend, no fabrication: the "
        "tool refuses honestly rather than substituting stock assets.")
    parameters = _schema(
        ["kind", "prompt"],
        {
            "kind": {"type": "string", "enum": ["image", "video", "animation"],
                     "description": "What to create; image/video need a configured provider"},
            "prompt": {"type": "string", "description": "What to depict (1–4000 chars)"},
            "width": {"type": "integer", "description": "Requested width in px (16–8192)"},
            "height": {"type": "integer", "description": "Requested height in px (16–8192)"},
            "seconds": {"type": "number", "description": "Requested duration for video/animation (0.1–600)"},
            "backend_hint": {"type": "string", "description": "Preferred backend name, if any"},
            "frames": {"type": "array", "description":
                       "animation only: [{label, duration_seconds?, detail?}] — at most 199 "
                       "frames; defaults to a single frame labeled from the prompt"},
        },
    )

    def __init__(self, *, backends: Optional[dict[str, MediaBackend]] = None,
                 poll_interval: float = 2.0, max_polls: int = 45):
        self._backends = backends
        self._poll_interval = poll_interval
        self._max_polls = max_polls

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "web" if args.get("kind") in ("image", "video") else ""

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        prompt = args.get("prompt")
        return {"kind": args.get("kind"),
                "backend_hint": args.get("backend_hint"),
                "width": args.get("width"), "height": args.get("height"),
                "seconds": args.get("seconds"),
                "prompt_chars": len(prompt) if isinstance(prompt, str) else 0}

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        kind = str(args.get("kind", ""))
        prompt = args.get("prompt")
        if kind not in ("image", "video", "animation"):
            return ToolResult(ok=False,
                              output="error: kind must be image, video, or animation")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            return ToolResult(ok=False,
                              output="error: provide a non-empty prompt of at most 4000 characters")
        prompt = prompt.strip()
        width, height = args.get("width"), args.get("height")
        seconds, backend_hint = args.get("seconds"), args.get("backend_hint")
        if kind == "animation":
            return self._run_animation(ctx, prompt, seconds, width, height,
                                       args.get("frames"))
        return self._run_provider(ctx, kind, prompt, width, height, seconds, backend_hint)

    # ------------------------------------------------------------- animation

    def _run_animation(self, ctx: ToolContext, prompt: str, seconds: Any,
                       width: Any, height: Any, frames: Any) -> ToolResult:
        frame_payload: dict[str, Any] = {"title": prompt[:200]}
        if isinstance(frames, list) and frames:
            frame_payload["frames"] = frames
        else:
            duration = seconds if isinstance(seconds, (int, float)) else 2.0
            frame_payload["frames"] = [{"label": prompt[:200],
                                        "duration_seconds": duration}]
        try:
            clean = validate_animation(frame_payload)
        except AnimationInvalid as exc:
            source = json.dumps(frame_payload, ensure_ascii=False, default=str)[:4000]
            return ToolResult(ok=False, output=(
                f"error: the animation was refused before anything was stored ({exc}). "
                f"The frames are preserved — fix and retry. Frames: {source}"))
        total = sum(float(f.get("duration_seconds", 2.0)) for f in clean["frames"])
        svg = render_animation(clean)
        service = _service(ctx)
        try:
            row = service.record_local(
                run_id=ctx.run.id, conversation_id=ctx.run.conversation_id,
                kind="animation",
                idempotency_key=_idempotency_key(ctx, "create-animation", clean),
                requested={"kind": "animation", "prompt": prompt[:4000],
                           "frames": len(clean["frames"]), "seconds": round(total, 3)},
                produce=lambda: (svg.encode("utf-8"),
                                 {"format": "svg+xml", "width": _svg_width(svg),
                                  "height": _svg_height(svg),
                                  "duration_seconds": total,
                                  "alt_text": f"Animation '{prompt[:200]}': "
                                  f"{len(clean['frames'])} labeled frames, {total:g}s total."}))
        except MediaJobError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        result = row.get("result") or {}
        if row.get("status") != "succeeded" or not result:
            return ToolResult(ok=False,
                              output=f"error: the animation could not be stored ({row.get('error')})")
        media_block = {
            "v": 1, "id": new_block_id(), "kind": "media", "revision": 1,
            "availability": "ready",
            "text_fallback": (f"Animation '{prompt[:200]}': {len(clean['frames'])} labeled "
                              f"frames over {total:g}s — "
                              + " | ".join(str(f.get("label", ""))[:60]
                                           for f in clean["frames"][:8]))[:4000],
            "provenance": {"run_id": ctx.run.id, "tool": self.name, "job_id": row["id"]},
            "payload": result,
        }
        errors = _check_blocks([media_block])
        warnings = ""
        if errors:
            warnings = (" (the block failed its own validation: "
                        + "; ".join(e.get("error", "?") for e in errors)[:300] + ")")
        data: dict[str, Any] = {"media": result, "job_id": row["id"],
                                "content_url": (f"/api/v1/media/{result['media_id']}"
                                                f"/versions/{result['version']}/content")}
        if not errors:
            data["blocks"] = [media_block]
        note = f"{len(clean['frames'])} frames, {total:g}s"
        return ToolResult(ok=True,
                          output=(f"rendered a deterministic SVG animation ({note}, "
                                  f"sha256 {result['sha256'][:16]}…); media "
                                  f"{result['media_id']} v{result['version']} is stored; "
                                  f"nothing was billed{warnings}"),
                          data=data)

    # ------------------------------------------------------------- provider

    def _run_provider(self, ctx: ToolContext, kind: str, prompt: str, width: Any,
                      height: Any, seconds: Any, backend_hint: Any) -> ToolResult:
        if ctx.dry_run:
            return rehearsed(f"create {kind} media from your prompt via a provider",
                             _CREATE_MEDIA_DECISION)
        backends = self._backends if self._backends is not None else _default_backends()
        service = _service(ctx, backends=backends)
        try:
            backend = service.backend_for(kind, str(backend_hint) if backend_hint else None)
        except (MediaUnavailableError, MediaJobError) as exc:
            return ToolResult(ok=False, output=(
                f"error: {exc}. hutch does not substitute stock assets or fabricate "
                "previews — configure a media backend to enable this kind."))
        clean_kwargs: dict[str, Any] = {}
        if isinstance(width, int):
            clean_kwargs["width"] = width
        if isinstance(height, int):
            clean_kwargs["height"] = height
        if isinstance(seconds, (int, float)):
            clean_kwargs["seconds"] = seconds
        action = f"create {kind} media via {backend.name}"
        try:
            ctx.gate.decide("media", action,
                            {"kind": kind, "backend": backend.name,
                             "prompt_chars": len(prompt),
                             "note": "provider charges apply; hutch cannot know the cost"},
                            _CREATE_MEDIA_DECISION)
        except Exception as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        refusal = ctx.begin_effect()
        if refusal:
            return ToolResult(ok=False,
                              output=f"error: the request was not started ({refusal})")
        idempotency_key = _idempotency_key(ctx, "create-media",
                                           {"kind": kind, "prompt": prompt, **clean_kwargs})
        try:
            row = service.submit(run_id=ctx.run.id, conversation_id=ctx.run.conversation_id,
                                 kind=kind, prompt=prompt, idempotency_key=idempotency_key,
                                 backend_hint=backend.name, **clean_kwargs)
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
        while polls < self._max_polls:
            observed = str(backend.poll(row).get("status", "running"))
            row = service.poll(row["id"], backend)   # records failed/cancelled honestly
            service_status_value = service_status(row)
            polls += 1
            if observed == "succeeded":
                upstream_succeeded = True
                break
            if service_status_value != "running":
                break
            time.sleep(self._poll_interval)
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
        alt_text = f"Generated {kind} from the prompt: {prompt[:400]}"[:600]
        try:
            payload, final_row = service.finalize(row["id"], alt_text=alt_text)
        except MediaJobError as exc:
            return ToolResult(ok=False, output=(
                f"error: the finished media could not be stored ({exc}); the provider "
                "charge may stand"))
        media_block = {
            "v": 1, "id": new_block_id(), "kind": "media", "revision": 1,
            "availability": "ready",
            "text_fallback": f"Generated {kind}: {alt_text[:400]}",
            "provenance": {"run_id": ctx.run.id, "tool": self.name,
                           "job_id": final_row.get("id", row["id"])},
            "payload": payload,
        }
        errors = _check_blocks([media_block])
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
                    "cannot verify the exact amount"),
            data=data)


TOOLS = [RenderDiagramTool(), CreateMediaTool()]
