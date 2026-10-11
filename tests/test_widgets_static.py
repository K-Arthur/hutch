"""Static coverage for the widgets lane (src/hutch/server/static/widgets.js).

Offline unit tests: no browser, no network. They pin the wiring between
app.js / index.html / widgets.js / the vendored uPlot build and the golden
block fixtures in tests/fixtures/blocks/, per the typed output-block contract
(docs/research/outputs-block-contract-2026-10-10.md). Where `node` is
available they also run real syntax checks on the JS files.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "src" / "hutch" / "server" / "static"
WIDGETS_JS = STATIC / "widgets.js"
WIDGETS_CSS = STATIC / "widgets.css"
APP_JS = STATIC / "app.js"
INDEX_HTML = STATIC / "index.html"
UPLOT_DIR = STATIC / "vendor" / "uplot"
UPLOT_JS = UPLOT_DIR / "uPlot.iife.min.js"
UPLOT_CSS = UPLOT_DIR / "uPlot.min.css"
FIXTURES = Path(__file__).parent / "fixtures" / "blocks"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def strip_js_comments(src: str) -> str:
    """Remove /*...*/ and //... comments (string-literal aware enough for a
    negative test: we only need URLs inside comments to be exempt)."""
    out, i, n = [], 0, len(src)
    in_str, quote = False, ""
    while i < n:
        c = src[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == quote:
                in_str = False
            i += 1
            continue
        if c in "\"'`":
            in_str, quote = True, c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j == -1 else j
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ── files exist ───────────────────────────────────────────────────────────────

def test_widgets_js_and_css_exist_and_are_nonempty():
    assert WIDGETS_JS.is_file() and len(read(WIDGETS_JS)) > 10_000
    assert WIDGETS_CSS.is_file() and len(read(WIDGETS_CSS)) > 2_000


def test_widgets_js_is_an_iife_defining_hutchwidgets():
    src = read(WIDGETS_JS)
    assert src.startswith("/* Typed output-block widgets")
    assert "(function () {" in src
    assert '"use strict";' in src
    assert "window.HutchWidgets = { renderBlocks, renderBlock, blocksHtml };" in src
    assert src.rstrip().endswith("})();" )


# ── no external URLs anywhere (comments exempt) ───────────────────────────────

@pytest.mark.parametrize("path", [WIDGETS_JS, UPLOT_JS, UPLOT_CSS])
def test_vendored_and_widget_js_reference_no_external_urls(path):
    src = strip_js_comments(read(path))
    assert "http://" not in src, f"{path.name} references an external http URL outside comments"
    assert "https://" not in src, f"{path.name} references an external https URL outside comments"


def test_widgets_js_only_fetches_same_origin_media_urls():
    src = read(WIDGETS_JS)
    fetches = re.findall(r"fetch\(", src)
    assert fetches, "animation sanitizer path should fetch the media store"
    # every fetch in the module goes through the same-origin media URL whitelist
    assert 'fetch(url, { credentials: "same-origin" })' in src
    assert MEDIA_URL_SHAPE in src


MEDIA_URL_SHAPE = "^\\/api\\/v1\\/media\\/(media_[0-9a-f]{16})\\/versions\\/\\d+\\/content$"


# ── index.html wiring ─────────────────────────────────────────────────────────

def test_index_html_references_widgets_assets():
    html = read(INDEX_HTML)
    assert '<link rel="stylesheet" href="/static/widgets.css">' in html
    assert '<script src="/static/vendor/uplot/uPlot.iife.min.js"></script>' in html
    assert '<script src="/static/widgets.js"></script>' in html


def test_index_html_load_order_matches_the_app_js_pattern():
    html = read(INDEX_HTML)
    uplot = html.index('/static/vendor/uplot/uPlot.iife.min.js')
    widgets = html.index('/static/widgets.js')
    app = html.index('/static/app.js')
    assert uplot < widgets < app, "vendor, then widgets.js, then app.js — same classic-script pattern as model-switcher.js"


# ── app.js delegation hook ────────────────────────────────────────────────────

def test_app_js_delegates_to_the_widgets_hook_exactly_once():
    src = read(APP_JS)
    # one call site inside toolLineHtml + one definition appended at file end
    assert src.count("hutchWidgetsFeedItemHtml") == 2
    call_idx = src.index("hutchWidgetsFeedItemHtml(res ? res.d : null")
    def_idx = src.index("function hutchWidgetsFeedItemHtml(data, helpers)")
    assert call_idx < def_idx, "call site lives in the existing renderer; definition is appended"


def test_app_js_hook_returns_empty_string_when_widgets_unavailable():
    src = read(APP_JS)
    assert "if (!widgets || typeof widgets.blocksHtml !== \"function\") return \"\";" in src


def test_app_js_edits_stay_within_the_three_line_budget():
    src = read(APP_JS)
    region = src[src.index("function toolLineHtml"):src.index("/* PF-2 kept the untruncated output")]
    added_delegation_lines = [ln for ln in region.splitlines() if "hutchWidgetsFeedItemHtml" in ln]
    assert len(added_delegation_lines) == 1


# ── every golden fixture kind has a renderer branch + unknown fallback ────────

def renderer_dispatch_body() -> str:
    src = read(WIDGETS_JS)
    start = src.index("const RENDERERS = {")
    end = src.index("};", start)
    return src[start:end]


@pytest.mark.parametrize("fixture", sorted(p for p in FIXTURES.glob("*.json")))
def test_every_golden_fixture_kind_has_a_renderer_branch(fixture):
    block = json.loads(fixture.read_text(encoding="utf-8"))
    kind = block.get("kind")
    if not kind:
        pytest.skip(f"{fixture.name} has no kind (invalid fixture)")
    assert re.search(rf"^\s+{re.escape(kind)}:\s+\w+,?\s*$", renderer_dispatch_body(), re.M), (
        f"kind '{kind}' from {fixture.name} has no entry in the RENDERERS dispatch"
    )


def test_unknown_kind_and_broken_blocks_get_a_labeled_fallback():
    src = read(WIDGETS_JS)
    assert "could not be rendered" in src                     # the labeled panel copy
    assert "unsupported block kind" in src                    # unknown-kind branch
    assert "block_errors" in src or "Output block rejected" in src
    # the #14541 rule: fallback text + error are never erased
    assert "text_fallback" in src


def test_widget_state_is_keyed_by_block_id_in_localstorage():
    src = read(WIDGETS_JS)
    assert '"widgets:"' in src
    assert src.count("store.get(`") >= 5                      # open/closed + filters + sorts are stored


# ── vendored uPlot ────────────────────────────────────────────────────────────

def test_uplot_is_vendored_pinned_and_documented():
    assert UPLOT_JS.is_file() and UPLOT_JS.stat().st_size > 30_000
    assert UPLOT_CSS.is_file()
    banner = read(UPLOT_JS).splitlines()[0]
    assert "1.6.32" in banner, f"unexpected uPlot banner: {banner!r}"
    readme = read(UPLOT_DIR / "README.md")
    assert "1.6.32" in readme and "jsdelivr" in readme
    assert (UPLOT_DIR / "LICENSE").is_file()
    assert "MIT License" in read(UPLOT_DIR / "LICENSE")


def test_uplot_is_a_classic_script_iife_defining_the_global():
    head = read(UPLOT_JS)[:200].replace(" ", "").replace("\n", "")
    assert "varuPlot=function()" in head


def test_uplot_min_css_is_scoped_and_referenceable():
    css = read(UPLOT_CSS)
    assert ".uplot" in css


# ── renderer content rules (static) ───────────────────────────────────────────

def test_renderers_escape_everything_and_never_trust_raw_data():
    src = read(WIDGETS_JS)
    assert "const esc = s =>" in src                          # own local esc, skills.js pattern
    # payload JSON rides along inertly, script-breaking characters escaped
    assert "safeJson" in src and "\\u003c" in src


def test_media_renders_only_from_the_whitelisted_content_url_pattern():
    src = read(WIDGETS_JS)
    assert "/api/v1/media/" in src
    assert "alt_text" in src                                  # required; missing → failed block
    assert "refusing to render unlabelled media" in src
    assert "playsinline" in src and "preload=\"metadata\"" in src
    assert "autoplay" not in src                              # never autoplays, with or without sound


def test_flowchart_nodes_are_focusable_read_only_inspection():
    src = read(WIDGETS_JS)
    assert 'role="button" tabindex="0"' in src
    assert "read-only" in src.lower()
    assert "Reset view" in src


def test_timeline_filters_declare_themselves_offline():
    src = read(WIDGETS_JS)
    assert "nothing is sent anywhere" in src


def test_comparison_states_are_distinct_words_never_blank():
    src = read(WIDGETS_JS)
    assert '"Unknown"' in src and '"Not applicable"' in src and '"Unsupported"' in src
    assert "ranking_note" in src


def test_widgets_css_uses_shared_tokens_only():
    css = read(WIDGETS_CSS)
    for token in ("--line", "--panel", "--r-panel", "--s-2", "--s-3", "--focus", "--text-2", "--mono"):
        assert token in css, f"widgets.css should consume the shared token {token}"
    # reduced motion is honored twice: media query + the app's Reduce effects override
    assert "prefers-reduced-motion" in css and "reduce-effects" in css
    assert "pointer: coarse" in css and "min-height: 44px" in css


# ── real syntax checks when node is available ─────────────────────────────────

NODE = shutil.which("node")
NEEDS_NODE = pytest.mark.skipif(NODE is None, reason="node not available")


@NEEDS_NODE
@pytest.mark.parametrize("path", [WIDGETS_JS, APP_JS, UPLOT_JS])
def test_node_check_passes(path):
    proc = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, f"node --check {path.name} failed:\n{proc.stderr}"


@NEEDS_NODE
def test_widgets_js_boots_and_renders_every_fixture_offline():
    """Run the IIFE under a DOM stub and render every golden fixture through
    blocksHtml: valid ones produce cards, the invalid one the labeled fallback."""
    smoke = REPO / "tests" / "support" / "widgets_smoke.mjs"
    if not smoke.is_file():
        pytest.fail(f"smoke harness missing: {smoke}")
    proc = subprocess.run([NODE, str(smoke)], capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, f"widgets smoke failed:\n{proc.stdout}\n{proc.stderr}"
