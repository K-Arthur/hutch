#!/usr/bin/env python3
"""Audit the provider-platform research package against the shipped catalogue and honesty rules.

Usage: python3 scripts/audit_provider_research.py [--json]

Fails when:
- a required document or research draft is missing or too small to be real research;
- a provider in src/hutch/data/providers.json is missing from the capability matrix;
- a matrix row claims live verification although no live-verification artifact exists;
- the validation ledger does not record the no-credentials boundary;
- the research register has too few dated HTTPS sources.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs" / "research" / "2026-10-provider-platform"
DRAFTS = PACKAGE / "drafts"
PROVIDERS = ROOT / "src" / "hutch" / "data" / "providers.json"

REQUIRED_DOCS = (
    "00-SCOPE.md", "01-RESEARCH-REGISTER.md", "02-FAILURES-AND-COMPLAINTS.md",
    "03-PROVIDER-CAPABILITY-MATRIX.md", "04-ARCHITECTURE-AND-ADRS.md", "05-IMPLEMENTATION-PLAN.md",
    "06-VALIDATION-LEDGER.md", "07-ROLLOUT-AND-MIGRATION.md", "README.md",
)
REQUIRED_DRAFTS = (
    "01-core-providers.md", "02-hosting-gateway-local.md", "03-media-speech-search.md",
    "04-current-state.md",
)
STATUS_STATES = ("implemented", "implemented-unverified", "experimental", "documented", "blocked",
                 "retired", "deferred")


def _fail(problems: list[str], message: str) -> None:
    problems.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    args = parser.parse_args()
    problems: list[str] = []
    checks: list[str] = []

    for name in REQUIRED_DOCS:
        path = PACKAGE / name
        if not path.is_file():
            _fail(problems, f"missing document: {path.relative_to(ROOT)}")
        elif path.stat().st_size < 400:
            _fail(problems, f"document is too small to carry evidence: {name}")
        else:
            checks.append(f"document {name}")

    for name in REQUIRED_DRAFTS:
        path = DRAFTS / name
        if not path.is_file():
            _fail(problems, f"missing research draft: {path.relative_to(ROOT)}")
        elif sum(1 for _ in path.open(encoding="utf-8")) < 100:
            _fail(problems, f"research draft is not substantial: {name}")
        else:
            checks.append(f"draft {name}")

    if not PROVIDERS.is_file():
        _fail(problems, "missing src/hutch/data/providers.json")
        providers = []
    else:
        providers = json.loads(PROVIDERS.read_text())["providers"]
        checks.append(f"provider catalogue ({len(providers)} identities)")

    matrix_path = PACKAGE / "03-PROVIDER-CAPABILITY-MATRIX.md"
    matrix = matrix_path.read_text() if matrix_path.is_file() else ""
    start, end = matrix.find("<!--MATRIX:START-->"), matrix.find("<!--MATRIX:END-->")
    if start == -1 or end == -1 or end <= start:
        _fail(problems, "capability matrix has no generated row block")
        block = ""
    else:
        block = matrix[start:end]
    rows = [line for line in block.splitlines() if line.startswith("| ") and not line.startswith("| Provider")]
    ids = {row.get("id") for row in providers}
    missing = sorted(provider_id for provider_id in ids if f"| {provider_id} |" not in block)
    if missing:
        _fail(problems, "capability matrix misses provider(s): " + ", ".join(missing))
    else:
        checks.append(f"capability matrix covers {len(ids)} provider identities")

    live_rows = [row for row in rows if not row.rstrip().endswith("not live-verified |")]
    if len(rows) != len(providers):
        _fail(problems, f"capability matrix has {len(rows)} rows for {len(providers)} providers")
    if live_rows:
        _fail(problems, f"{len(live_rows)} matrix row(s) claim something other than not live-verified")
    else:
        checks.append("no matrix row claims live verification")

    ledger = (PACKAGE / "06-VALIDATION-LEDGER.md").read_text() if (PACKAGE / "06-VALIDATION-LEDGER.md").is_file() else ""
    for needle in ("BLOCKED", "no provider credentials", "not live-verified"):
        if needle not in ledger:
            _fail(problems, f"validation ledger does not record: {needle}")

    register = (PACKAGE / "01-RESEARCH-REGISTER.md").read_text() if (PACKAGE / "01-RESEARCH-REGISTER.md").is_file() else ""
    links = len(re.findall(r"https://[^\s)<>]+", register))
    if links < 20:
        _fail(problems, f"research register has only {links} HTTPS sources")
    else:
        checks.append(f"research register sources ({links} HTTPS links)")

    statuses = {provider.get("integration_status") for provider in providers}
    unknown = sorted(status for status in statuses if status not in STATUS_STATES)
    if unknown:
        _fail(problems, "catalogue uses unknown integration status: " + ", ".join(unknown))
    else:
        checks.append("catalogue statuses are from the closed vocabulary")

    if (PACKAGE / "artifacts" / "live-verification").exists() and "live-verified" not in matrix:
        _fail(problems, "a live-verification artifact exists but the matrix does not record it")

    result = {"ok": not problems, "checks": checks, "problems": problems}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for check in checks:
            print(f"PASS {check}")
        for problem in problems:
            print(f"FAIL {problem}")
        print("RESULT:", "PASS" if not problems else f"FAIL ({len(problems)} problem(s))")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
