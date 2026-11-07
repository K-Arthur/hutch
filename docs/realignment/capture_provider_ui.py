"""Phase 7 real-stack visual and interaction gate for the provider surfaces.

Starts a real `hutch serve` on a real port against an isolated, populated state directory, drives it with
Playwright Chromium and records, per page and width: console errors, failed requests, horizontal overflow,
document height and a screenshot. It then runs interaction scenarios (filtering, keyboard traversal, the
route wizard, the route picker, media jobs, Strict Offline) and an axe-core pass.

  uv run --frozen --no-sync python docs/realignment/capture_provider_ui.py \
      --state ~/.hutch-tmp/provider-phase7/state --port 18896 \
      --axe /path/to/axe-core/axe.min.js --out docs/realignment/artifacts/provider-expansion-2026-11/phase7

The workspace is dark-only by product decision (ADR-0037), so captures are dark; the marketing site owns the
light/dark gate. Credentials in the state are placeholders and the run fails if one appears in any page.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from capture_provider_ui_scenarios import SCENARIOS, Gate

ROOT = Path(__file__).resolve().parents[2]
VIEWPORTS = (("360", 360, 800), ("768", 768, 1000), ("1280", 1280, 900), ("1920", 1920, 1080))
PLACEHOLDER_KEYS = {"deepseek-work": "sk-ui-capture-placeholder-deepseek", "openai-api": ""}


def seed_state(state: Path) -> None:
    """A populated but credential-free-in-reality state: two accounts, one with a placeholder key."""
    sys.path.insert(0, str(ROOT / "src"))
    os.environ["HUTCH_STATE_DIR"] = str(state)
    from hutch.connections import ConnectionBook
    book = ConnectionBook(state)
    book.add("deepseek", name="deepseek-work")
    book.set_key("deepseek-work", PLACEHOLDER_KEYS["deepseek-work"])
    book.add("openai-api", name="openai-api")
    book.add("opencode-go", name="opencode-go")


def start_server(state: Path, port: int) -> subprocess.Popen:
    env = {**os.environ, "HUTCH_STATE_DIR": str(state), "PYTHONPATH": str(ROOT / "src"), "HUTCH_SANDBOX": "off"}
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY"):
        env.pop(name, None)
    cli = ["-c", "from hutch.cli import app; app()"]
    subprocess.run([sys.executable, *cli, "init"], cwd=ROOT, env=env, check=True, capture_output=True, timeout=180)
    server = subprocess.Popen([sys.executable, *cli, "serve", "--port", str(port)], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/providers", timeout=2).read()
            return server
        except Exception:
            time.sleep(0.5)
    server.kill()
    raise SystemExit("server did not start: " + server.stderr.read().decode()[-600:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--port", type=int, default=18896)
    parser.add_argument("--out", required=True)
    parser.add_argument("--axe", default="", help="path to axe-core axe.min.js (not a Hutch dependency)")
    parser.add_argument("--only", default="", help="comma-separated scenario names")
    args = parser.parse_args()
    state, out = Path(args.state).expanduser(), Path(args.out)
    state.mkdir(parents=True, exist_ok=True)
    if any(state.iterdir()):
        raise SystemExit(f"refusing to run: {state} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    seed_state(state)
    server = start_server(state, args.port)
    gate = Gate(origin=f"http://127.0.0.1:{args.port}", out=out, viewports=VIEWPORTS,
                axe_path=args.axe, secrets=[v for v in PLACEHOLDER_KEYS.values() if v], state=state)
    wanted = {name for name in args.only.split(",") if name}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for name, scenario in SCENARIOS.items():
                if not wanted or name in wanted:
                    scenario(gate, browser)
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    gate.finish()
    return 0 if gate.passed else 1


if __name__ == "__main__":
    sys.exit(main())
