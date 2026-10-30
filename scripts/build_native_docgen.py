#!/usr/bin/env python3
"""Build and install the optional native XLSX write kernel.

The kernel is a PyO3 extension module (``native/docgen_xlsx``). It is optional: the
pure-Python generator in ``src/hutch/documents/docgen/xlsx.py`` stays the reference
implementation and fallback, and hutch works when the module is absent.

Usage (run with the project venv interpreter, e.g. `.venv/bin/python`)::

    python scripts/build_native_docgen.py            # build + install
    python scripts/build_native_docgen.py --check    # build + install + smoke test
    python scripts/build_native_docgen.py --clean    # remove build artifacts + installed module

Cargo is not run from the home directory: `CARGO_HOME` and `CARGO_TARGET_DIR` live
inside this checkout (`.cargo-home` / `.cargo-target`, both git-excluded) so a build
works on a host whose `$HOME/.cargo` is read-only and survives tool calls that reset
`/tmp`. `PYO3_PYTHON` defaults to the interpreter running this script, which must be
the interpreter that will import the extension (matching CPython major.minor).

Exit codes: 0 success, 1 build/install/smoke failure, 2 missing cargo.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRATE_DIR = ROOT / "native" / "docgen_xlsx"
NATIVE_DIR = ROOT / "src" / "hutch" / "documents" / "docgen" / "_native"
CARGO_HOME = ROOT / ".cargo-home"
CARGO_TARGET_DIR = ROOT / ".cargo-target"
MODULE_NAME = "hutch_docgen_native"


def _artifact_and_destination() -> tuple[Path, Path]:
    """Map the platform's cargo cdylib output name to Python's extension-module name."""
    if sys.platform == "win32":
        return (
            CARGO_TARGET_DIR / "release" / f"{MODULE_NAME}.dll",
            NATIVE_DIR / f"{MODULE_NAME}.pyd",
        )
    if sys.platform == "darwin":
        # Python extension modules use .so on macOS even though cargo emits a .dylib.
        return (
            CARGO_TARGET_DIR / "release" / f"lib{MODULE_NAME}.dylib",
            NATIVE_DIR / f"{MODULE_NAME}.so",
        )
    return (
        CARGO_TARGET_DIR / "release" / f"lib{MODULE_NAME}.so",
        NATIVE_DIR / f"{MODULE_NAME}.so",
    )


def build_environment() -> dict[str, str]:
    """Cargo environment that keeps every build cache inside the checkout."""
    cargo = shutil.which("cargo")
    if cargo is None:
        raise SystemExit("build_native_docgen: cargo not found on PATH; install Rust 1.83+")
    env = dict(os.environ)
    env["CARGO_HOME"] = str(CARGO_HOME)
    env["CARGO_TARGET_DIR"] = str(CARGO_TARGET_DIR)
    env.setdefault("PYO3_PYTHON", sys.executable)
    env.setdefault("CARGO_NET_RETRY", "3")
    return env


def build_release(env: dict[str, str]) -> None:
    command = ["cargo", "build", "--release", "--locked", "--features", "python"]
    print(f"build_native_docgen: {' '.join(command)}  (cwd={CRATE_DIR})", flush=True)
    completed = subprocess.run(command, cwd=CRATE_DIR, env=env)
    if completed.returncode != 0:
        raise SystemExit(f"build_native_docgen: cargo build failed (exit {completed.returncode})")


def install_extension() -> Path:
    source, destination = _artifact_and_destination()
    if not source.is_file():
        raise SystemExit(
            f"build_native_docgen: cargo did not produce {source}; "
            "check the crate lib target name"
        )
    NATIVE_DIR.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    shutil.copy2(source, destination)
    print(f"native docgen extension: {destination}", flush=True)
    return destination


def _load_extension(destination: Path):
    spec = importlib.util.spec_from_file_location(MODULE_NAME, destination)
    if spec is None or spec.loader is None:
        raise SystemExit(f"build_native_docgen: cannot load {destination} as a Python extension")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def smoke_test(destination: Path) -> None:
    """Import the installed module from its real location and round-trip one workbook."""
    module = _load_extension(destination)
    if not hasattr(module, "write_workbook"):
        raise SystemExit("build_native_docgen: extension module has no write_workbook()")
    spec_json = json.dumps(
        {
            "sheets": [
                {
                    "name": "Smoke",
                    "header": ["label", "value"],
                    "rows": [[["str", "007"], ["num", 1.5]]],
                    "col_widths": [8.0, 12.0],
                }
            ]
        }
    )
    data = module.write_workbook(spec_json)
    if not isinstance(data, bytes) or not data.startswith(b"PK\x03\x04"):
        raise SystemExit("build_native_docgen: smoke write did not return xlsx bytes")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        workbook_xml = archive.read("xl/workbook.xml")
    if b'fullCalcOnLoad="1"' not in workbook_xml:
        raise SystemExit("build_native_docgen: smoke workbook is missing fullCalcOnLoad")
    try:
        module.write_workbook('{"sheets": []}')
    except ValueError:
        pass
    else:
        raise SystemExit("build_native_docgen: invalid spec did not raise ValueError")
    print(
        f"smoke test: ok ({len(data)} bytes, version {getattr(module, '__version__', '?')})",
        flush=True,
    )


def clean() -> None:
    for path in (CARGO_TARGET_DIR, NATIVE_DIR, CARGO_HOME):
        if path.exists():
            shutil.rmtree(path)
            print(f"removed {path}", flush=True)
        else:
            print(f"absent {path}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and install the optional native XLSX write kernel.",
        epilog="The extension is optional: without it hutch uses the pure-Python XlsxWriter path.",
    )
    parser.add_argument(
        "--check", action="store_true", help="build, install, then import and smoke-test"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove .cargo-target, .cargo-home and the installed module",
    )
    args = parser.parse_args(argv)
    if args.clean:
        clean()
        return 0
    env = build_environment()
    build_release(env)
    destination = install_extension()
    if args.check:
        smoke_test(destination)
    else:
        print(
            "hint: pass --check to import the installed module and round-trip a smoke workbook",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
