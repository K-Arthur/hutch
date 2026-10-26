"""Build the native-OS backend into desktop/binaries/backend for Tauri resources."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--oauth-apps", type=Path, help="Publisher-owned public OAuth application configuration")
    parser.add_argument("--require-oauth", nargs="*", choices=["google", "microsoft"], default=[],
                        help="Refuse packaging unless these publisher app registrations are supplied")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve() if args.output else root / "desktop/binaries"
    if (output / "backend").exists():
        parser.error("output/backend already exists; choose a fresh output directory to preserve previous build evidence")
    from hutch.oauth_apps import MAX_CONFIG_BYTES, validate_oauth_apps
    oauth_source = args.oauth_apps or root / "src/hutch/data/oauth-apps.json"
    try:
        with oauth_source.open("rb") as stream:
            oauth = validate_oauth_apps(stream.read(MAX_CONFIG_BYTES + 1), required=tuple(args.require_oauth))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    inputs = output / "build-inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    oauth_path = inputs / "oauth-apps.json"
    oauth_path.write_text(json.dumps(oauth, indent=2) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "PyInstaller", str(root / "desktop/backend.spec"),
        "--distpath", str(output / "dist"), "--workpath", str(output / "work"),
        "--log-level", "WARN"], cwd=root, check=True,
        env={**os.environ, "HUTCH_BUILD_OAUTH_APPS": str(oauth_path)})
    shutil.copytree(output / "dist/hutch-backend", output / "backend", symlinks=True)
    print(f"Frozen backend: {output / 'backend'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
