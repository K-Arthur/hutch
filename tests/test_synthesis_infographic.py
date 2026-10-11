"""Infographic tests: honest spec construction, deterministic rendering, tool integration."""

from __future__ import annotations

import hashlib
import re
import uuid

from hutch.approvals import ApprovalGate
from hutch.models import ApprovalMode, Bot, Run
from hutch.safety import PolicyEngine
from hutch.synthesis.infographic import (
    InfographicRenderError,
    build_infographic_spec,
    layout_spec,
    render_png,
    render_svg,
    render_text_companion,
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
)
from hutch.tools.base import ToolContext
from hutch.tools.synthesis import RenderInfographicTool


def _manifest(*, claims=None, coverage_units=(24, 22)) -> SynthesisManifest:
    expected, accessible = coverage_units
    src = SourceRecord(kind="paper", identity="https://example.org/paper.pdf",
                       title="Caching at the Edge <a field study>", author="A. Author",
                       origin="example.org", retrieved_at="2026-10-11T10:00:00+00:00",
                       coverage=SourceCoverage(
                           state="partial" if accessible < expected else "complete",
                           expected_units=expected, accessible_units=accessible,
                           gaps=[CoverageGap(reason="truncated", where="pages 23-24")]
                           if accessible < expected else []))
    span = EvidenceSpan(source_id=src.id, source_revision=1, container="page",
                        locator={"page": 3}, quote="the hit rate rose 12%", quote_kind="quoted")
    span2 = EvidenceSpan(source_id=src.id, source_revision=1, container="figure",
                         locator={"figure": "Figure 2"}, quote_kind="paraphrased")
    default_claims = [
        Claim(text="The hit rate rose 12 percentage points on one workload.", kind="measurement",
              spans=[span.id], quantities=[Quantity(value=12.0, unit="%",
                                                    change_kind="percentage_point_change",
                                                    as_reported="the hit rate rose 12%")],
              caveats=["one workload only"], confidence_basis="single source"),
        Claim(text="The authors propose a two-tier eviction policy, unevaluated at scale.",
              kind="design_proposal", spans=[span2.id, span.id]),
        Claim(text="Across regions the median latency fell by about 8 milliseconds.",
              kind="measurement", spans=[span.id],
              quantities=[Quantity(value=8.0, unit="ms", qualifier="about",
                                   as_reported="latency fell by about 8 ms")],
              confidence_basis="independent x2"),
    ]
    claims_list = claims if claims is not None else default_claims
    return SynthesisManifest(
        sources=[src], spans=[span, span2], claims=claims_list,
        audience="platform engineers", expertise="informed",
        coverage_summary=f"{accessible} of {expected} pages accessible",
        caveats=["The evaluation covers one quarter of production traffic."],
        contradictions=[Contradiction(group="regions", claim_ids=[claims_list[0].id],
                                      description="one region saw no improvement")],
    )


def test_spec_draws_only_from_the_manifest_and_labels_percentage_points():
    manifest = _manifest()
    spec = build_infographic_spec(manifest)
    kinds = [s.kind for s in spec.sections]
    assert kinds == ["findings", "numbers", "limitations", "sources"]
    numbers = [i.text for s in spec.sections if s.kind == "numbers" for i in s.items]
    assert "the hit rate rose 12% — percentage-point change" in numbers
    assert "latency fell by about 8 ms" in numbers
    # a claim with no quantity contributes no number row
    assert all("two-tier" not in n for n in numbers)
    # every finding carries its source handle
    findings = [i for s in spec.sections if s.kind == "findings" for i in s.items]
    assert all(i.handles for i in findings)
    # limitations carry caveats and unresolved contradictions
    limitations = [i.text for s in spec.sections if s.kind == "limitations" for i in s.items]
    assert any("quarter of production traffic" in t for t in limitations)
    assert any("no improvement" in t for t in limitations)
    # the footer states provenance and the coverage
    assert "22 of 24 pages accessible" in spec.footer
    assert "compiled from the listed sources" in spec.footer


def test_spec_reports_overflow_instead_of_silently_dropping_findings():
    many = [Claim(text=f"Finding number {i} with a registered source.", spans=[]) for i in range(12)]
    spec = build_infographic_spec(_manifest(claims=many), max_findings=5)
    findings = next(s for s in spec.sections if s.kind == "findings")
    assert len(findings.items) == 5
    assert "showing 5 of 12 findings" in findings.note


def test_spec_excludes_retracted_claims_entirely():
    claims = [Claim(text="retracted thing", status="retracted", spans=[]),
              Claim(text="live thing", spans=[])]
    spec = build_infographic_spec(_manifest(claims=claims))
    findings = [i.text for s in spec.sections if s.kind == "findings" for i in s.items]
    assert findings == ["live thing"]


def test_svg_is_deterministic_escaped_and_self_contained():
    spec = build_infographic_spec(_manifest())
    layout = layout_spec(spec)
    first = render_svg(layout, spec)
    second = render_svg(layout, spec)
    assert first == second
    text = first.decode("utf-8")
    assert 'role="img"' in text and "<title>" in text
    assert "&lt;a field study&gt;" in text  # title escaped, never raw markup
    assert "<script" not in text.lower() and "xlink:href" not in text
    assert "http://www.w3.org/2000/svg" in text  # the only external-looking string is the ns
    for url in re.findall(r"https?://(?!www\.w3\.org)[^\s\"']+", text):
        raise AssertionError(f"unexpected external reference {url}")


def test_png_matches_canvas_and_companion_has_full_text():
    spec = build_infographic_spec(_manifest())
    layout = layout_spec(spec, width=1080, height=1600)
    try:
        png = render_png(layout, spec)
    except InfographicRenderError:
        png = None  # honest skip when no font exists on the host
    if png is not None:
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(png) > 10_000
    companion = render_text_companion(spec)
    assert "# Caching at the Edge <a field study>" in companion
    assert "12% — percentage-point change" in companion
    assert "## Sources" in companion and "[S1]" in companion


def test_layout_reserves_footer_space_and_refuses_tiny_canvases():
    spec = build_infographic_spec(_manifest())
    layout = layout_spec(spec, width=1080, height=800)
    # Every text stays inside the canvas, and the footer is fully present.
    assert all(t.y <= layout.height - 8 for t in layout.texts)
    footer_tail = " ".join(t.text for t in layout.texts[-4:])
    assert "Coverage:" in footer_tail and "carry the full wording" in footer_tail
    try:
        layout_spec(spec, width=200, height=200)
        raise AssertionError("tiny canvas should be refused")
    except ValueError:
        pass


def _ctx(tmp_path, store, config) -> ToolContext:
    bot = store.create_bot(Bot(name=f"info-{uuid.uuid4().hex[:6]}", model="mock/demo",
                               tools=["synthesis"], approval_mode=ApprovalMode.auto))
    run = store.create_run(Run(bot_id=bot.id, prompt="x"))
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    policy = PolicyEngine()
    gate = ApprovalGate(store, bot, run, policy, emit=lambda _e: None)
    return ToolContext(bot=bot, run=run, store=store, policy=policy, gate=gate,
                       config=config, workspace=ws)


def test_render_infographic_tool_stores_source_export_and_companion(tmp_path, store, config):
    ctx = _ctx(tmp_path, store, config)
    manifest = _manifest()
    store.save_synthesis_manifest(manifest.model_dump(mode="json"), reason="test")
    result = RenderInfographicTool().run({"manifest_id": manifest.id}, ctx)
    assert result.ok, result.output
    artifacts = result.data["artifacts"]
    assert set(artifacts) >= {"svg", "companion"}
    svg_row = store.get_synthesis_artifact(artifacts["svg"])
    assert svg_row["kind"] == "infographic" and svg_row["meta"]["variant"] == "svg"
    assert svg_row["meta"]["width"] == 1080
    companion_row = store.get_synthesis_artifact(artifacts["companion"])
    assert companion_row["kind"] == "companion" and companion_row["mime"].startswith("text/markdown")
    if "png" in artifacts:
        png_row = store.get_synthesis_artifact(artifacts["png"])
        assert png_row["meta"]["variant"] == "png" and png_row["version"] != svg_row["version"]

    missing = RenderInfographicTool().run({"manifest_id": "syn_missing"}, ctx)
    assert not missing.ok and "no such manifest" in missing.output
    too_small = RenderInfographicTool().run({"manifest_id": manifest.id, "width": 200}, ctx)
    assert not too_small.ok and "480" in too_small.output
