from __future__ import annotations

import pytest

from hutch.workflow.ops import apply_op


def test_bar_chart_svg_is_deterministic_accessible_and_escapes_labels():
    values = {"hardware": 4, 'R&D <"special">': 2}
    svg = apply_op("bar_chart_svg", {"values": values, "title": "Spend & volume"})

    assert svg == apply_op("bar_chart_svg", {"values": values, "title": "Spend & volume"})
    assert 'role="img" aria-labelledby="chart-title chart-description"' in svg
    assert "Spend &amp; volume" in svg
    assert "R&amp;D &lt;&quot;special&quot;&gt;" in svg
    assert '<desc id="chart-description">hardware: 4; R&amp;D &lt;&quot;special&quot;&gt;: 2</desc>' in svg
    assert ">4</text>" in svg and ">2</text>" in svg
    assert "<script" not in svg


def test_bar_chart_svg_handles_empty_data_without_inventing_a_bar():
    svg = apply_op("bar_chart_svg", {"values": {}})

    assert 'height="112"' in svg
    assert "No categories are available." in svg
    assert "<rect x=\"260\"" not in svg


def test_bar_chart_svg_scales_large_finite_values_without_overflow():
    svg = apply_op("bar_chart_svg", {"values": {"large": 1e308, "small": 1e307}})

    assert 'width="380"' in svg and ">1e+308</text>" in svg


@pytest.mark.parametrize("values", [
    {str(index): 1 for index in range(21)},
    {"negative": -1},
    {"boolean": True},
    {"not-number": "3"},
    {"not-finite": float("nan")},
    {"not-finite": float("inf")},
    {"not-finite": 10 ** 1000},
    {"": 1},
    {"x" * 81: 1},
])
def test_bar_chart_svg_rejects_ambiguous_or_unbounded_data(values):
    with pytest.raises(ValueError):
        apply_op("bar_chart_svg", {"values": values})


def test_bar_chart_svg_rejects_a_missing_or_overlong_title():
    with pytest.raises(ValueError, match="title"):
        apply_op("bar_chart_svg", {"values": {"hardware": 1}, "title": " "})
    with pytest.raises(ValueError, match="title"):
        apply_op("bar_chart_svg", {"values": {"hardware": 1}, "title": "x" * 161})


def test_document_coverage_requires_complete_discovery_and_verbatim_source_evidence():
    result = apply_op("document_coverage", {
        "discovered": ["a.md", "b.md"],
        "reviews": [{"path": "a.md", "source": "The service keeps monthly reports.",
                     "review": {"path": "a.md", "findings": ["Reports are monthly."],
                                "evidence": ["keeps monthly reports"]}}],
        "skipped": ["b.md"],
        "failures": [{"key": "b.md", "reason": "worker output did not satisfy its schema"}],
        "listing_complete": True,
    })

    assert result == {
        "complete": False,
        "discovery_complete": True,
        "discovered_count": 2,
        "covered_count": 1,
        "covered": [{"path": "a.md", "findings": ["Reports are monthly."],
                     "evidence": ["keeps monthly reports"]}],
        "omissions": [{"path": "b.md", "reason": "worker output did not satisfy its schema"}],
    }


def test_document_coverage_rejects_failure_details_hidden_from_the_skipped_paths():
    with pytest.raises(ValueError, match="also be present in skipped paths"):
        apply_op("document_coverage", {
            "discovered": ["a.md"], "reviews": [], "skipped": [],
            "failures": [{"key": "a.md", "reason": "worker failed"}],
            "listing_complete": True,
        })


@pytest.mark.parametrize("entry,listing_complete,expected_covered", [
    ({"path": "a.md", "source": "Report is ready.", "source_truncated": True,
      "review": {"path": "a.md", "findings": ["Ready."], "evidence": ["Report is ready"]}}, True, 0),
    ({"path": "a.md", "source": "Report is ready.", "source_truncated": False,
      "review": {"path": "a.md", "findings": ["Ready."], "evidence": ["This quote is invented"]}}, True, 0),
    ({"path": "a.md", "source": "Report is ready.", "source_truncated": False,
      "review": {"path": "wrong.md", "findings": ["Ready."], "evidence": ["Report is ready"]}}, True, 0),
    ({"path": "a.md", "source": "Report is ready.", "source_truncated": False,
      "review": {"path": "a.md", "findings": ["Ready."], "evidence": ["Report is ready"]}}, False, 1),
])
def test_document_coverage_does_not_certify_incomplete_or_unanchored_sources(
        entry, listing_complete, expected_covered):
    result = apply_op("document_coverage", {
        "discovered": ["a.md"], "reviews": [entry], "skipped": [], "failures": [],
        "listing_complete": listing_complete,
    })
    assert result["complete"] is False
    assert len(result["covered"]) == expected_covered
    assert result["omissions"]
