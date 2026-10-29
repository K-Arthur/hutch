"""Two-host script authoring: grounded prompt construction, strict parsing, offline drafts.

Two paths produce a :class:`~hutch.synthesis.model.Script`:

* :func:`parse_authored_script` accepts a model-authored JSON payload and *refuses* it
  unless every claim id exists, every spoken number traces to a manifest quantity, no
  non-vocal stage direction sits in the transcript, and the two-host shape holds. A
  rejected draft lists its problems so the caller can re-prompt once, bounded, never a
  silent repair.
* :func:`deterministic_draft` builds a plainly-labeled script without any model. It only
  sequences real manifest content (coverage, claims verbatim, caveats, contradictions),
  so it is honest for tests and strict-offline use; it is deliberately not presented as
  good dialogue.

The prompt separates the *content plan* (claims with ids, quantities, caveats) from the
spoken text, and it forbids new facts, invented numbers, and rhetorical questions that
smuggle in unsupported premises (the probe's questions must be answerable from the claims
or explicitly marked as unaddressed).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from .model import (
    Chapter,
    Claim,
    Script,
    Speaker,
    SynthesisManifest,
    Utterance,
    spoken_text_problems,
    utterance_number_problems,
)

GUIDE_ROLE = "guide"
PROBE_ROLE = "probe"

DEFAULT_VOICES: dict[str, dict[str, str]] = {
    "guide": {"gemini": "Puck", "openai": "alloy"},
    "probe": {"gemini": "Kore", "openai": "echo"},
}

MAX_UTTERANCES = 400
MAX_UTTERANCE_CHARS = 2_000


class ScriptRejected(ValueError):
    """The authored script is not acceptable. ``problems`` lists every reason."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems[:5]) or "script rejected")


# ---------------------------------------------------------------------------
# prompt construction


def authoring_prompt(manifest: SynthesisManifest, *, target_words: Optional[int] = None) -> dict[str, str]:
    """Deterministic, bounded authoring instructions plus the manifest's content plan."""
    target = target_words or manifest.depth.target_words or 900
    lines: list[str] = []
    lines.append(f"Audience: {manifest.audience} (expertise: {manifest.expertise}).")
    lines.append(f"Language: {manifest.language}. Tone: {manifest.tone}.")
    lines.append(f"Target spoken length: about {target} words.")
    lines.append(f"Coverage: {manifest.coverage_summary or 'see sources'}.")
    if manifest.caveats:
        lines.append("Global caveats that must be preserved where relevant:")
        for c in manifest.caveats[:12]:
            lines.append(f"- {c}")
    lines.append("")
    lines.append("Claims you may use (use the exact id; do not add any fact not listed):")
    for claim in manifest.claims[:80]:
        if claim.status == "retracted":
            continue
        bits = [f"[{claim.id}] ({claim.kind}) {claim.text}"]
        if claim.attribution:
            bits.append(f"  attribution: {claim.attribution}")
        for q in claim.quantities:
            bits.append(f"  quantity as reported: {q.as_reported}")
        for c in claim.caveats[:3]:
            bits.append(f"  caveat: {c}")
        if claim.confidence_basis:
            bits.append(f"  basis: {claim.confidence_basis}")
        if claim.status != "supported":
            bits.append(f"  status: {claim.status}")
        lines.append("\n".join(bits))
    for cx in manifest.contradictions:
        if cx.status == "unresolved":
            lines.append(f"Unresolved contradiction [{cx.id}]: {cx.description} "
                         f"(claims: {', '.join(cx.claim_ids)})")
    if manifest.policy == "source_only":
        lines.append("")
        lines.append("Source-only mode: you may not bring in outside facts.")

    system = (
        "You write a two-host spoken script from a fixed evidence revision. "
        "Host A (guide) explains; host B (probe) asks the questions a careful listener "
        "would ask about mechanisms, evidence and limitations, and the guide answers only "
        "from the listed claims. Rules: never state a fact, number, name or study that is "
        "not in the claim list; when a number is spoken it must match a listed quantity; "
        "when evidence is thin, mixed or missing, say so plainly; a question must not "
        "assert an unlisted premise. Put delivery notes ONLY in the 'style' field, never "
        "inside 'text'; 'text' is the exact spoken transcript. Respond with strict JSON "
        "matching the provided schema and nothing else."
    )
    user = "\n".join(lines)
    schema = {
        "chapters": [{"title": "string", "utterances": [
            {"speaker": "guide|probe", "kind": "statement|question|answer|transition",
             "text": "string", "claim_ids": ["cl_..."], "style": "string (optional)",
             "pause_after_ms": 0}
        ]}]
    }
    user += "\n\nReturn JSON shaped exactly like:\n" + json.dumps(schema, indent=1)
    return {"system": system, "user": user}


# ---------------------------------------------------------------------------
# strict parsing


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(payload: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    text = str(payload or "").strip()
    match = _JSON_FENCE.search(text)
    if match:
        text = match.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ScriptRejected([f"the draft is not valid JSON: {exc}"]) from exc
    if not isinstance(data, dict):
        raise ScriptRejected(["the draft must be a JSON object with a 'chapters' list"])
    return data


def parse_authored_script(payload: str | dict[str, Any], manifest: SynthesisManifest, *,
                          names: Optional[dict[str, str]] = None,
                          voices: Optional[dict[str, dict[str, str]]] = None,
                          version: int = 1, language: str = "") -> Script:
    """Validate a model-authored script against the manifest; refuse on any violation."""
    data = _extract_json(payload)
    problems: list[str] = []
    chapter_payload = data.get("chapters")
    if not isinstance(chapter_payload, list) or not chapter_payload:
        raise ScriptRejected(["the draft needs a non-empty 'chapters' list"])

    names = names or {"guide": "Host A", "probe": "Host B"}
    voices = voices or DEFAULT_VOICES
    speakers = [
        Speaker(id="host_a", name=names.get("guide", "Host A"), role=GUIDE_ROLE,
                voice=dict(voices.get("guide", {}))),
        Speaker(id="host_b", name=names.get("probe", "Host B"), role=PROBE_ROLE,
                voice=dict(voices.get("probe", {}))),
    ]
    by_role = {"guide": "host_a", "probe": "host_b"}

    chapters: list[Chapter] = []
    utterances: list[Utterance] = []
    total = 0
    for ci, ch in enumerate(chapter_payload[:40]):
        if not isinstance(ch, dict):
            problems.append(f"chapter {ci} is not an object")
            continue
        chapter = Chapter(index=ci, title=str(ch.get("title", f"Part {ci + 1}"))[:120])
        chapters.append(chapter)
        for ui, item in enumerate(ch.get("utterances") or []):
            total += 1
            if total > MAX_UTTERANCES:
                problems.append(f"too many utterances (>{MAX_UTTERANCES})")
                break
            if not isinstance(item, dict):
                problems.append(f"chapter {ci} utterance {ui} is not an object")
                continue
            role = str(item.get("speaker", "")).strip().lower()
            if role not in by_role:
                problems.append(f"chapter {ci} utterance {ui}: speaker must be guide|probe")
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                problems.append(f"chapter {ci} utterance {ui}: empty text")
                continue
            if len(text) > MAX_UTTERANCE_CHARS:
                problems.append(f"chapter {ci} utterance {ui}: text exceeds {MAX_UTTERANCE_CHARS} chars")
                continue
            claim_ids = [str(c) for c in (item.get("claim_ids") or [])]
            unknown = [c for c in claim_ids if manifest.claim(c) is None]
            if unknown:
                problems.append(f"chapter {ci} utterance {ui}: unknown claim ids {unknown}")
                continue
            kind = str(item.get("kind", "statement"))
            if kind not in ("statement", "question", "answer", "transition"):
                kind = "statement"
            pause = item.get("pause_after_ms", 0)
            try:
                pause = max(0, min(int(pause or 0), 10_000))
            except (TypeError, ValueError):
                pause = 0
            utterance = Utterance(
                speaker_id=by_role[role], text=text, claim_ids=claim_ids,
                chapter_id=chapter.id, style=str(item.get("style", ""))[:200],
                pause_after_ms=pause, kind=kind,
            )
            probes = spoken_text_problems(utterance.text)
            problems.extend(f"chapter {ci} utterance {ui}: {p}" for p in probes)
            if claim_ids:
                problems.extend(utterance_number_problems(utterance, manifest))
            chapters[-1].utterance_ids.append(utterance.id)
            utterances.append(utterance)
    if problems:
        raise ScriptRejected(problems[:20])

    return Script(
        manifest_id=manifest.id, manifest_revision=manifest.revision, version=version,
        language=language or manifest.language, speakers=speakers, chapters=chapters,
        utterances=utterances,
    )


# ---------------------------------------------------------------------------
# deterministic offline draft (explicitly plain, never presented as good dialogue)


def deterministic_draft(manifest: SynthesisManifest, *, names: Optional[dict[str, str]] = None,
                        voices: Optional[dict[str, dict[str, str]]] = None,
                        version: int = 1, include_questions: bool = True) -> Script:
    """A plainly-labeled script that only sequences real manifest content.

    Used for tests and strict-offline derivatives. Claims are read as written; caveats and
    unresolved contradictions get their own turns; nothing is paraphrased or invented.
    """
    names = names or {"guide": "Host A", "probe": "Host B"}
    voices = voices or DEFAULT_VOICES
    speakers = [
        Speaker(id="host_a", name=names.get("guide", "Host A"), role=GUIDE_ROLE, voice=dict(voices["guide"])),
        Speaker(id="host_b", name=names.get("probe", "Host B"), role=PROBE_ROLE, voice=dict(voices["probe"])),
    ]
    chapters: list[Chapter] = []
    utterances: list[Utterance] = []

    def add(chapter: Chapter, speaker: str, text: str, *, claim_ids: Optional[list[str]] = None,
            kind: str = "statement") -> None:
        u = Utterance(speaker_id=speaker, text=text, claim_ids=list(claim_ids or []),
                      chapter_id=chapter.id, kind=kind)
        utterances.append(u)
        chapter.utterance_ids.append(u.id)

    overview = Chapter(index=0, title="Overview")
    chapters.append(overview)
    add(overview, "host_a",
        f"This is a {manifest.expertise}-level overview for {manifest.audience}. "
        f"Coverage: {manifest.coverage_summary or 'see sources'}.")
    if manifest.caveats:
        add(overview, "host_b", "What should listeners keep in mind?", kind="question")
        add(overview, "host_a", " ".join(manifest.caveats[:4]), kind="answer")

    body = Chapter(index=1, title="Findings")
    chapters.append(body)
    for claim in manifest.claims:
        if claim.status == "retracted":
            continue
        add(body, "host_a", claim.text, claim_ids=[claim.id])
        if include_questions and (claim.caveats or claim.status != "supported" or claim.confidence_basis):
            probe = "What supports that, and how strong is it?"
            add(body, "host_b", probe, kind="question")
            answer_bits: list[str] = []
            if claim.confidence_basis:
                answer_bits.append(f"Basis: {claim.confidence_basis}.")
            if claim.caveats:
                answer_bits.append(" ".join(claim.caveats[:2]))
            if claim.status != "supported":
                answer_bits.append(f"Status: {claim.status.replace('_', ' ')}.")
            add(body, "host_a", " ".join(answer_bits) or "That claim rests on the cited source.",
                claim_ids=[claim.id], kind="answer")

    if manifest.contradictions:
        limits = Chapter(index=2, title="Unresolved points")
        chapters.append(limits)
        for cx in manifest.contradictions:
            if cx.status != "unresolved":
                continue
            add(limits, "host_b", "Where do the sources disagree?", kind="question")
            add(limits, "host_a", cx.description, claim_ids=list(cx.claim_ids), kind="answer")

    return Script(manifest_id=manifest.id, manifest_revision=manifest.revision, version=version,
                  language=manifest.language, speakers=speakers, chapters=chapters,
                  utterances=utterances)
