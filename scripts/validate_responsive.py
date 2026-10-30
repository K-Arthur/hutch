#!/usr/bin/env python3
"""Re-runnable responsive validation harness for Hutch.

Boots the real app with a deterministic seeded workspace plus the static
marketing site, measures every selected surface at every selected viewport in
the right pointer mode, captures committed screenshots, and writes
summary.json + assertions.txt under docs/responsive/screenshots/<label>/.

Examples:
  .venv/bin/python scripts/validate_responsive.py --label baseline-2a89909a
  .venv/bin/python scripts/validate_responsive.py --quick --no-screenshots
  .venv/bin/python scripts/validate_responsive.py --label final --fail-on all
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from responsive import capture, config, harness, report  # noqa: E402


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Measure and screenshot Hutch across viewports.")
    parser.add_argument("--label", default="",
                        help="evidence directory name; defaults to the current commit")
    parser.add_argument("--out", default="",
                        help="evidence directory; defaults to docs/responsive/screenshots/<label>")
    parser.add_argument("--fail-on", default="overflow,errors,external,ready,state,meta",
                        help="comma-separated check kinds that fail the run (or all/none)")
    parser.add_argument("--quick", action="store_true",
                        help="three surfaces x three viewports, no screenshots or state captures")
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument("--settle-ms", type=int, default=None)
    parser.add_argument("--surfaces", default="", help="comma-separated surface labels")
    parser.add_argument("--viewports", default="", help="comma-separated viewport labels")
    return parser.parse_args(argv)


def _prepare_environment() -> Path:
    """Isolate state and generated test artifacts outside the checkout."""
    scratch = Path(tempfile.mkdtemp(prefix="hutch-responsive-", dir="/tmp"))
    os.environ.setdefault("HUTCH_TESTING", "1")
    os.environ["HUTCH_STATE_DIR"] = str(scratch / "state")
    os.environ["HUTCH_TEST_ARTIFACTS_DIR"] = str(scratch / "artifacts")
    os.environ.setdefault("HUTCH_MAX_CONCURRENT", "2")
    os.environ.setdefault("HUTCH_SANDBOX", "off")
    return scratch


def main(argv=None) -> int:
    args = _parse_args(argv)
    git = report.git_metadata()
    args.label = args.label or ("worktree-" + git["sha"])
    args.screenshots = not args.no_screenshots
    args.settle_ms = args.settle_ms if args.settle_ms is not None else config.SETTLE_MS
    out_dir = Path(args.out) if args.out else config.DEFAULT_OUTPUT_ROOT / args.label

    scratch = _prepare_environment()
    app = harness.LiveApp()
    site = harness.SiteServer()
    try:
        app_url = app.start()
        site_url = site.start()
        summary = capture.run(app_url, site_url, args, out_dir)
    finally:
        site.stop()
        app.stop()
        shutil.rmtree(scratch, ignore_errors=True)

    summary["git"] = git
    summary["generated_at"] = report.utcnow_iso()
    summary["measurement_note"] = (
        "Measured the current working tree; another session's uncommitted changes may be "
        "present and are never staged by this task.")
    report.write_outputs(summary, out_dir)
    code = report.exit_code(summary, args.fail_on)
    print("responsive validation: %s | failures=%d warnings=%d screenshots=%d" % (
        args.label, len(summary["failures"]), len(summary["warnings"]),
        len(summary["screenshots"])))
    print("evidence: %s" % out_dir)
    print("result: %s" % ("PASS" if code == 0 else "FAIL"))
    return code


if __name__ == "__main__":
    sys.exit(main())
