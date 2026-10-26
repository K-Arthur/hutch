"""Record native-test identity without environment, credentials or personal paths."""
from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import re
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commit = os.environ.get("HUTCH_SOURCE_COMMIT", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        parser.error("HUTCH_SOURCE_COMMIT must identify the tested source commit")
    report = {
        "contract_version": 1,
        "commit": commit,
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_bits": 64 if sys.maxsize > 2**32 else 32,
        "scope": "kernel locks and skills registry; OS vault on Windows/macOS; Job Object on Windows only",
        "limitations": [
            "Not an installed desktop-package or GUI result",
            "Windows Server is not Windows 11 acceptance",
            "macOS 15 Intel is not macOS 14 Intel acceptance",
            "Non-Windows Rust process-guard has no supervision tests yet",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
