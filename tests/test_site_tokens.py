"""Website token source (website/tokens.json) must compile cleanly and stay in sync.

`scripts/build_site_tokens.py` resolves references, detects cycles and duplicate
names, verifies the declared text/background contrast pairs, and writes
website/tokens.css. `--check` fails on drift, so a hand-edited tokens.css
cannot silently diverge from the source.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "website" / "tokens.json"
CSS = ROOT / "website" / "tokens.css"
BUILDER = ROOT / "scripts" / "build_site_tokens.py"


@pytest.mark.skipif(not TOKENS.exists(), reason="website tokens not present")
def test_tokens_compile_without_drift():
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not CSS.exists(), reason="website tokens not built")
def test_generated_css_carries_the_brand_accent():
    css = CSS.read_text()
    assert "--color-semantic-brand: #34d399;" in css
    assert "--color-semantic-on-brand: #052e21;" in css
    # shape contract survives generation
    assert "--radius-control: 0px;" in css
    assert "--radius-panel: 8px;" in css
    assert "--radius-chip: 100px;" in css


@pytest.mark.skipif(not TOKENS.exists(), reason="website tokens not present")
def test_tokens_declare_contrast_pairs():
    import json

    raw = json.loads(TOKENS.read_text())
    pairs = [tuple(p) for p in raw["color"]["verify"]["$extensions"]["site.textPairs"]]
    assert len(pairs) >= 10
    assert ("color.semantic.text", "color.semantic.bg") in pairs
    assert ("color.semantic.on-brand", "color.semantic.brand") in pairs
