"""Synthesis tools: ingest sources, register the evidence manifest and script, render audio.

The model proposes; Hutch validates and persists. ``register_manifest`` accepts claims only
if every span resolves to a registered source revision, every quantity carries its exact
reported text, and corroboration spans come from independent origins, then a corrected
revision marks the outputs that depended on changed claims stale. ``render_audio_overview``
is metered generation: it is an outward action (no sticky allowance), runs through the
durable effect ledger per segment, and refuses cleanly when no provider key is configured.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from ..synthesis.authoring import ScriptRejected, authoring_prompt, parse_authored_script
from ..synthesis.infographic import (
    InfographicRenderError,
    build_infographic_spec,
    layout_spec,
    render_png,
    render_svg,
    render_text_companion,
)
from ..synthesis.ingest import PaperEncryptedError, ingest_paper, ingest_thread
from ..synthesis.model import (
    Claim,
    SynthesisManifest,
    diff_claims,
    invalidate_outputs,
    spoken_text_problems,
)
from ..synthesis.storage import (
    SynthesisStorage,
    SynthesisStorageError,
    new_artifact_id,
    next_kind_version,
)
from ..synthesis.tts import (
    GeminiTTSEngine,
    OpenAITTSEngine,
    TTSError,
    plan_segments,
    render_audio,
)
from .base import Tool, ToolContext, ToolResult, rehearsed

MAX_THREAD_POSTS = 500
MAX_PAPER_BYTES = 40_000_000


def _obj(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def tts_engines(config) -> list:
    """Available speech engines, discovered from the environment.

    Keys are only ever sent to each provider's official host by the engine constructors.
    No key means no engine, Hutch never substitutes a synthetic voice and calls it real.
    """
    engines: list = []
    gemini_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if gemini_key:
        engines.append(GeminiTTSEngine(gemini_key))
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if openai_key:
        engines.append(OpenAITTSEngine(openai_key))
    return engines


class IngestSourceTool(Tool):
    name = "ingest_source"
    description = (
        "Ingest one source into the synthesis registry: a social thread (posts with stable ids "
        "and reply/quote relationships) or a PDF paper in the workspace. Returns the coverage "
        "statement, explicit gaps, and a bounded excerpt/section outline for planning. Never "
        "invents missing posts or pages.")
    parameters = _obj(
        ["kind"],
        {
            "kind": {"type": "string", "enum": ["thread", "paper"]},
            "identity": {"type": "string", "description": "Canonical URL or platform object id"},
            "title": {"type": "string"},
            "author": {"type": "string"},
            "origin": {"type": "string"},
            "language": {"type": "string"},
            "expected_count": {"type": "integer", "description":
                               "The author's stated total (thread) — the only trusted total"},
            "posts": {"type": "array", "items": {"type": "object"}, "description":
                      "Thread posts: {post_id, author_id, author, text, created_at, edited_at, "
                      "reply_to, quoted, attachments, engagement, accessible, unavailable_reason}"},
            "path": {"type": "string", "description": "Workspace-relative PDF path (paper)"},
        },
    )

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        kind = str(args.get("kind", ""))
        identity = str(args.get("identity", "")).strip()
        title = str(args.get("title", "")).strip()
        author = str(args.get("author", "")).strip()
        origin = str(args.get("origin", "")).strip()
        language = str(args.get("language", "")).strip()
        try:
            if kind == "thread":
                posts = args.get("posts")
                if not isinstance(posts, list) or not posts:
                    return ToolResult(ok=False, output="error: provide the fetched posts list")
                if len(posts) > MAX_THREAD_POSTS:
                    return ToolResult(ok=False, output=f"error: at most {MAX_THREAD_POSTS} posts per ingest")
                expected = args.get("expected_count")
                result = ingest_thread(
                    posts, expected_count=int(expected) if expected is not None else None)
                record = result.source_record(identity=identity or "thread:unknown",
                                              title=title, origin=origin, language=language)
                stored = ctx.store.record_synthesis_source(
                    record.model_dump(mode="json"), conversation_id=ctx.run.conversation_id or "",
                    bot_id=ctx.bot.id, run_id=ctx.run.id)
                excerpt = "\n\n".join(
                    f"[{p.post_id}] {p.text}" for p in result.ordered)[:8_000]
                output = (
                    f"Ingested thread: {result.coverage.statement}. "
                    f"{len(result.ordered)} ordered posts, {len(result.duplicates)} duplicates "
                    f"excluded, {len(result.corrections)} correction(s), {len(result.attachments)} "
                    f"attachment(s). Gaps: "
                    + ("; ".join(f"{g.reason} ({g.where or g.note})" for g in result.gaps)[:400] or "none")
                    + f"\n\nRegistry source id: {stored['id']} (revision {stored['revision']})\n\n"
                    + excerpt
                )
                return ToolResult(ok=True, output=output[:20000], data={
                    "source_id": stored["id"], "revision": stored["revision"], "kind": "thread",
                    "coverage": result.coverage.model_dump(mode="json"),
                    "ordered_post_ids": [p.post_id for p in result.ordered],
                    "gaps": [g.model_dump(mode="json") for g in result.gaps],
                })
            if kind == "paper":
                raw_path = str(args.get("path", "")).strip()
                if not raw_path:
                    return ToolResult(ok=False, output="error: provide the PDF path in the workspace")
                target = (ctx.workspace / raw_path).resolve()
                workspace = Path(ctx.workspace).resolve()
                if not str(target).startswith(str(workspace) + os.sep) or not target.is_file():
                    return ToolResult(ok=False, output="error: the paper path is not a file inside the workspace")
                if target.stat().st_size > MAX_PAPER_BYTES:
                    return ToolResult(ok=False, output=f"error: the PDF exceeds {MAX_PAPER_BYTES // 1_000_000} MB")
                try:
                    result = ingest_paper(str(target), identity=identity or f"file:{target.name}",
                                          title=title, author=author, origin=origin, language=language)
                except PaperEncryptedError as exc:
                    return ToolResult(ok=False, output=f"error: {exc}; nothing was extracted")
                stored = ctx.store.record_synthesis_source(
                    result.source.model_dump(mode="json"), conversation_id=ctx.run.conversation_id or "",
                    bot_id=ctx.bot.id, run_id=ctx.run.id)
                outline = "\n".join(
                    f"- {s.number} {s.title} (p{s.start_page}-{s.end_page})" if s.number
                    else f"- {s.title} (p{s.start_page}-{s.end_page})" for s in result.sections)
                candidates = "\n".join(
                    f"- {i.label or i.kind} p{i.page}: {i.text[:120]}"
                    for i in (result.tables + result.figures)[:20])
                output = (
                    f"Ingested paper: {result.coverage.statement}. {result.page_count} pages, "
                    f"{len(result.sections)} sections, {len(result.tables)} table caption(s), "
                    f"{len(result.figures)} figure caption(s). Scanned pages: "
                    f"{result.scanned_pages or 'none'}. Registry source id: {stored['id']} "
                    f"(revision {stored['revision']}).\n\nSections:\n{outline}\n\n"
                    f"Captions (candidates; verify against the page before quoting):\n{candidates}"
                )
                return ToolResult(ok=True, output=output[:20000], data={
                    "source_id": stored["id"], "revision": stored["revision"], "kind": "paper",
                    "coverage": result.coverage.model_dump(mode="json"),
                    "sections": [s.model_dump(mode="json") for s in result.sections],
                    "abstract": result.abstract[:2_000],
                    "scanned_pages": result.scanned_pages,
                    "multi_column_suspected": result.multi_column_suspected,
                })
            return ToolResult(ok=False, output="error: kind must be 'thread' or 'paper'")
        except (ValueError, SynthesisStorageError) as exc:
            return ToolResult(ok=False, output=f"error: {exc}")


class RegisterManifestTool(Tool):
    name = "register_manifest"
    description = (
        "Validate and persist a synthesis manifest revision. Sources are registered by content "
        "(identity + hash); claims must cite registered spans, quantities must carry the exact "
        "reported text, and corroboration must come from independent origins. Re-registering a "
        "changed claim marks dependent outputs stale and returns their ids.")
    parameters = _obj(
        ["manifest"],
        {"manifest": {"type": "object", "description":
                      "The full manifest: sources[], spans[], claims[], audience, language, "
                      "depth, policy, caveats, contradictions, outputs[]"}},
    )

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        payload = args.get("manifest")
        if not isinstance(payload, dict):
            return ToolResult(ok=False, output="error: provide the manifest object")
        if ctx.dry_run:
            return rehearsed("register the synthesis manifest")
        try:
            proposed = SynthesisManifest.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - pydantic reports every violation
            return ToolResult(ok=False, output=f"error: the manifest is not valid: {str(exc)[:800]}")
        try:
            # Register every source by identity+content and remap ids so spans stay bound.
            data = proposed.model_dump(mode="json")
            mapping: dict[str, str] = {}
            for source in data["sources"]:
                stored = ctx.store.record_synthesis_source(
                    source, conversation_id=ctx.run.conversation_id or "", bot_id=ctx.bot.id,
                    run_id=ctx.run.id)
                mapping[source["id"]] = stored["id"]
            for source in data["sources"]:
                source["id"] = mapping[source["id"]]
            for span in data["spans"]:
                span["source_id"] = mapping[span["source_id"]]
            manifest = SynthesisManifest.model_validate(data)

            existing = ctx.store.get_synthesis_manifest(manifest.id)
            stale: list[str] = []
            changed: list[str] = []
            if existing is not None:
                old = SynthesisManifest.model_validate(existing["doc"])
                changes = diff_claims(old, manifest)
                changed = sorted({c.claim_id for c in changes})
                manifest.revision = int(existing["revision"]) + 1
                if changed:
                    stale = invalidate_outputs(
                        old, set(changed),
                        reason=f"claims changed in revision {manifest.revision}")
                    ctx.store.save_synthesis_manifest(
                        old.model_dump(mode="json"), reason="dependent outputs marked stale")
            stored = ctx.store.save_synthesis_manifest(
                manifest.model_dump(mode="json"),
                reason="registered via register_manifest")
        except ValueError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        summary = (
            f"Manifest {manifest.id} revision {manifest.revision} registered: "
            f"{len(manifest.sources)} source(s), {len(manifest.spans)} span(s), "
            f"{len(manifest.claims)} claim(s). Coverage: {manifest.coverage_summary or 'see sources'}. "
            + (f"Changed claims: {', '.join(changed)}. " if changed else "")
            + (f"Outputs now stale: {', '.join(stale)}." if stale else "")
        )
        return ToolResult(ok=True, output=summary, data={
            "manifest_id": manifest.id, "revision": manifest.revision,
            "changed_claim_ids": changed, "stale_output_ids": stale,
            "authoring_prompt": authoring_prompt(manifest),
        })


class RegisterScriptTool(Tool):
    name = "register_script"
    description = (
        "Validate a two-host script against the registered manifest and store it as an immutable "
        "artifact. Unknown claims, invented numbers and spoken stage directions are refused. The "
        "script is the exact text that will be synthesized; delivery notes live in 'style'.")
    parameters = _obj(
        ["manifest_id", "script"],
        {"manifest_id": {"type": "string"},
         "script": {"type": "object", "description":
                    "{chapters:[{title, utterances:[{speaker: guide|probe, kind, text, "
                    "claim_ids, style, pause_after_ms}]}]}"}},
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "fs"

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        manifest_id = str(args.get("manifest_id", "")).strip()
        manifest_row = ctx.store.get_synthesis_manifest(manifest_id) if manifest_id else None
        if manifest_row is None:
            return ToolResult(ok=False, output="error: no such manifest; register it first")
        manifest = SynthesisManifest.model_validate(manifest_row["doc"])
        if ctx.dry_run:
            return rehearsed(f"register a script for {manifest_id}")
        try:
            script = parse_authored_script(args.get("script") or {}, manifest)
        except ScriptRejected as exc:
            return ToolResult(ok=False, output="error: the script was rejected: " + "; ".join(exc.problems[:8]))
        try:
            segments = plan_segments(script, manifest=manifest)
        except TTSError as exc:
            return ToolResult(ok=False, output=f"error: the script cannot be synthesized: {exc}")
        storage = SynthesisStorage(ctx.config)
        existing = ctx.store.list_synthesis_artifacts(manifest_id, kind="script", limit=500)
        version = (max(int(a["version"]) for a in existing) + 1) if existing else 1
        script_json = json.dumps(script.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
        artifact_id = new_artifact_id()
        try:
            staged = storage.stage_bytes("script", f"script-v{version}.json", script_json)
            rel = storage.version_rel_path(manifest_id, "script", version, staged.sha256,
                                           staged.storage_name)
            storage.commit(staged, manifest_id, version, insert_row=lambda: ctx.store.record_synthesis_artifact(
                artifact_id=artifact_id, manifest_id=manifest_id, kind="script", version=version,
                status="validated", storage_path=rel, storage_name=staged.storage_name,
                mime=staged.mime, bytes_=staged.bytes, sha256=staged.sha256,
                meta={"utterances": len(script.utterances), "chapters": len(script.chapters),
                      "segments": len(segments), "language": script.language,
                      "speakers": [s.model_dump(mode="json") for s in script.speakers]}))
        except (SynthesisStorageError, ValueError) as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        problems: list[str] = []
        for u in script.utterances:
            problems.extend(spoken_text_problems(u.text))
        return ToolResult(ok=True, output=(
            f"Script v{version} registered ({artifact_id}): {len(script.chapters)} chapters, "
            f"{len(script.utterances)} utterances, {len(segments)} TTS segment(s). "
            + (f"Text warnings: {problems[:3]}" if problems else "Text validated.")),
            data={"script_artifact_id": artifact_id, "version": version, "segments": len(segments)})


class RenderAudioOverviewTool(Tool):
    name = "render_audio_overview"
    description = (
        "Render the registered two-host script to a downloadable WAV plus a VTT transcript. "
        "This is paid generation: it always asks for approval, journals each segment, reuses "
        "verified audio on retry, and reports which engine/voices were used. Needs a configured "
        "TTS key (GEMINI_API_KEY or OPENAI_API_KEY).")
    parameters = _obj(
        ["manifest_id", "script_artifact_id"],
        {"manifest_id": {"type": "string"},
         "script_artifact_id": {"type": "string"},
         "output_name": {"type": "string"}},
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "web"

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        manifest_id = str(args.get("manifest_id", "")).strip()
        artifact_id = str(args.get("script_artifact_id", "")).strip()
        manifest_row = ctx.store.get_synthesis_manifest(manifest_id) if manifest_id else None
        if manifest_row is None:
            return ToolResult(ok=False, output="error: no such manifest")
        artifact_row = ctx.store.get_synthesis_artifact(artifact_id)
        if artifact_row is None or artifact_row.get("kind") != "script":
            return ToolResult(ok=False, output="error: no such script artifact")
        manifest = SynthesisManifest.model_validate(manifest_row["doc"])
        storage = SynthesisStorage(ctx.config)
        try:
            raw = storage.read_artifact(artifact_row["storage_path"], artifact_row["sha256"],
                                        int(artifact_row["bytes"]))
            from ..synthesis.model import Script as ScriptModel

            script = ScriptModel.model_validate(json.loads(raw))
        except (SynthesisStorageError, ValueError) as exc:
            return ToolResult(ok=False, output=f"error: the stored script failed verification: {exc}")

        engines = tts_engines(ctx.config)
        if not engines:
            return ToolResult(ok=False, output=(
                "error: no speech engine is configured. Set GEMINI_API_KEY (multi-speaker, two "
                "prebuilt voices) or OPENAI_API_KEY (one voice per turn) and retry; Hutch will not "
                "substitute a synthetic voice and present it as the requested hosts."))
        engine = engines[0]
        try:
            segments = plan_segments(script, manifest=manifest)
        except TTSError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        chars = sum(s.chars for s in segments)
        if ctx.dry_run:
            return rehearsed(
                f"render {len(segments)} segment(s) ({chars} chars) with {engine.name}")
        try:
            ctx.gate.decide(
                "synthesis_audio",
                f"render {len(segments)} segment(s) with {engine.name}",
                {"manifest_id": manifest_id, "script_artifact_id": artifact_id,
                 "engine": engine.name, "model": getattr(engine, "model", engine.name),
                 "segments": len(segments), "chars": chars,
                 "speakers": [{"id": s.id, "voice": s.voice.get(engine.name, "")}
                              for s in script.speakers]},
                outward=True)
        except Exception as exc:  # noqa: BLE001 - denial and expiry both stop the call
            return ToolResult(ok=False, output=f"error: {exc}")
        try:
            result = render_audio(
                manifest, script, engines=engines, storage=storage, store=ctx.store,
                output_name=str(args.get("output_name") or ""))
        except TTSError as exc:
            return ToolResult(ok=False, output=f"error: the render failed: {exc}")
        return ToolResult(ok=True, output=(
            f"Audio overview rendered: {result.duration_ms / 1000:.1f}s, "
            f"{result.segments_rendered} segment(s) rendered, {result.segments_reused} reused. "
            f"Audio artifact {result.audio_artifact_id}; transcript {result.transcript_artifact_id}. "
            + ("Warnings: " + "; ".join(result.warnings[:3]) if result.warnings else "")),
            data={"audio_artifact_id": result.audio_artifact_id,
                  "transcript_artifact_id": result.transcript_artifact_id,
                  "duration_ms": result.duration_ms, "sha256": result.audio_sha256,
                  "warnings": result.warnings})

class RenderInfographicTool(Tool):
    name = "render_infographic"
    description = (
        "Render a deterministic infographic panel (SVG source + optional PNG export) and a "
        "plain-text companion from the registered manifest. Shows key findings with [S#] source "
        "handles, numbers exactly as reported (percentage-point changes labeled as such), "
        "limitations, and concise sources. Local rendering; no provider call.")
    parameters = _obj(
        ["manifest_id"],
        {"manifest_id": {"type": "string"},
         "width": {"type": "integer", "description": "Pixels; at least 480 (default 1080)"},
         "height": {"type": "integer", "description": "Pixels; at least 400 (default 1600)"},
         "include_png": {"type": "boolean", "description": "Raster export of the same layout (default true)"}},
    )

    def effect(self, args: dict[str, Any], ctx: ToolContext) -> str:
        return "fs"

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        manifest_id = str(args.get("manifest_id", "")).strip()
        row = ctx.store.get_synthesis_manifest(manifest_id) if manifest_id else None
        if row is None:
            return ToolResult(ok=False, output="error: no such manifest")
        manifest = SynthesisManifest.model_validate(row["doc"])
        spec = build_infographic_spec(manifest)
        try:
            layout = layout_spec(spec, width=int(args.get("width") or 1080),
                                 height=int(args.get("height") or 1600))
        except ValueError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        svg = render_svg(layout, spec)
        companion = render_text_companion(spec).encode("utf-8")
        png: Optional[bytes] = None
        raster_note = ""
        if bool(args.get("include_png", True)):
            try:
                png = render_png(layout, spec)
            except InfographicRenderError as exc:
                raster_note = f" PNG export unavailable: {exc}."
        storage = SynthesisStorage(ctx.config)
        artifacts: dict[str, str] = {}
        try:
            def _store(kind: str, name: str, payload: bytes, meta: dict) -> str:
                version = next_kind_version(ctx.store, manifest_id, kind)
                artifact_id = new_artifact_id()
                staged = storage.stage_bytes(kind, name, payload)
                rel = storage.version_rel_path(manifest_id, kind, version, staged.sha256,
                                               staged.storage_name)
                storage.commit(staged, manifest_id, version,
                               insert_row=lambda: ctx.store.record_synthesis_artifact(
                                   artifact_id=artifact_id, manifest_id=manifest_id, kind=kind,
                                   version=version, status="validated", storage_path=rel,
                                   storage_name=staged.storage_name, mime=staged.mime,
                                   bytes_=staged.bytes, sha256=staged.sha256, meta=meta))
                artifacts[kind if kind != "infographic" else meta["variant"]] = artifact_id
                return artifact_id

            _store("infographic", f"infographic-{layout.width}x{layout.height}.svg", svg,
                   {"variant": "svg", "width": layout.width, "height": layout.height,
                    "manifest_revision": manifest.revision})
            if png is not None:
                _store("infographic", f"infographic-{layout.width}x{layout.height}.png", png,
                       {"variant": "png", "width": layout.width, "height": layout.height,
                        "manifest_revision": manifest.revision})
            _store("companion", "infographic-companion.md", companion,
                   {"variant": "text", "manifest_revision": manifest.revision})
        except (SynthesisStorageError, ValueError) as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        sections = ", ".join(f"{s.kind} ({len(s.items)})" for s in spec.sections)
        return ToolResult(ok=True, output=(
            f"Infographic rendered at {layout.width}x{layout.height}: {sections}. "
            f"SVG artifact {artifacts.get('svg', '')}"
            + (f", PNG artifact {artifacts.get('png')}" if artifacts.get("png") else "")
            + f", text companion {artifacts.get('text', '')}. "
            "The SVG is the editable source; the PNG is a raster of the same layout."
            + raster_note),
            data={"manifest_id": manifest_id, "artifacts": artifacts,
                  "width": layout.width, "height": layout.height,
                  "source_handles": spec.source_handles})
