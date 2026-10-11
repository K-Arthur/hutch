"""Authoring contract tests: grounded prompts, strict parsing, honest offline drafts."""

from __future__ import annotations

import pytest

from hutch.synthesis.authoring import (
    ScriptRejected,
    authoring_prompt,
    deterministic_draft,
    parse_authored_script,
)
from hutch.synthesis.model import (
    Claim,
    Contradiction,
    CoverageGap,
    EvidenceSpan,
    Quantity,
    SourceCoverage,
    SourceRecord,
    SynthesisManifest,
    utterance_number_problems,
)
from hutch.synthesis.tts import plan_segments


def _manifest(policy: str = "source_only") -> SynthesisManifest:
    src = SourceRecord(kind="paper", identity="test://paper", title="On Caches",
                       author="A. Author", coverage=SourceCoverage(
                           state="partial", expected_units=20, accessible_units=18,
                           gaps=[CoverageGap(reason="truncated", where="pages 19-20")]))
    span = EvidenceSpan(source_id=src.id, source_revision=1, container="page",
                        locator={"page": 3}, quote="the hit rate rose 12%", quote_kind="quoted")
    claim_a = Claim(id="cl_a", text="The hit rate rose 12% with the larger cache.",
                    kind="measurement", attribution="Section 4", spans=[span.id],
                    quantities=[Quantity(value=12.0, unit="%", as_reported="hit rate rose 12%")],
                    caveats=["measured on one workload"], confidence_basis="single source")
    claim_b = Claim(id="cl_b", text="The authors propose a two-tier eviction policy.",
                    kind="design_proposal", spans=[span.id])
    manifest = SynthesisManifest(
        id="syn_" + "3" * 16, sources=[src], spans=[span], claims=[claim_a, claim_b],
        audience="engineers", expertise="informed", language="en",
        coverage_summary="18 of 20 pages accessible", caveats=["one workload only"],
        contradictions=[Contradiction(group="g", claim_ids=["cl_a"], description="one region disagreed")],
        policy=policy,
    )
    return manifest


def test_prompt_contains_plan_and_bans_outside_facts():
    prompt = authoring_prompt(_manifest())
    assert "[cl_a]" in prompt["user"] and "12%" in prompt["user"]
    assert "18 of 20 pages accessible" in prompt["user"]
    assert "engineers" in prompt["user"]
    assert "Source-only mode" in prompt["user"]
    assert "never state a fact" in prompt["system"]
    assert "style" in prompt["system"]  # delivery notes separated from transcript


def test_parse_accepts_grounded_draft_and_binds_claims():
    payload = {
        "chapters": [{"title": "Findings", "utterances": [
            {"speaker": "guide", "text": "The hit rate rose 12% in their measurements.",
             "claim_ids": ["cl_a"]},
            {"speaker": "probe", "kind": "question", "text": "What caveat applies?",
             "claim_ids": ["cl_a"]},
            {"speaker": "guide", "kind": "answer", "text": "It was one workload.",
             "claim_ids": ["cl_a"], "style": "measured"},
        ]}]
    }
    script = parse_authored_script(payload, _manifest())
    assert [s.role for s in script.speakers] == ["guide", "probe"]
    assert script.utterances[0].claim_ids == ["cl_a"]
    assert script.utterances[2].style == "measured"
    plan_segments(script, manifest=_manifest())  # validates cleanly


def test_parse_rejects_unknown_claims_invented_numbers_and_directions():
    bad_claims = {"chapters": [{"title": "x", "utterances": [
        {"speaker": "guide", "text": "A fact.", "claim_ids": ["cl_missing"]}]}]}
    with pytest.raises(ScriptRejected) as exc:
        parse_authored_script(bad_claims, _manifest())
    assert "unknown claim ids" in str(exc.value)

    invented = {"chapters": [{"title": "x", "utterances": [
        {"speaker": "guide", "text": "The rate rose 43%.", "claim_ids": ["cl_a"]}]}]}
    with pytest.raises(ScriptRejected) as exc:
        parse_authored_script(invented, _manifest())
    assert "43" in str(exc.value)

    directed = {"chapters": [{"title": "x", "utterances": [
        {"speaker": "guide", "text": "So <smiling slyly> the rate rose 12%.", "claim_ids": ["cl_a"]}]}]}
    with pytest.raises(ScriptRejected) as exc:
        parse_authored_script(directed, _manifest())
    assert "stage" in str(exc.value) or "tag" in str(exc.value)

    wrong_speaker = {"chapters": [{"title": "x", "utterances": [
        {"speaker": "narrator", "text": "Hi."}]}]}
    with pytest.raises(ScriptRejected) as exc:
        parse_authored_script(wrong_speaker, _manifest())
    assert "speaker must be" in str(exc.value)


def test_parse_strips_json_fences():
    fenced = "```json\n{\"chapters\": [{\"title\": \"x\", \"utterances\": [" \
             "{\"speaker\": \"guide\", \"text\": \"Plain.\"}]}]}\n```"
    script = parse_authored_script(fenced, _manifest())
    assert script.utterances[0].text == "Plain."


def test_deterministic_draft_is_grounded_and_labeled_plain():
    manifest = _manifest()
    script = deterministic_draft(manifest)
    assert len(script.speakers) == 2
    texts = [u.text for u in script.utterances]
    assert any("18 of 20 pages accessible" in t for t in texts)
    assert any(t == "The hit rate rose 12% with the larger cache." for t in texts)
    assert any("one region disagreed" in t for t in texts)  # unresolved contradiction surfaced
    # every claim-bearing utterance maps to a real claim and passes the number checker
    for u in script.utterances:
        for cid in u.claim_ids:
            assert manifest.claim(cid) is not None
        assert utterance_number_problems(u, manifest) == []
    # the segments the TTS layer would build validate against the manifest
    segs = plan_segments(script, manifest=manifest)
    assert segs and all(s.chars > 0 for s in segs)
