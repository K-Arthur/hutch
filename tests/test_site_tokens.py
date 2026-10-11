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
    # Shared Studio, server-page, and marketing geometry stays in sync.
    assert "--color-semantic-surface: #080c12;" in css
    assert "--color-semantic-border: rgba(255,255,255,0.07);" in css
    assert "--color-semantic-border-emphasis: rgba(255,255,255,0.22);" in css
    assert "--color-semantic-focus-ring: #60a5fa;" in css
    assert "--radius-control: 8px;" in css
    assert "--radius-panel: 12px;" in css
    assert "--radius-chip: 100px;" in css


@pytest.mark.skipif(not CSS.exists(), reason="website tokens not built")
def test_shared_operator_tokens_are_generated_from_the_same_source():
    shared = ROOT / "src/hutch/server/static/brand-tokens.css"
    assert shared.read_text() == CSS.read_text()


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


@pytest.mark.skipif(not CSS.exists(), reason="website tokens not built")
def test_studio_stylesheet_references_only_defined_tokens():
    """Studio equivalent of the stylesheet token guard.

    A fallback-less var(--x) that resolves nowhere does not fall back to an
    earlier rule — it computes to the property's initial (or inherited) value,
    so a renamed radius or surface token silently squares corners and clears
    backgrounds. Every fallback-less reference in the app-authored sheets must
    resolve to a definition in the Studio sheets, an @property declaration in
    the generated daisyUI sheet, or an element-scoped inline setter in the
    app templates/scripts. References with an explicit fallback are allowed to
    rely on it (that is how daisyUI exposes per-component hooks).
    """
    import re

    static = ROOT / "src/hutch/server/static"
    definition_files = ["ui.css", "brand-tokens.css", "style.css", "model-switcher.css"]
    inline_files = ["app.js", "model-switcher.js", "index.html"]
    defined: set[str] = set()
    for name in definition_files + inline_files:
        path = static / name
        if not path.exists():
            continue
        text = path.read_text()
        defined |= set(re.findall(r"(--[a-z0-9-]+)\s*:", text))
        defined |= set(re.findall(r"@property\s*(--[a-z0-9-]+)", text))
    missing: list[str] = []
    for name in ["style.css", "model-switcher.css"]:
        text = (static / name).read_text()
        for match in re.finditer(r"var\(\s*(--[a-z0-9-]+)\s*(,)?", text):
            token, has_fallback = match.group(1), bool(match.group(2))
            if token not in defined and not has_fallback:
                line = text[: match.start()].count("\n") + 1
                missing.append(f"{name}:{line}: {token}")
    assert not missing, "undefined fallback-less token refs:\n" + "\n".join(missing)


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
    assert "--color-primary:var(--color-semantic-brand)" in css
    assert "--color-base-200:var(--color-semantic-surface)" in css
    assert "--radius-field:.5rem" in css
    assert "--radius-box:.75rem" in css
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
