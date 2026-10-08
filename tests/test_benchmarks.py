from __future__ import annotations

import pytest

from benchmarks.run import METRICS, _percentile, compare, summarize_samples


def _r(**m):
    return {"metrics": m}


def test_twenty_percent_slower_cli_is_a_regression():
    bad = compare(_r(cli_status_ms=370.0), _r(cli_status_ms=280.0))
    assert bad and "cli_status_ms" in bad[0]


def test_within_tolerance_passes():
    assert compare(_r(cli_status_ms=320.0), _r(cli_status_ms=280.0)) == []  # +14%


def test_higher_is_better_metrics_regress_downward():
    assert compare(_r(events_per_sec=30_000), _r(events_per_sec=58_000))
    assert compare(_r(events_per_sec=70_000), _r(events_per_sec=58_000)) == []


def test_tiny_absolute_changes_are_noise():
    # 0.26 ms -> 0.40 ms is +54% but far below the 0.5 ms floor
    assert compare(_r(step_overhead_ms=0.40), _r(step_overhead_ms=0.26)) == []
    # one 10 ms clock tick in an 8 s window is ~4.5 s/hour
    assert compare(_r(idle_cpu_serve_s_per_hour=9.0), _r(idle_cpu_serve_s_per_hour=4.5)) == []


def test_every_draft_target_is_tracked():
    tracked = set(METRICS)
    assert {"idle_cpu_daemon_s_per_hour", "cli_status_ms", "events_per_sec",
            "step_overhead_ms", "idle_rss_daemon_mb"} <= tracked


def test_benchmark_summary_uses_nearest_rank_and_keeps_sample_count() -> None:
    values = [9.0, 1.0, 5.0, 3.0, 7.0]

    assert _percentile(values, 0.90) == 9.0
    assert summarize_samples(values) == {
        "n": 5,
        "median": 5.0,
        "p90": 9.0,
        "min": 1.0,
        "max": 9.0,
    }


def test_benchmark_summary_rejects_missing_measurements() -> None:
    with pytest.raises(ValueError, match="at least one sample"):
        summarize_samples([])
