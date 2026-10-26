"""Build the native-OS backend into desktop/binaries/backend for Tauri resources."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve() if args.output else root / "desktop/binaries"
    if (output / "backend").exists():
        parser.error("output/backend already exists; choose a fresh output directory to preserve previous build evidence")
    subprocess.run([sys.executable, "-m", "PyInstaller", str(root / "desktop/backend.spec"),
        "--distpath", str(output / "dist"), "--workpath", str(output / "work"),
        "--log-level", "WARN"], cwd=root, check=True)
    shutil.copytree(output / "dist/hutch-backend", output / "backend", symlinks=True)
    print(f"Frozen backend: {output / 'backend'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
