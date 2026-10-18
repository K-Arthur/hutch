"""Contract tests for the versioned synthesis manifest.

These pin the rules the mission names explicitly: source-versioned evidence, no fake
corroboration, no numeric confidence, missing values stay missing, corrections invalidate
dependents instead of silently leaving stale exports, and spoken text carries no stage
directions.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hutch.synthesis.model import (
    Chapter,
    Claim,
    Contradiction,
    CoverageGap,
    EnrichmentNote,
    EvidenceSpan,
    OutputRef,
    Quantity,
    Script,
    SourceCoverage,
    SourceRecord,
    Speaker,
    SynthesisManifest,
    Utterance,
    diff_claims,
    invalidate_outputs,
    next_output_version,
    spoken_text_problems,
    utterance_number_problems,
)


def _source(identity="https://example.org/a", *, cluster="", revision=1, coverage=None):
    return SourceRecord(
        kind="thread",
        identity=identity,
        revision=revision,
        author="Author",
        origin_cluster=cluster or identity,
        coverage=coverage or SourceCoverage(state="complete", expected_units=3, accessible_units=3),
    )


def _span(source, **kw):
    locator = kw.pop("locator", {"post_id": "p1"})
    container = kw.pop("container", "post")
    from hutch.synthesis.model import new_id

    return EvidenceSpan(id=kw.pop("id", None) or new_id("spn"), source_id=source.id,
                        source_revision=source.revision, container=container, locator=locator, **kw)


# ---------------------------------------------------------------------------
# coverage honesty


def test_coverage_statement_and_states():
    c = SourceCoverage(state="partial", expected_units=20, accessible_units=18,
                       gaps=[CoverageGap(reason="deleted", where="post p9")])
    assert c.statement == "18 of 20 accessible"

    with pytest.raises(ValidationError):
        SourceCoverage(state="complete", expected_units=3, accessible_units=3,
                       gaps=[CoverageGap(reason="deleted")])

    with pytest.raises(ValidationError):
        SourceCoverage(state="partial", expected_units=3, accessible_units=3)

    with pytest.raises(ValidationError):
        SourceCoverage(state="complete", expected_units=3, accessible_units=5)


# ---------------------------------------------------------------------------
# referential integrity


def test_claim_span_must_exist():
    src = _source()
    with pytest.raises(ValidationError):
        SynthesisManifest(sources=[src], spans=[], claims=[Claim(text="x", spans=["spn_missing"])])


def test_span_source_and_revision_must_exist():
    src = _source(revision=1)
    bad_rev = EvidenceSpan(source_id=src.id, source_revision=2, container="post",
                           locator={"post_id": "p1"})
    with pytest.raises(ValidationError):
        SynthesisManifest(sources=[src], spans=[bad_rev])
    orphan = EvidenceSpan(source_id="src_missing", source_revision=1, container="post",
                          locator={"post_id": "p1"})
    with pytest.raises(ValidationError):
        SynthesisManifest(sources=[src], spans=[orphan])


def test_span_locator_shape():
    src = _source()
    with pytest.raises(ValidationError):
        EvidenceSpan(source_id=src.id, container="page", locator={})
    with pytest.raises(ValidationError):
        EvidenceSpan(source_id=src.id, container="char", locator={"char_start": 5, "char_end": 5},
                     quote_kind="paraphrased")
    with pytest.raises(ValidationError):
        EvidenceSpan(source_id=src.id, container="post", locator={"post_id": "p1"},
                     quote_kind="quoted", quote="")


# ---------------------------------------------------------------------------
# corroboration independence


def test_two_hosts_agreeing_is_not_corroboration():
    a = _source("https://example.org/a", cluster="a")
    b = _source("https://mirror.example.org/a", cluster="a")  # same origin cluster
    span_a = _span(a)
    span_b = _span(b)
    with pytest.raises(ValidationError) as exc:
        SynthesisManifest(
            sources=[a, b], spans=[span_a, span_b],
            claims=[Claim(text="shared claim", spans=[span_a.id], corroboration=[span_b.id])],
        )
    assert "origin cluster" in str(exc.value)


def test_same_source_corroboration_rejected():
    a = _source()
    s1, s2 = _span(a), _span(a)
    with pytest.raises(ValidationError) as exc:
        SynthesisManifest(
            sources=[a], spans=[s1, s2],
            claims=[Claim(text="claim", spans=[s1.id], corroboration=[s2.id])],
        )
    assert "one source" in str(exc.value)


def test_independent_corroboration_accepted():
    a = _source("https://example.org/a", cluster="a")
    b = _source("https://other.org/b", cluster="b")
    s1, s2 = _span(a), _span(b)
    m = SynthesisManifest(
        sources=[a, b], spans=[s1, s2],
        claims=[Claim(text="claim", spans=[s1.id], corroboration=[s2.id],
                      confidence_basis="independent x2")],
    )
    assert m.claims[0].corroboration == [s2.id]


# ---------------------------------------------------------------------------
# quantities: missing is not zero; percentages are not percentage points


def test_quantity_requires_exact_reported_text():
    with pytest.raises(ValidationError):
        Quantity(value=12.0, unit="%", as_reported="")
    q = Quantity(value=12.0, unit="pp", change_kind="percentage_point_change",
                 qualifier="about", as_reported="up about 12 percentage points")
    assert q.value == 12.0 and q.change_kind == "percentage_point_change"


def test_missing_value_is_not_zero():
    # A manifest can state that a value is unknown without fabricating 0.
    claim = Claim(text="the reported improvement is listed only in prose", kind="author_claim")
    assert claim.quantities == []
    with pytest.raises(ValidationError):
        # pydantic refuses a Quantity without as_reported even when value is set
        Quantity(value=0.0, unit="%", as_reported="")


# ---------------------------------------------------------------------------
# enrichment policy


def test_source_only_default_refuses_enrichment():
    with pytest.raises(ValidationError):
        SynthesisManifest(policy="source_only", enrichment=EnrichmentNote(authorized_by="owner"))
    with pytest.raises(ValidationError):
        SynthesisManifest(policy="enriched", enrichment=EnrichmentNote(reason="no authorizer"))
    m = SynthesisManifest(policy="enriched",
                          enrichment=EnrichmentNote(authorized_by="owner", as_of="2026-10-11T00:00:00Z"))
    assert m.enrichment is not None and m.enrichment.as_of


# ---------------------------------------------------------------------------
# invalidation: corrections reach dependents


def _manifest_with_outputs():
    src = _source()
    span = _span(src)
    claim = Claim(text="the rate rose 12%", spans=[span.id],
                  quantities=[Quantity(value=12.0, unit="%", as_reported="12%")])
    audio = OutputRef(kind="audio_overview", version=1, status="validated",
                      depends_on_claim_ids=[claim.id])
    info = OutputRef(kind="infographic", version=1, status="validated",
                     depends_on_claim_ids=[claim.id])
    unrelated = OutputRef(kind="brief", version=1, status="validated", depends_on_claim_ids=[])
    m = SynthesisManifest(sources=[src], spans=[span], claims=[claim],
                          outputs=[audio, info, unrelated])
    return m, src, span, claim, audio, info, unrelated


def test_diff_claims_detects_number_correction():
    m, _src, _span, claim, *_ = _manifest_with_outputs()
    corrected = m.model_copy(deep=True)
    c = corrected.claim(claim.id)
    c.quantities = [Quantity(value=21.0, unit="%", as_reported="21%")]
    c.text = "the rate rose 21%"
    changes = diff_claims(m, corrected)
    assert [ch.claim_id for ch in changes] == [claim.id]
    assert "quantities" in changes[0].fields and "text" in changes[0].fields


def test_invalidate_marks_only_dependent_outputs():
    m, _src, _span, claim, audio, info, unrelated = _manifest_with_outputs()
    touched = invalidate_outputs(m, {claim.id}, reason="claim text corrected in revision 2")
    assert set(touched) == {audio.id, info.id}
    assert m.output(audio.id).status == "stale"
    assert "revision 2" in m.output(audio.id).stale_reason
    assert m.output(unrelated.id).status == "validated"

    superseded = OutputRef(kind="audio_overview", version=0, status="superseded",
                           depends_on_claim_ids=[claim.id])
    m.outputs.append(superseded)
    touched2 = invalidate_outputs(m, {claim.id}, reason="again")
    assert superseded.id not in touched2  # prior versions are not re-marked


def test_output_versions_increase_per_kind():
    m, *_ = _manifest_with_outputs()
    assert next_output_version(m, "audio_overview") == 2
    assert next_output_version(m, "infographic") == 2
    assert next_output_version(m, "table") == 1


def test_contradiction_references():
    m, _src, _span, claim, *_ = _manifest_with_outputs()
    other = Claim(text="the rate fell")
    m.claims.append(other)
    m.contradictions.append(Contradiction(group="rate-direction", claim_ids=[claim.id, other.id],
                                          description="one says up, one says down"))
    with pytest.raises(ValidationError):
        SynthesisManifest(
            sources=m.sources, spans=m.spans, claims=m.claims,
            contradictions=[Contradiction(group="g", claim_ids=[claim.id, "cl_missing"],
                                          description="bad")],
        )


def test_output_depends_on_unknown_claims_rejected():
    m, _src, _span, _claim, *_ = _manifest_with_outputs()
    with pytest.raises(ValidationError):
        SynthesisManifest(sources=m.sources, spans=m.spans, claims=m.claims,
                          outputs=[OutputRef(kind="brief", depends_on_claim_ids=["cl_missing"])])


# ---------------------------------------------------------------------------
# script contract


def test_script_needs_exactly_two_roles():
    with pytest.raises(ValidationError):
        Script(manifest_id="syn_x", manifest_revision=1,
               speakers=[Speaker(id="h1", name="A", role="guide")])
    with pytest.raises(ValidationError):
        Script(manifest_id="syn_x", manifest_revision=1,
               speakers=[Speaker(id="h1", name="A", role="guide"),
                         Speaker(id="h2", name="B", role="probe"),
                         Speaker(id="h3", name="C", role="probe")])


def test_script_unknown_speaker_and_chapter():
    chapter = Chapter(index=0, title="Intro")
    with pytest.raises(ValidationError):
        Script(manifest_id="syn_x", manifest_revision=1,
               speakers=[Speaker(id="h1", name="A", role="guide"),
                         Speaker(id="h2", name="B", role="probe")],
               chapters=[chapter],
               utterances=[Utterance(speaker_id="h9", text="x", chapter_id=chapter.id)])
    with pytest.raises(ValidationError):
        Script(manifest_id="syn_x", manifest_revision=1,
               speakers=[Speaker(id="h1", name="A", role="guide"),
                         Speaker(id="h2", name="B", role="probe")],
               utterances=[Utterance(speaker_id="h1", text="x", chapter_id="chp_missing")])


# ---------------------------------------------------------------------------
# spoken text: directions are metadata, not transcript


def test_stage_directions_are_flagged_not_spoken():
    assert spoken_text_problems("Hold on. <short pause> Right.") == []
    assert spoken_text_problems("She said <laugh> then left.") == []
    problems = spoken_text_problems("Read this <speaking slowly and dramatically> please")
    assert problems and "would be spoken" in problems[0]

    u = Utterance(speaker_id="h1", text="So <laugh> the number is 42%.", style="warm")
    assert u.style == "warm" and "<laugh>" in u.text  # style never folded into text


def test_utterance_numbers_must_trace_to_manifest_quantities():
    src = _source()
    span = _span(src)
    claim = Claim(text="42% of users", spans=[span.id],
                  quantities=[Quantity(value=42.0, unit="%", as_reported="42% of users")])
    m = SynthesisManifest(sources=[src], spans=[span], claims=[claim])
    ok = Utterance(speaker_id="h1", text="About 42% of users agreed.", claim_ids=[claim.id])
    assert utterance_number_problems(ok, m) == []
    bad = Utterance(speaker_id="h1", text="About 43% of users agreed.", claim_ids=[claim.id])
    assert utterance_number_problems(bad, m)
    # An utterance with no linked claims cannot pretend numbers came from the sources.
    unlinked = Utterance(speaker_id="h1", text="About 43% agreed.", claim_ids=[])
    assert utterance_number_problems(unlinked, m) == []
