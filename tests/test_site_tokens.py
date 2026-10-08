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


@pytest.mark.skipif(not CSS.exists(), reason="website tokens not built")
def test_stylesheet_references_only_defined_tokens():
    """A var(--x) with no definition collapses the whole declaration at
    computed-value time, which is how ad-hoc spacing silently creeps in.
    Every reference in the component sheet must resolve against tokens.css."""
    import re

    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", CSS.read_text()))
    used = set(re.findall(r"var\((--[a-z0-9-]+)", (ROOT / "website" / "styles.css").read_text()))
    missing = sorted(used - defined)
    assert not missing, f"undefined token refs in styles.css: {missing}"


@pytest.mark.skipif(not TOKENS.exists(), reason="website tokens not present")
def test_built_tailwind_sheet_is_present():
    """The marketing site ships the compiled Tailwind/DaisyUI sheet.

    `npm run build:css` writes website/app.css from website/src/input.css. The
    built file is committed so the page stays a static, no-build surface; this
    guards against shipping markup whose utility classes have no CSS behind
    them.
    """
    app = ROOT / "website" / "app.css"
    assert app.exists(), "website/app.css missing — run `npm run build:css`"
    css = app.read_text().replace(" ", "")
    assert "--color-primary:#34d399" in css
    assert "--radius-field:0rem" in css
    for component in (".btn{", ".badge{", ".card{", ".navbar{", ".table{", ".collapse{"):
        assert component in css, f"{component} missing from built sheet"


@pytest.mark.skipif(not TOKENS.exists(), reason="website tokens not present")
def test_local_site_images_are_content_pinned():
    """Updated product captures must not be hidden behind a stale browser cache."""
    import hashlib
    import re

    site = ROOT / "website"
    html = (site / "index.html").read_text()
    for name in ("assets/captures/setup-desktop.webp", "assets/captures/setup-phone.webp"):
        digest = hashlib.sha256((site / name).read_bytes()).hexdigest()[:8]
        assert re.search(rf"{re.escape(name)}\?v={digest}(?:\s|\")", html), name


@pytest.mark.skipif(not TOKENS.exists(), reason="website tokens not present")
def test_tokens_declare_contrast_pairs():
    import json

    raw = json.loads(TOKENS.read_text())
    pairs = [tuple(p) for p in raw["color"]["verify"]["$extensions"]["site.textPairs"]]
    assert len(pairs) >= 10
    assert ("color.semantic.text", "color.semantic.bg") in pairs
    assert ("color.semantic.on-brand", "color.semantic.brand") in pairs
