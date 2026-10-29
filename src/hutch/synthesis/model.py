"""The versioned synthesis manifest: one evidence revision every output derives from.

This module is the shared contract for grounded synthesis in Hutch. Audio scripts,
infographics, briefs and tables are all renderings of one :class:`SynthesisManifest`
revision; none of them may introduce a fact that is not reachable from it.

Load-bearing rules (each has a test):

* Every claim points at :class:`EvidenceSpan` entries with a source id **and** revision,
  so "which version of the source supported this?" stays answerable after the source
  changes.
* Corroboration is only between spans of *different* sources; two hosts (or two posts of
  the same author, or mirrors of one origin) are never independent corroboration.
* A :class:`Quantity` always carries the exact reported text (``as_reported``). Missing
  values are ``None``, never zero; percentages and percentage-point changes are distinct
  kinds.
* Corrections are events, not edits: claim text is versioned by bumping the manifest
  revision, and :func:`invalidate_outputs` marks exactly the outputs that depended on the
  changed claims as ``stale`` with a reason. Prior output versions stay accessible.
* Utterance text is a verbatim transcript for TTS; delivery lives in ``style``. Only a
  whitelisted set of R3 vocal tags may appear inline in text, and every number spoken in
  an utterance must be traceable to a manifest quantity.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# ids and time


def new_id(prefix: str, n: int = 16) -> str:
    return f"{prefix}_{secrets.token_hex(n // 2)}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now() -> str:
    return utc_now()


# ---------------------------------------------------------------------------
# sources and coverage

SourceKind = Literal["thread", "paper", "web", "document", "media"]

CoverageState = Literal["complete", "partial", "inaccessible", "metadata_only"]

GapReason = Literal[
    "deleted", "protected", "not_fetched", "parse_failure", "truncated", "image_only", "unknown"
]


class CoverageGap(BaseModel):
    """One concrete hole in a source, with where it is and why it exists."""

    model_config = ConfigDict(extra="forbid")

    reason: GapReason = "unknown"
    where: str = ""  # e.g. "between posts P12 and P14" or "pages 22-24"
    note: str = ""


class SourceCoverage(BaseModel):
    """What was actually accessible, not what the source claims to contain."""

    model_config = ConfigDict(extra="forbid")

    state: CoverageState = "complete"
    expected_units: Optional[int] = None  # posts in the thread / pages in the paper
    accessible_units: Optional[int] = None
    statement: str = ""  # "18 of 20 accessible", produced by ingestion, shown to users
    gaps: list[CoverageGap] = Field(default_factory=list)
    limits: list[str] = Field(default_factory=list)  # budgets applied: truncation, caps

    @model_validator(mode="after")
    def _statement_matches_counts(self) -> "SourceCoverage":
        if self.expected_units is not None and self.accessible_units is not None:
            if self.accessible_units > self.expected_units:
                raise ValueError("accessible_units cannot exceed expected_units")
        if not self.statement:
            if self.expected_units is not None and self.accessible_units is not None:
                self.statement = f"{self.accessible_units} of {self.expected_units} accessible"
            elif self.accessible_units is not None:
                self.statement = f"{self.accessible_units} accessible (total unknown)"
            else:
                self.statement = "coverage unknown"
        if self.state == "complete" and self.gaps:
            raise ValueError("coverage state 'complete' cannot carry gaps")
        if self.state == "partial" and not self.gaps and not self.limits:
            raise ValueError("coverage state 'partial' needs at least one gap or limit")
        return self


class SourceRecord(BaseModel):
    """One immutable revision of one source. ``identity`` is stable across revisions."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("src"))
    kind: SourceKind
    identity: str  # canonical URL or platform object id: the stable source identity
    revision: int = 1
    title: str = ""
    author: str = ""  # attribution where known; "" means unknown, not "anonymous"
    origin: str = ""  # domain / platform
    origin_cluster: str = ""  # dedup cluster (mirrors/syndication collapse to one origin)
    published_at: Optional[str] = None
    updated_at: Optional[str] = None
    retrieved_at: str = Field(default_factory=_now)
    content_sha256: str = ""
    language: str = ""
    coverage: SourceCoverage = Field(default_factory=SourceCoverage)
    grounding_source_id: Optional[str] = None  # inv_sources.id when the evidence layer holds it
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("identity")
    @classmethod
    def _identity_required(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("a source identity is required")
        return v


# ---------------------------------------------------------------------------
# evidence spans

Container = Literal["post", "page", "section", "figure", "table", "utterance", "char"]

_LOCATOR_RULES: dict[str, tuple[str, ...]] = {
    "post": ("post_id",),
    "page": ("page",),
    "section": ("section",),
    "figure": ("figure",),
    "table": ("table",),
    "utterance": ("utterance_id",),
    "char": ("char_start", "char_end"),
}


class EvidenceSpan(BaseModel):
    """Exactly where a claim is supported, in a named source revision."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("spn"))
    source_id: str
    source_revision: int = 1
    container: Container
    locator: dict[str, Any] = Field(default_factory=dict)
    quote: str = ""  # verbatim, bounded; "" only with quote_kind "paraphrased"
    quote_kind: Literal["quoted", "paraphrased"] = "paraphrased"
    note: str = ""

    @field_validator("quote")
    @classmethod
    def _quote_bounded(cls, v: str) -> str:
        if len(v) > 2_000:
            raise ValueError("span quotes are bounded to 2000 characters")
        return v

    @model_validator(mode="after")
    def _locator_shape(self) -> "EvidenceSpan":
        required = _LOCATOR_RULES[self.container]
        missing = [k for k in required if self.locator.get(k) in (None, "")]
        if missing:
            raise ValueError(f"container {self.container!r} needs locator keys {missing}")
        if self.container == "char":
            start, end = self.locator.get("char_start"), self.locator.get("char_end")
            if not isinstance(start, int) or not isinstance(end, int) or end <= start:
                raise ValueError("char spans need integer char_start < char_end")
        if self.quote_kind == "quoted" and not self.quote:
            raise ValueError("a quoted span needs its verbatim text")
        return self


# ---------------------------------------------------------------------------
# claims and quantities

ClaimKind = Literal[
    "author_claim",  # the author says it
    "measurement",  # a measured/observed value
    "design_proposal",  # a proposed system/design, not evaluated here
    "evaluated_result",  # a result from an evaluation actually reported
    "estimate",  # a stated approximation
    "opinion",
    "interpretation",  # Hutch's own framing, kept separate from the authors
    "context",  # background needed to read the material
]

ChangeKind = Literal[
    "level",  # a level: "raise of 12%"
    "percentage_change",  # relative change: "12% higher than X"
    "percentage_point_change",  # "up 12 percentage points"
    "ratio",
    "count",
    "duration",
    "other",
]


class Quantity(BaseModel):
    """A number with its unit, change semantics and exact reported text."""

    model_config = ConfigDict(extra="forbid")

    value: float
    unit: str
    change_kind: ChangeKind = "level"
    qualifier: str = ""  # "about", "at least", "up to", as reported
    as_reported: str  # the exact source wording; required so no number is invented
    span_ids: list[str] = Field(default_factory=list)

    @field_validator("as_reported")
    @classmethod
    def _reported_required(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("a quantity must carry the exact reported text")
        return v


class Claim(BaseModel):
    """One atom of synthesizable content, traceable to evidence.

    ``confidence_basis`` is a short *qualitative* phrase ("single source",
    "independent x2", "author's estimate"); this contract deliberately has no numeric
    confidence field.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("cl"))
    text: str
    kind: ClaimKind = "author_claim"
    attribution: str = ""  # "the paper's authors", a host name, "" unknown
    spans: list[str] = Field(default_factory=list)  # EvidenceSpan ids
    corroboration: list[str] = Field(default_factory=list)  # span ids, independent origins only
    quantities: list[Quantity] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    limitation_of: str = ""  # claim id this is a stated limitation of, when applicable
    contradiction_group: str = ""  # claims sharing a group contradict each other
    confidence_basis: str = ""
    status: Literal["supported", "partially_supported", "unresolved", "retracted"] = "supported"

    @field_validator("text")
    @classmethod
    def _text_required(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("claim text is required")
        return v


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("cx"))
    group: str
    claim_ids: list[str]
    description: str
    status: Literal["unresolved", "resolved_by_source", "resolved_by_scope"] = "unresolved"


class EnrichmentNote(BaseModel):
    """Outside research is opt-in and carries its own evidence and freshness boundary."""

    model_config = ConfigDict(extra="forbid")

    authorized_by: str = ""
    reason: str = ""
    as_of: str = ""  # freshness boundary: nothing after this instant was used
    span_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# outputs

OutputKind = Literal["audio_overview", "transcript", "infographic", "brief", "table"]

OutputStatus = Literal["draft", "validated", "failed", "stale", "superseded"]


class OutputRef(BaseModel):
    """A rendered derivative bound to the manifest revision it was made from."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("out"))
    kind: OutputKind
    version: int = 1
    manifest_revision: int = 1
    status: OutputStatus = "draft"
    stale_reason: str = ""
    artifact_sha256: str = ""
    bytes: int = 0
    mime: str = ""
    depends_on_claim_ids: list[str] = Field(default_factory=list)
    depends_on_source_ids: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# the manifest

Expertise = Literal["general", "informed", "expert"]
SynthesisPolicy = Literal["source_only", "enriched"]
LengthClass = Literal["shorter", "default", "longer"]


class DepthPlan(BaseModel):
    """Intended depth for every format at once; ``reason`` records omissions."""

    model_config = ConfigDict(extra="forbid")

    length_class: LengthClass = "default"
    target_minutes: Optional[float] = None
    target_words: Optional[int] = None
    dimensions: Optional[str] = None  # e.g. "1080x1350" for an infographic
    reason: str = ""  # what was omitted for the requested length and why


class SynthesisManifest(BaseModel):
    """One approved evidence revision. Outputs never invent facts outside it."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("syn"))
    revision: int = 1
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    conversation_id: str = ""
    bot_id: str = ""
    run_id: str = ""

    sources: list[SourceRecord] = Field(default_factory=list)
    spans: list[EvidenceSpan] = Field(default_factory=list)
    coverage_summary: str = ""

    audience: str = "a general listener"
    expertise: Expertise = "general"
    tone: str = "conversational"
    language: str = "en"
    depth: DepthPlan = Field(default_factory=DepthPlan)
    policy: SynthesisPolicy = "source_only"
    enrichment: Optional[EnrichmentNote] = None

    claims: list[Claim] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)  # interpretation separation notes

    settings: dict[str, Any] = Field(default_factory=dict)
    outputs: list[OutputRef] = Field(default_factory=list)

    # -- lookups -----------------------------------------------------------
    def source(self, source_id: str) -> Optional[SourceRecord]:
        return next((s for s in self.sources if s.id == source_id), None)

    def span(self, span_id: str) -> Optional[EvidenceSpan]:
        return next((s for s in self.spans if s.id == span_id), None)

    def claim(self, claim_id: str) -> Optional[Claim]:
        return next((c for c in self.claims if c.id == claim_id), None)

    def output(self, output_id: str) -> Optional[OutputRef]:
        return next((o for o in self.outputs if o.id == output_id), None)

    def spans_of_source(self, source_id: str) -> list[EvidenceSpan]:
        return [s for s in self.spans if s.source_id == source_id]

    def claims_of_span(self, span_id: str) -> list[Claim]:
        return [c for c in self.claims if span_id in c.spans or span_id in c.corroboration]

    # -- validation ----------------------------------------------------------
    @model_validator(mode="after")
    def _referential_integrity(self) -> "SynthesisManifest":
        source_ids = [s.id for s in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source ids must be unique within a manifest revision")
        source_id_set = set(source_ids)

        span_ids = [s.id for s in self.spans]
        if len(set(span_ids)) != len(span_ids):
            raise ValueError("span ids must be unique within a manifest revision")
        span_id_set = set(span_ids)
        for span in self.spans:
            if span.source_id not in source_id_set:
                raise ValueError(f"span {span.id} references unknown source {span.source_id}")
            src = self.source(span.source_id)
            if src is not None and span.source_revision > src.revision:
                raise ValueError(
                    f"span {span.id} claims source revision {span.source_revision} but "
                    f"source {src.id} is at revision {src.revision}"
                )

        claim_ids = [c.id for c in self.claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("claim ids must be unique within a manifest revision")
        claim_id_set = set(claim_ids)

        for claim in self.claims:
            unknown = [s for s in claim.spans if s not in span_id_set]
            if unknown:
                raise ValueError(f"claim {claim.id} references unknown spans {unknown}")
            unknown_corr = [s for s in claim.corroboration if s not in span_id_set]
            if unknown_corr:
                raise ValueError(f"claim {claim.id} corroborates with unknown spans {unknown_corr}")
            for q in claim.quantities:
                unknown_q = [s for s in q.span_ids if s not in span_id_set]
                if unknown_q:
                    raise ValueError(f"claim {claim.id} quantity has unknown spans {unknown_q}")
            if claim.corroboration:
                self._check_independent_corroboration(claim)

        for cx in self.contradictions:
            unknown = [cid for cid in cx.claim_ids if cid not in claim_id_set]
            if unknown:
                raise ValueError(f"contradiction {cx.id} references unknown claims {unknown}")

        for out in self.outputs:
            unknown = [cid for cid in out.depends_on_claim_ids if cid not in claim_id_set]
            if unknown:
                raise ValueError(f"output {out.id} depends on unknown claims {unknown}")
            unknown_src = [sid for sid in out.depends_on_source_ids if sid not in source_id_set]
            if unknown_src:
                raise ValueError(f"output {out.id} depends on unknown sources {unknown_src}")

        if self.policy == "source_only" and self.enrichment is not None:
            raise ValueError("source_only synthesis cannot carry an enrichment note")
        if self.policy == "enriched" and (self.enrichment is None or not self.enrichment.authorized_by):
            raise ValueError("enriched synthesis needs an authorized enrichment note")
        return self

    def _check_independent_corroboration(self, claim: Claim) -> None:
        """Corroboration must come from a different source *and* origin cluster.

        Two mirrors of one article, two posts of one author, or the two hosts agreeing
        are not independent. This raises instead of silently accepting them.
        """
        supports = list(dict.fromkeys(claim.spans + claim.corroboration))
        by_source: dict[str, list[str]] = {}
        for sid in supports:
            span = self.span(sid)
            if span is None:
                continue
            by_source.setdefault(span.source_id, []).append(sid)
        if len(by_source) < 2:
            raise ValueError(
                f"claim {claim.id} marks corroboration but all spans come from one source"
            )
        clusters = set()
        for source_id in by_source:
            src = self.source(source_id)
            if src is None:
                continue
            clusters.add(src.origin_cluster or src.identity)
        if len(clusters) < 2:
            raise ValueError(
                f"claim {claim.id} marks corroboration from one origin cluster only"
            )


# ---------------------------------------------------------------------------
# script (speaker turns)

SpeakerRole = Literal["guide", "probe"]  # guide explains; probe tests mechanisms/limits


class Speaker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str  # stable: "host_a"/"host_b"
    name: str
    role: SpeakerRole
    voice: dict[str, str] = Field(default_factory=dict)  # provider -> voice id


class Utterance(BaseModel):
    """One spoken turn. ``text`` is verbatim; ``style`` never enters the transcript."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("utt"))
    speaker_id: str
    text: str
    claim_ids: list[str] = Field(default_factory=list)
    span_ids: list[str] = Field(default_factory=list)
    chapter_id: str = ""
    style: str = ""  # turn-level delivery metadata only (R3)
    pause_after_ms: int = 0
    kind: Literal["statement", "question", "answer", "transition"] = "statement"


class Chapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("chp"))
    index: int
    title: str
    utterance_ids: list[str] = Field(default_factory=list)


class Script(BaseModel):
    """A two-host script revision, frozen for TTS. Never contains new facts."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: new_id("scr"))
    manifest_id: str
    manifest_revision: int
    version: int = 1
    language: str = "en"
    speakers: list[Speaker]
    chapters: list[Chapter] = Field(default_factory=list)
    utterances: list[Utterance] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    status: Literal["draft", "approved", "superseded"] = "draft"

    @model_validator(mode="after")
    def _shape(self) -> "Script":
        ids = [s.id for s in self.speakers]
        if len(ids) != len(set(ids)):
            raise ValueError("speaker ids must be unique")
        if len(ids) < 2:
            raise ValueError("a two-host script needs two stable speakers")
        roles = sorted(s.role for s in self.speakers)
        if roles != ["guide", "probe"]:
            raise ValueError("exactly one guide and one probe speaker are required")
        utt_ids = [u.id for u in self.utterances]
        if len(utt_ids) != len(set(utt_ids)):
            raise ValueError("utterance ids must be unique")
        for u in self.utterances:
            if u.speaker_id not in ids:
                raise ValueError(f"utterance {u.id} has unknown speaker {u.speaker_id}")
        chapter_ids = {c.id for c in self.chapters}
        for u in self.utterances:
            if u.chapter_id and u.chapter_id not in chapter_ids:
                raise ValueError(f"utterance {u.id} has unknown chapter {u.chapter_id}")
        return self


# R3 whitelisted point-in-time vocal tags; anything else inside angle brackets is a
# stage direction that must not be spoken.
VOCAL_TAGS = {
    "laugh", "laughter", "chuckle", "chuckles", "sigh", "sighs", "breath", "heavy breath",
    "exhales", "cough", "gasp", "giggle", "groan", "grunt", "hmm", "short pause",
    "long pause", "throat-clearing", "whispers", "whispering", "snort", "tsk",
}
_TAG_RE = re.compile(r"<([^<>]{1,40})>")


def spoken_text_problems(text: str) -> list[str]:
    """Return reasons ``text`` must not go to TTS unchanged."""
    problems: list[str] = []
    for raw in _TAG_RE.findall(text):
        tag = raw.strip().lower()
        if tag not in VOCAL_TAGS:
            problems.append(f"non-vocal tag <{raw}> would be spoken or misread")
    return problems


# ---------------------------------------------------------------------------
# invalidation


class ClaimChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    fields: list[str]  # changed field names ("text", "quantities", ...)


def diff_claims(old: "SynthesisManifest", new: "SynthesisManifest") -> list[ClaimChange]:
    """Which claims changed between two revisions of the same manifest."""
    old_by_id = {c.id: c for c in old.claims}
    new_by_id = {c.id: c for c in new.claims}
    changes: list[ClaimChange] = []
    for cid, before in old_by_id.items():
        after = new_by_id.get(cid)
        if after is None:
            changes.append(ClaimChange(claim_id=cid, fields=["removed"]))
            continue
        fields = [
            name
            for name in (
                "text", "kind", "quantities", "spans", "corroboration", "caveats",
                "status", "attribution",
            )
            if getattr(before, name) != getattr(after, name)
        ]
        if fields:
            changes.append(ClaimChange(claim_id=cid, fields=fields))
    for cid in new_by_id:
        if cid not in old_by_id:
            changes.append(ClaimChange(claim_id=cid, fields=["added"]))
    return changes


def changed_claims_for_sources(manifest: "SynthesisManifest", source_ids: set[str]) -> set[str]:
    """Claims whose evidence lives in any of ``source_ids``.

    When a source revision changes, every claim resting on its spans becomes suspect,    including corroboration spans, which are evidence too.
    """
    hit: set[str] = set()
    span_to_source = {s.id: s.source_id for s in manifest.spans}
    for claim in manifest.claims:
        for sid in list(claim.spans) + list(claim.corroboration):
            if span_to_source.get(sid) in source_ids:
                hit.add(claim.id)
    return hit


def invalidate_outputs(
    manifest: "SynthesisManifest", changed_claim_ids: set[str], *, reason: str
) -> list[str]:
    """Mark dependent outputs stale in place; return the ids that changed.

    Outputs depending on no changed claim are intentionally untouched. The caller
    persists the returned manifest in its own transaction; prior versions remain
    reachable under retention policy.
    """
    touched: list[str] = []
    for out in manifest.outputs:
        if out.status in ("superseded", "failed"):
            continue
        if set(out.depends_on_claim_ids) & changed_claim_ids:
            out.status = "stale"
            out.stale_reason = reason
            touched.append(out.id)
    return touched


def next_output_version(manifest: "SynthesisManifest", kind: OutputKind) -> int:
    versions = [o.version for o in manifest.outputs if o.kind == kind]
    return (max(versions) + 1) if versions else 1


# ---------------------------------------------------------------------------
# number checking: every number an utterance speaks must trace back to a quantity

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|percent(?:age points?)?|pp)?", re.IGNORECASE)


def numbers_in_text(text: str) -> list[str]:
    """Candidate numeric tokens. Deliberately shallow: this flags for checking, it does
    not interpret semantics."""
    return [m.group(0).strip() for m in _NUM_RE.finditer(text or "") if m.group(0).strip()]


def utterance_number_problems(utterance: Utterance, manifest: "SynthesisManifest") -> list[str]:
    """Numbers in an utterance that no linked claim quantity accounts for.

    Matching is by the digits themselves appearing anywhere in a linked quantity's
    ``as_reported`` text: a spoken "42" may come from "42%" but "43" may not.
    """
    if not utterance.claim_ids:
        return []
    allowed_digits: set[str] = set()
    for cid in utterance.claim_ids:
        claim = manifest.claim(cid)
        if claim is None:
            continue
        for q in claim.quantities:
            for token in numbers_in_text(q.as_reported):
                allowed_digits.update(re.findall(r"\d+(?:[.,]\d+)?", token))
    problems: list[str] = []
    for token in numbers_in_text(utterance.text):
        digits = re.findall(r"\d+(?:[.,]\d+)?", token)
        for d in digits:
            if d not in allowed_digits:
                problems.append(f"number {d!r} in utterance {utterance.id} has no manifest quantity")
    return problems
