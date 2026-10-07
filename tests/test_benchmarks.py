"""The regression gate itself (PF-12): >20% worse fails, noise below the floor does not."""

from __future__ import annotations

from benchmarks.run import METRICS, compare


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
    # one 10 ms clock tick in an 8 s window is ~4.5 s/hour: not a regression
    assert compare(_r(idle_cpu_serve_s_per_hour=9.0), _r(idle_cpu_serve_s_per_hour=4.5)) == []


def test_every_draft_target_is_tracked():
    tracked = set(METRICS)
    # PF-5 idle CPU, PF-6 CLI start, PF-7 events/s, PF-11 step overhead, PF-13 idle RSS
    assert {"idle_cpu_daemon_s_per_hour", "cli_status_ms", "events_per_sec",
            "step_overhead_ms", "idle_rss_daemon_mb"} <= tracked
