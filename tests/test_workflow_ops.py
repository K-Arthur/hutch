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
