"""Write the evidence files and translate findings into a process exit code."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from responsive import config

ALL_FAILURE_KINDS = ("overflow", "errors", "external", "ready", "state", "meta",
                     "touch24", "contrast")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_metadata() -> dict:
    """Record the exact working-tree state the measurements ran against."""
    def run(*args: str) -> str:
        result = subprocess.run(list(args), cwd=str(config.REPO_ROOT), capture_output=True,
                                text=True, check=False)
        return result.stdout

    sha = run("git", "rev-parse", "--short", "HEAD").strip() or "unknown"
    dirty = [line for line in run("git", "status", "--porcelain").splitlines() if line.strip()]
    return {"sha": sha, "dirty_entries": len(dirty)}


def resolve_failure_kinds(fail_on: str) -> set[str]:
    """Expand the --fail-on selector into the kinds that should fail the run."""
    kinds = {kind.strip() for kind in fail_on.split(",") if kind.strip()}
    if "all" in kinds:
        return set(ALL_FAILURE_KINDS)
    return kinds & set(ALL_FAILURE_KINDS)


def exit_code(summary: dict, fail_on: str) -> int:
    failing = resolve_failure_kinds(fail_on)
    if not failing:
        return 0
    return 1 if any(failure["kind"] in failing for failure in summary["failures"]) else 0


def _count_by_kind(entries: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    return dict(sorted(counts.items()))


def _failure_lines(summary: dict) -> list[str]:
    lines = []
    for failure in summary["failures"][:80]:
        lines.append("  %-8s %-16s %-20s %s" % (
            failure["kind"], failure.get("surface", "-"), failure.get("viewport", "-"),
            failure.get("detail", "")))
    if len(summary["failures"]) > 80:
        lines.append("  ... %d more failures, see summary.json" % (len(summary["failures"]) - 80))
    return lines


def _assertion_lines(summary: dict, fail_on: str) -> list[str]:
    viewports = len(summary["viewports"])
    surfaces = len(summary["surfaces"])
    results = summary["results"]
    overflow = sum(1 for record in results if record["overflow_px"] > 0)
    ready = sum(1 for record in results if not record["ready"])
    errors = sum(1 for record in results if record["page_errors"])
    external = sum(1 for record in results if record["external_requests"])
    contract = [record for record in results if record.get("viewport_contract")]
    contract_bad = sum(1 for record in contract
                       if not (record["viewport_contract"].get("present")
                               and record["viewport_contract"].get("width_device")
                               and record["viewport_contract"].get("viewport_fit_cover")))
    touch_records = [record for record in results if record.get("targets")]
    touch_min = sum(1 for record in touch_records if record["targets"]["under_min_count"])
    touch_comfort = sum(1 for record in touch_records if record["targets"]["under_comfort_count"])
    contrast_records = [record for record in results if record.get("contrast")]
    contrast_bad = sum(1 for record in contrast_records if record["contrast"]["violation_count"])

    lines = [
        "Responsive validation: %s" % summary["label"],
        "Generated: %s" % summary["generated_at"],
        "Git: %s (uncommitted worktree entries: %d)" % (
            summary["git"]["sha"], summary["git"]["dirty_entries"]),
        "Matrix: %d surfaces x %d viewports = %d measurements" % (surfaces, viewports, len(results)),
        "Fail-on: %s" % (", ".join(summary["fail_on"]) or "(none)"),
        "",
        "ASSERTIONS",
        "  horizontal overflow: %d/%d measuring pairs overflow" % (overflow, len(results)),
        "  ready selector:      %d/%d pairs did not render" % (ready, len(results)),
        "  page errors:         %d/%d pairs raised" % (errors, len(results)),
        "  non-local requests:  %d/%d pairs made one" % (external, len(results)),
        "  viewport contract:   %d/%d pairs missing width=device-width or viewport-fit=cover" % (
            contract_bad, len(contract)),
        "  touch targets < %dpx: %d/%d coarse-pointer pairs" % (
            config.MIN_TARGET_PX, touch_min, len(touch_records)),
        "  touch targets < %dpx: %d/%d coarse-pointer pairs (comfort warning)" % (
            config.COMFORT_TARGET_PX, touch_comfort, len(touch_records)),
        "  contrast < WCAG AA:  %d/%d sampled pairs" % (contrast_bad, len(contrast_records)),
        "",
        "FAILURES (%d)" % len(summary["failures"]),
    ]
    lines.extend(_failure_lines(summary))
    lines.extend([
        "",
        "WARNINGS (%d): %s" % (len(summary["warnings"]), _count_by_kind(summary["warnings"])),
        "",
        "SCREENSHOTS (%d)" % len(summary["screenshots"]),
    ])
    lines.extend("  %s" % path for path in summary["screenshots"][:80])
    lines.extend(["", "STATES (%d)" % len(summary["states"])])
    lines.extend("  %-28s %s" % (state["name"], state["screenshot"])
                 for state in summary["states"])
    lines.extend([
        "",
        "NOTE: measurements ran against the current working tree. Uncommitted changes",
        "owned by another session may be present; this task never stages them.",
        "",
        "RESULT: %s" % ("PASS" if not any(
            failure["kind"] in resolve_failure_kinds(fail_on)
            for failure in summary["failures"]) else "FAIL"),
    ])
    return lines


def write_outputs(summary: dict, output_dir: Path) -> None:
    """Write summary.json and assertions.txt into the evidence directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    lines = _assertion_lines(summary, ",".join(summary["fail_on"]))
    (output_dir / "assertions.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
