"""Record native-test identity without environment, credentials or personal paths."""
from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import re
import sys


def validate_target(target: str, report: dict) -> None:
    expected = {"linux-x64": ("Linux", "x64"), "windows-x64": ("Windows", "x64"),
                "macos-arm64": ("Darwin", "arm64"), "macos-x64": ("Darwin", "x64")}
    machine = report["machine"].lower()
    arch = "x64" if machine in ("x86_64", "amd64") else "arm64" if machine in ("arm64", "aarch64") else "unknown"
    if target not in expected or expected[target] != (report["system"], arch) or report["python_bits"] != 64:
        raise ValueError("native runner does not match its selected operating system and architecture")
    if report["system"] == "Linux" and report["os_version"] != "ubuntu 24.04":
        raise ValueError("Linux native checks require Ubuntu 24.04, not only a matching runner label")
    if report["system"] == "Darwin":
        try:
            supported = int(report["os_version"].split(".")[0]) >= 14
        except (ValueError, IndexError):
            supported = False
        if not supported:
            raise ValueError("macOS native checks require version 14 or later")


def os_version() -> str:
    if platform.system() == "Darwin":
        return platform.mac_ver()[0]
    if platform.system() == "Windows":
        return platform.win32_ver()[1]
    if platform.system() == "Linux":
        try:
            data = platform.freedesktop_os_release()
            return f"{data.get('ID', '')} {data.get('VERSION_ID', '')}".strip()
        except OSError:
            return "unknown"
    return platform.release()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--emit", type=Path)
    args = parser.parse_args()
    if args.emit is not None:
        # Fixed owned filenames only. Logs avoid artifact/cache quota charges.
        for name in ("host.json", "python.xml", "process-guard.log"):
            path = args.emit / name
            print(f"Native evidence: {name}")
            try:
                with path.open("rb") as stream:
                    raw = stream.read(1_000_001)
            except FileNotFoundError:
                print("Not produced; the preceding check did not complete.")
                continue
            if len(raw) > 1_000_000:
                parser.error("native evidence exceeded the bounded log size")
            print(raw.decode("utf-8", errors="replace"))
        return 0
    commit = os.environ.get("HUTCH_SOURCE_COMMIT", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        parser.error("HUTCH_SOURCE_COMMIT must identify the tested source commit")
    report = {
        "contract_version": 1,
        "commit": commit,
        "system": platform.system(),
        "release": platform.release(),
        "os_version": os_version(),
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
    target = os.environ.get("HUTCH_NATIVE_TARGET", "")
    if target:
        try:
            validate_target(target, report)
        except ValueError as exc:
            parser.error(str(exc))
        report["target"] = target
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
