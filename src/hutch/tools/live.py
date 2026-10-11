"""Live grounding tools: bounded fan-out search and media inspection.

Both tools are *reads*: they can reach public origins and write only into Hutch's own
state directory. They record everything in the canonical grounding tables so the answer,
the UI, and a later correction all read the same evidence rows.

``live_search`` returns a compact citation brief with stable [S#] handles. ``inspect_media``
acquires one artifact, inspects it locally, stores derivatives, and hands frames to the
runtime through ``ToolResult.data["media_attachments"]`` — the runtime decides whether the
selected model route can receive them and records what actually reached the model.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from ..grounding import media as media_mod
from ..grounding import acquire as acquire_mod
from ..grounding.clock import SYSTEM_CLOCK
from ..grounding.dedup import filter_sensitivity_summary, noise_signals, origin_clusters
from ..grounding.report import CitationIndex, ClaimDraft, EvidenceLinkDraft, assess_claims, render_brief
from ..grounding.temporal import EvidenceCutoff
from .base import Tool, ToolContext, ToolResult, _schema, clip

DEFAULT_HORIZON_HOURS = 72.0


def _tool_clock(ctx: ToolContext) -> Clock:
    return getattr(ctx, "clock", None) or SYSTEM_CLOCK


def _stop_predicate(ctx: ToolContext):
    return lambda: bool(ctx.closed or ctx.gate.cancelled())


class LiveSearchTool(Tool):
    name = "live_search"
    description = (
        "Fan out a question across authorized live sources (news, first-party feeds, public discussion, "
        "optional social/SearXNG), with explicit time bounds, local date validation, and origin clustering. "
        "Returns a citation brief with [S#] handles, acquisition outcomes, coverage gaps, and the effective "
        "as-of time. Popularity is never treated as corroboration.")
    parameters = _schema(["question"], {
        "question": {"type": "string", "description": "The question to ground, e.g. 'what changed about X since yesterday?'"},
        "lanes": {"type": "array", "items": {"type": "string", "enum": list(acquire_mod.LANES)},
                  "description": "Which lanes to use (default: news, feeds, discussion, social)"},
        "horizon_hours": {"type": "number", "description": "How far back the question reaches (default 72; use 8760 for a year)"},
        "as_of": {"type": "string", "description": "ISO instant for a historical as-of boundary (evidence available by then)"},
        "timezone": {"type": "string", "description": "IANA zone for civil-time intent (default UTC)"},
        "claim": {"type": "string", "description": "An optional specific claim to verify against the same fan-out"},
        "max_results": {"type": "integer", "description": "Retained sources budget (default 40, max 40)"},
    })

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        clock = _tool_clock(ctx)
        question = str(args.get("question") or "").strip()
        if not question:
            return ToolResult(ok=False, output="error: a question is required")
        claim_text = str(args.get("claim") or "").strip()
        horizon = float(args.get("horizon_hours") or DEFAULT_HORIZON_HOURS)
        horizon = max(0.25, min(horizon, 24 * 366 * 5))
        timezone_name = str(args.get("timezone") or "UTC")
        lanes = tuple(l for l in (args.get("lanes") or ["news", "feeds", "discussion", "social"])
                      if l in acquire_mod.LANES) or ("news", "feeds")
        cutoff = EvidenceCutoff.from_clock(clock, as_of=args.get("as_of"), timezone_name=timezone_name,
                                           horizon_hours=horizon)
        cfg = acquire_mod.GroundingConfig.load(ctx.config.state_dir)
        budget = acquire_mod.AcquireBudget(
            max_total_sources=max(1, min(int(args.get("max_results") or 40), 40)))
        question_kind = "recent" if horizon <= 48 else "general"
        investigation = ctx.store.investigation_for_run(ctx.run.id) or ctx.store.create_investigation(
            run_id=ctx.run.id, conversation_id=ctx.run.conversation_id or "", bot_id=ctx.bot.id,
            question=question, reference_instant=cutoff.reference_instant.isoformat(),
            as_of_instant=cutoff.as_of.isoformat() if cutoff.as_of else None,
            user_timezone=timezone_name, horizon_hours=horizon, question_kind=question_kind,
            budget_json={"max_sources": budget.max_total_sources, "lanes": list(lanes)})
        inv_id = investigation["id"]
        queries = [question] + ([claim_text] if claim_text and claim_text.casefold() != question.casefold() else [])
        result = acquire_mod.run_search(question, cutoff=cutoff, budget=budget, clock=clock, cfg=cfg,
                                        lanes=lanes, queries=queries, stop=_stop_predicate(ctx))

        attempt_ids = ctx.store.record_query_attempts(inv_id, [o.to_json() for o in result.outcomes])
        by_adapter: dict[str, str] = {}
        for outcome, attempt_id in zip(result.outcomes, attempt_ids):
            by_adapter.setdefault(outcome.adapter, attempt_id)
        stored = ctx.store.record_sources(
            inv_id,
            [{**s.to_json(), "content_sha256": hashlib.sha256((s.title + s.excerpt).encode("utf-8")).hexdigest()[:32]}
             for s in result.sources],
            attempts_by_adapter=by_adapter)

        # claim + conservative automatic binding: retrieval by claim keywords is an allegation/context
        # link, never "supports". Passage-level support is a separate, explicit step.
        claims: list[ClaimDraft] = []
        links: list[EvidenceLinkDraft] = []
        if claim_text:
            claim = ClaimDraft(claim_id="c1", text=claim_text, kind="allegation")
        else:
            claim = ClaimDraft(claim_id="c1", text=question, kind="occurrence")
        claims.append(claim)
        claim_row_id = ctx.store.add_claim(inv_id, text=claim.text, kind=claim.kind,
                                           note="created by live_search from the request")
        claim.claim_id = claim_row_id
        terms = acquire_mod._query_terms(claim_text or question)
        for source, stored_row in zip(result.sources, stored):
            relevance = acquire_mod._relevance(f"{source.title} {source.excerpt}", terms)
            relation = "reports_allegation" if claim_text and relevance >= 0.5 else "context"
            link = EvidenceLinkDraft(claim_id=claim_row_id, source_key=source.origin_id or source.url,
                                     relation=relation, independence="unknown",
                                     note=("retrieved by claim keywords; the source statement is bound, not yet "
                                           "passage-verified" if relation == "reports_allegation" else
                                           "retrieved for the question; provides context only"))
            links.append(link)
            ctx.store.add_evidence_link(inv_id, claim_id=claim_row_id, source_id=stored_row["id"],
                                        relation=relation, independence="unknown",
                                        quote=source.excerpt[:800], note=link.note)
        # origin clustering / noise (persisted as coverage, and applied to the brief)
        dedup_items = [s.dedup_item() for s in result.sources]
        clusters = origin_clusters(dedup_items)
        sensitivity = filter_sensitivity_summary(dedup_items)
        noise = noise_signals(dedup_items)
        signals_total = sum(len(v) for v in noise.values())
        # derived labels are stored once so the API/UI and the brief cannot disagree
        stored_by_key: dict[str, dict[str, Any]] = {row["item_key"]: row for row in stored}
        annotations: dict[str, dict[str, str]] = {}
        for cluster in clusters:
            independence = "independent" if cluster.kind == "origin" else "same_origin"
            for member in cluster.members:
                row = stored_by_key.get(member.key)
                if row is not None:
                    annotations[row["id"]] = {"cluster": cluster.cluster_id, "independence": independence}
        if annotations:
            ctx.store.annotate_sources(inv_id, annotations)
        citation_index = CitationIndex.build(result.sources)
        citations_by_source: dict[str, str] = {}
        for key, handle in citation_index.handles.items():
            row = stored_by_key.get(key)
            if row is not None:
                citations_by_source[row["id"]] = handle
        coverage = {
            "adapters": {o.adapter: o.state for o in result.outcomes},
            "missing": result.missing_ledger(),
            "sample": sensitivity,
            "noise_signal_count": signals_total,
            "citations": citations_by_source,
            "deadline_hit": result.deadline_hit,
            "truncated": result.truncated,
            "note": ("observed sample, not the public: denominators are shown; filters are reversible and their "
                     "reasons are recorded"),
        }
        ctx.store.update_investigation(inv_id, coverage=coverage, status="open")
        assessments = assess_claims(claims, links, result.sources, cutoff=cutoff,
                                    missing_checks=[f"{row['adapter']} did not deliver: {row['state']}"
                                                    for row in result.missing_ledger()][:6])
        brief = render_brief(question, result, cutoff=cutoff, clock=clock, claims=claims, links=links,
                             assessments=assessments)
        ctx.store.add_answer(inv_id, body_json={
            "kind": "evidence_brief", "text": brief,
            "assessments": {cid: a.to_json() for cid, a in assessments.items()},
            "citations": citations_by_source}, effective_as_of=cutoff.effective.isoformat(),
            evidence_cutoff=cutoff.describe(), coverage_json=coverage)
        summary = (f"acquired {len(result.sources)} sources "
                   f"({', '.join(o.adapter + ':' + o.state for o in result.outcomes)})")
        return ToolResult(ok=True, output=clip(brief), data={
            "investigation_id": inv_id, "sources": len(result.sources),
            "outcomes": [o.to_json() for o in result.outcomes], "summary": summary,
            "truncated": result.truncated, "deadline_hit": result.deadline_hit})

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        return {k: (v[:200] if isinstance(v, str) else v) for k, v in args.items()}


class InspectMediaTool(Tool):
    name = "inspect_media"
    description = (
        "Acquire one image/video (workspace path or public URL), store the original with its hash, inspect "
        "container/metadata/C2PA-presence safely, sample claim-relevant video frames, and attach those frames "
        "to the model when the route supports images. Records exactly which frames were inspected and what was "
        "not; never a real/fake verdict.")
    parameters = _schema([], {
        "url": {"type": "string", "description": "Public https URL of the media"},
        "path": {"type": "string", "description": "A path inside this run's workspace"},
        "claim": {"type": "string", "description": "What is being asserted about this media (the claim under check)"},
        "times_ms": {"type": "array", "items": {"type": "integer"},
                     "description": "Claim-relevant video moments to sample (milliseconds)"},
        "max_frames": {"type": "integer", "description": "Frame budget (default 6, max 6)"},
    })

    def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        clock = _tool_clock(ctx)
        url = str(args.get("url") or "").strip()
        path = str(args.get("path") or "").strip()
        if bool(url) == bool(path):
            return ToolResult(ok=False, output="error: provide exactly one of 'url' or 'path'")
        claim = str(args.get("claim") or "").strip()
        times = [int(t) for t in (args.get("times_ms") or []) if isinstance(t, (int, float))][:6]
        max_frames = max(1, min(int(args.get("max_frames") or media_mod.MAX_FRAMES), media_mod.MAX_FRAMES))
        offline = getattr(getattr(ctx.bot, "inference_mode", None), "value", "") == "offline"
        if url and offline:
            return ToolResult(ok=False, output="error: remote media cannot be fetched in Strict Offline mode; "
                                               "save the file into the workspace and pass its path")
        investigation = ctx.store.investigation_for_run(ctx.run.id) or ctx.store.create_investigation(
            run_id=ctx.run.id, conversation_id=ctx.run.conversation_id or "", bot_id=ctx.bot.id,
            question=claim or f"inspect media {url or path}", reference_instant=clock.now().isoformat(),
            user_timezone="UTC", question_kind="media")
        media_id = f"media_{uuid.uuid4().hex[:10]}"
        store_dir = ctx.config.state_dir / "grounding" / "media" / ctx.run.id
        try:
            bundle = media_mod.inspect_media(url or path, store_dir=store_dir, media_id=media_id, clock=clock,
                                             claim=claim, claim_times_ms=times, workspace=ctx.workspace,
                                             allow_remote=not offline, max_frames=max_frames)
        except media_mod.MediaError as exc:
            return ToolResult(ok=False, output=f"error: {exc}")
        row_id = ctx.store.add_media(
            investigation["id"], origin=bundle.origin, local_path=bundle.local_path, kind=bundle.kind,
            mime=bundle.mime, byte_size=bundle.bytes, sha256=bundle.sha256, probe_json=bundle.probe,
            metadata_json=bundle.metadata, c2pa_json=bundle.c2pa, transformations_json=bundle.transformations,
            acquired_at=bundle.metadata.get("retrieved_at", clock.now().isoformat()),
            frames=[{"at_ms": f.get("at_ms", 0), "path": f.get("path", ""), "sha256": f.get("sha256", ""),
                     "note": f.get("error", "")[:300]} for f in bundle.frames])
        attachments = []
        for frame in bundle.frames:
            if frame.get("path") and frame.get("sha256"):
                attachments.append({"path": frame["path"], "mime": "image/jpeg",
                                    "label": f"frame at {frame.get('at_ms', 0)} ms", "timecode_ms": frame.get("at_ms", 0)})
        attachments = attachments[:max_frames]
        for observation in bundle.observations:
            ctx.store.add_observation(investigation["id"], kind=observation.get("kind", "note"),
                                      text=str(observation.get("text", ""))[:4000], media_id=row_id,
                                      transmitted_json={"attachments": len(attachments)} if observation.get("kind") == "scope_statement" else {},
                                      uncertain=False)
        for limitation in bundle.limitations:
            ctx.store.add_observation(investigation["id"], kind="limitation",
                                      text=str(limitation)[:4000], media_id=row_id)
        lines = [f"MEDIA EVIDENCE — inspected locally; no authenticity or truth verdict is produced",
                 f"kind={bundle.kind} mime={bundle.mime} bytes={bundle.bytes} sha256={bundle.sha256[:16]}…",
                 f"origin: {bundle.origin[:180]}"]
        if bundle.probe:
            lines.append(f"container/probe: {json_safe(bundle.probe)}")
        if bundle.metadata.get("exif"):
            lines.append(f"EXIF clues (editable, often stripped): {json_safe(bundle.metadata['exif'])}")
        if bundle.metadata.get("creation_time"):
            lines.append(f"container creation_time: {bundle.metadata['creation_time']} — a clue, not event time")
        c2pa = bundle.c2pa
        lines.append(f"C2PA: {c2pa.get('state')}"
                     + (f" — {c2pa.get('detail')}" if c2pa.get('detail') else "")
                     + (f" (verifier: {c2pa.get('verifier')})" if c2pa.get('verifier') else ""))
        if bundle.frames:
            shown = ", ".join(f"{f.get('at_ms', 0)}ms" for f in bundle.frames if f.get("path"))
            lines.append(f"frames inspected: {shown}" if shown else "no frame could be extracted")
        else:
            lines.append("no frames were extracted")
        for limitation in bundle.limitations:
            lines.append(f"limit: {limitation}")
        if attachments:
            lines.append("Attached below: the listed frames (derivatives of the stored original). Describe only what "
                         "is visible; do not infer identity, exact location, intent, or whether the media is 'real'. "
                         "State crop/resize/compression limits when they matter to the claim.")
        else:
            lines.append("No frames reached the model in this call; report the limitations above instead of "
                         "describing unseen content.")
        lines.append(f"reverse-image checks: {json_safe(media_mod.reverse_image_search_status())}")
        ctx.store.add_observation(investigation["id"], kind="transmitted",
                                  text=f"{len(attachments)} frame attachment(s) prepared for the model route",
                                  media_id=row_id, transmitted_json={"frames": [a["timecode_ms"] for a in attachments]})
        return ToolResult(ok=True, output=clip("\n".join(lines)), data={
            "investigation_id": investigation["id"], "media_id": row_id, "media_row": row_id,
            "sha256": bundle.sha256, "frames": [a["timecode_ms"] for a in attachments],
            "media_attachments": attachments,
            "c2pa_state": c2pa.get("state", "absent")})

    def recorded_arguments(self, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        return {k: (v[:200] if isinstance(v, str) else v) for k, v in args.items()}


def json_safe(value: Any) -> str:
    import json
    try:
        return json.dumps(value, ensure_ascii=False)[:600]
    except (TypeError, ValueError):
        return str(value)[:600]
